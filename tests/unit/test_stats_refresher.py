"""Deterministic lifecycle seams for the bounded statistics refresher."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from threading import Thread, current_thread
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.bookmarks.stats.refresher import StatsRefresher


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
        (
            "bookmark_stats.refresher_started",
            {"initial_success": False, "failure_count": 1, "interval_seconds": 1},
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
            {"initial_success": True, "failure_count": 0, "interval_seconds": 1},
        )
    ]


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
