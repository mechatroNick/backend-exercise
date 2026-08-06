"""API-wide OpenAPI metadata regression checks without exercising runtime behavior."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.mandatory


def test_public_openapi_has_complete_fictional_metadata_without_contract_drift() -> None:
    document = create_app(
        Settings(app_env="test", database_url="sqlite:////private/tmp/openapi-metadata.sqlite3")
    ).openapi()
    operations = [
        (path, method, operation)
        for path, item in document["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "patch", "delete"}
    ]
    assert len(operations) == 8
    assert len({operation["operationId"] for _, _, operation in operations}) == 8
    for _, method, operation in operations:
        assert operation["tags"] and operation["summary"] and operation.get("description")
        for parameter in operation.get("parameters", []):
            assert parameter["schema"].get("examples")
        if method != "delete":
            success = (
                "201" if operation["summary"] in {"Create a bookmark", "Register a user"} else "200"
            )
            assert "application/json" in operation["responses"][success]["content"]
        for status, response in operation["responses"].items():
            if status.startswith(("4", "5")):
                assert response["content"]["application/json"]["examples"]
    assert document["paths"]["/api/auth/register"]["post"].get("security") in (None, [])
    assert document["paths"]["/api/auth/login"]["post"].get("security") in (None, [])
    for path in ("/api/bookmarks", "/api/bookmarks/stats", "/api/bookmarks/{bookmark_id}"):
        for operation in document["paths"][path].values():
            assert operation["security"] == [{"BearerAuth": []}]
    schemas = document["components"]["schemas"]
    for name in (
        "RegisterRequest",
        "LoginRequest",
        "AuthResponse",
        "BookmarkCreate",
        "BookmarkPatch",
        "BookmarkPublic",
        "BookmarkList",
        "BookmarkStats",
    ):
        assert schemas[name].get("examples")
    for path in ("/api/auth/register", "/api/auth/login", "/api/bookmarks"):
        for operation in document["paths"][path].values():
            if "requestBody" in operation:
                schema_ref = operation["requestBody"]["content"]["application/json"]["schema"][
                    "$ref"
                ]
                assert schemas[schema_ref.rsplit("/", 1)[-1]]["examples"]
    assert schemas["RegisterRequest"]["properties"]["password"]["writeOnly"] is True
    delete = document["paths"]["/api/bookmarks/{bookmark_id}"]["delete"]["responses"]["204"]
    assert delete["description"] == "Bookmark deleted successfully; the response has no body."
    assert "content" not in delete
    stats_headers = document["paths"]["/api/bookmarks/stats"]["get"]["responses"]["200"]["headers"]
    assert set(stats_headers) == {"X-Stats-Source", "X-Stats-Generated-At"}
    serialized = str(document)
    assert "user_id" not in serialized and "Fictional-Password-Only-123" in serialized
