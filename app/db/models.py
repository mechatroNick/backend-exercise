"""Deterministic SQLModel metadata registry consumed by future Alembic configuration."""

from sqlmodel import SQLModel

# These imports intentionally register every feature-owned core table in a stable order.
from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag
from app.bookmarks.stats.dirty import BookmarkStatsWindowDirty
from app.bookmarks.stats.projection_models import (
    BookmarkStatsProjectionState,
    BookmarkStatsWindowPoint,
    BookmarkStatsWindowWorking,
)

metadata = SQLModel.metadata

__all__ = [
    "Bookmark",
    "BookmarkStatsProjectionState",
    "BookmarkStatsWindowDirty",
    "BookmarkStatsWindowPoint",
    "BookmarkStatsWindowWorking",
    "BookmarkTag",
    "Tag",
    "User",
    "metadata",
]
