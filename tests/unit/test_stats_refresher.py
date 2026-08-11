"""Deterministic lifecycle seams for the bounded statistics refresher."""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime
from threading import Thread, current_thread
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

import app.bookmarks.stats.refresher as refresher_module
from app.bookmarks.stats.projection_repository import (
    ProjectionCalculationVersionMismatchError,
    ProjectionReadinessSnapshot,
)
from app.bookmarks.stats.projection_service import ProjectionProcessOutcome
from app.bookmarks.stats.refresher import (
    ProjectionLifecycleStatus,
    StatsRefresher,
    _ProjectionCycleResult,
)
from app.core.config import Settings
from app.core.logging import configure_logging


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 10, tzinfo=UTC)


class _Publisher:
    def __init__(self) -> None:
        self.required = 0

    def drain(self, limit: int):
        assert limit == 10
        return ()

    def state(self):
        return type(
            "State",
            (),
            {"reconciliation_required": False, "reconciliation_epoch": self.required},
        )()

    def acknowledge_full_reconciliation(self, expected_epoch: int) -> bool:
        assert expected_epoch == self.required
        return True

    def require_full_reconciliation(self) -> None:
        self.required += 1


class _Thread:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.started = False
        self.timeout: float | None = None

    def start(self) -> None:
        self.started = True

    def join(self, timeout: float) -> None:
        self.timeout = timeout

    def is_alive(self) -> bool:
        return False


class _AliveThread(_Thread):
    def is_alive(self) -> bool:
        return True


class _FailingStartThread(_Thread):
    def start(self) -> None:
        raise RuntimeError("private-thread-sentinel")


class _RaisingLogger(logging.Logger):
    def _log(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("private-logger-sentinel")


class _RaisingClock:
    def now(self) -> datetime:
        raise RuntimeError("private-clock-sentinel")


class _ScriptedStop:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self, _timeout: float) -> bool:
        self.calls += 1
        return self.calls >= 2


class _Session:
    def __init__(self) -> None:
        self.rollbacks = 0
        self.closed = False

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _RollbackFailingSession(_Session):
    def rollback(self) -> None:
        raise RuntimeError("private-rollback-sentinel")


class _CloseFailingSession(_Session):
    def close(self) -> None:
        raise RuntimeError("private-close-sentinel")


class _FailingPublisher(_Publisher):
    def drain(self, limit: int) -> tuple[()]:
        del limit
        raise RuntimeError("private-drain-sentinel")

    def require_full_reconciliation(self) -> None:
        raise RuntimeError("private-reconciliation-sentinel")


class _FailingStatePublisher(_Publisher):
    def state(self) -> object:
        raise RuntimeError("private-state-sentinel")


def _fail_session() -> Any:
    raise RuntimeError("private-session-sentinel")


def _refresher(**overrides: Any) -> StatsRefresher:
    arguments: dict[str, Any] = {
        "session_factory": _fail_session,
        "publisher": _Publisher(),
        "store": type("Store", (), {})(),
        "clock": _Clock(),
        "top_tags_limit": 5,
        "interval_seconds": 1,
        "full_reconciliation_seconds": 1,
        "batch_size": 10,
        "logger": logging.getLogger("test.stats.refresher.unit"),
        "service_instance_id": uuid4(),
        "projection_enabled": False,
        "thread_factory": _Thread,
    }
    arguments.update(overrides)
    return StatsRefresher(**arguments)


def test_constructor_is_inert_and_validates_bounds() -> None:
    value = _refresher()
    assert not value.state().started and value.stop(0)
    for name, invalid in (
        ("top_tags_limit", 0),
        ("top_tags_limit", 101),
        ("top_tags_limit", True),
        ("interval_seconds", 0),
        ("interval_seconds", "1"),
        ("full_reconciliation_seconds", 0),
        ("batch_size", 0),
        ("batch_size", 101),
    ):
        with pytest.raises(ValueError):
            _refresher(**{name: invalid})
    with pytest.raises(ValueError, match="at least"):
        _refresher(interval_seconds=2, full_reconciliation_seconds=1)
    for invalid_id in (UUID(int=0), "uuid"):
        with pytest.raises(ValueError, match="service_instance_id"):
            _refresher(service_instance_id=invalid_id)

    for invalid_timeout in (-1, True, "1"):
        with pytest.raises(ValueError, match="timeout_seconds"):
            value.wait_initial(invalid_timeout)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="timeout_seconds"):
            value.stop(invalid_timeout)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="full"):
        value.run_cycle(full=1)  # type: ignore[arg-type]


