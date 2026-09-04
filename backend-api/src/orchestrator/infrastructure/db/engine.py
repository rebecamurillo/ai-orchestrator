"""The one datasource.

`DATABASE_URL` is read from the typed settings, never from the environment directly
(AD-20), and it is a `SecretStr` because the committed contract embeds the Postgres
password in it. `create_engine` opens no connection, which is what lets the unit suite
construct an engine with no database running (AD-18).
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

from orchestrator.infrastructure.settings import Settings


def create_engine_from(settings: Settings) -> Engine:
    """Build the process-wide engine from `DATABASE_URL`."""
    return create_engine(
        settings.database_url.get_secret_value(),
        # Postgres restarting leaves dead connections in the pool; without this the first
        # request after a restart fails instead of transparently reconnecting
        pool_pre_ping=True,
        future=True,
    )
