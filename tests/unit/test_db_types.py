"""Unit tests for deterministic UTC persistence conversion."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.sqlite import dialect

from app.db.types import UTCDateTime


def test_utc_datetime_normalizes_offset_and_persists_fixed_width_text() -> None:
    value = datetime(2026, 8, 6, 10, 30, 1, 123_456, tzinfo=timezone(timedelta(hours=10)))

    persisted = UTCDateTime().process_bind_param(value, dialect())

    assert persisted == "2026-08-06T00:30:01.123456Z"


def test_utc_datetime_round_trips_an_aware_utc_datetime() -> None:
    persisted = "2026-08-06T00:30:01.123456Z"

    restored = UTCDateTime().process_result_value(persisted, dialect())

    assert restored == datetime(2026, 8, 6, 0, 30, 1, 123_456, tzinfo=UTC)
    assert restored.tzinfo is UTC


def test_utc_datetime_rejects_naive_input() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        UTCDateTime().process_bind_param(datetime(2026, 8, 6, 0, 30), dialect())


def test_utc_datetime_allows_database_nulls_without_converting_them() -> None:
    persistence_type = UTCDateTime()

    assert persistence_type.process_bind_param(None, dialect()) is None
    assert persistence_type.process_result_value(None, dialect()) is None


def test_utc_datetime_rejects_non_datetime_bind_values() -> None:
    with pytest.raises(TypeError, match="datetime instances"):
        UTCDateTime().process_bind_param(42, dialect())  # type: ignore[arg-type]


def test_utc_datetime_rejects_malformed_database_text() -> None:
    with pytest.raises(ValueError, match="valid UTC timestamp"):
        UTCDateTime().process_result_value("2026-08-06 00:30:01", dialect())


@pytest.mark.parametrize("value", [42, b"2026-08-06T00:30:01.123456Z"])
def test_utc_datetime_rejects_non_string_database_values(value: object) -> None:
    with pytest.raises(TypeError, match="must be strings"):
        UTCDateTime().process_result_value(value, dialect())
