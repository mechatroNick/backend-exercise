"""HTTP evidence for ADR-007's local rate-limit transport contract."""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlmodel import Session

from app.api.rate_limit import RateLimiter
from app.auth.models import User
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "rate-limit-correct-horse-battery-staple"


class FakeMonotonic:
    """A request-test clock that can model invalid limiter time values."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": database_url,
        "stats_refresh_enabled": False,
        "rate_limit_auth_requests": 10,
        "rate_limit_auth_window_seconds": 60,
        "rate_limit_bookmark_requests": 10,
        "rate_limit_bookmark_window_seconds": 60,
        "rate_limit_max_keys": 10,
        "rate_limit_idle_ttl_seconds": 60,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture
def client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    del migrated_engine
    app = create_app(_settings(database_url))
    with TestClient(app, raise_server_exceptions=False) as started:
        yield started


def _register(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": _PASSWORD,
        },
    )
    assert response.status_code == 201
    return str(response.json()["token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create(client: TestClient, token: str, title: str = "Rate limited") -> int:
    response = client.post(
        "/api/bookmarks",
        headers=_headers(token),
        json={"url": "https://example.com/rate", "title": title, "tags": ["rate"]},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _limited(response: Any) -> None:
    assert response.status_code == 429
    assert response.json() == {
        "error": {"code": "rate_limited", "message": "Too many requests.", "details": None}
    }
    assert response.headers["retry-after"].isdigit()
    assert int(response.headers["retry-after"]) >= 1
    assert response.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in response.headers


def test_auth_register_and_login_share_socket_peer_policy_and_ignore_forwarded_for(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(_settings(database_url, rate_limit_auth_requests=2))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "alice")
        assert (
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "198.51.100.1"},
                json={"email": "alice@example.com", "password": _PASSWORD},
            ).status_code
            == 200
        )
        _limited(
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.99"},
                json={"email": "alice@example.com", "password": _PASSWORD},
            )
        )
    assert token


def test_auth_rate_limit_precedes_service_work_and_preserves_no_side_effects(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(_settings(database_url, rate_limit_auth_requests=1))
    with TestClient(app, raise_server_exceptions=False) as client:
        _register(client, "first")
        _limited(
            client.post(
                "/api/auth/register",
                json={
                    "username": "second",
                    "email": "second@example.com",
                    "password": _PASSWORD,
                },
            )
        )
    with Session(app.state.engine) as session:
        assert [row[0] for row in session.exec(select(User.username)).all()] == ["first"]


def test_all_six_bookmark_operations_share_one_verified_user_bucket(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(_settings(database_url, rate_limit_bookmark_requests=6))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "alice")
        bookmark_id = _create(client, token)
        headers = _headers(token)
        assert client.get("/api/bookmarks", headers=headers).status_code == 200
        assert client.get("/api/bookmarks/stats", headers=headers).status_code == 200
        assert client.get(f"/api/bookmarks/{bookmark_id}", headers=headers).status_code == 200
        assert (
            client.patch(
                f"/api/bookmarks/{bookmark_id}", headers=headers, json={"title": "Updated"}
            ).status_code
            == 200
        )
        assert client.delete(f"/api/bookmarks/{bookmark_id}", headers=headers).status_code == 204
        _limited(client.get("/api/bookmarks", headers=headers))


def test_bookmark_limits_are_isolated_by_verified_user_and_invalid_bearer_keeps_401_precedence(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(_settings(database_url, rate_limit_bookmark_requests=1))
    with TestClient(app, raise_server_exceptions=False) as client:
        alice = _register(client, "alice")
        bob = _register(client, "bob")
        _create(client, alice, "alice")
        _create(client, bob, "bob")
        _limited(client.get("/api/bookmarks", headers=_headers(alice)))
        invalid = client.get("/api/bookmarks", headers={"Authorization": "Bearer invalid"})

    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "authentication_failed"
    assert "retry-after" not in invalid.headers


def test_excluded_health_docs_openapi_unknown_and_test_seam_do_not_consume_public_buckets(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(_settings(database_url, rate_limit_auth_requests=1))
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "alice")
        assert client.get("/health/live").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/not-a-route").status_code == 404
        assert client.get("/__track02/protected", headers=_headers(token)).status_code == 200
        _limited(
            client.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "password": _PASSWORD},
            )
        )


def test_disabled_test_policy_is_an_explicit_supported_configuration(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    app = create_app(
        _settings(
            database_url,
            rate_limit_enabled=False,
            rate_limit_auth_requests=1,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        _register(client, "alice")
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "alice@example.com", "password": _PASSWORD},
            ).status_code
            == 200
        )


def test_rate_limit_event_is_low_volume_json_and_never_reflects_request_sensitive_values(
    database_url: str, migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    import app.main as main

    stream = io.StringIO()
    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    app = create_app(_settings(database_url, rate_limit_auth_requests=1))
    body_sentinel = "rate-limit-body-sentinel-do-not-emit"
    forwarded_sentinel = "rate-limit-forwarded-sentinel-do-not-emit"
    with TestClient(app, raise_server_exceptions=False) as client:
        _register(client, "alice")
        _limited(
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": forwarded_sentinel},
                json={"email": "alice@example.com", "password": body_sentinel},
            )
        )
        _limited(
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": forwarded_sentinel},
                json={"email": "alice@example.com", "password": body_sentinel},
            )
        )

    records = [json.loads(line) for line in stream.getvalue().splitlines() if line]
    rejections = [record for record in records if record["event"] == "rate_limit.rejected"]
    assert len(rejections) == 1
    assert rejections[0]["context"] == {
        "policy": "auth",
        "retry_after_seconds": 60,
        "route_family": "authentication",
        "capacity_exhausted": False,
    }
    assert body_sentinel not in stream.getvalue()
    assert forwarded_sentinel not in stream.getvalue()


@pytest.mark.parametrize("invalid_time", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_limiter_clock_is_a_redacted_unexpected_500(
    database_url: str, migrated_engine: Engine, invalid_time: float
) -> None:
    del migrated_engine
    clock = FakeMonotonic(invalid_time)
    app = create_app(_settings(database_url, rate_limit_auth_requests=1))
    app.state.rate_limiter = RateLimiter(
        enabled=True,
        auth_requests=1,
        auth_window_seconds=60,
        bookmark_requests=1,
        bookmark_window_seconds=60,
        max_keys=10,
        idle_ttl_seconds=60,
        monotonic=clock,
        identity_key=b"deterministic-rate-limit-key",
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": _PASSWORD},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error.", "details": None}
    }


def test_backward_limiter_clock_is_a_redacted_unexpected_500(
    database_url: str, migrated_engine: Engine
) -> None:
    del migrated_engine
    clock = FakeMonotonic()
    app = create_app(_settings(database_url, rate_limit_auth_requests=2))
    app.state.rate_limiter = RateLimiter(
        enabled=True,
        auth_requests=2,
        auth_window_seconds=60,
        bookmark_requests=1,
        bookmark_window_seconds=60,
        max_keys=10,
        idle_ttl_seconds=60,
        monotonic=clock,
        identity_key=b"deterministic-rate-limit-key",
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        _register(client, "alice")
        clock.value = -1.0
        response = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": _PASSWORD},
        )

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Internal server error.",
        "details": None,
    }
