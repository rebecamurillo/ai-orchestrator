"""The `ProjectRepository` and its siblings: domain entities in, domain entities out.

A repository translates between an entity and its row and does nothing else — no rule, no
decision about what a missing row means. It is built on the session the unit of work
already opened, so a use case's reads and writes share one transaction.
"""

from __future__ import annotations

from orchestrator.infrastructure.db.repositories.projects import SQLAlchemyProjectRepository
from orchestrator.infrastructure.db.repositories.repository import (
    SQLAlchemyRepositoryRepository,
)
from orchestrator.infrastructure.db.repositories.templates import (
    SQLAlchemyTemplateVersionRepository,
)

__all__ = [
    "SQLAlchemyProjectRepository",
    "SQLAlchemyRepositoryRepository",
    "SQLAlchemyTemplateVersionRepository",
]
