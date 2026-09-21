"""Harness self-checks: the guards that keep local, CI and Render from silently diverging.

Each test here exists because the guard it covers was missing when CI first ran (2026-09-21):
an undeclared dependency and an "there is no internet in tests" assumption both passed locally
and failed on GitHub. These tests fail *here* if a guard is switched off.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOLDOUT = REPO / "reports" / "v2" / "holdout"
LOCKS = ("requirements/constraints.txt", "requirements/dev.txt", "requirements/serve.txt")


# --- 1. tests never reach the public network ---------------------------------------------------


def test_public_network_is_blocked_for_tests() -> None:
    # pytest-socket is armed via addopts; with --allow-hosts a connect to any other host is
    # refused (SocketConnectBlockedError) before a packet leaves the machine.
    from pytest_socket import SocketConnectBlockedError

    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("192.0.2.1", 80), timeout=1)  # TEST-NET-1, never routable


def test_loopback_stays_allowed_for_test_clients() -> None:
    # The API TestClient and the "cluster unreachable" degrade tests need loopback; a refused
    # connection (nothing listens on port 1) is fine, a pytest-socket block is not.
    from pytest_socket import SocketBlockedError, SocketConnectBlockedError

    try:
        socket.create_connection(("127.0.0.1", 1), timeout=0.2)
    except (SocketBlockedError, SocketConnectBlockedError):  # pragma: no cover — misconfigured
        pytest.fail("loopback must remain allowed (--allow-hosts)")
    except OSError:
        pass


# --- 2. the lock pins the scikit-learn the promoted model was pickled with ---------------------


def _pinned(lock: str) -> str:
    text = (REPO / lock).read_text(encoding="utf-8")
    m = re.search(r"^scikit-learn==([^\s;#]+)", text, flags=re.MULTILINE)
    assert m, f"{lock} does not pin scikit-learn"
    return m.group(1)


def test_manifest_records_library_versions() -> None:
    manifest = json.loads((HOLDOUT / "promoted_model.json").read_text(encoding="utf-8"))
    assert manifest["library_versions"]["scikit-learn"]


def test_every_lock_pins_the_manifest_sklearn_version() -> None:
    manifest = json.loads((HOLDOUT / "promoted_model.json").read_text(encoding="utf-8"))
    recorded = manifest["library_versions"]["scikit-learn"]
    for lock in LOCKS:
        assert _pinned(lock) == recorded, f"{lock} pins {_pinned(lock)}, manifest says {recorded}"


def test_loader_refuses_a_different_sklearn(tmp_path: Path) -> None:
    from ml.forecasting.promoted import PromotedModelUnavailable, load_promoted_model

    shutil.copy(HOLDOUT / "promoted_model.joblib", tmp_path / "promoted_model.joblib")
    manifest = json.loads((HOLDOUT / "promoted_model.json").read_text(encoding="utf-8"))
    manifest["library_versions"] = {"scikit-learn": "0.0.0"}
    (tmp_path / "promoted_model.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PromotedModelUnavailable, match=r"pickled with scikit-learn 0\.0\.0"):
        load_promoted_model(tmp_path)


def test_loader_refuses_a_manifest_without_versions(tmp_path: Path) -> None:
    from ml.forecasting.promoted import PromotedModelUnavailable, load_promoted_model

    shutil.copy(HOLDOUT / "promoted_model.joblib", tmp_path / "promoted_model.joblib")
    manifest = json.loads((HOLDOUT / "promoted_model.json").read_text(encoding="utf-8"))
    del manifest["library_versions"]
    (tmp_path / "promoted_model.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PromotedModelUnavailable, match="does not record library_versions"):
        load_promoted_model(tmp_path)


def test_manifest_only_stays_loadable_without_the_pickle(tmp_path: Path) -> None:
    # No joblib on disk -> nothing to mistrust; the manifest alone loads as non-servable.
    from ml.forecasting.promoted import load_promoted_model

    manifest = json.loads((HOLDOUT / "promoted_model.json").read_text(encoding="utf-8"))
    del manifest["library_versions"]
    (tmp_path / "promoted_model.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert load_promoted_model(tmp_path).is_servable is False


def test_committed_model_loads_under_the_installed_sklearn() -> None:
    # With the environment installed from the lock this is the real serving path; a floating
    # scikit-learn fails here with the loader's message rather than a silent sklearn warning.
    from ml.forecasting.promoted import load_promoted_model

    assert load_promoted_model(HOLDOUT).is_servable


# --- 3. the final audit does not dirty the tree it verifies -----------------------------------


def test_final_audit_keeps_the_file_when_only_the_run_stamp_changed(tmp_path: Path) -> None:
    from scripts.v2_final_audit import write_if_changed

    path = tmp_path / "claim_matrix.json"
    first = {"run_id": "run_a", "freshness": "t0", "verdict": "V2_COMPLETE", "n_artifacts": 45}
    assert write_if_changed(path, first) is True
    before = path.read_bytes()

    same_content = {**first, "run_id": "run_b", "freshness": "t1"}
    assert write_if_changed(path, same_content) is False
    assert path.read_bytes() == before

    changed = {**same_content, "n_artifacts": 46}
    assert write_if_changed(path, changed) is True
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "run_b"
