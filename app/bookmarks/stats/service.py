"""Request-facing selection between current snapshots and canonical live SQL."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.bookmarks.stats.schemas import BookmarkStats
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.clock import Clock, normalize_utc


class StatsSource(StrEnum):
    """Documented current-statistics body source."""

    SNAPSHOT = "snapshot"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class CurrentStatsResult:
    """Unchanged body plus transport-only source metadata."""

    stats: BookmarkStats
    source: StatsSource
    generated_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.stats, BookmarkStats):
            raise TypeError("stats must be BookmarkStats")
        if not isinstance(self.source, StatsSource):
            raise TypeError("source must be StatsSource")
        if self.source is StatsSource.SNAPSHOT:
            if self.generated_at is None:
                raise ValueError("snapshot results require generated_at")
            normalized = normalize_utc(self.generated_at)
            if normalized != self.generated_at or self.generated_at.utcoffset() != timedelta(0):
                raise ValueError("snapshot generated_at must be UTC")
        elif self.generated_at is not None:
            raise ValueError("live results must not include generated_at")


class CurrentStatsService:
    """Use only a trustworthy fresh snapshot; otherwise execute canonical SQL."""

    def __init__(
        self,
        *,
        reader: BookmarkStatsReader,
        store: StatsSnapshotStore | None,
        clock: Clock,
        refresh_enabled: bool,
        stale_after_seconds: int,
        snapshot_healthy: Callable[[], bool],
    ) -> None:
        if not isinstance(refresh_enabled, bool):
            raise TypeError("refresh_enabled must be a boolean")
        if (
            isinstance(stale_after_seconds, bool)
            or not isinstance(stale_after_seconds, int)
            or stale_after_seconds <= 0
        ):
            raise ValueError("stale_after_seconds must be a positive integer")
        self._reader = reader
        self._store = store
        self._clock = clock
        self._refresh_enabled = refresh_enabled
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._snapshot_healthy = snapshot_healthy

    def read(self, user_id: int) -> CurrentStatsResult:
        """Return a fresh trusted snapshot or the unchanged canonical live result."""
        now = normalize_utc(self._clock.now())
        if self._refresh_enabled and self._store is not None:
            try:
                healthy = self._snapshot_healthy()
                record = self._store.get(user_id) if healthy else None
            except Exception:
                record = None
            if record is not None:
                age = now - record.generated_at
                if timedelta(0) <= age <= self._stale_after:
                    return CurrentStatsResult(
                        stats=record.stats,
                        source=StatsSource.SNAPSHOT,
                        generated_at=record.generated_at,
                    )
        return CurrentStatsResult(
            stats=self._reader.read(user_id),
            source=StatsSource.LIVE,
            generated_at=None,
        )


def stats_generated_at_header(value: datetime) -> str:
    """Encode one non-content snapshot time in canonical fixed-width UTC form."""
    return normalize_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = [
    "CurrentStatsResult",
    "CurrentStatsService",
    "StatsSource",
    "stats_generated_at_header",
]
