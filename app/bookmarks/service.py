"""Transport-independent, transaction-owning bookmark CRUD use cases."""

from __future__ import annotations

import builtins
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from pydantic import AnyHttpUrl
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.bookmarks.events import (
    BookmarkMutationKind,
    BookmarkStatsInvalidated,
    DomainEventPublisher,
)
from app.bookmarks.models import Bookmark, Tag
from app.bookmarks.pagination import BookmarkCursorCodec, CursorBoundary
from app.bookmarks.policy import (
    BookmarkPatchValues,
    BookmarkSnapshot,
    classify_patch,
    next_updated_at,
)
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import (
    BookmarkCreate,
    BookmarkList,
    BookmarkPatch,
    BookmarkPublic,
    BookmarkQuery,
    TagPublic,
)
from app.bookmarks.stats.dirty import DirtyReason, utc_monday
from app.core.clock import Clock, normalize_utc
from app.core.errors import NotFoundError
from app.db.engine import begin_sqlite_read_snapshot

_TAG_UNIQUE_MESSAGE = "UNIQUE constraint failed: tags.name"


class DirtyMarkerWriter(Protocol):
    """Stage one durable invalidation in the caller-owned transaction."""

    def mark_dirty(
        self,
        user_id: int,
        window_start: datetime,
        reason: DirtyReason,
        marked_at: datetime,
    ) -> None:
        """Insert or atomically increment one dirty generation."""


@dataclass(frozen=True, slots=True)
class CursorListResult:
    """A normal list body with an optional opaque continuation value."""

    body: BookmarkList
    next_cursor: str | None


