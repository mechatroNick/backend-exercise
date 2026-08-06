"""Unit tests for pure bookmark normalization, materiality, and clock policies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.bookmarks.policy import (
    BookmarkSnapshot,
    classify_patch,
    next_updated_at,
    normalize_tag_membership,
    normalize_tag_name,
)
from app.bookmarks.schemas import BookmarkPatch


def snapshot() -> BookmarkSnapshot:
    """Create canonical state used by materiality cases."""
    instant = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
    return BookmarkSnapshot(
        id=7,
        url="https://example.test/",
        title="Title",
        description="Description",
        tags=("api", "python"),
        created_at=instant,
        updated_at=instant,
    )


def test_tag_name_normalization_and_membership_are_canonical() -> None:
    assert normalize_tag_name("  MiXeD  ") == "mixed"
    assert normalize_tag_membership([" Python ", "api", "API"]) == ("api", "python")


@pytest.mark.parametrize("value", [1, None, "", "  ", "x" * 51])
def test_tag_name_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_tag_name(value)


@pytest.mark.parametrize("values", [[], "api", {"api"}, ["   "], ["x" * 51]])
def test_tag_membership_rejects_empty_or_non_array_inputs(values: object) -> None:
    with pytest.raises(ValueError):
        normalize_tag_membership(values)


def test_classify_patch_treats_empty_and_canonical_equivalences_as_noops() -> None:
    current = snapshot()

    empty = classify_patch(current, BookmarkPatch())
    equivalent = classify_patch(
        current,
        BookmarkPatch(url="https://EXAMPLE.test", tags=[" PYTHON ", "api", "API"]),
    )

    assert not empty.is_material
    assert empty.changed_fields == frozenset()
    assert not equivalent.is_material
    assert equivalent.tags == ("api", "python")
    assert equivalent.url == "https://example.test/"


@pytest.mark.parametrize(
    ("patch", "changed"),
    [
        (BookmarkPatch(title="Replacement"), frozenset({"title"})),
        (BookmarkPatch(description=None), frozenset({"description"})),
        (BookmarkPatch(tags=["api", "rust"]), frozenset({"tags"})),
        (
            BookmarkPatch(url="https://other.test", title="Replacement", tags=["rust"]),
            frozenset({"url", "title", "tags"}),
        ),
    ],
)
def test_classify_patch_reports_only_material_scalar_and_tag_changes(
    patch: BookmarkPatch, changed: frozenset[str]
) -> None:
    result = classify_patch(snapshot(), patch)

    assert result.is_material
    assert result.changed_fields == changed


def test_classify_patch_resolves_targets_without_changing_omitted_fields() -> None:
    result = classify_patch(snapshot(), BookmarkPatch(description=None))

    assert result.url == "https://example.test/"
    assert result.title == "Title"
    assert result.description is None
    assert result.tags == ("api", "python")


def test_next_updated_at_is_monotonic_for_repeated_backward_and_offset_clocks() -> None:
    current = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)

    assert next_updated_at(current, current) == current + timedelta(microseconds=1)
    assert next_updated_at(current, current - timedelta(seconds=1)) == current + timedelta(
        microseconds=1
    )
    assert next_updated_at(current, current + timedelta(seconds=1)) == current + timedelta(
        seconds=1
    )
    offset_observed = datetime(2026, 8, 6, 10, 0, 2, tzinfo=timezone(timedelta(hours=10)))
    assert next_updated_at(current, offset_observed) == datetime(2026, 8, 6, 0, 0, 2, tzinfo=UTC)


def test_next_updated_at_rejects_naive_datetimes() -> None:
    aware = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
    naive = datetime(2026, 8, 6, 0, 0)

    with pytest.raises(ValueError, match="timezone-aware"):
        next_updated_at(naive, aware)
    with pytest.raises(ValueError, match="timezone-aware"):
        next_updated_at(aware, naive)
