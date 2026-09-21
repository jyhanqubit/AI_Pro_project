"""Load the promoted measured forecasting model for serving (V2-01).

Non-demo modes must serve the **promoted measured model artifact**, not a demo heuristic
(``CLAUDE_V2_APPEND_REVISED.md`` → Productization). This module is the single read path for that
artifact: it loads the manifest written by ``ml.forecasting.h3_multiholdout`` and, when present,
the fitted estimator, and returns them behind a small typed handle.

The manifest (``reports/v2/holdout/promoted_model.json``) and the fitted
``promoted_model.joblib`` (the one ``*.joblib`` the .gitignore lets through) both commit, so the
served model is exactly the measured one. Serving code should surface the manifest fields
(``run_id``, ``claim_status``, ``freshness``) so every served number stays traceable to its
measured origin.

Version discipline: the joblib is a pickle, and scikit-learn only *warns* when a different
version unpickles it. The manifest therefore records the library versions at fit time
(``library_versions``) and :func:`load_promoted_model` refuses to serve when the installed
scikit-learn differs from the recorded one, or when sklearn's ``InconsistentVersionWarning``
fires anyway. ``requirements/constraints.txt`` pins the lock to the same version.

The API wiring that calls this in a live/replay request lands in **V2-07**; this module is the
contract that wiring depends on.
"""

from __future__ import annotations

import json
import platform
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path("reports/v2/holdout")

# The library whose version decides whether the pickle means the same thing. numpy/python are
# recorded for the audit trail but not enforced (their pickle formats are stable across versions).
ENFORCED_LIBRARY = "scikit-learn"


class PromotedModelUnavailable(RuntimeError):
    """Raised when no promoted-model manifest exists — run ``make v2-holdout`` to produce it."""


def library_versions() -> dict[str, str]:
    """Versions of the libraries that shape the pickled estimator, as the writer records them."""
    import numpy
    import sklearn

    return {
        "scikit-learn": sklearn.__version__,
        "numpy": numpy.__version__,
        "python": platform.python_version(),
    }


def check_library_versions(manifest: dict[str, Any]) -> None:
    """Refuse a manifest whose recorded scikit-learn differs from the installed one."""
    recorded = (manifest.get("library_versions") or {}).get(ENFORCED_LIBRARY)
    if not recorded:
        raise PromotedModelUnavailable(
            "promoted_model.json does not record library_versions['scikit-learn']; the pickle "
            "cannot be trusted across versions — re-promote with `make v2-holdout`."
        )
    installed = library_versions()[ENFORCED_LIBRARY]
    if recorded != installed:
        raise PromotedModelUnavailable(
            f"promoted model was pickled with scikit-learn {recorded} but {installed} is installed; "
            "install from the lock (`make install`, requirements/serve.txt) or re-promote with "
            "`make v2-holdout`."
        )


@dataclass(frozen=True)
class PromotedModel:
    """A loaded promoted model plus the provenance a served result must carry."""

    manifest: dict[str, Any]
    estimator: Any | None  # None when only the manifest is present (joblib not on disk)
    features: list[str]
    target: str

    @property
    def run_id(self) -> str:
        return self.manifest["run_id"]

    @property
    def claim_status(self) -> str:
        return self.manifest["claim_status"]

    @property
    def freshness(self) -> str:
        return self.manifest["freshness"]

    @property
    def is_servable(self) -> bool:
        """True when the fitted estimator is loaded and can produce predictions."""
        return self.estimator is not None


def load_promoted_model(directory: Path | str = _DEFAULT_DIR) -> PromotedModel:
    """Load the promoted-model manifest (+ fitted estimator if present)."""
    directory = Path(directory)
    manifest_path = directory / "promoted_model.json"
    if not manifest_path.exists():
        raise PromotedModelUnavailable(
            f"{manifest_path} missing — run `make v2-holdout` to promote a measured model."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    estimator: Any | None = None
    features: list[str] = []
    target: str = manifest.get("target", "departures")
    model_path = directory / "promoted_model.joblib"
    if model_path.exists():
        check_library_versions(manifest)
        try:
            import joblib
            from sklearn.exceptions import InconsistentVersionWarning

            with warnings.catch_warnings():
                # Belt and braces: even if the manifest lied, sklearn's own version stamp inside
                # the pickle must agree with the installed library.
                warnings.simplefilter("error", InconsistentVersionWarning)
                bundle = joblib.load(model_path)
            estimator = bundle.get("estimator")
            features = list(bundle.get("features", []))
            target = bundle.get("target", target)
        except Exception as exc:  # noqa: BLE001 — surface, never silently serve a demo fallback
            raise PromotedModelUnavailable(f"failed to load {model_path}: {exc!r}") from exc

    return PromotedModel(manifest=manifest, estimator=estimator, features=features, target=target)
