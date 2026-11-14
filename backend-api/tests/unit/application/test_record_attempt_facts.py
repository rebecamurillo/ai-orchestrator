"""`record_attempt_facts`: one fact set per ended attempt, and it never raises (RM-1)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases.record_attempt_facts import (
    LOG_SWEPT,
    NO_EXTRACTOR,
    NO_LOG,
    record_attempt_facts,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, UsageFact
from orchestrator.domain.ids import new_id
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.log_facts import ScriptedLogFacts, facts_ports
from tests.unit.fakes.runs import FakeAttemptRepository

LOG = "/work/logs/1.log"


def an_ended(**over: Any) -> Attempt:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "done",
        "harness": "fake",
        "log_path": LOG,
    }
    fields.update(over)
    return Attempt(**fields)


ROWS = AttemptFacts(usage=(UsageFact(source="harness", usage_class="output", tokens=5),))


def test_the_extractors_rows_are_stored_under_one_ok_set() -> None:
    ports = facts_ports({"fake": ScriptedLogFacts(ROWS)}, existing=[LOG])
    attempt = an_ended()
    stored = record_attempt_facts(ports, attempt)
    assert stored is not None
    assert (stored.status, stored.extractor, stored.extractor_version) == ("ok", "fake", 1)
    assert stored.run_id == attempt.run_id
    assert stored.read_at == ports.clock.now()
    assert ports.facts.rows(stored.id) == ROWS  # type: ignore[attr-defined]
    assert ports.uow.committed  # type: ignore[attr-defined]


def test_a_partial_extraction_carries_its_status_and_reason() -> None:
    partial = AttemptFacts(status="partial", reason="half a log")
    ports = facts_ports({"fake": ScriptedLogFacts(partial)}, existing=[LOG])
    stored = record_attempt_facts(ports, an_ended())
    assert stored is not None
    assert (stored.status, stored.reason) == ("partial", "half a log")


def test_an_extractor_that_raises_leaves_a_failed_set_naming_why() -> None:
    boom = ScriptedLogFacts(raises=ValueError("bad line"))
    ports = facts_ports({"fake": boom}, existing=[LOG])
    stored = record_attempt_facts(ports, an_ended())
    assert stored is not None
    assert stored.status == "failed"
    assert stored.reason is not None and "bad line" in stored.reason


def test_a_harness_without_an_extractor_is_a_failed_set() -> None:
    ports = facts_ports({"fake": ScriptedLogFacts()}, existing=[LOG])
    stored = record_attempt_facts(ports, an_ended(harness="claude"))
    assert stored is not None
    assert (stored.status, stored.reason) == ("failed", NO_EXTRACTOR.format(harness="claude"))
    assert (stored.extractor, stored.extractor_version) == ("claude", 0)


def test_an_attempt_with_no_harness_names_the_extractor_none() -> None:
    stored = record_attempt_facts(facts_ports(), an_ended(harness=None))
    assert stored is not None
    assert stored.extractor == "none"


def test_an_attempt_with_no_log_path_is_a_failed_set() -> None:
    stored = record_attempt_facts(facts_ports(), an_ended(log_path=None))
    assert stored is not None
    assert (stored.status, stored.reason) == ("failed", NO_LOG)


def test_a_log_that_is_gone_is_a_failed_set() -> None:
    extractor = ScriptedLogFacts()
    stored = record_attempt_facts(facts_ports({"fake": extractor}), an_ended())
    assert stored is not None
    assert (stored.status, stored.reason) == ("failed", LOG_SWEPT)
    assert extractor.calls == []


def test_a_second_call_for_the_same_attempt_writes_nothing() -> None:
    ports = facts_ports(existing=[LOG])
    attempt = an_ended()
    assert record_attempt_facts(ports, attempt) is not None
    assert record_attempt_facts(ports, attempt) is None
    assert len(ports.facts.sets) == 1  # type: ignore[attr-defined]


def test_a_store_that_raises_is_logged_and_returns_none() -> None:
    class Failing(FakeFactSetRepository):
        def add(self, *_args: Any) -> bool:
            raise RuntimeError("database is down")

    ports = facts_ports(existing=[LOG], repository=Failing())
    assert record_attempt_facts(ports, an_ended()) is None


def test_no_attempt_is_ever_written() -> None:
    attempts = FakeAttemptRepository()
    ports = replace(facts_ports(existing=[LOG], attempts=attempts))
    record_attempt_facts(ports, an_ended())
    assert attempts.calls == []


@pytest.mark.parametrize("harness", ["fake"])
def test_the_extractor_is_asked_for_the_attempts_own_log(harness: str) -> None:
    extractor = ScriptedLogFacts()
    attempt = an_ended(harness=harness)
    record_attempt_facts(facts_ports({"fake": extractor}, existing=[LOG]), attempt)
    assert extractor.calls == [(attempt, LOG)]
