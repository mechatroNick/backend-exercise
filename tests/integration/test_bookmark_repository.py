"""Alembic-backed integration evidence for bookmark persistence adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, event, select
from sqlmodel import Session

from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _add_user(session: Session, name: str) -> User:
    user = User(
        username=name,
        email=f"{name}@example.test",
        password_hash="$argon2id$test-hash",
        created_at=_NOW,
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    return user


def _add_bookmark(
    session: Session,
    *,
    user_id: int,
    title: str,
    created_at: datetime = _NOW,
) -> Bookmark:
    bookmark = Bookmark(
        url="https://example.test/same-url",
        title=title,
        description=None,
        user_id=user_id,
        created_at=created_at,
        updated_at=created_at,
    )
    BookmarkRepository(session).add(bookmark)
    session.flush()
    assert bookmark.id is not None
    return bookmark


def _add_tag(session: Session, name: str) -> Tag:
    tag = Tag(name=name)
    TagRepository(session).add(tag)
    session.flush()
    assert tag.id is not None
    return tag


def test_owner_scoped_get_list_order_and_deterministic_tags(migrated_engine: Engine) -> None:
    session = Session(migrated_engine)
    try:
        alice = _add_user(session, "alice")
        bob = _add_user(session, "bob")
        assert alice.id is not None
        assert bob.id is not None
        newest = _add_bookmark(session, user_id=alice.id, title="newest")
        same_time = _add_bookmark(session, user_id=alice.id, title="same-time")
        _add_bookmark(
            session,
            user_id=alice.id,
            title="oldest",
            created_at=_NOW - timedelta(seconds=1),
        )
        _add_bookmark(session, user_id=bob.id, title="bob-only")
        zebra = _add_tag(session, "zebra")
        alpha = _add_tag(session, "alpha")
        assert newest.id is not None
        assert same_time.id is not None
        assert zebra.id is not None
        assert alpha.id is not None
        session.add_all(
            [
                BookmarkTag(bookmark_id=newest.id, tag_id=zebra.id),
                BookmarkTag(bookmark_id=newest.id, tag_id=alpha.id),
            ]
        )
        session.commit()

        repository = BookmarkRepository(session)
        snapshot = repository.get_owned(alice.id, newest.id)
        assert snapshot is not None
        assert snapshot.tags == ("alpha", "zebra")
        assert [item.title for item in repository.list_owned(alice.id)] == [
            "same-time",
            "newest",
            "oldest",
        ]
        assert repository.get_owned(bob.id, newest.id) is None
        assert repository.get_owned(alice.id, 999_999) is None
        assert repository.list_owned(999_999) == []
        assert repository._tag_names_for_bookmarks(alice.id, []) == {}  # type: ignore[attr-defined]
        with pytest.raises(ValueError, match="identifier"):
            repository._required_id(  # type: ignore[attr-defined]
                Bookmark(
                    url="https://example.test/unpersisted",
                    title="unpersisted",
                    user_id=alice.id,
                    created_at=_NOW,
                    updated_at=_NOW,
                )
            )
    finally:
        session.close()


def test_owned_mutations_protect_other_users_and_keep_missing_indistinguishable(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        alice = _add_user(session, "alice")
        bob = _add_user(session, "bob")
        assert alice.id is not None
        assert bob.id is not None
        bookmark = _add_bookmark(session, user_id=alice.id, title="alice")
        tag = _add_tag(session, "python")
        assert bookmark.id is not None
        assert tag.id is not None
        session.commit()

        repository = BookmarkRepository(session)
        assert repository.update_owned(bob.id, bookmark.id, {"title": "intrusion"}) is False
        assert repository.update_owned(bob.id, 999_999, {"title": "intrusion"}) is False
        assert repository.replace_tag_links_owned(bob.id, bookmark.id, [tag.id]) is False
        assert repository.replace_tag_links_owned(bob.id, 999_999, [tag.id]) is False
        assert repository.delete_owned(bob.id, bookmark.id) is False
        assert repository.delete_owned(bob.id, 999_999) is False
        assert repository.get_owned(alice.id, bookmark.id).title == "alice"  # type: ignore[union-attr]
        for immutable_values in ({"user_id": bob.id}, {"created_at": _NOW}, {"id": 99}):
            with pytest.raises(ValueError, match="immutable fields"):
                repository.update_owned(alice.id, bookmark.id, immutable_values)
        assert repository.get_owned(alice.id, bookmark.id).title == "alice"  # type: ignore[union-attr]
    finally:
        session.close()


def test_replace_links_and_delete_preserve_global_orphan_tags(migrated_engine: Engine) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        bookmark = _add_bookmark(session, user_id=user.id, title="bookmark")
        python = _add_tag(session, "python")
        async_tag = _add_tag(session, "async")
        assert bookmark.id is not None
        assert python.id is not None
        assert async_tag.id is not None
        session.add(BookmarkTag(bookmark_id=bookmark.id, tag_id=python.id))
        session.commit()

        repository = BookmarkRepository(session)
        assert repository.replace_tag_links_owned(user.id, bookmark.id, [async_tag.id]) is True
        session.flush()
        assert repository.get_owned(user.id, bookmark.id).tags == ("async",)  # type: ignore[union-attr]
        assert session.execute(select(Tag.name).order_by(Tag.name)).scalars().all() == [
            "async",
            "python",
        ]

        assert repository.delete_owned(user.id, bookmark.id) is True
        session.flush()
        assert session.execute(select(BookmarkTag)).scalars().all() == []
        assert session.execute(select(Tag.name).order_by(Tag.name)).scalars().all() == [
            "async",
            "python",
        ]
    finally:
        session.close()


def test_repositories_stage_work_without_committing_and_rollback_restores_state(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        original = _add_bookmark(session, user_id=user.id, title="original")
        existing_tag = _add_tag(session, "existing")
        assert original.id is not None
        assert existing_tag.id is not None
        session.add(BookmarkTag(bookmark_id=original.id, tag_id=existing_tag.id))
        session.commit()

        repository = BookmarkRepository(session)
        tag_repository = TagRepository(session)
        staged = Bookmark(
            url="https://example.test/staged",
            title="staged",
            description=None,
            user_id=user.id,
            created_at=_NOW,
            updated_at=_NOW,
        )
        staged_tag = Tag(name="staged")
        repository.add(staged)
        tag_repository.add(staged_tag)
        session.flush()
        assert staged.id is not None
        assert staged_tag.id is not None
        assert repository.update_owned(user.id, original.id, {"title": "changed"}) is True
        assert repository.update_owned(user.id, original.id, {}) is True
        assert repository.replace_tag_links_owned(user.id, original.id, []) is True
        assert repository.replace_tag_links_owned(user.id, staged.id, [staged_tag.id]) is True
        assert repository.delete_owned(user.id, staged.id) is True
        session.rollback()

        assert repository.get_owned(user.id, original.id).title == "original"  # type: ignore[union-attr]
        assert repository.get_owned(user.id, original.id).tags == ("existing",)  # type: ignore[union-attr]
        assert (
            session.execute(select(Tag.name).where(Tag.name == "staged")).scalar_one_or_none()
            is None
        )
        assert repository.update_owned(user.id, 999_999, {}) is False
    finally:
        session.close()


def test_duplicate_urls_snapshots_and_global_tag_reuse_across_users(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        alice = _add_user(session, "alice")
        bob = _add_user(session, "bob")
        assert alice.id is not None
        assert bob.id is not None
        alice_bookmark = _add_bookmark(session, user_id=alice.id, title="alice")
        bob_bookmark = _add_bookmark(session, user_id=bob.id, title="bob")
        shared = _add_tag(session, "python")
        assert alice_bookmark.id is not None
        assert bob_bookmark.id is not None
        assert shared.id is not None
        session.add_all(
            [
                BookmarkTag(bookmark_id=alice_bookmark.id, tag_id=shared.id),
                BookmarkTag(bookmark_id=bob_bookmark.id, tag_id=shared.id),
            ]
        )
        session.commit()

        assert TagRepository(session).find_by_name("python") == shared
        assert TagRepository(session).find_by_name("missing") is None
        snapshot = BookmarkRepository(session).get_owned(alice.id, alice_bookmark.id)
        assert snapshot is not None
    finally:
        session.close()

    assert snapshot.title == "alice"
    assert snapshot.tags == ("python",)


def test_owner_predicates_are_present_in_bookmark_detail_and_dml_statements(
    migrated_engine: Engine,
) -> None:
    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lower())

    event.listen(migrated_engine, "before_cursor_execute", record_statement)
    session = Session(migrated_engine)
    try:
        user = _add_user(session, "alice")
        assert user.id is not None
        bookmark = _add_bookmark(session, user_id=user.id, title="bookmark")
        tag = _add_tag(session, "python")
        assert bookmark.id is not None
        assert tag.id is not None
        session.commit()
        statements.clear()

        repository = BookmarkRepository(session)
        assert repository.get_owned(user.id, bookmark.id) is not None
        assert repository.update_owned(user.id, bookmark.id, {"title": "changed"}) is True
        assert repository.replace_tag_links_owned(user.id, bookmark.id, [tag.id]) is True
        assert repository.delete_owned(user.id, bookmark.id) is True
        rendered = "\n".join(statements)
        assert "bookmarks.user_id" in rendered
        assert "update bookmarks" in rendered
        assert "delete from bookmark_tags" in rendered
        assert "exists (select bookmarks.id" in rendered
        assert "delete from bookmarks" in rendered
    finally:
        session.close()
        event.remove(migrated_engine, "before_cursor_execute", record_statement)
