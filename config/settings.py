"""Typed runtime configuration. CLAUDE.md sections 3 and 16.

Field names match the environment variables in ``.env.example`` (case-insensitive).
Demo defaults are safe and offline-compatible: no external API key is required.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from contracts.enums import OperatingMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    shockflow_mode: OperatingMode = Field(default=OperatingMode.DEMO_FIXTURE)
    enable_gbfs_live: bool = Field(default=False)
    enable_gdelt_live: bool = Field(default=False)
    # "mock" (default, offline) | "anthropic" (Claude) | "openai" (GPT-4o)
    llm_provider: str = Field(default="mock")
    llm_api_key: str | None = Field(default=None)
    # Extraction model for the real (opt-in) Anthropic provider. Demo Mode never uses it.
    llm_model: str = Field(default="claude-opus-4-8")
    # Real (opt-in) OpenAI provider. Prefers openai_api_key, else the SDK reads OPENAI_API_KEY.
    # Demo Mode never uses these.
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str | None = Field(default=None)
    # Relational store (opt-in [rdb] extra). SQLite by default (zero-config, offline); swap to a
    # Postgres URL (postgresql+psycopg://…) without code changes. Demo Mode never requires it.
    database_url: str = Field(default="sqlite:///data/processed/shockflow.db")
    local_tz: str = Field(default="America/New_York")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor for application code."""
    return Settings()
