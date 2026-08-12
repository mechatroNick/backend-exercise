"""Private, deterministic weekly bookmark-statistics calculation primitives."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import TextClause, text
from sqlmodel import Session

from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag
from app.core.clock import normalize_utc
from app.core.internal_models import FrozenInternalModel
from app.db.engine import begin_sqlite_read_snapshot

PAYLOAD_SCHEMA_VERSION = 1
_ALGORITHM_VERSION = "weekly-v1"
_MIN_TOP_TAGS_LIMIT = 1
_MAX_TOP_TAGS_LIMIT = 100
_UTC_TEXT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_HASH_DOMAIN = b"bookmark-stats-window\0"

# These statements intentionally parallel, rather than alter, Track 04's all-time reader.
WINDOW_TOTALS_SQL: TextClause = text("""
    SELECT
        count(DISTINCT b.id) AS total_bookmarks,
        count(DISTINCT bt.tag_id) AS total_tags
    FROM bookmarks AS b
    LEFT JOIN bookmark_tags AS bt ON bt.bookmark_id = b.id
    WHERE b.user_id = :user_id
      AND b.created_at >= :window_start
      AND b.created_at < :window_end
""")

WINDOW_TOP_TAGS_SQL: TextClause = text("""
    SELECT
        t.name AS name,
        count(*) AS count
    FROM bookmarks AS b
    JOIN bookmark_tags AS bt ON bt.bookmark_id = b.id
    JOIN tags AS t ON t.id = bt.tag_id
    WHERE b.user_id = :user_id
      AND b.created_at >= :window_start
      AND b.created_at < :window_end
    GROUP BY t.id, t.name
    ORDER BY count DESC, t.name ASC
    LIMIT :top_tags_limit
""")

WINDOW_MONTHS_SQL: TextClause = text("""
    SELECT
        substr(b.created_at, 1, 7) AS month,
        count(*) AS count
    FROM bookmarks AS b
    WHERE b.user_id = :user_id
      AND b.created_at >= :window_start
      AND b.created_at < :window_end
    GROUP BY substr(b.created_at, 1, 7)
    ORDER BY month ASC
""")


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _top_tags_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("top_tags_limit must be an integer")
    if not _MIN_TOP_TAGS_LIMIT <= value <= _MAX_TOP_TAGS_LIMIT:
        raise ValueError("top_tags_limit must be between 1 and 100")
    return value


def _utc(value: datetime, name: str = "datetime") -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    return normalize_utc(value)


def _encoded(value: datetime) -> str:
    return _utc(value).strftime(_UTC_TEXT_FORMAT)


class WeeklyWindow(FrozenInternalModel):
    """One exact UTC Monday-to-Monday half-open event-time window."""

    start: datetime
    end: datetime

    @classmethod
    def from_datetime(cls, value: datetime) -> WeeklyWindow:
        """Normalize one aware instant into its UTC Monday-to-Monday event-time window."""
        instant = _utc(value)
        start = (instant - timedelta(days=instant.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return cls(start=start, end=start + timedelta(days=7))

    @classmethod
    def from_bounds(cls, start: datetime, end: datetime) -> WeeklyWindow:
        """Validate exact canonical bounds before accepting persisted or caller-supplied windows."""
        normalized_start = _utc(start, "window_start")
        normalized_end = _utc(end, "window_end")
        if normalized_start.weekday() != 0 or normalized_start.time().isoformat() != "00:00:00":
            raise ValueError("window_start must be UTC Monday midnight")
        if normalized_end != normalized_start + timedelta(days=7):
            raise ValueError("window_end must be exactly seven days after window_start")
        return cls(start=normalized_start, end=normalized_end)


def weekly_window(value: datetime) -> WeeklyWindow:
    """Return the sole Track 07 calendar calculation for an aware instant."""
    return WeeklyWindow.from_datetime(value)


class WeeklyStatsReader:
    """Read a windowed owner aggregate in one caller-owned SQLite snapshot."""

    def __init__(self, session: Session, top_tags_limit: int) -> None:
        self._session = session
        self._top_tags_limit = _top_tags_limit(top_tags_limit)

    @property
    def calculation_version(self) -> str:
        """Expose the aggregate identity required to compare this reader's payloads safely."""
        return calculation_version(self._top_tags_limit)

    def read(self, user_id: int, window: WeeklyWindow) -> BookmarkStats:
        """Read one owner-scoped event-time aggregate from the caller-owned SQLite snapshot."""
        _positive(user_id, "user_id")
        if not isinstance(window, WeeklyWindow):
            raise TypeError("window must be a WeeklyWindow")
        validated_window = WeeklyWindow.from_bounds(window.start, window.end)
        parameters = {
            "user_id": user_id,
            "window_start": _encoded(validated_window.start),
            "window_end": _encoded(validated_window.end),
            "top_tags_limit": self._top_tags_limit,
        }
        begin_sqlite_read_snapshot(self._session)
        totals = self._session.execute(WINDOW_TOTALS_SQL, parameters).mappings().one()
        top_tags = tuple(
            TopTag(name=row["name"], count=row["count"])
            for row in self._session.execute(WINDOW_TOP_TAGS_SQL, parameters).mappings()
        )
        bookmarks_per_month = tuple(
            BookmarksPerMonth(month=row["month"], count=row["count"])
            for row in self._session.execute(WINDOW_MONTHS_SQL, parameters).mappings()
        )
        return BookmarkStats(
            total_bookmarks=totals["total_bookmarks"],
            total_tags=totals["total_tags"],
            top_tags=top_tags,
            bookmarks_per_month=bookmarks_per_month,
        )


