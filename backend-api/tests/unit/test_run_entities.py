"""The four entities Epic 4 executes over: `Run`, `StepRun`, `Attempt`, `GateRecord`.

Nothing here has behaviour — that is the point of landing them behaviour-free — so what is
checked is what every later story reads without asking: the fields a create must supply,
the defaults a field a later story fills reads before it is filled, and that all four are
frozen, so `apply_step_result` and `signal_run` stay the only writers (AD-8) by making a
mutation impossible rather than by convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree

AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "story",
        "template_version": 1,
        "status": "queued",
        "budget_usd": Decimal("10.000000"),
        "created_at": AT,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_step_run(**overrides: object) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "seq": 1,
        "path": "steps[0]",
        "label": "worktree",
        "kind": "git.worktree",
        "gate": "deterministic",
        "status": "planned",
    }
    fields.update(overrides)
    return StepRun(**fields)  # type: ignore[arg-type]


def an_attempt(**overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "running",
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


def a_gate_record(**overrides: object) -> GateRecord:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "at": AT,
        "event": "start",
        "actor": "machine",
        "text": "run started",
    }
    fields.update(overrides)
    return GateRecord(**fields)  # type: ignore[arg-type]


# ── Run ──────────────────────────────────────────────────────────────────────


def test_a_new_run_carries_what_create_run_supplies() -> None:
    run = a_run()

    assert run.template_name == "story"
    assert run.template_version == 1
    assert run.status == "queued"
    assert run.budget_usd == Decimal("10.000000")
    assert run.created_at == AT


def test_a_new_run_has_spent_nothing_and_estimated_nothing() -> None:
    run = a_run()

    assert run.spend_usd == Decimal("0")
    assert run.manual_estimate_h is None


def test_a_new_run_is_not_parked() -> None:
    run = a_run()

    assert run.park_kind is None
    assert run.park_path is None
    assert run.park_reason is None


def test_a_new_run_has_no_plan_no_engine_reference_and_no_trace() -> None:
    run = a_run()

    assert run.plan_ref is None
    assert run.plan_refs == {}
    assert run.engine_ref == {}
    assert run.trace_id is None


def test_a_new_run_has_no_worktree_no_accepted_path_and_no_compare_url() -> None:
    run = a_run()

    assert run.worktree_path is None
    assert run.worktrees == ()
    assert run.accepted_paths == ()
    assert run.compare_urls == ()


def test_a_new_run_has_no_terminal_session_no_re_review_and_no_active_time() -> None:
    run = a_run()

    assert run.terminal_session is False
    assert run.re_review_done is False
    assert run.active_seconds == 0
    assert run.last_opened_at is None


def test_a_new_run_has_not_started_or_ended() -> None:
    run = a_run()

    assert run.started_at is None
    assert run.ended_at is None


def test_a_run_pins_versions_as_the_template_ref_that_already_exists() -> None:
    run = a_run(pinned_versions=(TemplateRef(name="story", version=1),))

    assert run.pinned_versions == (TemplateRef(name="story", version=1),)


def test_a_run_carries_the_bound_inputs_whole() -> None:
    run = a_run(inputs={"base_branch": "main", "harness": "claude", "model": "sonnet"})

    assert run.inputs["harness"] == "claude"


def test_a_run_carries_its_worktrees_as_value_objects() -> None:
    worktree = Worktree(branch="story/4-1", path="/work/wt/a", created_branch=True, pushed=False)

    run = a_run(worktrees=(worktree,), worktree_path="/work/wt/a")

    assert run.worktrees == (worktree,)
    assert run.worktree_path == "/work/wt/a"


def test_a_run_refuses_a_status_outside_the_run_alphabet() -> None:
    with pytest.raises(ValidationError):
        a_run(status="blocked")


def test_a_run_refuses_a_park_kind_the_brief_does_not_name() -> None:
    with pytest.raises(ValidationError):
        a_run(park_kind="exploded")


def test_a_copy_of_a_run_with_a_new_spend_is_a_new_object() -> None:
    """`update` takes an entity; a frozen Run means the caller built a new one to pass."""
    run = a_run()

    spent = run.model_copy(update={"spend_usd": Decimal("1.500000")})

    assert spent is not run
    assert spent.spend_usd == Decimal("1.500000")
    assert run.spend_usd == Decimal("0")
    assert spent.id == run.id


# ── StepRun ──────────────────────────────────────────────────────────────────


def test_a_planned_row_carries_the_columns_the_planner_wrote() -> None:
    row = a_step_run()

    assert row.seq == 1
    assert row.path == "steps[0]"
    assert row.label == "worktree"
    assert row.kind == "git.worktree"
    assert row.gate == "deterministic"
    assert row.status == "planned"


def test_a_new_row_has_no_reason_no_resolved_inputs_and_no_counters() -> None:
    row = a_step_run()

    assert row.reason is None
    assert row.with_resolved == {}
    assert row.retry_count == 0
    assert row.redispatch_count == 0


def test_a_new_row_has_no_frame_and_no_story_until_the_planner_fills_them() -> None:
    row = a_step_run()

    assert row.frame is None
    assert row.story_id is None


def test_a_row_records_the_frame_and_the_story_epic_6_skips_by() -> None:
    row = a_step_run(frame="steps[3].stories[0]", story_id="4-1")

    assert row.frame == "steps[3].stories[0]"
    assert row.story_id == "4-1"


def test_a_row_takes_the_unvalidated_gate_the_planner_records() -> None:
    assert a_step_run(gate="unvalidated").gate == "unvalidated"


def test_a_row_refuses_a_status_outside_the_step_alphabet() -> None:
    with pytest.raises(ValidationError):
        a_step_run(status="needs_you")


# ── Attempt ──────────────────────────────────────────────────────────────────


def test_a_new_attempt_is_the_nth_execution_of_one_row() -> None:
    attempt = an_attempt()

    assert attempt.n == 1
    assert attempt.status == "running"


def test_a_new_attempt_has_neither_half_of_the_shas_mark_started_writes() -> None:
    attempt = an_attempt()

    assert attempt.started_at is None
    assert attempt.ended_at is None
    assert attempt.start_sha is None
    assert attempt.end_sha is None
    assert attempt.frozen_test_files is None


def test_a_new_attempt_has_no_log_no_exit_code_and_no_output() -> None:
    attempt = an_attempt()

    assert attempt.log_path is None
    assert attempt.exit_code is None
    assert attempt.output_ref is None
    assert attempt.engine_ref == {}


def test_a_new_attempt_carries_none_of_the_agent_extras() -> None:
    attempt = an_attempt()

    assert attempt.harness is None
    assert attempt.model is None
    assert attempt.session_id is None
    assert attempt.pgid is None
    assert attempt.tokens_in is None
    assert attempt.tokens_out is None
    assert attempt.cost_usd is None
    assert attempt.cost_provisional is False


def test_an_agent_attempt_carries_the_harness_the_model_and_the_usage() -> None:
    attempt = an_attempt(
        harness="claude",
        model="sonnet",
        session_id="abc",
        pgid=4321,
        tokens_in=100,
        tokens_out=200,
        cost_usd=Decimal("0.012345"),
        cost_provisional=True,
    )

    assert attempt.harness == "claude"
    assert attempt.cost_usd == Decimal("0.012345")
    assert attempt.cost_provisional is True


def test_an_attempt_status_is_a_row_status_not_a_second_alphabet() -> None:
    assert an_attempt(status="blocked").status == "blocked"
    with pytest.raises(ValidationError):
        an_attempt(status="needs_you")


def test_an_attempt_records_the_frozen_test_files_of_the_frames_first_try() -> None:
    attempt = an_attempt(frozen_test_files=("tests/unit/a.py",))

    assert attempt.frozen_test_files == ("tests/unit/a.py",)


# ── GateRecord ───────────────────────────────────────────────────────────────


def test_a_gate_record_names_when_what_and_who() -> None:
    record = a_gate_record()

    assert record.at == AT
    assert record.event == "start"
    assert record.actor == "machine"
    assert record.text == "run started"


def test_a_gate_record_has_no_path_no_attempt_and_no_payload_by_default() -> None:
    record = a_gate_record()

    assert record.path is None
    assert record.attempt_n is None
    assert record.payload == {}


@pytest.mark.parametrize("event", ["blocked", "budget_raise", "cancelled"])
def test_a_gate_record_event_is_a_park_kind_a_signal_kind_or_a_lifecycle_event(
    event: str,
) -> None:
    assert a_gate_record(event=event).event == event


def test_a_gate_record_refuses_an_event_none_of_the_three_alphabets_names() -> None:
    with pytest.raises(ValidationError):
        a_gate_record(event="park")


def test_a_gate_record_refuses_an_actor_outside_the_three() -> None:
    with pytest.raises(ValidationError):
        a_gate_record(actor="robot")


def test_a_gate_record_carries_the_accepted_files_a_continue_wrote() -> None:
    record = a_gate_record(
        event="continue", actor="operator", path="steps[2]", attempt_n=2, payload={"accepted": []}
    )

    assert record.path == "steps[2]"
    assert record.attempt_n == 2  # noqa: PLR2004 — the attempt number under test
    assert record.payload == {"accepted": []}


def test_two_gate_records_do_not_share_one_payload() -> None:
    assert a_gate_record().payload is not a_gate_record().payload


# ── frozen ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("entity", "field"),
    [
        (a_run(), "status"),
        (a_step_run(), "status"),
        (an_attempt(), "status"),
        (a_gate_record(), "event"),
    ],
    ids=["run", "step_run", "attempt", "gate_record"],
)
def test_every_entity_is_frozen(entity: object, field: str) -> None:
    with pytest.raises(ValidationError):
        setattr(entity, field, "done")
