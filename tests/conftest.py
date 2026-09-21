"""Session-wide harness rules.

Committed artifacts under ``reports/v2/**`` are evidence, not scratch space: several benchmark
runners are exercised by tests via their ``main()``, and each one writes its report to a
module-level output path. Without redirection a test run rewrites committed evidence (at best a
timestamp churn, at worst an environment-specific stub replacing a real measurement, which then
fails the final-audit envelope gate). This fixture points every writer at a per-session sandbox
that starts as a copy of the committed tree, so runners still find their inputs and tests that
read what a runner just wrote read it from the sandbox (via the same module constants).

The audit gates (``scripts.v2_final_audit``, ``ml.monitoring.run_manifest``) keep scanning the
committed tree — that is what they exist to check — only their own output files are redirected.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
V2_REPORTS = REPO / "reports" / "v2"

# (module, attribute, relative path under the sandbox) for every runner that writes a report
_WRITERS: tuple[tuple[str, str, str], ...] = (
    ("ml.copilot.benchmark", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.graphrag_benchmark", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.graphrag_scale", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.neutral_retrieval", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.ragas_generation", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.ragas_retrieval", "OUT_DIR", "reports/v2/copilot"),
    ("ml.copilot.trip_faithfulness", "OUT", "reports/v2/copilot/trip_faithfulness.json"),
    ("ml.copilot.trip_parse_benchmark", "OUT", "reports/v2/copilot/trip_parse_benchmark.json"),
    ("ml.monitoring.run_manifest", "OUT", "reports/v2/monitoring/run_manifest.json"),
    ("ml.monitoring.delayed_labels", "OUT", "reports/v2/monitoring/delayed_labels.json"),
    ("scripts.v2_final_audit", "CLAIM_MATRIX", "reports/v2/final/claim_matrix.json"),
)


@pytest.fixture(scope="session", autouse=True)
def artifact_sandbox(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Redirect every report writer into a sandbox copy of ``reports/v2`` for the whole session."""
    root = tmp_path_factory.mktemp("artifact_sandbox")
    shutil.copytree(V2_REPORTS, root / "reports" / "v2")
    mp = pytest.MonkeyPatch()
    for module, attr, rel in _WRITERS:
        mp.setattr(f"{module}.{attr}", root / rel, raising=True)
    yield root
    mp.undo()
