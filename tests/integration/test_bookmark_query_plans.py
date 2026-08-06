"""Track 04 query-plan and raw-SQL-boundary evidence on migrated SQLite data."""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import Engine, event, insert
from sqlalchemy.engine import Connection
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository
from app.bookmarks.schemas import BookmarkQuery
from app.bookmarks.stats import raw_sql
from app.bookmarks.stats.raw_sql import BookmarkStatsReader

_OWNER_ID = 1
_OTHER_USER_ID = 2
_FIXTURE_COUNT = 250
_FIXTURE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class _ExecutedStatement:
    statement: str
    parameters: tuple[object, ...] | dict[str, object]


def _seed_plan_fixture(engine: Engine) -> None:
    owner_bookmarks: list[dict[str, object]] = []
    other_bookmarks: list[dict[str, object]] = []
    links: list[dict[str, int]] = []
    for offset in range(_FIXTURE_COUNT):
        month = (offset % 3) + 1
        timestamp = _FIXTURE_TIME.replace(month=month, day=(offset % 28) + 1)
        owner_id = 10_000 + offset
        other_id = 20_000 + offset
        owner_bookmarks.append(
            {
                "id": owner_id,
                "url": f"https://fixture.example/{owner_id}",
                "title": f"target bookmark {offset}",
                "description": None,
                "user_id": _OWNER_ID,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        other_bookmarks.append(
            {
                "id": other_id,
                "url": f"https://fixture.example/{other_id}",
                "title": f"other bookmark {offset}",
                "description": None,
                "user_id": _OTHER_USER_ID,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
        if offset % 2 == 0:
            links.append({"bookmark_id": owner_id, "tag_id": 101})
            links.append({"bookmark_id": other_id, "tag_id": 101})
        if offset % 3 == 0:
            links.append({"bookmark_id": owner_id, "tag_id": 102})
            links.append({"bookmark_id": other_id, "tag_id": 102})

    with engine.begin() as connection:
        connection.execute(
            insert(User.__table__),  # type: ignore[arg-type]
            [
                {
                    "id": _OWNER_ID,
                    "username": "query-plan-owner",
                    "email": "query-plan-owner@example.test",
                    "password_hash": "test-only-noncredential-marker",
                    "created_at": _FIXTURE_TIME,
                },
                {
                    "id": _OTHER_USER_ID,
                    "username": "query-plan-other",
                    "email": "query-plan-other@example.test",
                    "password_hash": "test-only-noncredential-marker",
                    "created_at": _FIXTURE_TIME,
                },
            ],
        )
        connection.execute(insert(Bookmark.__table__), owner_bookmarks)  # type: ignore[arg-type]
        connection.execute(insert(Bookmark.__table__), other_bookmarks)  # type: ignore[arg-type]
        connection.execute(
            insert(Tag.__table__),  # type: ignore[arg-type]
            [{"id": 101, "name": "focus"}, {"id": 102, "name": "overlap"}],
        )
        connection.execute(insert(BookmarkTag.__table__), links)  # type: ignore[arg-type]


def _capture_search_statements(
    engine: Engine, query: BookmarkQuery
) -> tuple[_ExecutedStatement, ...]:
    captured: list[_ExecutedStatement] = []

    def record(
        _connection: Connection,
        _cursor: object,
        statement: str,
        parameters: tuple[object, ...] | dict[str, object],
        _context: object,
        _executemany: bool,
    ) -> None:
        captured.append(_ExecutedStatement(statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        with Session(engine) as session:
            items, total = BookmarkRepository(session).search_owned(_OWNER_ID, query)
        assert total > 0
        assert items
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return tuple(captured)


def _capture_stats_statements(engine: Engine) -> tuple[_ExecutedStatement, ...]:
    captured: list[_ExecutedStatement] = []

    def record(
        _connection: Connection,
        _cursor: object,
        statement: str,
        parameters: tuple[object, ...] | dict[str, object],
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement != "BEGIN DEFERRED":
            captured.append(_ExecutedStatement(statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        with Session(engine) as session:
            assert BookmarkStatsReader(session, 5).read(_OWNER_ID).total_bookmarks == _FIXTURE_COUNT
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return tuple(captured)


def _plan(connection: Connection, executed: _ExecutedStatement) -> tuple[str, ...]:
    rows = connection.exec_driver_sql(
        f"EXPLAIN QUERY PLAN {executed.statement}", executed.parameters
    ).all()
    return tuple(" ".join(str(row[3]).upper().split()) for row in rows)


def _find(captured: Iterator[_ExecutedStatement], fragment: str) -> _ExecutedStatement:
    return next(statement for statement in captured if fragment in statement.statement)


def _assert_searches_index(plan: tuple[str, ...], index_name: str) -> None:
    assert any(
        re.search(rf"\bSEARCH (?:B|BOOKMARKS) USING (?:COVERING )?INDEX {index_name}\b", detail)
        for detail in plan
    ), plan


def _assert_no_unqualified_bookmark_scan(plan: tuple[str, ...]) -> None:
    assert not any(
        re.search(r"\bSCAN (?:TABLE )?(?:B|BOOKMARKS)\b(?!.*\bUSING\b)", detail) for detail in plan
    ), plan


def test_track04_query_plans_use_owner_and_association_indexes_without_raw_sql_leakage(
    migrated_engine: Engine,
) -> None:
    _seed_plan_fixture(migrated_engine)
    date_query = BookmarkQuery(
        created_from=date(2026, 1, 1), created_to=date(2026, 3, 31), page_size=25
    )
    tag_query = BookmarkQuery(
        tag="focus", created_from=date(2026, 1, 1), created_to=date(2026, 3, 31), page_size=25
    )
    substring_query = BookmarkQuery(q="target", page_size=25)
    date_search = _capture_search_statements(migrated_engine, date_query)
    tag_search = _capture_search_statements(migrated_engine, tag_query)
    substring_search = _capture_search_statements(migrated_engine, substring_query)
    stats = _capture_stats_statements(migrated_engine)

    with migrated_engine.connect() as connection:
        date_count_plan = _plan(connection, _find(iter(date_search), "count(*) AS count_1"))
        date_page_plan = _plan(
            connection, _find(iter(date_search), "ORDER BY bookmarks.created_at")
        )
        tag_count_plan = _plan(connection, _find(iter(tag_search), "count(*) AS count_1"))
        tag_page_plan = _plan(connection, _find(iter(tag_search), "ORDER BY bookmarks.created_at"))
        substring_page_plan = _plan(
            connection, _find(iter(substring_search), "ORDER BY bookmarks.created_at")
        )
        tag_load_plan = _plan(connection, _find(iter(date_search), "FROM bookmark_tags JOIN tags"))
        totals_plan = _plan(connection, stats[0])
        top_tags_plan = _plan(connection, stats[1])
        months_plan = _plan(connection, stats[2])

    for plan in (date_count_plan, date_page_plan, tag_count_plan, tag_page_plan):
        _assert_searches_index(plan, "IX_BOOKMARKS_USER_CREATED_ID")
        _assert_no_unqualified_bookmark_scan(plan)

    # Literal substring matching has no asserted title-index benefit; only owner isolation remains.
    assert any("SEARCH BOOKMARKS USING" in detail for detail in substring_page_plan), (
        substring_page_plan
    )

    for plan in (tag_count_plan, tag_page_plan):
        assert any(
            re.search(
                r"\bSEARCH (?:T|TAGS) USING COVERING INDEX SQLITE_AUTOINDEX_TAGS_1\b",
                detail,
            )
            for detail in plan
        ), plan
        assert any(
            re.search(
                r"\bSEARCH (?:BT|BOOKMARK_TAGS) USING COVERING INDEX "
                r"SQLITE_AUTOINDEX_BOOKMARK_TAGS_1\b",
                detail,
            )
            for detail in plan
        ), plan
    assert any(
        re.search(
            r"\bSEARCH (?:BT|BOOKMARK_TAGS) USING COVERING INDEX "
            r"SQLITE_AUTOINDEX_BOOKMARK_TAGS_1\b",
            detail,
        )
        for detail in tag_load_plan
    ), tag_load_plan

    for plan in (totals_plan, top_tags_plan, months_plan):
        assert any("SEARCH B USING" in detail for detail in plan), plan
        _assert_no_unqualified_bookmark_scan(plan)
    assert any("SEARCH BT USING" in detail for detail in totals_plan), totals_plan
    assert any("SEARCH BT USING" in detail for detail in top_tags_plan), top_tags_plan
    assert any("SEARCH T USING" in detail for detail in top_tags_plan), top_tags_plan

    repository_source = inspect.getsource(BookmarkRepository)
    service_source = Path("app/bookmarks/service.py").read_text(encoding="utf-8")
    stats_source = inspect.getsource(raw_sql)
    assert "text(" not in repository_source
    assert "TextClause" not in repository_source
    assert "text(" not in service_source
    assert "TextClause" not in service_source
    assert stats_source.count("text(") == 3
    assert ".format(" not in stats_source
    assert not any(word in stats_source.lower() for word in ("cache", "queue", "worker", "history"))
