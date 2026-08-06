"""Strict transport DTOs for the bookmark CRUD boundary."""

from __future__ import annotations

from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.bookmarks.policy import normalize_tag_membership


def _validate_url(value: AnyHttpUrl) -> AnyHttpUrl:
    """Reject credential-bearing URLs while retaining Pydantic's canonical URL value."""
    if value.scheme not in {"http", "https"}:
        msg = "URL scheme must be http or https"
        raise ValueError(msg)
    if value.username is not None or value.password is not None:
        msg = "URL userinfo is not allowed"
        raise ValueError(msg)
    return value


def _validate_title(value: str) -> str:
    """Reject blank titles without rewriting an otherwise valid title."""
    if not value.strip():
        msg = "title must not be blank"
        raise ValueError(msg)
    return value


class BookmarkCreate(BaseModel):
    """Untrusted input for a new bookmark."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    tags: tuple[str, ...]

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        return _validate_url(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _validate_title(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> tuple[str, ...]:
        return normalize_tag_membership(value)


class BookmarkPatch(BaseModel):
    """Partial bookmark input, preserving omitted-versus-null field semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: AnyHttpUrl | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    tags: tuple[str, ...] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is None:
            msg = "url may not be null"
            raise ValueError(msg)
        return _validate_url(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            msg = "title may not be null"
            raise ValueError(msg)
        return _validate_title(value)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> tuple[str, ...]:
        if value is None:
            msg = "tags may not be null"
            raise ValueError(msg)
        return normalize_tag_membership(value)


class TagPublic(BaseModel):
    """The public representation of a normalized tag."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str


class BookmarkPublic(BaseModel):
    """The exact response shape for a bookmark; persistence fields stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(gt=0)
    url: AnyHttpUrl
    title: str
    description: str | None
    tags: tuple[TagPublic, ...]
    created_at: datetime
    updated_at: datetime


class BookmarkList(BaseModel):
    """Forward-compatible baseline collection response for Track 04."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[BookmarkPublic, ...]
    total: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


__all__ = [
    "BookmarkCreate",
    "BookmarkList",
    "BookmarkPatch",
    "BookmarkPublic",
    "TagPublic",
]
