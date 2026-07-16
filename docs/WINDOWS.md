# Running on Windows (PowerShell)

`make` and the `.sh` scripts are Unix tools — on Windows either run the plain Python commands below
(no extra install), or use **WSL** (`wsl --install`) where `make` / `.sh` work as-is. This guide is
100% native PowerShell.

## One command (setup → demo → data → lift → databases)

From the repo root (the folder with `pyproject.toml`):

```powershell
# blocked by execution policy? run this once in the session first:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\scripts\run_all.ps1                                 # setup + offline demo + data + lift(mock)
.\scripts\run_all.ps1 -AnthropicKey "sk-ant-..."      # + real Claude extraction
.\scripts\run_all.ps1 -NewsSource guardian -GuardianKey "xxxx"  # full-history real headlines
.\scripts\run_all.ps1 -NewsSource gdelt_bulk          # no key, no rate limit, full history
.\scripts\run_all.ps1 -From 202601 -To 202606 -WithDatabases -WithDocker
.\scripts\run_all.ps1 -SkipData -SkipLift             # just setup + offline demo
```

`run_all.ps1` drives the venv Python directly (no `Activate.ps1`), and every stage degrades on its
own: no internet skips the live fetch, no `-AnthropicKey` uses the offline mock extractor, no
`-WithDocker` skips Neo4j/Postgres. The step-by-step commands below are the same stages by hand.

## PowerShell gotchas

- **Activate the venv:** `.\.venv\Scripts\Activate.ps1`
  (blocked? first run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)
- **Environment variables:** `export VAR=x` → **`$env:VAR = "x"`**
- **Line continuation:** Linux `\` → PowerShell **backtick** `` ` ``
- **Run every command from the repo root** (the folder with `pyproject.toml`) — check with
  `Test-Path pyproject.toml` → must be `True`.

## `make` → direct command

| `make …` | PowerShell |
| --- | --- |
| `make install` | `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"` |
| `make test` | `python -m pytest` |
| `make collect-demo` | `python -m pipelines.collectors.demo` |
| `make build-features` | `python -m pipelines.features.demo` |
| `make extract-events-demo` | `python -m pipelines.events.demo` |
| `make graph-upsert-demo` | `python -m pipelines.graph.demo` |
| `make graph-features-demo` | `python -m pipelines.features.graph_features_demo` |
| `make rebalance-demo` | `python -m optimization.demo` |
| `make v2-evaluate-revenue` | `python -m ml.pricing.revenue_eval` |
| `make v2-evaluate-predictive-lift` | `python -m ml.forecasting.predictive_lift_demo` |
| `make db-load` | `python -m services.db.demo` |
| `make download-citibike MONTHS="202601 202602"` | `python -m pipelines.collectors.download_citibike 202601 202602` |
| `make api` | `python -m services.api.main` |
| `make web` | `cd apps\web; npm run dev` |

---

## 0. Setup (once)

```powershell
# clone, then cd into the repo (the folder with pyproject.toml)
cd C:\dev                                   # any space-free path is safest
git clone https://github.com/jyhanqubit/AI_Pro_project.git
cd AI_Pro_project
Test-Path pyproject.toml                    # must print True

python -m venv .venv
.\.venv\Scripts\Activate.ps1                # (Set-ExecutionPolicy -Scope Process Bypass if blocked)
pip install -e ".[dev]"
python -m pytest                            # some torch/data-dependent tests skip/fail — that's fine
```

## A. Offline demo (no key / no internet / no docker)

```powershell
python -m pipelines.collectors.demo
python -m pipelines.features.demo
python -m pipelines.events.demo
python -m pipelines.graph.demo
python -m pipelines.features.graph_features_demo
python -m optimization.demo
python -m ml.pricing.revenue_eval
```

App (two PowerShell windows):

```powershell
python -m services.api.main                 # window 1  -> http://127.0.0.1:8000
cd apps\web; npm install; npm run dev        # window 2  -> http://localhost:3000
```

## B. Real data → measure the LLM-feature lift

### Choosing a news source (`-NewsSource`)

GDELT's DOC API is rate-limited and only serves ~the last 3 months. Two more sources are wired in:

