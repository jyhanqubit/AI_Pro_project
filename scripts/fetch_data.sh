#!/usr/bin/env bash
# Fetch the three ShockFlow AI data sources for a month range, by code. CLAUDE.md §7.
#
#   scripts/fetch_data.sh [FROM_YYYYMM] [TO_YYYYMM] [REGION]
#   scripts/fetch_data.sh 202601 202606 nyc        # defaults shown
#
# Produces:
#   - trips:    data/raw/citibike/<YYYYMM>-citibike-tripdata.zip   (one per month)
#   - news:     data/fixtures/news_live/news_<REGION>_<FROM>_<TO>.jsonl  (all months, combined)
#   - stations: the CURRENT network imported into the fixtures (GBFS has no history)
#
# Requirements:
#   - outbound network (Citi Bike S3 is public + no key; GDELT news needs egress)
#   - GDELT news collection is opt-in: this script sets ENABLE_GDELT_LIVE=true for you
#   - stations import needs egress to the GBFS feed
#
# Notes:
#   - Trip files are large (NYC months are hundreds of MB); they are git-ignored (§7.1) — do NOT
#     commit them. Re-running skips files already present.
#   - GBFS is a *current* snapshot only. Historical station identity/coords already live inside the
#     trip CSVs, so there is no 6-month station history to download.

set -euo pipefail

FROM="${1:-202601}"
TO="${2:-202606}"
REGION="${3:-nyc}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== ShockFlow AI data fetch =="
echo "   range : $FROM .. $TO"
echo "   region: $REGION"
echo

# Month list from the repo's own helper (validates YYYYMM + range).
MONTHS="$(python -c "from pipelines.collectors.download_citibike import month_range; print(' '.join(month_range('$FROM','$TO')))")"
echo "months: $MONTHS"
echo

# 1) TRIPS -----------------------------------------------------------------------------------------
echo "== 1/3  trips (Citi Bike S3, public, no key) =="
JC_FLAG=""
[ "$REGION" = "jc" ] && JC_FLAG="--jersey-city"
python -m pipelines.collectors.download_citibike --from "$FROM" --to "$TO" $JC_FLAG
echo

# 2) NEWS (per month, then combine into one JSONL) -------------------------------------------------
echo "== 2/3  news (GDELT DOC 2.0, free, no key; needs egress) =="
export ENABLE_GDELT_LIVE=true
NEWS_DIR="data/fixtures/news_live"
COMBINED="$NEWS_DIR/news_${REGION}_${FROM}_${TO}.jsonl"
mkdir -p "$NEWS_DIR"
: > "$COMBINED"   # truncate/create the combined file
for m in $MONTHS; do
  Y="${m:0:4}"; MO="${m:4:2}"
  START="${m}01000000"
  END="$(python -c "y=$Y; mo=$MO; ny,nm=(y+1,1) if mo==12 else (y,mo+1); print(f'{ny:04d}{nm:02d}01000000')")"
  echo "  - $m : $START .. $END"
  python -m pipelines.collectors.collect_live_news --live --region "$REGION" \
    --start "$START" --end "$END" --max-records 250 --stamp "${REGION}_${m}" || \
    echo "    (month $m degraded — continuing)"
  SNAP="$NEWS_DIR/news_gdelt_${REGION}_${m}.jsonl"
  [ -f "$SNAP" ] && cat "$SNAP" >> "$COMBINED"
done
echo "  combined news -> $COMBINED ($(wc -l < "$COMBINED" 2>/dev/null || echo 0) articles)"
echo

# 3) STATIONS (current network snapshot; GBFS has no history) --------------------------------------
echo "== 3/3  stations (GBFS current snapshot; no history) =="
python -m pipelines.collectors.import_gbfs_stations --limit 40 || \
  echo "  (stations import degraded — needs egress to the GBFS feed)"
echo

echo "== done =="
echo "Next — measure the LLM-feature lift on one month (real Claude extraction needs ANTHROPIC_API_KEY):"
echo "  export ANTHROPIC_API_KEY=sk-ant-..."
echo "  python -m ml.forecasting.run data/raw/citibike/${FROM}-citibike-tripdata.zip \\"
echo "    --news $COMBINED --provider anthropic"
