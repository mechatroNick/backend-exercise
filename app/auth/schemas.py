"""Strict transport DTOs for the authentication feature."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class RegisterRequest(BaseModel):
    """Untrusted registration input; the password remains redacted in repr output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    username: str
    email: str
    password: SecretStr = Field(json_schema_extra={"writeOnly": True})


class LoginRequest(BaseModel):
    """Untrusted login input; the password remains redacted in repr output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    email: str
    password: SecretStr = Field(json_schema_extra={"writeOnly": True})


class PublicUser(BaseModel):
    """The intentionally minimal user representation returned by auth operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    username: str
    email: str


class AuthResponse(BaseModel):
    """Successful auth result with a serializable but repr-safe bearer token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user: PublicUser
    token: str = Field(repr=False)


class CurrentSubject(BaseModel):
    """Authenticated durable identity for future request-scoped authorization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: int = Field(gt=0)


__all__ = [
    "AuthResponse",
    "CurrentSubject",
    "LoginRequest",
    "PublicUser",
    "RegisterRequest",
]
