"""Focused deterministic tests for authentication service failure ownership."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.auth.models import User
from app.auth.passwords import PasswordHasher
from app.auth.repository import UserRepository
from app.auth.security import AccessTokenCodec
from app.auth.service import AuthService, _identity_conflict_from_integrity_error
from app.core.errors import AuthenticationError

_PASSWORD = "p" * 15
_NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self) -> None:
        self.calls = 0

    def now(self) -> datetime:
        self.calls += 1
        return _NOW


class FakeSession:
    def __init__(
        self,
        *,
        failure_at: str | None = None,
        failure: Exception | None = None,
        assigned_id: int | None = 7,
    ) -> None:
        self.failure_at = failure_at
        self.failure = failure
        self.assigned_id = assigned_id
        self.added: list[User] = []
        self.flushes = 0
        self.commits = 0
        self.rollbacks = 0

    def add(self, user: User) -> None:
        if self.failure_at == "add":
            raise RuntimeError("add failed")
        self.added.append(user)

    def flush(self) -> None:
        self.flushes += 1
        if self.failure is not None:
            raise self.failure
        if self.failure_at == "flush":
            raise RuntimeError("flush failed")
        self.added[-1].id = self.assigned_id

    def commit(self) -> None:
        self.commits += 1
        if self.failure_at == "commit":
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeRepository:
    def __init__(self, session: FakeSession, *, user: User | None = None) -> None:
        self.session = session
        self.user = user
        self.emails: list[str] = []

    def add(self, user: User) -> None:
        self.session.add(user)

    def find_by_canonical_email(self, canonical_email: str) -> User | None:
        self.emails.append(canonical_email)
        return self.user

    def find_by_id(self, _user_id: int) -> User | None:
        return self.user


class FakeHasher:
    def __init__(self, *, verified: bool = True, verify_failure: Exception | None = None) -> None:
        self.verified = verified
        self.verify_failure = verify_failure
        self.hash_inputs: list[object] = []
        self.verify_inputs: list[tuple[object, str | None]] = []

    def hash(self, password: object) -> str:
        self.hash_inputs.append(password)
        return "$argon2id$test-hash"

    def verify_or_dummy(self, password: object, password_hash: str | None) -> bool:
        self.verify_inputs.append((password, password_hash))
        if self.verify_failure is not None:
            raise self.verify_failure
        return self.verified


class FakeTokenCodec:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.subjects: list[str] = []

    def issue(self, subject: str) -> str:
        self.subjects.append(subject)
        if self.failure is not None:
            raise self.failure
        return "opaque-test-token"


def _service(
    session: FakeSession,
    *,
    repository: FakeRepository | None = None,
    hasher: FakeHasher | None = None,
    codec: FakeTokenCodec | None = None,
    clock: FixedClock | None = None,
) -> AuthService:
    return AuthService(
        session=cast(Session, session),
        repository=cast(UserRepository, repository or FakeRepository(session)),
        password_hasher=cast("PasswordHasher", hasher or FakeHasher()),
        token_codec=cast(AccessTokenCodec, codec or FakeTokenCodec()),
        clock=clock or FixedClock(),
    )


def test_registration_canonicalizes_hashes_commits_and_uses_one_created_at_instant() -> None:
    session = FakeSession()
    clock = FixedClock()
    hasher = FakeHasher()
    codec = FakeTokenCodec()

    response = _service(session, hasher=hasher, codec=codec, clock=clock).register(
        username=" Alice ", email=" Alice@Example.com ", password=_PASSWORD
    )

    assert response.model_dump(mode="json") == {
        "user": {"id": 7, "username": "alice", "email": "alice@example.com"},
        "token": "opaque-test-token",
    }
    assert session.commits == 1
    assert session.rollbacks == 0
    assert session.added[0].created_at == _NOW
    assert hasher.hash_inputs == [_PASSWORD]
    assert codec.subjects == ["7"]
    assert clock.calls == 1


@pytest.mark.parametrize("failure_at", ["add", "flush", "commit"])
def test_registration_rolls_back_before_propagating_persistence_failures(failure_at: str) -> None:
    session = FakeSession(failure_at=failure_at)

    with pytest.raises(RuntimeError):
        _service(session).register(username="alice", email="alice@example.com", password=_PASSWORD)

    assert session.rollbacks == 1


def test_registration_rolls_back_before_propagating_token_failure() -> None:
    session = FakeSession()

    with pytest.raises(RuntimeError):
        _service(session, codec=FakeTokenCodec(failure=RuntimeError("token failed"))).register(
            username="alice", email="alice@example.com", password=_PASSWORD
        )

    assert session.rollbacks == 1
    assert session.commits == 0


def test_registration_rejects_an_unassigned_persisted_identifier_after_rollback() -> None:
    session = FakeSession(assigned_id=None)

    with pytest.raises(RuntimeError, match="valid identifier"):
        _service(session).register(username="alice", email="alice@example.com", password=_PASSWORD)

    assert session.rollbacks == 1


def test_registration_reraises_unrecognized_integrity_errors_after_rollback() -> None:
    original = sqlite3.IntegrityError("UNIQUE constraint failed: tags.name")
    error = IntegrityError("INSERT INTO tags ...", {}, original)
    session = FakeSession(failure=error)

    with pytest.raises(IntegrityError) as raised:
        _service(session).register(username="alice", email="alice@example.com", password=_PASSWORD)

    assert raised.value is error
    assert session.rollbacks == 1


def test_login_has_one_verify_for_unknown_and_bad_password_with_identical_expected_errors() -> None:
    unknown_hasher = FakeHasher(verified=False)
    unknown_repository = FakeRepository(FakeSession())
    bad_hasher = FakeHasher(verified=False)
    bad_repository = FakeRepository(
        FakeSession(),
        user=User(
            id=7,
            username="alice",
            email="alice@example.com",
            password_hash="$argon2id$stored-hash",
            created_at=_NOW,
        ),
    )

    with pytest.raises(AuthenticationError) as unknown_error:
        _service(
            unknown_repository.session, repository=unknown_repository, hasher=unknown_hasher
        ).login(email="alice@example.com", password=_PASSWORD)
    with pytest.raises(AuthenticationError) as bad_error:
        _service(bad_repository.session, repository=bad_repository, hasher=bad_hasher).login(
            email="alice@example.com", password=_PASSWORD
        )

    assert (unknown_error.value.code, unknown_error.value.message, unknown_error.value.details) == (
        bad_error.value.code,
        bad_error.value.message,
        bad_error.value.details,
    )
    assert len(unknown_hasher.verify_inputs) == len(bad_hasher.verify_inputs) == 1
    assert unknown_hasher.verify_inputs[0][1] is None
    assert bad_hasher.verify_inputs[0][1] is not None


def test_login_returns_exact_shape_without_mutating_a_session() -> None:
    session = FakeSession()
    repository = FakeRepository(
        session,
        user=User(
            id=7,
            username="alice",
            email="alice@example.com",
            password_hash="$argon2id$stored-hash",
            created_at=_NOW,
        ),
    )

    response = _service(session, repository=repository).login(
        email=" Alice@Example.com ", password=_PASSWORD
    )

    assert response.user.model_dump() == {
        "id": 7,
        "username": "alice",
        "email": "alice@example.com",
    }
    assert session.commits == session.rollbacks == 0


def test_malformed_hash_or_backend_failure_remains_unexpected() -> None:
    session = FakeSession()
    repository = FakeRepository(
        session,
        user=User(
            id=7,
            username="alice",
            email="alice@example.com",
            password_hash="$argon2id$stored-hash",
            created_at=_NOW,
        ),
    )

    with pytest.raises(RuntimeError, match="verification backend failed"):
        _service(
            session,
            repository=repository,
            hasher=FakeHasher(verify_failure=RuntimeError("verification backend failed")),
        ).login(email="alice@example.com", password=_PASSWORD)


def test_login_rejects_a_corrupted_persisted_identifier_as_unexpected() -> None:
    session = FakeSession()
    repository = FakeRepository(
        session,
        user=User(
            id=None,
            username="alice",
            email="alice@example.com",
            password_hash="$argon2id$stored-hash",
            created_at=_NOW,
        ),
    )

    with pytest.raises(RuntimeError, match="invalid identifier"):
        _service(session, repository=repository).login(
            email="alice@example.com", password=_PASSWORD
        )


def test_integrity_classifier_fails_closed_for_forged_and_other_driver_errors() -> None:
    forged = IntegrityError(
        "INSERT INTO users ...",
        {},
        sqlite3.IntegrityError("UNIQUE constraint failed: users.username"),
    )
    other_driver = IntegrityError("INSERT INTO users ...", {}, RuntimeError("duplicate"))

    assert _identity_conflict_from_integrity_error(forged) is None
    assert _identity_conflict_from_integrity_error(other_driver) is None


def test_integrity_classifier_rejects_other_table_and_composite_messages() -> None:
    class NativeUniqueError(sqlite3.IntegrityError):
        sqlite_errorcode = sqlite3.SQLITE_CONSTRAINT_UNIQUE

    for message in (
        "UNIQUE constraint failed: tags.name",
        "UNIQUE constraint failed: bookmark_tags.bookmark_id, bookmark_tags.tag_id",
    ):
        error = IntegrityError("INSERT ...", {}, NativeUniqueError(message))
        assert _identity_conflict_from_integrity_error(error) is None
