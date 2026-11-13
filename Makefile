# Pricelight developer tasks. Requires uv (https://docs.astral.sh/uv/) and Node.js 20.19+.
.DEFAULT_GOAL := help
DATA ?= data
SITE := site

.PHONY: help setup demo data dev build preview test test-py test-site e2e lint format typecheck check screenshots benchmark version-check clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install Python and Node dependencies
	uv sync
	cd $(SITE) && npm ci

demo: ## Generate the synthetic demo dataset and publish it to the site
	uv run pricelight --data $(DATA) run --demo --publish $(SITE)/public/data

data: ## Ingest + build from $(DATA)/manifest.csv (real files) and publish to the site
	uv run pricelight --data $(DATA) run --publish $(SITE)/public/data

dev: ## Run the site dev server (http://localhost:5173)
	cd $(SITE) && npm run dev

build: ## Production build of the site into site/dist
	cd $(SITE) && npm run build

preview: build ## Serve the production build (http://localhost:4173)
	cd $(SITE) && npm run preview

test: test-py test-site ## Run all unit tests

test-py: ## Python tests (parser + pipeline, with doctests)
	uv run pytest

test-site: ## Site unit tests
	cd $(SITE) && npm test

e2e: build ## End-to-end browser tests (Playwright)
	cd $(SITE) && npm run e2e

lint: ## Lint Python and check formatting everywhere
	uv run ruff check .
	uv run ruff format --check .
	cd $(SITE) && npm run format:check

format: ## Format all code
	uv run ruff format .
	uv run ruff check --fix .
	cd $(SITE) && npm run format

typecheck: ## mypy (strict) and svelte-check
	uv run mypy
	cd $(SITE) && npm run check

check: version-check lint typecheck test ## Everything CI runs except e2e

version-check: ## Verify all component versions match VERSION
	python3 scripts/version.py check

screenshots: build ## Regenerate README screenshots (needs a preview server)
	cd $(SITE) && (npm run preview >/dev/null 2>&1 & echo $$! > .preview.pid; sleep 3; node scripts/screenshots.mjs; kill `cat .preview.pid`; rm -f .preview.pid)

benchmark: ## Parser throughput on 200 MB synthetic files
	uv run python scripts/benchmark.py --size-mb 200

clean: ## Remove build outputs and generated data
	rm -rf $(DATA) dist $(SITE)/dist $(SITE)/public/data $(SITE)/test-results $(SITE)/playwright-report .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml
