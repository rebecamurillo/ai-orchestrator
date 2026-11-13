"""SQLAlchemy adapters for the fact ports (AGENTS.md "Data capture").

Append-only: neither class has an `update` or a `delete`. `add` on a fact set is one
`INSERT … ON CONFLICT DO NOTHING` on the unique triple, so the attempt tail and the sweep
cannot both write a set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import (
    ActivityFact,
    AttemptFacts,
    EventFact,
    FactSet,
    GapFact,
    GatewayRead,
    RequestFact,
    UsageFact,
)
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.facts import (
    FACT_SET_UNIQUE,
    ActivityFactRow,
    EventFactRow,
    FactSetRow,
    GapFactRow,
    GatewayReadRow,
    RequestFactRow,
    UsageFactRow,
)
from orchestrator.infrastructure.db.models.run import AttemptRow
from orchestrator.infrastructure.db.repositories.attempts import to_entity as attempt_entity

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def _fields(model: Any) -> dict[str, Any]:
    return dict(model.model_dump())


def _usage_row(usage: UsageFact, **parent: UUID) -> UsageFactRow:
    values = _fields(usage)
    return UsageFactRow(id=new_id(), **parent, **values)


def _set_entity(row: FactSetRow) -> FactSet:
    return FactSet(
        id=row.id,
        attempt_id=row.attempt_id,
        run_id=row.run_id,
        extractor=row.extractor,
        extractor_version=row.extractor_version,
        read_at=row.read_at,
        status=row.status,  # type: ignore[arg-type]
        reason=row.reason,
    )


class SQLAlchemyFactSetRepository:
    """Fact sets and their rows, over one open session. No update, no delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, fact_set: FactSet, facts: AttemptFacts) -> bool:
        statement = (
            postgresql.insert(FactSetRow)
            .values(**_fields(fact_set))
            .on_conflict_do_nothing(constraint=FACT_SET_UNIQUE)
            .returning(FactSetRow.id)
        )
        stored = self._session.execute(statement).scalar_one_or_none()
        if stored is None:
            return False
        parent = {"fact_set_id": stored}
        rows: list[Any] = [_usage_row(usage, **parent) for usage in facts.usage]
        rows += [RequestFactRow(id=new_id(), **parent, **_fields(r)) for r in facts.requests]
        rows += [ActivityFactRow(id=new_id(), **parent, **_fields(a)) for a in facts.activity]
        rows += [
            GapFactRow(id=new_id(), **parent, **{**_fields(g), "gaps_s": list(g.gaps_s)})
            for g in facts.gaps
        ]
        rows += [EventFactRow(id=new_id(), **parent, **_fields(e)) for e in facts.events]
        self._session.add_all(rows)
        return True

    def list_for_attempt(self, attempt_id: UUID) -> list[FactSet]:
        rows = self._session.scalars(
            select(FactSetRow)
            .where(FactSetRow.attempt_id == attempt_id)
            .order_by(FactSetRow.read_at)
        ).all()
        return [_set_entity(row) for row in rows]

    def rows(self, fact_set_id: UUID) -> AttemptFacts:
        def of(model: Any) -> list[Any]:
            return list(
                self._session.scalars(select(model).where(model.fact_set_id == fact_set_id)).all()
            )

        def plain(row: Any, skip: tuple[str, ...] = ("id", "fact_set_id")) -> dict[str, Any]:
            return {
                k: v for k, v in row.__dict__.items() if not k.startswith("_") and k not in skip
            }

        header = self._session.get(FactSetRow, fact_set_id)
        status = "partial" if header is not None and header.status == "partial" else "ok"
        return AttemptFacts(
            status=status,
            reason=header.reason if header is not None else None,
            usage=tuple(
                UsageFact(**plain(r, ("id", "fact_set_id", "gateway_read_id")))
                for r in of(UsageFactRow)
            ),
            requests=tuple(RequestFact(**plain(r)) for r in of(RequestFactRow)),
            activity=tuple(ActivityFact(**plain(r)) for r in of(ActivityFactRow)),
            gaps=tuple(GapFact(**{**plain(r), "gaps_s": tuple(r.gaps_s)}) for r in of(GapFactRow)),
            events=tuple(EventFact(**plain(r)) for r in of(EventFactRow)),
        )

    def unrecorded_attempts(self, limit: int) -> list[Attempt]:
        rows = self._session.scalars(
            select(AttemptRow)
            .where(
                AttemptRow.ended_at.is_not(None),
                AttemptRow.harness.is_not(None),
                AttemptRow.harness != "",
                ~exists().where(FactSetRow.attempt_id == AttemptRow.id),
            )
            .order_by(AttemptRow.ended_at)
            .limit(limit)
        ).all()
        return [attempt_entity(row) for row in rows]


class SQLAlchemyGatewayReadRepository:
    """Gateway reads and their usage rows, over one open session. No update, no delete."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, read: GatewayRead, usage: tuple[UsageFact, ...]) -> None:
        self._session.add(GatewayReadRow(**_fields(read)))
        # no relationship() ties the two mappers, so the unit of work may insert the usage
        # rows first and break their foreign key: the read is flushed before they are added
        self._session.flush()
        self._session.add_all(_usage_row(u, gateway_read_id=read.id) for u in usage)

    def list_for_attempt(self, attempt_id: UUID) -> list[GatewayRead]:
        rows = self._session.scalars(
            select(GatewayReadRow)
            .where(GatewayReadRow.attempt_id == attempt_id)
            # the gate figure takes the newest read: two reads stamped alike are told apart
            # by their UUIDv7 ids, never by whatever order postgres returns them in
            .order_by(GatewayReadRow.read_at.desc(), GatewayReadRow.id.desc())
        ).all()
        return [
            GatewayRead.model_validate(
                {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
            )
            for r in rows
        ]

    def usage(self, read_id: UUID) -> tuple[UsageFact, ...]:
        rows = self._session.scalars(
            select(UsageFactRow).where(UsageFactRow.gateway_read_id == read_id)
        ).all()
        skip = ("id", "fact_set_id", "gateway_read_id")
        return tuple(
            UsageFact(
                **{k: v for k, v in r.__dict__.items() if not k.startswith("_") and k not in skip}
            )
            for r in rows
        )
