"""Pure bookmark normalization, materiality, and timestamp policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast

from pydantic import AnyHttpUrl

from app.core.clock import normalize_utc


def normalize_tag_name(value: object) -> str:
    """Return the canonical tag name or reject an invalid transport value."""
    if not isinstance(value, str):
        msg = "tag name must be a string"
        raise ValueError(msg)
    normalized = value.strip().lower()
    if not normalized:
        msg = "tag name must not be empty"
        raise ValueError(msg)
    if len(normalized) > 50:
        msg = "tag name must be at most 50 characters"
        raise ValueError(msg)
    return normalized


def normalize_tag_membership(values: object) -> tuple[str, ...]:
    """Canonicalize tag membership as a non-empty, sorted, unique tuple."""
    if not isinstance(values, (list, tuple)):
        msg = "tags must be an array"
        raise ValueError(msg)
    normalized = tuple(sorted({normalize_tag_name(value) for value in values}))
    if not normalized:
        msg = "at least one tag is required"
        raise ValueError(msg)
    return normalized


def canonical_url(value: AnyHttpUrl | str) -> str:
    """Return the Pydantic canonical string form used for persistence and comparison."""
    return str(value)


@dataclass(frozen=True, slots=True)
class BookmarkSnapshot:
    """Canonical bookmark state needed to decide whether a PATCH is material."""

    id: int
    url: str
    title: str
    description: str | None
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MaterialPatch:
    """Resolved target state and the public fields that change materially."""

    url: str
    title: str
    description: str | None
    tags: tuple[str, ...]
    changed_fields: frozenset[str]

    @property
    def is_material(self) -> bool:
        """Whether applying this PATCH requires a durable state change."""
        return bool(self.changed_fields)


class BookmarkPatchValues(Protocol):
    """The narrow PATCH value surface consumed by the pure materiality policy."""

    model_fields_set: set[str]
    url: AnyHttpUrl | None
    title: str | None
    description: str | None
    tags: tuple[str, ...] | None


def classify_patch(snapshot: BookmarkSnapshot, patch: BookmarkPatchValues) -> MaterialPatch:
    """Resolve a PATCH against a snapshot and identify canonical state differences.

    ``patch`` intentionally uses the small Pydantic model surface shared by the
    transport layer: ``model_fields_set`` and the four bookmark attributes.
    This keeps the policy independent from FastAPI and persistence adapters.
    """
    fields_set = frozenset(patch.model_fields_set)
    url = canonical_url(cast(AnyHttpUrl, patch.url)) if "url" in fields_set else snapshot.url
    title = cast(str, patch.title) if "title" in fields_set else snapshot.title
    description = patch.description if "description" in fields_set else snapshot.description
    tags = cast(tuple[str, ...], patch.tags) if "tags" in fields_set else snapshot.tags

    changed = frozenset(
        field
        for field, current, target in (
            ("url", snapshot.url, url),
            ("title", snapshot.title, title),
            ("description", snapshot.description, description),
            ("tags", snapshot.tags, tags),
        )
        if current != target
    )
    return MaterialPatch(
        url=url,
        title=title,
        description=description,
        tags=tags,
        changed_fields=changed,
    )


def next_updated_at(current: datetime, observed: datetime) -> datetime:
    """Advance an update timestamp monotonically, even for repeated/backward clocks."""
    normalized_current = normalize_utc(current)
    return max(normalize_utc(observed), normalized_current + timedelta(microseconds=1))


__all__ = [
    "BookmarkSnapshot",
    "MaterialPatch",
    "canonical_url",
    "classify_patch",
    "next_updated_at",
    "normalize_tag_membership",
    "normalize_tag_name",
]
