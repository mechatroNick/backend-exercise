"""Disclosure and strictness tests for Track 02 authentication DTOs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.auth.schemas import AuthResponse, CurrentSubject, LoginRequest, PublicUser, RegisterRequest


def test_request_dtos_forbid_extra_input_and_redact_passwords_from_repr() -> None:
    password = "p" * 15
    registration = RegisterRequest(
        username="alice",
        email="alice@example.test",
        password=password,
    )
    login = LoginRequest(email="alice@example.test", password=password)

    assert registration.password.get_secret_value() == password
    assert login.password.get_secret_value() == password
    assert password not in repr(registration)
    assert password not in repr(login)
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="alice",
            email="alice@example.test",
            password=password,
            ignored=True,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"username": 1, "email": "alice@example.test", "password": "p" * 15},
        {"username": "alice", "email": 1, "password": "p" * 15},
        {"username": "alice", "email": "alice@example.test", "password": 1},
    ],
)
def test_request_dtos_reject_type_coercion(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(payload)


def test_public_auth_response_has_exact_fields_and_hides_token_from_repr() -> None:
    opaque_token = "opaque-test-token"
    response = AuthResponse(
        user=PublicUser(id=7, username="alice", email="alice@example.test"),
        token=opaque_token,
    )

    assert response.model_dump(mode="json") == {
        "user": {"id": 7, "username": "alice", "email": "alice@example.test"},
        "token": opaque_token,
    }
    assert opaque_token not in repr(response)
    assert set(PublicUser.model_fields) == {"id", "username", "email"}
    assert set(AuthResponse.model_fields) == {"user", "token"}
    assert not {"created_at", "token_type", "access_token", "password", "password_hash"} & set(
        AuthResponse.model_fields | PublicUser.model_fields
    )


def test_current_subject_is_frozen_and_requires_a_positive_identifier() -> None:
    subject = CurrentSubject(user_id=7)

    with pytest.raises(ValidationError):
        CurrentSubject(user_id=0)
    with pytest.raises(ValidationError):
        subject.user_id = 8  # type: ignore[misc]
