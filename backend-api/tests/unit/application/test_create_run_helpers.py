"""The helpers `create_run` calls, moved to `create_run_helpers` unchanged."""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.templates.plan_model import Plan
from orchestrator.application.use_cases import create_run
from orchestrator.application.use_cases.create_run_helpers import (
    _partition_branch,
    _step_run,
    _trace_name,
    _working_branch,
)
from orchestrator.domain.values import PlannedRow
from tests.unit.application.test_create_run_use_case import base_request

RUN_ID = UUID(int=1)


def test_trace_name_names_template_version_and_branch() -> None:
    assert _trace_name(base_request()).startswith("run repo-init@1 ")


def test_branch_helpers_read_the_first_declared_branch() -> None:
    plan = Plan(plan_ref="x", branches={"spec/a": "spec/a-1", "spec/b": "spec/b-1"})
    empty = Plan(plan_ref="x")

    assert _partition_branch(plan, "main") == "spec/a"
    assert _working_branch(plan) == "spec/a-1"
    assert _partition_branch(empty, "main") == "main"
    assert _working_branch(empty) is None


def test_step_run_copies_the_planned_row() -> None:
    row = PlannedRow.model_construct(
        seq=3,
        path="a/b",
        label="L",
        kind="agent",
        gate="deterministic",
        status="planned",
        reason=None,
        with_resolved={},
        frame=None,
        story_id="1.1",
        role="dev",
    )

    step = _step_run(RUN_ID, row)

    assert (step.run_id, step.seq, step.path, step.story_id, step.role) == (
        RUN_ID,
        3,
        "a/b",
        "1.1",
        "dev",
    )


def test_create_run_still_exports_the_partition_helper() -> None:
    assert create_run._partition_branch is _partition_branch
