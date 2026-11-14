"""The facts sweep: fill the fact set of any ended harness attempt that has none."""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.use_cases.record_attempt_facts import (
    FactsPorts,
    record_attempt_facts,
)

SWEEP_BATCH = 500


def run_facts_sweep(ports: FactsPorts, batch: int = SWEEP_BATCH) -> list[UUID]:
    """The attempt ids a fact set was written for; a second sweep finds nothing to do."""
    with ports.uow:
        pending = ports.facts.unrecorded_attempts(batch)
    return [attempt.id for attempt in pending if record_attempt_facts(ports, attempt) is not None]
