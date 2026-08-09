"""Contract tests for the centralized Track 02 HTTP error boundary."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import _safe_location, error_response, request_validation_issues
from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ValidationApplicationError,
    ValidationIssue,
)
from app.main import create_app


def _response(error: dict[str, object]) -> dict[str, object]:
    return {"error": error}


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    stream = io.StringIO()
    import app.main as main

    original_configure_logging = main.configure_logging

    def configure_to_stream(value: Settings, *, component: str) -> Any:
        return original_configure_logging(value, stream=stream, component=component)

    monkeypatch.setattr(main, "configure_logging", configure_to_stream)
    application = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'unmigrated.sqlite3'}",
            stats_refresh_enabled=False,
        )
    )
    application.state.test_log_stream = stream

    @application.get("/__test__/expected")
    def expected(kind: str) -> None:
        errors = {
            "auth": AuthenticationError,
            "conflict": ConflictError,
            "not-found": NotFoundError,
        }
        if kind == "validation":
            raise ValidationApplicationError(
                details=(
                    ValidationIssue(loc=("query", "count"), type="int_parsing", message="ignored"),
                )
            )
        raise errors[kind]()

    @application.get("/__test__/typed")
    def typed(count: int) -> dict[str, int]:
        return {"count": count}

    return application


@pytest.mark.parametrize(
    ("kind", "status_code", "code", "message", "headers"),
    [
        (
            "auth",
            401,
            "authentication_failed",
            "Authentication failed.",
            {"www-authenticate": "Bearer"},
        ),
        ("conflict", 409, "conflict", "Resource conflict.", {}),
        ("not-found", 404, "not_found", "Resource not found.", {}),
    ],
)
def test_expected_errors_use_stable_envelopes(
    app: FastAPI,
    kind: str,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str],
) -> None:
    with TestClient(app) as client:
        response = client.get("/__test__/expected", params={"kind": kind})

    assert response.status_code == status_code
    assert response.json() == _response({"code": code, "message": message, "details": None})
    for name, value in headers.items():
        assert response.headers[name] == value


def test_rate_limit_error_has_exact_safe_headers_without_a_bearer_challenge() -> None:
    response = error_response(RateLimitError(0))

    assert response.status_code == 429
    assert json.loads(response.body) == _response(
        {"code": "rate_limited", "message": "Too many requests.", "details": None}
    )
    assert dict(response.headers) == {
        "retry-after": "1",
        "cache-control": "no-store",
        "content-length": str(len(response.body)),
        "content-type": "application/json",
    }


def test_application_validation_error_only_exposes_safe_structured_details(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/__test__/expected", params={"kind": "validation"})

    assert response.status_code == 422
    assert response.json() == _response(
        {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {"loc": ["query", "count"], "type": "int_parsing", "message": "Invalid value"}
            ],
        }
    )


def test_framework_validation_does_not_echo_submitted_input_or_context(app: FastAPI) -> None:
    submitted_sentinel = "track02-submitted-token-sentinel-do-not-emit"
    with TestClient(app) as client:
        response = client.get("/__test__/typed", params={"count": submitted_sentinel})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"] == [
        {"loc": ["query", "count"], "type": "int_parsing", "message": "Invalid value"}
    ]
    assert submitted_sentinel not in response.text


def test_unknown_route_uses_not_found_envelope_without_an_unexpected_log(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/__test__/missing")

    assert response.status_code == 404
    assert response.json() == _response(
        {"code": "not_found", "message": "Resource not found.", "details": None}
    )
    records = [
        json.loads(line)
        for line in app.state.test_log_stream.getvalue().splitlines()
        if line.strip()
    ]
    assert not [
        record for record in records if record["event"] == "http.request.unexpected_exception"
    ]


def test_non_not_found_framework_errors_still_use_the_envelope(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.post("/__test__/typed")

    assert response.status_code == 405
    assert response.json() == _response(
        {"code": "http_error", "message": "Request failed.", "details": None}
    )


def test_validation_issue_sanitizer_bounds_paths_types_and_count() -> None:
    errors = [
        {
            "loc": tuple(["query"] + ["location" * 20] * 12),
            "type": "unsafe type with spaces",
            "input": "track02-submitted-token-sentinel-do-not-emit",
            "ctx": {"unsafe": "track02-secret-sentinel-do-not-emit"},
        }
        for _ in range(25)
    ]
    request_error = type("RequestError", (), {"errors": lambda self: errors})()

    issues = request_validation_issues(request_error)  # type: ignore[arg-type]

    assert len(issues) == 20
    assert issues[0].type == "invalid"
    assert issues[0].message == "Invalid value"
    assert len(issues[0].loc) == 10
    assert all(isinstance(part, str) and len(part) <= 64 for part in issues[0].loc)


def test_validation_location_sanitizer_covers_non_collection_and_each_part_kind() -> None:
    assert _safe_location("not-a-path") == ()
    assert _safe_location([True, 4, "field", object()]) == ("invalid", 4, "field", "invalid")
