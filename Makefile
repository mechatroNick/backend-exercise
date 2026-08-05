.DEFAULT_GOAL := check

UV ?= uv

HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: sync format format-check lint typecheck migrate migration-check run bootstrap test check

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

run:
	$(UV) run uvicorn app.main:create_app --factory --host $(HOST) --port $(PORT) --workers 1 --no-access-log --log-level critical

bootstrap:
	@$(UV) run alembic upgrade head
	@exec $(UV) run uvicorn app.main:create_app --factory --host $(HOST) --port $(PORT) --workers 1 --no-access-log --log-level critical

test:
	$(UV) run pytest

check: format-check lint typecheck test
