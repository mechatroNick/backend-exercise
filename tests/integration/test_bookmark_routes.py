"""HTTP and bounded OpenAPI contracts for protected bookmark CRUD."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy import Engine, select
from sqlmodel import Session

from app.bookmarks.dependencies import get_bookmark_service
from app.bookmarks.models import Tag
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    """Start the real composition root against a migrated disposable database."""
    del migrated_engine
    app = create_app(
        Settings(app_env="test", database_url=database_url, stats_refresh_enabled=False)
    )
    with TestClient(app) as value:
        yield value


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
    return response.json()["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "url": "https://example.test/bookmark",
        "title": "Bookmark",
        "description": "description",
        "tags": ["Python", " API ", "python"],
    }
    payload.update(changes)
    return payload


def test_protected_crud_normalizes_tags_and_keeps_responses_public(client: TestClient) -> None:
    token = _register(client, "alice")
    headers = _headers(token)

    created = client.post("/api/bookmarks", headers=headers, json=_create_payload())
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "url",
        "title",
        "description",
        "tags",
        "created_at",
        "updated_at",
    }
    assert [tag["name"] for tag in body["tags"]] == ["api", "python"]
    assert body["created_at"] == body["updated_at"]
    assert "user_id" not in body

    listed = client.get("/api/bookmarks", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == {"items": [body], "total": 1, "page": 1, "page_size": 20}

    detail = client.get(f"/api/bookmarks/{body['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json() == body

    no_op = client.patch(
        f"/api/bookmarks/{body['id']}", headers=headers, json={"tags": ["api", "PYTHON"]}
    )
    assert no_op.status_code == 200
    assert no_op.json()["updated_at"] == body["updated_at"]

    changed = client.patch(
        f"/api/bookmarks/{body['id']}",
        headers=headers,
        json={"title": "Changed", "description": None, "tags": ["Rust", "api"]},
    )
    assert changed.status_code == 200
    assert changed.json()["title"] == "Changed"
    assert changed.json()["description"] is None
    assert [tag["name"] for tag in changed.json()["tags"]] == ["api", "rust"]
    assert changed.json()["created_at"] == body["created_at"]
    assert changed.json()["updated_at"] > body["updated_at"]

    deleted = client.delete(f"/api/bookmarks/{body['id']}", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert "content-type" not in deleted.headers


def test_bearer_failures_and_two_user_concealment_are_identical(client: TestClient) -> None:
    unauthenticated = client.get("/api/bookmarks")
    malformed = client.post("/api/bookmarks", headers={"Authorization": "Bearer invalid"}, json={})
    assert unauthenticated.status_code == malformed.status_code == 401
    assert unauthenticated.json() == malformed.json()
    assert unauthenticated.headers["www-authenticate"] == "Bearer"

    alice = _headers(_register(client, "alice"))
    bob = _headers(_register(client, "bob"))
    created = client.post("/api/bookmarks", headers=alice, json=_create_payload())
    bookmark_id = created.json()["id"]
    missing = client.get("/api/bookmarks/9999", headers=bob)
    other_user = client.get(f"/api/bookmarks/{bookmark_id}", headers=bob)
    assert missing.status_code == other_user.status_code == 404
    assert missing.json() == other_user.json()
    other_patch = client.patch(f"/api/bookmarks/{bookmark_id}", headers=bob, json={"title": "Nope"})
    other_delete = client.delete(f"/api/bookmarks/{bookmark_id}", headers=bob)
    assert other_patch.status_code == other_delete.status_code == 404
    assert other_patch.json() == other_delete.json() == missing.json()
    assert client.get("/api/bookmarks", headers=bob).json()["items"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "https://example.test", "title": None, "tags": ["safe"]},
        {"url": "https://example.test", "title": "Title", "tags": ["   "]},
        {"url": "https://example.test", "title": "Title", "tags": ["x" * 51]},
    ],
)
def test_create_validation_is_safe_strict_and_does_not_leak_input(
    client: TestClient, payload: dict[str, object]
) -> None:
    response = client.post(
        "/api/bookmarks", headers=_headers(_register(client, "alice")), json=payload
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_create_rejects_extra_owner_input_without_reflecting_its_value(client: TestClient) -> None:
    sentinel = "track03-untrusted-sentinel-do-not-emit"
    response = client.post(
        "/api/bookmarks",
        headers=_headers(_register(client, "alice")),
        json=_create_payload(owner_id=999, ignored=sentinel),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert sentinel not in response.text


def test_description_omit_set_clear_duplicate_url_reuse_and_orphan_tags(
    client: TestClient,
) -> None:
    headers = _headers(_register(client, "alice"))
    first = client.post(
        "/api/bookmarks",
        headers=headers,
        json=_create_payload(description=None, tags=["Shared"]),
    ).json()
    second = client.post(
        "/api/bookmarks",
        headers=headers,
        json=_create_payload(title="Second", tags=["shared"]),
    ).json()
    assert first["id"] != second["id"]
    assert second["description"] == "description"

    omitted = client.patch(f"/api/bookmarks/{first['id']}", headers=headers, json={})
    assert omitted.status_code == 200
    assert omitted.json()["description"] is None
    set_description = client.patch(
        f"/api/bookmarks/{first['id']}", headers=headers, json={"description": "now set"}
    )
    assert set_description.json()["description"] == "now set"
    assert (
        client.patch(
            f"/api/bookmarks/{first['id']}", headers=headers, json={"description": None}
        ).json()["description"]
        is None
    )
    assert client.delete(f"/api/bookmarks/{first['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/bookmarks/{second['id']}", headers=headers).status_code == 204

    with Session(client.app.state.engine) as session:
        assert (
            session.execute(select(Tag.name).where(Tag.name == "shared")).scalar_one() == "shared"
        )


def test_bookmark_operations_have_bounded_openapi_contracts_and_runtime_schema_bodies(
    client: TestClient,
) -> None:
    document = client.get("/openapi.json").json()
    operations = document["paths"]["/api/bookmarks"]
    assert set(operations) == {"get", "post"}
    for path, method, accepted in (
        ("/api/bookmarks", "post", {"201", "401", "422", "429", "500"}),
        ("/api/bookmarks", "get", {"200", "401", "422", "429", "500"}),
        ("/api/bookmarks/{bookmark_id}", "get", {"200", "401", "404", "422", "429", "500"}),
        ("/api/bookmarks/{bookmark_id}", "patch", {"200", "401", "404", "422", "429", "500"}),
        ("/api/bookmarks/{bookmark_id}", "delete", {"204", "401", "404", "422", "429", "500"}),
    ):
        operation = document["paths"][path][method]
        assert set(operation["responses"]) == accepted
        assert operation["security"] == [{"BearerAuth": []}]
    assert document["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert (
        "content"
        not in document["paths"]["/api/bookmarks/{bookmark_id}"]["delete"]["responses"]["204"]
    )

    registry = Registry().with_resource(
        "urn:track03:openapi", Resource.from_contents(document, default_specification=DRAFT202012)
    )

    def validate(path: str, method: str, response: object) -> None:
        status_code = str(response.status_code)  # type: ignore[union-attr]
        payload = response.json()  # type: ignore[union-attr]
        schema = document["paths"][path][method]["responses"][status_code]["content"][
            "application/json"
        ]["schema"]
        Draft202012Validator(
            {"$id": "urn:track03:openapi", **document, **schema}, registry=registry
        ).validate(payload)

    headers = _headers(_register(client, "alice"))
    created = client.post("/api/bookmarks", headers=headers, json=_create_payload())
    bookmark_id = created.json()["id"]
    listed = client.get("/api/bookmarks", headers=headers)
    detail = client.get(f"/api/bookmarks/{bookmark_id}", headers=headers)
    patched = client.patch(f"/api/bookmarks/{bookmark_id}", headers=headers, json={"title": "New"})
    unauthenticated = client.get("/api/bookmarks")
    missing = client.get("/api/bookmarks/9999", headers=headers)
    invalid = client.get("/api/bookmarks/0", headers=headers)

    for path, method, response in (
        ("/api/bookmarks", "post", created),
        ("/api/bookmarks", "get", listed),
        ("/api/bookmarks/{bookmark_id}", "get", detail),
        ("/api/bookmarks/{bookmark_id}", "patch", patched),
        ("/api/bookmarks", "get", unauthenticated),
        ("/api/bookmarks/{bookmark_id}", "get", missing),
        ("/api/bookmarks/{bookmark_id}", "get", invalid),
    ):
        validate(path, method, response)

    class FailingService:
        def list(self, _user_id: int) -> object:
            raise RuntimeError("track03-service-sentinel-do-not-emit")

    client.app.dependency_overrides[get_bookmark_service] = lambda: FailingService()
    try:
        unexpected = client.get("/api/bookmarks", headers=headers)
    finally:
        client.app.dependency_overrides.clear()
    assert unexpected.status_code == 500
    validate("/api/bookmarks", "get", unexpected)


@pytest.mark.parametrize("bookmark_id", ["0", "not-an-integer"])
def test_detail_path_identifier_must_be_positive_and_safe(
    client: TestClient, bookmark_id: str
) -> None:
    response = client.get(
        f"/api/bookmarks/{bookmark_id}", headers=_headers(_register(client, "alice"))
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
