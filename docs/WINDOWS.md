# Running on Windows (PowerShell)

`make` and the `.sh` scripts are Unix tools — on Windows either run the plain Python commands below
(no extra install), or use **WSL** (`wsl --install`) where `make` / `.sh` work as-is. This guide is
100% native PowerShell.

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

```powershell
# B-1. Fetch trips + news + stations for a month range, one command:
.\scripts\fetch_data.ps1 202601 202606 nyc

# B-2. Real Claude extraction key:
pip install anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."       # shell only — never commit
# cheaper for bulk: $env:LLM_MODEL = "claude-haiku-4-5"

# B-3. Combine all six months into one panel and measure lift:
python -m ml.forecasting.run --data-dir data\raw\citibike `
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
| `blocked_data`, too few rows | trip window too short — fetch more months |
| event features all 0 | news window doesn't overlap the trip window — align the fetch months |
| `GDELT degraded` | no egress — run where the internet is reachable |
| extraction all errors | `$env:ANTHROPIC_API_KEY` unset, or `pip install anthropic` missing |
