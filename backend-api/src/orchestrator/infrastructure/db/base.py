"""The declarative base every model inherits, and the metadata Alembic compares against.

One `MetaData` for schema `public` — the `dbos` schema is DBOS-managed and Alembic never
touches it (AD-6). No table is declared in this story: a table arrives with the story that
needs it, so the baseline revision creates nothing.

The naming convention is not decoration. PostgreSQL invents a name for an unnamed
constraint, and a `downgrade()` written months later has no name to drop; fixing the names
here means every constraint is referable from the migration that created it.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The mapper registry. `alembic/env.py` reads `Base.metadata` as its target."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
