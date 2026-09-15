"""Load the promoted measured forecasting model for serving (V2-01).

Non-demo modes must serve the **promoted measured model artifact**, not a demo heuristic
(``CLAUDE_V2_APPEND_REVISED.md`` → Productization). This module is the single read path for that
artifact: it loads the manifest written by ``ml.forecasting.h3_multiholdout`` and, when present,
the fitted estimator, and returns them behind a small typed handle.

The manifest (``reports/v2/holdout/promoted_model.json``) always commits; the fitted
``promoted_model.joblib`` is git-ignored (regenerable via ``make v2-holdout``). Serving code
should surface the manifest fields (``run_id``, ``claim_status``, ``freshness``) so every served
number stays traceable to its measured origin.

The API wiring that calls this in a live/replay request lands in **V2-07**; this module is the
contract that wiring depends on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DEFAULT_DIR = Path("reports/v2/holdout")


class PromotedModelUnavailable(RuntimeError):
    """Raised when no promoted-model manifest exists — run ``make v2-holdout`` to produce it."""


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
        try:
            import joblib

            bundle = joblib.load(model_path)
            estimator = bundle.get("estimator")
            features = list(bundle.get("features", []))
            target = bundle.get("target", target)
        except Exception as exc:  # noqa: BLE001 — surface, never silently serve a demo fallback
            raise PromotedModelUnavailable(f"failed to load {model_path}: {exc!r}") from exc

    return PromotedModel(manifest=manifest, estimator=estimator, features=features, target=target)
