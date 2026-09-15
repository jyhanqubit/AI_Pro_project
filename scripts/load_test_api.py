"""Closed-loop load test for the promoted-model serving endpoint (V2-07).

Measures how p50/p95/p99 latency, throughput and error rate change as the number of
concurrent users grows, against the same single-process uvicorn server that `make api`
starts. Each simulated user is a coroutine that issues requests back-to-back
(closed-loop), so concurrency N means "N requests in flight at all times".

Honest-measurement rules baked in:
- A warmup phase runs before any recorded level, so the one-off cost of loading
  promoted_model.joblib and the serving snapshot never contaminates the numbers.
- Every recorded request carries its own wall-clock latency; percentiles are computed
  from the raw samples, never estimated.
- The artifact records that client and server share one machine: there is no network
  RTT in these numbers, and the client competes with the server for the same CPUs.

Usage:
    python -m scripts.load_test_api --url http://127.0.0.1:8000/v2/model/forecast?top=20
Outputs (committed, small):
    reports/v2/serving/load_test.csv   per-level metrics table
    reports/v2/serving/load_test.json  same + environment + knee analysis
    reports/v2/serving/load_test_p99.png  latency-vs-concurrency chart
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

DEFAULT_URL = "http://127.0.0.1:8000/v2/model/forecast?top=20"
DEFAULT_LEVELS = (1, 5, 10, 20, 50, 100)
OUT_DIR = Path("reports/v2/serving")
KNEE_RATIO = 2.0  # p99 jumping to >= 2x the previous level marks the knee


def percentile(samples: list[float], q: float) -> float:
    """Nearest-rank percentile on the raw samples (no interpolation surprises)."""
    if not samples:
        return float("nan")
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, max(0, round(q / 100.0 * len(ordered)) - 1))
    return ordered[idx]


async def _user_loop(
    session: aiohttp.ClientSession,
    url: str,
    stop_at: float,
    latencies: list[float],
    errors: list[str],
) -> None:
    while time.perf_counter() < stop_at:
        t0 = time.perf_counter()
        try:
            async with session.get(url) as resp:
                await resp.read()
                elapsed = time.perf_counter() - t0
                if resp.status == 200:
                    latencies.append(elapsed)
                else:
                    errors.append(f"http_{resp.status}")
        except Exception as exc:  # noqa: BLE001 - a failed request is a data point, not a crash
            errors.append(type(exc).__name__)


async def run_level(
    url: str, users: int, duration_s: float, warmup_s: float, keepalive: bool = True
) -> dict[str, Any]:
    # With a multi-worker server, keep-alive pins each connection to one worker for its
    # whole life, so a handful of persistent connections can land unevenly and idle some
    # workers. force_close re-balances at the cost of a loopback TCP setup per request.
    connector = aiohttp.TCPConnector(limit=users, force_close=not keepalive)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Per-level warmup: same concurrency, results discarded (connection setup,
        # server thread-pool growth, allocator steady state).
        sink: list[float] = []
        sink_err: list[str] = []
        stop = time.perf_counter() + warmup_s
        await asyncio.gather(
            *(_user_loop(session, url, stop, sink, sink_err) for _ in range(users))
        )

        latencies: list[float] = []
        errors: list[str] = []
        t_start = time.perf_counter()
        stop = t_start + duration_s
        await asyncio.gather(
            *(_user_loop(session, url, stop, latencies, errors) for _ in range(users))
        )
        elapsed = time.perf_counter() - t_start

    n = len(latencies)
    total = n + len(errors)
    return {
        "concurrency": users,
        "requests_ok": n,
        "requests_error": len(errors),
        "error_rate": round(len(errors) / total, 6) if total else 0.0,
        "duration_s": round(elapsed, 3),
        "rps": round(n / elapsed, 1) if elapsed else 0.0,
        "p50_ms": round(percentile(latencies, 50) * 1000, 2),
        "p95_ms": round(percentile(latencies, 95) * 1000, 2),
        "p99_ms": round(percentile(latencies, 99) * 1000, 2),
        "max_ms": round(max(latencies) * 1000, 2) if latencies else float("nan"),
        "error_kinds": sorted(set(errors)),
    }


def find_knee(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """First level whose p99 is >= KNEE_RATIO x the previous level's p99."""
    for prev, cur in zip(rows, rows[1:], strict=False):
        if prev["p99_ms"] > 0 and cur["p99_ms"] / prev["p99_ms"] >= KNEE_RATIO:
            return {
                "knee_concurrency": cur["concurrency"],
                "p99_before_ms": prev["p99_ms"],
                "p99_after_ms": cur["p99_ms"],
                "ratio": round(cur["p99_ms"] / prev["p99_ms"], 2),
                "rule": f"p99 >= {KNEE_RATIO}x previous level",
            }
    return {"knee_concurrency": None, "rule": f"p99 >= {KNEE_RATIO}x previous level"}


