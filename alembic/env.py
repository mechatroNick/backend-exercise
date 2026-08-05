"""Alembic environment with the same SQLite connection policy as the application."""

from sqlalchemy import text

from alembic import context
from app.core.config import Settings
from app.db.engine import create_database_engine
from app.db.models import metadata

config = context.config
target_metadata = metadata


def _settings_for_command() -> Settings:
    """Resolve settings only when an Alembic command actually runs."""
    database_url = config.get_main_option("sqlalchemy.url")
    if database_url:
        return Settings(database_url=database_url)
    return Settings()


def run_migrations_offline() -> None:
    """Refuse offline SQL generation because it cannot prove SQLite connection policy."""
    msg = "offline migrations are unsupported because SQLite connection policy cannot be verified"
    raise RuntimeError(msg)


def run_migrations_online() -> None:
    """Run revisions through an engine that enforces the application SQLite policy."""
    engine = create_database_engine(_settings_for_command())
    try:
        with engine.begin() as connection:
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
            if foreign_keys != 1:
                msg = "Alembic requires SQLite foreign_keys=ON"
                raise RuntimeError(msg)
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
