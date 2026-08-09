"""Metadata-only tests for feature-owned SQLModel table declarations."""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.sql.schema import Index

from app.db.models import metadata
from app.db.types import UTCDateTime


def test_core_metadata_has_the_expected_table_and_column_inventory() -> None:
    assert tuple(metadata.tables) == (
        "users",
        "bookmarks",
        "tags",
        "bookmark_tags",
        "bookmark_stats_window_dirty",
        "bookmark_stats_window_working",
        "bookmark_stats_window_point",
        "bookmark_stats_projection_state",
    )

    users = metadata.tables["users"]
    bookmarks = metadata.tables["bookmarks"]
    tags = metadata.tables["tags"]
    bookmark_tags = metadata.tables["bookmark_tags"]
    dirty = metadata.tables["bookmark_stats_window_dirty"]
    working = metadata.tables["bookmark_stats_window_working"]
    point = metadata.tables["bookmark_stats_window_point"]
    state = metadata.tables["bookmark_stats_projection_state"]

    assert [(column.name, column.nullable) for column in users.columns] == [
        ("id", False),
        ("username", False),
        ("email", False),
        ("password_hash", False),
        ("created_at", False),
    ]
    assert [(column.name, column.nullable) for column in bookmarks.columns] == [
        ("id", False),
        ("url", False),
        ("title", False),
        ("description", True),
        ("user_id", False),
        ("created_at", False),
        ("updated_at", False),
    ]
    assert [(column.name, column.nullable) for column in tags.columns] == [
        ("id", False),
        ("name", False),
    ]
    assert [(column.name, column.nullable) for column in bookmark_tags.columns] == [
        ("bookmark_id", False),
        ("tag_id", False),
    ]
    assert [(column.name, column.nullable) for column in dirty.columns] == [
        ("user_id", False),
        ("window_start", False),
        ("generation", False),
        ("current_completed_generation", False),
        ("projection_completed_generation", False),
        ("reason", False),
        ("first_marked_at", False),
        ("last_marked_at", False),
    ]
    assert isinstance(users.c.created_at.type, UTCDateTime)
    assert isinstance(bookmarks.c.created_at.type, UTCDateTime)
    assert isinstance(bookmarks.c.updated_at.type, UTCDateTime)
    assert isinstance(dirty.c.window_start.type, UTCDateTime)
    assert isinstance(dirty.c.first_marked_at.type, UTCDateTime)
    assert isinstance(dirty.c.last_marked_at.type, UTCDateTime)
    assert [column.name for column in working.columns] == [
        "user_id",
        "window_start",
        "window_end",
        "payload",
        "calculated_at",
        "source_generation",
        "calculation_version",
        "content_hash",
    ]
    assert [column.name for column in point.columns] == [
        "id",
        "user_id",
        "window_start",
        "window_end",
        "revision",
        "supersedes_id",
        "payload",
        "calculated_at",
        "developed_at",
        "correction_reason",
        "source_generation",
        "calculation_version",
        "content_hash",
    ]
    assert [column.name for column in state.columns] == [
        "id",
        "status",
        "calculation_version",
        "checkpoint_user_id",
        "checkpoint_window_start",
        "baseline_started_at",
        "baseline_completed_at",
        "updated_at",
        "last_projection_success_at",
        "failure_code",
    ]