def plot(rows: list[dict[str, Any]], out_png: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = [r["concurrency"] for r in rows]
    fig, ax1 = plt.subplots(figsize=(7, 4.2))
    for key, style in (("p50_ms", "o--"), ("p95_ms", "s--"), ("p99_ms", "^-")):
        ax1.plot(x, [r[key] for r in rows], style, label=key.replace("_ms", ""))
    ax1.set_xlabel("concurrent users (closed-loop)")
    ax1.set_ylabel("latency (ms)")
    ax1.set_xscale("log")
    ax1.set_xticks(x)
    ax1.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax1.grid(True, alpha=0.3)
    ax2 = ax1.twinx()
    ax2.plot(x, [r["rps"] for r in rows], "x:", color="gray", label="RPS")
    ax2.set_ylabel("requests / s", color="gray")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title("Serving endpoint latency vs concurrency (same-machine, no network RTT)")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=140)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--levels", type=int, nargs="+", default=list(DEFAULT_LEVELS))
    parser.add_argument("--duration", type=float, default=15.0, help="seconds measured per level")
    parser.add_argument("--warmup", type=float, default=3.0, help="warmup seconds per level")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--no-keepalive", action="store_true", help="reconnect per request (fair worker balancing for multi-worker servers)")
    args = parser.parse_args()

    # Global warmup: absorb the one-off joblib/snapshot load before level 1.
    async with aiohttp.ClientSession() as session:
        for _ in range(50):
            async with session.get(args.url) as resp:
                await resp.read()

    rows = []
    for users in args.levels:
        row = await run_level(args.url, users, args.duration, args.warmup, keepalive=not args.no_keepalive)
        rows.append(row)
        print(
            f"c={row['concurrency']:>4}  p50={row['p50_ms']:>7.2f}ms  p95={row['p95_ms']:>7.2f}ms  "
            f"p99={row['p99_ms']:>7.2f}ms  rps={row['rps']:>7.1f}  err={row['error_rate']:.4f}"
        )

    knee = find_knee(rows)
    payload = {
        "artifact_id": "reports/v2/serving/load_test.json",
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.url,
        "method": (
            "closed-loop: each user coroutine issues requests back-to-back; "
            f"{args.warmup}s warmup + {args.duration}s measured per level; "
            "50-request global warmup excludes cold-start model load; "
            f"keepalive={not args.no_keepalive}"
        ),
        "environment": {
            "cpus": os.cpu_count(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "server": "uvicorn single process (make api default)",
            "same_machine": True,
            "caveat": (
                "client and server share one machine: numbers exclude network RTT and the "
                "load generator competes with the server for CPU at high concurrency"
            ),
        },
        "levels": rows,
        "knee": knee,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "load_test.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    header = [
        "concurrency", "requests_ok", "requests_error", "error_rate",
        "duration_s", "rps", "p50_ms", "p95_ms", "p99_ms", "max_ms",
    ]
    csv_lines = [",".join(header)] + [
        ",".join(str(r[h]) for h in header) for r in rows
    ]
    (args.out_dir / "load_test.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    plot(rows, args.out_dir / "load_test_p99.png")
    print(f"knee: {knee}")
    print(f"wrote {args.out_dir}/load_test.{{csv,json}} and load_test_p99.png")


if __name__ == "__main__":
    asyncio.run(main())
