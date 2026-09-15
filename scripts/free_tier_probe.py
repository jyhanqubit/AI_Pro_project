"""Measure the serving API under emulated free-tier limits (0.1 CPU share, one core).

The live Render instance could not be reached from the measurement sandbox (egress policy),
so this script reproduces the two limits that define Render's free web service — a fractional
CPU share and a single shared core — locally, and records everything else it cannot reproduce
(network RTT to the region, the cold start after spin-down, noisy neighbours).

CPU emulation: the API process is pinned to one core (`taskset`) and throttled the way
`cpulimit` does it — a SIGSTOP/SIGCONT duty cycle at `--cpu-share` (0.1 = runs 10 ms of every
100 ms). Memory is not limited because a warm worker (~217 MB) already fits the 512 MB instance;
its RSS is recorded instead.

Per endpoint the probe records p50/p95/p99 of sequential warm requests, payload bytes, and the
number of records the response carries, so latency can be judged against how much data a
request actually touches (ms per record, records per second). It then runs a short closed-loop
ramp on the model endpoint to find where the throttled process saturates.

Usage:
    python -m scripts.free_tier_probe [--cpu-share 0.1] [--levels 1 2 5 10]
Output:
    reports/v2/serving/free_tier_emulation.json / .png
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp

from scripts.load_test_api import percentile, run_level

PORT = 8021
BASE = f"http://127.0.0.1:{PORT}"
OUT_JSON = Path("reports/v2/serving/free_tier_emulation.json")
OUT_PNG = Path("reports/v2/serving/free_tier_emulation.png")

# (label, path, how to count the records a response carries)
ENDPOINTS: list[tuple[str, str, str]] = [
    ("health", "/v1/health", "none"),
    ("forecasts", "/v1/forecasts", "forecasts"),
    ("model_forecast_top10", "/v2/model/forecast?top=10", "n_zones"),
    ("model_forecast_top200", "/v2/model/forecast?top=200", "n_zones"),
    ("operator_statistics", "/v2/operator/statistics", "largest_list"),
]


def _count_records(payload: Any, how: str) -> int | None:
    if how == "none":
        return None
    if how == "n_zones":
        return int(payload.get("n_zones", 0))
    if how == "forecasts":
        return len(payload.get("forecasts", []))
    if how == "largest_list":
        best = 0

        def walk(o: Any) -> None:
            nonlocal best
            if isinstance(o, list):
                best = max(best, len(o))
                for x in o:
                    walk(x)
            elif isinstance(o, dict):
                for x in o.values():
                    walk(x)

        walk(payload)
        return best
    return None


class CpuThrottle:
    """cpulimit-style duty cycle: SIGSTOP for (1-share) of each period, SIGCONT for share."""

    def __init__(self, pid: int, share: float, period_ms: float = 100.0) -> None:
        self.pid, self.share, self.period = pid, share, period_ms / 1000.0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        run = self.period * self.share
        idle = self.period - run
        while not self._stop.is_set():
            os.kill(self.pid, signal.SIGCONT)
            time.sleep(run)
            os.kill(self.pid, signal.SIGSTOP)
            time.sleep(idle)
        os.kill(self.pid, signal.SIGCONT)

    def start(self) -> None:
        if self.share < 1.0:
            self._t.start()

    def stop(self) -> None:
        self._stop.set()
        if self._t.is_alive():
            self._t.join(timeout=2)
        try:
            os.kill(self.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass


def _rss_mb(pid: int) -> float | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS"):
                return round(int(line.split()[1]) / 1024, 0)
    except OSError:
        return None
    return None


async def _probe_endpoint(session: aiohttp.ClientSession, path: str, how: str, n: int) -> dict:
    lat: list[float] = []
    size = 0
    records: int | None = None
    for i in range(n + 5):  # first 5 are warmup for this path
        t0 = time.perf_counter()
        async with session.get(BASE + path) as resp:
            body = await resp.read()
        dt = time.perf_counter() - t0
        if i >= 5:
            lat.append(dt)
        if i == 0:
            size = len(body)
            try:
                records = _count_records(json.loads(body), how)
            except ValueError:
                records = None
    p50, p95, p99 = (percentile(lat, q) * 1000 for q in (50, 95, 99))
    return {
        "path": path,
        "n_requests": n,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "p99_ms": round(p99, 1),
        "payload_bytes": size,
        "records": records,
        "ms_per_record": round(p50 / records, 3) if records else None,
        "records_per_s_sequential": round(records / (p50 / 1000), 0) if records else None,
    }


async def _run(args: argparse.Namespace, pid: int) -> dict:
    # cold-ish first call: the process is warm but the model bundle is not loaded yet
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as s:
        async with s.get(BASE + "/v2/model/forecast?top=10") as r:
            await r.read()
        first_call_ms = round((time.perf_counter() - t0) * 1000, 0)
        endpoints = [await _probe_endpoint(s, p, how, args.n) for _, p, how in ENDPOINTS]
    for (label, _, _), e in zip(ENDPOINTS, endpoints, strict=True):
        e["endpoint"] = label
    levels = []
    for users in args.levels:
        row = await run_level(BASE + "/v2/model/forecast?top=10", users, args.duration, 2.0)
        levels.append(
            {k: row[k] for k in ("concurrency", "p50_ms", "p95_ms", "p99_ms", "rps", "error_rate")}
        )
        print(levels[-1])
    return {"first_call_ms": first_call_ms, "endpoints": endpoints, "levels": levels}


def plot(res: dict, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    eps = res["endpoints"]
    names = [e["endpoint"] for e in eps]
    ax1.barh(names, [e["p50_ms"] for e in eps], color="#4c72b0", label="p50")
    ax1.barh(
        names,
        [e["p95_ms"] - e["p50_ms"] for e in eps],
        left=[e["p50_ms"] for e in eps],
        color="#dd8452",
        label="p50→p95",
    )
    ax1.set_xlabel("latency (ms), sequential, 0.1 CPU share")
    ax1.set_title("Per-endpoint latency (emulated free tier)")
    ax1.invert_yaxis()
    ax1.legend(fontsize=9)
    ax1.grid(True, axis="x", alpha=0.3)
    lv = res["levels"]
    x = [r["concurrency"] for r in lv]
    ax2.plot(x, [r["p99_ms"] for r in lv], "^-", label="p99 ms")
    ax2.set_xlabel("concurrent users (closed-loop)")
    ax2.set_ylabel("p99 latency (ms)")
    ax2b = ax2.twinx()
    ax2b.plot(x, [r["rps"] for r in lv], "x:", color="gray", label="req/s")
    ax2b.set_ylabel("requests / s", color="gray")
    ax2.set_title("Model endpoint ramp, 0.1 CPU share")
    ax2.grid(True, alpha=0.3)
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cpu-share", type=float, default=0.1)
    ap.add_argument("--n", type=int, default=40, help="sequential requests per endpoint")
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 5, 10])
    ap.add_argument("--duration", type=float, default=10.0)
    args = ap.parse_args()

    env = {**os.environ, "OMP_NUM_THREADS": "1", "SHOCKFLOW_MODE": "demo_fixture"}
    server = subprocess.Popen(
        [
            "taskset",
            "-c",
            "0",
            sys.executable,
            "-m",
            "uvicorn",
            "services.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Throttle from the very first instruction so startup (imports, model load) is measured
        # under the same CPU share the requests get.
        throttle = CpuThrottle(server.pid, args.cpu_share)
        throttle.start()
        try:
            t0 = time.perf_counter()
            ready_ms: float | None = None
            deadline = t0 + 300
            while time.perf_counter() < deadline:
                try:
                    import urllib.request

                    with urllib.request.urlopen(BASE + "/v1/health", timeout=5) as r:
                        if r.status == 200:
                            ready_ms = round((time.perf_counter() - t0) * 1000, 0)
                            break
                except Exception:  # noqa: BLE001 - not up yet
                    time.sleep(0.5)
            res = asyncio.run(_run(args, server.pid))
            res["startup_to_ready_ms"] = ready_ms
        finally:
            throttle.stop()
        res["rss_mb_after"] = _rss_mb(server.pid)
    finally:
        server.terminate()
        server.wait(timeout=10)

    payload = {
        "run_id": "run_v2-07freetier_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "artifact_id": str(OUT_JSON),
        "mode": "historical_replay",
        "claim_status": "measured",
        "freshness": datetime.now(UTC).isoformat(),
        "emulation": {
            "cpu_share": args.cpu_share,
            "cores": 1,
            "method": "taskset -c 0 + cpulimit-style SIGSTOP/SIGCONT duty cycle (100 ms period)",
            "omp_num_threads": 1,
            "workers": 1,
            "target": "Render free web service: 0.1 CPU, 512 MB, single instance",
            "not_reproduced": [
                "network RTT from the user's region to Render "
                "(sandbox egress policy blocked the live URL)",
                "cold start after spin-down (~30-60 s on Render)",
                "noisy neighbours on the shared host",
            ],
        },
        **res,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    plot(res, OUT_PNG)
    print(json.dumps({k: payload[k] for k in ("first_call_ms", "rss_mb_after")}))
    for e in res["endpoints"]:
        print(e)
    print(f"wrote {OUT_JSON} and {OUT_PNG}")


if __name__ == "__main__":
    main()
