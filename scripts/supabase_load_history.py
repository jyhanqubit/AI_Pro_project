"""Load the repository's historical data into a Postgres (Supabase) or SQLite database.

What goes in (each table keyed so a re-run upserts instead of duplicating):

    events              extracted events from the committed event graph snapshot
                        (data/processed/graph/event_graph.json; `make seed-graph` rebuilds it)
    model_forecasts     the promoted model's next-hour prediction per H3 zone, as served by
                        /v2/model/forecast (run_id + zone_id)
    demand_zone_hour    H3 zone x local hour demand labels (departures, arrivals, net_flow),
                        aggregated from local Citi Bike trip files with the same code the
                        forecasting pipeline uses (`--trips` points at the files; slow for NYC)
    load_runs           one audit row per table per run (source, row count, loaded_at)

Why a script and not the chat connector: these tables run to hundreds of thousands of rows, which
is a job for a direct Postgres connection (`DATABASE_URL`), not for SQL pasted through a tool.

Usage (see supabase/README.md for where the connection string comes from):

    DATABASE_URL='postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres' \\
        python -m scripts.supabase_load_history --events --forecasts
    python -m scripts.supabase_load_history --panel --trips data/raw/citibike --database-url sqlite:///x.db

Every row carries `mode` and a `source`/`run_id` so the data contract's provenance rule holds in the
database as it does in the artifacts. On Postgres the tables get row-level security with a
read-only policy for the API roles, matching the live tables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_SNAPSHOT = REPO_ROOT / "data" / "processed" / "graph" / "event_graph.json"
BATCH = 1000

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("event_id", String, primary_key=True),
    Column("event_type", String, nullable=False),
    Column("title", Text, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("event_start_at", DateTime(timezone=True)),
    Column("event_end_at", DateTime(timezone=True)),
    Column("demand_effect", String),
    Column("capacity_effect", String),
    Column("severity", Float),
    Column("confidence", Float),
    Column("status", String, nullable=False),
    Column("extraction_model", String),
    Column("prompt_version", String),
    Column("zone_ids", Text, nullable=False),  # JSON list of affected H3 zones (may be empty)
    Column("source", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

model_forecasts = Table(
    "model_forecasts",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("zone_id", String, primary_key=True),
    Column("serving_hour", DateTime(timezone=True), nullable=False),
    Column("predicted_departures", Float, nullable=False),
    Column("lat", Float),
    Column("lng", Float),
    Column("model_version", String, nullable=False),
    Column("feature_version", String, nullable=False),
    Column("claim_status", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

demand_zone_hour = Table(
    "demand_zone_hour",
    metadata,
    Column("zone_id", String, primary_key=True),
    Column("hour_start", DateTime(timezone=True), primary_key=True),
    Column("departures", Float, nullable=False),
    Column("arrivals", Float, nullable=False),
    Column("net_flow", Float, nullable=False),
    Column("source", String, nullable=False),
    Column("mode", String, nullable=False),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

load_runs = Table(
    "history_load_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String, nullable=False),
    Column("source", String, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("loaded_at", DateTime(timezone=True), nullable=False),
)

RLS_TABLES = ("events", "model_forecasts", "demand_zone_hour", "history_load_runs")


# --------------------------------------------------------------------------- helpers
def _chunks(rows: Iterable[dict[str, Any]], size: int = BATCH) -> Iterator[list[dict[str, Any]]]:
    buf: list[dict[str, Any]] = []
    for r in rows:
        buf.append(r)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def upsert(engine: Engine, table: Table, rows: Iterable[dict[str, Any]]) -> int:
    """Insert-or-update on the primary key; same semantics on Postgres and SQLite."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:  # pragma: no cover - other dialects are not a target
        raise SystemExit(f"unsupported database dialect: {dialect}")
    pk = [c.name for c in table.primary_key.columns]
    n = 0
    with engine.begin() as conn:
        for batch in _chunks(rows):
            stmt = dialect_insert(table).values(batch)
            update_cols = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk}
            conn.execute(stmt.on_conflict_do_update(index_elements=pk, set_=update_cols))
            n += len(batch)
    return n


def record_load(
    engine: Engine, table_name: str, source: str, row_count: int, now: datetime
) -> None:
    with engine.begin() as conn:
        conn.execute(
            load_runs.insert().values(
                table_name=table_name, source=source, row_count=row_count, loaded_at=now
            )
        )


def count(engine: Engine, table: Table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar() or 0)


