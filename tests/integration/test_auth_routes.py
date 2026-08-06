"""HTTP contract evidence for the Track 02 authentication transport."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import get_auth_service
from app.auth.models import User
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(database_url: str, migrated_engine: object) -> TestClient:
    """Start one app against an Alembic-migrated database for each transport case."""
    del migrated_engine
    app = create_app(
        Settings(app_env="test", database_url=database_url, stats_refresh_enabled=False)
    )
    with TestClient(app, raise_server_exceptions=False) as started:
        yield started


def _register(
    client: TestClient, *, username: str = " Alice ", email: str = " Alice@Example.com "
) -> Any:
    return client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": _PASSWORD},
    )


def test_register_login_and_protected_flow_have_the_exact_public_shape(client: TestClient) -> None:
    registered = _register(client)

    assert registered.status_code == 201
    body = registered.json()
    assert set(body) == {"user", "token"}
    assert body["user"] == {"id": 1, "username": "alice", "email": "alice@example.com"}
    assert isinstance(body["token"], str) and body["token"]

    logged_in = client.post(
        "/api/auth/login", json={"email": " ALICE@example.COM ", "password": _PASSWORD}
    )
    assert logged_in.status_code == 200
    assert set(logged_in.json()) == {"user", "token"}
    protected = client.get(
        "/__track02/protected", headers={"Authorization": f"Bearer {logged_in.json()['token']}"}
    )
    assert protected.status_code == 200
    assert protected.json() == {"user_id": 1}


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        (
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": _PASSWORD,
                "x": "track02-untrusted-extra-value",
            },
            422,
        ),
        ({"username": "alice", "email": "alice@example.com", "password": "too-short"}, 422),
        (
            {
                "email": "alice@example.com",
                "password": _PASSWORD,
                "x": "track02-untrusted-extra-value",
            },
            422,
        ),
    ],
)
def test_auth_body_validation_is_strict_and_does_not_echo_inputs(
    client: TestClient, payload: dict[str, str], status: int
) -> None:
    path = "/api/auth/register" if "username" in payload else "/api/auth/login"
    response = client.post(path, json=payload)

    assert response.status_code == status
    assert response.json()["error"]["code"] == "validation_error"
    assert _PASSWORD not in response.text
    assert payload.get("x", "not-present") not in response.text


def test_malformed_json_uses_the_safe_validation_envelope_without_echoing_input(
    client: TestClient,
) -> None:
    sentinel = "track02-malformed-password-sentinel-do-not-emit"

    response = client.post(
        "/api/auth/login",
        content=f'{{"email":"alice@example.com","password":"{sentinel}"',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed."
    assert len(error["details"]) == 1
    assert error["details"][0]["loc"][0] == "body"
    assert isinstance(error["details"][0]["loc"][1], int)
    assert error["details"][0]["type"] == "json_invalid"
    assert error["details"][0]["message"] == "Invalid value"
    assert sentinel not in response.text


def test_duplicate_and_generic_login_failures_preserve_the_error_contract(
    client: TestClient,
) -> None:
    assert _register(client).status_code == 201
    conflict = _register(client, username="alice", email="other@example.com")
    unknown = client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": _PASSWORD}
    )
    wrong = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "z" * 27}
    )

    assert conflict.status_code == 409
    assert conflict.json() == {
        "error": {
            "code": "identity_conflict",
            "message": "Username or email is already registered.",
            "details": None,
        }
    }
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert unknown.headers["www-authenticate"] == wrong.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer not-a-token"])
def test_protected_route_rejects_every_invalid_bearer_shape(
    client: TestClient, authorization: str | None
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get("/__track02/protected", headers=headers)

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "authentication_failed",
            "message": "Authentication failed.",
            "details": None,
        }
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_deleted_subject_is_indistinguishable_from_other_credential_failures(
    client: TestClient,
) -> None:
    registered = _register(client).json()
    app = client.app
    with app.state.session_factory() as session:
        user = session.get(User, registered["user"]["id"])
        assert user is not None
        session.delete(user)
        session.commit()

    response = client.get(
        "/__track02/protected", headers={"Authorization": f"Bearer {registered['token']}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


@pytest.mark.parametrize("subject", ["0", "01", "-1", "١"])
def test_signed_but_noncanonical_subjects_are_rejected_at_the_http_boundary(
    client: TestClient, subject: str
) -> None:
    assert _register(client).status_code == 201
    token = client.app.state.token_codec.issue(subject)

    response = client.get("/__track02/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_unrelated_integrity_failure_is_logged_once_with_database_values_redacted(
    database_url: str, migrated_engine: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    del migrated_engine
    import app.main as main

    stream = io.StringIO()
    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    class FailingService:
        def login(self, **_kwargs: object) -> object:
            raise IntegrityError(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                {
                    "email": "track02-email-sentinel-do-not-emit",
                    "password_hash": "track02-password-hash-sentinel-do-not-emit",
                },
                sqlite3.IntegrityError("track02-driver-password-sentinel-do-not-emit"),
            )

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    app = create_app(
        Settings(app_env="test", database_url=database_url, stats_refresh_enabled=False)
    )
    app.dependency_overrides[get_auth_service] = lambda: FailingService()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": _PASSWORD},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error.",
            "details": None,
        }
    }
    raw = stream.getvalue()
    for secret in (
        "track02-email-sentinel-do-not-emit",
        "track02-password-hash-sentinel-do-not-emit",
        "track02-driver-password-sentinel-do-not-emit",
        _PASSWORD,
    ):
        assert secret not in raw
    records = [json.loads(line) for line in raw.splitlines()]
    unexpected = [
        record for record in records if record["event"] == "http.request.unexpected_exception"
    ]
    assert len(unexpected) == 1
    assert unexpected[0]["exception"]["type"] == "IntegrityError"
    assert unexpected[0]["exception"]["message"] == "[REDACTED]"
    assert unexpected[0]["context"] == {"method": "POST"}


def test_private_protected_route_and_openapi_are_absent_outside_test(tmp_path: Path) -> None:
    for environment, secret in (("development", None), ("production", "P" * 32)):
        values: dict[str, object] = {
            "app_env": environment,
            "database_url": f"sqlite:///{tmp_path / f'{environment}.sqlite3'}",
            "stats_refresh_enabled": False,
        }
        if secret is not None:
            values["jwt_secret"] = secret
        app = create_app(Settings.model_validate(values))
        with TestClient(app) as client:
            assert client.get("/__track02/protected").status_code == 404
            openapi = client.get("/openapi.json").json()

        assert "/__track02/protected" not in openapi["paths"]
        assert openapi["components"]["securitySchemes"]["BearerAuth"] == {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        for path in ("/api/auth/register", "/api/auth/login"):
            assert "security" not in openapi["paths"][path]["post"]


def test_auth_runtime_bodies_validate_against_the_generated_openapi_schema(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    registry = Registry().with_resource(
        "urn:track02:openapi", Resource.from_contents(document, default_specification=DRAFT202012)
    )

    def validate(path: str, status: str, payload: dict[str, object]) -> None:
        schema = document["paths"][path]["post"]["responses"][status]["content"][
            "application/json"
        ]["schema"]
        root_schema = {"$id": "urn:track02:openapi", **document, **schema}
        Draft202012Validator(root_schema, registry=registry).validate(payload)

    register = _register(client)
    login = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": _PASSWORD}
    )
    conflict = _register(client)
    validation = client.post("/api/auth/login", json={"email": "alice@example.com"})
    authentication = client.post(
        "/api/auth/login", json={"email": "missing@example.com", "password": _PASSWORD}
    )

    class FailingService:
        def login(self, **_kwargs: object) -> object:
            raise RuntimeError("track02-service-sentinel-do-not-emit")

    client.app.dependency_overrides[get_auth_service] = lambda: FailingService()
    unexpected = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": _PASSWORD}
    )
    client.app.dependency_overrides.clear()
    for path, response in (
        ("/api/auth/register", register),
        ("/api/auth/login", login),
        ("/api/auth/register", conflict),
        ("/api/auth/login", validation),
        ("/api/auth/login", authentication),
        ("/api/auth/login", unexpected),
    ):
        validate(path, str(response.status_code), response.json())

    assert set(document["paths"]) == {
        "/api/auth/register",
        "/api/auth/login",
        "/api/bookmarks",
        "/api/bookmarks/stats",
        "/api/bookmarks/{bookmark_id}",
        "/health/live",
        "/health/ready",
    }
    serialized = str(document)
    assert "password" not in str(document["components"]["schemas"]["AuthResponse"])
    assert "writeOnly" in serialized
