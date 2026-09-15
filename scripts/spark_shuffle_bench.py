"""Measure shuffle cost on the real 24.9M-row trip table: pandas vs PySpark (V2 extra).

Three ways to run the same two workloads over identical Parquet input
(``data/processed/spark_bench/``, built from the 7 monthly NYC archives):

  (a) pandas, single process
  (b) PySpark local mode, default partitioning
  (c) PySpark, input pre-repartitioned by the aggregation/join key

Workloads:
  groupby: departures per (start_station_id, hour)  — the project's real demand grain
  join:    trips joined to a per-station dimension on end_station_id
           (autoBroadcastJoinThreshold=-1 so the join actually shuffles; a 2K-row dim
           would be broadcast in production — the point here is to measure the shuffle)

Each Spark run repeats at shuffle partition counts 8 / 32 / 200, and shuffle
read/write bytes are pulled from the Spark UI REST API per query (stage-delta).
Timing includes the Parquet scan and a `noop` materialization for every engine, so
the engines pay the same I/O. Pre-repartition time is INCLUDED in (c): whether the
extra up-front shuffle pays for itself is exactly the question.

Usage:
    python -m scripts.spark_shuffle_bench [--cores 4] [--partitions 8 32 200]
Output:
    reports/v2/spark/shuffle_bench.json / .csv / shuffle_bench.png
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data/processed/spark_bench")
OUT_DIR = Path("reports/v2/spark")
UI = "http://localhost:4040/api/v1"


# ----------------------------------------------------------------------------- helpers
def _ui_json(path: str) -> Any:
    with urllib.request.urlopen(f"{UI}{path}", timeout=10) as resp:
        return json.loads(resp.read())


def shuffle_totals() -> tuple[int, int]:
    """Sum shuffle read/write bytes over all stages of the running app (UI REST API)."""
    apps = _ui_json("/applications")
    app_id = apps[0]["id"]
    read = write = 0
    for st in _ui_json(f"/applications/{app_id}/stages"):
        read += st.get("shuffleReadBytes", 0)
        write += st.get("shuffleWriteBytes", 0)
    return read, write


def timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return round(time.perf_counter() - t0, 2)


def build_parquet(raw_dir: Path = Path("data/raw/citibike")) -> None:
    """Convert the monthly NYC trip zips to a 3-column Parquet the benchmark reads.

    Only the three columns the two workloads need are kept, so the Parquet stays small
    relative to the raw archives. Idempotent: skips if the output already has parts.
    """
    import glob
    import zipfile

    import pandas as pd

    if any(DATA_DIR.glob("*.parquet")):
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["started_at", "start_station_id", "end_station_id"]
    part = 0
    archives = sorted(glob.glob(str(raw_dir / "2026*-citibike-tripdata.zip")))
    if not archives:
        raise SystemExit(
            f"no NYC trip archives in {raw_dir} — run `make download-citibike "
            'MONTHS="202601 202602 202603 202604 202605 202606 202607"` first'
        )
    for f in archives:
        z = zipfile.ZipFile(f)
        for n in z.namelist():
            if n.lower().endswith(".csv") and "__MACOSX" not in n:
                with z.open(n) as fh:
                    for chunk in pd.read_csv(
                        fh,
                        usecols=cols,
                        dtype={"start_station_id": "string", "end_station_id": "string"},
                        chunksize=2_000_000,
                    ):
                        chunk["started_at"] = pd.to_datetime(chunk["started_at"], format="mixed")
                        chunk.to_parquet(DATA_DIR / f"part-{part:04d}.parquet", index=False)
                        part += 1
    print(f"built {part} Parquet parts in {DATA_DIR}")


# ----------------------------------------------------------------------------- pandas
def run_pandas() -> list[dict[str, Any]]:
    import pandas as pd

    rows: list[dict[str, Any]] = []

    def _groupby() -> None:
        df = pd.read_parquet(DATA_DIR)
        agg = df.groupby(["start_station_id", df["started_at"].dt.floor("h")], observed=True).size()
        assert len(agg) > 0

    def _join() -> None:
        df = pd.read_parquet(DATA_DIR)
        dim = (
            df[["start_station_id"]]
            .drop_duplicates()
            .rename(columns={"start_station_id": "station_id"})
        )
        dim["zone_bucket"] = dim["station_id"].astype("str").map(hash) % 100
        joined = df.merge(dim, left_on="end_station_id", right_on="station_id", how="inner")
        assert len(joined) > 0

    for name, fn in (("groupby", _groupby), ("join", _join)):
        rows.append(
            {
                "engine": "pandas",
                "variant": "single_process",
                "workload": name,
                "partitions": None,
                "seconds": timed(fn),
                "shuffle_read_mb": None,
                "shuffle_write_mb": None,
            }
        )
        print(rows[-1])
    return rows


# ----------------------------------------------------------------------------- spark
def run_spark(cores: int, partition_counts: list[int]) -> list[dict[str, Any]]:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    rows: list[dict[str, Any]] = []

    for n_part in partition_counts:
        spark = (
            SparkSession.builder.master(f"local[{cores}]")
            .appName(f"shuffle-bench-p{n_part}")
            .config("spark.driver.memory", "6g")
            .config("spark.sql.shuffle.partitions", str(n_part))
            .config("spark.sql.autoBroadcastJoinThreshold", "-1")
            .config("spark.ui.enabled", "true")
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("WARN")

        # Default-arg binding pins the loop variables to each iteration's values, so the
        # closures stay correct if they ever outlive the loop body (ruff B023).
        def _measure(variant: str, workload: str, fn, n_part: int = n_part) -> None:
            r0, w0 = shuffle_totals()
            secs = timed(fn)
            r1, w1 = shuffle_totals()
            rows.append(
                {
                    "engine": "pyspark",
                    "variant": variant,
                    "workload": workload,
                    "partitions": n_part,
                    "seconds": secs,
                    "shuffle_read_mb": round((r1 - r0) / 1e6, 1),
                    "shuffle_write_mb": round((w1 - w0) / 1e6, 1),
                }
            )
            print(rows[-1])

        def _noop(df) -> None:
            df.write.format("noop").mode("overwrite").save()

        def _trips(spark=spark):
            return spark.read.parquet(str(DATA_DIR))

        def _dim(df):
            return (
                df.select("start_station_id")
                .distinct()
                .withColumnRenamed("start_station_id", "station_id")
                .withColumn("zone_bucket", F.crc32(F.col("station_id")) % 100)
            )

        # (b) default partitioning ------------------------------------------------
        _measure(
            "default",
            "groupby",
            lambda: _noop(
                _trips()
                .groupBy("start_station_id", F.date_trunc("hour", "started_at").alias("hour"))
                .count()
            ),
        )
        _measure(
            "default",
            "join",
            lambda: _noop(
                _trips().join(
                    _dim(_trips()),
                    F.col("end_station_id") == F.col("station_id"),
                    "inner",
                )
            ),
        )

        # (c) pre-repartitioned by the key (repartition time included) -----------
        _measure(
            "pre_repartitioned",
            "groupby",
            lambda n_part=n_part: _noop(
                _trips()
                .repartition(n_part, "start_station_id")
                .groupBy("start_station_id", F.date_trunc("hour", "started_at").alias("hour"))
                .count()
            ),
        )
        _measure(
            "pre_repartitioned",
            "join",
            lambda n_part=n_part: _noop(
                _trips()
                .repartition(n_part, "end_station_id")
                .join(
                    _dim(_trips()).repartition(n_part, "station_id"),
                    F.col("end_station_id") == F.col("station_id"),
                    "inner",
                )
            ),
        )

        spark.stop()
        time.sleep(2)  # release the UI port before the next session
    return rows


# ----------------------------------------------------------------------------- output
def plot(rows: list[dict[str, Any]], out_png: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, workload in zip(axes, ("groupby", "join"), strict=True):
        parts = sorted({r["partitions"] for r in rows if r["partitions"]})
        for variant, style in (("default", "o-"), ("pre_repartitioned", "s--")):
            ys = [
                next(
                    r["seconds"]
                    for r in rows
                    if r["engine"] == "pyspark"
                    and r["variant"] == variant
                    and r["workload"] == workload
                    and r["partitions"] == p
                )
                for p in parts
            ]
            ax.plot(parts, ys, style, label=f"pyspark {variant}")
        pandas_s = next(
            r["seconds"] for r in rows if r["engine"] == "pandas" and r["workload"] == workload
        )
        ax.axhline(pandas_s, color="gray", ls=":", label=f"pandas ({pandas_s:.0f}s)")
        ax.set_xscale("log")
        ax.set_xticks(parts)
        ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
        ax.set_xlabel("shuffle partitions")
        ax.set_ylabel("wall time (s)")
        ax.set_title(f"{workload} — 24.9M rows, local[4]")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--partitions", type=int, nargs="+", default=[8, 32, 200])
    args = parser.parse_args()

    build_parquet()  # idempotent: builds the 3-column Parquet from the raw zips if absent

    rows = run_pandas() + run_spark(args.cores, args.partitions)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_id = "run_v2-extra-spark_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "run_id": run_id,  # provenance: required by the V2 envelope/manifest gates
        "artifact_id": "reports/v2/spark/shuffle_bench.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": datetime.now(UTC).isoformat(),
        "input": {
            "rows": 24_914_442,
            "source": "NYC Citi Bike 2026-01..07 monthly archives -> Parquet (3 columns)",
            "path": str(DATA_DIR),
        },
        "environment": {
            "spark_master": f"local[{args.cores}]",
            "note": (
                "local mode = 1 JVM; executor count is not a free variable here, "
                "parallelism comes from cores. Shuffle bytes are from the Spark UI REST API "
                "(stage deltas per query). autoBroadcastJoinThreshold=-1 forces the join to "
                "shuffle; a 2K-row dimension would be broadcast in production."
            ),
        },
        "results": rows,
    }
    (OUT_DIR / "shuffle_bench.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    header = [
        "engine",
        "variant",
        "workload",
        "partitions",
        "seconds",
        "shuffle_read_mb",
        "shuffle_write_mb",
    ]
    lines = [",".join(header)] + [
        ",".join("" if r[h] is None else str(r[h]) for h in header) for r in rows
    ]
    (OUT_DIR / "shuffle_bench.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    plot(rows, OUT_DIR / "shuffle_bench.png")
    print(f"wrote {OUT_DIR}/shuffle_bench.{{json,csv,png}}")


if __name__ == "__main__":
    main()