def apply_read_only_rls(engine: Engine) -> None:
    """Postgres only: RLS on, read-only policy for the API roles (as the live tables have)."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for name in RLS_TABLES:
            conn.execute(text(f'alter table public."{name}" enable row level security'))
            conn.execute(
                text(
                    f"""
                    do $p$ begin
                      if not exists (select 1 from pg_policies
                                     where schemaname = 'public' and tablename = '{name}'
                                       and policyname = 'public read') then
                        execute 'create policy "public read" on public."{name}" '
                                'for select to anon, authenticated using (true)';
                      end if;
                    end $p$;
                    """
                )
            )


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- sources
def event_rows(snapshot: Path, now: datetime) -> Iterator[dict[str, Any]]:
    """Event nodes of the graph snapshot, with the H3 zones they AFFECT (if any edges exist)."""
    graph = json.loads(snapshot.read_text(encoding="utf-8"))
    affects: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        if e.get("type") == "AFFECTS":
            affects.setdefault(str(e.get("source") or e.get("from")), []).append(
                str(e.get("target") or e.get("to"))
            )
    source = (
        str(snapshot.relative_to(REPO_ROOT))
        if snapshot.is_relative_to(REPO_ROOT)
        else str(snapshot)
    )
    for node in graph.get("nodes", []):
        if node.get("label") != "Event":
            continue
        p = node.get("props", {})
        key = str(node["key"])
        yield {
            "event_id": key,
            "event_type": p.get("event_type", "OTHER"),
            "title": p.get("title", ""),
            "available_at": _ts(p.get("available_at")),
            "event_start_at": _ts(p.get("event_start_at")),
            "event_end_at": _ts(p.get("event_end_at")),
            "demand_effect": p.get("demand_effect"),
            "capacity_effect": p.get("capacity_effect"),
            "severity": float(p["severity"]) if p.get("severity") not in (None, "") else None,
            "confidence": float(p["confidence"]) if p.get("confidence") not in (None, "") else None,
            "status": p.get("status", "unknown"),
            "extraction_model": p.get("extraction_model"),
            "prompt_version": p.get("prompt_version"),
            "zone_ids": json.dumps(sorted(set(affects.get(key, [])))),
            "source": source,
            "mode": "historical_replay",
            "loaded_at": now,
        }


def forecast_rows(now: datetime) -> Iterator[dict[str, Any]]:
    """Every zone's next-hour prediction from the promoted model (the served numbers)."""
    from services.api.model_serving import model_forecast

    out = model_forecast(top=10_000)
    serving_hour = _ts(out.get("serving_hour")) or now
    model = out.get("model") or {}
    for r in out["forecasts"]:
        yield {
            "run_id": out["run_id"],
            "zone_id": r["zone_id"],
            "serving_hour": serving_hour,
            "predicted_departures": float(r["predicted_departures"]),
            "lat": r.get("lat"),
            "lng": r.get("lng"),
            "model_version": str(model.get("algorithm") or "unknown"),
            "feature_version": str(model.get("feature_version") or "unknown"),
            "claim_status": out.get("claim_status", "measured"),
            "mode": out.get("mode", "historical_replay"),
            "loaded_at": now,
        }


def panel_rows(trips: Path, now: datetime) -> Iterator[dict[str, Any]]:
    """H3 zone x local hour demand labels from local trip files (same code as the pipeline)."""
    from ml.forecasting.dataset import load_real_panel

    panel = load_real_panel(trips)
    df = panel.df
    targets = list(panel.target_cols)
    missing = [c for c in ("departures", "arrivals", "net_flow") if c not in df.columns]
    if missing:
        raise SystemExit(f"panel lacks target columns {missing}; targets were {targets}")
    source = str(trips)
    for zone_id, hour_start, dep, arr, net in zip(
        df["zone_id"],
        df["hour_start"],
        df["departures"],
        df["arrivals"],
        df["net_flow"],
        strict=True,
    ):
        hs = hour_start.to_pydatetime() if hasattr(hour_start, "to_pydatetime") else hour_start
        yield {
            "zone_id": str(zone_id),
            "hour_start": hs if hs.tzinfo is not None else hs.replace(tzinfo=UTC),
            "departures": float(dep),
            "arrivals": float(arr),
            "net_flow": float(net),
            "source": source,
            "mode": "historical_replay",
            "loaded_at": now,
        }


# --------------------------------------------------------------------------- main
def run(
    database_url: str,
    *,
    do_events: bool,
    do_forecasts: bool,
    do_panel: bool,
    trips: Path | None,
    graph_snapshot: Path = GRAPH_SNAPSHOT,
) -> dict[str, int]:
    engine = create_engine(database_url)
    metadata.create_all(engine)
    apply_read_only_rls(engine)
    now = datetime.now(UTC)
    loaded: dict[str, int] = {}

    if do_events:
        if not graph_snapshot.exists():
            raise SystemExit(f"{graph_snapshot} missing; run `make seed-graph` first")
        n = upsert(engine, events, event_rows(graph_snapshot, now))
        record_load(engine, "events", str(graph_snapshot), n, now)
        loaded["events"] = n
    if do_forecasts:
        n = upsert(engine, model_forecasts, forecast_rows(now))
        record_load(engine, "model_forecasts", "services.api.model_serving.model_forecast", n, now)
        loaded["model_forecasts"] = n
    if do_panel:
        if trips is None:
            raise SystemExit("--panel needs --trips <file or directory of Citi Bike trip archives>")
        n = upsert(engine, demand_zone_hour, panel_rows(trips, now))
        record_load(engine, "demand_zone_hour", str(trips), n, now)
        loaded["demand_zone_hour"] = n

    totals = {t.name: count(engine, t) for t in (events, model_forecasts, demand_zone_hour)}
    print(f"database: {engine.dialect.name}")
    for name, n in loaded.items():
        print(f"  upserted {name:18s} {n:>8,} rows   (table now {totals[name]:,})")
    engine.dispose()
    return loaded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument(
        "--events", action="store_true", help="load extracted events from the graph snapshot"
    )
    ap.add_argument(
        "--forecasts", action="store_true", help="load the promoted model's zone predictions"
    )
    ap.add_argument(
        "--panel", action="store_true", help="aggregate local trip files into zone x hour demand"
    )
    ap.add_argument("--trips", type=Path, help="trip file or directory for --panel")
    args = ap.parse_args(argv)
    if not args.database_url:
        ap.error("set DATABASE_URL or pass --database-url")
    if not (args.events or args.forecasts or args.panel):
        args.events = args.forecasts = True
    run(
        args.database_url,
        do_events=args.events,
        do_forecasts=args.forecasts,
        do_panel=args.panel,
        trips=args.trips,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
