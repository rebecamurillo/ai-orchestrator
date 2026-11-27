"""`initiative_advance.advance_initiative` and `sweep_advances` (epic 8 story 1, AC5-AC13).

Each decision is monkeypatched in; the real `next_run` is `test_initiative_next.py`'s.
Epic 8 story 3 (2026-11-25) replaced the stub `next_run`."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases import initiative_advance as module
from orchestrator.application.use_cases.create_run import CreateRunRequest
from orchestrator.application.use_cases.initiative_advance import (
    AdvancePorts,
    Blocked,
    NextRun,
    advance_initiative,
    sweep_advances,
)
from orchestrator.domain.entities.initiative import Initiative, InitiativeKey
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_world import SPEC_TEMPLATE, SPEC_VERSION, InitiativeWorld
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.engine import FakeWorkflowEngine

NEW_ROUND = 2


class Case:
    """A world holding an initiative, a from-Run and one advance."""

    def __init__(self, *, run_status: str = "done", round_: int = 1, **initiative: Any) -> None:
        self.world = InitiativeWorld()
        self.initiative: Initiative = self.world.seed(self.world.initiative(**initiative))
        self.from_run: Run = build_run(
            run_status,  # type: ignore[arg-type]
            initiative_id=self.initiative.id,
            initiative_round=round_,
            initiative_position=1,
        )
        self.world.runs.add(self.from_run)
        self.advance = InitiativeAdvance(
            id=new_id(),
            initiative_id=self.initiative.id,
            from_run_id=self.from_run.id,
            round=round_,
            position=1,
        )
        self.world.advances.add(self.advance)
        self.redacted: list[str] = []
        self.ports = AdvancePorts(
            initiatives=self.world.initiatives,
            advances=self.world.advances,
            runs=self.world.runs,
            create_run=self.world.create_ports,
            uow=self.world.uow,
            clock=self.world.harness.clock,
            redact=lambda text: text.replace("s3cret", "***"),
        )

    def stored(self) -> InitiativeAdvance:
        [advance] = [a for a in self.world.advances.advances if a.id == self.advance.id]
        return advance

    def returns(self, monkeypatch: pytest.MonkeyPatch, answer: object) -> list[object]:
        calls: list[object] = []

        def fake(*args: object) -> object:
            calls.append(args)
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(module, "next_run", fake)
        return calls

    def request(self, position: int = 7) -> CreateRunRequest:
        return CreateRunRequest(
            template_name=SPEC_TEMPLATE,
            template_version=SPEC_VERSION,
            project_id=self.world.project.id,
            repository_id=self.world.hub.id,
            base_branch=self.world.hub.default_branch,
            budget_usd=self.world.project.default_budget_usd,
            harness="claude",
            model="sonnet",
            conflict_consent=True,
            inputs={
                "slug": "snake-v3",
                "branch": "spec/snake-v3",
                "first_turn": "hello",
                "initiative_folder": "initiatives",
            },
            initiative=InitiativeKey(
                initiative_id=self.initiative.id, round=self.initiative.round, position=position
            ),
        )

    def runs_of_key(self, position: int = 7) -> list[Run]:
        return [
            r
            for r in self.world.runs.runs.values()
            if r.initiative_id == self.initiative.id and r.initiative_position == position
        ]


def test_ac5_a_cancelled_initiative_consumes_without_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    case.world.initiatives.update(
        case.initiative.model_copy(update={"cancelled_at": case.world.harness.clock.now()})
    )
    calls = case.returns(monkeypatch, None)

    advance_initiative(case.ports, case.advance.id)

    assert case.stored().consumed_at is not None
    assert calls == []
    assert case.runs_of_key() == []


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_ac6_a_failed_or_cancelled_from_run_consumes_without_next_run(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    case = Case(run_status=status)
    calls = case.returns(monkeypatch, NextRun(case.request()))

    advance_initiative(case.ports, case.advance.id)

    assert calls == []
    assert case.stored().consumed_at is not None
    assert case.runs_of_key() == []


def test_ac7_a_consumed_advance_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    case.returns(monkeypatch, None)
    advance_initiative(case.ports, case.advance.id)
    calls_before = list(case.world.uow.calls)
    case.world.advances.calls.clear()
    case.world.initiatives.calls.clear()

    advance_initiative(case.ports, case.advance.id)

    assert ("update", case.advance.id) not in case.world.advances.calls
    assert not [c for c in case.world.initiatives.calls if c[0] == "get_for_update"]
    assert case.world.uow.calls == calls_before


def test_a_missing_advance_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    calls = case.returns(monkeypatch, None)

    advance_initiative(case.ports, new_id())

    assert calls == [] and case.stored().consumed_at is None


def test_ac8_a_superseded_round_consumes_without_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case(round=2)
    case.world.advances.advances[0] = case.advance.model_copy(update={"round": 1})
    case.world.initiatives.update(case.initiative.model_copy(update={"round": 2}))
    calls = case.returns(monkeypatch, None)

    advance_initiative(case.ports, case.advance.id)

    assert calls == []
    assert case.stored().consumed_at is not None


@pytest.mark.parametrize("error", [RuntimeError("boom s3cret"), ValueError("plain")])
def test_ac9_a_raising_next_run_blocks_the_advance_with_a_redacted_reason(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    case = Case()
    case.returns(monkeypatch, error)

    advance_initiative(case.ports, case.advance.id)

    stored = case.stored()
    assert stored.consumed_at is None
    assert stored.blocked_reason is not None
    assert stored.blocked_reason.startswith("advance failed:")
    assert "s3cret" not in stored.blocked_reason
    assert case.runs_of_key() == []


def test_ac9_a_failure_after_the_advance_was_consumed_leaves_it_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case()

    def consume_then_raise(*_a: object) -> object:
        case.world.advances.advances[0] = case.advance.model_copy(
            update={"consumed_at": case.world.harness.clock.now()}
        )
        raise RuntimeError("late")

    monkeypatch.setattr(module, "next_run", consume_then_raise)

    advance_initiative(case.ports, case.advance.id)

    assert case.stored().blocked_reason is None


def test_ac9_a_failure_of_the_advance_itself_missing_on_the_second_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case()

    def drop_then_raise(*_a: object) -> object:
        case.world.advances.advances.clear()
        raise RuntimeError("gone")

    monkeypatch.setattr(module, "next_run", drop_then_raise)

    advance_initiative(case.ports, case.advance.id)

    assert case.world.advances.advances == []


def test_ac10_blocked_keeps_the_advance_open_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case()
    case.returns(monkeypatch, Blocked("x"))

    advance_initiative(case.ports, case.advance.id)

    stored = case.stored()
    assert (stored.blocked_reason, stored.consumed_at) == ("x", None)


def test_ac10_none_for_a_done_from_run_consumes(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    calls = case.returns(monkeypatch, None)

    advance_initiative(case.ports, case.advance.id)

    assert len(calls) == 1
    assert case.stored().consumed_at is not None


def test_ac11_next_run_creates_exactly_one_run_over_two_executions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case()
    case.returns(monkeypatch, NextRun(case.request()))

    advance_initiative(case.ports, case.advance.id)
    assert case.stored().consumed_at is not None
    advance_initiative(case.ports, case.advance.id)

    assert len(case.runs_of_key()) == 1
    assert case.stored().consumed_at is not None


def test_ac11_a_run_that_already_holds_the_key_still_consumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = Case()
    case.world.runs.add(
        build_run(
            "queued",
            initiative_id=case.initiative.id,
            initiative_round=1,
            initiative_position=7,
        )
    )
    case.returns(monkeypatch, NextRun(case.request()))

    advance_initiative(case.ports, case.advance.id)

    assert len(case.runs_of_key()) == 1
    assert case.stored().consumed_at is not None


def test_ac11_a_new_round_is_written_in_the_same_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    case.returns(monkeypatch, NextRun(case.request(), new_round=2))

    advance_initiative(case.ports, case.advance.id)

    stored = case.world.initiatives.get(case.initiative.id)
    assert stored is not None and stored.round == NEW_ROUND
    assert stored.updated_at == case.world.harness.clock.now()
    assert case.stored().consumed_at is not None


def test_ac12_every_read_precedes_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    seen: list[list[tuple[str, object]]] = []

    def probe(*_a: object) -> None:
        seen.append(list(case.world.initiatives.calls))

    monkeypatch.setattr(module, "next_run", probe)

    advance_initiative(case.ports, case.advance.id)

    assert seen and ("get_for_update", case.initiative.id) not in seen[0]
    assert ("get_for_update", case.initiative.id) in case.world.initiatives.calls


@pytest.mark.parametrize("change", ["consumed", "cancelled", "round"])
def test_ac13_a_change_between_the_read_and_the_lock_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    case = Case()
    now = case.world.harness.clock.now()

    def drift(*_a: object) -> NextRun:
        if change == "consumed":
            case.world.advances.advances[0] = case.advance.model_copy(update={"consumed_at": now})
        elif change == "cancelled":
            case.world.initiatives.update(case.initiative.model_copy(update={"cancelled_at": now}))
        else:
            case.world.initiatives.update(case.initiative.model_copy(update={"round": 2}))
        return NextRun(case.request())

    monkeypatch.setattr(module, "next_run", drift)

    advance_initiative(case.ports, case.advance.id)

    assert case.runs_of_key() == []
    assert case.stored().consumed_at is not None or change == "consumed"


def test_the_real_next_run_answers_a_block_for_an_entry_with_no_transition() -> None:
    """Epic 8 story 3, 2026-11-25: `next_run` is `initiative_next.decide`, not the stub's `None`."""
    case = Case()  # position 1 of the fixture sequence is its build, which creates nothing
    assert module.next_run(case.ports, case.initiative, case.advance, case.from_run) is None
    odd = case.initiative.sequence.workflows[1].model_copy(
        update={"type": "auto", "shown_as": "workflow"}
    )
    sequence = case.initiative.sequence.model_copy(
        update={"workflows": (case.initiative.sequence.workflows[0], odd, odd)}
    )
    initiative = case.initiative.model_copy(update={"sequence": sequence})

    later = case.advance.model_copy(update={"position": 2})

    decision = module.next_run(case.ports, initiative, later, case.from_run)

    assert decision == Blocked("no transition for build")


