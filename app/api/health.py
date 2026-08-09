"""Minimal public health routes with bounded internal readiness evaluation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from enum import StrEnum
from math import ceil
from threading import Lock
from typing import TYPE_CHECKING, Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlmodel import Session

from app.core.clock import Clock, normalize_utc
from app.core.config import Settings
from app.core.internal_models import FrozenInternalModel
from app.core.logging import log_event
from app.db.engine import SessionFactory

if TYPE_CHECKING:
    from app.bookmarks.stats.dirty import DirtyBacklog
    from app.bookmarks.stats.publisher import PublisherState, StatsInvalidationPublisher
    from app.bookmarks.stats.refresher import RefresherState, StatsRefresher

_NO_STORE = "no-store"


class LiveHealthResponse(BaseModel):
    """Static liveness body with no dependency-derived detail."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        json_schema_extra={"examples": [{"status": "live"}]},
    )
    status: Literal["live"] = "live"


class ReadyHealthResponse(BaseModel):
    """Redacted readiness body shared by the success and failure statuses."""

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        json_schema_extra={"examples": [{"status": "ready"}, {"status": "not_ready"}]},
    )
    status: Literal["ready", "not_ready"]


class ReadinessReason(StrEnum):
    """Fixed internal failure precedence; never returned by the public route."""

    READY = "ready"
    DATABASE_UNAVAILABLE = "database_unavailable"
    STATE_UNAVAILABLE = "state_unavailable"
    WORKER_NOT_STARTED = "worker_not_started"
    WORKER_NOT_ALIVE = "worker_not_alive"
    SHUTDOWN_TIMEOUT = "shutdown_timeout"
    STARTUP_TIMEOUT = "startup_timeout"
    NEVER_SUCCESSFUL = "never_successful"
    CYCLE_STUCK = "cycle_stuck"
    CYCLE_OVERDUE = "cycle_overdue"
    SUCCESS_STALE = "success_stale"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    DIRTY_BACKLOG_COUNT = "dirty_backlog_count"
    DIRTY_BACKLOG_AGE = "dirty_backlog_age"
    CLOCK_INVALID = "clock_invalid"


class ReadinessSnapshot(FrozenInternalModel):
    """Internal bounded evidence used for decisions and transition logs."""

    ready: bool
    reason: ReadinessReason
    refresh_enabled: bool
    queue_depth: int | None = None
    overflow_count: int | None = None
    dirty_count: int | None = None
    dirty_age_seconds: int | None = None
    consecutive_failures: int | None = None
    cycle_age_seconds: int | None = None
    success_age_seconds: int | None = None


class _Refresher(Protocol):
    def state(self) -> RefresherState: ...


class _Publisher(Protocol):
    def state(self) -> PublisherState: ...


DatabaseProbe = Callable[[Session], bool]
BacklogReader = Callable[[Session], "DirtyBacklog"]


def _database_probe(session: Session) -> bool:
    return bool(session.execute(text("SELECT 1")).scalar_one() == 1)


def _backlog_reader(session: Session) -> DirtyBacklog:
    from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository

    return BookmarkStatsDirtyRepository(session).backlog()


