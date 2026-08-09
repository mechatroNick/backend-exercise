"""Additive Track 09 evidence for strict Pydantic-backed test helpers."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.integration.test_bookmark_query_plans import _ExecutedStatement


def test_query_plan_statement_record_is_strict_and_value_equal() -> None:
    statement = _ExecutedStatement(statement="SELECT 1", parameters=())

    assert statement == _ExecutedStatement(statement="SELECT 1", parameters=())
    with pytest.raises(ValidationError):
        _ExecutedStatement(statement="SELECT 1", parameters=(), extra="rejected")