def test_a_vanished_from_run_is_a_failure_that_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    case.world.runs.runs.pop(case.from_run.id)
    case.returns(monkeypatch, None)

    advance_initiative(case.ports, case.advance.id)

    stored = case.stored()
    assert stored.consumed_at is None and (stored.blocked_reason or "").startswith(
        "advance failed:"
    )


def test_sweep_enqueues_only_the_unheld_unblocked_advances() -> None:
    case = Case()
    held = case.advance
    other = held.model_copy(update={"id": new_id(), "position": 2})
    blocked = held.model_copy(update={"id": new_id(), "position": 3, "blocked_reason": "x"})
    free = held.model_copy(update={"id": new_id(), "position": 4})
    for advance in (other, blocked, free):
        case.world.advances.add(advance)
    engine = FakeWorkflowEngine()

    sweep_advances(case.ports, engine, frozenset({held.id, other.id}))

    assert engine.calls == [("enqueue_advance", free.id)]


def test_without_a_redactor_the_reason_is_kept_as_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    case = Case()
    ports = replace(case.ports, redact=AdvancePorts.__dataclass_fields__["redact"].default)
    case.returns(monkeypatch, RuntimeError("plain s3cret"))

    advance_initiative(ports, case.advance.id)

    assert case.stored().blocked_reason == "advance failed: plain s3cret"
