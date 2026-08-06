"""Immutable response DTOs for Track 04's canonical current statistics."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.bookmarks.policy import normalize_tag_name

_MONTH = re.compile(r"[0-9]{4}-[0-9]{2}\Z")


class TopTag(BaseModel):
    """One deterministic current top-tag aggregate row."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    count: int = Field(ge=1)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: object) -> str:
        return normalize_tag_name(value)


class BookmarksPerMonth(BaseModel):
    """One UTC calendar-month bookmark aggregate row."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    month: str
    count: int = Field(ge=1)

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        if _MONTH.fullmatch(value) is None:
            msg = "month must use YYYY-MM"
            raise ValueError(msg)
        year = int(value[:4])
        month = int(value[5:])
        if not 1 <= month <= 12 or year < 1:
            msg = "month must be a valid calendar month"
            raise ValueError(msg)
        return value


class BookmarkStats(BaseModel):
    """Exact user-scoped current-statistics response body for Track 04."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    total_bookmarks: int = Field(ge=0)
    total_tags: int = Field(ge=0)
    top_tags: tuple[TopTag, ...]
    bookmarks_per_month: tuple[BookmarksPerMonth, ...]


__all__ = ["BookmarkStats", "BookmarksPerMonth", "TopTag"]
