"""Graph-store selection. CLAUDE.md §3, §9, §16.

Chooses the backend for graph upserts. Demo Mode stays offline on the in-memory store; a real Neo4j
backend is opt-in and requires the ``[graph]`` extra plus credentials. The forecasting graph
features are pure functions and never depend on this — the graph store is the §9 upsert/audit
surface, not the critical path.
"""

from __future__ import annotations

from config.settings import get_settings

from .store import GraphStore, InMemoryGraphStore


def build_graph_store(backend: str = "auto") -> GraphStore:
    """Return a graph store for the requested backend.

    * ``memory`` — the offline in-memory store (Demo Mode default, always available).
    * ``neo4j`` — a live Neo4j store from settings (``NEO4J_URI`` / ``NEO4J_USER`` /
      ``NEO4J_PASSWORD``); requires the ``[graph]`` extra. Raises a clear error if the password is
      unset or the driver is missing — never silently falls back (an explicit backend is honoured).
    * ``auto`` — ``neo4j`` when ``NEO4J_PASSWORD`` is configured, else ``memory``.
    """
    settings = get_settings()
    if backend == "auto":
        backend = "neo4j" if settings.neo4j_password else "memory"

    if backend == "memory":
        return InMemoryGraphStore()
    if backend == "neo4j":
        if not settings.neo4j_password:
            raise RuntimeError(
                "backend 'neo4j' requires NEO4J_PASSWORD (and NEO4J_URI / NEO4J_USER). "
                "Start Neo4j (docker compose up neo4j) and set the credentials, or use --backend "
                "memory for the offline store."
            )
        from .neo4j_store import Neo4jGraphStore

        return Neo4jGraphStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
    raise ValueError(f"unknown graph backend: {backend!r} (available: 'memory', 'neo4j', 'auto')")
