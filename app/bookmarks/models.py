"""Feature-owned SQLModel table declarations for bookmarks and tags."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.db.types import UTCDateTime


class Bookmark(SQLModel, table=True):
    """A private saved URL owned by exactly one application user."""

    __tablename__ = "bookmarks"  # pyright: ignore[reportAssignmentType] -- SQLModel metaclass
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_bookmarks"),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_bookmarks_user_id_users", ondelete="CASCADE"
        ),
        CheckConstraint("length(trim(url)) > 0", name="ck_bookmarks_url_nonblank"),
        CheckConstraint("length(trim(title)) > 0", name="ck_bookmarks_title_nonblank"),
        CheckConstraint("length(title) <= 200", name="ck_bookmarks_title_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 500",
            name="ck_bookmarks_description_length",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_bookmarks_updated_not_before_created"),
        Index("ix_bookmarks_user_created_id", "user_id", "created_at", "id"),
        Index("ix_bookmarks_user_updated_id", "user_id", "updated_at", "id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    url: str = Field(sa_column=Column(String, nullable=False))
    title: str = Field(sa_column=Column(String(200), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String(500), nullable=True))
    user_id: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
    updated_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))


class Tag(SQLModel, table=True):
    """A globally unique, service-normalized tag name."""

    __tablename__ = "tags"  # pyright: ignore[reportAssignmentType] -- SQLModel metaclass
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_tags"),
        UniqueConstraint("name", name="uq_tags_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_tags_name_nonblank"),
        CheckConstraint("length(name) <= 50", name="ck_tags_name_length"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(50), nullable=False))


class BookmarkTag(SQLModel, table=True):
    """Explicit many-to-many link table between bookmarks and globally shared tags."""

    __tablename__ = "bookmark_tags"  # pyright: ignore[reportAssignmentType] -- SQLModel metaclass
    __table_args__ = (
        PrimaryKeyConstraint("bookmark_id", "tag_id", name="pk_bookmark_tags"),
        ForeignKeyConstraint(
            ["bookmark_id"],
            ["bookmarks.id"],
            name="fk_bookmark_tags_bookmark_id_bookmarks",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name="fk_bookmark_tags_tag_id_tags", ondelete="CASCADE"
        ),
        Index("ix_bookmark_tags_tag_bookmark", "tag_id", "bookmark_id"),
    )

    bookmark_id: int = Field(sa_column=Column(Integer, nullable=False, primary_key=True))
    tag_id: int = Field(sa_column=Column(Integer, nullable=False, primary_key=True))