def test_start_once_exact_thread_and_failed_cycle_state() -> None:
    value = _refresher()
    assert value.start() and not value.start()
    assert (
        value._thread.kwargs["name"] == "bookmark-stats-refresher"
        and not value._thread.kwargs["daemon"]
    )
    assert not value.run_cycle() and value.state().total_cycles >= 1
    assert not value.wait_initial(0)
    assert not value.snapshot_healthy()
    assert value.stop(0)


def test_real_worker_completes_initial_failure_and_stops_cooperatively() -> None:
    value = _refresher(thread_factory=Thread)
    assert value.start()
    assert not value.wait_initial(2)
    state = value.state()
    assert state.initial_completed and not state.initial_success and state.alive
    assert state.consecutive_failures == 1 and state.last_error_code == "cycle_failed"
    assert value.stop(2)
    assert not value.state().alive


def test_thread_start_and_join_timeout_failures_are_explicit() -> None:
    failed_start = _refresher(thread_factory=_FailingStartThread)
    with pytest.raises(RuntimeError, match="private-thread"):
        failed_start.start()
    assert not failed_start.state().started
    assert failed_start.state().last_error_code == "thread_start_failed"

    stuck = _refresher(thread_factory=_AliveThread)
    assert stuck.start()
    assert not stuck.stop(0)
    assert stuck.state().shutdown_timed_out
    assert stuck.state().last_error_code == "shutdown_timeout"

    current = _refresher()
    current._started = True
    current._thread = current_thread()
    assert not current.stop(0)


def test_worker_loop_uses_interruptible_wait_without_sleeping() -> None:
    value = _refresher(publisher=_FailingStatePublisher())
    scripted = _ScriptedStop()
    value._stop_event = scripted  # type: ignore[assignment]
    callbacks: list[str] = []
    events: list[tuple[str, dict[str, Any] | None]] = []
    value._thread = _AliveThread()
    value.defer_until_stopped(lambda: callbacks.append("deferred"))
    value._log_event = (  # type: ignore[method-assign]
        lambda _level, event, **kwargs: events.append((event, kwargs.get("context")))
    )

    value._run()

    assert scripted.calls == 2
    assert callbacks == ["deferred"]
    assert value.state().total_cycles == 2
    assert value.state().consecutive_failures == 2
    assert value.state().initial_completed
    assert events == [
        ("bookmark_stats.projection_disabled", None),
        (
            "bookmark_stats.refresher_started",
            {
                "initial_success": False,
                "failure_count": 1,
                "interval_seconds": 1,
                "worker_is_daemon": current_thread().daemon,
            },
        ),
        ("bookmark_stats.refresh_retrying", {"failure_count": 1}),
    ]


