"""Total nonblocking publisher for process-local statistics wake-up hints."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Lock
from uuid import UUID

from app.bookmarks.events import BookmarkStatsInvalidated, PublishOutcome
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.logging import log_event, log_exception

_MAX_QUEUE_CAPACITY = 1_000_000


class _PublisherBoundaryError(RuntimeError):
    """Sanitized exception used to preserve frames without raw adapter text."""


@dataclass(frozen=True, slots=True)
class PublisherState:
    """Safe aggregate publisher state without event or owner identifiers."""

    queue_depth: int
    reconciliation_required: bool
    enqueued_count: int
    overflow_count: int
    failure_count: int
    reconciliation_epoch: int


class StatsInvalidationPublisher:
    """Invalidate locally, attempt one enqueue, and never raise to a request."""

    def __init__(
        self,
        *,
        store: StatsSnapshotStore,
        capacity: int,
        logger: logging.Logger,
        service_instance_id: UUID,
    ) -> None:
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or not 1 <= capacity <= _MAX_QUEUE_CAPACITY
        ):
            raise ValueError("capacity must be between 1 and 1000000")
        if not isinstance(service_instance_id, UUID) or service_instance_id.int == 0:
            raise ValueError("service_instance_id must be a non-nil UUID")
        self._store = store
        self._queue: Queue[BookmarkStatsInvalidated] = Queue(maxsize=capacity)
        self._capacity = capacity
        self._logger = logger
        self._service_instance_id = str(service_instance_id)
        self._lock = Lock()
        self._reconciliation_required = False
        self._overflow_logged = False
        self._enqueued_count = 0
        self._overflow_count = 0
        self._failure_count = 0
        self._reconciliation_epoch = 0

    def publish(self, event_value: BookmarkStatsInvalidated) -> PublishOutcome:
        """Invalidate then make exactly one nonblocking queue attempt."""
        try:
            self._store.invalidate(event_value.user_id)
            self._queue.put_nowait(event_value)
        except Full:
            should_log = self._record_overflow()
            if should_log:
                self._log_overflow(event_value)
            return PublishOutcome.QUEUE_FULL
        except Exception as error:
            self._record_failure()
            self._log_failure(error)
            return PublishOutcome.UNAVAILABLE
        with self._lock:
            self._enqueued_count += 1
        return PublishOutcome.ENQUEUED

    def drain(self, limit: int) -> tuple[BookmarkStatsInvalidated, ...]:
        """Drain at most the requested bounded number of wake-up hints."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= self._capacity
        ):
            raise ValueError("limit must be between 1 and queue capacity")
        drained: list[BookmarkStatsInvalidated] = []
        for _ in range(limit):
            try:
                drained.append(self._queue.get_nowait())
            except Empty:
                break
        return tuple(drained)

    def state(self) -> PublisherState:
        """Return a safe immutable state snapshot for worker and health decisions."""
        with self._lock:
            return PublisherState(
                queue_depth=self._queue.qsize(),
                reconciliation_required=self._reconciliation_required,
                enqueued_count=self._enqueued_count,
                overflow_count=self._overflow_count,
                failure_count=self._failure_count,
                reconciliation_epoch=self._reconciliation_epoch,
            )

    def acknowledge_full_reconciliation(self, expected_epoch: int) -> bool:
        """Clear suspicion only if no newer failure occurred during reconciliation."""
        if (
            isinstance(expected_epoch, bool)
            or not isinstance(expected_epoch, int)
            or expected_epoch < 0
        ):
            raise ValueError("expected_epoch must be a nonnegative integer")
        with self._lock:
            if self._reconciliation_epoch != expected_epoch:
                return False
            self._reconciliation_required = False
            self._overflow_logged = False
            return True

    def require_full_reconciliation(self) -> None:
        """Fail closed when a later component detects possible lost work."""
        with self._lock:
            self._reconciliation_required = True
            self._reconciliation_epoch += 1

    def _record_overflow(self) -> bool:
        with self._lock:
            self._reconciliation_required = True
            self._reconciliation_epoch += 1
            self._overflow_count += 1
            should_log = not self._overflow_logged
            self._overflow_logged = True
            return should_log

    def _record_failure(self) -> None:
        with self._lock:
            self._reconciliation_required = True
            self._reconciliation_epoch += 1
            self._failure_count += 1

    def _safe_context(self) -> dict[str, int | str | bool]:
        state = self.state()
        return {
            "service_instance_id": self._service_instance_id,
            "queue_capacity": self._capacity,
            "queue_depth": state.queue_depth,
            "reconciliation_required": state.reconciliation_required,
            "overflow_count": state.overflow_count,
            "failure_count": state.failure_count,
        }

    def _log_overflow(self, event_value: BookmarkStatsInvalidated) -> None:
        try:
            log_event(
                self._logger,
                logging.WARNING,
                "bookmark_stats.queue_overflow",
                outcome="degraded",
                message="statistics queue capacity reached",
                context=self._safe_context(),
                correlation_id=str(event_value.correlation_id),
                component="bookmark_stats_refresher",
                stacklevel=3,
            )
        except Exception:
            return

    def _log_failure(self, error: Exception) -> None:
        safe_error = _PublisherBoundaryError(
            "statistics publisher operation failed"
        ).with_traceback(error.__traceback__)
        try:
            log_exception(
                self._logger,
                "bookmark_stats.publisher_failed",
                exception=safe_error,
                message="statistics publisher failed",
                context=self._safe_context(),
                component="bookmark_stats_refresher",
                stacklevel=3,
            )
        except Exception:
            return


__all__ = ["PublisherState", "StatsInvalidationPublisher"]
