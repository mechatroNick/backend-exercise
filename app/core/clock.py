"""Injectable UTC time primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Supplies timezone-aware UTC instants to application services."""

    def now(self) -> datetime:
        """Return the current instant as an aware UTC datetime."""
        ...


def normalize_utc(value: datetime) -> datetime:
    """Convert an aware datetime to UTC and reject ambiguous naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "datetime must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


class SystemClock:
    """The production clock backed by the system's UTC time source."""

    def now(self) -> datetime:
        """Return the current UTC instant for production adapters."""
        return datetime.now(UTC)
