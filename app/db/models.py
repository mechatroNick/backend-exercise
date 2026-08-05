"""Deterministic SQLModel metadata registry consumed by future Alembic configuration."""

from sqlmodel import SQLModel

# These imports intentionally register every feature-owned core table in a stable order.
from app.auth.models import User
from app.bookmarks.models import Bookmark, BookmarkTag, Tag

metadata = SQLModel.metadata

__all__ = ["Bookmark", "BookmarkTag", "Tag", "User", "metadata"]
