"""The `LogFacts` port: reads one attempt's harness log into facts, without I/O of its own kind."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts


@dataclass(frozen=True)
class LogFactsCapabilities:
    """What an extractor can read out of its harness's log."""

    per_request_usage: bool
    activity: bool
    events: bool
    harness_money_per_model: bool


@runtime_checkable
class LogFacts(Protocol):
    """One harness's extractor. A change of `version` makes its facts a new fact set."""

    name: str
    version: int
    capabilities: LogFactsCapabilities

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        """The facts in the log at `log_path`; raises on a log it cannot read."""
        ...
