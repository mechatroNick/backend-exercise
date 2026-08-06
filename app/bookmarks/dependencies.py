"""HTTP composition for the bookmark CRUD transport boundary."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from sqlmodel import Session

from app.auth.dependencies import get_session
from app.bookmarks.events import DomainEventPublisher, NoOpDomainEventPublisher
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.service import BookmarkService
from app.bookmarks.stats.dirty import BookmarkStatsDirtyRepository
from app.bookmarks.stats.raw_sql import BookmarkStatsReader
from app.bookmarks.stats.service import CurrentStatsService
from app.bookmarks.stats.snapshots import StatsSnapshotStore
from app.core.clock import Clock


def get_bookmark_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> BookmarkService:
    """Compose the bookmark use case from request-scoped and application-owned state."""
    clock: Clock = request.app.state.clock
    publisher: DomainEventPublisher = getattr(
        request.app.state,
        "bookmark_stats_publisher",
        NoOpDomainEventPublisher(),
    )
    return BookmarkService(
        session=session,
        bookmarks=BookmarkRepository(session),
        tags=TagRepository(session),
        clock=clock,
        publisher=publisher,
        dirty=BookmarkStatsDirtyRepository(session),
        correlation_id_factory=uuid4,
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


def get_bookmark_stats_service(
    request: Request,
    reader: Annotated[BookmarkStatsReader, Depends(get_bookmark_stats_reader)],
) -> CurrentStatsService:
    """Compose optional snapshot acceleration around the canonical live reader."""
    store: StatsSnapshotStore | None = getattr(request.app.state, "bookmark_stats_store", None)
    snapshot_healthy = getattr(
        request.app.state,
        "bookmark_stats_snapshot_healthy",
        lambda: False,
    )
    settings = request.app.state.settings
    return CurrentStatsService(
        reader=reader,
        store=store,
        clock=request.app.state.clock,
        refresh_enabled=settings.stats_refresh_enabled,
        stale_after_seconds=settings.stats_stale_after_seconds,
        snapshot_healthy=snapshot_healthy,
    )


__all__ = [
    "get_bookmark_service",
    "get_bookmark_stats_reader",
    "get_bookmark_stats_service",
]
