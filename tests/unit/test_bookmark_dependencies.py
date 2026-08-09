"""Composition tests for cursor-specific bookmark dependencies."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from app.bookmarks.dependencies import get_bookmark_cursor_codec
from app.bookmarks.pagination import BookmarkCursorCodec


def test_cursor_codec_dependency_returns_only_the_composed_codec() -> None:
    codec = BookmarkCursorCodec(secret=SecretStr("cursor-dependency-secret"), ttl_seconds=900)
    app = SimpleNamespace(state=SimpleNamespace(bookmark_cursor_codec=codec))
    request = Request({"type": "http", "app": app})

    assert get_bookmark_cursor_codec(request) is codec


def test_cursor_codec_dependency_rejects_uninitialized_application_state() -> None:
    app = SimpleNamespace(state=SimpleNamespace(bookmark_cursor_codec=object()))
    request = Request({"type": "http", "app": app})

    with pytest.raises(RuntimeError, match="cursor codec is unavailable"):
        get_bookmark_cursor_codec(request)