def _is_tag_unique_conflict(error: IntegrityError) -> bool:
    """Recognize only the native SQLite uniqueness race for ``tags.name``."""
    original = error.orig
    return (
        isinstance(original, sqlite3.IntegrityError)
        and getattr(original, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
        and str(original) == _TAG_UNIQUE_MESSAGE
    )


class BookmarkService:
    """Coordinate bookmark and tag persistence within caller-injected collaborators."""

    def __init__(
        self,
        *,
        session: Session,
        bookmarks: BookmarkRepository,
        tags: TagRepository,
        clock: Clock,
        publisher: DomainEventPublisher,
        dirty: DirtyMarkerWriter,
        correlation_id_factory: Callable[[], UUID],
    ) -> None:
        self._session = session
        self._bookmarks = bookmarks
        self._tags = tags
        self._clock = clock
        self._publisher = publisher
        self._dirty = dirty
        self._correlation_id_factory = correlation_id_factory

    def create(self, user_id: int, data: BookmarkCreate) -> BookmarkPublic:
        """Create one bookmark, its canonical tag links, and then notify after commit."""
        try:
            created_at = normalize_utc(self._clock.now())
            bookmark = Bookmark(
                url=str(data.url),
                title=data.title,
                description=data.description,
                user_id=user_id,
                created_at=created_at,
                updated_at=created_at,
            )
            self._bookmarks.add(bookmark)
            self._session.flush()
            bookmark_id = _bookmark_id(bookmark)
            tag_ids = self._resolve_tag_ids(data.tags)
            if not self._bookmarks.replace_tag_links_owned(user_id, bookmark_id, tag_ids):
                raise NotFoundError()
            self._session.flush()
            snapshot = self._required_snapshot(user_id, bookmark_id)
            result = _public_bookmark(snapshot)
            event = self._event(
                user_id=user_id,
                bookmark_id=bookmark_id,
                window_value=snapshot.created_at,
                mutation_kind=BookmarkMutationKind.CREATED,
                occurred_at=created_at,
            )
            self._dirty.mark_dirty(user_id, snapshot.created_at, DirtyReason.CREATE, created_at)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._publisher.publish(event)
        return result

    def list(self, user_id: int, query: BookmarkQuery | None = None) -> BookmarkList:
        """Return one owner-scoped filtered page from a stable SQLite read snapshot."""
        resolved_query = query or BookmarkQuery()
        begin_sqlite_read_snapshot(self._session)
        snapshots, total = self._bookmarks.search_owned(user_id, resolved_query)
        return BookmarkList(
            items=tuple(_public_bookmark(snapshot) for snapshot in snapshots),
            total=total,
            page=resolved_query.page,
            page_size=resolved_query.page_size,
        )

    def list_cursor(
        self,
        user_id: int,
        query: BookmarkQuery,
        *,
        cursor: str | None,
        codec: BookmarkCursorCodec,
    ) -> CursorListResult:
        """Read an owner-bound keyset page from the same SQLite snapshot as totals."""
        boundary = (
            codec.decode(cursor, owner_id=user_id, query=query, now=self._clock.now())
            if cursor is not None
            else None
        )
        begin_sqlite_read_snapshot(self._session)
        snapshots, total, has_more = self._bookmarks.search_owned_after(user_id, query, boundary)
        page = boundary.page if boundary is not None else 1
        body = BookmarkList(
            items=tuple(_public_bookmark(snapshot) for snapshot in snapshots),
            total=total,
            page=page,
            page_size=query.page_size,
        )
        next_cursor: str | None = None
        if has_more:
            last = snapshots[-1]
            next_cursor = codec.encode(
                owner_id=user_id,
                query=query,
                boundary=CursorBoundary(
                    created_at=last.created_at,
                    bookmark_id=last.id,
                    page=page + 1,
                ),
                now=self._clock.now(),
            )
        return CursorListResult(body=body, next_cursor=next_cursor)

    def get(self, user_id: int, bookmark_id: int) -> BookmarkPublic:
        """Return an owner-visible bookmark without opening a write transaction."""
        return _public_bookmark(self._required_snapshot(user_id, bookmark_id))

    def patch(self, user_id: int, bookmark_id: int, data: BookmarkPatch) -> BookmarkPublic:
        """Apply only a material canonical PATCH and publish only after its commit."""
        current = self._required_snapshot(user_id, bookmark_id)
        target = classify_patch(current, cast(BookmarkPatchValues, data))
        if not target.is_material:
            return _public_bookmark(current)

        try:
            updated_at = next_updated_at(current.updated_at, self._clock.now())
            values: dict[str, object] = {"updated_at": updated_at}
            for field, value in (
                ("url", target.url),
                ("title", target.title),
                ("description", target.description),
            ):
                if field in target.changed_fields:
                    values[field] = value
            if not self._bookmarks.update_owned(user_id, bookmark_id, values):
                raise NotFoundError()
            if "tags" in target.changed_fields:
                tag_ids = self._resolve_tag_ids(target.tags)
                if not self._bookmarks.replace_tag_links_owned(user_id, bookmark_id, tag_ids):
                    raise NotFoundError()
            self._session.flush()
            snapshot = self._required_snapshot(user_id, bookmark_id)
            result = _public_bookmark(snapshot)
            mutation_kind = (
                BookmarkMutationKind.TAGS_UPDATED
                if target.changed_fields == frozenset({"tags"})
                else BookmarkMutationKind.UPDATED
            )
            event = self._event(
                user_id=user_id,
                bookmark_id=bookmark_id,
                window_value=current.created_at,
                mutation_kind=mutation_kind,
                occurred_at=updated_at,
            )
            self._dirty.mark_dirty(user_id, current.created_at, DirtyReason.UPDATE, updated_at)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._publisher.publish(event)
        return result

    def delete(self, user_id: int, bookmark_id: int) -> None:
        """Delete an owner-visible bookmark and notify only after the durable commit."""
        try:
            current = self._required_snapshot(user_id, bookmark_id)
            occurred_at = normalize_utc(self._clock.now())
            if not self._bookmarks.delete_owned(user_id, bookmark_id):
                raise NotFoundError()
            event = self._event(
                user_id=user_id,
                bookmark_id=bookmark_id,
                window_value=current.created_at,
                mutation_kind=BookmarkMutationKind.DELETED,
                occurred_at=occurred_at,
            )
            self._dirty.mark_dirty(user_id, current.created_at, DirtyReason.DELETE, occurred_at)
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._publisher.publish(event)

    def _event(
        self,
        *,
        user_id: int,
        bookmark_id: int,
        window_value: datetime,
        mutation_kind: BookmarkMutationKind,
        occurred_at: datetime,
    ) -> BookmarkStatsInvalidated:
        """Build the complete safe event before the mutation commit."""
        return BookmarkStatsInvalidated(
            user_id=user_id,
            window_start=utc_monday(window_value),
            mutation_kind=mutation_kind,
            bookmark_id=bookmark_id,
            occurred_at=normalize_utc(occurred_at),
            correlation_id=self._correlation_id_factory(),
        )

    def _resolve_tag_ids(self, names: tuple[str, ...]) -> builtins.list[int]:
        """Return IDs for sorted canonical names, creating only known-race-safe rows."""
        tag_ids: builtins.list[int] = []
        for name in names:
            tag = self._tags.find_by_name(name)
            if tag is None:
                tag = self._create_or_reload_tag(name)
            tag_ids.append(_tag_id(tag))
        return tag_ids

    def _create_or_reload_tag(self, name: str) -> Tag:
        """Create a tag in a savepoint or reload the exact known uniqueness winner."""
        candidate = Tag(name=name)
        try:
            with self._session.begin_nested():
                self._tags.add(candidate)
                self._session.flush()
        except IntegrityError as error:
            if not _is_tag_unique_conflict(error):
                raise
            winner = self._tags.find_by_name(name)
            if winner is None:
                msg = "tag uniqueness conflict did not yield a persisted winner"
                raise RuntimeError(msg) from error
            return winner
        return candidate

    def _required_snapshot(self, user_id: int, bookmark_id: int) -> BookmarkSnapshot:
        """Convert an owner-scoped absence into the shared concealment-safe error."""
        snapshot = self._bookmarks.get_owned(user_id, bookmark_id)
        if snapshot is None:
            raise NotFoundError()
        return snapshot


def _bookmark_id(bookmark: Bookmark) -> int:
    """Reject a malformed persistence result before using it as a link key."""
    if not isinstance(bookmark.id, int) or isinstance(bookmark.id, bool) or bookmark.id <= 0:
        msg = "persisted bookmark did not receive a valid identifier"
        raise RuntimeError(msg)
    return bookmark.id


def _tag_id(tag: Tag) -> int:
    """Reject a malformed persistence result before using it as a link key."""
    if not isinstance(tag.id, int) or isinstance(tag.id, bool) or tag.id <= 0:
        msg = "persisted tag did not receive a valid identifier"
        raise RuntimeError(msg)
    return tag.id


def _public_bookmark(snapshot: BookmarkSnapshot) -> BookmarkPublic:
    """Map immutable repository data to a session-independent public DTO."""
    return BookmarkPublic(
        id=snapshot.id,
        url=cast(AnyHttpUrl, snapshot.url),
        title=snapshot.title,
        description=snapshot.description,
        tags=tuple(TagPublic(name=name) for name in snapshot.tags),
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
    )


__all__ = ["BookmarkService", "CursorListResult", "DirtyMarkerWriter"]
