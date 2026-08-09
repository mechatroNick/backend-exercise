"""Deterministic weekly calendar, payload, and hash-domain behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.bookmarks.stats.schemas import BookmarkStats, TopTag
from app.bookmarks.stats.weekly import (
    PAYLOAD_SCHEMA_VERSION,
    HashComparison,
    WeeklyStatsReader,
    WeeklyWindow,
    calculate_weekly_payload,
    calculation_version,
    canonical_payload_bytes,
    compare_content_hashes,
    content_hash,
    weekly_window,
)


def _stats() -> BookmarkStats:
    return BookmarkStats(
        total_bookmarks=1,
        total_tags=1,
        top_tags=(TopTag(name="café", count=1),),
        bookmarks_per_month=(),
    )


@pytest.mark.parametrize(
    ("instant", "start"),
    [
        (datetime(2026, 8, 9, 23, 59, 59, tzinfo=UTC), datetime(2026, 8, 3, tzinfo=UTC)),
        (datetime(2026, 8, 10, tzinfo=UTC), datetime(2026, 8, 10, tzinfo=UTC)),
        (datetime(2024, 2, 29, 12, tzinfo=UTC), datetime(2024, 2, 26, tzinfo=UTC)),
        (
            datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=11))),
            datetime(2025, 12, 29, tzinfo=UTC),
        ),
    ],
)
def test_weekly_window_normalizes_utc_calendar_boundaries(
    instant: datetime, start: datetime
) -> None:
    assert weekly_window(instant) == WeeklyWindow(start=start, end=start + timedelta(days=7))


def test_weekly_window_rejects_naive_non_datetime_and_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        weekly_window(datetime(2026, 8, 3))
    with pytest.raises(TypeError, match="datetime"):
        weekly_window("2026-08-03")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="UTC Monday midnight"):
        WeeklyWindow.from_bounds(
            datetime(2026, 8, 4, tzinfo=UTC), datetime(2026, 8, 11, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="exactly seven days"):
        WeeklyWindow.from_bounds(datetime(2026, 8, 3, tzinfo=UTC), datetime(2026, 8, 9, tzinfo=UTC))


def test_canonical_payload_is_compact_unicode_stable_and_version_scoped() -> None:
    first = calculate_weekly_payload(_stats(), 5)
    second = calculate_weekly_payload(_stats(), 5)

    assert PAYLOAD_SCHEMA_VERSION == 1
    assert (
        first.payload
        == second.payload
        == (
            b'{"schema_version":1,"stats":{"bookmarks_per_month":[],"top_tags":['
            b'{"count":1,"name":"caf\xc3\xa9"}],"total_bookmarks":1,"total_tags":1}}'
        )
    )
    assert b" " not in first.payload and b"\n" not in first.payload
    assert first.calculation_version == "weekly-v1;payload-schema=1;top-tags-limit=5"
    assert first.content_hash == content_hash(first.calculation_version, first.payload)
    assert canonical_payload_bytes(_stats()) == first.payload


def test_hash_comparison_never_equates_cross_version_candidates() -> None:
    calculation = calculate_weekly_payload(_stats(), 5)
    assert (
        compare_content_hashes(
            stored_version=calculation.calculation_version,
            stored_hash=calculation.content_hash,
            candidate_version=calculation.calculation_version,
            candidate_hash=calculation.content_hash,
        )
        is HashComparison.SAME
    )
    assert (
        compare_content_hashes(
            stored_version=calculation.calculation_version,
            stored_hash=calculation.content_hash,
            candidate_version=calculation.calculation_version,
            candidate_hash="0" * 64,
        )
        is HashComparison.CHANGED
    )
    assert (
        compare_content_hashes(
            stored_version=calculation.calculation_version,
            stored_hash=calculation.content_hash,
            candidate_version=calculation_version(6),
            candidate_hash=calculation.content_hash,
        )
        is HashComparison.VERSION_MISMATCH
    )


@pytest.mark.parametrize("limit", [0, 101, True, "5"])
def test_calculation_rejects_invalid_top_tag_limits(limit: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        calculate_weekly_payload(_stats(), limit)  # type: ignore[arg-type]


def test_hash_rejects_noncanonical_inputs() -> None:
    with pytest.raises(ValueError, match="nonempty string"):
        content_hash("", b"{}")
    with pytest.raises(ValueError, match="nonempty bytes"):
        content_hash("weekly-v1", b"")


def test_reader_validates_user_and_window_before_it_accesses_a_session() -> None:
    reader = WeeklyStatsReader(None, 5)  # type: ignore[arg-type]
    assert reader.calculation_version == calculation_version(5)
    with pytest.raises(ValueError, match="positive integer"):
        reader.read(0, weekly_window(datetime(2026, 8, 3, tzinfo=UTC)))
    with pytest.raises(TypeError, match="WeeklyWindow"):
        reader.read(1, None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="BookmarkStats"):
        canonical_payload_bytes(None)  # type: ignore[arg-type]