class ReadinessEvaluator:
    """Evaluate independently sampled operational state and log only transitions."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        clock: Clock,
        refresher: StatsRefresher | _Refresher | None,
        publisher: StatsInvalidationPublisher | _Publisher | None,
        logger: logging.Logger,
        service_instance_id: UUID,
        database_probe: DatabaseProbe = _database_probe,
        backlog_reader: BacklogReader = _backlog_reader,
    ) -> None:
        if not isinstance(service_instance_id, UUID) or service_instance_id.int == 0:
            raise ValueError("service_instance_id must be a non-nil UUID")
        self._settings = settings
        self._session_factory = session_factory
        self._clock = clock
        self._refresher: _Refresher | None = refresher
        self._publisher: _Publisher | None = publisher
        self._logger = logger
        self._service_instance_id = str(service_instance_id)
        self._database_probe = database_probe
        self._backlog_reader = backlog_reader
        self._transition_lock = Lock()
        self._last_transition: tuple[bool, ReadinessReason] | None = None

    def evaluate(self) -> ReadinessSnapshot:
        """Return one total, redacted readiness decision."""
        database_ok, backlog = self._read_database_state()
        if not database_ok:
            return self._finish(self._failed(ReadinessReason.DATABASE_UNAVAILABLE))
        if not self._settings.stats_refresh_enabled:
            return self._finish(
                ReadinessSnapshot(
                    ready=True,
                    reason=ReadinessReason.READY,
                    refresh_enabled=False,
                )
            )
        if self._refresher is None or self._publisher is None or backlog is None:
            return self._finish(self._failed(ReadinessReason.STATE_UNAVAILABLE))

        try:
            now = normalize_utc(self._clock.now())
            worker = self._refresher.state()
            publisher = self._publisher.state()
            snapshot = self._enabled_snapshot(now, worker, publisher, backlog)
        except Exception:
            snapshot = self._failed(ReadinessReason.STATE_UNAVAILABLE)
        return self._finish(snapshot)

    def _read_database_state(self) -> tuple[bool, DirtyBacklog | None]:
        session: Session | None = None
        database_ok = False
        backlog: DirtyBacklog | None = None
        cleanup_ok = True
        try:
            session = self._session_factory()
            database_ok = self._database_probe(session) is True
            if database_ok and self._settings.stats_refresh_enabled:
                backlog = self._backlog_reader(session)
        except Exception:
            database_ok = False
        finally:
            if session is not None:
                try:
                    session.rollback()
                except Exception:
                    cleanup_ok = False
                try:
                    session.close()
                except Exception:
                    cleanup_ok = False
        return database_ok and cleanup_ok, backlog

    def _enabled_snapshot(
        self,
        now: datetime,
        worker: RefresherState,
        publisher: PublisherState,
        backlog: DirtyBacklog,
    ) -> ReadinessSnapshot:
        cycle_age = self._age(
            now,
            worker.last_cycle_started_at
            if worker.cycle_running
            else worker.last_cycle_completed_at,
        )
        success_age = self._age(now, worker.last_success_at)
        dirty_age = self._age(now, backlog.oldest_marked_at)
        reason = self._enabled_reason(worker, publisher, backlog, cycle_age, success_age, dirty_age)
        return ReadinessSnapshot(
            ready=reason is ReadinessReason.READY,
            reason=reason,
            refresh_enabled=True,
            queue_depth=publisher.queue_depth,
            overflow_count=publisher.overflow_count,
            dirty_count=backlog.count,
            dirty_age_seconds=dirty_age,
            consecutive_failures=worker.consecutive_failures,
            cycle_age_seconds=cycle_age,
            success_age_seconds=success_age,
        )

    def _enabled_reason(
        self,
        worker: RefresherState,
        publisher: PublisherState,
        backlog: DirtyBacklog,
        cycle_age: int | None,
        success_age: int | None,
        dirty_age: int | None,
    ) -> ReadinessReason:
        stale_after = self._settings.stats_stale_after_seconds
        if not self._valid_state(worker, publisher, backlog):
            return ReadinessReason.STATE_UNAVAILABLE
        if not worker.started:
            return ReadinessReason.WORKER_NOT_STARTED
        if worker.shutdown_timed_out:
            return ReadinessReason.SHUTDOWN_TIMEOUT
        if not worker.alive:
            return ReadinessReason.WORKER_NOT_ALIVE
        if not worker.initial_completed:
            return ReadinessReason.STARTUP_TIMEOUT
        if worker.successful_cycles == 0 or worker.last_success_at is None:
            return ReadinessReason.NEVER_SUCCESSFUL
        if worker.cycle_running and worker.last_cycle_started_at is None:
            return ReadinessReason.STATE_UNAVAILABLE
        if not worker.cycle_running and worker.last_cycle_completed_at is None:
            return ReadinessReason.STATE_UNAVAILABLE
        if worker.cycle_running and cycle_age is not None and cycle_age > stale_after:
            return ReadinessReason.CYCLE_STUCK
        if worker.consecutive_failures > 0:
            return ReadinessReason.CONSECUTIVE_FAILURES
        if not worker.cycle_running and cycle_age is not None and cycle_age > stale_after:
            return ReadinessReason.CYCLE_OVERDUE
        if success_age is not None and success_age > stale_after:
            return ReadinessReason.SUCCESS_STALE
        if publisher.reconciliation_required:
            return ReadinessReason.RECONCILIATION_REQUIRED
        if backlog.count > self._settings.stats_dirty_max_count:
            return ReadinessReason.DIRTY_BACKLOG_COUNT
        if backlog.count == 0 and backlog.oldest_marked_at is not None:
            return ReadinessReason.STATE_UNAVAILABLE
        if backlog.count > 0 and backlog.oldest_marked_at is None:
            return ReadinessReason.STATE_UNAVAILABLE
        if dirty_age is not None and dirty_age > self._settings.stats_dirty_max_age_seconds:
            return ReadinessReason.DIRTY_BACKLOG_AGE
        if any(age is not None and age < 0 for age in (cycle_age, success_age, dirty_age)):
            return ReadinessReason.CLOCK_INVALID
        return ReadinessReason.READY

    @staticmethod
    def _valid_state(
        worker: RefresherState,
        publisher: PublisherState,
        backlog: DirtyBacklog,
    ) -> bool:
        integer_values = (
            worker.total_cycles,
            worker.successful_cycles,
            worker.consecutive_failures,
            worker.last_affected_user_count,
            worker.last_marker_count,
            publisher.queue_depth,
            publisher.enqueued_count,
            publisher.overflow_count,
            publisher.failure_count,
            publisher.reconciliation_epoch,
            backlog.count,
        )
        return (
            all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in integer_values
            )
            and worker.successful_cycles <= worker.total_cycles
            and isinstance(worker.started, bool)
            and isinstance(worker.alive, bool)
            and isinstance(worker.cycle_running, bool)
            and isinstance(worker.initial_completed, bool)
            and isinstance(worker.initial_success, bool)
            and isinstance(worker.shutdown_timed_out, bool)
            and isinstance(publisher.reconciliation_required, bool)
        )

    @staticmethod
    def _age(now: datetime, value: datetime | None) -> int | None:
        if value is None:
            return None
        seconds = (now - normalize_utc(value)).total_seconds()
        return -1 if seconds < 0 else ceil(seconds)

    def _failed(self, reason: ReadinessReason) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            ready=False,
            reason=reason,
            refresh_enabled=self._settings.stats_refresh_enabled,
        )

    def _finish(self, snapshot: ReadinessSnapshot) -> ReadinessSnapshot:
        transition = (snapshot.ready, snapshot.reason)
        with self._transition_lock:
            changed = transition != self._last_transition
            if changed:
                self._last_transition = transition
        if changed:
            self._log_transition(snapshot)
        return snapshot

    def _log_transition(self, snapshot: ReadinessSnapshot) -> None:
        context: dict[str, bool | int | str] = {
            "service_instance_id": self._service_instance_id,
            "ready": snapshot.ready,
            "reason_code": snapshot.reason.value,
            "refresh_enabled": snapshot.refresh_enabled,
        }
        for name in (
            "queue_depth",
            "overflow_count",
            "dirty_count",
            "dirty_age_seconds",
            "consecutive_failures",
            "cycle_age_seconds",
            "success_age_seconds",
        ):
            value = getattr(snapshot, name)
            if value is not None:
                context[name] = value
        component = (
            "database"
            if snapshot.reason is ReadinessReason.DATABASE_UNAVAILABLE
            else "bookmark_stats_refresher"
            if snapshot.refresh_enabled
            else "api"
        )
        with suppress(Exception):
            log_event(
                self._logger,
                logging.INFO if snapshot.ready else logging.WARNING,
                "health.readiness_changed",
                outcome="success" if snapshot.ready else "degraded",
                message="application readiness changed",
                context=context,
                component=component,
                stacklevel=3,
            )


def get_readiness_evaluator(request: Request) -> ReadinessEvaluator:
    """Resolve the lifespan-owned evaluator after application startup."""
    evaluator = request.app.state.readiness_evaluator
    if not isinstance(evaluator, ReadinessEvaluator):
        raise RuntimeError("application readiness evaluator is unavailable")
    return evaluator


router = APIRouter(tags=["health"])


@router.get(
    "/health/live",
    response_model=LiveHealthResponse,
    summary="Report process liveness",
)
def live(response: Response) -> LiveHealthResponse:
    """Return process-local liveness without consulting any dependency."""
    response.headers["Cache-Control"] = _NO_STORE
    return LiveHealthResponse()


@router.get(
    "/health/ready",
    response_model=ReadyHealthResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadyHealthResponse,
            "description": "The database or required internal service is not ready.",
            "content": {
                "application/json": {
                    "examples": {
                        "notReady": {
                            "summary": "A required internal dependency is unavailable",
                            "value": {"status": "not_ready"},
                        }
                    }
                }
            },
        }
    },
    summary="Report application readiness",
)
def ready(
    response: Response,
    evaluator: Annotated[ReadinessEvaluator, Depends(get_readiness_evaluator)],
) -> ReadyHealthResponse:
    """Map internal operational evidence to one redacted availability response."""
    snapshot = evaluator.evaluate()
    response.headers["Cache-Control"] = _NO_STORE
    if not snapshot.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyHealthResponse(status="not_ready")
    return ReadyHealthResponse(status="ready")


__all__ = [
    "LiveHealthResponse",
    "ReadinessEvaluator",
    "ReadinessReason",
    "ReadinessSnapshot",
    "ReadyHealthResponse",
    "get_readiness_evaluator",
    "router",
]