def calculation_version(top_tags_limit: int) -> str:
    """Return the durable version identifier for this exact aggregate shape."""
    return (
        f"{_ALGORITHM_VERSION};payload-schema={PAYLOAD_SCHEMA_VERSION};"
        f"top-tags-limit={_top_tags_limit(top_tags_limit)}"
    )


def canonical_payload_bytes(stats: BookmarkStats) -> bytes:
    """Serialize schema-wrapped aggregate data to its sole stable UTF-8 representation."""
    if not isinstance(stats, BookmarkStats):
        raise TypeError("stats must be BookmarkStats")
    payload: dict[str, Any] = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "stats": stats.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def content_hash(calculation_version_text: str, payload: bytes) -> str:
    """Hash canonical bytes with a calculation-version-scoped domain separator."""
    if not isinstance(calculation_version_text, str) or not calculation_version_text:
        raise ValueError("calculation_version must be a nonempty string")
    if not isinstance(payload, bytes) or not payload:
        raise ValueError("payload must be nonempty bytes")
    return hashlib.sha256(
        _HASH_DOMAIN + calculation_version_text.encode("utf-8") + b"\0" + payload
    ).hexdigest()


class HashComparison(StrEnum):
    """Whether two version-scoped payload identities are comparable and equal."""

    SAME = "same"
    CHANGED = "changed"
    VERSION_MISMATCH = "version_mismatch"


def compare_content_hashes(
    *,
    stored_version: str,
    stored_hash: str,
    candidate_version: str,
    candidate_hash: str,
) -> HashComparison:
    """Compare only compatible hashes; callers decide whether any persistence is warranted."""
    if stored_version != candidate_version:
        return HashComparison.VERSION_MISMATCH
    return HashComparison.SAME if stored_hash == candidate_hash else HashComparison.CHANGED


class WeeklyCalculation(FrozenInternalModel):
    """One deterministic private payload and its version-scoped identity."""

    calculation_version: str
    payload: bytes
    content_hash: str


def calculate_weekly_payload(stats: BookmarkStats, top_tags_limit: int) -> WeeklyCalculation:
    """Build an auditable persistence candidate without accessing time or I/O."""
    version = calculation_version(top_tags_limit)
    payload = canonical_payload_bytes(stats)
    return WeeklyCalculation(
        calculation_version=version,
        payload=payload,
        content_hash=content_hash(version, payload),
    )


__all__ = [
    "HashComparison",
    "PAYLOAD_SCHEMA_VERSION",
    "WINDOW_MONTHS_SQL",
    "WINDOW_TOP_TAGS_SQL",
    "WINDOW_TOTALS_SQL",
    "WeeklyCalculation",
    "WeeklyStatsReader",
    "WeeklyWindow",
    "calculate_weekly_payload",
    "calculation_version",
    "canonical_payload_bytes",
    "compare_content_hashes",
    "content_hash",
    "weekly_window",
]
