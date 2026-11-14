"""A `StepPorts.facts_writes` scope over the shared fact fakes, for the call-site tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from orchestrator.application.use_cases.record_attempt_facts import FactsPorts
from orchestrator.domain.entities.facts import AttemptFacts
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.log_facts import ScriptedLogFacts


class AnyHarness(dict[str, Any]):
    """An extractor registry that answers for every harness name."""

    def __init__(self, extractor: ScriptedLogFacts) -> None:
        super().__init__()
        self.extractor = extractor

    def get(self, key: str, default: Any = None) -> Any:
        return self.extractor


@dataclass
class FactsScope:
    """Callable scope: every entry opens a fresh unit of work over one shared repository."""

    extractor: ScriptedLogFacts = field(default_factory=ScriptedLogFacts)
    repository: FakeFactSetRepository = field(default_factory=FakeFactSetRepository)
    opens: int = 0
    fail_open: bool = False

    @contextmanager
    def __call__(self) -> Iterator[FactsPorts]:
        self.opens += 1
        if self.fail_open:
            raise RuntimeError("no facts scope")
        yield FactsPorts(
            facts=self.repository,
            uow=FakeUnitOfWork(),
            clock=FakeClock(),
            extractors=AnyHarness(self.extractor),
            log_exists=lambda _path: True,
        )


EMPTY = AttemptFacts()
