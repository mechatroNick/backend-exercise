"""Add weekly projection persistence and dual dirty-marker completion.

Revision ID: 0003_weekly_stats_projections
Revises: 0002_bookmark_stats_window_dirty

The dirty-marker alteration uses Alembic's SQLite-safe batch reconstruction:
existing rows are copied into the recreated table, while server defaults make
both newly introduced completion counters valid for every preserved row.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_weekly_stats_projections"
down_revision: str | Sequence[str] | None = "0002_bookmark_stats_window_dirty"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WINDOW_START_CHECK = (
    "length(window_start) = 27 "
    "AND substr(window_start, 11) = 'T00:00:00.000000Z' "
    "AND strftime('%w', window_start) = '1'"
)
_WINDOW_END_CHECK = (
    "length(window_end) = 27 "
    "AND substr(window_end, 11) = 'T00:00:00.000000Z' "
    "AND strftime('%w', window_end) = '1' "
    "AND window_end = strftime('%Y-%m-%dT00:00:00.000000Z', date(window_start, '+7 days'))"
)
_VERSION_CHECK = "length(trim(calculation_version)) > 0 AND length(calculation_version) <= 128"
_HASH_CHECK = "length(content_hash) = 64 AND content_hash NOT GLOB '*[^0-9a-f]*'"


def _monday_check(column: str) -> str:
    return (
        f"length({column}) = 27 "
        f"AND substr({column}, 11) = 'T00:00:00.000000Z' "
        f"AND strftime('%w', {column}) = '1'"
    )


def upgrade() -> None:
    """Add projection state while preserving existing SQLite dirty-marker rows."""
    # SQLite cannot apply these constraint-bearing column changes in place;
    # batch recreation copies the existing relation before adding safe defaults.
    with op.batch_alter_table("bookmark_stats_window_dirty", recreate="always") as batch:
        batch.add_column(
            sa.Column(
                "current_completed_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(
            sa.Column(
                "projection_completed_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.create_check_constraint(
            "ck_stats_dirty_current_completion_generation",
            "current_completed_generation >= 0 AND current_completed_generation <= generation",
        )
        batch.create_check_constraint(
            "ck_stats_dirty_projection_completion_generation",
            "projection_completed_generation >= 0 "
            "AND projection_completed_generation <= generation",
        )

    op.create_table(
        "bookmark_stats_window_working",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.String(length=27), nullable=False),
        sa.Column("window_end", sa.String(length=27), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("calculated_at", sa.String(length=27), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint(_WINDOW_START_CHECK, name="ck_stats_working_window_start_monday_utc"),
        sa.CheckConstraint(_WINDOW_END_CHECK, name="ck_stats_working_window_end_one_week"),
        sa.CheckConstraint("length(payload) > 0", name="ck_stats_working_payload_nonempty"),
        sa.CheckConstraint("source_generation >= 0", name="ck_stats_working_source_generation"),
        sa.CheckConstraint(_VERSION_CHECK, name="ck_stats_working_calculation_version"),
        sa.CheckConstraint(_HASH_CHECK, name="ck_stats_working_content_hash"),
        sa.CheckConstraint(
            "length(calculated_at) = 27 AND substr(calculated_at, 27, 1) = 'Z'",
            name="ck_stats_working_calculated_at_utc",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_working_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "window_start", name="pk_stats_working_user_window"),
    )
    op.create_index(
        "ix_stats_working_window_end_user",
        "bookmark_stats_window_working",
        ["window_end", "user_id"],
    )

    op.create_table(
        "bookmark_stats_window_point",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.String(length=27), nullable=False),
        sa.Column("window_end", sa.String(length=27), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("calculated_at", sa.String(length=27), nullable=False),
        sa.Column("developed_at", sa.String(length=27), nullable=False),
        sa.Column("correction_reason", sa.String(length=128), nullable=True),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.String(length=128), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_stats_point_revision_positive"),
        sa.CheckConstraint(
            "(revision = 1 AND supersedes_id IS NULL) "
            "OR (revision > 1 AND supersedes_id IS NOT NULL)",
            name="ck_stats_point_root_iff_revision_one",
        ),
        sa.CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id != id",
            name="ck_stats_point_no_self_supersession",
        ),
        sa.CheckConstraint(_WINDOW_START_CHECK, name="ck_stats_point_window_start_monday_utc"),
        sa.CheckConstraint(_WINDOW_END_CHECK, name="ck_stats_point_window_end_one_week"),
        sa.CheckConstraint("length(payload) > 0", name="ck_stats_point_payload_nonempty"),
        sa.CheckConstraint("source_generation >= 0", name="ck_stats_point_source_generation"),
        sa.CheckConstraint(_VERSION_CHECK, name="ck_stats_point_calculation_version"),
        sa.CheckConstraint(_HASH_CHECK, name="ck_stats_point_content_hash"),
        sa.CheckConstraint(
            "length(calculated_at) = 27 AND substr(calculated_at, 27, 1) = 'Z'",
            name="ck_stats_point_calculated_at_utc",
        ),
        sa.CheckConstraint(
            "length(developed_at) = 27 AND substr(developed_at, 27, 1) = 'Z'",
            name="ck_stats_point_developed_at_utc",
        ),
        sa.CheckConstraint(
            "developed_at >= calculated_at", name="ck_stats_point_developed_after_calculated"
        ),
        sa.CheckConstraint(
            "(revision = 1 AND correction_reason IS NULL) OR "
            "(revision > 1 AND correction_reason IN "
            "('late_recalculation', 'calculation_upgrade'))",
            name="ck_stats_point_correction_reason",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_stats_point_user", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id", "user_id", "window_start"],
            [
                "bookmark_stats_window_point.id",
                "bookmark_stats_window_point.user_id",
                "bookmark_stats_window_point.window_start",
            ],
            name="fk_stats_point_supersedes_same_window",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stats_point"),
        sa.UniqueConstraint(
            "user_id", "window_start", "revision", name="uq_stats_point_user_window_revision"
        ),
        sa.UniqueConstraint("supersedes_id", name="uq_stats_point_supersedes"),
        sa.UniqueConstraint("id", "user_id", "window_start", name="uq_stats_point_id_user_window"),
    )
    op.create_index(
        "ix_stats_point_effective_user_window_revision",
        "bookmark_stats_window_point",
        ["user_id", "window_start", "revision"],
    )

    op.create_table(
        "bookmark_stats_projection_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("calculation_version", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_user_id", sa.Integer(), nullable=True),
        sa.Column("checkpoint_window_start", sa.String(length=27), nullable=True),
        sa.Column("baseline_started_at", sa.String(length=27), nullable=True),
        sa.Column("baseline_completed_at", sa.String(length=27), nullable=True),
        sa.Column("updated_at", sa.String(length=27), nullable=False),
        sa.Column("last_projection_success_at", sa.String(length=27), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_stats_projection_state_singleton"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'active', 'failed')",
            name="ck_stats_projection_state_status",
        ),
        sa.CheckConstraint(_VERSION_CHECK, name="ck_stats_projection_state_calculation_version"),
        sa.CheckConstraint(
            "(checkpoint_user_id IS NULL AND checkpoint_window_start IS NULL) OR "
            "(checkpoint_user_id > 0 AND checkpoint_window_start IS NOT NULL)",
            name="ck_stats_projection_state_checkpoint_pair",
        ),
        sa.CheckConstraint(
            "checkpoint_window_start IS NULL OR (" + _monday_check("checkpoint_window_start") + ")",
            name="ck_stats_projection_state_checkpoint_monday_utc",
        ),
        sa.CheckConstraint(
            "length(updated_at) = 27 AND substr(updated_at, 27, 1) = 'Z'",
            name="ck_stats_projection_state_updated_at_utc",
        ),
        sa.CheckConstraint(
            "baseline_started_at IS NULL OR "
            "(length(baseline_started_at) = 27 AND substr(baseline_started_at, 27, 1) = 'Z')",
            name="ck_stats_projection_state_baseline_started_at_utc",
        ),
        sa.CheckConstraint(
            "baseline_completed_at IS NULL OR "
            "(length(baseline_completed_at) = 27 AND substr(baseline_completed_at, 27, 1) = 'Z')",
            name="ck_stats_projection_state_baseline_completed_at_utc",
        ),
        sa.CheckConstraint(
            "last_projection_success_at IS NULL OR "
            "(length(last_projection_success_at) = 27 "
            "AND substr(last_projection_success_at, 27, 1) = 'Z')",
            name="ck_stats_projection_state_last_success_at_utc",
        ),
        sa.CheckConstraint(
            "baseline_completed_at IS NULL OR (baseline_started_at IS NOT NULL "
            "AND baseline_completed_at >= baseline_started_at)",
            name="ck_stats_projection_state_baseline_order",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR (length(failure_code) > 0 AND length(failure_code) <= 64 "
            "AND failure_code NOT GLOB '*[^a-z0-9_]*')",
            name="ck_stats_projection_state_failure_code_sanitized",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_stats_projection_state"),
    )


def downgrade() -> None:
    """Remove projection state and reconstruct the pre-0003 dirty-marker schema safely."""
    op.drop_table("bookmark_stats_projection_state")
    op.drop_index(
        "ix_stats_point_effective_user_window_revision",
        table_name="bookmark_stats_window_point",
    )
    op.drop_table("bookmark_stats_window_point")
    op.drop_index("ix_stats_working_window_end_user", table_name="bookmark_stats_window_working")
    op.drop_table("bookmark_stats_window_working")
    # Reconstructing through batch mode preserves dirty-marker rows while dropping
    # only the two 0003 completion columns and their dependent constraints.
    with op.batch_alter_table("bookmark_stats_window_dirty", recreate="always") as batch:
        batch.drop_constraint("ck_stats_dirty_projection_completion_generation", type_="check")
        batch.drop_constraint("ck_stats_dirty_current_completion_generation", type_="check")
        batch.drop_column("projection_completed_generation")
        batch.drop_column("current_completed_generation")
