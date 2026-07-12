"""Base model for all data contracts.

CLAUDE.md requires typed contracts at service and pipeline boundaries (section 6) and
timezone-aware timestamps everywhere (section 5.1). Timezone-awareness is enforced by
annotating datetime fields with pydantic's ``AwareDatetime`` type in each model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Strict base: unknown fields are rejected so contract drift fails loudly."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=False,
    )
