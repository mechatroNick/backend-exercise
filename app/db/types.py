"""SQLAlchemy persistence types shared by feature-owned SQLModel tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import String, TypeDecorator

from app.core.clock import normalize_utc

_UTC_TEXT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_UTC_TEXT_LENGTH = 27


class UTCDateTime(TypeDecorator[datetime]):
    """Store aware UTC datetimes as fixed-width, lexicographically ordered SQLite text."""

    impl = String(_UTC_TEXT_LENGTH)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        """Normalize aware input to UTC and reject naive datetimes at the persistence edge."""
        del dialect
        if value is None:
            return None
        if not isinstance(value, datetime):
            msg = "UTCDateTime values must be datetime instances"
            raise TypeError(msg)
        return normalize_utc(value).strftime(_UTC_TEXT_FORMAT)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        """Return only valid, aware UTC values from the deterministic on-disk format."""
        del dialect
        if value is None:
            return None
        if not isinstance(value, str):
            msg = "UTCDateTime database values must be strings"
            raise TypeError(msg)
        try:
            return datetime.strptime(value, _UTC_TEXT_FORMAT).replace(tzinfo=UTC)
        except ValueError as exc:
            msg = "UTCDateTime database value is not a valid UTC timestamp"
            raise ValueError(msg) from exc
