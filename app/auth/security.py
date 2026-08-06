"""Strict access-only HS256 JWT issue and verification primitives."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Protocol, cast

import jwt
from pydantic import SecretStr

from app.core.clock import Clock, normalize_utc
from app.core.errors import AuthenticationError

_ALGORITHM = "HS256"
_MIN_SECRET_LENGTH_BYTES = 32


class JwtBackend(Protocol):
    """The narrow PyJWT capability used by the access-token adapter."""

    def encode(self, payload: dict[str, object], key: str, algorithm: str) -> str: ...

    def decode(
        self,
        jwt: str,
        key: str,
        algorithms: list[str],
        options: dict[str, object],
    ) -> dict[str, Any]: ...


class TokenConfigurationError(RuntimeError):
    """Unexpected secure-token configuration failure with no secret representation."""


class TokenBackendError(RuntimeError):
    """Unexpected JWT backend failure, preserving the implementation cause."""


class AccessTokenCodec:
    """Issue and verify short-lived access tokens against an injected UTC clock."""

    def __init__(
        self,
        *,
        secret: SecretStr | str,
        ttl: timedelta,
        clock: Clock,
        backend: JwtBackend | None = None,
    ) -> None:
        resolved_secret = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
        if not isinstance(resolved_secret, str):
            raise TokenConfigurationError("JWT signing secret is invalid")
        try:
            secret_length = len(resolved_secret.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise TokenConfigurationError("JWT signing secret is invalid") from error
        token_lifetime_seconds = int(ttl.total_seconds())
        if secret_length < _MIN_SECRET_LENGTH_BYTES:
            raise TokenConfigurationError("JWT signing secret is invalid")
        if ttl <= timedelta(0) or token_lifetime_seconds <= 0:
            raise TokenConfigurationError("JWT access-token lifetime is invalid")
        self._secret = resolved_secret
        self._ttl_seconds = token_lifetime_seconds
        self._clock = clock
        self._backend = (
            backend
            if backend is not None
            else cast(JwtBackend, jwt.PyJWT(options={"enforce_minimum_key_length": True}))
        )

    def issue(self, subject: object) -> str:
        """Issue one HS256 access token with integer POSIX iat and exp claims."""
        if not isinstance(subject, str) or not subject:
            raise ValueError("access-token subject must be a nonempty string")
        issued_at = int(normalize_utc(self._clock.now()).timestamp())
        payload: dict[str, object] = {
            "sub": subject,
            "iat": issued_at,
            "exp": issued_at + self._ttl_seconds,
        }
        try:
            return self._backend.encode(payload, self._secret, algorithm=_ALGORITHM)
        except Exception as error:
            raise TokenBackendError("access-token issuance failed") from error

    def verify(self, token: object) -> str:
        """Verify a bearer token's HS256 signature and exact injected-clock claims."""
        if not isinstance(token, str) or not token:
            raise AuthenticationError() from None
        try:
            claims = self._backend.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                options={
                    "require": ["sub", "iat", "exp"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.InvalidTokenError:
            raise AuthenticationError() from None
        except Exception as error:
            raise TokenBackendError("access-token verification failed") from error

        subject = claims.get("sub")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        now = int(normalize_utc(self._clock.now()).timestamp())
        if (
            not isinstance(subject, str)
            or not subject
            or type(issued_at) is not int
            or type(expires_at) is not int
            or issued_at > now
            or expires_at <= now
            or expires_at <= issued_at
        ):
            raise AuthenticationError() from None
        return subject


__all__ = [
    "AccessTokenCodec",
    "JwtBackend",
    "TokenBackendError",
    "TokenConfigurationError",
]
