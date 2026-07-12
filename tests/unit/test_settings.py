"""Settings tests. CLAUDE.md sections 3 and 16.

Verifies the offline-safe demo defaults and environment overriding.
"""

from __future__ import annotations

import pytest

from config.settings import Settings
from contracts.enums import OperatingMode


def test_defaults_are_offline_safe():
    s = Settings(_env_file=None)
    assert s.shockflow_mode is OperatingMode.DEMO_FIXTURE
    assert s.enable_gbfs_live is False
    assert s.enable_gdelt_live is False
    assert s.llm_provider == "mock"
    assert s.llm_api_key is None
    assert s.local_tz == "America/New_York"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SHOCKFLOW_MODE", "historical_replay")
    monkeypatch.setenv("ENABLE_GBFS_LIVE", "true")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.shockflow_mode is OperatingMode.HISTORICAL_REPLAY
    assert s.enable_gbfs_live is True


def test_invalid_mode_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SHOCKFLOW_MODE", "not_a_mode")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
