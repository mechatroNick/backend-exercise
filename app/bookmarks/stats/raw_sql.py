"""Current user-scoped bookmark statistics through the Track 04 raw-SQL boundary."""

from __future__ import annotations

from sqlalchemy import TextClause, text
from sqlmodel import Session

from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag
from app.db.engine import begin_sqlite_read_snapshot

_MIN_TOP_TAGS_LIMIT = 1
_MAX_TOP_TAGS_LIMIT = 100

# The three immutable statements below are deliberately the only SQL in this reader.
TOTALS_SQL: TextClause = text("""
    SELECT
        count(DISTINCT b.id) AS total_bookmarks,
        count(DISTINCT bt.tag_id) AS total_tags
    FROM bookmarks AS b
    LEFT JOIN bookmark_tags AS bt ON bt.bookmark_id = b.id
    WHERE b.user_id = :user_id
""")

TOP_TAGS_SQL: TextClause = text("""
    SELECT
        t.name AS name,
        count(*) AS count
    FROM bookmarks AS b
    JOIN bookmark_tags AS bt ON bt.bookmark_id = b.id
    JOIN tags AS t ON t.id = bt.tag_id
    WHERE b.user_id = :user_id
    GROUP BY t.id, t.name
    ORDER BY count DESC, t.name ASC
    LIMIT :top_tags_limit
""")

MONTHS_SQL: TextClause = text("""
    SELECT
        substr(b.created_at, 1, 7) AS month,
        count(*) AS count
    FROM bookmarks AS b
    WHERE b.user_id = :user_id
    GROUP BY substr(b.created_at, 1, 7)
    ORDER BY month ASC
""")


class BookmarkStatsReader:
    """Read one user's canonical live statistics in one SQLite snapshot."""

    def __init__(self, session: Session, top_tags_limit: int) -> None:
        if isinstance(top_tags_limit, bool) or not isinstance(top_tags_limit, int):
            msg = "top_tags_limit must be an integer"
            raise TypeError(msg)
        if not _MIN_TOP_TAGS_LIMIT <= top_tags_limit <= _MAX_TOP_TAGS_LIMIT:
            msg = "top_tags_limit must be between 1 and 100"
            raise ValueError(msg)
        self._session = session
        self._top_tags_limit = top_tags_limit

    def read(self, user_id: int) -> BookmarkStats:
        """Map three owner-scoped aggregates without committing or rolling back the session."""
        begin_sqlite_read_snapshot(self._session)
        totals = self._session.execute(TOTALS_SQL, {"user_id": user_id}).mappings().one()
        top_tags = tuple(
            TopTag(name=row["name"], count=row["count"])
            for row in self._session.execute(
                TOP_TAGS_SQL,
                {"user_id": user_id, "top_tags_limit": self._top_tags_limit},
            ).mappings()
        )
        bookmarks_per_month = tuple(
            BookmarksPerMonth(month=row["month"], count=row["count"])
            for row in self._session.execute(MONTHS_SQL, {"user_id": user_id}).mappings()
        )
        return BookmarkStats(
            total_bookmarks=totals["total_bookmarks"],
            total_tags=totals["total_tags"],
            top_tags=top_tags,
            bookmarks_per_month=bookmarks_per_month,
        )


__all__ = ["BookmarkStatsReader"]
