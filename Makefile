# ShockFlow AI — standard commands.
# Only targets that execute a real, tested workflow are defined.
# Later phases add: api, web, demo.

# Real Citi Bike history for the forecasting evaluation (git-ignored per section 7.1).
# Override on the CLI: `make evaluate CITIBIKE_ZIP=path/to/other.zip`.
CITIBIKE_ZIP ?= data/raw/citibike/JC-202606-citibike-tripdata.csv.zip

.PHONY: install lint typecheck test collect-demo build-features extract-events-demo graph-upsert-demo seed-graph graph-features-demo train-baseline evaluate rebalance-demo v1-live-fixture evaluate-recommendation evaluate-recommendation-sample train-recommendation-retriever evaluate-recommendation-e2e v1-policy-simulation v1-experiment-dry-run v1-backfill-news v1-collect-news-live v1-build-event-features v1-news-vectorstore v1-evaluate-anomalies api web api-lan web-lan v2-evaluate-search v2-evaluate-predictive-lift v2-evaluate-revenue v2-import-stations db-load graph-upsert-neo4j download-citibike v2-audit v2-holdout v2-ledger v2-llm-value v2-llm-value-borough v2-mpc v2-pricing v2-copilot v2-monitor v2-rl v2-final v2-news-followups v2-kpi

install:  ## Create/refresh the dev environment (pip + venv)
	python -m venv .venv
	.venv/Scripts/pip install -e ".[dev]"

lint:  ## Ruff lint + format check
	ruff check .
	ruff format --check .

typecheck:  ## Static type check
	mypy .

test:  ## Run the test suite
	pytest

collect-demo:  ## Run all three fixture collectors offline and print a summary
	python -m pipelines.collectors.demo

build-features:  ## Aggregate demand (H3 zone x local hour) and build leakage-safe features
	python -m pipelines.features.demo

extract-events-demo:  ## Extract events from the demo news fixture (deterministic mock LLM)
	python -m pipelines.events.demo

graph-upsert-demo:  ## Upsert extracted events into the offline event graph (idempotent)
	python -m pipelines.graph.demo

seed-graph:  ## Build the event graph from repo data (news + NYC permitted events) -> JSON snapshot
	python -m scripts.build_graph

graph-features-demo:  ## Build as-of graph features at successive cutoffs (leakage-safe)
	python -m pipelines.features.graph_features_demo

train-baseline:  ## Forecasting run: seasonal-naive B0 + tuned model zoo (needs CITIBIKE_ZIP)
	python -m ml.forecasting.run $(CITIBIKE_ZIP)

evaluate:  ## GridSearch x algorithm zoo, ablation B0-B4, feature selection (needs CITIBIKE_ZIP)
	python -m ml.forecasting.run $(CITIBIKE_ZIP)

rebalance-demo:  ## Solve the golden-path rebalancing plan offline (greedy, MILP, QUBO validation)
	python -m optimization.demo

evaluate-recommendation:  ## V1-07A: measure RENT/RETURN baselines B0-B3 on real Trip History
	python -m ml.recsys.evaluate

evaluate-recommendation-sample:  ## V1-07A: fast smoke on the tiny fixture
	python -m ml.recsys.evaluate --sample

train-recommendation-retriever:  ## V1-07B: train + eval the dual-encoder retriever on real data
	python -m ml.recsys.retriever_eval

evaluate-recommendation-e2e:  ## V1-07C: train reranker + measure the full recommender (real data)
	python -m ml.recsys.reranker_eval

v1-policy-simulation:  ## V1-07D: simulate P0-P5 incentive/policy comparison (SIMULATED, offline)
	python -m ml.pricing.evaluate

v1-experiment-dry-run:  ## V1-08: clustered-switchback battery (A/A, rec, credit, hybrid) — SIMULATED
	python -m ml.experiment.evaluate

v1-backfill-news:  ## V1-01: news backfill (fixture) + coverage gate; GDELT disabled offline
	python -m pipelines.collectors.backfill_demo

v1-collect-news-live:  ## V1-01: OPT-IN live GDELT collection (needs internet) -> snapshot fixture
	ENABLE_GDELT_LIVE=true python -m pipelines.collectors.collect_live_news --live

v1-build-event-features:  ## V1-02: incremental graph-feature refresh == full rebuild (offline)
	python -m pipelines.features.incremental_demo

v1-news-vectorstore:  ## FAISS news vector store demo (semantic search + near-dup + persistence)
	python -m ml.vectorstore.demo

v1-evaluate-anomalies:  ## V1-06: run the 4 anomaly detectors on the synthetic-fault scenario
	python -m ml.anomaly.demo

v1-live-fixture:  ## V1-05: live-shadow fixture stream (micro-batches, pending_label, offline)
	python -m pipelines.live.demo

v2-evaluate-search:  ## V2-03: hybrid geo-semantic search relevance on the gold set (offline)
	python -m ml.search.evaluate

