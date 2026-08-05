"""Create constrained core bookmark tables.

Revision ID: 0001_core_schema
Revises: None
Create Date: 2026-08-06

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_core_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four constrained core tables in foreign-key dependency order."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint("length(trim(username)) > 0", name="ck_users_username_nonblank"),
        sa.CheckConstraint("length(username) <= 80", name="ck_users_username_length"),
        sa.CheckConstraint("length(trim(email)) > 0", name="ck_users_email_nonblank"),
        sa.CheckConstraint(
            "length(trim(password_hash)) > 0", name="ck_users_password_hash_nonblank"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_tags_name_nonblank"),
        sa.CheckConstraint("length(name) <= 50", name="ck_tags_name_length"),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.UniqueConstraint("name", name="uq_tags_name"),
    )
    op.create_table(
        "bookmarks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=27), nullable=False),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.CheckConstraint("length(trim(url)) > 0", name="ck_bookmarks_url_nonblank"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_bookmarks_title_nonblank"),
        sa.CheckConstraint("length(title) <= 200", name="ck_bookmarks_title_length"),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 500",
            name="ck_bookmarks_description_length",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name="ck_bookmarks_updated_not_before_created"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_bookmarks_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bookmarks"),
    )
    op.create_index(
        "ix_bookmarks_user_created_id",
        "bookmarks",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_bookmarks_user_updated_id",
        "bookmarks",
        ["user_id", "updated_at", "id"],
        unique=False,
    )
    op.create_table(
        "bookmark_tags",
        sa.Column("bookmark_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["bookmark_id"],
            ["bookmarks.id"],
            name="fk_bookmark_tags_bookmark_id_bookmarks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name="fk_bookmark_tags_tag_id_tags", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("bookmark_id", "tag_id", name="pk_bookmark_tags"),
    )
    op.create_index(
        "ix_bookmark_tags_tag_bookmark",
        "bookmark_tags",
        ["tag_id", "bookmark_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop tables in reverse foreign-key dependency order."""
    op.drop_index("ix_bookmark_tags_tag_bookmark", table_name="bookmark_tags")
    op.drop_table("bookmark_tags")
    op.drop_index("ix_bookmarks_user_updated_id", table_name="bookmarks")
    op.drop_index("ix_bookmarks_user_created_id", table_name="bookmarks")
    op.drop_table("bookmarks")
    op.drop_table("tags")
    op.drop_table("users")
