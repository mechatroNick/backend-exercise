"""Unit tests for NFC-aware Argon2 password handling."""

from __future__ import annotations

import pytest

from app.auth.passwords import PasswordHasher, PasswordHashFailure, normalize_password
from app.core.errors import ValidationApplicationError


class FailingPasswordHash:
    def hash(self, password: str, *, salt: bytes | None = None) -> str:
        raise RuntimeError("backend unavailable")

    def verify(self, password: str, hash: str) -> bool:
        raise RuntimeError("backend unavailable")


class UnsupportedPasswordHash:
    def hash(self, password: str, *, salt: bytes | None = None) -> str:
        return "unsupported-format"

    def verify(self, password: str, hash: str) -> bool:
        return False


def test_password_normalization_uses_nfc_before_counting_and_preserves_spaces() -> None:
    decomposed = "e\u0301" * 15

    assert normalize_password(decomposed) == "é" * 15
    assert normalize_password(" " * 15) == " " * 15


@pytest.mark.parametrize("value", [None, 12, "x" * 14, "x" * 129])
def test_password_policy_rejects_non_strings_and_post_normalization_length(value: object) -> None:
    with pytest.raises(ValidationApplicationError):
        normalize_password(value)


def test_argon2_hashes_are_distinct_verify_nfc_equivalents_and_reject_wrong_password() -> None:
    hasher = PasswordHasher()
    decomposed = "e\u0301" * 15
    composed = "é" * 15

    first = hasher.hash(decomposed)
    second = hasher.hash(decomposed)

    assert first.startswith("$argon2id$")
    assert second.startswith("$argon2id$")
    assert first != second
    assert hasher.verify(composed, first) is True
    assert hasher.verify("z" * 15, first) is False


@pytest.mark.parametrize("stored", [None, "", "not-an-argon2-hash"])
def test_malformed_stored_hashes_are_unexpected_failures(stored: object) -> None:
    with pytest.raises(PasswordHashFailure):
        PasswordHasher().verify("x" * 15, stored)


def test_backend_failures_preserve_an_unexpected_cause() -> None:
    hasher = PasswordHasher(FailingPasswordHash())

    with pytest.raises(PasswordHashFailure) as hash_failure:
        hasher.hash("x" * 15)
    assert isinstance(hash_failure.value.__cause__, RuntimeError)

    with pytest.raises(PasswordHashFailure) as verify_failure:
        hasher.verify("x" * 15, "$argon2id$valid-looking")
    assert isinstance(verify_failure.value.__cause__, RuntimeError)


def test_hash_preserves_validation_errors_and_rejects_non_argon2_backend_output() -> None:
    with pytest.raises(ValidationApplicationError):
        PasswordHasher().hash("x" * 14)
    with pytest.raises(PasswordHashFailure, match="unsupported hash format"):
        PasswordHasher(UnsupportedPasswordHash()).hash("x" * 15)


def test_missing_subject_path_uses_a_generated_private_dummy_hash() -> None:
    hasher = PasswordHasher()

    generated = hasher.dummy_hash()

    assert generated.startswith("$argon2id$")
    assert generated == hasher.dummy_hash()
    assert hasher.verify_or_dummy("x" * 15, None) is False
