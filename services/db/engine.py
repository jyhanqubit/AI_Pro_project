"""Engine construction + schema init. CLAUDE.md §16.

``get_engine`` builds a SQLAlchemy engine from ``DATABASE_URL`` (SQLite default, Postgres via URL).
``init_db`` creates the tables idempotently with ``checkfirst=True`` and never drops anything — a
normal startup is non-destructive (§16).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine

from config.settings import get_settings

from .schema import metadata


def get_engine(url: str | None = None) -> Engine:
    """Create an engine for ``url`` (defaults to ``settings.database_url``).

    For a file-backed SQLite URL the parent directory is created so a first run works out of the
    box. In-memory SQLite (``sqlite://``) and non-SQLite URLs are used as-is.
    """
    url = url or get_settings().database_url
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def init_db(engine: Engine) -> None:
    """Create all tables if absent (idempotent, non-destructive)."""
    metadata.create_all(engine, checkfirst=True)
