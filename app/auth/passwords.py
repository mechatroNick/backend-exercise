"""Argon2 password primitives with strict NFC and failure semantics."""

from __future__ import annotations

import secrets
import unicodedata
from typing import Protocol

from pwdlib import PasswordHash

from app.core.errors import ValidationApplicationError

_MIN_PASSWORD_LENGTH = 15
_MAX_PASSWORD_LENGTH = 128


class PasswordHashPort(Protocol):
    """The narrow pwdlib capability needed by application services."""

    def hash(self, password: str, *, salt: bytes | None = None) -> str: ...

    def verify(self, password: str, hash: str) -> bool: ...


class PasswordHashFailure(RuntimeError):
    """Unexpected hash-format or backend failure; its cause is retained safely."""


def normalize_password(value: object) -> str:
    """Apply the exact NFC and post-normalization length policy without trimming."""
    if not isinstance(value, str):
        raise ValidationApplicationError() from None
    normalized = unicodedata.normalize("NFC", value)
    if not _MIN_PASSWORD_LENGTH <= len(normalized) <= _MAX_PASSWORD_LENGTH:
        raise ValidationApplicationError() from None
    return normalized


class PasswordHasher:
    """A process-local Argon2 adapter with a generated missing-user dummy hash."""

    def __init__(self, password_hash: PasswordHashPort | None = None) -> None:
        self._password_hash = (
            password_hash if password_hash is not None else PasswordHash.recommended()
        )
        self._dummy_hash: str | None = None

    def hash(self, password: object) -> str:
        """NFC-normalize and Argon2id-hash a password with pwdlib's random salt."""
        try:
            password_hash = self._password_hash.hash(normalize_password(password))
        except ValidationApplicationError:
            raise
        except Exception as error:
            raise PasswordHashFailure("password hashing failed") from error
        if not password_hash.startswith("$argon2id$"):
            raise PasswordHashFailure("password hashing produced an unsupported hash format")
        return password_hash

    def verify(self, password: object, password_hash: object) -> bool:
        """Return false for a valid mismatch and surface malformed/backend failure safely."""
        normalized = normalize_password(password)
        if not isinstance(password_hash, str) or not password_hash:
            raise PasswordHashFailure("stored password hash is invalid")
        try:
            return self._password_hash.verify(normalized, password_hash)
        except Exception as error:
            raise PasswordHashFailure("password hash verification failed") from error

    def dummy_hash(self) -> str:
        """Lazily generate a process-local dummy hash for non-enumerating login checks."""
        if self._dummy_hash is None:
            generated_password = secrets.token_urlsafe(32)
            self._dummy_hash = self.hash(generated_password)
        return self._dummy_hash

    def verify_or_dummy(self, password: object, password_hash: str | None) -> bool:
        """Verify a supplied hash, or exercise the same path against a private dummy hash."""
        return self.verify(
            password, password_hash if password_hash is not None else self.dummy_hash()
        )


__all__ = [
    "PasswordHashFailure",
    "PasswordHashPort",
    "PasswordHasher",
    "normalize_password",
]
