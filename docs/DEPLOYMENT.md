# Deployment Guide

How to run ShockFlow AI beyond the offline demo — including the features that need outbound network
access (live news sync, optional Elasticsearch, optional real LLM extraction).

The default configuration is **offline and safe**: it runs entirely on bundled fixtures with no API
keys. Live features are opt-in and degrade gracefully when their dependency is unavailable.

---

## 1. Requirements

| Component | Version | Notes |
| --- | --- | --- |
| Python | 3.11 | API + pipelines |
| Node.js | 18+ (20 recommended) | Next.js web app |
| Outbound HTTPS | optional | needed only for **live news sync** (GDELT) |
| Elasticsearch | 8.x, optional | only if `ENABLE_ELASTIC=true`; otherwise the local hybrid provider is used |

Install:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api,ml,vectorstore]"     # add ,recsys for the dual-encoder recommender
cd apps/web && npm install
```

---

## 2. Run it (two processes)

```bash
# terminal 1 — API on 127.0.0.1:8000 (offline, no key)
make api

# terminal 2 — web on http://localhost:3000
make web            # dev server (hot reload)
# or a production build:
cd apps/web && npm run build && NEXT_PUBLIC_API_BASE=http://<api-host>:8000 npm start
```

`NEXT_PUBLIC_API_BASE` is baked at **build time** for `next build` / `npm start`, and read at dev
start for `npm run dev`. Point it at wherever the API is reachable from the browser.

### View on a phone (same Wi-Fi)

```bash
make api-lan                       # API on 0.0.0.0:8000
make web-lan LAN_IP=192.168.0.10   # web on 0.0.0.0:3000, API base = your PC's LAN IP
```

Then open `http://<your-PC-IP>:3000` on the phone. Still offline; only your local network can reach it.

---

## 3. Environment variables

`.env.example` documents the safe defaults. Key variables:

| Variable | Default | Effect |
| --- | --- | --- |
| `SHOCKFLOW_MODE` | `demo_fixture` | operating mode label |
| `SHOCKFLOW_API_HOST` / `SHOCKFLOW_API_PORT` | `127.0.0.1` / `8000` | API bind (set host `0.0.0.0` for LAN) |
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` | web → API URL (build-time) |
| `LLM_PROVIDER` | `mock` | `mock` = deterministic offline extractor; a real provider enables live event extraction |
| `ENABLE_GDELT_LIVE` | `false` | opt-in for the CLI live news backfill (the **sync button** is always user-initiated) |
| `ENABLE_ELASTIC` | `false` | use Elasticsearch for hybrid search; degrades to local if unreachable |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch endpoint |

---

## 4. Live news sync (free, no API key)

The "🔄 뉴스 동기화" button (rider home + operator news screen) calls `POST /v2/news/sync`, which
pulls recent mobility news from **GDELT DOC 2.0** — a free, key-less API. Fetched articles are
deduplicated and accumulated into the news vector store, so they become searchable immediately.

- **Requirement:** the API host needs **outbound HTTPS to `api.gdeltproject.org`**. That's the only
  thing live news needs — no key, no account.
- **If there's no egress** (e.g. a locked-down sandbox), the button returns a `degraded` status with
  the reason and the demo keeps working unchanged. Deploy somewhere with network access and the same
  button pulls live news as-is.
- Verify from the server:

  ```bash
  curl -X POST http://127.0.0.1:8000/v2/news/sync -H 'Content-Type: application/json' -d '{}'
  # status:"live"  → egress works;  status:"degraded" → check the API host's outbound network
  ```

GDELT returns title + metadata only (no article body). To turn live articles into graph events you
also need a real `LLM_PROVIDER` (the default `mock` extractor is deterministic on the demo fixture).

---

## 5. Optional Elasticsearch (hybrid search)

Search runs fully offline by default (`local-hybrid`: BM25 + vector + geo, RRF). To back it with a
real cluster:

```bash
docker run -p 9200:9200 -e discovery.type=single-node -e xpack.security.enabled=false \
  docker.elastic.co/elasticsearch/elasticsearch:8.14.0
ENABLE_ELASTIC=true ELASTIC_URL=http://localhost:9200 make api
```

If the cluster is unreachable the API degrades to the local provider and reports `degraded: true` —
it never blocks search.

---

## 6. Data at operational scale

- Station network: `data/fixtures/station_gazetteer.json` + `data/fixtures/rebalancing_demo.json`
  (currently 16 stations across 4 regions). Add stations by appending to both files with matching
  `station_id`s (coordinates + capacity + base_target in the rebalancing file; KO/EN names + aliases
  in the gazetteer). Search, map, statistics, pricing, allocation, and the copilots pick them up
  automatically.
- Real Citi Bike history for the forecasting evaluation goes under `data/raw/citibike/` (git-ignored);
  run `make evaluate CITIBIKE_ZIP=path/to.zip`. Enabling a **measured** predictive-lift claim also
  needs a real overlapping-news backfill (`make v1-collect-news-live` with egress) so the coverage
  gate can pass; until then `GET /v2/model/predictive-lift` reports `blocked_data`.

---

## 7. Pre-deploy checks

```bash
make test                 # backend suite (torch-optional tests skip if torch absent)
make v2-evaluate-search   # hybrid search relevance on the gold set
cd apps/web && npm run typecheck && npm run build
```

Modes stay explicit end-to-end: fixture demo data is labelled demo, and live results carry a LIVE
badge — the two are never mixed.
