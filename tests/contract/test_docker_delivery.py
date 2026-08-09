"""Static delivery contracts for the intentionally local Docker topology."""

from __future__ import annotations

from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_repository_file(relative_path: str) -> str:
    return (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_container_build_uses_python_312_locked_dependencies_and_a_minimal_runtime() -> None:
    dockerfile = _read_repository_file("Dockerfile")

    assert "FROM python:3.12.12-slim-bookworm AS builder" in dockerfile
    assert "FROM python:3.12.12-slim-bookworm AS runtime" in dockerfile
    assert "COPY pyproject.toml uv.lock ./" in dockerfile
    assert "uv sync --locked --no-dev --no-install-project" in dockerfile
    assert "uv sync --locked --no-dev" in dockerfile
    assert "COPY --from=builder --chown=app:app /opt/venv /opt/venv" in dockerfile
    assert "COPY ." not in dockerfile
    assert "USER app" in dockerfile
    assert "APP_WORKER_COUNT=1" in dockerfile
    assert '--workers", "1"' in dockerfile


def test_container_uses_a_writable_local_sqlite_volume_and_liveness_healthcheck() -> None:
    dockerfile = _read_repository_file("Dockerfile")

    assert "DATABASE_URL=sqlite:////data/bookmarks.db" in dockerfile
    assert "install --directory --owner=app --group=app /data" in dockerfile
    assert 'VOLUME ["/data"]' in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "http://127.0.0.1:8000/health/live" in dockerfile
    assert "STOPSIGNAL SIGTERM" in dockerfile


def test_entrypoint_runs_only_alembic_for_schema_then_execs_the_application() -> None:
    entrypoint = _read_repository_file("scripts/docker-entrypoint.sh")
    dockerfile = _read_repository_file("Dockerfile")

    assert entrypoint.startswith("#!/bin/sh\nset -eu\n")
    assert '"${1:-}" = "migrate-only"' in entrypoint
    assert entrypoint.count("alembic upgrade head") == 2
    assert "create_all" not in entrypoint
    assert 'exec "$@"' in entrypoint
    assert 'ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]' in dockerfile
    assert "app.main:create_app" in dockerfile


def test_dockerignore_excludes_secrets_generated_artifacts_and_unneeded_context() -> None:
    dockerignore = _read_repository_file(".dockerignore")

    for ignored_path in (
        ".git",
        ".env",
        ".env.*",
        "*.env",
        ".aws/",
        ".ssh/",
        "*.pem",
        "*.key",
        "*.secret",
        "*.db",
        ".venv/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".coverage",
        "tests/",
        ".tracks/",
    ):
        assert ignored_path in dockerignore
    assert "!scripts/docker-entrypoint.sh" in dockerignore


def test_container_delivery_allows_private_projections_without_history_or_external_workers() -> (
    None
):
    delivery = "\n".join(
        _read_repository_file(relative_path)
        for relative_path in ("Dockerfile", ".dockerignore", "scripts/docker-entrypoint.sh")
    ).lower()

    for forbidden_component in ("celery", "kafka", "redis", "dramatiq", "rq"):
        assert forbidden_component not in delivery

    migration = _read_repository_file("alembic/versions/0003_weekly_stats_projections.py")
    assert "bookmark_stats_window_working" in migration
    assert "bookmark_stats_window_point" in migration
    assert "bookmark_stats_projection_state" in migration
    public_bookmark_router = _read_repository_file("app/bookmarks/router.py").lower()
    assert "history" not in public_bookmark_router
    assert "weekly" not in public_bookmark_router
