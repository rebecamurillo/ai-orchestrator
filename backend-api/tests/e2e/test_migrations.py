"""The migration actually ran — the one claim only a database can settle.

Every assertion in `tests/unit/test_migrations.py` stubs `command.upgrade`, so the unit
suite can prove the ordering and the wiring but never that a schema was changed: it would
happily log `migrations applied` against a database that was never touched. This module
closes that at the one boundary where a database exists.

It reads `DATABASE_URL` through the same typed settings the application uses — already a
`Settings` field and already in the contract, so no new variable — and compares what the
database holds against the head of the committed migration tree rather than a literal
revision id, which keeps it true as later stories add revisions.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.db.migrations import alembic_config, head_revision
from orchestrator.infrastructure.settings import Settings

VERSION_TABLE = "public.alembic_version"


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    """The instance configuration. `stack` first, so a missing variable is reported once."""
    return Settings()


@pytest.fixture(scope="module")
def applied_revisions(settings: Settings) -> list[str]:
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text(f"select version_num from {VERSION_TABLE}"))
            return [row[0] for row in rows]
    finally:
        engine.dispose()


def test_the_version_table_holds_exactly_one_revision(applied_revisions: list[str]) -> None:
    """No row means nothing was applied; two mean the tree branched."""
    assert len(applied_revisions) == 1, applied_revisions


def test_the_database_is_at_the_head_of_the_committed_tree(
    settings: Settings, applied_revisions: list[str]
) -> None:
    expected = head_revision(alembic_config(settings))

    assert applied_revisions == [expected]


def test_the_version_table_lives_in_the_schema_alembic_manages(settings: Settings) -> None:
    """Schema `public` only; schema `dbos` belongs to the durable engine (AD-6)."""
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            schemas = connection.execute(
                text(
                    "select table_schema from information_schema.tables "
                    "where table_name = 'alembic_version'"
                )
            )
            assert [row[0] for row in schemas] == ["public"]
    finally:
        engine.dispose()
