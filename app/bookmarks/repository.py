"""Owner-scoped SQLModel persistence adapters for bookmark CRUD."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import Table, delete, exists, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session

from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.policy import (
    BookmarkSnapshot,
    literal_like_pattern,
    utc_midnight_lower_bound,
    utc_midnight_upper_bound,
)
from app.bookmarks.schemas import BookmarkQuery

_BOOKMARKS = cast(Table, Bookmark.__table__)  # type: ignore[attr-defined]
_BOOKMARK_TAGS = cast(Table, BookmarkTag.__table__)  # type: ignore[attr-defined]
_TAGS = cast(Table, Tag.__table__)  # type: ignore[attr-defined]
_MUTABLE_BOOKMARK_FIELDS = frozenset({"url", "title", "description", "updated_at"})


class BookmarkRepository:
    """Expose explicit bookmark persistence operations without owning transactions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, bookmark: Bookmark) -> None:
        """Stage a new bookmark in the caller-owned transaction."""
        self._session.add(bookmark)

    def get_owned(self, user_id: int, bookmark_id: int) -> BookmarkSnapshot | None:
        """Return an immutable owned bookmark snapshot, including ordered tag names."""
        statement = select(Bookmark).where(
            _BOOKMARKS.c.id == bookmark_id,
            _BOOKMARKS.c.user_id == user_id,
        )
        bookmark = self._session.execute(statement).scalar_one_or_none()
        if bookmark is None:
            return None
        return self._snapshot(bookmark, user_id)

    def list_owned(self, user_id: int) -> list[BookmarkSnapshot]:
        """Return all owner-visible bookmarks in the accepted deterministic order."""
        statement = (
            select(Bookmark)
            .where(_BOOKMARKS.c.user_id == user_id)
            .order_by(_BOOKMARKS.c.created_at.desc(), _BOOKMARKS.c.id.desc())
        )
        bookmarks = list(self._session.execute(statement).scalars())
        if not bookmarks:
            return []

        tag_names_by_bookmark = self._tag_names_for_bookmarks(
            user_id,
            [self._required_id(bookmark) for bookmark in bookmarks],
        )
        return [
            self._snapshot_from_values(bookmark, tag_names_by_bookmark[self._required_id(bookmark)])
            for bookmark in bookmarks
        ]

    def search_owned(
        self, user_id: int, query: BookmarkQuery
    ) -> tuple[list[BookmarkSnapshot], int]:
        """Return one owner-scoped page and total using exactly shared ORM predicates."""
        predicates = self._search_predicates(user_id, query)
        count_statement = select(func.count()).select_from(Bookmark).where(*predicates)
        total = int(self._session.execute(count_statement).scalar_one())
        offset = (query.page - 1) * query.page_size
        if offset >= total:
            return [], total

        page_statement = (
            select(Bookmark)
            .where(*predicates)
            .order_by(_BOOKMARKS.c.created_at.desc(), _BOOKMARKS.c.id.desc())
            .offset(offset)
            .limit(query.page_size)
        )
        bookmarks = list(self._session.execute(page_statement).scalars())
        tag_names_by_bookmark = self._tag_names_for_bookmarks(
            user_id,
            [self._required_id(bookmark) for bookmark in bookmarks],
        )
        return (
            [
                self._snapshot_from_values(
                    bookmark, tag_names_by_bookmark[self._required_id(bookmark)]
                )
                for bookmark in bookmarks
            ],
            total,
        )

    def update_owned(self, user_id: int, bookmark_id: int, values: Mapping[str, object]) -> bool:
        """Apply scalar values only when the target bookmark belongs to ``user_id``."""
        unsupported = set(values) - _MUTABLE_BOOKMARK_FIELDS
        if unsupported:
            msg = "bookmark update contains immutable fields"
            raise ValueError(msg)
        if not values:
            return self._owned_bookmark_exists(user_id, bookmark_id)
        statement = (
            update(Bookmark)
            .where(_BOOKMARKS.c.id == bookmark_id, _BOOKMARKS.c.user_id == user_id)
            .values(**dict(values))
        )
        result = cast(CursorResult[Any], self._session.execute(statement))
        return bool(result.rowcount)

    def replace_tag_links_owned(
        self, user_id: int, bookmark_id: int, tag_ids: Sequence[int]
    ) -> bool:
        """Replace links for an owned bookmark without deleting global tag rows."""
        if not self._owned_bookmark_exists(user_id, bookmark_id):
            return False

        owned_bookmark = exists(
            select(_BOOKMARKS.c.id).where(
                _BOOKMARKS.c.id == bookmark_id,
                _BOOKMARKS.c.user_id == user_id,
            )
        )
        delete_statement = delete(BookmarkTag).where(
            _BOOKMARK_TAGS.c.bookmark_id == bookmark_id,
            owned_bookmark,
        )
        self._session.execute(delete_statement)
        self._session.add_all(
            [BookmarkTag(bookmark_id=bookmark_id, tag_id=tag_id) for tag_id in tag_ids]
        )
        return True

    def delete_owned(self, user_id: int, bookmark_id: int) -> bool:
        """Delete an owned bookmark; database cascades remove only its association rows."""
        statement = delete(Bookmark).where(
            _BOOKMARKS.c.id == bookmark_id,
            _BOOKMARKS.c.user_id == user_id,
        )
        result = cast(CursorResult[Any], self._session.execute(statement))
        return bool(result.rowcount)

    def _owned_bookmark_exists(self, user_id: int, bookmark_id: int) -> bool:
        statement = select(_BOOKMARKS.c.id).where(
            _BOOKMARKS.c.id == bookmark_id,
            _BOOKMARKS.c.user_id == user_id,
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    @staticmethod
    def _search_predicates(user_id: int, query: BookmarkQuery) -> tuple[ColumnElement[bool], ...]:
        predicates: list[ColumnElement[bool]] = [_BOOKMARKS.c.user_id == user_id]
        if query.tag is not None:
            tag_matches = exists(
                select(1)
                .select_from(_BOOKMARK_TAGS.join(_TAGS, _TAGS.c.id == _BOOKMARK_TAGS.c.tag_id))
                .where(
                    _BOOKMARK_TAGS.c.bookmark_id == _BOOKMARKS.c.id,
                    _TAGS.c.name == query.tag,
                )
            )
            predicates.append(tag_matches)
        if query.q is not None:
            predicates.append(
                func.lower(_BOOKMARKS.c.title).like(
                    literal_like_pattern(query.q.lower()), escape="\\"
                )
            )
        for column, lower, upper in (
            (_BOOKMARKS.c.created_at, query.created_from, query.created_to),
            (_BOOKMARKS.c.updated_at, query.updated_from, query.updated_to),
        ):
            if lower is not None:
                predicates.append(column >= utc_midnight_lower_bound(lower))
            if upper is not None:
                upper_bound = utc_midnight_upper_bound(upper)
                if upper_bound is not None:
                    predicates.append(column < upper_bound)
        return tuple(predicates)

    def _snapshot(self, bookmark: Bookmark, user_id: int) -> BookmarkSnapshot:
        bookmark_id = self._required_id(bookmark)
        tag_names = self._tag_names_for_bookmarks(user_id, [bookmark_id])[bookmark_id]
        return self._snapshot_from_values(bookmark, tag_names)

    def _tag_names_for_bookmarks(
        self, user_id: int, bookmark_ids: Sequence[int]
    ) -> dict[int, tuple[str, ...]]:
        tag_names: dict[int, list[str]] = {bookmark_id: [] for bookmark_id in bookmark_ids}
        if not bookmark_ids:
            return {}
        statement = (
            select(_BOOKMARK_TAGS.c.bookmark_id, _TAGS.c.name)
            .join(_TAGS, _TAGS.c.id == _BOOKMARK_TAGS.c.tag_id)
            .join(_BOOKMARKS, _BOOKMARKS.c.id == _BOOKMARK_TAGS.c.bookmark_id)
            .where(
                _BOOKMARK_TAGS.c.bookmark_id.in_(bookmark_ids),
                _BOOKMARKS.c.user_id == user_id,
            )
            .order_by(_BOOKMARK_TAGS.c.bookmark_id, _TAGS.c.name)
        )
        for bookmark_id, tag_name in self._session.execute(statement):
            tag_names[bookmark_id].append(tag_name)
        return {bookmark_id: tuple(names) for bookmark_id, names in tag_names.items()}

    @staticmethod
    def _snapshot_from_values(bookmark: Bookmark, tag_names: tuple[str, ...]) -> BookmarkSnapshot:
        return BookmarkSnapshot(
            id=BookmarkRepository._required_id(bookmark),
            url=bookmark.url,
            title=bookmark.title,
            description=bookmark.description,
            tags=tag_names,
            created_at=bookmark.created_at,
            updated_at=bookmark.updated_at,
        )

    @staticmethod
    def _required_id(bookmark: Bookmark) -> int:
        if bookmark.id is None:
            msg = "bookmark must have an identifier before it can be queried"
            raise ValueError(msg)
        return bookmark.id


class TagRepository:
    """Expose global canonical-tag lookup and staging without transaction ownership."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_name(self, name: str) -> Tag | None:
        """Return the globally unique tag matching an already-normalized name."""
        statement = select(Tag).where(_TAGS.c.name == name)
        return self._session.execute(statement).scalar_one_or_none()

    def add(self, tag: Tag) -> None:
        """Stage a global tag in the caller-owned transaction."""
        self._session.add(tag)


__all__ = ["BookmarkRepository", "TagRepository"]
