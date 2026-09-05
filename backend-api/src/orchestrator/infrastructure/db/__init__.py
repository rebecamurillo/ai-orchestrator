"""The datasource, behind one package (AD-2).

`domain/` and `application/` never import `sqlalchemy`; they take the `UnitOfWork` port and
the repository ports that later stories add here. Everything SQLAlchemy knows about this
system is inside this package, and `main.py` is the only module that constructs it.
"""

from __future__ import annotations

from orchestrator.infrastructure.db.base import NAMING_CONVENTION, Base
from orchestrator.infrastructure.db.engine import create_engine_from

# imported for its side effect as much as for the name: declaring the model is what puts the
# table in `Base.metadata`, which is what `alembic --autogenerate` compares against
from orchestrator.infrastructure.db.models import ProjectRow, RepositoryRow
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
)
from orchestrator.infrastructure.db.session import create_session_factory
from orchestrator.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "ProjectRow",
    "RepositoryRow",
    "SQLAlchemyProjectRepository",
    "SQLAlchemyRepositoryRepository",
    "SQLAlchemyUnitOfWork",
    "create_engine_from",
    "create_session_factory",
]
