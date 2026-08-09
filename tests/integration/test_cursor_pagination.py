"""HTTP and SQLite evidence for ADR-007 cursor pagination."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.pagination import CursorBoundary
from app.bookmarks.repository import BookmarkRepository
from app.bookmarks.schemas import BookmarkQuery
from app.core.config import Settings
from app.main import create_app

_PASSWORD = "correct-horse-battery-staple"
_NOW = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)


@pytest.fixture
def client(database_url: str, migrated_engine: Engine) -> Iterator[TestClient]:
    del migrated_engine
    app = create_app(
        Settings(app_env="test", database_url=database_url, stats_refresh_enabled=False)
    )
    with TestClient(app, raise_server_exceptions=False) as started:
        yield started


def _token(client: TestClient, username: str) -> str:
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


def _owner_id(client: TestClient, username: str) -> int:
    with Session(client.app.state.engine) as session:
        user = session.execute(select(User).where(User.username == username)).scalar_one()
        assert user.id is not None
        return user.id


def _seed(client: TestClient, username: str, count: int, *, start: datetime = _NOW) -> list[int]:
    owner_id = _owner_id(client, username)
    with Session(client.app.state.engine) as session:
        bookmarks = [
            Bookmark(
                url=f"https://cursor.example/{username}/{offset}",
                title=f"{username}-{offset}",
                description=None,
                user_id=owner_id,
                created_at=start + timedelta(seconds=offset // 2),
                updated_at=start + timedelta(seconds=offset // 2),
            )
            for offset in range(count)
        ]
        session.add_all(bookmarks)
        session.commit()
        return [bookmark.id for bookmark in bookmarks if bookmark.id is not None]


def _get(client: TestClient, token: str, **params: str | int) -> object:
    return client.get(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
        params={"pagination": "cursor", **params},
    )


def test_cursor_first_ties_terminal_empty_and_one_item_contracts(client: TestClient) -> None:
    token = _token(client, "cursalice")
    _seed(client, "cursalice", 5)

    first = _get(client, token, page_size=2)
    assert first.status_code == 200
    assert first.json()["total"] == 5
    assert first.json()["page"] == 1
    assert len(first.json()["items"]) == 2
    first_cursor = first.headers["x-next-cursor"]

    second = _get(client, token, page_size=2, cursor=first_cursor)
    assert second.status_code == 200
    assert second.json()["page"] == 2
    assert len(second.json()["items"]) == 2
    second_cursor = second.headers["x-next-cursor"]

    terminal = _get(client, token, page_size=2, cursor=second_cursor)
    assert terminal.status_code == 200
    assert terminal.json()["page"] == 3
    assert len(terminal.json()["items"]) == 1
    assert "x-next-cursor" not in terminal.headers
    ids = [item["id"] for result in (first, second, terminal) for item in result.json()["items"]]
    assert len(ids) == len(set(ids)) == 5

    empty_token = _token(client, "cursempty")
    empty = _get(client, empty_token)
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert "x-next-cursor" not in empty.headers

    one_token = _token(client, "cursone")
    _seed(client, "cursone", 1)
    one = _get(client, one_token)
    assert one.status_code == 200
    assert len(one.json()["items"]) == 1
    assert "x-next-cursor" not in one.headers

    exact_token = _token(client, "cursexact")
    _seed(client, "cursexact", 2)
    exact = _get(client, exact_token, page_size=2)
    assert exact.status_code == 200
    assert len(exact.json()["items"]) == 2
    assert "x-next-cursor" not in exact.headers


def test_cursor_replay_owner_filter_page_size_and_mode_binding_are_safe(client: TestClient) -> None:
    alice, bob = _token(client, "cursowner"), _token(client, "cursother")
    _seed(client, "cursowner", 3)
    first = _get(client, alice, page_size=1)
    cursor = first.headers["x-next-cursor"]
    replay = _get(client, alice, page_size=1, cursor=cursor)
    assert replay.status_code == 200
    assert replay.json()["page"] == 2

    for token, params in (
        (bob, {"page_size": 1, "cursor": cursor}),
        (alice, {"page_size": 2, "cursor": cursor}),
        (alice, {"page_size": 1, "tag": "different", "cursor": cursor}),
        (alice, {"page_size": 1, "q": "different", "cursor": cursor}),
        (alice, {"page_size": 1, "from": "2026-08-01", "cursor": cursor}),
        (alice, {"page_size": 1, "to": "2026-08-09", "cursor": cursor}),
        (alice, {"page_size": 1, "updated_from": "2026-08-01", "cursor": cursor}),
        (alice, {"page_size": 1, "updated_to": "2026-08-09", "cursor": cursor}),
    ):
        response = _get(client, token, **params)
        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "invalid_cursor",
                "message": "Cursor is invalid or expired.",
                "details": None,
            }
        }

    page_mode = client.get(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {alice}"},
        params={"cursor": cursor},
    )
    assert page_mode.status_code == 422
    assert page_mode.json()["error"]["code"] == "validation_error"
    assert page_mode.json()["error"]["details"] == [
        {"loc": ["query", "cursor"], "type": "value_error", "message": "Invalid value"}
    ]
    conflict = _get(client, alice, page_size=1, page=2, cursor=cursor)
    assert conflict.status_code == 422
    assert conflict.json()["error"]["code"] == "validation_error"
    oversized = _get(client, alice, cursor="x" * 2049)
    assert oversized.status_code == 422
    assert oversized.json()["error"]["code"] == "invalid_cursor"
    legacy_invalid = client.get(
        "/api/bookmarks", headers={"Authorization": f"Bearer {alice}"}, params={"page": "zero"}
    )
    assert legacy_invalid.status_code == 422
    assert legacy_invalid.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {"loc": ["query", "page"], "type": "value_error", "message": "Invalid value"}
            ],
        }
    }
    lower_bound = client.get(
        "/api/bookmarks", headers={"Authorization": f"Bearer {alice}"}, params={"page": 0}
    )
    assert lower_bound.status_code == 422
    assert lower_bound.json()["error"]["details"] == [
        {"loc": ["query", "page"], "type": "greater_than_equal", "message": "Invalid value"}
    ]
    unexpected = client.get(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {alice}"},
        params={"unexpected": "value"},
    )
    assert unexpected.status_code == 422
    assert unexpected.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {
                    "loc": ["query", "unexpected"],
                    "type": "extra_forbidden",
                    "message": "Invalid value",
                }
            ],
        }
    }


@pytest.mark.parametrize("parameter", ("from", "to", "updated_from", "updated_to"))
def test_legacy_nullable_date_query_literals_are_treated_as_absent(
    client: TestClient, parameter: str
) -> None:
    token = _token(client, f"cursnull{parameter.replace('_', '')}")
    response = client.get(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
        params={parameter: "null"},
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}


@pytest.mark.parametrize("parameter", ("from", "to", "updated_from", "updated_to"))
def test_legacy_malformed_date_query_values_keep_safe_validation_details(
    client: TestClient, parameter: str
) -> None:
    token = _token(client, f"cursmalformed{parameter.replace('_', '')}")
    response = client.get(
        "/api/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
        params={parameter: "not-a-date"},
    )
    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "details": [
                {"loc": ["query", parameter], "type": "value_error", "message": "Invalid value"}
            ],
        }
    }


def test_cursor_keyset_has_no_shift_after_newer_insert_and_deleted_anchor(
    client: TestClient,
) -> None:
    token = _token(client, "cursshift")
    seeded = _seed(client, "cursshift", 4)
    first = _get(client, token, page_size=2)
    first_ids = [item["id"] for item in first.json()["items"]]
    cursor = first.headers["x-next-cursor"]
    assert first_ids == list(reversed(seeded[-2:]))

    owner_id = _owner_id(client, "cursshift")
    with Session(client.app.state.engine) as session:
        session.add(
            Bookmark(
                url="https://cursor.example/cursshift/newer",
                title="newer",
                description=None,
                user_id=owner_id,
                created_at=_NOW + timedelta(days=1),
                updated_at=_NOW + timedelta(days=1),
            )
        )
        session.commit()
    deleted = client.delete(
        f"/api/bookmarks/{first_ids[-1]}", headers={"Authorization": f"Bearer {token}"}
    )
    assert deleted.status_code == 204

    second = _get(client, token, page_size=2, cursor=cursor)
    assert second.status_code == 200
    second_ids = [item["id"] for item in second.json()["items"]]
    assert not set(first_ids) & set(second_ids)
    assert set(second_ids) == set(seeded[:2])
    assert all(item["title"] != "newer" for item in second.json()["items"])


def test_cursor_skips_a_deleted_below_boundary_row_without_replaying_or_failing(
    client: TestClient,
) -> None:
    token = _token(client, "cursbelow")
    seeded = _seed(client, "cursbelow", 5)
    first = _get(client, token, page_size=2)
    cursor = first.headers["x-next-cursor"]
    # This row belongs after the signed boundary, rather than being the boundary itself.
    removed = client.delete(
        f"/api/bookmarks/{seeded[2]}", headers={"Authorization": f"Bearer {token}"}
    )
    assert removed.status_code == 204

    second = _get(client, token, page_size=2, cursor=cursor)
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == [seeded[1], seeded[0]]
    assert second.json()["total"] == 4  # Totals are live per-request snapshot values.


def test_cursor_populated_read_stays_at_four_snapshot_statements_and_uses_keyset_limit(
    client: TestClient,
) -> None:
    token = _token(client, "cursstatements")
    _seed(client, "cursstatements", 3)
    statements: list[str] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    event.listen(client.app.state.engine, "before_cursor_execute", record)
    try:
        response = _get(client, token, page_size=2)
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert len(statements) == 5  # authenticated owner lookup plus collection snapshot work.
    assert "from users" in statements[0]
    assert statements[1] == "begin deferred"
    assert "count" in statements[2]
    assert "limit ? offset ?" in statements[3]
    assert "from bookmark_tags join tags" in statements[4]


def test_cursor_keyset_query_plan_uses_the_existing_owner_created_identifier_index(
    client: TestClient,
) -> None:
    token = _token(client, "cursplan")
    seeded = _seed(client, "cursplan", 3)
    del token
    statements: list[tuple[str, tuple[object, ...] | dict[str, object]]] = []

    def record(
        _connection: Connection,
        _cursor: object,
        statement: str,
        parameters: tuple[object, ...] | dict[str, object],
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append((statement, parameters))

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        with Session(engine) as session:
            items, total, has_more = BookmarkRepository(session).search_owned_after(
                _owner_id(client, "cursplan"),
                BookmarkQuery(page_size=1),
                CursorBoundary(
                    created_at=_NOW + timedelta(seconds=1), bookmark_id=seeded[-1], page=2
                ),
            )
        assert total == 3
        assert len(items) == 1
        assert has_more
    finally:
        event.remove(engine, "before_cursor_execute", record)

    statement, parameters = next(
        item
        for item in statements
        if "from bookmarks" in item[0].lower() and "count(" not in item[0].lower()
    )
    with engine.connect() as connection:
        plan = connection.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters).all()
    details = "\n".join(str(row[3]).upper() for row in plan)
    assert "USING INDEX IX_BOOKMARKS_USER_CREATED_ID" in details
    assert "LIMIT" in statement.upper()
    assert "OFFSET" in statement.upper()


def test_cursor_read_keeps_one_wal_snapshot_across_a_writer_interleaving(
    client: TestClient,
) -> None:
    """Count, page, and tag load observe generation A despite a committed generation B."""
    engine = client.app.state.engine
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode = WAL").scalar_one() == "wal"
        connection.commit()
    token = _token(client, "curswal")
    owner_id = _owner_id(client, "curswal")
    with Session(engine) as setup:
        generation_a = Bookmark(
            url="https://cursor.example/curswal/generation-a",
            title="generation-a",
            description=None,
            user_id=owner_id,
            created_at=_NOW,
            updated_at=_NOW,
        )
        alpha = Tag(name="cursor-wal-alpha")
        setup.add_all((generation_a, alpha))
        setup.flush()
        assert generation_a.id is not None and alpha.id is not None
        setup.add(BookmarkTag(bookmark_id=generation_a.id, tag_id=alpha.id))
        setup.commit()

    writer_turn, writer_done = Event(), Event()
    errors: list[BaseException] = []
    responses: list[object] = []

    def pause_before_page(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if "from bookmarks" in statement.lower() and "count(" not in statement.lower():
            writer_turn.set()
            assert writer_done.wait(timeout=5)

    def read_generation_a() -> None:
        try:
            responses.append(_get(client, token))
        except BaseException as error:  # pragma: no cover - surfaced below.
            errors.append(error)

    event.listen(engine, "before_cursor_execute", pause_before_page)
    try:
        reader = Thread(target=read_generation_a)
        reader.start()
        assert writer_turn.wait(timeout=5)
        with Session(engine) as writer:
            writer.add(
                Bookmark(
                    url="https://cursor.example/curswal/generation-b",
                    title="generation-b",
                    description=None,
                    user_id=owner_id,
                    created_at=_NOW + timedelta(days=1),
                    updated_at=_NOW + timedelta(days=1),
                )
            )
            writer.commit()
        writer_done.set()
        reader.join(timeout=5)
        assert not reader.is_alive()
    finally:
        event.remove(engine, "before_cursor_execute", pause_before_page)

    assert errors == []
    response = responses[0]
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["title"] for item in response.json()["items"]] == ["generation-a"]
    assert response.json()["items"][0]["tags"] == [{"name": "cursor-wal-alpha"}]


def test_cursor_rejections_do_not_retain_token_owner_or_filter_values_in_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    token = _token(client, "curslogs")
    _seed(client, "curslogs", 2)
    first = _get(client, token, page_size=1)
    cursor = first.headers["x-next-cursor"]
    caplog.clear()
    caplog.set_level(logging.INFO)

    rejected = _get(
        client,
        token,
        cursor=cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
        page_size=1,
        q="cursor-filter-sentinel-do-not-log",
    )

    assert rejected.status_code == 422
    rendered = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("app")
    )
    assert cursor not in rendered
    assert "cursor-filter-sentinel-do-not-log" not in rendered
    assert str(_owner_id(client, "curslogs")) not in rendered
