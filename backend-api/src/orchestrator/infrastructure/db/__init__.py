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
from orchestrator.infrastructure.db.models import (
    AttemptRow,
    GateRecordRow,
    HarnessRow,
    ProjectRow,
    RepositoryRow,
    RunRow,
    StepRunRow,
    TemplateRow,
    TemplateVersionRow,
)
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyHarnessRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
)
from orchestrator.infrastructure.db.session import create_session_factory
from orchestrator.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork

__all__ = [
    "NAMING_CONVENTION",
    "AttemptRow",
    "Base",
    "GateRecordRow",
    "HarnessRow",
    "ProjectRow",
    "RepositoryRow",
    "RunRow",
    "SQLAlchemyAttemptRepository",
    "SQLAlchemyGateRecordRepository",
    "SQLAlchemyHarnessRepository",
    "SQLAlchemyProjectRepository",
    "SQLAlchemyRepositoryRepository",
    "SQLAlchemyRunRepository",
    "SQLAlchemyStepRunRepository",
    "SQLAlchemyTemplateVersionRepository",
    "SQLAlchemyUnitOfWork",
    "StepRunRow",
    "TemplateRow",
    "TemplateVersionRow",
    "create_engine_from",
    "create_session_factory",
]
