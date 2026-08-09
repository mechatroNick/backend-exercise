"""Feature-owned SQLModel table declarations for application users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from app.db.types import UTCDateTime


class User(SQLModel, table=True):
    """Persisted account identity; application validation is introduced in Track 02."""

    __tablename__ = "users"  # pyright: ignore[reportAssignmentType] -- SQLModel metaclass
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_users"),
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("length(trim(username)) > 0", name="ck_users_username_nonblank"),
        CheckConstraint("length(username) <= 80", name="ck_users_username_length"),
        CheckConstraint("length(trim(email)) > 0", name="ck_users_email_nonblank"),
        CheckConstraint("length(trim(password_hash)) > 0", name="ck_users_password_hash_nonblank"),
    )

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(sa_column=Column(String(80), nullable=False))
    email: str = Field(sa_column=Column(String, nullable=False))
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    created_at: datetime = Field(sa_column=Column(UTCDateTime(), nullable=False))
