"""The SQLAlchemy adapters for the initiative ports (AD-36), over the unit of work's session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.initiative import FrozenSequence, Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.infrastructure.db.models.initiative import InitiativeAdvanceRow, InitiativeRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: InitiativeRow) -> Initiative:
    return Initiative(
        id=row.id,
        project_id=row.project_id,
        repository_id=row.repository_id,
        slug=row.slug,
        name=row.name,
        first_message=row.first_message,
        sequence=FrozenSequence.model_validate(row.sequence),
        round=row.round if row.round is not None else 1,
        cancelled_at=row.cancelled_at,
        branch_cleanup_error=row.branch_cleanup_error,
        pr_merged_at=row.pr_merged_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_opened_at=row.last_opened_at,
    )


def row_values(initiative: Initiative) -> dict[str, Any]:
    """Every column of `initiative`, keyed by name — except the database-owned `updated_at`."""
    return {
        "id": initiative.id,
        "project_id": initiative.project_id,
        "repository_id": initiative.repository_id,
        "slug": initiative.slug,
        "name": initiative.name,
        "first_message": initiative.first_message,
        "sequence": initiative.sequence.model_dump(mode="json"),
        "round": initiative.round,
        "cancelled_at": initiative.cancelled_at,
        "branch_cleanup_error": initiative.branch_cleanup_error,
        "pr_merged_at": initiative.pr_merged_at,
        "created_at": initiative.created_at,
        "last_opened_at": initiative.last_opened_at,
    }


def advance_to_entity(row: InitiativeAdvanceRow) -> InitiativeAdvance:
    return InitiativeAdvance(
        id=row.id,
        initiative_id=row.initiative_id,
        from_run_id=row.from_run_id,
        round=row.round,
        position=row.position,
        blocked_reason=row.blocked_reason,
        consumed_at=row.consumed_at,
    )


def advance_row_values(advance: InitiativeAdvance) -> dict[str, Any]:
    return {
        "id": advance.id,
        "initiative_id": advance.initiative_id,
        "from_run_id": advance.from_run_id,
        "round": advance.round,
        "position": advance.position,
        "blocked_reason": advance.blocked_reason,
        "consumed_at": advance.consumed_at,
    }


class SQLAlchemyInitiativeRepository:
    """Stored initiatives, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, initiative: Initiative) -> None:
        self._session.add(InitiativeRow(**row_values(initiative)))
        # emitted now, so a Run that references this initiative cannot be inserted first
        self._session.flush()

    def get(self, initiative_id: UUID) -> Initiative | None:
        row = self._session.get(InitiativeRow, initiative_id)
        return None if row is None else to_entity(row)

    def get_for_update(self, initiative_id: UUID) -> Initiative | None:
        statement = (
            select(InitiativeRow)
            .where(InitiativeRow.id == initiative_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        return None if row is None else to_entity(row)

    def update(self, initiative: Initiative) -> None:
        row = self._session.get(InitiativeRow, initiative.id)
        if row is None:
            raise ValueError(f"no initiative with id {initiative.id} is stored")
        for column, value in row_values(initiative).items():
            if column != "id":
                setattr(row, column, value)

    def list(self, *, project_id: UUID | None = None) -> list[Initiative]:
        statement = select(InitiativeRow)
        if project_id is not None:
            statement = statement.where(InitiativeRow.project_id == project_id)
        rows = self._session.scalars(
            statement.order_by(InitiativeRow.created_at.desc(), InitiativeRow.id.desc())
        ).all()
        return [to_entity(row) for row in rows]

    def get_open_by_slug(self, repository_id: UUID, slug: str) -> Initiative | None:
        row = self._session.scalars(
            select(InitiativeRow).where(
                InitiativeRow.repository_id == repository_id,
                InitiativeRow.slug == slug,
                InitiativeRow.cancelled_at.is_(None),
            )
        ).first()
        return None if row is None else to_entity(row)

    def list_by_slug(self, repository_id: UUID, slug: str) -> list[Initiative]:
        return self._in_creation_order(
            InitiativeRow.repository_id == repository_id, InitiativeRow.slug == slug
        )

    def list_open_for_package(self, project_id: UUID, package_name: str) -> list[Initiative]:
        return self._in_creation_order(
            InitiativeRow.project_id == project_id,
            InitiativeRow.cancelled_at.is_(None),
            InitiativeRow.pr_merged_at.is_(None),
            InitiativeRow.sequence["package"].astext == package_name,
        )

    def _in_creation_order(self, *conditions: Any) -> list[Initiative]:
        rows = self._session.scalars(
            select(InitiativeRow)
            .where(*conditions)
            .order_by(InitiativeRow.created_at, InitiativeRow.id)
        ).all()
        return [to_entity(row) for row in rows]


class SQLAlchemyInitiativeAdvanceRepository:
    """Stored advances, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, advance: InitiativeAdvance) -> None:
        self._session.add(InitiativeAdvanceRow(**advance_row_values(advance)))
        self._session.flush()

    def list_for_initiative(self, initiative_id: UUID) -> list[InitiativeAdvance]:
        rows = self._session.scalars(
            select(InitiativeAdvanceRow)
            .where(InitiativeAdvanceRow.initiative_id == initiative_id)
            .order_by(InitiativeAdvanceRow.round, InitiativeAdvanceRow.position)
        ).all()
        return [advance_to_entity(row) for row in rows]

    def list_unconsumed(self) -> list[InitiativeAdvance]:
        rows = self._session.scalars(
            select(InitiativeAdvanceRow)
            .where(InitiativeAdvanceRow.consumed_at.is_(None))
            .order_by(
                InitiativeAdvanceRow.round, InitiativeAdvanceRow.position, InitiativeAdvanceRow.id
            )
        ).all()
        return [advance_to_entity(row) for row in rows]
