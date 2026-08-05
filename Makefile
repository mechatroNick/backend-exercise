.DEFAULT_GOAL := check

UV ?= uv

.PHONY: sync format format-check lint typecheck check

sync:
	$(UV) sync --locked

format:
	$(UV) run ruff format .

format-check:
	$(UV) run ruff format --check .

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy app

check: format-check lint typecheck
