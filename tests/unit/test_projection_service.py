"""Pure application-boundary failure tests for the weekly projection baseline."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.bookmarks.stats import projection_repository as repository_module
from app.bookmarks.stats.projection_repository import (
    ProjectionCalculationVersionMismatchError,
    ProjectionCandidateError,
    ProjectionStateError,
    ProjectionStateRecord,
    ProjectionStateTransitionError,
    SurvivingWindowCandidate,
    WeeklyProjectionRepository,
)
from app.bookmarks.stats.projection_service import BaselineRunner
from app.bookmarks.stats.schemas import BookmarkStats
from app.bookmarks.stats.weekly import calculate_weekly_payload, calculation_version, weekly_window

_NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)
_WINDOW = weekly_window(_NOW)
_VERSION = calculation_version(5)
_STATS = BookmarkStats(
    total_bookmarks=0,
    total_tags=0,
    top_tags=(),
    bookmarks_per_month=(),
)
_CALCULATION = calculate_weekly_payload(_STATS, 5)


class _Clock:
    def now(self) -> datetime:
        return _NOW


def _runner(**overrides: object) -> BaselineRunner:
    values: dict[str, object] = {
        "session_factory": lambda: object(),
        "clock": _Clock(),
        "top_tags_limit": 5,
        "batch_size": 1,
        "reader_factory": lambda _session, _limit: object(),
        "repository_factory": lambda _session: object(),
    }
    values.update(overrides)
    return BaselineRunner(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"session_factory": object()}, "session_factory"),
        ({"clock": object()}, "clock"),
        ({"top_tags_limit": True}, "top_tags_limit"),
        ({"batch_size": True}, "batch_size"),
        ({"batch_size": 0}, "batch_size"),
        ({"reader_factory": object()}, "reader_factory"),
        ({"repository_factory": object()}, "repository_factory"),
    ],
)
def test_baseline_runner_rejects_invalid_dependencies_and_bounds(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _runner(**overrides)


def test_checkpoint_rejects_incomplete_running_state() -> None:
    state = ProjectionStateRecord(
        status=repository_module._ProjectionStateStatus.RUNNING,
        calculation_version=_VERSION,
        checkpoint_user_id=1,
        checkpoint_window=None,
        baseline_started_at=_NOW,
        baseline_completed_at=None,
        updated_at=_NOW,
        last_projection_success_at=None,
        failure_code=None,
    )
    with pytest.raises(ProjectionStateError, match="incomplete"):
        BaselineRunner._checkpoint(state)


class _VersionMismatchReader:
    calculation_version = "wrong-version"

    def read(self, _user_id: int, _window: object) -> BookmarkStats:
        return _STATS


def test_persist_candidate_rejects_reader_calculation_version_mismatch() -> None:
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="reader calculation"):
        _runner()._persist_candidate(
            repository=object(),  # type: ignore[arg-type]
            reader=_VersionMismatchReader(),  # type: ignore[arg-type]
            candidate=SurvivingWindowCandidate(user_id=1, window=_WINDOW),
            now=_NOW,
        )


def test_closed_and_current_existing_version_mismatches_fail_without_writes() -> None:
    closed_repository = SimpleNamespace(
        effective_point=lambda _user_id, _window: SimpleNamespace(
            calculation_version="older-version", content_hash="0" * 64
        )
    )
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="developed"):
        BaselineRunner._persist_closed_candidate(
            closed_repository,  # type: ignore[arg-type]
            SurvivingWindowCandidate(user_id=1, window=_WINDOW),
            _CALCULATION,
            _NOW,
        )

    current_repository = SimpleNamespace(
        get_working=lambda _user_id, _window: SimpleNamespace(calculation_version="older-version")
    )
    with pytest.raises(ProjectionCalculationVersionMismatchError, match="working"):
        BaselineRunner._persist_current_candidate(
            current_repository,  # type: ignore[arg-type]
            SurvivingWindowCandidate(user_id=1, window=_WINDOW),
            _CALCULATION,
            _NOW,
        )


def _state_record(**overrides: object) -> ProjectionStateRecord:
    values: dict[str, object] = {
        "status": repository_module._ProjectionStateStatus.RUNNING,
        "calculation_version": _VERSION,
        "checkpoint_user_id": None,
        "checkpoint_window": None,
        "baseline_started_at": _NOW,
        "baseline_completed_at": None,
        "updated_at": _NOW,
        "last_projection_success_at": None,
        "failure_code": None,
    }
    values.update(overrides)
    return ProjectionStateRecord(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "record",
    [
        _state_record(checkpoint_window=_WINDOW),
        _state_record(checkpoint_user_id=1),
        _state_record(baseline_completed_at=datetime(2026, 8, 18, 11, tzinfo=UTC)),
        _state_record(
            status=repository_module._ProjectionStateStatus.ACTIVE,
            baseline_started_at=None,
        ),
        _state_record(status=repository_module._ProjectionStateStatus.PENDING),
    ],
)
def test_state_record_validation_rejects_malformed_or_impossible_lifecycle(
    record: ProjectionStateRecord,
) -> None:
    with pytest.raises(ProjectionStateTransitionError):
        repository_module._validate_state(record)


def test_state_record_validation_accepts_last_projection_success_timestamp() -> None:
    repository_module._validate_state(_state_record(last_projection_success_at=_NOW))


def test_persisted_state_and_candidate_mismatch_are_rejected() -> None:
    state_row = {
        "status": "running",
        "calculation_version": _VERSION,
        "checkpoint_user_id": 1,
        "checkpoint_window_start": None,
        "baseline_started_at": "2026-08-18T12:00:00.000000Z",
        "baseline_completed_at": None,
        "updated_at": "2026-08-18T12:00:00.000000Z",
        "last_projection_success_at": None,
        "failure_code": None,
    }
    with pytest.raises(ProjectionStateTransitionError, match="checkpoint"):
        repository_module._state(state_row)
    with pytest.raises(ValueError, match="window_start"):
        repository_module._state(
            state_row | {"checkpoint_window_start": "2026-08-18T12:00:00.000000Z"}
        )
    with pytest.raises(ProjectionCandidateError, match="does not match"):
        repository_module._candidate(
            {
                "user_id": 1,
                "representative_created_at": "2026-08-18T12:00:00.000000Z",
                "window_start": "2026-08-10T00:00:00.000000Z",
            }
        )


class _NoopSession:
    def execute(self, _statement: object, _parameters: object = None) -> None:
        return None


def test_repository_state_transition_races_fail_closed() -> None:
    repository = WeeklyProjectionRepository(_NoopSession())  # type: ignore[arg-type]
    repository.get_state = lambda: None  # type: ignore[method-assign]
    with pytest.raises(ProjectionStateTransitionError, match="not created"):
        repository.ensure_state(_VERSION, _NOW)

    repository.ensure_state = lambda _version, _now: SimpleNamespace(  # type: ignore[method-assign]
        status=repository_module._ProjectionStateStatus.PENDING
    )
    with pytest.raises(ProjectionStateTransitionError, match="did not enter"):
        repository.start_or_resume(_VERSION, _NOW)

    repository.ensure_state = lambda _version, _now: SimpleNamespace(  # type: ignore[method-assign]
        status=object()
    )
    with pytest.raises(ProjectionStateTransitionError, match="unsupported"):
        repository.start_or_resume(_VERSION, _NOW)

    repository.get_state = lambda: None  # type: ignore[method-assign]
    candidate = SurvivingWindowCandidate(user_id=1, window=_WINDOW)
    with pytest.raises(ProjectionStateTransitionError, match="checkpoint"):
        repository.advance(candidate, _NOW)
    with pytest.raises(ProjectionStateTransitionError, match="activate"):
        repository.activate(_NOW)
    with pytest.raises(ProjectionStateTransitionError, match="absent"):
        repository.fail(_VERSION, "baseline_failed", _NOW)

    repository.get_state = lambda: SimpleNamespace(  # type: ignore[method-assign]
        status=repository_module._ProjectionStateStatus.ACTIVE,
        calculation_version=_VERSION,
    )
    with pytest.raises(ProjectionStateTransitionError, match="active"):
        repository.fail(_VERSION, "baseline_failed", _NOW)

    calls = iter(
        (
            SimpleNamespace(
                status=repository_module._ProjectionStateStatus.RUNNING,
                calculation_version=_VERSION,
            ),
            None,
        )
    )
    repository.get_state = lambda: next(calls)  # type: ignore[method-assign]
    with pytest.raises(ProjectionStateTransitionError, match="did not enter failed"):
        repository.fail(_VERSION, "baseline_failed", _NOW)
