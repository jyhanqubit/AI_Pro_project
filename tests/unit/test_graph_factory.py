"""Graph-store backend selection (CLAUDE.md §3, §9, §16).

The factory must keep Demo Mode offline (in-memory) and only reach for Neo4j when explicitly asked
with credentials present — never silently swap backends. No live server or driver is needed here.
"""

from __future__ import annotations

import pytest

from config.settings import Settings
from pipelines.graph import InMemoryGraphStore, build_graph_store
from pipelines.graph import factory as graph_factory


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **kw) -> None:
    base = dict(neo4j_uri="bolt://localhost:7687", neo4j_user="neo4j", neo4j_password=None)
    base.update(kw)
    monkeypatch.setattr(graph_factory, "get_settings", lambda: Settings(**base))


def test_auto_is_in_memory_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, neo4j_password=None)
    assert isinstance(build_graph_store("auto"), InMemoryGraphStore)


def test_memory_backend_is_always_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, neo4j_password="secret")  # even with creds, memory stays memory
    assert isinstance(build_graph_store("memory"), InMemoryGraphStore)


def test_neo4j_without_password_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch, neo4j_password=None)
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        build_graph_store("neo4j")


def test_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_settings(monkeypatch)
    with pytest.raises(ValueError, match="unknown graph backend"):
        build_graph_store("mongodb")
