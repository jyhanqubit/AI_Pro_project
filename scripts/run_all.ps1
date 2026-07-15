<#
.SYNOPSIS
  One command that does everything on Windows: setup -> offline demo -> data download -> lift
  measurement -> databases. Native PowerShell; no `make`, no bash. CLAUDE.md sections 7, 11, 16.

.DESCRIPTION
  Runs from the repo root and drives the venv Python directly (no Activate.ps1, so no execution-
  policy prompts). Every stage degrades independently: no internet skips the live fetch, no API key
  falls back to the deterministic mock extractor, no Docker skips the server databases. Large raw
  trip files stay git-ignored.

.PARAMETER From / To / Region
  Trip + news month range (YYYYMM) and region (nyc | jc). Default 202601..202606 nyc.

.PARAMETER AnthropicKey
  If set, the lift step uses real Claude extraction (installs `anthropic`); otherwise it uses the
  offline mock extractor on the same real news.

.PARAMETER SkipInstall / SkipDemo / SkipData / SkipLift
  Turn off individual stages.

.PARAMETER WithDatabases
  Also run SQLite RDB + FAISS demos. Add -WithDocker to bring up Neo4j + Postgres via Docker Desktop.

.EXAMPLE
  .\scripts\run_all.ps1                                  # demo + data + lift(mock)
  .\scripts\run_all.ps1 -AnthropicKey sk-ant-xxx         # real Claude extraction
  .\scripts\run_all.ps1 -From 202601 -To 202606 -WithDatabases -WithDocker
  .\scripts\run_all.ps1 -SkipData -SkipLift              # just setup + offline demo
#>

param(
  [string]$From         = "202601",
  [string]$To           = "202606",
  [string]$Region       = "nyc",
  [string]$AnthropicKey = "",
  [string]$Model        = "claude-opus-4-8",
  [switch]$SkipInstall,
  [switch]$SkipDemo,
  [switch]$SkipData,
  [switch]$SkipLift,
  [switch]$WithDatabases,
  [switch]$WithDocker
)

# --- repo root + venv python -----------------------------------------------------------------------
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
  throw "Run from the repo (pyproject.toml not found next to this script's parent)."
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Banner([string]$t) { Write-Host "`n==================== $t ====================" -ForegroundColor Cyan }
function Step([string]$t)   { Write-Host "-- $t" -ForegroundColor Yellow }

function Get-Months([string]$from, [string]$to) {
  foreach ($m in @($from, $to)) {
    if ($m -notmatch '^\d{6}$' -or [int]$m.Substring(4, 2) -lt 1 -or [int]$m.Substring(4, 2) -gt 12) {
      throw "month must be YYYYMM (01-12): $m"
    }
  }
  $y = [int]$from.Substring(0, 4); $mo = [int]$from.Substring(4, 2)
  $ey = [int]$to.Substring(0, 4);  $em = [int]$to.Substring(4, 2)
  if ($y -gt $ey -or ($y -eq $ey -and $mo -gt $em)) { throw "From $from is after To $to" }
  $out = @()
  while ($y -lt $ey -or ($y -eq $ey -and $mo -le $em)) {
    $out += ("{0:D4}{1:D2}" -f $y, $mo)
    if ($mo -eq 12) { $y++; $mo = 1 } else { $mo++ }
  }
  return $out
}

# --- 1. setup --------------------------------------------------------------------------------------
Banner "1. setup"
if (-not $SkipInstall) {
  if (-not (Test-Path $Py)) { Step "creating venv"; python -m venv .venv }
  $extras = "dev"
  if ($WithDatabases) { $extras = "dev,rdb,vectorstore" }
  Step "installing (.[$extras])"
  & $Py -m pip install --quiet --upgrade pip
  & $Py -m pip install -e ".[$extras]"
  if ($AnthropicKey) { Step "installing anthropic SDK"; & $Py -m pip install --quiet anthropic }
} else {
  Step "skipped (-SkipInstall)"
}