| Source | Key | History | Headlines? | Notes |
| --- | --- | --- | --- | --- |
| `gdelt` (default) | none | ~last 3 months | yes (title) | throttled — 429s on bursts |
| `guardian` | free `GUARDIAN_API_KEY` | 1999→ full | **yes** (title + summary) | best for LLM lift; get a key at open-platform.theguardian.com/access |
| `gdelt_bulk` | none | 2015→ full | **no** (URL + GDELT theme tags only) | no rate limit; coverage/signal source, not prose |

```powershell
# B-1. Fetch trips + news + stations for a month range, one command:
.\scripts\fetch_data.ps1 202601 202606 nyc                          # default: gdelt
.\scripts\fetch_data.ps1 202601 202606 nyc -NewsSource guardian -GuardianKey "xxxx"
.\scripts\fetch_data.ps1 202601 202606 nyc -NewsSource gdelt_bulk   # no key, full history

# B-2. Real Claude extraction key:
pip install anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."       # shell only — never commit
# cheaper for bulk: $env:LLM_MODEL = "claude-haiku-4-5"

# B-3. Combine all six months into one panel and measure lift:
python -m ml.forecasting.run --data-dir data\raw\citibike `
  --news data\fixtures\news_live\news_nyc_202601_202606.jsonl --provider anthropic

# Out of memory on a full 6-month NYC window? Bound it to the most recent N months (still real
# data, just a shorter panel) — via the script (-MaxMonths 3) or the command (--max-months 3):
python -m ml.forecasting.run --data-dir data\raw\citibike --max-months 3 `
  --news data\fixtures\news_live\news_nyc_202601_202606.jsonl --provider anthropic
```

Output: `reports\phase06_results.json` (B0–B4 leaderboard + lift). Verdict only:
`python -m ml.forecasting.predictive_lift_demo`.

**Honest reading:** B3 (LLM) / B4 (graph) beat B1 on WAPE with a CI above 0 → a measured lift;
otherwise the verdict is `no_lift` / `inconclusive` — reported as-is, never fabricated.

## C. Databases (optional)

```powershell
# RDB — SQLite (zero-config)
pip install -e ".[rdb]"; python -m services.db.demo
# Postgres: docker compose up -d postgres; $env:DATABASE_URL = "postgresql+psycopg://shockflow:shockflow@localhost:5432/shockflow"

# Graph — Neo4j
docker compose up -d neo4j
pip install -e ".[graph]"
$env:NEO4J_PASSWORD = "shockflow_dev"
python -m pipelines.graph.demo --backend neo4j

# FAISS news
pip install -e ".[vectorstore]"; python -m ml.vectorstore.demo
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `neither 'setup.py' nor 'pyproject.toml' found` | You're not in the repo root — `cd AI_Pro_project`; `Test-Path pyproject.toml` must be `True` |
| `Activate.ps1 cannot be loaded … execution policy` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then activate |
| `make: term not recognized` | `make` isn't on Windows — use the commands above (or WSL) |
| `MemoryError` in the lift step | a full 6-month NYC panel is too big for this machine's RAM — bound it with `-MaxMonths 3` (script) or `--max-months 3` (command); still real data, shorter window |
| `DenseSpanTooLarge … likely a corrupt timestamp` | one trip row has a bad date stretching the hourly grid over years — drop that file/rows, or use `--max-months` |
| `blocked_data`, too few rows | trip window too short — fetch more months |
| event features all 0 | news window doesn't overlap the trip window — align the fetch months |
| `GDELT degraded … 429 Too Many Requests` | rate-limited by bursty querying. The collector now backs off exponentially and the scripts space months out; if it still trips, raise the gap (`.\scripts\run_all.ps1 -NewsDelaySeconds 15`) or re-run in a few minutes (only the missing months refetch). For older months (>~3 months back) GDELT DOC has no data at all — switch to `-NewsSource guardian` or `-NewsSource gdelt_bulk` for full history |
| `guardian degraded … key missing` | get a free developer key at open-platform.theguardian.com/access and pass `-GuardianKey "xxxx"` (or `$env:GUARDIAN_API_KEY`) |
| `gdelt_bulk` returns few rows for a month | by default it caps at `--max-records 96` 15-min files (~1 day). A full month is ~2,880 files — fetch day-by-day (narrow `--start/--end`) or raise the cap; it has no headlines, so use it as a coverage/signal source and Guardian for prose |
| `GDELT degraded` (other) | no egress — run where the internet is reachable |
| extraction all errors | `$env:ANTHROPIC_API_KEY` unset, or `pip install anthropic` missing |
