"""Exact immutable DTO tests for Track 04 current bookmark statistics."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.bookmarks.stats.schemas import BookmarksPerMonth, BookmarkStats, TopTag


def test_stats_models_are_frozen_exact_and_preserve_reader_order() -> None:
    stats = BookmarkStats(
        total_bookmarks=3,
        total_tags=2,
        top_tags=(TopTag(name=" Python ", count=2), TopTag(name="api", count=1)),
        bookmarks_per_month=(
            BookmarksPerMonth(month="2025-12", count=1),
            BookmarksPerMonth(month="2026-01", count=2),
        ),
    )

    assert stats.model_dump(mode="json") == {
        "total_bookmarks": 3,
        "total_tags": 2,
        "top_tags": [{"name": "python", "count": 2}, {"name": "api", "count": 1}],
        "bookmarks_per_month": [
            {"month": "2025-12", "count": 1},
            {"month": "2026-01", "count": 2},
        ],
    }
    assert set(BookmarkStats.model_fields) == {
        "total_bookmarks",
        "total_tags",
        "top_tags",
        "bookmarks_per_month",
    }
    with pytest.raises(ValidationError):
        stats.total_tags = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "model, payload",
    [
        (TopTag, {"name": " ", "count": 1}),
        (TopTag, {"name": "x" * 51, "count": 1}),
        (TopTag, {"name": "api", "count": 0}),
        (TopTag, {"name": "api", "count": True}),
        (BookmarksPerMonth, {"month": "2026-1", "count": 1}),
        (BookmarksPerMonth, {"month": "2026-13", "count": 1}),
        (BookmarksPerMonth, {"month": "0000-01", "count": 1}),
        (BookmarksPerMonth, {"month": "2026-01", "count": 0}),
        (
            BookmarkStats,
            {"total_bookmarks": -1, "total_tags": 0, "top_tags": (), "bookmarks_per_month": ()},
        ),
        (
            BookmarkStats,
            {"total_bookmarks": 0, "total_tags": -1, "top_tags": (), "bookmarks_per_month": ()},
        ),
    ],
)
def test_stats_models_reject_invalid_shapes_and_counts(
    model: type[TopTag] | type[BookmarksPerMonth] | type[BookmarkStats], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "model, payload",
    [
        (TopTag, {"name": "api", "count": 1, "extra": "no"}),
        (BookmarksPerMonth, {"month": "2026-01", "count": 1, "extra": "no"}),
        (
            BookmarkStats,
            {
                "total_bookmarks": 0,
                "total_tags": 0,
                "top_tags": (),
                "bookmarks_per_month": (),
                "extra": "no",
            },
        ),
    ],
)
def test_stats_models_forbid_extra_fields(
    model: type[TopTag] | type[BookmarksPerMonth] | type[BookmarkStats], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)
