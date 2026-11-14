"""The registry of log extractors, keyed by harness name (AGENTS.md "Data capture").

Every extractor is wrapped so an event's command is redacted before it is stored (AD-5).
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ports.catalogue import Catalogue
from orchestrator.domain.ports.log_facts import LogFacts, LogFactsCapabilities
from orchestrator.infrastructure.harness.claude.facts import ClaudeLogFacts
from orchestrator.infrastructure.harness.codex.facts import CodexLogFacts
from orchestrator.infrastructure.harness.fake.facts import FakeLogFacts
from orchestrator.infrastructure.harness.opencode.facts import OpenCodeLogFacts
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue
from orchestrator.infrastructure.process.logs import log_secrets
from orchestrator.infrastructure.redact import redact
from orchestrator.infrastructure.settings import Settings


class RedactingLogFacts:
    """An extractor whose stored commands carry no instance secret."""

    def __init__(self, inner: LogFacts, secrets: tuple[str, ...]) -> None:
        self._inner = inner
        self._secrets = secrets
        self.name: str = inner.name
        self.version: int = inner.version
        self.capabilities: LogFactsCapabilities = inner.capabilities

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        facts = self._inner.extract(attempt, log_path)
        events = tuple(
            event.model_copy(update={"command": self._redacted(event.command)})
            for event in facts.events
        )
        return facts.model_copy(update={"events": events})

    def _redacted(self, command: str | None) -> str | None:
        if command is None:
            return None
        for secret in self._secrets:
            command = redact(command, secret)
        return command


def build_log_facts(settings: Settings) -> dict[str, LogFacts]:
    """The extractors this instance has, by harness name."""
    secrets = log_secrets(settings)
    opencode = RedactingLogFacts(OpenCodeLogFacts(), secrets)
    return {
        "fake": RedactingLogFacts(FakeLogFacts(), secrets),
        "claude": RedactingLogFacts(ClaudeLogFacts(test_run_patterns(PackageCatalogue())), secrets),
        "codex": RedactingLogFacts(CodexLogFacts(), secrets),
        "opencode": opencode,
        "local": opencode,
    }


def test_run_patterns(catalogue: Catalogue) -> tuple[str, ...]:
    """The `test_run_patterns` parameter of method 1 of `activity.test_runs`."""
    entries = {e.id: e for e in catalogue.entries()}
    method = next(m for m in entries["activity.test_runs"].methods if m.n == 1)
    return tuple(str(p) for p in method.parameters["test_run_patterns"])  # type: ignore[attr-defined]


def log_file_exists(path: str) -> bool:
    """Whether a log is still on disk."""
    return Path(path).is_file()
