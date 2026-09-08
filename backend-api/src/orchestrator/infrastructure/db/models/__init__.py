"""The SQLAlchemy models — the tables `Base.metadata` holds and Alembic compares against.

Importing this package declares every table. `infrastructure/db/__init__.py` imports it for
exactly that reason: a model nothing imported would be invisible to `alembic
--autogenerate`, and the revision that shipped would look complete while it was not.
"""

from __future__ import annotations

from orchestrator.infrastructure.db.models.harness import HarnessRow
from orchestrator.infrastructure.db.models.project import ProjectRow
from orchestrator.infrastructure.db.models.repository import RepositoryRow
from orchestrator.infrastructure.db.models.run import (
    AttemptRow,
    GateRecordRow,
    RunRow,
    StepRunRow,
)
from orchestrator.infrastructure.db.models.template import TemplateRow, TemplateVersionRow
from orchestrator.infrastructure.db.models.trajectory import TrajectoryRow

__all__ = [
    "AttemptRow",
    "GateRecordRow",
    "HarnessRow",
    "ProjectRow",
    "RepositoryRow",
    "RunRow",
    "StepRunRow",
    "TemplateRow",
    "TemplateVersionRow",
    "TrajectoryRow",
]
