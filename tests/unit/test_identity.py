"""Unit tests for canonical identity validation."""

from __future__ import annotations

import pytest

from app.auth import identity
from app.auth.identity import canonicalize_email, canonicalize_username
from app.core.errors import ValidationApplicationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Alice.Example@Example.COM  ", "alice.example@example.com"),
        ("USER+tag@example.com", "user+tag@example.com"),
    ],
)
def test_email_is_trimmed_lowercased_and_syntax_checked(raw: str, expected: str) -> None:
    assert canonicalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        42,
        "",
        "   ",
        "not-an-email",
        "name <person@example.com>",
        "person@example",
        "person @example.com",
    ],
)
def test_invalid_email_values_are_transport_independent_validation_errors(raw: object) -> None:
    with pytest.raises(ValidationApplicationError):
        canonicalize_email(raw)


def test_email_uses_the_validator_normalized_canonical_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NormalizedEmail:
        normalized = "normalized@example.com"

    monkeypatch.setattr(identity, "validate_email", lambda *_args, **_kwargs: NormalizedEmail())

    assert canonicalize_email("different@example.com") == "normalized@example.com"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Alice_Example-1  ", "alice_example-1"),
        ("A.B", "a.b"),
        ("x" * 80, "x" * 80),
    ],
)
def test_username_is_trimmed_lowercased_and_limited_to_ascii_policy(
    raw: str, expected: str
) -> None:
    assert canonicalize_username(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        42,
        "ab",
        "x" * 81,
        "user name",
        "üser",
        "name/with/slash",
        "name!",
    ],
)
def test_username_rejects_invalid_type_length_and_characters(raw: object) -> None:
    with pytest.raises(ValidationApplicationError):
        canonicalize_username(raw)
