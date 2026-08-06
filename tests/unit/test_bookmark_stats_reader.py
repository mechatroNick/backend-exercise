"""Unit tests for Track 04's isolated current-statistics SQL boundary."""

from __future__ import annotations

import inspect
from typing import cast

import pytest
from sqlalchemy import TextClause
from sqlmodel import Session

from app.bookmarks.stats import raw_sql
from app.bookmarks.stats.raw_sql import (
    MONTHS_SQL,
    TOP_TAGS_SQL,
    TOTALS_SQL,
    BookmarkStatsReader,
)


@pytest.mark.parametrize("value", [True, False, 0, -1, 101])
def test_reader_rejects_invalid_top_tag_limits(value: int | bool) -> None:
    with pytest.raises((TypeError, ValueError)):
        BookmarkStatsReader(cast(Session, object()), value)


def test_reader_owns_exactly_three_static_bound_text_clauses() -> None:
    statements = (TOTALS_SQL, TOP_TAGS_SQL, MONTHS_SQL)

    assert all(isinstance(statement, TextClause) for statement in statements)
    assert len(statements) == 3
    assert set(TOTALS_SQL.compile().params) == {"user_id"}
    assert set(TOP_TAGS_SQL.compile().params) == {"user_id", "top_tags_limit"}
    assert set(MONTHS_SQL.compile().params) == {"user_id"}
    assert all("WHERE b.user_id = :user_id" in statement.text for statement in statements)
    assert "LIMIT :top_tags_limit" in TOP_TAGS_SQL.text
    assert "GROUP BY t.id, t.name" in TOP_TAGS_SQL.text
    assert "ORDER BY count DESC, t.name ASC" in TOP_TAGS_SQL.text
    assert "substr(b.created_at, 1, 7)" in MONTHS_SQL.text
    source = inspect.getsource(raw_sql)
    assert source.count("text(") == 3
    assert ".format(" not in source
