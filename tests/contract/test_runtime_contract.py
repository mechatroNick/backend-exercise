"""Controlled runtime/OpenAPI contract matrix for all public operations."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import schemathesis
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy import Engine

from app.auth.dependencies import get_auth_service
from app.bookmarks.dependencies import get_bookmark_service, get_bookmark_stats_service
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "contract-safe-password"
_INVENTORY = {
    ("/api/auth/register", "POST"): {201, 409, 422, 500},
    ("/api/auth/login", "POST"): {200, 401, 422, 500},
    ("/api/bookmarks", "POST"): {201, 401, 422, 500},
    ("/api/bookmarks", "GET"): {200, 401, 422, 500},
    ("/api/bookmarks/stats", "GET"): {200, 401, 500},
    ("/api/bookmarks/{bookmark_id}", "GET"): {200, 401, 404, 422, 500},
    ("/api/bookmarks/{bookmark_id}", "PATCH"): {200, 401, 404, 422, 500},
    ("/api/bookmarks/{bookmark_id}", "DELETE"): {204, 401, 404, 422, 500},
}


@pytest.fixture
def contract_client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    del migrated_engine
    app = create_app(
        Settings(app_env="test", database_url=database_url, stats_refresh_enabled=False)
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _register(client: TestClient, name: str = "alice") -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bookmark(client: TestClient, token: str) -> int:
    response = client.post(
        "/api/bookmarks",
        headers=_headers(token),
        json={"url": "https://example.test/contract", "title": "Contract", "tags": ["api"]},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _validate(document: dict[str, Any], app: Any, path: str, method: str, response: Any) -> None:
    status = str(response.status_code)
    operation = document["paths"][path][method.lower()]
    schemathesis.openapi.from_asgi("/openapi.json", app)[path][method.lower()].validate_response(
        response
    )
    if status == "204":
        assert response.content == b"" and "content-type" not in response.headers
        assert "content" not in operation["responses"][status]
        return
    assert response.headers["content-type"].startswith("application/json")
    schema = operation["responses"][status]["content"]["application/json"]["schema"]
    registry = Registry().with_resource(
        "urn:track05:openapi", Resource.from_contents(document, default_specification=DRAFT202012)
    )
    Draft202012Validator(
        {"$id": "urn:track05:openapi", **document, **schema}, registry=registry
    ).validate(response.json())


@pytest.mark.mandatory
def test_documented_inventory_is_exactly_eight_operations_and_34_status_pairs(
    contract_client: TestClient,
) -> None:
    document = contract_client.get("/openapi.json").json()
    observed = {
        (path, method.upper()): {int(status) for status in operation["responses"]}
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    }
    assert observed == _INVENTORY
    assert sum(len(statuses) for statuses in observed.values()) == 34


@pytest.mark.mandatory
@pytest.mark.parametrize(
    ("path", "method", "status"),
    [
        (path, method, status)
        for (path, method), statuses in _INVENTORY.items()
        for status in statuses
    ],
)
def test_documented_status_pair_has_a_controlled_runtime_response(
    contract_client: TestClient, path: str, method: str, status: int
) -> None:
    token = _register(contract_client)
    bookmark_id = _bookmark(contract_client, token)
    headers = _headers(token)
    document = contract_client.get("/openapi.json").json()
    request_path = path.replace("{bookmark_id}", str(bookmark_id if status != 404 else 999_999))
    if status == 401:
        headers = {}
    elif status == 422:
        request_path = path.replace("{bookmark_id}", "0")
    if status == 500:
        dependency = (
            get_auth_service
            if path.startswith("/api/auth/")
            else get_bookmark_stats_service
            if path.endswith("/stats")
            else get_bookmark_service
        )
        contract_client.app.dependency_overrides[dependency] = lambda: (_ for _ in ()).throw(
            RuntimeError()
        )
    try:
        if path == "/api/auth/register":
            payload = {
                "username": "alice" if status == 409 else "new",
                "email": "alice@example.com" if status == 409 else "new@example.com",
                "password": _PASSWORD,
            }
            if status == 422:
                payload = {"username": "", "email": "bad", "password": "x"}
            response = contract_client.post(path, json=payload)
        elif path == "/api/auth/login":
            payload = {
                "email": "alice@example.com",
                "password": _PASSWORD if status != 401 else "incorrect-password",
            }
            if status == 422:
                payload = {"email": "alice@example.com"}
            response = contract_client.post(path, json=payload)
        elif method == "POST":
            payload = {"url": "https://example.test/new", "title": "New", "tags": ["api"]}
            if status == 422:
                payload = {"url": "bad"}
            response = contract_client.post(path, headers=headers, json=payload)
        elif method == "PATCH":
            response = contract_client.patch(
                request_path, headers=headers, json={"title": "Changed"}
            )
        elif method == "DELETE":
            response = contract_client.delete(request_path, headers=headers)
        else:
            response = contract_client.get(
                request_path, headers=headers, params={"page": 0} if status == 422 else None
            )
    finally:
        contract_client.app.dependency_overrides.clear()
    assert response.status_code == status
    _validate(document, contract_client.app, path, method, response)
