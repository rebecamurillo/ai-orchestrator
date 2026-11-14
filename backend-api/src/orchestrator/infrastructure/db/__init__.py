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
    ActivityFactRow,
    AttemptRow,
    ChatNoticeRow,
    ChatThreadRow,
    EventFactRow,
    FactSetRow,
    GapFactRow,
    GateRecordRow,
    GatewayReadRow,
    HarnessRow,
    InstanceHoldRow,
    ProjectChannelRow,
    ProjectRow,
    RepositoryRow,
    RequestFactRow,
    RunRow,
    StepRunRow,
    TemplateRow,
    TemplateVersionRow,
    TrajectoryRow,
    UsageFactRow,
)
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyChatNoticeRepository,
    SQLAlchemyChatThreadRepository,
    SQLAlchemyFactSetRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyGatewayReadRepository,
    SQLAlchemyHarnessRepository,
    SQLAlchemyHistoryQuery,
    SQLAlchemyInstanceHoldRepository,
    SQLAlchemyMetricCalculationRepository,
    SQLAlchemyProjectChannelRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyResultVersionRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyTrajectoryRepository,
)
from orchestrator.infrastructure.db.session import create_session_factory
from orchestrator.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from orchestrator.infrastructure.db.writers import SessionUnitOfWork, open_writer_ports

__all__ = [
    "NAMING_CONVENTION",
    "ActivityFactRow",
    "AttemptRow",
    "Base",
    "ChatNoticeRow",
    "ChatThreadRow",
    "EventFactRow",
    "FactSetRow",
    "GapFactRow",
    "GateRecordRow",
    "GatewayReadRow",
    "HarnessRow",
    "InstanceHoldRow",
    "ProjectChannelRow",
    "ProjectRow",
    "RepositoryRow",
    "RequestFactRow",
    "RunRow",
    "SQLAlchemyAttemptRepository",
    "SQLAlchemyChatNoticeRepository",
    "SQLAlchemyChatThreadRepository",
    "SQLAlchemyFactSetRepository",
    "SQLAlchemyGateRecordRepository",
    "SQLAlchemyGatewayReadRepository",
    "SQLAlchemyHarnessRepository",
    "SQLAlchemyHistoryQuery",
    "SQLAlchemyInstanceHoldRepository",
    "SQLAlchemyMetricCalculationRepository",
    "SQLAlchemyProjectChannelRepository",
    "SQLAlchemyProjectRepository",
    "SQLAlchemyRepositoryRepository",
    "SQLAlchemyResultVersionRepository",
    "SQLAlchemyRunRepository",
    "SQLAlchemyStepRunRepository",
    "SQLAlchemyTemplateVersionRepository",
    "SQLAlchemyTrajectoryRepository",
    "SQLAlchemyUnitOfWork",
    "SessionUnitOfWork",
    "StepRunRow",
    "TemplateRow",
    "TemplateVersionRow",
    "TrajectoryRow",
    "UsageFactRow",
    "create_engine_from",
    "create_session_factory",
    "open_writer_ports",
]
