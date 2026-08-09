"""Migrated-SQLite proof for the private weekly raw-SQL reader."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, event, text
from sqlmodel import Session

from app.bookmarks.stats.weekly import (
    WINDOW_MONTHS_SQL,
    WINDOW_TOP_TAGS_SQL,
    WINDOW_TOTALS_SQL,
    WeeklyStatsReader,
    weekly_window,
)


def _seed(connection: Any) -> None:
    connection.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, 'hash', :created_at)"
        ),
        {
            "id": 1,
            "username": "owner",
            "email": "owner@example.test",
            "created_at": "2026-08-01T00:00:00.000000Z",
        },
    )
    connection.execute(
        text(
            "INSERT INTO users (id, username, email, password_hash, created_at) "
            "VALUES (:id, :username, :email, 'hash', :created_at)"
        ),
        {
            "id": 2,
            "username": "other",
            "email": "other@example.test",
            "created_at": "2026-08-01T00:00:00.000000Z",
        },
    )
    for bookmark_id, user_id, created_at in (
        (1, 1, "2026-08-02T23:59:59.999999Z"),
        (2, 1, "2026-08-03T00:00:00.000000Z"),
        (3, 1, "2026-08-09T23:59:59.999999Z"),
        (4, 1, "2026-08-10T00:00:00.000000Z"),
        (5, 2, "2026-08-04T00:00:00.000000Z"),
    ):
        connection.execute(
            text(
                "INSERT INTO bookmarks (id, url, title, description, user_id, created_at, "
                "updated_at) "
                "VALUES (:id, :url, :title, NULL, :user_id, :created_at, :created_at)"
            ),
            {
                "id": bookmark_id,
                "url": f"https://example.test/{bookmark_id}",
                "title": f"b-{bookmark_id}",
                "user_id": user_id,
                "created_at": created_at,
            },
        )
    for tag_id, name in ((1, "alpha"), (2, "beta"), (3, "漢字'; DROP TABLE bookmarks;--")):
        connection.execute(
            text("INSERT INTO tags (id, name) VALUES (:id, :name)"), {"id": tag_id, "name": name}
        )
    for bookmark_id, tag_id in ((2, 1), (2, 2), (3, 1), (3, 2), (3, 3), (5, 1)):
        connection.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": bookmark_id, "tag_id": tag_id},
        )


def test_weekly_reader_uses_exact_bounds_ordering_owner_scope_and_bound_parameters(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as connection:
        _seed(connection)
    statements: list[str] = []
    parameters: list[tuple[object, ...]] = []

    def record(
        _connection: object,
        _cursor: object,
        statement: str,
        params: object,
        _context: object,
        _many: bool,
    ) -> None:
        if "bookmarks AS b" in statement:
            statements.append(statement.strip())
            assert isinstance(params, tuple)
            parameters.append(params)

    event.listen(migrated_engine, "before_cursor_execute", record)
    try:
        with Session(migrated_engine) as session:
            stats = WeeklyStatsReader(session, 3).read(
                1, weekly_window(datetime(2026, 8, 9, tzinfo=UTC))
            )
    finally:
        event.remove(migrated_engine, "before_cursor_execute", record)

    assert stats.model_dump(mode="json") == {
        "total_bookmarks": 2,
        "total_tags": 3,
        "top_tags": [
            {"name": "alpha", "count": 2},
            {"name": "beta", "count": 2},
            {"name": "漢字'; drop table bookmarks;--", "count": 1},
        ],
        "bookmarks_per_month": [{"month": "2026-08", "count": 2}],
    }
    compiled = [
        str(statement.compile(dialect=migrated_engine.dialect)).strip()
        for statement in (WINDOW_TOTALS_SQL, WINDOW_TOP_TAGS_SQL, WINDOW_MONTHS_SQL)
    ]
    assert statements == compiled
    assert parameters == [
        (1, "2026-08-03T00:00:00.000000Z", "2026-08-10T00:00:00.000000Z"),
        (1, "2026-08-03T00:00:00.000000Z", "2026-08-10T00:00:00.000000Z", 3),
        (1, "2026-08-03T00:00:00.000000Z", "2026-08-10T00:00:00.000000Z"),
    ]
    with migrated_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM bookmarks")).scalar_one() == 5
