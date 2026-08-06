"""Failure, overflow, and redaction evidence for the bounded publisher."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest

from app.bookmarks.events import (
    BookmarkMutationKind,
    BookmarkStatsInvalidated,
    PublishOutcome,
)
from app.bookmarks.stats.publisher import StatsInvalidationPublisher
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.logging import JsonFormatter

_INSTANCE_ID = UUID("12345678-1234-5678-9234-567812345678")
_CORRELATION_ID = UUID("87654321-4321-6789-a234-567812345678")


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _logger() -> tuple[logging.Logger, ListHandler]:
    logger = logging.getLogger(f"test.stats.publisher.{id(object())}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    handler = ListHandler()
    logger.addHandler(handler)
    return logger, handler


def _event(bookmark_id: int = 11) -> BookmarkStatsInvalidated:
    return BookmarkStatsInvalidated(
        user_id=7,
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        mutation_kind=BookmarkMutationKind.CREATED,
        bookmark_id=bookmark_id,
        occurred_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
        correlation_id=_CORRELATION_ID,
    )


def _publisher(
    store: StatsSnapshotStore,
    capacity: int = 2,
) -> tuple[StatsInvalidationPublisher, ListHandler]:
    logger, handler = _logger()
    return (
        StatsInvalidationPublisher(
            store=store,
            capacity=capacity,
            logger=logger,
            service_instance_id=_INSTANCE_ID,
        ),
        handler,
    )


def test_publish_invalidates_before_one_enqueue_and_drains_bounded_order() -> None:
    store = StatsSnapshotStore()
    publisher, handler = _publisher(store)
    first, second = _event(11), _event(12)

    assert publisher.publish(first) is PublishOutcome.ENQUEUED
    assert publisher.publish(second) is PublishOutcome.ENQUEUED
    assert store.epoch(7) == 2
    assert publisher.drain(1) == (first,)
    assert publisher.drain(2) == (second,)
    assert publisher.drain(2) == ()
    assert publisher.state().enqueued_count == 2
    assert handler.records == []


def test_overflow_invalidates_sets_reconciliation_and_logs_once_per_episode() -> None:
    store = StatsSnapshotStore()
    publisher, handler = _publisher(store, capacity=1)

    assert publisher.publish(_event(11)) is PublishOutcome.ENQUEUED
    assert publisher.publish(_event(12)) is PublishOutcome.QUEUE_FULL
    assert publisher.publish(_event(13)) is PublishOutcome.QUEUE_FULL
    state = publisher.state()
    assert (state.queue_depth, state.reconciliation_required, state.overflow_count) == (
        1,
        True,
        2,
    )
    assert store.epoch(7) == 3
    assert [record.event for record in handler.records] == ["bookmark_stats.queue_overflow"]
    context = handler.records[0].structured_context
    serialized = repr(context)
    assert str(_INSTANCE_ID) in serialized
    assert all(value not in serialized for value in ("user_id", "bookmark_id", " 7", " 12"))

    overflow_epoch = publisher.state().reconciliation_epoch
    assert publisher.acknowledge_full_reconciliation(overflow_epoch)
    assert not publisher.state().reconciliation_required
    assert publisher.publish(_event(14)) is PublishOutcome.QUEUE_FULL
    assert len(handler.records) == 2


class FailingStore:
    def invalidate(self, user_id: int) -> int:
        del user_id
        raise RuntimeError("private-user-content-sentinel")


class FailingQueue:
    def put_nowait(self, value: object) -> None:
        del value
        raise RuntimeError("private-queue-content-sentinel")

    def qsize(self) -> int:
        return 0


class RaisingLogger(logging.Logger):
    def _log(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("logger-private-content-sentinel")


def test_internal_failures_are_total_set_reconciliation_and_log_once() -> None:
    logger, store_handler = _logger()
    store_failure = StatsInvalidationPublisher(
        store=cast(StatsSnapshotStore, FailingStore()),
        capacity=1,
        logger=logger,
        service_instance_id=_INSTANCE_ID,
    )
    assert store_failure.publish(_event()) is PublishOutcome.UNAVAILABLE
    assert store_failure.state().failure_count == 1
    assert store_failure.state().reconciliation_required
    assert [record.event for record in store_handler.records] == ["bookmark_stats.publisher_failed"]

    queue_failure, queue_handler = _publisher(StatsSnapshotStore(), capacity=1)
    queue_failure._queue = cast(Any, FailingQueue())  # type: ignore[attr-defined]
    assert queue_failure.publish(_event()) is PublishOutcome.UNAVAILABLE
    assert queue_failure.state().failure_count == 1
    assert len(queue_handler.records) == 1
    for record in (*store_handler.records, *queue_handler.records):
        assert "private" not in repr(record.structured_context)
        assert "user" not in repr(record.structured_context)
        rendered = JsonFormatter().format(record)
        payload = json.loads(rendered)
        assert "private" not in rendered
        assert payload["exception"]["message"] == "statistics publisher operation failed"
        assert payload["exception"]["frames"]


def test_logging_failure_cannot_escape_the_total_publisher() -> None:
    logger = RaisingLogger("test.stats.publisher.raising")
    overflow = StatsInvalidationPublisher(
        store=StatsSnapshotStore(),
        capacity=1,
        logger=logger,
        service_instance_id=_INSTANCE_ID,
    )
    assert overflow.publish(_event(11)) is PublishOutcome.ENQUEUED
    assert overflow.publish(_event(12)) is PublishOutcome.QUEUE_FULL

    failure = StatsInvalidationPublisher(
        store=cast(StatsSnapshotStore, FailingStore()),
        capacity=1,
        logger=logger,
        service_instance_id=_INSTANCE_ID,
    )
    assert failure.publish(_event()) is PublishOutcome.UNAVAILABLE


def test_publisher_validates_bounds_and_explicit_reconciliation_state() -> None:
    logger, _ = _logger()
    for capacity in (0, -1, True, 1_000_001):
        with pytest.raises(ValueError, match="capacity"):
            StatsInvalidationPublisher(
                store=StatsSnapshotStore(),
                capacity=capacity,
                logger=logger,
                service_instance_id=_INSTANCE_ID,
            )
    with pytest.raises(ValueError, match="service_instance_id"):
        StatsInvalidationPublisher(
            store=StatsSnapshotStore(),
            capacity=1,
            logger=logger,
            service_instance_id=UUID(int=0),
        )

    publisher, _ = _publisher(StatsSnapshotStore(), capacity=2)
    for limit in (0, -1, True, 3):
        with pytest.raises(ValueError, match="limit"):
            publisher.drain(limit)
    publisher.require_full_reconciliation()
    assert publisher.state().reconciliation_required


def test_reconciliation_ack_is_epoch_conditional_and_validates_input() -> None:
    publisher, _ = _publisher(StatsSnapshotStore(), capacity=2)
    publisher.require_full_reconciliation()
    observed_epoch = publisher.state().reconciliation_epoch
    publisher.require_full_reconciliation()

    assert not publisher.acknowledge_full_reconciliation(observed_epoch)
    assert publisher.state().reconciliation_required
    assert publisher.acknowledge_full_reconciliation(observed_epoch + 1)
    assert not publisher.state().reconciliation_required
    for invalid in (-1, True, "1"):
        with pytest.raises(ValueError, match="expected_epoch"):
            publisher.acknowledge_full_reconciliation(invalid)  # type: ignore[arg-type]
