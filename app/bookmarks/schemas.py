"""Strict transport DTOs for the bookmark CRUD boundary."""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.bookmarks.policy import normalize_tag_membership, normalize_tag_name

_CALENDAR_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


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


def _parse_calendar_date(value: object) -> date:
    """Accept a date object or one canonical ISO calendar-date string only."""
    if isinstance(value, datetime):
        msg = "date filters must be calendar dates, not datetimes"
        raise ValueError(msg)
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or _CALENDAR_DATE.fullmatch(value) is None:
        msg = "date filters must use YYYY-MM-DD"
        raise ValueError(msg)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = "date filters must use valid calendar dates"
        raise ValueError(msg) from exc


def _parse_query_positive_int(value: object) -> int:
    """Parse an ASCII decimal query value without accepting coercive spellings."""
    if isinstance(value, bool):
        msg = "pagination values must be integers"
        raise ValueError(msg)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    msg = "pagination values must be ASCII decimal integers"
    raise ValueError(msg)


class BookmarkQuery(BaseModel):
    """Frozen, strict-shape filters for the Track 04 bookmark collection."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, validate_default=True
    )

    tag: str | None = None
    q: str | None = Field(default=None, max_length=200)
    created_from: date | None = Field(
        default=None, validation_alias="from", serialization_alias="from"
    )
    created_to: date | None = Field(default=None, validation_alias="to", serialization_alias="to")
    updated_from: date | None = None
    updated_to: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_tag_name(value)

    @field_validator("q", mode="before")
    @classmethod
    def validate_query(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            msg = "q must be a string"
            raise ValueError(msg)
        if not value:
            msg = "q must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("created_from", "created_to", "updated_from", "updated_to", mode="before")
    @classmethod
    def validate_calendar_date(cls, value: object) -> date | None:
        if value is None:
            return None
        return _parse_calendar_date(value)

    @field_validator("page", "page_size", mode="before")
    @classmethod
    def parse_pagination(cls, value: object) -> int:
        return _parse_query_positive_int(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> BookmarkQuery:
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            msg = "from must not be after to"
            raise ValueError(msg)
        if (
            self.updated_from is not None
            and self.updated_to is not None
            and self.updated_from > self.updated_to
        ):
            msg = "updated_from must not be after updated_to"
            raise ValueError(msg)
        return self


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
    "BookmarkQuery",
    "TagPublic",
]
