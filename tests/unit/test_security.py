"""Deterministic tests for strict HS256 access-token semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import SecretStr

from app.auth.security import AccessTokenCodec, TokenBackendError, TokenConfigurationError
from app.core.errors import AuthenticationError

_SECRET = "t" * 48


class FakeClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class FailingJwtBackend:
    def encode(self, payload: dict[str, object], key: str, algorithm: str) -> str:
        raise RuntimeError("JWT backend unavailable")

    def decode(
        self, token: str, key: str, algorithms: list[str], options: dict[str, object]
    ) -> dict[str, object]:
        raise RuntimeError("JWT backend unavailable")


def _clock() -> FakeClock:
    return FakeClock(datetime(2026, 8, 6, 12, 0, tzinfo=UTC))


def _codec(
    *, clock: FakeClock | None = None, ttl: timedelta = timedelta(minutes=30)
) -> AccessTokenCodec:
    return AccessTokenCodec(secret=SecretStr(_SECRET), ttl=ttl, clock=clock or _clock())


def _token(payload: dict[str, object], algorithm: str = "HS256") -> str:
    key = _SECRET if algorithm != "none" else ""
    return jwt.encode(payload, key, algorithm=algorithm)


def test_issues_and_verifies_exact_integer_claims_at_the_issued_instant() -> None:
    clock = _clock()
    codec = _codec(clock=clock)

    token = codec.issue("42")
    claims = jwt.decode(
        token,
        _SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )

    assert claims == {"sub": "42", "iat": 1786017600, "exp": 1786019400}
    assert codec.verify(token) == "42"


@pytest.mark.parametrize("subject", [None, ""])
def test_issuing_requires_a_nonempty_string_subject(subject: object) -> None:
    with pytest.raises(ValueError):
        _codec().issue(subject)


@pytest.mark.parametrize(
    "payload",
    [
        {"iat": 1786017600, "exp": 1786019400},
        {"sub": None, "iat": 1786017600, "exp": 1786019400},
        {"sub": "42", "iat": None, "exp": 1786019400},
        {"sub": "42", "iat": True, "exp": 1786019400},
        {"sub": "42", "iat": 1786017600.0, "exp": 1786019400},
        {"sub": "42", "iat": "1786017600", "exp": 1786019400},
        {"sub": "42", "iat": 1786017601, "exp": 1786019400},
        {"sub": "42", "iat": 1786017600, "exp": 1786017600},
        {"sub": "42", "iat": 1786017600, "exp": 1786017599},
    ],
)
def test_missing_wrong_type_and_temporally_invalid_claims_are_generic_auth_failures(
    payload: dict[str, object],
) -> None:
    with pytest.raises(AuthenticationError):
        _codec().verify(_token(payload))


@pytest.mark.parametrize("token", [None, "", "not.a.jwt", "eyJhbGciOiJub25lIn0.eyJzdWIiOiI0MiJ9."])
def test_missing_and_malformed_tokens_are_generic_auth_failures(token: object) -> None:
    with pytest.raises(AuthenticationError):
        _codec().verify(token)


def test_tampered_none_and_unpinned_algorithms_are_rejected() -> None:
    valid = _codec().issue("42")
    payload = {"sub": "42", "iat": 1786017600, "exp": 1786019400}

    tokens = [
        f"{valid}x",
        _token(payload, algorithm="HS384"),
        _token(payload, algorithm="none"),
    ]
    for token in tokens:
        with pytest.raises(AuthenticationError):
            _codec().verify(token)


def test_expiry_has_zero_leeway() -> None:
    clock = _clock()
    codec = _codec(clock=clock, ttl=timedelta(seconds=1))
    token = codec.issue("42")
    clock.value = clock.value + timedelta(seconds=1)

    with pytest.raises(AuthenticationError):
        codec.verify(token)


def test_short_secret_and_nonpositive_ttl_are_unexpected_configuration_failures() -> None:
    with pytest.raises(TokenConfigurationError):
        AccessTokenCodec(secret=SecretStr("short"), ttl=timedelta(minutes=1), clock=_clock())
    with pytest.raises(TokenConfigurationError):
        AccessTokenCodec(secret=SecretStr(_SECRET), ttl=timedelta(0), clock=_clock())
    with pytest.raises(TokenConfigurationError):
        AccessTokenCodec(secret=SecretStr(_SECRET), ttl=timedelta(microseconds=1), clock=_clock())


def test_secret_minimum_is_measured_in_utf8_bytes_and_default_backend_enforces_it() -> None:
    with pytest.raises(TokenConfigurationError):
        AccessTokenCodec(  # type: ignore[arg-type]
            secret=object(), ttl=timedelta(minutes=1), clock=_clock()
        )
    with pytest.raises(TokenConfigurationError):
        AccessTokenCodec(secret=SecretStr("é" * 15), ttl=timedelta(minutes=1), clock=_clock())
    with pytest.raises(TokenConfigurationError) as encoding_failure:
        AccessTokenCodec(
            secret=SecretStr(chr(0xD800) * 32), ttl=timedelta(minutes=1), clock=_clock()
        )
    assert isinstance(encoding_failure.value.__cause__, UnicodeEncodeError)

    codec = AccessTokenCodec(secret=SecretStr("é" * 16), ttl=timedelta(minutes=1), clock=_clock())
    assert codec.verify(codec.issue("42")) == "42"


def test_backend_failures_remain_unexpected_with_causes() -> None:
    codec = AccessTokenCodec(
        secret=SecretStr(_SECRET),
        ttl=timedelta(minutes=1),
        clock=_clock(),
        backend=FailingJwtBackend(),
    )

    with pytest.raises(TokenBackendError) as issue_failure:
        codec.issue("42")
    assert isinstance(issue_failure.value.__cause__, RuntimeError)

    with pytest.raises(TokenBackendError) as verify_failure:
        codec.verify("anything")
    assert isinstance(verify_failure.value.__cause__, RuntimeError)
