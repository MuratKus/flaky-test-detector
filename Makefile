.DEFAULT_GOAL := help

.PHONY: dev lint format typecheck test test-cov check help

dev: ## Install all dependencies
	uv sync

lint: ## Run ruff linter
	uv run ruff check .

format: ## Run ruff formatter
	uv run ruff format .

typecheck: ## Run ty type checker
	uv run ty check

test: ## Run tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --cov=flakydetector --cov-report=term-missing

check: lint typecheck test ## Run lint + typecheck + tests

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
