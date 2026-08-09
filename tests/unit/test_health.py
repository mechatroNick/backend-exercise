"""Deterministic fail-closed readiness evaluator matrix."""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.health import (
    ReadinessEvaluator,
    ReadinessReason,
    get_readiness_evaluator,
)
from app.bookmarks.stats.dirty import DirtyBacklog
from app.bookmarks.stats.publisher import PublisherState
from app.bookmarks.stats.refresher import RefresherState
from app.core.config import Settings
from app.core.logging import configure_logging

_NOW = datetime(2026, 8, 7, 12, tzinfo=UTC)


class _Clock:
    def __init__(self, value: datetime = _NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class _Session:
    def __init__(self, failure: str | None = None) -> None:
        self.failure = failure

    def rollback(self) -> None:
        if self.failure == "rollback":
            raise RuntimeError("sentinel")

    def close(self) -> None:
        if self.failure == "close":
            raise RuntimeError("sentinel")


def _worker(**changes: object) -> RefresherState:
    values = dict(
        started=True,
        alive=True,
        cycle_running=False,
        initial_completed=True,
        initial_success=True,
        last_cycle_started_at=None,
        last_cycle_completed_at=_NOW,
        last_success_at=_NOW,
        total_cycles=1,
        successful_cycles=1,
        consecutive_failures=0,
        last_affected_user_count=0,
        last_marker_count=0,
        last_error_code=None,
        shutdown_timed_out=False,
    )
    values.update(changes)
    return RefresherState(**values)


def _publisher(**changes: object) -> PublisherState:
    values = dict(
        queue_depth=0,
        reconciliation_required=False,
        enqueued_count=0,
        overflow_count=0,
        failure_count=0,
        reconciliation_epoch=0,
    )
    values.update(changes)
    return PublisherState(**values)


def _evaluator(
    *,
    enabled: bool = True,
    probe=True,
    backlog=None,
    worker=None,
    publisher=None,
    session_failure=None,
    backlog_failure=None,
    clock=_NOW,
    stream=None,
):
    settings = Settings(
        app_env="test",
        stats_refresh_enabled=enabled,
        stats_refresh_interval_seconds=1,
        stats_stale_after_seconds=10,
        stats_dirty_max_age_seconds=10,
    )
    logger = (
        configure_logging(settings, stream=stream) if stream else logging.getLogger("health-test")
    )

    def factory() -> _Session:
        return _Session(session_failure)

    return ReadinessEvaluator(
        settings=settings,
        session_factory=factory,
        clock=_Clock(clock),
        refresher=type("R", (), {"state": lambda self: worker or _worker()})(),
        publisher=type("P", (), {"state": lambda self: publisher or _publisher()})(),
        logger=logger,
        service_instance_id=uuid4(),
        database_probe=lambda session: (
            probe if not isinstance(probe, Exception) else (_ for _ in ()).throw(probe)
        ),
        backlog_reader=lambda session: (
            (_ for _ in ()).throw(backlog_failure)
            if isinstance(backlog_failure, Exception)
            else DirtyBacklog(count=0, oldest_marked_at=None)
            if backlog is None
            else backlog
        ),
    )


def test_constructor_rejects_non_uuid_and_nil_uuid() -> None:
    evaluator = _evaluator()
    kwargs = {
        "settings": evaluator._settings,
        "session_factory": evaluator._session_factory,
        "clock": evaluator._clock,
        "refresher": evaluator._refresher,
        "publisher": evaluator._publisher,
        "logger": evaluator._logger,
    }
    with pytest.raises(ValueError, match="non-nil UUID"):
        ReadinessEvaluator(**kwargs, service_instance_id=UUID(int=0))
    with pytest.raises(ValueError, match="non-nil UUID"):
        ReadinessEvaluator(**kwargs, service_instance_id="not-a-uuid")


def test_disabled_is_database_only_and_fail_closed_cleanup() -> None:
    assert _evaluator(enabled=False).evaluate().ready
    assert (
        _evaluator(enabled=False, probe=False).evaluate().reason
        is ReadinessReason.DATABASE_UNAVAILABLE
    )
    assert (
        _evaluator(enabled=False, session_failure="rollback").evaluate().reason
        is ReadinessReason.DATABASE_UNAVAILABLE
    )
    assert (
        _evaluator(enabled=False, session_failure="close").evaluate().reason
        is ReadinessReason.DATABASE_UNAVAILABLE
    )
    assert (
        _evaluator(enabled=False, probe=RuntimeError("sentinel")).evaluate().reason
        is ReadinessReason.DATABASE_UNAVAILABLE
    )


def test_enabled_missing_or_unavailable_internal_state_fails_closed() -> None:
    evaluator = _evaluator()
    evaluator._refresher = None
    assert evaluator.evaluate().reason is ReadinessReason.STATE_UNAVAILABLE

    evaluator = _evaluator(backlog_failure=RuntimeError("sentinel"))
    assert evaluator.evaluate().reason is ReadinessReason.DATABASE_UNAVAILABLE

    evaluator = _evaluator()
    evaluator._session_factory = lambda: (_ for _ in ()).throw(RuntimeError("sentinel"))
    assert evaluator.evaluate().reason is ReadinessReason.DATABASE_UNAVAILABLE

    class BrokenRefresher:
        def state(self):
            raise RuntimeError("sentinel")

    evaluator = _evaluator()
    evaluator._refresher = BrokenRefresher()
    assert evaluator.evaluate().reason is ReadinessReason.STATE_UNAVAILABLE


@pytest.mark.parametrize(
    ("worker", "publisher", "backlog", "reason"),
    [
        (
            _worker(started=False),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.WORKER_NOT_STARTED,
        ),
        (
            _worker(alive=False),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.WORKER_NOT_ALIVE,
        ),
        (
            _worker(shutdown_timed_out=True),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.SHUTDOWN_TIMEOUT,
        ),
        (
            _worker(initial_completed=False),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.STARTUP_TIMEOUT,
        ),
        (
            _worker(successful_cycles=0, last_success_at=None),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.NEVER_SUCCESSFUL,
        ),
        (
            _worker(consecutive_failures=1),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.CONSECUTIVE_FAILURES,
        ),
        (
            _worker(),
            _publisher(reconciliation_required=True),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.RECONCILIATION_REQUIRED,
        ),
        (
            _worker(),
            _publisher(),
            DirtyBacklog(count=1, oldest_marked_at=None),
            ReadinessReason.STATE_UNAVAILABLE,
        ),
        (
            _worker(),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=_NOW),
            ReadinessReason.STATE_UNAVAILABLE,
        ),
        (
            _worker(cycle_running=True, last_cycle_started_at=None),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.STATE_UNAVAILABLE,
        ),
        (
            _worker(last_cycle_completed_at=None),
            _publisher(),
            DirtyBacklog(count=0, oldest_marked_at=None),
            ReadinessReason.STATE_UNAVAILABLE,
        ),
    ],
)
def test_fixed_reason_branches(worker, publisher, backlog, reason) -> None:
    assert (
        _evaluator(worker=worker, publisher=publisher, backlog=backlog).evaluate().reason is reason
    )


