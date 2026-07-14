# V1 — News Collection & How News Affects the Forecast

How to collect **real** news, and how a news item propagates into the demand forecast and the
recommendation. Two paths: an offline deterministic fixture (default, for Demo/tests) and an
opt-in **live GDELT** collector (real internet).

## 1. Collect real news (opt-in, live)

GDELT's DOC 2.0 API is free and key-less. The collector is disabled by default so Demo/tests stay
offline; enable it explicitly:

```bash
make v1-collect-news-live                 # ENABLE_GDELT_LIVE=true, default query + recent window
# or a specific window (UTC):
ENABLE_GDELT_LIVE=true python -m pipelines.collectors.collect_live_news \
    --live --start 20260601000000 --end 20260701000000 --stamp 2026-06
```

It fetches, filters, deduplicates (url + normalised-title hash), and **snapshots** the accepted
articles to `data/fixtures/news_live/news_gdelt_<stamp>.jsonl` (git-ignored — generated). The rest
of the pipeline then runs deterministically off that snapshot.

**What GDELT gives:** title + metadata (domain, seen-date) only — **no article body**. So `text` is
left empty (a title-only snippet, never fabricated), and `seendate` is used for `published_at` /
`first_seen_at` (documented approximation). The availability rule still holds:
`available_at = max(published_at, first_seen_at)`.

## 2. Honest caveat — real news is noisy

Keyword collection over the whole web has a low signal-to-noise ratio for a small area. A tighter,
Jersey-City-anchored, mobility-specific query (`config/backfill.py::DEFAULT_GDELT_QUERY`) returns
mostly-relevant June-2026 items (e.g. Hudson Place ribbon-cutting, NJ commuting, World-Cup-2026 fan
zones, Hoboken) **mixed with keyword false positives**. That is a genuine property of the source, so:

- The **coverage gate** (`pipelines/collectors/coverage.py`) reports the real accepted count and
  passes/fails honestly; a broad query that yields mostly noise **fails the gate**, which keeps the
  accuracy claim disabled (§7) — we never rewrite or hand-pick the data.
- GDELT already location/topic-matches the full text server-side, so the live path trusts the query
  and skips a redundant title-only re-filter; the fixture path keeps the ontology+city filter.

## 3. How a news item affects the forecast

```text
Article (title, source, available_at)
  → LLM event extraction        (pipelines/events): event_type, severity, confidence,
                                 demand_effect, evidence spans — never a numeric demand %
  → Event graph                 (pipelines/graph): Article→Event→Place→H3Zone, idempotent upsert
  → as-of graph features        (pipelines/features/graph_features): event_count, distance-decayed
                                 impact, transit_disruption_exposure, neighbor_zone_impact, …
                                 built ONLY from events with available_at ≤ forecast_cutoff
  → forecast                    M1 (event-aware) vs M0 (baseline) vs M1-zero (event features
                                 zeroed) → the model-attributed event delta (not causal)
  → recommendation / rebalancing  the delta raises a zone's demand → steer riders / move bikes
```

A news item only moves the forecast when its `available_at ≤ cutoff` (no leakage) and it maps to a
served H3 zone. The effect is **model-attributed**, never claimed as causal.

## 3b. FAISS vector store — accumulating news

As real-time collection accumulates news, a **persistent FAISS vector store** (`ml/vectorstore/`)
indexes an embedding per article for semantic search, near-duplicate detection (stronger than the
exact title hash), and same-event grouping. It is offline by default (a deterministic char-n-gram
**lexical embedder** — no external model download) and **accumulates across runs**: `add` is
idempotent on `article_id`, and the index + metadata persist under `data/processed/vectorstore/`.
`make v1-collect-news-live` upserts each collection into it automatically.

```bash
make v1-news-vectorstore          # demo: semantic search + near-dup + persistence (offline)
pip install -e .[vectorstore]     # installs faiss-cpu (optional extra)
```

The same FAISS path is available to the recommendation retriever (`ml/recsys/index.py::FaissIndex`,
an `IndexFlatIP` whose Top-K equals the default `ExactTorchIndex` — verified in tests). It earns its
keep at scale (approximate indexes); the small 251-station demo still uses the exact index.

## 4. Why the demo shows a zero event effect

The bundled curated events sit on 2026-07-12, but the measured trip data is **June 2026** — they do
not overlap, so on that data the event features are legitimately zero (`insufficient_event_overlap`;
see `docs/STATUS.md`, `reports/v1/recsys/*`). Collecting **June-2026** news with the live path (§1)
is exactly what creates overlapping events so the event-lift can be measured for real (V1-04). Until
that overlap exists and passes the coverage gate, the event-accuracy claim stays `BLOCKED_DATA`.
