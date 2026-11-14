"""Store what an attempt did, once, when it ends (AGENTS.md "Data capture", RM-1).

Never raises, and reads and writes no attempt, step or Run status: a fact never decides a
route, a park or a gate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import structlog

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, FactSetStatus
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository
from orchestrator.domain.ports.log_facts import LogFacts
from orchestrator.domain.ports.unit_of_work import UnitOfWork

log = structlog.get_logger(__name__)

NO_EXTRACTOR = "no extractor for {harness}"
NO_LOG = "no log"
LOG_SWEPT = "log swept"
EXTRACT_FAILED = "fact extraction failed"
STORE_FAILED = "fact store failed"


@dataclass(frozen=True)
class FactsPorts:
    """What recording an attempt's facts reaches."""

    facts: FactSetRepository
    uow: UnitOfWork
    clock: Clock
    extractors: Mapping[str, LogFacts]
    log_exists: Callable[[str], bool]
    subscription_auth: bool | None = None


def record_attempt_facts(ports: FactsPorts, attempt: Attempt) -> FactSet | None:
    """One fact set for `attempt`; `None` when it was already stored or could not be."""
    try:
        return _record(ports, attempt)
    except Exception:
        log.exception(STORE_FAILED, run_id=str(attempt.run_id), attempt=attempt.n)
        return None


def _record(ports: FactsPorts, attempt: Attempt) -> FactSet | None:
    harness = attempt.harness or ""
    extractor = ports.extractors.get(harness)
    name, version = (extractor.name, extractor.version) if extractor else (harness or "none", 0)
    status, reason, facts = _extract(ports, attempt, extractor, harness)
    fact_set = FactSet(
        id=new_id(),
        attempt_id=attempt.id,
        run_id=attempt.run_id,
        extractor=name,
        extractor_version=version,
        read_at=ports.clock.now(),
        status=status,
        reason=reason,
        subscription=_subscription(ports, harness),
    )
    with ports.uow:
        stored = ports.facts.add(fact_set, facts)
        ports.uow.commit()
    return fact_set if stored else None


def _subscription(ports: FactsPorts, harness: str) -> bool | None:
    if ports.subscription_auth is None:
        return None
    return harness == "claude" and ports.subscription_auth


def _extract(
    ports: FactsPorts, attempt: Attempt, extractor: LogFacts | None, harness: str
) -> tuple[FactSetStatus, str | None, AttemptFacts]:
    """`(status, reason, rows)`; a log that cannot be read is a `failed` set, not an error."""
    none = AttemptFacts()
    if extractor is None:
        return "failed", NO_EXTRACTOR.format(harness=harness), none
    if attempt.log_path is None:
        return "failed", NO_LOG, none
    if not ports.log_exists(attempt.log_path):
        return "failed", LOG_SWEPT, none
    try:
        facts = extractor.extract(attempt, attempt.log_path)
    except Exception as error:
        log.exception(EXTRACT_FAILED, run_id=str(attempt.run_id), attempt=attempt.n)
        return "failed", f"{type(error).__name__}: {error}", none
    return facts.status, facts.reason, facts
