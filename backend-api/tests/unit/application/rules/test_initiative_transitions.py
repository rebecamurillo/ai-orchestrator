"""`rules/initiative_transitions`: the pure classification and text rules (epic 8 story 3)."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.preflight.model import Line, PreflightResult
from orchestrator.application.rules import initiative_transitions as rules
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_transition_world import (
    BUILD,
    MERGE,
    SPEC,
    entry,
    sequence,
    spec_steps,
)

SEQUENCE = sequence()
SPEC_ENTRY, MERGE_ENTRY, BUILD_ENTRY = SEQUENCE.workflows


def row(kind: str, step: str | None, **resolved: Any) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=1,
        path=f"{step}",
        label=f"{step}",
        kind=kind,
        gate="human",
        status="done",
        with_resolved={"step": step, **resolved},
    )


def line(check: str, status: str = "fail", text: str = "bad") -> Line:
    return Line(check, status, text)  # type: ignore[arg-type]


def result(*lines: Line, plan_error: PlanError | None = None) -> PreflightResult:
    return PreflightResult(
        lines=lines, start_allowed=False, queue_note="", rows=None, plan_error=plan_error
    )


def test_a_spec_is_interactive_with_a_conversation_step() -> None:
    assert rules.is_spec(SPEC_ENTRY)
    assert not rules.is_spec(MERGE_ENTRY)
    assert not rules.is_spec(BUILD_ENTRY)
    assert not rules.is_spec(entry(SPEC, type_="auto", shown="workflow", steps=spec_steps()))


def test_a_merge_is_a_shown_as_step_interactive_entry_that_is_not_a_spec() -> None:
    assert rules.is_merge(MERGE_ENTRY)
    assert not rules.is_merge(SPEC_ENTRY)
    assert not rules.is_merge(BUILD_ENTRY)
    assert not rules.is_merge(entry(MERGE, type_="interactive", shown="workflow"))


def test_the_spec_index_is_the_last_spec_at_or_before_the_position() -> None:
    assert [rules.spec_index(SEQUENCE, p) for p in range(3)] == [0, 0, 0]
    no_spec = SEQUENCE.model_copy(update={"workflows": (MERGE_ENTRY, BUILD_ENTRY)})
    assert rules.spec_index(no_spec, 1) is None
    two = SEQUENCE.model_copy(
        update={"workflows": (SPEC_ENTRY, SPEC_ENTRY, MERGE_ENTRY, BUILD_ENTRY)}
    )
    assert rules.spec_index(two, 3) == 1


def test_the_first_auto_after_an_index() -> None:
    assert rules.first_auto_after(SEQUENCE, 0) == 2  # noqa: PLR2004
    assert rules.first_auto_after(SEQUENCE, 2) is None
    assert rules.first_auto_after(SEQUENCE, None) is None


def test_the_build_is_the_first_auto_after_the_spec() -> None:
    assert [rules.is_build(SEQUENCE, p) for p in range(3)] == [False, False, True]
    later = SEQUENCE.model_copy(
        update={"workflows": (*SEQUENCE.workflows, entry(BUILD, type_="auto", shown="step"))}
    )
    assert not rules.is_build(later, 3)


def test_owners_follow_the_entrys_step_order_and_foreigners_are_named() -> None:
    assert rules.owners_in_order(["tech", "ux", "gone"], SPEC_ENTRY) == ["ux", "tech"]
    assert rules.foreign_owner(["ux", "deploy", "x"], SPEC_ENTRY) == "deploy"
    assert rules.foreign_owner(["ux"], SPEC_ENTRY) is None


def test_the_tech_step_is_the_one_that_writes_epics_yaml() -> None:
    rows = [
        row("conversation", "intake"),
        row("conversation", "tech", writes=["initiatives/x/epics.yaml"]),
        row("conversation", "last"),
        row("shell", None),
    ]
    assert rules.tech_step(rows) == "tech"


def test_without_an_epics_writer_the_last_conversation_step_is_the_tech_step() -> None:
    rows = [
        row("conversation", "a", writes=["SPEC.md"]),
        row("conversation", "b"),
        row("shell", "z"),
    ]
    assert rules.tech_step(rows) == "b"
    assert rules.tech_step([row("shell", "z")]) is None
    assert rules.tech_step([]) is None


def test_a_spec_file_failure_is_a_defect_and_the_first_other_failure_is_the_block() -> None:
    outcome = result(
        line("epics.yaml", text="not found"),
        line("harness", text="harness not available"),
        line("SPEC.md", text="x: missing"),
        line("branch", status="ok"),
        line("docker", text="no"),
    )

    defects, other = rules.preflight_failure(outcome)

    assert defects == ["epics.yaml: not found", "SPEC.md: x: missing"]
    assert other == "preflight: harness: harness not available"


def test_a_plan_error_is_a_defect_unless_a_line_already_carries_it() -> None:
    error = PlanError(reason="list file not found", item="a.yaml")

    defects, other = rules.preflight_failure(result(plan_error=error))
    assert (defects, other) == ([str(error)], None)

    carried = result(line("epics.yaml", text=str(error)), plan_error=error)
    assert rules.preflight_failure(carried)[0] == [f"epics.yaml: {error}"]


def test_a_clean_preflight_has_no_failure() -> None:
    assert rules.preflight_failure(result(line("branch", status="ok"))) == ([], None)


def test_offered_inputs_keep_declared_non_null_names() -> None:
    offered = {"a": 1, "b": None, "c": "x", "d": 0}

    assert rules.offered_inputs({"a", "b", "d"}, offered) == {"a": 1, "d": 0}


@pytest.mark.parametrize(
    ("message", "count"),
    [("- a\n- b\nplain\n  - nested", 2), ("", 0), ("no bullets", 0)],
)
def test_defects_are_the_lines_starting_with_a_dash_and_a_space(message: str, count: int) -> None:
    assert rules.defect_count(message) == count
