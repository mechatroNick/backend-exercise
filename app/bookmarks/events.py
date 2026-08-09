"""Safe typed post-commit events for current-statistics invalidation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import model_validator

from app.core.internal_models import FrozenInternalModel


class BookmarkMutationKind(StrEnum):
    """Bounded material mutation categories without submitted content."""

    CREATED = "created"
    UPDATED = "updated"
    TAGS_UPDATED = "tags_updated"
    DELETED = "deleted"


def _positive_identifier(value: int, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must be UTC")


class BookmarkStatsInvalidated(FrozenInternalModel):
    """Content-free wake-up hint for a committed bookmark mutation."""

    user_id: int
    window_start: datetime
    mutation_kind: BookmarkMutationKind
    bookmark_id: int
    occurred_at: datetime
    correlation_id: UUID

    @model_validator(mode="after")
    def _validate_invariants(self) -> BookmarkStatsInvalidated:
        _positive_identifier(self.user_id, "user_id")
        _positive_identifier(self.bookmark_id, "bookmark_id")
        _require_utc(self.window_start, "window_start")
        _require_utc(self.occurred_at, "occurred_at")
        if (
            self.window_start.weekday() != 0
            or self.window_start.hour != 0
            or self.window_start.minute != 0
            or self.window_start.second != 0
            or self.window_start.microsecond != 0
        ):
            raise ValueError("window_start must be UTC Monday midnight")
        if self.correlation_id.int == 0:
            raise ValueError("correlation_id must not be nil")
        return self


class PublishOutcome(StrEnum):
    """Low-cardinality outcome from one total publication attempt."""

    ENQUEUED = "enqueued"
    QUEUE_FULL = "queue_full"
    UNAVAILABLE = "unavailable"


class DomainEventPublisher(Protocol):
    """Publish one event without raising into an already committed request."""

    def publish(self, event: BookmarkStatsInvalidated) -> PublishOutcome:
        """Attempt publication once and return a safe outcome."""
        ...


class NoOpDomainEventPublisher:
    """Typed disabled adapter used until the queue is composed by lifespan."""

    def publish(self, event: BookmarkStatsInvalidated) -> PublishOutcome:
        """Consume the safe event without performing external work."""
        del event
        return PublishOutcome.UNAVAILABLE


__all__ = [
    "BookmarkMutationKind",
    "BookmarkStatsInvalidated",
    "DomainEventPublisher",
    "NoOpDomainEventPublisher",
    "PublishOutcome",
]
