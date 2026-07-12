# ShockFlow AI — standard commands.
# Only targets that execute a real, tested workflow are defined.
# Later phases add: train-baseline, evaluate, api, web, demo.

.PHONY: install lint typecheck test collect-demo build-features extract-events-demo graph-upsert-demo

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
