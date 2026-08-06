"""Health-route integration against lifecycle-owned, migrated infrastructure."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.health import get_readiness_evaluator
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def disabled_client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    del migrated_engine
    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            stats_refresh_enabled=False,
        )
    )
    with TestClient(app) as client:
        yield client


def test_liveness_is_static_public_and_never_consults_readiness(
    disabled_client: TestClient,
) -> None:
    disabled_client.app.dependency_overrides[get_readiness_evaluator] = lambda: (
        _ for _ in ()
    ).throw(AssertionError("liveness must not resolve readiness"))

    response = disabled_client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
    assert response.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in response.headers


def test_disabled_readiness_requires_only_the_migrated_database(
    disabled_client: TestClient,
) -> None:
    response = disabled_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "reason" not in response.text


def test_readiness_maps_dependency_failure_to_one_redacted_503(
    disabled_client: TestClient,
) -> None:
    evaluator = disabled_client.app.state.readiness_evaluator
    evaluator._database_probe = lambda _session: False

    response = disabled_client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    assert "database" not in response.text


def test_enabled_readiness_observes_the_real_initial_refresh(
    database_url: str,
    migrated_engine: Engine,
) -> None:
    del migrated_engine
    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            stats_refresh_enabled=True,
            stats_refresh_interval_seconds=1,
            stats_stale_after_seconds=2,
            stats_full_reconciliation_seconds=2,
            stats_dirty_max_age_seconds=2,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"


def test_health_surface_has_only_the_two_authorized_paths(
    disabled_client: TestClient,
) -> None:
    assert disabled_client.get("/health").status_code == 404
    assert disabled_client.get("/health/live/details").status_code == 404
    assert disabled_client.get("/health/ready/details").status_code == 404
