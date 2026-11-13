"""In-memory fact repositories — the shared fakes for `FactSetRepository` and
`GatewayReadRepository` (AD-18). Append-only: no update, no delete."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, GatewayRead, UsageFact
from orchestrator.domain.ports.facts import FactSetRepository, GatewayReadRepository
from tests.unit.fakes.runs import FakeAttemptRepository


class FakeFactSetRepository:
    def __init__(self, attempts: FakeAttemptRepository | None = None) -> None:
        self.attempts = attempts
        self.sets: list[FactSet] = []
        self.stored: dict[UUID, AttemptFacts] = {}
        self.calls: list[tuple[str, object]] = []

    def add(self, fact_set: FactSet, facts: AttemptFacts) -> bool:
        self.calls.append(("add", fact_set.attempt_id))
        key = (fact_set.attempt_id, fact_set.extractor, fact_set.extractor_version)
        if any((s.attempt_id, s.extractor, s.extractor_version) == key for s in self.sets):
            return False
        self.sets.append(fact_set)
        self.stored[fact_set.id] = facts
        return True

    def list_for_attempt(self, attempt_id: UUID) -> list[FactSet]:
        return [s for s in self.sets if s.attempt_id == attempt_id]

    def rows(self, fact_set_id: UUID) -> AttemptFacts:
        return self.stored[fact_set_id]

    def subscriptions(self, run_ids: Sequence[UUID]) -> dict[UUID, list[bool | None]]:
        found: dict[UUID, list[bool | None]] = {}
        for s in self.sets:
            if s.run_id in run_ids:
                found.setdefault(s.run_id, []).append(s.subscription)
        return found

    def unrecorded_attempts(self, limit: int) -> list[Attempt]:
        self.calls.append(("unrecorded_attempts", limit))
        assert self.attempts is not None
        recorded = {s.attempt_id for s in self.sets}
        found = [
            a
            for a in self.attempts.attempts.values()
            if a.ended_at is not None and a.harness and a.id not in recorded
        ]
        found.sort(key=lambda a: a.ended_at)  # type: ignore[arg-type, return-value]
        return found[:limit]


class FakeGatewayReadRepository:
    def __init__(self) -> None:
        self.reads: list[tuple[GatewayRead, tuple[UsageFact, ...]]] = []

    def add(self, read: GatewayRead, usage: tuple[UsageFact, ...]) -> None:
        self.reads.append((read, usage))

    def list_for_attempt(self, attempt_id: UUID) -> list[GatewayRead]:
        found = [r for r, _ in self.reads if r.attempt_id == attempt_id]
        return sorted(found, key=lambda r: r.read_at, reverse=True)

    def usage(self, read_id: UUID) -> tuple[UsageFact, ...]:
        return next((u for r, u in self.reads if r.id == read_id), ())


assert isinstance(FakeFactSetRepository(), FactSetRepository)
assert isinstance(FakeGatewayReadRepository(), GatewayReadRepository)
