"""A scripted `LogFacts` extractor and a `FactsPorts` builder over the shared fakes (AD-18)."""

from __future__ import annotations

from collections.abc import Iterable

from orchestrator.application.use_cases.record_attempt_facts import FactsPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ports.log_facts import LogFacts, LogFactsCapabilities
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.runs import FakeAttemptRepository


class ScriptedLogFacts:
    def __init__(
        self,
        facts: AttemptFacts | None = None,
        raises: Exception | None = None,
        name: str = "fake",
        version: int = 1,
    ) -> None:
        self.facts = facts if facts is not None else AttemptFacts()
        self.raises = raises
        self.name = name
        self.version = version
        self.capabilities = LogFactsCapabilities(False, False, False, False)
        self.calls: list[tuple[Attempt, str]] = []

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        self.calls.append((attempt, log_path))
        if self.raises is not None:
            raise self.raises
        return self.facts


def facts_ports(
    extractors: dict[str, LogFacts] | None = None,
    existing: Iterable[str] = (),
    attempts: FakeAttemptRepository | None = None,
    repository: FakeFactSetRepository | None = None,
) -> FactsPorts:
    present = set(existing)
    return FactsPorts(
        facts=repository if repository is not None else FakeFactSetRepository(attempts),
        uow=FakeUnitOfWork(),
        clock=FakeClock(),
        extractors=extractors if extractors is not None else {"fake": ScriptedLogFacts()},
        log_exists=lambda path: path in present,
    )


assert isinstance(ScriptedLogFacts(), LogFacts)
