"""Safe, deterministic development seed command for an already-migrated database.

Run with an explicit target only::

    DATABASE_URL=sqlite:////absolute/path/bookmarks.sqlite3 uv run python -m app.seed

The module deliberately never creates a schema, deletes rows, or changes an
existing seed record.  It is also callable with injected settings/session
factories for integration tests and other local tooling.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, Table
from sqlmodel import Session, select

from app.auth.models import User
from app.auth.passwords import PasswordHasher
from app.auth.repository import UserRepository
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.repository import BookmarkRepository, TagRepository
from app.core.config import Settings
from app.core.logging import configure_logging, log_event, log_exception
from app.db.engine import SessionFactory, create_database_engine, create_session_factory

# ``python -m app.seed`` assigns this module ``__main__``; keep its application
# logger beneath ``app`` so the configured application handler receives events.
_LOGGER = logging.getLogger("app.seed")
_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
_SEED_PASSWORD: Final = "fictional-seed-password-only"


class SeedError(RuntimeError):
    """Base class for safe, command-owned seed failures."""


class SeedSafetyError(SeedError):
    """The command target or migration state is not safe to seed."""


class SeedConflictError(SeedError):
    """An existing row has a seed identity but does not match the fixed fixture."""


@dataclass(frozen=True, slots=True)
class SeedBookmark:
    """One fixed, non-sensitive bookmark fixture."""

    url: str
    title: str
    description: str | None
    tags: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SeedSummary:
    """Content-free result counts suitable for structured logging."""

    users_created: int = 0
    bookmarks_created: int = 0
    tags_created: int = 0
    existing_records: int = 0

    def as_context(self) -> dict[str, int]:
        """Return low-cardinality totals whose field names need no content redaction."""
        return {
            "created_records": self.users_created + self.bookmarks_created + self.tags_created,
            "unchanged_seed_records": self.existing_records,
        }


_SEED_USER: Final = ("fictional-reader", "fictional-reader@example.test")
_SEED_BOOKMARKS: Final = (
    SeedBookmark(
        url="https://example.test/field-notes",
        title="Field Notes",
        description="A fictional reading list for local development.",
        tags=("fiction", "reading"),
        created_at=datetime(2025, 1, 15, 9, 30, tzinfo=UTC),
    ),
    SeedBookmark(
        url="https://example.test/sky-atlas",
        title="Sky Atlas",
        description="A fictional reference for local development.",
        tags=("fiction", "reference"),
        created_at=datetime(2025, 2, 20, 14, 0, tzinfo=UTC),
    ),
)
_BOOKMARK_TAGS = cast(Table, BookmarkTag.__table__)  # type: ignore[attr-defined]
_TAGS = cast(Table, Tag.__table__)  # type: ignore[attr-defined]


def _alembic_heads() -> frozenset[str]:
    config = Config(str(_REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_REPOSITORY_ROOT / "alembic"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def verify_migrated_schema(engine: Engine) -> None:
    """Require the database to be at this checkout's Alembic head before writing."""
    expected_heads = _alembic_heads()
    with engine.connect() as connection:
        current_heads = frozenset(MigrationContext.configure(connection).get_current_heads())
    if current_heads != expected_heads:
        raise SeedSafetyError("database schema is not at the required Alembic revision")


