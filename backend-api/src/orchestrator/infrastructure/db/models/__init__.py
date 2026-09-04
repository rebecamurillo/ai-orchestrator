"""The SQLAlchemy models — the tables `Base.metadata` holds and Alembic compares against.

Importing this package declares every table. `infrastructure/db/__init__.py` imports it for
exactly that reason: a model nothing imported would be invisible to `alembic
--autogenerate`, and the revision that shipped would look complete while it was not.
"""

from __future__ import annotations

from orchestrator.infrastructure.db.models.project import ProjectRow

__all__ = ["ProjectRow"]
