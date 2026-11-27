"""Every revision id fits `alembic_version.version_num`, a `varchar(32)` Alembic creates.

A longer id passes every unit test (none applies the chain to Postgres) and fails at boot,
on the `UPDATE alembic_version` that closes the migration: the container exits 1 and the
instance never starts. Found by the aio-e2e stack on 2026-11-26 (`0046`, 33 characters).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_migration_chain import VERSIONS, _revision_ids

VERSION_NUM_LENGTH = 32


@pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.name)
def test_the_revision_id_fits_the_version_table(path: Path) -> None:
    revision, _ = _revision_ids(path)

    assert len(revision) <= VERSION_NUM_LENGTH, f"{revision!r} is {len(revision)} characters"