def _required_id(value: int | None, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SeedError(f"persisted {name} did not receive a valid identifier")
    return value


def _seed_user(session: Session, summary: SeedSummary) -> tuple[User, SeedSummary]:
    username, email = _SEED_USER
    users = UserRepository(session)
    by_username = session.exec(select(User).where(User.username == username)).one_or_none()
    by_email = users.find_by_canonical_email(email)
    if by_username is not None or by_email is not None:
        if by_username is None or by_email is None or by_username.id != by_email.id:
            raise SeedConflictError("an existing user conflicts with the seed identity")
        return by_username, SeedSummary(
            users_created=summary.users_created,
            bookmarks_created=summary.bookmarks_created,
            tags_created=summary.tags_created,
            existing_records=summary.existing_records + 1,
        )

    user = User(
        username=username,
        email=email,
        password_hash=PasswordHasher().hash(_SEED_PASSWORD),
        created_at=_SEED_BOOKMARKS[0].created_at,
    )
    users.add(user)
    session.flush()
    _required_id(user.id, "user")
    return user, SeedSummary(
        users_created=summary.users_created + 1,
        bookmarks_created=summary.bookmarks_created,
        tags_created=summary.tags_created,
        existing_records=summary.existing_records,
    )


def _resolve_tags(
    session: Session, names: tuple[str, ...], summary: SeedSummary
) -> tuple[list[int], SeedSummary]:
    tags = TagRepository(session)
    tag_ids: list[int] = []
    result = summary
    for name in names:
        tag = tags.find_by_name(name)
        if tag is None:
            tag = Tag(name=name)
            tags.add(tag)
            session.flush()
            result = SeedSummary(
                users_created=result.users_created,
                bookmarks_created=result.bookmarks_created,
                tags_created=result.tags_created + 1,
                existing_records=result.existing_records,
            )
        else:
            # Global tags can belong to unrelated data; reusing one is intentionally
            # not counted as an unchanged seed record.
            pass
        tag_ids.append(_required_id(tag.id, "tag"))
    return tag_ids, result


def _existing_tag_names(session: Session, bookmark_id: int) -> tuple[str, ...]:
    statement = (
        select(_TAGS.c.name)
        .select_from(_BOOKMARK_TAGS)
        .join(_TAGS, _BOOKMARK_TAGS.c.tag_id == _TAGS.c.id)
        .where(_BOOKMARK_TAGS.c.bookmark_id == bookmark_id)
        .order_by(_TAGS.c.name)
    )
    return tuple(session.exec(statement).all())


def _seed_bookmark(
    session: Session, user_id: int, fixture: SeedBookmark, summary: SeedSummary
) -> SeedSummary:
    existing = session.exec(
        select(Bookmark).where(Bookmark.user_id == user_id, Bookmark.url == fixture.url)
    ).all()
    if len(existing) > 1:
        raise SeedConflictError("multiple existing bookmarks conflict with the seed identity")
    if existing:
        bookmark = existing[0]
        if (
            bookmark.title != fixture.title
            or bookmark.description != fixture.description
            or bookmark.created_at != fixture.created_at
            or bookmark.updated_at != fixture.created_at
            or _existing_tag_names(session, _required_id(bookmark.id, "bookmark")) != fixture.tags
        ):
            raise SeedConflictError("an existing bookmark conflicts with the seed fixture")
        return SeedSummary(
            users_created=summary.users_created,
            bookmarks_created=summary.bookmarks_created,
            tags_created=summary.tags_created,
            existing_records=summary.existing_records + 1,
        )

    bookmark = Bookmark(
        url=fixture.url,
        title=fixture.title,
        description=fixture.description,
        user_id=user_id,
        created_at=fixture.created_at,
        updated_at=fixture.created_at,
    )
    BookmarkRepository(session).add(bookmark)
    session.flush()
    bookmark_id = _required_id(bookmark.id, "bookmark")
    tag_ids, result = _resolve_tags(session, fixture.tags, summary)
    session.add_all([BookmarkTag(bookmark_id=bookmark_id, tag_id=tag_id) for tag_id in tag_ids])
    session.flush()
    return SeedSummary(
        users_created=result.users_created,
        bookmarks_created=result.bookmarks_created + 1,
        tags_created=result.tags_created,
        existing_records=result.existing_records,
    )


def seed_database(engine: Engine, session_factory: SessionFactory | None = None) -> SeedSummary:
    """Apply the fixed fixture once, atomically, without changing existing seed records."""
    verify_migrated_schema(engine)
    factory = session_factory or create_session_factory(engine)
    session = factory()
    try:
        user, summary = _seed_user(session, SeedSummary())
        user_id = _required_id(user.id, "user")
        for fixture in _SEED_BOOKMARKS:
            summary = _seed_bookmark(session, user_id, fixture, summary)
        session.commit()
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _settings_from_explicit_environment(environ: Mapping[str, str]) -> Settings:
    """Reject absent or blank targets instead of accepting Settings' application default."""
    database_url = environ.get("DATABASE_URL")
    if not database_url or not database_url.strip():
        raise SeedSafetyError("DATABASE_URL must be explicitly set for seed execution")
    requested_environment = environ.get("APP_ENV")
    if requested_environment is not None and requested_environment not in {
        "development",
        "test",
        "production",
    }:
        raise SeedSafetyError("APP_ENV is invalid for seed execution")
    if requested_environment == "production":
        raise SeedSafetyError("seed execution is not allowed in production")
    isolated_values = Settings.model_construct().model_dump()
    isolated_values.update(
        database_url=database_url,
        app_env=requested_environment or "development",
    )
    settings = Settings.model_validate(isolated_values)
    return settings


def main(environ: Mapping[str, str] | None = None) -> int:
    """Run the command boundary and return a shell-safe status code."""
    environment = os.environ if environ is None else environ
    try:
        settings = _settings_from_explicit_environment(environment)
    except Exception as error:
        # Explicitly override a malformed environment value solely to configure
        # the safe log handler; this path never creates an engine or schema.
        configure_logging(Settings(database_url="sqlite:///:memory:"))
        log_event(
            _LOGGER,
            logging.ERROR,
            "seed.rejected",
            outcome="failure",
            message="seed execution was rejected",
            context={"reason": "invalid_or_missing_target"},
            component="seed",
        )
        del error
        return 2

    configure_logging(settings)
    engine = create_database_engine(settings)
    try:
        summary = seed_database(engine)
    except SeedError:
        log_event(
            _LOGGER,
            logging.ERROR,
            "seed.rejected",
            outcome="failure",
            message="seed execution was rejected",
            context={"reason": "safety_or_conflict"},
            component="seed",
        )
        return 2
    except Exception as error:
        log_exception(
            _LOGGER,
            "seed.failed",
            exception=error,
            message="seed execution failed",
            component="seed",
        )
        return 1
    finally:
        engine.dispose()

    log_event(
        _LOGGER,
        logging.INFO,
        "seed.completed",
        outcome="success",
        message="seed execution completed",
        context=summary.as_context(),
        component="seed",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