def test_worker_loop_logs_successful_start_without_a_retry_transition() -> None:
    value = _refresher()
    scripted = _ScriptedStop()
    value._stop_event = scripted  # type: ignore[assignment]
    cycles: list[bool] = []
    events: list[tuple[str, dict[str, Any] | None]] = []

    def run_cycle(*, full: bool = False) -> bool:
        cycles.append(full)
        return True

    def record_event(
        _level: int,
        event: str,
        *,
        outcome: str = "success",
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        del outcome, message
        events.append((event, context))

    value.run_cycle = run_cycle  # type: ignore[method-assign]
    value._log_event = record_event  # type: ignore[method-assign]

    value._run()

    assert cycles == [True, True]
    assert events == [
        (
            "bookmark_stats.refresher_started",
            {
                "initial_success": True,
                "failure_count": 0,
                "interval_seconds": 1,
                "worker_is_daemon": current_thread().daemon,
            },
        )
    ]


def test_worker_retry_json_logs_keep_application_source_and_safe_context() -> None:
    stream = io.StringIO()
    logger = configure_logging(
        Settings(app_env="test", stats_refresh_enabled=False),
        stream=stream,
        component="bookmark_stats_refresher",
    )
    value = _refresher(logger=logger, publisher=_FailingStatePublisher())
    value._stop_event = _ScriptedStop()  # type: ignore[assignment]

    value._run()

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    events = [record["event"] for record in records]
    assert "bookmark_stats.refresher_started" in events
    assert "bookmark_stats.refresh_retrying" in events
    assert all(record["source"]["package"].startswith("app") for record in records)
    assert all(record["source"]["module"].startswith("app.") for record in records)
    started = next(
        record for record in records if record["event"] == "bookmark_stats.refresher_started"
    )
    assert type(started["context"]["worker_is_daemon"]) is bool
    assert started["context"]["worker_is_daemon"] is current_thread().daemon
    retry = next(
        record for record in records if record["event"] == "bookmark_stats.refresh_retrying"
    )
    assert retry["context"]["failure_count"] == 1
    assert "private-state-sentinel" not in stream.getvalue()


def test_clock_logger_and_outer_adapter_failures_fail_closed() -> None:
    value = _refresher(clock=_RaisingClock(), logger=_RaisingLogger("raising"))
    assert not value.run_cycle()
    assert not value.run_cycle()

    session = _Session()
    failing_publisher = _FailingPublisher()
    adapter_failure = _refresher(
        session_factory=lambda: session,
        publisher=failing_publisher,
        logger=_RaisingLogger("raising-adapter"),
    )
    assert not adapter_failure.run_cycle()
    assert session.rollbacks == 1 and session.closed

    for failing_session in (_RollbackFailingSession(), _CloseFailingSession()):
        failure = _refresher(
            session_factory=lambda session=failing_session: session,
            publisher=_FailingPublisher(),
        )
        assert not failure.run_cycle()

    class _FailingStore:
        def invalidate(self, _user_id: int) -> int:
            raise RuntimeError("private-invalidation-sentinel")

    adapter_failure._store = _FailingStore()
    adapter_failure._invalidate_safely(1)


def test_deferred_cleanup_validates_and_runs_immediately_after_exit() -> None:
    value = _refresher()
    callbacks: list[str] = []
    value.defer_until_stopped(lambda: callbacks.append("immediate"))
    assert callbacks == ["immediate"]
    with pytest.raises(TypeError, match="callback"):
        value.defer_until_stopped(None)  # type: ignore[arg-type]

    value.defer_until_stopped(
        lambda: (_ for _ in ()).throw(RuntimeError("private-callback-sentinel"))
    )


def test_projection_lifecycle_keeps_running_progress_out_of_failure_accounting() -> None:
    value = _refresher()
    events: list[str] = []
    value._log_event = lambda _level, event, **_kwargs: events.append(event)  # type: ignore[method-assign]

    value._record_projection_cycle(
        _ProjectionCycleResult(
            status=ProjectionLifecycleStatus.RUNNING,
            successful=True,
        ),
        datetime(2026, 8, 10, tzinfo=UTC),
    )

    state = value.state()
    assert state.projection_baseline_status is ProjectionLifecycleStatus.RUNNING
    assert not state.projection_successful
    assert state.projection_last_success_at is None
    assert state.projection_consecutive_failures == 0
    assert events == ["bookmark_stats.projection_baseline_progressed"]


def test_projection_failure_is_logged_once_and_current_lifecycle_remains_separate() -> None:
    value = _refresher()
    events: list[str] = []
    value._log_event = lambda _level, event, **_kwargs: events.append(event)  # type: ignore[method-assign]
    failure = _ProjectionCycleResult(
        status=ProjectionLifecycleStatus.FAILED,
        successful=False,
        error_code="projection_cycle_failed",
    )

    value._record_projection_cycle(failure, datetime(2026, 8, 10, tzinfo=UTC))
    value._record_projection_cycle(failure, datetime(2026, 8, 10, tzinfo=UTC))
    state = value.state()

    assert state.projection_consecutive_failures == 2
    assert state.consecutive_failures == 0
    assert events == ["bookmark_stats.projection_failed"]

    value._record_projection_cycle(
        _ProjectionCycleResult(
            status=ProjectionLifecycleStatus.ACTIVE,
            successful=True,
        ),
        datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert value.state().projection_last_success_at is not None
    assert events[-2:] == [
        "bookmark_stats.projection_baseline_completed",
        "bookmark_stats.projection_recovered",
    ]


def test_unexpected_projection_failure_logs_one_safe_exception_and_recovers() -> None:
    class FailingBaseline:
        def run_step(self) -> None:
            raise RuntimeError("private-projection-sentinel")

    instance_id = UUID("11111111-1111-1111-1111-111111111111")
    stream = io.StringIO()
    logger = configure_logging(
        Settings(app_env="test", stats_refresh_enabled=False),
        stream=stream,
        component="bookmark_stats_refresher",
    )
    value = _refresher(
        logger=logger,
        service_instance_id=instance_id,
        projection_enabled=True,
        baseline_runner_factory=lambda **_kwargs: FailingBaseline(),
    )

    result = value._run_projection_phase()
    value._record_projection_cycle(result, datetime(2026, 8, 10, tzinfo=UTC))
    value._record_projection_cycle(result, datetime(2026, 8, 10, tzinfo=UTC))
    assert value.state().projection_consecutive_failures == 2
    assert value.state().consecutive_failures == 0
    value._record_projection_cycle(
        _ProjectionCycleResult(
            status=ProjectionLifecycleStatus.ACTIVE,
            successful=True,
        ),
        datetime(2026, 8, 10, tzinfo=UTC),
    )

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    failures = [
        record for record in records if record["event"] == "bookmark_stats.projection_failed"
    ]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["level"] == "ERROR"
    assert failure["outcome"] == "degraded"
    assert failure["context"] == {
        "service_instance_id": str(instance_id),
        "failure_count": 1,
    }
    assert failure["exception"]["type"] == "_RefresherBoundaryError"
    assert failure["exception"]["message"] == "weekly projection failed"
    assert failure["exception"]["frames"]
    assert any(
        frame["module"] == "app.bookmarks.stats.refresher"
        for frame in failure["exception"]["frames"]
    )
    assert failure["source"]["package"] == "app.bookmarks.stats"
    assert failure["source"]["module"] == "app.bookmarks.stats.refresher"
    assert "private-projection-sentinel" not in stream.getvalue()
    assert value.state().projection_consecutive_failures == 0
    assert [record["event"] for record in records].count("bookmark_stats.projection_recovered") == 1


def test_projection_version_mismatch_remains_a_low_cardinality_event() -> None:
    class FailingBaseline:
        def run_step(self) -> None:
            raise ProjectionCalculationVersionMismatchError("private-version-sentinel")

    stream = io.StringIO()
    logger = configure_logging(
        Settings(app_env="test", stats_refresh_enabled=False),
        stream=stream,
        component="bookmark_stats_refresher",
    )
    value = _refresher(
        logger=logger,
        projection_enabled=True,
        baseline_runner_factory=lambda **_kwargs: FailingBaseline(),
    )

    result = value._run_projection_phase()
    value._record_projection_cycle(result, datetime(2026, 8, 10, tzinfo=UTC))

    failures = [
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if json.loads(line)["event"] == "bookmark_stats.projection_failed"
    ]
    assert len(failures) == 1
    assert failures[0]["level"] == "WARNING"
    assert failures[0]["context"]["failure_count"] == 1
    assert "exception" not in failures[0]


class _ProjectionSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_projection_phase_skips_dirty_processing_until_baseline_is_active() -> None:
    class IncompleteBaseline:
        def run_step(self):
            return type("Result", (), {"active": False})()

    value = _refresher(
        projection_enabled=True,
        baseline_runner_factory=lambda **_kwargs: IncompleteBaseline(),
    )

    result = value._run_projection_phase()

    assert result.status is ProjectionLifecycleStatus.RUNNING
    assert result.successful
    assert value._projection_last_success_at is None


def test_projection_phase_maps_version_mismatch_without_a_generic_failure() -> None:
    class FailingBaseline:
        def run_step(self):
            raise ProjectionCalculationVersionMismatchError("private-version-sentinel")

    value = _refresher(
        projection_enabled=True,
        baseline_runner_factory=lambda **_kwargs: FailingBaseline(),
    )

    result = value._run_projection_phase()

    assert result.status is ProjectionLifecycleStatus.ACTIVE
    assert not result.successful
    assert not result.version_compatible
    assert result.error_code == "calculation_version_mismatch"


def test_projection_phase_closes_observation_session_when_rollback_fails() -> None:
    class ActiveBaseline:
        def run_step(self):
            return type("Result", (), {"active": True})()

    class RollbackFailingSession(_ProjectionSession):
        def rollback(self) -> None:
            self.rollbacks += 1
            raise RuntimeError("private-rollback-sentinel")

    session = RollbackFailingSession()
    value = _refresher(
        projection_enabled=True,
        session_factory=lambda: session,
        baseline_runner_factory=lambda **_kwargs: ActiveBaseline(),
        projection_repository_factory=lambda _session: type(
            "Repository",
            (),
            {
                "readiness_snapshot": lambda self, _version, _now: (
                    ProjectionReadinessSnapshot.model_construct(
                        state=None,
                        calculation_version_compatible=True,
                        pending_projection_count=0,
                        overdue_working_count=0,
                    )
                )
            },
        )(),
    )

    result = value._run_projection_phase()

    assert result.status is ProjectionLifecycleStatus.FAILED
    assert session.closed


def test_projection_status_distinguishes_absent_and_version_mismatch() -> None:
    absent = ProjectionReadinessSnapshot.model_construct(
        state=None,
        calculation_version_compatible=True,
        pending_projection_count=0,
        overdue_working_count=0,
    )
    mismatch = ProjectionReadinessSnapshot.model_construct(
        state=type("State", (), {"status": ProjectionLifecycleStatus.ACTIVE})(),
        calculation_version_compatible=False,
        pending_projection_count=0,
        overdue_working_count=0,
    )

    assert StatsRefresher._projection_status(absent) is ProjectionLifecycleStatus.ABSENT
    assert StatsRefresher._projection_status(mismatch) is ProjectionLifecycleStatus.FAILED


def test_projection_lifecycle_logs_backlog_transition_once_per_change() -> None:
    value = _refresher()
    events: list[str] = []
    value._log_event = lambda _level, event, **_kwargs: events.append(event)  # type: ignore[method-assign]
    active_with_backlog = _ProjectionCycleResult(
        status=ProjectionLifecycleStatus.ACTIVE,
        successful=True,
        pending_count=1,
    )

    value._record_projection_cycle(active_with_backlog, datetime(2026, 8, 10, tzinfo=UTC))
    value._record_projection_cycle(active_with_backlog, datetime(2026, 8, 10, tzinfo=UTC))
    value._record_projection_cycle(
        _ProjectionCycleResult(status=ProjectionLifecycleStatus.ACTIVE, successful=True),
        datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert events == [
        "bookmark_stats.projection_baseline_completed",
        "bookmark_stats.projection_backlog_detected",
        "bookmark_stats.projection_backlog_cleared",
    ]


@pytest.mark.parametrize(
    "name",
    [
        "baseline_runner_factory",
        "projection_processor_factory",
        "projection_repository_factory",
    ],
)
def test_projection_factories_must_be_callable(name: str) -> None:
    with pytest.raises(TypeError, match=name):
        _refresher(**{name: None})


def test_projection_enabled_must_be_boolean() -> None:
    with pytest.raises(TypeError, match="projection_enabled"):
        _refresher(projection_enabled=1)


def _active_projection_snapshot() -> ProjectionReadinessSnapshot:
    return ProjectionReadinessSnapshot.model_construct(
        state=SimpleNamespace(status=ProjectionLifecycleStatus.ACTIVE),
        calculation_version_compatible=True,
        pending_projection_count=0,
        overdue_working_count=0,
    )


def _projection_phase_refresher(
    monkeypatch: pytest.MonkeyPatch, *, dirty_outcome: object, overdue_outcome: object
) -> tuple[StatsRefresher, list[_ProjectionSession]]:
    class ActiveBaseline:
        def run_step(self):
            return SimpleNamespace(active=True)

    class DirtyRepository:
        def __init__(self, _session: object) -> None:
            pass

        def observe(self, _limit: int) -> tuple[object, ...]:
            return (SimpleNamespace(projection_completed_generation=0, generation=1),)

    class Repository:
        def readiness_snapshot(self, _version: str, _now: datetime) -> ProjectionReadinessSnapshot:
            return _active_projection_snapshot()

        def observe_overdue(self, _now: datetime, _limit: int) -> tuple[object, ...]:
            return (object(),)

    class Processor:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def process_dirty(self, _session: object, _marker: object) -> object:
            if isinstance(dirty_outcome, Exception):
                raise dirty_outcome
            return SimpleNamespace(outcome=dirty_outcome)

        def process_overdue(self, _session: object, _observed: object) -> object:
            if isinstance(overdue_outcome, Exception):
                raise overdue_outcome
            return SimpleNamespace(outcome=overdue_outcome)

    sessions = [_ProjectionSession() for _ in range(4)]
    session_index = 0

    def session_factory() -> _ProjectionSession:
        nonlocal session_index
        session = sessions[session_index]
        session_index += 1
        return session

    monkeypatch.setattr(refresher_module, "BookmarkStatsDirtyRepository", DirtyRepository)
    value = _refresher(
        projection_enabled=True,
        session_factory=session_factory,
        baseline_runner_factory=lambda **_kwargs: ActiveBaseline(),
        projection_processor_factory=Processor,
        projection_repository_factory=lambda _session: Repository(),
    )
    return value, sessions


def test_projection_phase_rolls_back_stale_and_deferred_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, sessions = _projection_phase_refresher(
        monkeypatch,
        dirty_outcome=ProjectionProcessOutcome.STALE,
        overdue_outcome=ProjectionProcessOutcome.DEFERRED,
    )

    result = value._run_projection_phase()

    assert result.successful
    assert all(session.closed for session in sessions)
    assert all(session.commits == 0 for session in sessions)
    assert all(session.rollbacks == 1 for session in sessions)


def test_projection_phase_commits_applied_dirty_and_overdue_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value, sessions = _projection_phase_refresher(
        monkeypatch,
        dirty_outcome=ProjectionProcessOutcome.APPLIED,
        overdue_outcome=ProjectionProcessOutcome.APPLIED,
    )

    result = value._run_projection_phase()

    assert result.successful
    assert sessions[1].commits == 1
    assert sessions[2].commits == 1


@pytest.mark.parametrize("failure_phase", ["dirty", "overdue"])
def test_projection_phase_rolls_back_and_degrades_when_processor_raises(
    monkeypatch: pytest.MonkeyPatch, failure_phase: str
) -> None:
    value, sessions = _projection_phase_refresher(
        monkeypatch,
        dirty_outcome=(
            RuntimeError("private-dirty-sentinel")
            if failure_phase == "dirty"
            else ProjectionProcessOutcome.APPLIED
        ),
        overdue_outcome=(
            RuntimeError("private-overdue-sentinel")
            if failure_phase == "overdue"
            else ProjectionProcessOutcome.APPLIED
        ),
    )

    result = value._run_projection_phase()

    assert not result.successful
    assert result.error_code == "projection_cycle_failed"
    assert all(session.closed for session in sessions[: 2 if failure_phase == "dirty" else 3])
