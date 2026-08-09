"""OpenAPI-only checks for Track 08's additive 429 responses."""

from __future__ import annotations

from app.core.config import Settings
from app.main import create_app

_LIMITED_OPERATIONS = (
    ("/api/auth/register", "post"),
    ("/api/auth/login", "post"),
    ("/api/bookmarks", "post"),
    ("/api/bookmarks", "get"),
    ("/api/bookmarks/stats", "get"),
    ("/api/bookmarks/{bookmark_id}", "get"),
    ("/api/bookmarks/{bookmark_id}", "patch"),
    ("/api/bookmarks/{bookmark_id}", "delete"),
)

_FULL_INVENTORY = {
    ("/health/live", "GET"): {200},
    ("/health/ready", "GET"): {200, 503},
    ("/api/auth/register", "POST"): {201, 409, 422, 429, 500},
    ("/api/auth/login", "POST"): {200, 401, 422, 429, 500},
    ("/api/bookmarks", "POST"): {201, 401, 422, 429, 500},
    ("/api/bookmarks", "GET"): {200, 401, 422, 429, 500},
    ("/api/bookmarks/stats", "GET"): {200, 401, 429, 500},
    ("/api/bookmarks/{bookmark_id}", "GET"): {200, 401, 404, 422, 429, 500},
    ("/api/bookmarks/{bookmark_id}", "PATCH"): {200, 401, 404, 422, 429, 500},
    ("/api/bookmarks/{bookmark_id}", "DELETE"): {204, 401, 404, 422, 429, 500},
}


def test_bonus_full_openapi_inventory_is_exactly_ten_operations_and_45_status_pairs() -> None:
    document = create_app(
        Settings(
            app_env="test", database_url="sqlite:////private/tmp/rate-openapi-inventory.sqlite3"
        )
    ).openapi()
    observed = {
        (path, method.upper()): {int(status) for status in operation["responses"]}
        for path, methods in document["paths"].items()
        for method, operation in methods.items()
    }

    assert observed == _FULL_INVENTORY
    assert sum(len(statuses) for statuses in observed.values()) == 45


def test_all_eight_selected_operations_document_the_same_safe_429_contract() -> None:
    document = create_app(
        Settings(app_env="test", database_url="sqlite:////private/tmp/rate-openapi.sqlite3")
    ).openapi()

    for path, method in _LIMITED_OPERATIONS:
        response = document["paths"][path][method]["responses"]["429"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }
        example = next(iter(response["content"]["application/json"]["examples"].values()))
        assert example["value"] == {
            "error": {"code": "rate_limited", "message": "Too many requests."}
        }
        assert response["headers"] == {
            "Retry-After": {
                "description": "Positive whole seconds until one request token is available.",
                "required": True,
                "schema": {"type": "integer", "minimum": 1},
            },
            "Cache-Control": {
                "description": "Prevents storage of a rate-limit response.",
                "required": True,
                "schema": {"type": "string", "example": "no-store"},
            },
        }


def test_cursor_extension_keeps_the_frozen_inventory_while_documenting_its_safe_contract() -> None:
    document = create_app(
        Settings(app_env="test", database_url="sqlite:////private/tmp/cursor-openapi.sqlite3")
    ).openapi()
    operation = document["paths"]["/api/bookmarks"]["get"]
    parameters = {item["name"]: item["schema"] for item in operation["parameters"]}

    assert parameters["pagination"]["enum"] == ["page", "cursor"]
    assert parameters["pagination"]["default"] == "page"
    assert parameters["cursor"]["maxLength"] == 2048
    assert operation["responses"]["200"]["headers"]["X-Next-Cursor"] == {
        "description": (
            "Opaque continuation cursor for pagination=cursor; absent when no further page exists."
        ),
        "required": False,
        "schema": {"type": "string", "maxLength": 2048},
    }
    assert "forbids cursor" in parameters["pagination"]["description"]
    assert "forbids an explicitly supplied page" in parameters["pagination"]["description"]
    assert "only when pagination=cursor" in parameters["cursor"]["description"]
    examples = operation["responses"]["422"]["content"]["application/json"]["examples"]
    assert examples["invalid_cursor"]["value"] == {
        "error": {"code": "invalid_cursor", "message": "Cursor is invalid or expired."}
    }
