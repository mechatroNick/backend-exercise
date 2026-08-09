"""Snapshot selection and live-fallback evidence for current statistics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest
from pydantic import ValidationError

from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag
from app.bookmarks.stats.service import (
    CurrentStatsResult,
    CurrentStatsService,
    StatsSource,
    stats_generated_at_header,
)
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.clock import Clock

_NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


def _stats(total: int) -> BookmarkStats:
    return BookmarkStats(
        total_bookmarks=total,
        total_tags=1 if total else 0,
        top_tags=(TopTag(name="python", count=total),) if total else (),
        bookmarks_per_month=(BookmarksPerMonth(month="2026-08", count=total),) if total else (),
    )


class FakeReader:
    def __init__(self, result: BookmarkStats) -> None:
        self.result = result
        self.user_ids: list[int] = []

    def read(self, user_id: int) -> BookmarkStats:
        self.user_ids.append(user_id)
        return self.result


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def _service(
    *,
    reader: FakeReader,
    store: StatsSnapshotStore | None,
    now: datetime = _NOW,
    enabled: bool = True,
    healthy: object = True,
    stale_after: int = 30,
) -> CurrentStatsService:
    def health() -> bool:
        if isinstance(healthy, Exception):
            raise healthy
        return bool(healthy)

    return CurrentStatsService(
        reader=cast(BookmarkStatsReader, reader),
        store=store,
        clock=cast(Clock, FixedClock(now)),
        refresh_enabled=enabled,
        stale_after_seconds=stale_after,
        snapshot_healthy=health,
    )


@pytest.mark.parametrize("age_seconds", [0, 30])
def test_fresh_healthy_snapshot_is_used_at_inclusive_boundaries(age_seconds: int) -> None:
    store = StatsSnapshotStore()
    snapshot = _stats(2)
    assert store.publish(
        user_id=7,
        stats=snapshot,
        generated_at=_NOW - timedelta(seconds=age_seconds),
        source_generation=1,
        expected_epoch=0,
    )
    reader = FakeReader(_stats(99))

    result = _service(reader=reader, store=store).read(7)

    assert result.stats is snapshot
    assert result.source is StatsSource.SNAPSHOT
    assert result.generated_at == _NOW - timedelta(seconds=age_seconds)
    assert reader.user_ids == []


@pytest.mark.parametrize(
    ("store_mode", "enabled", "healthy", "now"),
    [
        ("missing", True, True, _NOW),
        ("absent", True, True, _NOW),
        ("fresh", False, True, _NOW),
        ("fresh", True, False, _NOW),
        ("fresh", True, RuntimeError("unsafe-health-sentinel"), _NOW),
        ("fresh", True, True, _NOW + timedelta(seconds=31)),
        ("fresh", True, True, _NOW - timedelta(microseconds=1)),
        ("invalidated", True, True, _NOW),
    ],
)
def test_every_untrusted_snapshot_path_uses_exact_live_reader(
    store_mode: str,
    enabled: bool,
    healthy: object,
    now: datetime,
) -> None:
    store = None if store_mode == "absent" else StatsSnapshotStore()
    if store is not None and store_mode not in {"missing"}:
        assert store.publish(
            user_id=7,
            stats=_stats(2),
            generated_at=_NOW,
            source_generation=1,
            expected_epoch=0,
        )
        if store_mode == "invalidated":
            store.invalidate(7)
    live = _stats(3)
    reader = FakeReader(live)

    result = _service(
        reader=reader,
        store=store,
        now=now,
        enabled=enabled,
        healthy=healthy,
    ).read(7)

    assert result.stats is live
    assert result.source is StatsSource.LIVE
    assert result.generated_at is None
    assert reader.user_ids == [7]


def test_service_and_header_encoding_validate_boundaries() -> None:
    reader = FakeReader(_stats(0))
    for enabled in (0, "true"):
        with pytest.raises(TypeError, match="refresh_enabled"):
            CurrentStatsService(
                reader=cast(BookmarkStatsReader, reader),
                store=None,
                clock=cast(Clock, FixedClock(_NOW)),
                refresh_enabled=enabled,  # type: ignore[arg-type]
                stale_after_seconds=30,
                snapshot_healthy=lambda: True,
            )
    for stale_after in (0, -1, True):
        with pytest.raises(ValueError, match="stale_after_seconds"):
            _service(reader=reader, store=None, stale_after=stale_after)

    assert stats_generated_at_header(_NOW) == "2026-08-06T12:00:00.000000Z"
    assert (
        stats_generated_at_header(_NOW.astimezone(timezone(timedelta(hours=10))))
        == "2026-08-06T12:00:00.000000Z"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        stats_generated_at_header(_NOW.replace(tzinfo=None))


def test_result_rejects_incoherent_internal_source_metadata() -> None:
    stats = _stats(0)
    with pytest.raises(ValidationError):
        CurrentStatsResult(stats={}, source=StatsSource.LIVE, generated_at=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        CurrentStatsResult(stats=stats, source="live", generated_at=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="require generated_at"):
        CurrentStatsResult(stats=stats, source=StatsSource.SNAPSHOT, generated_at=None)
    with pytest.raises(ValidationError, match="timezone-aware"):
        CurrentStatsResult(
            stats=stats,
            source=StatsSource.SNAPSHOT,
            generated_at=_NOW.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError, match="must be UTC"):
        CurrentStatsResult(
            stats=stats,
            source=StatsSource.SNAPSHOT,
            generated_at=_NOW.astimezone(timezone(timedelta(hours=10))),
        )
    with pytest.raises(ValidationError, match="must not include"):
        CurrentStatsResult(stats=stats, source=StatsSource.LIVE, generated_at=_NOW)
