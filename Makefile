# ShockFlow AI — standard commands.
# Only targets that execute a real, tested workflow are defined.
# Later phases add: api, web, demo.

# Real Citi Bike history for the forecasting evaluation (git-ignored per section 7.1).
# Override on the CLI: `make evaluate CITIBIKE_ZIP=path/to/other.zip`.
CITIBIKE_ZIP ?= data/raw/citibike/JC-202606-citibike-tripdata.csv.zip

.PHONY: install lint typecheck test collect-demo build-features extract-events-demo graph-upsert-demo graph-features-demo train-baseline evaluate

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

graph-features-demo:  ## Build as-of graph features at successive cutoffs (leakage-safe)
	python -m pipelines.features.graph_features_demo

train-baseline:  ## Forecasting run: seasonal-naive B0 + tuned model zoo (needs CITIBIKE_ZIP)
	python -m ml.forecasting.run $(CITIBIKE_ZIP)

evaluate:  ## GridSearch x algorithm zoo, ablation B0-B4, feature selection (needs CITIBIKE_ZIP)
	python -m ml.forecasting.run $(CITIBIKE_ZIP)
