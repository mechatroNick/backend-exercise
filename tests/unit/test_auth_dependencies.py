"""Unit evidence for defensive authentication dependency boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.auth.dependencies import _canonical_subject_id, _rate_limiter, _session_factory
from app.core.errors import AuthenticationError


def test_session_factory_rejects_uninitialized_application_state() -> None:
    app = SimpleNamespace(state=SimpleNamespace(session_factory=object()))
    request = Request({"type": "http", "app": app})

    with pytest.raises(RuntimeError, match="session factory is unavailable"):
        _session_factory(request)


def test_rate_limiter_rejects_uninitialized_application_state() -> None:
    app = SimpleNamespace(state=SimpleNamespace(rate_limiter=object()))
    request = Request({"type": "http", "app": app})

    with pytest.raises(RuntimeError, match="rate limiter is unavailable"):
        _rate_limiter(request)


def test_canonical_subject_rejects_values_over_pythons_safe_integer_limit() -> None:
    with pytest.raises(AuthenticationError):
        _canonical_subject_id("9" * 5_000)
