"""Safe-field and validation evidence for statistics invalidation events."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest

from app.bookmarks.events import (
    BookmarkMutationKind,
    BookmarkStatsInvalidated,
    DomainEventPublisher,
    NoOpDomainEventPublisher,
    PublishOutcome,
)

_CORRELATION_ID = UUID("12345678-1234-5678-9234-567812345678")
_WINDOW = datetime(2026, 8, 3, tzinfo=UTC)
_OCCURRED = datetime(2026, 8, 6, 12, tzinfo=UTC)


def _event(**changes: object) -> BookmarkStatsInvalidated:
    values: dict[str, object] = {
        "user_id": 7,
        "window_start": _WINDOW,
        "mutation_kind": BookmarkMutationKind.CREATED,
        "bookmark_id": 11,
        "occurred_at": _OCCURRED,
        "correlation_id": _CORRELATION_ID,
    }
    values.update(changes)
    return BookmarkStatsInvalidated(**cast(Any, values))


def test_event_is_frozen_content_free_and_noop_publisher_is_total() -> None:
    event = _event()
    publisher: DomainEventPublisher = cast(DomainEventPublisher, NoOpDomainEventPublisher())

    assert publisher.publish(event) is PublishOutcome.UNAVAILABLE
    assert {field.name for field in fields(event)} == {
        "user_id",
        "window_start",
        "mutation_kind",
        "bookmark_id",
        "occurred_at",
        "correlation_id",
    }
    assert not {
        "url",
        "title",
        "description",
        "tags",
        "email",
        "username",
        "password",
        "password_hash",
        "authorization",
        "token",
    } & {field.name for field in fields(event)}
    with pytest.raises(FrozenInstanceError):
        event.user_id = 8  # type: ignore[misc]


@pytest.mark.parametrize("field", ["user_id", "bookmark_id"])
@pytest.mark.parametrize("value", [0, -1])
def test_event_rejects_nonpositive_identifiers(field: str, value: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _event(**{field: value})


@pytest.mark.parametrize("field", ["user_id", "bookmark_id"])
@pytest.mark.parametrize("value", [True, "7", 7.0])
def test_event_rejects_noninteger_identifiers(field: str, value: object) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        _event(**{field: value})


@pytest.mark.parametrize("field", ["window_start", "occurred_at"])
def test_event_rejects_naive_and_non_utc_timestamps(field: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _event(**{field: _OCCURRED.replace(tzinfo=None)})
    with pytest.raises(ValueError, match="must be UTC"):
        _event(
            **{
                field: _OCCURRED.astimezone(timezone(timedelta(hours=10))),
            }
        )


@pytest.mark.parametrize(
    "window",
    [
        _WINDOW + timedelta(days=1),
        _WINDOW + timedelta(hours=1),
        _WINDOW + timedelta(minutes=1),
        _WINDOW + timedelta(seconds=1),
        _WINDOW + timedelta(microseconds=1),
    ],
)
def test_event_rejects_noncanonical_window(window: datetime) -> None:
    with pytest.raises(ValueError, match="UTC Monday midnight"):
        _event(window_start=window)


def test_event_rejects_unbounded_types_and_nil_correlation() -> None:
    with pytest.raises(TypeError, match="window_start must be a datetime"):
        _event(window_start="2026-08-03T00:00:00Z")
    with pytest.raises(TypeError, match="occurred_at must be a datetime"):
        _event(occurred_at="2026-08-06T12:00:00Z")
    with pytest.raises(TypeError, match="mutation_kind"):
        _event(mutation_kind="created")
    with pytest.raises(TypeError, match="correlation_id"):
        _event(correlation_id=str(_CORRELATION_ID))
    with pytest.raises(ValueError, match="must not be nil"):
        _event(correlation_id=UUID(int=0))
