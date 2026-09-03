"""Alembic's entry point.

Two things are deliberate here.

**The URL comes from the typed settings, not from `alembic.ini`.** `DATABASE_URL` carries
the Postgres password, and a credential never enters a committed file (hard rule 5). When
the application runs migrations at start-up it passes the `Settings` it already built
through `config.attributes`, so the environment is read once (AD-20); `alembic upgrade head`
typed at a shell builds its own.

**`fileConfig` is not called.** Alembic's default would replace the structlog JSON handler
`configure_logging` installed, and the `migrations applied` line would be the only plain
text on an otherwise JSON stream.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.settings import Settings

config = context.config

# Alembic compares against this; no table is declared yet, and a table arrives with the
# story that needs it.
target_metadata = Base.metadata

VERSION_TABLE = config.get_main_option("version_table", "alembic_version")
# schema `public` only — schema `dbos` belongs to the durable engine (AD-6)
VERSION_TABLE_SCHEMA = config.get_main_option("version_table_schema", "public")


def database_url() -> str:
    """The one datasource URL, from the settings the process already read."""
    settings = config.attributes.get("settings") or Settings()
    return str(settings.database_url.get_secret_value())


# Without these two, `alembic revision --autogenerate` silently ignores a changed column
# type or server default, and the revision that ships looks complete while it is not.
COMPARISON = {"compare_type": True, "compare_server_default": True}


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: emit SQL without connecting."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        version_table_schema=VERSION_TABLE_SCHEMA,
        include_schemas=False,
        **COMPARISON,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """The normal path: one connection, one transaction, closed before the server binds."""
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                version_table=VERSION_TABLE,
                version_table_schema=VERSION_TABLE_SCHEMA,
                include_schemas=False,
                **COMPARISON,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        # a failed upgrade must not leave the pool holding a connection to a database the
        # process is about to abort against
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
