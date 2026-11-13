"""`open_spend_ports` wires the fact-set repository the budget gate reads (story 6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.infrastructure.db.repositories import SQLAlchemyFactSetRepository
from orchestrator.infrastructure.db.writers import open_spend_ports


class Session:
    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class Gateway:
    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        return AttemptSpend(
            usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
        )


def factory() -> Any:
    return Session()


def test_the_scope_carries_the_fact_set_repository() -> None:
    with open_spend_ports(factory, Gateway()) as ports:
        assert isinstance(ports.fact_sets, SQLAlchemyFactSetRepository)
