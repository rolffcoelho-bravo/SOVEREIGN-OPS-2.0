.PHONY: install verify lint typecheck test audit quickstart api clean help

PYTHON  := uv run --locked
UV      := uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (locked)
	$(UV) sync --locked

verify: lint typecheck test audit ## Run the full verification pipeline

lint: ## Lint and format check
	$(PYTHON) ruff check .
	$(PYTHON) ruff format --check .

typecheck: ## Run mypy strict type checking
	$(PYTHON) mypy

test: ## Run pytest suite
	$(PYTHON) pytest --junitxml=test-results.xml

audit: ## Security and dependency audit
	$(PYTHON) python scripts/smoke_http.py
	$(PYTHON) python scripts/check_secrets.py
	$(UV) export --locked --all-groups --no-emit-project --format requirements-txt --output-file audit-requirements.txt
	$(PYTHON) pip-audit --requirement audit-requirements.txt --disable-pip --no-deps --strict --progress-spinner off --cache-dir .cache/pip-audit

quickstart: ## Run the quick-start vignette (synthetic data)
	$(PYTHON) python notebooks/quickstart.py

api: ## Start the development API server
	$(PYTHON) uvicorn sovereign_ops.api:app --host 127.0.0.1 --port 8000

clean: ## Remove build artifacts
	rm -rf .cache/ .mypy_cache/ .pytest_cache/ .ruff_cache/
	rm -f test-results.xml audit-requirements.txt
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
