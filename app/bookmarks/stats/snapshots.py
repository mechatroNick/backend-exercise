"""Atomic process-local current-statistics snapshots and invalidation epochs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from app.bookmarks.stats.schemas import BookmarkStats
from app.core.clock import normalize_utc


def _positive_identifier(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id must be a positive integer")


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    """One complete immutable aggregate generation."""

    stats: BookmarkStats
    generated_at: datetime
    source_generation: int
    invalidation_epoch: int


class StatsSnapshotStore:
    """Copy-on-write snapshots protected by per-user invalidation epochs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[int, SnapshotRecord] = {}
        self._epochs: dict[int, int] = {}

    def invalidate(self, user_id: int) -> int:
        """Advance and return the epoch before an event enqueue attempt."""
        _positive_identifier(user_id)
        with self._lock:
            epoch = self._epochs.get(user_id, 0) + 1
            self._epochs[user_id] = epoch
            return epoch

    def epoch(self, user_id: int) -> int:
        """Read the epoch a worker must preserve while building a candidate."""
        _positive_identifier(user_id)
        with self._lock:
            return self._epochs.get(user_id, 0)

    def publish(
        self,
        *,
        user_id: int,
        stats: BookmarkStats,
        generated_at: datetime,
        source_generation: int,
        expected_epoch: int,
    ) -> bool:
        """Atomically install a complete candidate only if no mutation intervened."""
        _positive_identifier(user_id)
        if not isinstance(stats, BookmarkStats):
            raise TypeError("stats must be BookmarkStats")
        generated_at = normalize_utc(generated_at)
        if (
            isinstance(source_generation, bool)
            or not isinstance(source_generation, int)
            or source_generation <= 0
        ):
            raise ValueError("source_generation must be a positive integer")
        if (
            isinstance(expected_epoch, bool)
            or not isinstance(expected_epoch, int)
            or expected_epoch < 0
        ):
            raise ValueError("expected_epoch must be a nonnegative integer")
        candidate = SnapshotRecord(
            stats=stats,
            generated_at=generated_at,
            source_generation=source_generation,
            invalidation_epoch=expected_epoch,
        )
        with self._lock:
            if self._epochs.get(user_id, 0) != expected_epoch:
                return False
            records = dict(self._records)
            records[user_id] = candidate
            self._records = records
            return True

    def get(self, user_id: int) -> SnapshotRecord | None:
        """Return only a complete record from the user's current epoch."""
        _positive_identifier(user_id)
        with self._lock:
            record = self._records.get(user_id)
            current_epoch = self._epochs.get(user_id, 0)
            if record is None or record.invalidation_epoch != current_epoch:
                return None
            return record


__all__ = ["SnapshotRecord", "StatsSnapshotStore"]
