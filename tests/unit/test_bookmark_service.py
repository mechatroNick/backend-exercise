"""Transaction-orchestration tests for the bookmark application service."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.bookmarks.events import DomainEventPublisher
from app.bookmarks.models import Bookmark, Tag
from app.bookmarks.policy import BookmarkSnapshot
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.bookmarks.schemas import BookmarkCreate, BookmarkPatch
from app.bookmarks.service import BookmarkService, _bookmark_id, _is_tag_unique_conflict
from app.core.clock import Clock
from app.core.errors import NotFoundError

_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(seconds=1)
_TAG_UNIQUE_MESSAGE = "UNIQUE constraint failed: tags.name"


class NativeTagUniqueError(sqlite3.IntegrityError):
    """A native-shaped SQLite unique error that preserves its error code."""

    sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_UNIQUE


class FakeClock:
    def __init__(self, *instants: datetime) -> None:
        self._instants = list(instants or (_NOW,))
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return self._instants.pop(0)


class _NestedTransaction(AbstractContextManager[None]):
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def __enter__(self) -> None:
        self._session.calls.append("savepoint.enter")
        return None

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        self._session.calls.append(
            "savepoint.rollback" if exception is not None else "savepoint.release"
        )
        return False


class FakeSession:
    def __init__(self, *, failure_at: str | None = None) -> None:
        self.failure_at = failure_at
        self.calls: list[str] = []
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value: object) -> None:
        self.calls.append("session.add")
        if self.failure_at == "session.add":
            raise RuntimeError("session add failed")
        self.added.append(value)

    def flush(self) -> None:
        self.calls.append("flush")
        if self.failure_at == "flush":
            raise RuntimeError("flush failed")
        for value in self.added:
            if isinstance(value, Bookmark) and value.id is None:
                value.id = 11
            if isinstance(value, Tag) and value.id is None:
                value.id = 21

    def begin_nested(self) -> _NestedTransaction:
        self.calls.append("savepoint")
        return _NestedTransaction(self)

    def commit(self) -> None:
        self.calls.append("commit")
        self.commits += 1
        if self.failure_at == "commit":
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.calls.append("rollback")
        self.rollbacks += 1


class FakeBookmarks:
    def __init__(self, session: FakeSession, *, snapshot: BookmarkSnapshot | None = None) -> None:
        self.session = session
        self.snapshot = snapshot or _snapshot()
        self.added: list[Bookmark] = []
        self.links: list[tuple[int, int, list[int]]] = []
        self.updates: list[tuple[int, int, dict[str, object]]] = []
        self.deleted: list[tuple[int, int]] = []
        self.list_result: list[BookmarkSnapshot] = [self.snapshot]
        self.fail_at: str | None = None
        self.present = True
        self.update_result: bool | None = None
        self.link_result: bool | None = None

    def add(self, bookmark: Bookmark) -> None:
        self.session.calls.append("bookmark.add")
        if self.fail_at == "bookmark.add":
            raise RuntimeError("bookmark add failed")
        self.added.append(bookmark)
        self.session.add(bookmark)

    def get_owned(self, _user_id: int, _bookmark_id: int) -> BookmarkSnapshot | None:
        self.session.calls.append("bookmark.get")
        return self.snapshot if self.present else None

    def list_owned(self, _user_id: int) -> list[BookmarkSnapshot]:
        self.session.calls.append("bookmark.list")
        return self.list_result

    def replace_tag_links_owned(self, user_id: int, bookmark_id: int, tag_ids: list[int]) -> bool:
        self.session.calls.append("bookmark.links")
        if self.fail_at == "bookmark.links":
            raise RuntimeError("links failed")
        self.links.append((user_id, bookmark_id, tag_ids))
        return self.present if self.link_result is None else self.link_result

    def update_owned(self, user_id: int, bookmark_id: int, values: dict[str, object]) -> bool:
        self.session.calls.append("bookmark.update")
        if self.fail_at == "bookmark.update":
            raise RuntimeError("update failed")
        self.updates.append((user_id, bookmark_id, values))
        return self.present if self.update_result is None else self.update_result

    def delete_owned(self, user_id: int, bookmark_id: int) -> bool:
        self.session.calls.append("bookmark.delete")
        if self.fail_at == "bookmark.delete":
            raise RuntimeError("delete failed")
        self.deleted.append((user_id, bookmark_id))
        return self.present


class FakeTags:
    def __init__(self, session: FakeSession, *, existing: dict[str, Tag] | None = None) -> None:
        self.session = session
        self.existing = existing or {}
        self.lookups: list[str] = []
        self.added: list[Tag] = []
        self.fail_at: str | None = None
        self.race_winner: Tag | None = None

    def find_by_name(self, name: str) -> Tag | None:
        self.session.calls.append(f"tag.find:{name}")
        self.lookups.append(name)
        return self.existing.get(name) or self.race_winner

    def add(self, tag: Tag) -> None:
        self.session.calls.append(f"tag.add:{tag.name}")
        if self.fail_at == "tag.add":
            raise RuntimeError("tag add failed")
        self.added.append(tag)
        self.session.add(tag)


class FakePublisher:
    def __init__(self, *, failure: Exception | None = None, calls: list[str] | None = None) -> None:
        self.failure = failure
        self.calls = calls if calls is not None else []
        self.count = 0

    def publish(self) -> None:
        self.calls.append("publish")
        self.count += 1
        if self.failure is not None:
            raise self.failure


def _snapshot(**changes: object) -> BookmarkSnapshot:
    values: dict[str, object] = {
        "id": 11,
        "url": "https://example.test/bookmark",
        "title": "Bookmark",
        "description": "description",
        "tags": ("python",),
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    values.update(changes)
    return BookmarkSnapshot(**cast(Any, values))


def _create(**changes: object) -> BookmarkCreate:
    values: dict[str, object] = {
        "url": "https://example.test/bookmark",
        "title": "Bookmark",
        "description": "description",
        "tags": ["python", "async"],
    }
    values.update(changes)
    return BookmarkCreate(**values)


def _service(
    session: FakeSession,
    *,
    bookmarks: FakeBookmarks | None = None,
    tags: FakeTags | None = None,
    clock: FakeClock | None = None,
    publisher: FakePublisher | None = None,
) -> BookmarkService:
    return BookmarkService(
        session=cast(Session, session),
        bookmarks=cast(BookmarkRepository, bookmarks or FakeBookmarks(session)),
        tags=cast(TagRepository, tags or FakeTags(session)),
        clock=cast(Clock, clock or FakeClock()),
        publisher=cast(DomainEventPublisher, publisher or FakePublisher()),
    )


def test_create_uses_one_instant_commits_once_and_publishes_after_the_durable_snapshot() -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    tags = FakeTags(session, existing={"async": Tag(id=22, name="async")})
    clock = FakeClock(_NOW)
    publisher = FakePublisher(calls=session.calls)

    response = _service(
        session, bookmarks=bookmarks, tags=tags, clock=clock, publisher=publisher
    ).create(7, _create())

    assert response.model_dump(mode="json") == {
        "id": 11,
        "url": "https://example.test/bookmark",
        "title": "Bookmark",
        "description": "description",
        "tags": [{"name": "python"}],
        "created_at": "2026-08-06T12:00:00Z",
        "updated_at": "2026-08-06T12:00:00Z",
    }
    assert (bookmarks.added[0].created_at, bookmarks.added[0].updated_at) == (_NOW, _NOW)
    assert bookmarks.links == [(7, 11, [22, 21])]
    assert clock.calls == publisher.count == session.commits == 1
    assert session.rollbacks == 0
    assert session.calls == [
        "bookmark.add",
        "session.add",
        "flush",
        "tag.find:async",
        "tag.find:python",
        "savepoint",
        "savepoint.enter",
        "tag.add:python",
        "session.add",
        "flush",
        "savepoint.release",
        "bookmark.links",
        "flush",
        "bookmark.get",
        "commit",
        "publish",
    ]


def test_reads_are_transaction_time_and_publisher_inert_and_list_is_fixed_first_twenty() -> None:
    session = FakeSession()
    snapshots = [_snapshot(id=index, title=f"bookmark-{index}") for index in range(1, 24)]
    bookmarks = FakeBookmarks(session, snapshot=snapshots[0])
    bookmarks.list_result = snapshots
    clock = FakeClock()
    publisher = FakePublisher()
    service = _service(session, bookmarks=bookmarks, clock=clock, publisher=publisher)

    assert service.get(7, 1).id == 1
    result = service.list(7)

    assert [item.id for item in result.items] == list(range(1, 21))
    assert (result.total, result.page, result.page_size) == (23, 1, 20)
    assert session.commits == session.rollbacks == clock.calls == publisher.count == 0
    assert session.calls == ["bookmark.get", "bookmark.list"]


@pytest.mark.parametrize(
    "patch",
    [BookmarkPatch(), BookmarkPatch(title="Bookmark"), BookmarkPatch(tags=["python"])],
)
def test_noop_patch_does_no_clock_dml_commit_or_publication(patch: BookmarkPatch) -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    clock = FakeClock(_LATER)
    publisher = FakePublisher()

    response = _service(session, bookmarks=bookmarks, clock=clock, publisher=publisher).patch(
        7, 11, patch
    )

    assert response.updated_at == _NOW
    assert session.calls == ["bookmark.get"]
    assert session.commits == session.rollbacks == clock.calls == publisher.count == 0


def test_material_patch_updates_scalars_resolves_changed_tags_and_publishes_post_commit() -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    tags = FakeTags(session, existing={"async": Tag(id=22, name="async")})
    publisher = FakePublisher(calls=session.calls)
    service = _service(
        session,
        bookmarks=bookmarks,
        tags=tags,
        clock=FakeClock(_LATER),
        publisher=publisher,
    )

    response = service.patch(7, 11, BookmarkPatch(title="Changed", tags=["async"]))

    assert response.title == "Bookmark"  # The fake repository controls the reloaded snapshot.
    assert bookmarks.updates == [(7, 11, {"updated_at": _LATER, "title": "Changed"})]
    assert bookmarks.links == [(7, 11, [22])]
    assert tags.lookups == ["async"]
    assert session.calls[-3:] == ["bookmark.get", "commit", "publish"]
    assert session.commits == publisher.count == 1


def test_scalar_only_patch_skips_tag_resolution_and_link_replacement() -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    tags = FakeTags(session)

    _service(session, bookmarks=bookmarks, tags=tags, clock=FakeClock(_LATER)).patch(
        7, 11, BookmarkPatch(title="Changed")
    )

    assert tags.lookups == []
    assert bookmarks.links == []
    assert session.commits == 1


@pytest.mark.parametrize("failure_at", ["bookmark.add", "flush", "bookmark.links", "commit"])
def test_create_rolls_back_exactly_once_and_preserves_precommit_failure(
    failure_at: str,
) -> None:
    session = FakeSession(failure_at=failure_at if failure_at in {"flush", "commit"} else None)
    bookmarks = FakeBookmarks(session)
    bookmarks.fail_at = failure_at if failure_at != "flush" else None
    publisher = FakePublisher()

    with pytest.raises(RuntimeError, match="failed") as raised:
        _service(session, bookmarks=bookmarks, publisher=publisher).create(
            7, _create(tags=["python"])
        )

    assert session.rollbacks == 1
    assert session.commits == (1 if failure_at == "commit" else 0)
    assert publisher.count == 0
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("failure_at", ["bookmark.update", "bookmark.links", "flush", "commit"])
def test_material_patch_rolls_back_exactly_once_without_publishing(failure_at: str) -> None:
    session = FakeSession(failure_at=failure_at if failure_at in {"flush", "commit"} else None)
    bookmarks = FakeBookmarks(session)
    bookmarks.fail_at = failure_at if failure_at != "flush" else None
    publisher = FakePublisher()

    with pytest.raises(RuntimeError, match="failed"):
        _service(session, bookmarks=bookmarks, publisher=publisher).patch(
            7, 11, BookmarkPatch(title="Changed", tags=["async"])
        )

    assert session.rollbacks == 1
    assert session.commits == (1 if failure_at == "commit" else 0)
    assert publisher.count == 0


def test_delete_is_owner_scoped_transactional_and_publisher_failure_does_not_roll_back() -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    publisher = FakePublisher(failure=RuntimeError("publisher failed"), calls=session.calls)

    with pytest.raises(RuntimeError, match="publisher failed"):
        _service(session, bookmarks=bookmarks, publisher=publisher).delete(7, 11)

    assert bookmarks.deleted == [(7, 11)]
    assert session.calls == ["bookmark.delete", "flush", "commit", "publish"]
    assert session.commits == publisher.count == 1
    assert session.rollbacks == 0


@pytest.mark.parametrize("operation", ["create", "patch"])
def test_publisher_failure_follows_each_other_durable_mutation_without_rollback(
    operation: str,
) -> None:
    session = FakeSession()
    publisher = FakePublisher(failure=RuntimeError("publisher failed"), calls=session.calls)
    service = _service(session, clock=FakeClock(_LATER), publisher=publisher)

    with pytest.raises(RuntimeError, match="publisher failed"):
        if operation == "create":
            service.create(7, _create(tags=["python"]))
        else:
            service.patch(7, 11, BookmarkPatch(title="Changed"))

    assert session.commits == publisher.count == 1
    assert session.rollbacks == 0


@pytest.mark.parametrize("failure_at", ["bookmark.delete", "flush", "commit"])
def test_delete_precommit_and_commit_failures_roll_back_once_without_publishing(
    failure_at: str,
) -> None:
    session = FakeSession(failure_at=failure_at if failure_at in {"flush", "commit"} else None)
    bookmarks = FakeBookmarks(session)
    bookmarks.fail_at = failure_at if failure_at == "bookmark.delete" else None
    publisher = FakePublisher()

    with pytest.raises(RuntimeError, match="failed"):
        _service(session, bookmarks=bookmarks, publisher=publisher).delete(7, 11)

    assert session.rollbacks == 1
    assert session.commits == (1 if failure_at == "commit" else 0)
    assert publisher.count == 0


@pytest.mark.parametrize("operation", ["get", "patch", "delete"])
def test_missing_or_other_user_resources_use_one_generic_not_found(operation: str) -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    bookmarks.present = False
    service = _service(session, bookmarks=bookmarks)

    with pytest.raises(NotFoundError) as raised:
        if operation == "get":
            service.get(8, 11)
        elif operation == "patch":
            service.patch(8, 11, BookmarkPatch(title="Changed"))
        else:
            service.delete(8, 11)

    assert (raised.value.code, raised.value.message) == ("not_found", "Resource not found.")
    if operation == "delete":
        assert session.rollbacks == 1
    else:
        assert session.rollbacks == 0


@pytest.mark.parametrize("operation", ["create", "update", "links"])
def test_owner_scoped_mutation_false_results_become_not_found_and_roll_back(operation: str) -> None:
    session = FakeSession()
    bookmarks = FakeBookmarks(session)
    if operation == "create":
        bookmarks.link_result = False

        def invoke() -> None:
            _service(session, bookmarks=bookmarks).create(7, _create(tags=["python"]))

    elif operation == "update":
        bookmarks.update_result = False

        def invoke() -> None:
            _service(session, bookmarks=bookmarks).patch(7, 11, BookmarkPatch(title="Changed"))

    else:
        bookmarks.link_result = False

        def invoke() -> None:
            _service(session, bookmarks=bookmarks).patch(7, 11, BookmarkPatch(tags=["async"]))

    with pytest.raises(NotFoundError):
        invoke()

    assert session.rollbacks == 1


def test_tag_race_recovers_only_the_exact_native_sqlite_unique_error() -> None:
    session = FakeSession()
    tags = FakeTags(session)
    winner = Tag(id=44, name="python")
    original_flush = session.flush

    def race_flush() -> None:
        original_flush()
        tags.race_winner = winner
        raise IntegrityError(
            "INSERT INTO tags", {}, NativeTagUniqueError("UNIQUE constraint failed: tags.name")
        )

    session.flush = race_flush  # type: ignore[method-assign]

    resolved = _service(session, tags=tags)._resolve_tag_ids(("python",))  # type: ignore[attr-defined]

    assert resolved == [44]
    assert session.rollbacks == 0
    assert session.calls[-2:] == ["savepoint.rollback", "tag.find:python"]


def test_tag_insert_failure_rolls_back_the_outer_create_once_without_publishing() -> None:
    session = FakeSession()
    tags = FakeTags(session)
    tags.fail_at = "tag.add"
    publisher = FakePublisher()

    with pytest.raises(RuntimeError, match="tag add failed"):
        _service(session, tags=tags, publisher=publisher).create(7, _create(tags=["python"]))

    assert session.rollbacks == 1
    assert publisher.count == 0


@pytest.mark.parametrize(
    "original",
    [
        NativeTagUniqueError("UNIQUE constraint failed: tags.name"),
        NativeTagUniqueError("UNIQUE constraint failed: tags.name, tags.id"),
        NativeTagUniqueError(
            "UNIQUE constraint failed: bookmark_tags.bookmark_id, bookmark_tags.tag_id"
        ),
        sqlite3.IntegrityError("UNIQUE constraint failed: tags.name"),
        RuntimeError("duplicate"),
    ],
)
def test_tag_unique_classifier_fails_closed_for_forged_or_other_integrity_errors(
    original: BaseException,
) -> None:
    error = IntegrityError("INSERT INTO tags", {}, original)

    expected = isinstance(original, NativeTagUniqueError) and str(original) == _TAG_UNIQUE_MESSAGE
    assert _is_tag_unique_conflict(error) is expected


def test_tag_race_without_a_reloaded_winner_and_invalid_persistence_ids_fail_loudly() -> None:
    session = FakeSession()
    tags = FakeTags(session)
    original_flush = session.flush

    def race_flush() -> None:
        original_flush()
        raise IntegrityError("INSERT INTO tags", {}, NativeTagUniqueError(_TAG_UNIQUE_MESSAGE))

    session.flush = race_flush  # type: ignore[method-assign]
    service = _service(session, tags=tags)

    with pytest.raises(RuntimeError, match="persisted winner"):
        service._resolve_tag_ids(("python",))  # type: ignore[attr-defined]

    broken_session = FakeSession()
    broken_tags = FakeTags(broken_session, existing={"python": Tag(id=0, name="python")})
    with pytest.raises(RuntimeError, match="valid identifier"):
        _service(broken_session, tags=broken_tags)._resolve_tag_ids(("python",))  # type: ignore[attr-defined]


def test_unrecognized_tag_integrity_and_missing_bookmark_ids_are_not_silently_repaired() -> None:
    session = FakeSession()
    tags = FakeTags(session)
    original_flush = session.flush

    def unrelated_flush() -> None:
        original_flush()
        raise IntegrityError("INSERT INTO tags", {}, RuntimeError("not a tag uniqueness race"))

    session.flush = unrelated_flush  # type: ignore[method-assign]

    with pytest.raises(IntegrityError):
        _service(session, tags=tags)._resolve_tag_ids(("python",))  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="valid identifier"):
        _bookmark_id(
            Bookmark(
                id=None,
                url="https://example.test",
                title="title",
                user_id=7,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
