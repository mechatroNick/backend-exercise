"""Tests for injected UTC time primitives."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.clock import Clock, SystemClock, normalize_utc


class FakeClock:
    """Deterministic test-only clock implementing the production protocol."""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


def test_system_clock_returns_aware_utc_datetime() -> None:
    instant = SystemClock().now()

    assert instant.tzinfo is UTC
    assert instant.utcoffset() == timedelta(0)


def test_normalize_utc_converts_an_aware_offset() -> None:
    offset_time = datetime(2026, 8, 6, 10, 30, tzinfo=timezone(timedelta(hours=10)))

    assert normalize_utc(offset_time) == datetime(2026, 8, 6, 0, 30, tzinfo=UTC)


def test_normalize_utc_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_utc(datetime(2026, 8, 6, 0, 30))


def test_fake_clock_is_deterministic_and_satisfies_protocol() -> None:
    frozen = datetime(2026, 8, 6, 0, 30, tzinfo=UTC)
    clock: Clock = FakeClock(frozen)

    assert clock.now() is frozen
    assert clock.now() is frozen
