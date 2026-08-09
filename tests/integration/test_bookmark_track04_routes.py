"""Track 04 HTTP filtering, current-statistics, and bounded OpenAPI evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from sqlalchemy import Engine, event
from sqlalchemy.engine import Connection

from app.bookmarks.dependencies import get_bookmark_stats_service
from app.bookmarks.stats.schemas import BookmarkStats
from app.bookmarks.stats.service import CurrentStatsResult, StatsSource
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    del migrated_engine
    app = create_app(
        Settings(
            app_env="test",
            database_url=database_url,
            top_tags_limit=1,
            stats_refresh_enabled=False,
        )
    )
    with TestClient(app, raise_server_exceptions=False) as started:
        yield started


def _token(client: TestClient, name: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": name, "email": f"{name}@example.com", "password": _PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["token"]


def _create(client: TestClient, token: str, title: str, tags: list[str]) -> dict[str, object]:
    response = client.post(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "url": f"https://example.com/{title.lower().replace(' ', '-')}",
            "title": title,
            "description": f"description {title}",
            "tags": tags,
        },
    )
    assert response.status_code == 201
    return response.json()


def _validate(document: dict[str, object], path: str, status: str, body: object) -> None:
    operation = document["paths"][path]["get"]  # type: ignore[index]
    schema = operation["responses"][status]["content"]["application/json"]["schema"]  # type: ignore[index]
    registry = Registry().with_resource(
        "urn:track04:openapi", Resource.from_contents(document, default_specification=DRAFT202012)
    )
    Draft202012Validator(
        {"$id": "urn:track04:openapi", **document, **schema}, registry=registry
    ).validate(body)  # type: ignore[arg-type]


def test_list_filters_pages_and_stats_are_owner_scoped(client: TestClient) -> None:
    alice, bob = _token(client, "alice"), _token(client, "bob")
    first = _create(client, alice, "Alpha Python", ["python", "api"])
    _create(client, alice, "Beta Rust", ["python", "rust"])
    _create(client, bob, "Private", ["private"])
    headers = {"Authorization": f"Bearer {alice}"}

    filtered = client.get(
        "/api/bookmarks", headers=headers, params={"tag": " PYTHON ", "q": "Alpha"}
    )
    assert filtered.status_code == 200
    assert filtered.json() == {"items": [first], "total": 1, "page": 1, "page_size": 20}
    paged = client.get("/api/bookmarks", headers=headers, params={"page": 2, "page_size": 1})
    assert paged.status_code == 200
    assert paged.json() == {"items": [first], "total": 2, "page": 2, "page_size": 1}
    date_filtered = client.get("/api/bookmarks", headers=headers, params={"from": "2999-01-01"})
    assert date_filtered.status_code == 200
    assert date_filtered.json()["items"] == []

    stats = client.get("/api/bookmarks/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["total_bookmarks"] == 2
    assert stats.json()["total_tags"] == 3
    assert stats.json()["top_tags"] == [{"name": "python", "count": 2}]
    assert len(stats.json()["bookmarks_per_month"]) == 1
    assert (
        client.get("/api/bookmarks/stats", headers={"Authorization": f"Bearer {bob}"}).json()[
            "total_bookmarks"
        ]
        == 1
    )
    assert stats.headers["x-stats-source"] == "live"
    assert "x-stats-generated-at" not in stats.headers
    assert not {"cache-control", "etag", "x-stats-snapshot"} & set(stats.headers)


class _SnapshotStatsService:
    def read(self, user_id: int) -> CurrentStatsResult:
        assert user_id > 0
        return CurrentStatsResult(
            stats=BookmarkStats(
                total_bookmarks=0,
                total_tags=0,
                top_tags=(),
                bookmarks_per_month=(),
            ),
            source=StatsSource.SNAPSHOT,
            generated_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
        )


def test_stats_snapshot_headers_are_transport_only_and_fixed_width(
    client: TestClient,
) -> None:
    token = _token(client, "snapshot-user")
    client.app.dependency_overrides[get_bookmark_stats_service] = _SnapshotStatsService
    try:
        response = client.get(
            "/api/bookmarks/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "total_bookmarks": 0,
        "total_tags": 0,
        "top_tags": [],
        "bookmarks_per_month": [],
    }
    assert response.headers["x-stats-source"] == "snapshot"
    assert response.headers["x-stats-generated-at"] == "2026-08-06T12:00:00.000000Z"


def test_list_and_stats_auth_query_and_openapi_contracts(client: TestClient) -> None:
    token = _token(client, "alice")
    document = client.get("/openapi.json").json()
    headers = {"Authorization": f"Bearer {token}"}
    unauthenticated = client.get("/api/bookmarks")
    invalid = client.get("/api/bookmarks", headers=headers, params={"page": "zero"})
    stats = client.get("/api/bookmarks/stats", headers=headers)
    assert unauthenticated.status_code == 401
    assert invalid.status_code == 422
    assert client.get("/api/bookmarks/stats").status_code == 401
    assert stats.status_code == 200 and stats.json() == {
        "total_bookmarks": 0,
        "total_tags": 0,
        "top_tags": [],
        "bookmarks_per_month": [],
    }
    assert client.get("/api/bookmarks/stats", headers=headers).status_code == 200

    list_operation = document["paths"]["/api/bookmarks"]["get"]
    stats_operation = document["paths"]["/api/bookmarks/stats"]["get"]
    assert {item["name"] for item in list_operation["parameters"]} == {
        "tag",
        "q",
        "from",
        "to",
        "updated_from",
        "updated_to",
        "page",
        "page_size",
        "pagination",
        "cursor",
    }
    assert {"created_from", "created_to"}.isdisjoint(
        {item["name"] for item in list_operation["parameters"]}
    )
    assert set(list_operation["responses"]) == {"200", "401", "422", "429", "500"}
    assert set(stats_operation["responses"]) == {"200", "401", "429", "500"}
    stats_headers = stats_operation["responses"]["200"]["headers"]
    assert set(stats_headers) == {"X-Stats-Source", "X-Stats-Generated-At"}
    assert stats_headers["X-Stats-Source"]["required"] is True
    assert stats_headers["X-Stats-Source"]["schema"]["enum"] == ["snapshot", "live"]
    assert stats_headers["X-Stats-Generated-At"]["required"] is False
    assert list_operation["security"] == stats_operation["security"] == [{"BearerAuth": []}]
    assert "parameters" not in stats_operation and "requestBody" not in stats_operation
    parameters = {item["name"]: item["schema"] for item in list_operation["parameters"]}
    assert parameters["page"] == {
        "type": "integer",
        "minimum": 1,
        "default": 1,
        "examples": [1],
        "title": "Page",
    }
    assert parameters["page_size"] == {
        "type": "integer",
        "maximum": 100,
        "minimum": 1,
        "default": 20,
        "examples": [20],
        "title": "Page Size",
    }
    assert parameters["pagination"]["default"] == "page"
    assert parameters["pagination"]["enum"] == ["page", "cursor"]
    assert parameters["cursor"]["maxLength"] == 2048
    assert "forbids cursor" in parameters["pagination"]["description"]
    assert "forbids an explicitly supplied page" in parameters["pagination"]["description"]
    assert "only when pagination=cursor" in parameters["cursor"]["description"]
    assert list_operation["responses"]["200"]["headers"]["X-Next-Cursor"]["required"] is False
    _validate(
        document, "/api/bookmarks", "200", client.get("/api/bookmarks", headers=headers).json()
    )
    _validate(document, "/api/bookmarks", "401", unauthenticated.json())
    _validate(document, "/api/bookmarks", "422", invalid.json())
    _validate(document, "/api/bookmarks/stats", "200", stats.json())


def _driver_connection(connection: Connection) -> sqlite3.Connection:
    """Resolve the SQLite DB-API connection across SQLAlchemy pool wrappers."""
    driver_connection = connection.connection.driver_connection
    assert isinstance(driver_connection, sqlite3.Connection)
    return driver_connection


@pytest.mark.parametrize(
    ("path", "expected_feature"),
    [
        (
            "/api/bookmarks",
            (
                lambda statements: (
                    "count(" in statements[2]
                    and "from bookmarks" in statements[3]
                    and "from bookmark_tags join tags" in statements[4]
                )
            ),
        ),
        (
            "/api/bookmarks/stats",
            (
                lambda statements: (
                    "count(distinct" in statements[2]
                    and "group by" in statements[3]
                    and "substr(" in statements[4]
                )
            ),
        ),
    ],
)
def test_authenticated_reads_use_one_connection_for_auth_snapshot_and_features(
    client: TestClient,
    path: str,
    expected_feature: object,
) -> None:
    token = _token(client, "alice")
    _create(client, token, "Seed", ["python", "api"])
    engine = client.app.state.engine
    recorded: list[tuple[str, int, sqlite3.Connection]] = []

    def record(
        connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        driver_connection = _driver_connection(connection)
        recorded.append((statement.lower(), id(driver_connection), driver_connection))

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(path, headers={"Authorization": f"Bearer {token}"})
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert response.status_code == 200
    statements = [statement for statement, _identity, _driver in recorded]
    assert len(statements) == 5
    assert "from users" in statements[0]
    assert statements[1] == "begin deferred"
    assert len({identity for _statement, identity, _driver in recorded}) == 1
    assert callable(expected_feature)
    assert expected_feature(statements)
    assert all(
        driver_connection.in_transaction is False for _statement, _id, driver_connection in recorded
    )