def test_threshold_boundaries_future_and_healthy_metrics() -> None:
    old = _NOW - timedelta(seconds=11)
    assert (
        _evaluator(backlog=DirtyBacklog(count=1001, oldest_marked_at=_NOW)).evaluate().reason
        is ReadinessReason.DIRTY_BACKLOG_COUNT
    )
    assert (
        _evaluator(backlog=DirtyBacklog(count=1, oldest_marked_at=old)).evaluate().reason
        is ReadinessReason.DIRTY_BACKLOG_AGE
    )
    assert (
        _evaluator(worker=_worker(last_success_at=_NOW + timedelta(seconds=1))).evaluate().reason
        is ReadinessReason.CLOCK_INVALID
    )
    snapshot = _evaluator().evaluate()
    assert snapshot.ready and snapshot.queue_depth == snapshot.dirty_count == 0


@pytest.mark.parametrize(
    ("worker", "reason"),
    [
        (
            _worker(
                cycle_running=True,
                last_cycle_started_at=_NOW - timedelta(seconds=11),
            ),
            ReadinessReason.CYCLE_STUCK,
        ),
        (
            _worker(last_cycle_completed_at=_NOW - timedelta(seconds=11)),
            ReadinessReason.CYCLE_OVERDUE,
        ),
        (
            _worker(last_success_at=_NOW - timedelta(seconds=11)),
            ReadinessReason.SUCCESS_STALE,
        ),
    ],
)
def test_cycle_and_success_staleness_reason_precedence(worker, reason) -> None:
    assert _evaluator(worker=worker).evaluate().reason is reason


