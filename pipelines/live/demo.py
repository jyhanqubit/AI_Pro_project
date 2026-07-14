"""Live-shadow fixture-stream demo (offline): python -m pipelines.live.demo."""

from __future__ import annotations

from config.collectors import NEWS_DEMO_FIXTURE
from pipelines.collectors import NewsFixtureCollector
from pipelines.events import build_provider, extract_events
from pipelines.live import run_shadow_stream


def main() -> None:
    articles = NewsFixtureCollector(NEWS_DEMO_FIXTURE).collect().records
    events, _ = extract_events(articles, build_provider("mock"))
    res = run_shadow_stream(events, articles)
    d = res.as_dict()
    print(f"micro-batches processed: {d['batches_processed']}  "
          f"pending predictions: {d['n_pending_predictions']}  all_pending={d['all_pending']}")
    print(f"latency p50={d['latency_p50_ms']}ms p95={d['latency_p95_ms']}ms")
    for p in d["predictions"]:
        print(f"  {p['cutoff']}  {p['zone_id']}  exposure={p['event_exposure']}  "
              f"claim={p['claim_state']}")
    print("Predictions are pending_label until delayed Trip-History labels arrive (§11).")


if __name__ == "__main__":
    main()
