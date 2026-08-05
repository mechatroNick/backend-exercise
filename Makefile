.DEFAULT_GOAL := check

UV ?= uv

.PHONY: sync format format-check lint typecheck migrate migration-check check

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

migrate:
	$(UV) run alembic upgrade head

migration-check:
	$(UV) run alembic check

check: format-check lint typecheck
