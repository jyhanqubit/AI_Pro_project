<#
.SYNOPSIS
  Fetch the three ShockFlow AI data sources for a month range (Windows PowerShell port of
  scripts/fetch_data.sh). CLAUDE.md section 7.

.DESCRIPTION
  Produces:
    - trips:    data\raw\citibike\<YYYYMM>-citibike-tripdata.zip        (one per month)
    - news:     data\fixtures\news_live\news_<REGION>_<FROM>_<TO>.jsonl (all months, combined)
    - stations: the CURRENT network imported into the fixtures (GBFS has no history)

  Needs outbound network (Citi Bike S3 is public + no key; GDELT news needs egress). Trip files are
  large and git-ignored (section 7.1) - do not commit them. Re-running skips files already present.
  GBFS is a *current* snapshot only; historical station identity already lives in the trip CSVs.

.EXAMPLE
  .\scripts\fetch_data.ps1 202601 202606 nyc
  .\scripts\fetch_data.ps1                     # defaults: 202601 202606 nyc
#>

param(
  [string]$From   = "202601",
  [string]$To     = "202606",
  [string]$Region = "nyc"
)

# Note: default ErrorActionPreference (Continue) — external tools that print warnings to stderr
# must not abort the whole fetch; each source degrades independently. Explicit `throw`s below
# (bad month range) still stop the script.

# Run from the repo root (this script lives in scripts\).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-Months([string]$from, [string]$to) {
  foreach ($m in @($from, $to)) {
    if ($m -notmatch '^\d{6}$' -or [int]$m.Substring(4, 2) -lt 1 -or [int]$m.Substring(4, 2) -gt 12) {
      throw "month must be YYYYMM (01-12): $m"
    }
  }
  $y = [int]$from.Substring(0, 4); $mo = [int]$from.Substring(4, 2)
  $ey = [int]$to.Substring(0, 4);  $em = [int]$to.Substring(4, 2)
  if ($y -gt $ey -or ($y -eq $ey -and $mo -gt $em)) { throw "FROM $from is after TO $to" }
  $out = @()
  while ($y -lt $ey -or ($y -eq $ey -and $mo -le $em)) {
    $out += ("{0:D4}{1:D2}" -f $y, $mo)
    if ($mo -eq 12) { $y++; $mo = 1 } else { $mo++ }
  }
  return $out
}

Write-Host "== ShockFlow AI data fetch =="
Write-Host "   range : $From .. $To"
Write-Host "   region: $Region`n"

$months = Get-Months $From $To
Write-Host ("months: " + ($months -join " ") + "`n")

# 1) TRIPS -----------------------------------------------------------------------------------------
Write-Host "== 1/3  trips (Citi Bike S3, public, no key) =="
$jc = @()
if ($Region -eq "jc") { $jc = @("--jersey-city") }
python -m pipelines.collectors.download_citibike --from $From --to $To @jc
Write-Host ""

# 2) NEWS (per month, then combine into one JSONL) -------------------------------------------------
Write-Host "== 2/3  news (GDELT DOC 2.0, free, no key; needs egress) =="
$env:ENABLE_GDELT_LIVE = "true"
$newsDir  = "data\fixtures\news_live"
$combined = Join-Path $newsDir ("news_{0}_{1}_{2}.jsonl" -f $Region, $From, $To)
New-Item -ItemType Directory -Force -Path $newsDir | Out-Null
New-Item -ItemType File -Force -Path $combined | Out-Null    # create / truncate to empty
foreach ($m in $months) {
  $y = [int]$m.Substring(0, 4); $mo = [int]$m.Substring(4, 2)
  if ($mo -eq 12) { $ny = $y + 1; $nm = 1 } else { $ny = $y; $nm = $mo }
  $start = "${m}01000000"
  $end   = "{0:D4}{1:D2}01000000" -f $ny, $nm
  Write-Host "  - $m : $start .. $end"
  try {
    python -m pipelines.collectors.collect_live_news --live --region $Region `
      --start $start --end $end --max-records 250 --stamp "${Region}_$m"
  } catch {
    Write-Host "    (month $m degraded - continuing)"
  }
  $snap = Join-Path $newsDir ("news_gdelt_{0}_{1}.jsonl" -f $Region, $m)
  if (Test-Path $snap) { Get-Content $snap | Add-Content $combined }
}
$articleCount = 0
if (Test-Path $combined) { $articleCount = (Get-Content $combined | Measure-Object -Line).Lines }
Write-Host "  combined news -> $combined ($articleCount articles)`n"

# 3) STATIONS (current network snapshot; GBFS has no history) --------------------------------------
Write-Host "== 3/3  stations (GBFS current snapshot; no history) =="
try {
  python -m pipelines.collectors.import_gbfs_stations --limit 40
} catch {
  Write-Host "  (stations import degraded - needs egress to the GBFS feed)"
}
Write-Host ""

Write-Host "== done =="
Write-Host "Next - measure the LLM-feature lift over ALL $From..$To as one panel"
Write-Host "(real Claude extraction needs `$env:ANTHROPIC_API_KEY):"
Write-Host "  `$env:ANTHROPIC_API_KEY = 'sk-ant-...'"
Write-Host "  python -m ml.forecasting.run --data-dir data\raw\citibike ``"
Write-Host "    --news $combined --provider anthropic"
