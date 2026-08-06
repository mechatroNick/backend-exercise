"""Real Alembic SQLite evidence for the Track 02 authentication service."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import cast

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.models import User
from app.auth.passwords import PasswordHasher
from app.auth.repository import UserRepository
from app.auth.security import AccessTokenCodec
from app.auth.service import AuthService, _identity_conflict_from_integrity_error
from app.core.errors import IdentityConflictError

_PASSWORD = "p" * 15
_SECRET = "t" * 48
_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_NOW_TEXT = _NOW.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class FixedClock:
    def now(self) -> datetime:
        return _NOW


class FastHasher:
    def hash(self, _password: object) -> str:
        return "$argon2id$test-hash"

    def verify_or_dummy(self, _password: object, _password_hash: str | None) -> bool:
        return True


class FastTokenCodec:
    def issue(self, _subject: str) -> str:
        return "opaque-test-token"


def _service(session: Session, *, fast: bool = False) -> AuthService:
    clock = FixedClock()
    return AuthService(
        session=session,
        repository=UserRepository(session),
        password_hasher=cast("PasswordHasher", FastHasher()) if fast else PasswordHasher(),
        token_codec=(
            cast(AccessTokenCodec, FastTokenCodec())
            if fast
            else AccessTokenCodec(secret=SecretStr(_SECRET), ttl=timedelta(minutes=30), clock=clock)
        ),
        clock=clock,
    )


def test_repository_queries_canonical_email_and_identifier_without_transaction_ownership(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        repository = UserRepository(session)
        user = User(
            username="alice",
            email="alice@example.com",
            password_hash="$argon2id$test-hash",
            created_at=_NOW,
        )
        repository.add(user)
        session.commit()

        assert user.id is not None
        assert repository.find_by_canonical_email("alice@example.com") == user
        assert repository.find_by_canonical_email("ALICE@example.com") is None
        assert repository.find_by_id(user.id) == user
        assert repository.find_by_id(user.id + 1) is None
    finally:
        session.close()


def test_registration_persists_canonical_identity_argon2_hash_and_verifiable_token(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        service = _service(session)
        response = service.register(
            username=" Alice ", email=" Alice@Example.com ", password=_PASSWORD
        )
        stored = session.exec(select(User)).one()

        assert response.user.model_dump() == {
            "id": stored.id,
            "username": "alice",
            "email": "alice@example.com",
        }
        assert stored.password_hash.startswith("$argon2id$")
        assert stored.password_hash != _PASSWORD
        assert PasswordHasher().verify(_PASSWORD, stored.password_hash) is True
        assert service._token_codec.verify(response.token) == str(stored.id)  # type: ignore[attr-defined]
    finally:
        session.close()


@pytest.mark.parametrize(
    ("existing_username", "existing_email", "new_username", "new_email"),
    [
        ("alice", "alice@example.com", " Alice ", "other@example.com"),
        ("alice", "alice@example.com", "other", " Alice@Example.com "),
    ],
)
def test_real_sqlite_unique_code_2067_becomes_generic_conflict_and_session_recovers(
    migrated_engine: Engine,
    existing_username: str,
    existing_email: str,
    new_username: str,
    new_email: str,
) -> None:
    session = Session(migrated_engine)
    try:
        service = _service(session, fast=True)
        service.register(username=existing_username, email=existing_email, password=_PASSWORD)

        with pytest.raises(IdentityConflictError) as conflict:
            service.register(username=new_username, email=new_email, password=_PASSWORD)

        assert (conflict.value.code, conflict.value.message) == (
            "identity_conflict",
            "Username or email is already registered.",
        )
        assert isinstance(conflict.value.__cause__, IntegrityError)
        original = conflict.value.__cause__.orig
        assert isinstance(original, sqlite3.IntegrityError)
        assert original.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE
        follow_up = service.register(
            username="follow-up", email="follow-up@example.com", password=_PASSWORD
        )
        assert follow_up.user.id > 0
        assert len(session.exec(select(User)).all()) == 2
    finally:
        session.close()


def test_unrelated_real_check_tag_and_composite_integrity_errors_are_never_identity_conflicts(
    migrated_engine: Engine,
) -> None:
    session = Session(migrated_engine)
    try:
        session.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES ('check-user', 'check@example.test', '', :created_at)"
            ),
            {"created_at": _NOW_TEXT},
        )
    except IntegrityError as error:
        session.rollback()
        assert _identity_conflict_from_integrity_error(error) is None
    else:
        pytest.fail("expected a SQLite CHECK integrity error")
    try:
        session.execute(text("INSERT INTO tags (name) VALUES ('python')"))
        session.commit()
        session.execute(text("INSERT INTO tags (name) VALUES ('python')"))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        assert _identity_conflict_from_integrity_error(error) is None
    else:
        pytest.fail("expected a SQLite tag uniqueness error")
    try:
        user_id = session.execute(
            text(
                "INSERT INTO users (username, email, password_hash, created_at) "
                "VALUES ('composite-user', 'composite@example.com', 'hash', :created_at)"
            ),
            {"created_at": _NOW_TEXT},
        ).lastrowid
        bookmark_id = session.execute(
            text(
                "INSERT INTO bookmarks (url, title, description, user_id, created_at, updated_at) "
                "VALUES ('https://example.com/bookmark', 'bookmark', NULL, :user_id, "
                ":created_at, :created_at)"
            ),
            {"user_id": user_id, "created_at": _NOW_TEXT},
        ).lastrowid
        tag_id = session.execute(text("INSERT INTO tags (name) VALUES ('async')")).lastrowid
        session.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": bookmark_id, "tag_id": tag_id},
        )
        session.commit()
        session.execute(
            text("INSERT INTO bookmark_tags (bookmark_id, tag_id) VALUES (:bookmark_id, :tag_id)"),
            {"bookmark_id": bookmark_id, "tag_id": tag_id},
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        assert _identity_conflict_from_integrity_error(error) is None
    else:
        pytest.fail("expected a SQLite composite primary-key integrity error")
    finally:
        session.close()


def test_two_session_duplicate_race_has_one_success_one_conflict_and_one_row(
    migrated_engine: Engine,
) -> None:
    start = Barrier(2)

    def register_in_own_session() -> str:
        session = Session(migrated_engine)
        try:
            start.wait(timeout=5)
            _service(session, fast=True).register(
                username="race-user", email="race@example.com", password=_PASSWORD
            )
            return "success"
        except IdentityConflictError:
            return "conflict"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(register_in_own_session) for _ in range(2)]
        outcomes = [future.result(timeout=10) for future in futures]

    with Session(migrated_engine) as session:
        assert sorted(outcomes) == ["conflict", "success"]
        assert len(session.exec(select(User)).all()) == 1
