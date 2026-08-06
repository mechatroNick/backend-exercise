"""Transport-independent, transaction-owning bookmark CRUD use cases."""

from __future__ import annotations

import builtins
import sqlite3
from typing import cast

from pydantic import AnyHttpUrl
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.bookmarks.events import DomainEventPublisher
from app.bookmarks.models import Bookmark, Tag
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
    TagPublic,
)
from app.core.clock import Clock, normalize_utc
from app.core.errors import NotFoundError

_TAG_UNIQUE_MESSAGE = "UNIQUE constraint failed: tags.name"
_BASELINE_PAGE = 1
_BASELINE_PAGE_SIZE = 20


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
    ) -> None:
        self._session = session
        self._bookmarks = bookmarks
        self._tags = tags
        self._clock = clock
        self._publisher = publisher

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
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        result = _public_bookmark(snapshot)
        self._publisher.publish()
        return result

    def list(self, user_id: int) -> BookmarkList:
        """Return the accepted baseline order, its in-memory total, and first 20 items."""
        snapshots = self._bookmarks.list_owned(user_id)
        return BookmarkList(
            items=tuple(_public_bookmark(snapshot) for snapshot in snapshots[:_BASELINE_PAGE_SIZE]),
            total=len(snapshots),
            page=_BASELINE_PAGE,
            page_size=_BASELINE_PAGE_SIZE,
        )

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
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        result = _public_bookmark(snapshot)
        self._publisher.publish()
        return result

    def delete(self, user_id: int, bookmark_id: int) -> None:
        """Delete an owner-visible bookmark and notify only after the durable commit."""
        try:
            if not self._bookmarks.delete_owned(user_id, bookmark_id):
                raise NotFoundError()
            self._session.flush()
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._publisher.publish()

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


__all__ = ["BookmarkService"]