def test_all_thresholds_are_inclusive_and_fail_only_after_the_limit() -> None:
    exact = _NOW - timedelta(seconds=10)
    assert _evaluator(worker=_worker(last_cycle_completed_at=exact)).evaluate().ready
    assert _evaluator(worker=_worker(last_success_at=exact)).evaluate().ready
    assert _evaluator(backlog=DirtyBacklog(count=1000, oldest_marked_at=exact)).evaluate().ready
    running = _worker(cycle_running=True, last_cycle_started_at=exact)
    assert _evaluator(worker=running).evaluate().ready


@pytest.mark.parametrize(
    "worker",
    [
        _worker(total_cycles=-1),
        _worker(total_cycles=1, successful_cycles=2),
    ],
)
def test_semantically_malformed_worker_state_is_never_treated_as_ready(worker) -> None:
    assert _evaluator(worker=worker).evaluate().reason is ReadinessReason.STATE_UNAVAILABLE


@pytest.mark.parametrize(
    "changes",
    [
        {"total_cycles": True},
        {"started": 1},
        {"alive": 1},
        {"cycle_running": 1},
        {"initial_completed": 1},
        {"initial_success": 1},
        {"shutdown_timed_out": 1},
    ],
)
def test_worker_state_rejects_coercive_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _worker(**changes)


def test_malformed_publisher_and_backlog_state_is_never_ready() -> None:
    assert (
        _evaluator(publisher=_publisher(queue_depth=-1)).evaluate().reason
        is ReadinessReason.STATE_UNAVAILABLE
    )
    assert (
        _evaluator(backlog=DirtyBacklog(count=-1, oldest_marked_at=None)).evaluate().reason
        is ReadinessReason.STATE_UNAVAILABLE
    )


def test_publisher_state_rejects_coercive_values() -> None:
    with pytest.raises(ValidationError):
        _publisher(reconciliation_required=1)


@pytest.mark.parametrize(
    ("worker", "backlog"),
    [
        (
            _worker(
                cycle_running=True,
                last_cycle_started_at=_NOW + timedelta(seconds=1),
            ),
            DirtyBacklog(count=0, oldest_marked_at=None),
        ),
        (_worker(), DirtyBacklog(count=1, oldest_marked_at=_NOW + timedelta(seconds=1))),
    ],
)
def test_future_operational_timestamps_fail_with_clock_invalid(worker, backlog) -> None:
    assert (
        _evaluator(worker=worker, backlog=backlog).evaluate().reason
        is ReadinessReason.CLOCK_INVALID
    )


def test_subsecond_future_and_threshold_overrun_fail_closed() -> None:
    assert (
        _evaluator(worker=_worker(last_success_at=_NOW + timedelta(microseconds=1)))
        .evaluate()
        .reason
        is ReadinessReason.CLOCK_INVALID
    )
    assert (
        _evaluator(worker=_worker(last_success_at=_NOW - timedelta(seconds=10, microseconds=1)))
        .evaluate()
        .reason
        is ReadinessReason.SUCCESS_STALE
    )


def test_transition_logging_is_once_and_redacted() -> None:
    stream = io.StringIO()
    evaluator = _evaluator(stream=stream)
    evaluator.evaluate()
    evaluator.evaluate()
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 1 and records[0]["event"] == "health.readiness_changed"
    assert {"source", "timestamp", "process_id", "thread_id", "context"} <= set(records[0])
    assert "sentinel" not in stream.getvalue()


def test_transition_logging_records_degraded_to_ready_without_identifiers() -> None:
    stream = io.StringIO()
    evaluator = _evaluator(probe=False, stream=stream)
    assert not evaluator.evaluate().ready
    evaluator._database_probe = lambda _session: True
    assert evaluator.evaluate().ready

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [record["context"]["reason_code"] for record in records] == [
        "database_unavailable",
        "ready",
    ]
    assert [record["component"] for record in records] == ["database", "bookmark_stats_refresher"]
    assert all("user_id" not in json.dumps(record) for record in records)


def test_logging_failure_cannot_break_readiness() -> None:
    class BrokenLogger(logging.Logger):
        def handle(self, record):
            raise RuntimeError("sentinel")

    evaluator = _evaluator()
    evaluator._logger = BrokenLogger("broken-health")
    assert evaluator.evaluate().ready


def test_dependency_rejects_an_invalid_lifespan_state() -> None:
    app = SimpleNamespace(state=SimpleNamespace(readiness_evaluator=object()))
    request = Request({"type": "http", "app": app})
    with pytest.raises(RuntimeError, match="evaluator is unavailable"):
        get_readiness_evaluator(request)