v2-evaluate-predictive-lift:  ## V2-02: predictive-lift coverage gate + honest verdict (offline)
	python -m ml.forecasting.predictive_lift_demo

v2-evaluate-revenue:  ## V2-05: flat vs event-aware dynamic-fare revenue + elasticity/severity sweep (SIMULATED)
	python -m ml.pricing.revenue_eval

download-citibike:  ## Bulk-download real Citi Bike trip months to data/raw/citibike (needs egress). Usage: make download-citibike MONTHS="202406 202407"
	python -m pipelines.collectors.download_citibike $(MONTHS)

v2-import-stations:  ## V2: import the REAL Citi Bike network from GBFS into the fixtures (needs egress)
	python -m pipelines.collectors.import_gbfs_stations --limit 40

db-load:  ## Load the station fixtures into the relational store (SQLite default; needs [rdb] extra)
	python -m services.db.demo

graph-upsert-neo4j:  ## Upsert the event graph into a LIVE Neo4j (needs [graph] extra + docker compose up neo4j)
	python -m pipelines.graph.demo --backend neo4j

api:  ## Run the offline replay API on 127.0.0.1:8000 (Demo Mode, no API key)
	python -m services.api.main

web:  ## Run the Next.js operator UI dev server (apps/web; needs npm install first)
	cd apps/web && npm run dev

# --- Phone / LAN viewing (same Wi-Fi) --------------------------------------------------------
# Open the demo on your phone: run `make api-lan` and `make web-lan LAN_IP=<your PC IP>` in two
# terminals, then browse to http://<your PC IP>:3000 on the phone. Still fully offline (no API key);
# only your local network can reach it. Find your IP: macOS `ipconfig getifaddr en0`, Linux `hostname -I`.
api-lan:  ## Serve the API on all interfaces for phone/LAN viewing (offline, same Wi-Fi)
	SHOCKFLOW_API_HOST=0.0.0.0 python -m services.api.main

web-lan:  ## Serve the UI on the LAN. Usage: make web-lan LAN_IP=192.168.0.10
	cd apps/web && NEXT_PUBLIC_API_BASE=http://$(LAN_IP):8000 npx next dev -H 0.0.0.0

v2-audit:  ## V2-00: domain-drift gate + result-envelope contract check (offline, CI-safe)
	python -m scripts.v2_audit

v2-holdout:  ## V2-01: promote a measured model + rolling H3 multi-holdout (needs data/raw/citibike)
	python -m ml.forecasting.h3_multiholdout --data-dir data/raw/citibike --windows 3

v2-ledger:  ## V2-02: profit/regret ledger over the V2-01 forecast (needs promoted_model.json)
	python -m optimization.ledger_run

v2-llm-value:  ## V2-03: No-Event/Rule-Event/LLM-Event ablation + CI + profit + LLM cost (needs data/raw/citibike_2026 + news)
	python -m ml.forecasting.llm_value

v2-llm-value-borough:  ## V2-03: borough-grain LLM value on NYC trips (structured vs LLM-news, needs data/raw/nyc + news + events)
	python -m ml.forecasting.llm_value_borough

v2-news-followups:  ## V2-03: 뉴스 후속 3질문(선행성/다른 source/다른 quantity) — committed artifact 기반 정직 판정
	python -m ml.forecasting.news_followups

v2-kpi:  ## V2: 운영 KPI(사용율/재고율/서비스레벨) — trip+GBFS+ledger, source별 정직 라벨
	python -m ml.monitoring.operational_kpis

v2-mpc:  ## V2-04: multi-period policy comparison No-Action/Greedy/MILP/MPC + Oracle (offline, simulated)
	python -m optimization.mpc_run

v2-pricing:  ## V2-05: bounded dynamic pricing + guardrail audit + A/A dry-run (offline, SIMULATED)
	python -m ml.pricing.pricing_v2_run

v2-copilot:  ## V2-06: Copilot benchmark — typed-tool numeric grounding + GraphRAG event-graph relevance (offline)
	python -m ml.copilot.benchmark
	python -m ml.copilot.graphrag_scale
	python -m ml.copilot.neutral_retrieval
	python -m ml.copilot.ragas_retrieval
	python -m ml.copilot.ragas_generation
	python -m ml.copilot.trip_parse_benchmark
	python -m ml.copilot.trip_faithfulness

v2-monitor:  ## V2-08: run manifest + freshness monitoring + delayed-label loop (leakage-safe)
	python -m ml.monitoring.run_manifest
	python -m ml.monitoring.delayed_labels

v2-rl:  ## RESEARCH: tabular Q-learning + PPO rebalancing vs No-Action/Greedy/MILP/MPC/Oracle (offline, research-only)
	python -m optimization.rl.run

v2-final:  ## V2-09: final audit — envelope honesty + completion-artifact + traceability gates -> claim_matrix.json
	python -m scripts.v2_final_audit
