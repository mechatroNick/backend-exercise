"""Inert post-commit publisher seam for future bookmark-domain integration."""

from __future__ import annotations

from typing import Protocol


class DomainEventPublisher(Protocol):
    """Accept notification that a durable domain mutation has completed."""

    def publish(self) -> None:
        """Publish no concrete Track 03 event payload."""


class NoOpDomainEventPublisher:
    """A deliberately inert publisher used until a later track defines events."""

    def publish(self) -> None:
        """Leave the committed bookmark transaction unchanged."""


__all__ = ["DomainEventPublisher", "NoOpDomainEventPublisher"]
