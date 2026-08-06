"""Deterministic unit evidence for atomic current-statistics snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from typing import Any, cast

import pytest

from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag
from app.bookmarks.stats.snapshots import StatsSnapshotStore

_NOW = datetime(2026, 8, 6, 12, tzinfo=UTC)


def _stats(total: int) -> BookmarkStats:
    return BookmarkStats(
        total_bookmarks=total,
        total_tags=1 if total else 0,
        top_tags=(TopTag(name="python", count=total),) if total else (),
        bookmarks_per_month=(BookmarksPerMonth(month="2026-08", count=total),) if total else (),
    )


def test_publish_get_invalidate_and_epoch_compare_and_swap() -> None:
    store = StatsSnapshotStore()
    assert store.epoch(7) == 0
    assert store.get(7) is None
    assert store.publish(
        user_id=7,
        stats=_stats(1),
        generated_at=_NOW,
        source_generation=3,
        expected_epoch=0,
    )
    record = store.get(7)
    assert record is not None
    assert (
        record.stats.total_bookmarks,
        record.generated_at,
        record.source_generation,
        record.invalidation_epoch,
    ) == (1, _NOW, 3, 0)

    assert store.invalidate(7) == 1
    assert store.get(7) is None
    assert not store.publish(
        user_id=7,
        stats=_stats(2),
        generated_at=_NOW,
        source_generation=4,
        expected_epoch=0,
    )
    assert store.publish(
        user_id=7,
        stats=_stats(2),
        generated_at=_NOW + timedelta(seconds=1),
        source_generation=4,
        expected_epoch=1,
    )
    assert store.get(7).stats.total_bookmarks == 2  # type: ignore[union-attr]


def test_snapshot_store_rejects_invalid_boundaries() -> None:
    store = StatsSnapshotStore()
    for invalid_user_id in (0, -1, True):
        with pytest.raises(ValueError, match="user_id"):
            store.epoch(invalid_user_id)
        with pytest.raises(ValueError, match="user_id"):
            store.invalidate(invalid_user_id)
        with pytest.raises(ValueError, match="user_id"):
            store.get(invalid_user_id)

    values: dict[str, Any] = {
        "user_id": 7,
        "stats": _stats(1),
        "generated_at": _NOW,
        "source_generation": 1,
        "expected_epoch": 0,
    }
    for field, value, error in (
        ("user_id", True, "user_id"),
        ("stats", {}, "stats"),
        ("generated_at", _NOW.replace(tzinfo=None), "timezone-aware"),
        ("source_generation", 0, "source_generation"),
        ("source_generation", True, "source_generation"),
        ("expected_epoch", -1, "expected_epoch"),
        ("expected_epoch", True, "expected_epoch"),
    ):
        with pytest.raises((TypeError, ValueError), match=error):
            store.publish(**cast(Any, {**values, field: value}))


def test_readers_observe_only_complete_prior_or_new_records() -> None:
    store = StatsSnapshotStore()
    assert store.publish(
        user_id=7,
        stats=_stats(1),
        generated_at=_NOW,
        source_generation=1,
        expected_epoch=0,
    )
    start = Barrier(2)
    observed: list[tuple[int, int]] = []

    def writer() -> None:
        start.wait()
        for generation in range(2, 102):
            assert store.publish(
                user_id=7,
                stats=_stats(generation),
                generated_at=_NOW + timedelta(seconds=generation),
                source_generation=generation,
                expected_epoch=0,
            )

    thread = Thread(target=writer)
    thread.start()
    start.wait()
    while thread.is_alive():
        record = store.get(7)
        assert record is not None
        observed.append((record.stats.total_bookmarks, record.source_generation))
    thread.join()
    final = store.get(7)
    assert final is not None
    observed.append((final.stats.total_bookmarks, final.source_generation))
    assert observed
    assert all(total == generation for total, generation in observed)
    assert observed[-1] == (101, 101)