def test_core_metadata_has_deterministic_constraints_foreign_keys_and_indexes() -> None:
    expected_constraints = {
        "users": {
            "pk_users",
            "uq_users_username",
            "uq_users_email",
            "ck_users_username_nonblank",
            "ck_users_username_length",
            "ck_users_email_nonblank",
            "ck_users_password_hash_nonblank",
        },
        "bookmarks": {
            "pk_bookmarks",
            "fk_bookmarks_user_id_users",
            "ck_bookmarks_url_nonblank",
            "ck_bookmarks_title_nonblank",
            "ck_bookmarks_title_length",
            "ck_bookmarks_description_length",
            "ck_bookmarks_updated_not_before_created",
        },
        "tags": {"pk_tags", "uq_tags_name", "ck_tags_name_nonblank", "ck_tags_name_length"},
        "bookmark_tags": {
            "pk_bookmark_tags",
            "fk_bookmark_tags_bookmark_id_bookmarks",
            "fk_bookmark_tags_tag_id_tags",
        },
        "bookmark_stats_window_dirty": {
            "pk_stats_dirty_user_window",
            "fk_stats_dirty_user",
            "ck_stats_dirty_generation_positive",
            "ck_stats_dirty_reason_bounded",
            "ck_stats_dirty_reason_known",
            "ck_stats_dirty_window_monday_utc",
            "ck_stats_dirty_first_marked_utc",
            "ck_stats_dirty_last_marked_utc",
            "ck_stats_dirty_current_completion_generation",
            "ck_stats_dirty_projection_completion_generation",
        },
    }
    expected_indexes = {
        "users": {},
        "bookmarks": {
            "ix_bookmarks_user_created_id": ("user_id", "created_at", "id"),
            "ix_bookmarks_user_updated_id": ("user_id", "updated_at", "id"),
        },
        "tags": {},
        "bookmark_tags": {"ix_bookmark_tags_tag_bookmark": ("tag_id", "bookmark_id")},
        "bookmark_stats_window_dirty": {
            "ix_stats_dirty_last_marked_user_window": (
                "last_marked_at",
                "user_id",
                "window_start",
            ),
            "ix_stats_dirty_window_user": ("window_start", "user_id"),
        },
        "bookmark_stats_window_working": {
            "ix_stats_working_window_end_user": ("window_end", "user_id")
        },
        "bookmark_stats_window_point": {
            "ix_stats_point_effective_user_window_revision": ("user_id", "window_start", "revision")
        },
        "bookmark_stats_projection_state": {},
    }

    for table_name, expected_names in expected_constraints.items():
        table = metadata.tables[table_name]
        assert {constraint.name for constraint in table.constraints} == expected_names
        assert {
            index.name: tuple(column.name for column in index.columns) for index in table.indexes
        } == expected_indexes[table_name]

    bookmarks = metadata.tables["bookmarks"]
    bookmark_tags = metadata.tables["bookmark_tags"]
    dirty = metadata.tables["bookmark_stats_window_dirty"]
    working = metadata.tables["bookmark_stats_window_working"]
    point = metadata.tables["bookmark_stats_window_point"]
    assert [
        (foreign_key.name, tuple(foreign_key.column_keys), foreign_key.ondelete)
        for foreign_key in bookmarks.constraints
        if isinstance(foreign_key, ForeignKeyConstraint)
    ] == [("fk_bookmarks_user_id_users", ("user_id",), "CASCADE")]
    assert {
        (foreign_key.name, tuple(foreign_key.column_keys), foreign_key.ondelete)
        for foreign_key in bookmark_tags.constraints
        if isinstance(foreign_key, ForeignKeyConstraint)
    } == {
        ("fk_bookmark_tags_bookmark_id_bookmarks", ("bookmark_id",), "CASCADE"),
        ("fk_bookmark_tags_tag_id_tags", ("tag_id",), "CASCADE"),
    }
    assert [
        (foreign_key.name, tuple(foreign_key.column_keys), foreign_key.ondelete)
        for foreign_key in dirty.constraints
        if isinstance(foreign_key, ForeignKeyConstraint)
    ] == [("fk_stats_dirty_user", ("user_id",), "CASCADE")]
    assert [
        (foreign_key.name, tuple(foreign_key.column_keys), foreign_key.ondelete)
        for foreign_key in working.constraints
        if isinstance(foreign_key, ForeignKeyConstraint)
    ] == [("fk_stats_working_user", ("user_id",), "CASCADE")]
    assert {
        (foreign_key.name, tuple(foreign_key.column_keys), foreign_key.ondelete)
        for foreign_key in point.constraints
        if isinstance(foreign_key, ForeignKeyConstraint)
    } == {
        ("fk_stats_point_user", ("user_id",), "CASCADE"),
        (
            "fk_stats_point_supersedes_same_window",
            ("supersedes_id", "user_id", "window_start"),
            None,
        ),
    }


def test_metadata_uses_expected_constraint_kinds() -> None:
    users = metadata.tables["users"]
    bookmarks = metadata.tables["bookmarks"]
    bookmark_tags = metadata.tables["bookmark_tags"]
    dirty = metadata.tables["bookmark_stats_window_dirty"]

    assert sum(isinstance(item, PrimaryKeyConstraint) for item in users.constraints) == 1
    assert sum(isinstance(item, UniqueConstraint) for item in users.constraints) == 2
    assert sum(isinstance(item, CheckConstraint) for item in bookmarks.constraints) == 5
    assert sum(isinstance(item, PrimaryKeyConstraint) for item in bookmark_tags.constraints) == 1
    assert tuple(bookmark_tags.primary_key.columns.keys()) == ("bookmark_id", "tag_id")
    assert tuple(dirty.primary_key.columns.keys()) == ("user_id", "window_start")
    assert sum(isinstance(item, CheckConstraint) for item in dirty.constraints) == 8
    assert all(isinstance(index, Index) for index in bookmarks.indexes)
