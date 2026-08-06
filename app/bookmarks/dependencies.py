"""HTTP composition for the bookmark CRUD transport boundary."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.auth.dependencies import get_session
from app.bookmarks.events import NoOpDomainEventPublisher
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.service import BookmarkService
from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.core.clock import Clock


def get_bookmark_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkService:
    """Compose the bookmark use case from request-scoped and application-owned state."""
    clock: Clock = request.app.state.clock
    return BookmarkService(
        session=session,
        bookmarks=BookmarkRepository(session),
        tags=TagRepository(session),
        clock=clock,
        publisher=NoOpDomainEventPublisher(),
    )


def get_bookmark_stats_reader(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkStatsReader:
    """Compose the live current-stats reader from the same request-scoped session."""
    return BookmarkStatsReader(
        session=session,
        top_tags_limit=request.app.state.settings.top_tags_limit,
    )


__all__ = ["get_bookmark_service", "get_bookmark_stats_reader"]
