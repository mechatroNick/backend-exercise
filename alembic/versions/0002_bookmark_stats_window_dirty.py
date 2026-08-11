"""Create the reversible durable per-user statistics dirty-marker table.

This initial table creation/removal is deliberately separate from the later
SQLite batch reconstruction so the 0002 downgrade restores the exact 0001
schema boundary without needing to transform pre-existing dirty-marker rows.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_bookmark_stats_window_dirty"
down_revision: str | Sequence[str] | None = "0001_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the empty dirty-marker relation with its durable ownership constraints."""
    op.create_table(
        "bookmark_stats_window_dirty",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.String(27), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("first_marked_at", sa.String(27), nullable=False),
        sa.Column("last_marked_at", sa.String(27), nullable=False),
        sa.CheckConstraint("generation > 0", name="ck_stats_dirty_generation_positive"),
        sa.CheckConstraint(
            "length(reason) > 0 AND length(reason) <= 32", name="ck_stats_dirty_reason_bounded"
        ),
        sa.CheckConstraint(
            "reason IN ('create', 'update', 'delete', 'reconcile')",
            name="ck_stats_dirty_reason_known",
        ),
        sa.CheckConstraint(
            "length(window_start) = 27 "
            "AND substr(window_start, 11) = 'T00:00:00.000000Z' "
            "AND strftime('%w', window_start) = '1'",
            name="ck_stats_dirty_window_monday_utc",
        ),
        sa.CheckConstraint(
            "length(first_marked_at) = 27 AND substr(first_marked_at, 27, 1) = 'Z'",
            name="ck_stats_dirty_first_marked_utc",
        ),
        sa.CheckConstraint(
            "length(last_marked_at) = 27 AND substr(last_marked_at, 27, 1) = 'Z'",
            name="ck_stats_dirty_last_marked_utc",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_dirty_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "window_start", name="pk_stats_dirty_user_window"),
    )
    op.create_index(
        "ix_stats_dirty_window_user", "bookmark_stats_window_dirty", ["window_start", "user_id"]
    )
    op.create_index(
        "ix_stats_dirty_last_marked_user_window",
        "bookmark_stats_window_dirty",
        ["last_marked_at", "user_id", "window_start"],
    )


def downgrade() -> None:
    """Remove only the 0002 relation after its indexes, returning to 0001 exactly."""
    op.drop_index(
        "ix_stats_dirty_last_marked_user_window",
        table_name="bookmark_stats_window_dirty",
    )
    op.drop_index("ix_stats_dirty_window_user", table_name="bookmark_stats_window_dirty")
    op.drop_table("bookmark_stats_window_dirty")
