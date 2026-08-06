"""Transport-independent registration and login application service."""

from __future__ import annotations

import sqlite3

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.auth.identity import canonicalize_email, canonicalize_username
from app.auth.models import User
from app.auth.passwords import PasswordHasher
from app.auth.repository import UserRepository
from app.auth.schemas import AuthResponse, PublicUser
from app.auth.security import AccessTokenCodec
from app.core.clock import Clock, normalize_utc
from app.core.errors import AuthenticationError, IdentityConflictError

_UNIQUE_USER_MESSAGES = frozenset(
    {
        "UNIQUE constraint failed: users.username",
        "UNIQUE constraint failed: users.email",
    }
)


def _identity_conflict_from_integrity_error(error: IntegrityError) -> IdentityConflictError | None:
    """Translate only exact native SQLite user-identity uniqueness failures."""
    original = error.orig
    if (
        isinstance(original, sqlite3.IntegrityError)
        and getattr(original, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
        and str(original) in _UNIQUE_USER_MESSAGES
    ):
        return IdentityConflictError()
    return None


class AuthService:
    """Own authentication use cases and the registration transaction boundary."""

    def __init__(
        self,
        *,
        session: Session,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_codec: AccessTokenCodec,
        clock: Clock,
    ) -> None:
        self._session = session
        self._repository = repository
        self._password_hasher = password_hasher
        self._token_codec = token_codec
        self._clock = clock

    def register(self, *, username: object, email: object, password: object) -> AuthResponse:
        """Persist a canonical identity and issue its access token atomically."""
        canonical_username = canonicalize_username(username)
        canonical_email = canonicalize_email(email)
        password_hash = self._password_hasher.hash(password)
        created_at = normalize_utc(self._clock.now())
        user = User(
            username=canonical_username,
            email=canonical_email,
            password_hash=password_hash,
            created_at=created_at,
        )
        try:
            self._repository.add(user)
            self._session.flush()
            if not isinstance(user.id, int) or isinstance(user.id, bool) or user.id <= 0:
                raise RuntimeError("persisted user did not receive a valid identifier")
            token = self._token_codec.issue(str(_user_id(user)))
            self._session.commit()
        except Exception as error:
            self._session.rollback()
            if isinstance(error, IntegrityError):
                identity_conflict = _identity_conflict_from_integrity_error(error)
                if identity_conflict is not None:
                    raise identity_conflict from error
            raise
        return _auth_response(user, token)

    def login(self, *, email: object, password: object) -> AuthResponse:
        """Authenticate with a single non-enumerating password verification."""
        canonical_email = canonicalize_email(email)
        user = self._repository.find_by_canonical_email(canonical_email)
        verified = self._password_hasher.verify_or_dummy(
            password, user.password_hash if user is not None else None
        )
        if user is None or not verified:
            raise AuthenticationError() from None
        return _auth_response(user, self._token_codec.issue(str(_user_id(user))))


def _user_id(user: User) -> int:
    """Reject corrupted persisted identifiers before they become token subjects."""
    if not isinstance(user.id, int) or isinstance(user.id, bool) or user.id <= 0:
        raise RuntimeError("persisted user has an invalid identifier")
    return user.id


def _auth_response(user: User, token: str) -> AuthResponse:
    """Map an ORM entity to the exact public auth response shape."""
    return AuthResponse(
        user=PublicUser(id=_user_id(user), username=user.username, email=user.email),
        token=token,
    )


__all__ = ["AuthService"]
