"""The facts sweep fills the fact set of any ended harness attempt that has none."""

from __future__ import annotations

from datetime import timedelta

from orchestrator.application.jobs.facts_sweep import run_facts_sweep
from orchestrator.application.use_cases.record_attempt_facts import LOG_SWEPT
from tests.unit.application.test_record_attempt_facts import LOG, an_ended
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.log_facts import facts_ports
from tests.unit.fakes.runs import FakeAttemptRepository


def test_one_set_is_written_and_a_second_sweep_writes_nothing() -> None:
    attempt = an_ended(ended_at=EPOCH)
    attempts = FakeAttemptRepository([attempt])
    ports = facts_ports(existing=[LOG], attempts=attempts)
    assert run_facts_sweep(ports) == [attempt.id]
    assert run_facts_sweep(ports) == []
    assert len(ports.facts.sets) == 1  # type: ignore[attr-defined]


def test_a_swept_log_is_a_failed_set() -> None:
    attempts = FakeAttemptRepository([an_ended(ended_at=EPOCH)])
    ports = facts_ports(attempts=attempts)
    run_facts_sweep(ports)
    only = ports.facts.sets[0]  # type: ignore[attr-defined]
    assert (only.status, only.reason) == ("failed", LOG_SWEPT)


def test_a_running_attempt_and_one_with_no_harness_are_skipped() -> None:
    attempts = FakeAttemptRepository(
        [an_ended(), an_ended(ended_at=EPOCH, harness=None), an_ended(ended_at=EPOCH, harness="")]
    )
    assert run_facts_sweep(facts_ports(existing=[LOG], attempts=attempts)) == []


def test_the_batch_bounds_the_work_and_the_oldest_end_goes_first() -> None:
    old = an_ended(ended_at=EPOCH)
    new = an_ended(ended_at=EPOCH + timedelta(hours=1))
    repository = FakeFactSetRepository(FakeAttemptRepository([new, old]))
    ports = facts_ports(existing=[LOG], repository=repository)
    assert run_facts_sweep(ports, batch=1) == [old.id]
    assert run_facts_sweep(ports, batch=1) == [new.id]