# --- 2. offline demo -------------------------------------------------------------------------------
if (-not $SkipDemo) {
  Banner "2. offline demo (no key / no internet)"
  foreach ($mod in @(
      "pipelines.collectors.demo",
      "pipelines.features.demo",
      "pipelines.events.demo",
      "pipelines.graph.demo",
      "pipelines.features.graph_features_demo",
      "optimization.demo",
      "ml.pricing.revenue_eval")) {
    Step $mod
    & $Py -m $mod
  }
}

# --- 3. data download (trips + news + stations) ----------------------------------------------------
$combined = Join-Path "data\fixtures\news_live" ("news_{0}_{1}_{2}.jsonl" -f $Region, $From, $To)
if (-not $SkipData) {
  Banner "3. data download ($From..$To, $Region)"
  $months = Get-Months $From $To

  Step "trips (Citi Bike S3, public, no key)"
  $jc = @(); if ($Region -eq "jc") { $jc = @("--jersey-city") }
  & $Py -m pipelines.collectors.download_citibike --from $From --to $To @jc

  Step "news (GDELT per month -> one JSONL; needs internet)"
  $env:ENABLE_GDELT_LIVE = "true"
  New-Item -ItemType Directory -Force -Path "data\fixtures\news_live" | Out-Null
  New-Item -ItemType File -Force -Path $combined | Out-Null
  foreach ($m in $months) {
    $y = [int]$m.Substring(0, 4); $mo = [int]$m.Substring(4, 2)
    if ($mo -eq 12) { $ny = $y + 1; $nm = 1 } else { $ny = $y; $nm = $mo }
    $start = "${m}01000000"; $end = "{0:D4}{1:D2}01000000" -f $ny, $nm
    Write-Host "     $m : $start .. $end"
    & $Py -m pipelines.collectors.collect_live_news --live --region $Region `
      --start $start --end $end --max-records 250 --stamp "${Region}_$m"
    $snap = Join-Path "data\fixtures\news_live" ("news_gdelt_{0}_{1}.jsonl" -f $Region, $m)
    if (Test-Path $snap) { Get-Content $snap | Add-Content $combined }
  }
  $n = 0; if (Test-Path $combined) { $n = (Get-Content $combined | Measure-Object -Line).Lines }
  Write-Host "     combined news -> $combined ($n articles)"

  Step "stations (GBFS current snapshot; needs internet)"
  & $Py -m pipelines.collectors.import_gbfs_stations --limit 40
}

# --- 4. lift (real data + real/mock extraction) ----------------------------------------------------
if (-not $SkipLift) {
  Banner "4. lift measurement (six months as one panel)"
  $provider = "mock"
  if ($AnthropicKey) {
    $env:ANTHROPIC_API_KEY = $AnthropicKey
    $env:LLM_MODEL = $Model
    $provider = "anthropic"
    Step "real Claude extraction (model $Model)"
  } else {
    Step "no -AnthropicKey -> deterministic mock extractor on the real news"
  }
  $newsArgs = @()
  if (Test-Path $combined) { $newsArgs = @("--news", $combined) }
  & $Py -m ml.forecasting.run --data-dir "data\raw\citibike" @newsArgs --provider $provider
  Write-Host "     report -> reports\phase06_results.json"
}

# --- 5. databases (optional) -----------------------------------------------------------------------
if ($WithDatabases) {
  Banner "5. databases"
  if ($WithDocker) {
    Step "docker compose up neo4j + postgres"
    docker compose up -d neo4j postgres
    Start-Sleep -Seconds 8
  }
  Step "RDB (SQLite by default)"
  & $Py -m services.db.demo
  Step "FAISS news vector store"
  & $Py -m ml.vectorstore.demo
  if ($WithDocker) {
    Step "Neo4j graph upsert"
    $env:NEO4J_PASSWORD = "shockflow_dev"
    & $Py -m pipelines.graph.demo --backend neo4j
  }
}

# --- done ------------------------------------------------------------------------------------------
Banner "done"
Write-Host "Start the app in two more terminals:" -ForegroundColor Green
Write-Host "  & '$Py' -m services.api.main            # -> http://127.0.0.1:8000"
Write-Host "  cd apps\web; npm install; npm run dev    # -> http://localhost:3000"
