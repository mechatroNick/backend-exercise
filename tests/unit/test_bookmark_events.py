"""Unit evidence for the deliberately inert Track 03 publisher seam."""

from __future__ import annotations

from typing import cast

from app.bookmarks.events import DomainEventPublisher, NoOpDomainEventPublisher


def test_noop_publisher_implements_the_zero_argument_inert_port() -> None:
    publisher: DomainEventPublisher = cast(DomainEventPublisher, NoOpDomainEventPublisher())

    assert publisher.publish() is None
