"""Each initiative `*Out.of`, field for field (story 4, epic 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.api.schemas.board_view import CardOut, InitiativeTagOut
from orchestrator.api.schemas.initiatives import (
    InitiativeDetailOut,
    InitiativeListOut,
    InitiativeRowOut,
)
from orchestrator.application.use_cases.initiative_view_types import (
    Column,
    DetailRun,
    DetailStep,
    DetailWorkflow,
    InitiativeDetail,
    InitiativeList,
    InitiativeRow,
    InitiativeTag,
    ListCounts,
    StepFile,
    Turn,
    WorkflowFoot,
)
from orchestrator.application.use_cases.run_view_types import Card
from orchestrator.domain.ids import new_id

AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
ID = UUID("01960000-0000-7000-9000-000000000001")
PARK_SEQ = 3


def a_row() -> InitiativeRow:
    return InitiativeRow(
        id=ID,
        project_id=ID,
        project_name="Acme",
        repository_id=ID,
        repo_tag=("hub",),
        slug="snake",
        name="Snake",
        status="running",
        step="intake",
        reason="",
        workflow="spec",
        position=1,
        workflow_count=2,
        workflows=(
            WorkflowFoot("spec", "interactive", "ongoing"),
            WorkflowFoot("build", "auto", None),
        ),
        line="your turn · conversation, 2 turns",
        progress="step 1 of 3",
        attention="your_turn",
        updated_at=AT,
    )


def test_a_row_maps_every_field_and_turns_tuples_into_lists() -> None:
    out = InitiativeRowOut.of(a_row()).model_dump(mode="json")

    assert out["repo_tag"] == ["hub"]
    assert out["workflows"] == [
        {"workflow": "spec", "type": "interactive", "state": "ongoing"},
        {"workflow": "build", "type": "auto", "state": None},
    ]
    assert out["updated_at"] == "2026-11-24T09:00:00Z"
    assert out["attention"] == "your_turn"
    assert out["line"] == "your turn · conversation, 2 turns"


def test_the_list_maps_items_columns_and_counts() -> None:
    view = InitiativeList(
        items=[a_row()],
        columns=[Column("spec", "interactive")],
        counts=ListCounts(ongoing=1, need_you=1, oldest_wait_at=AT, cancelled=0),
    )

    out = InitiativeListOut.of(view).model_dump(mode="json")

    assert out["columns"] == [{"workflow": "spec", "type": "interactive"}]
    assert out["counts"] == {
        "ongoing": 1,
        "need_you": 1,
        "oldest_wait_at": "2026-11-24T09:00:00Z",
        "cancelled": 0,
    }
    assert out["next_cursor"] is None
    assert len(out["items"]) == 1


def test_the_detail_maps_workflows_steps_turns_files_and_runs() -> None:
    attempt_id, run_id = new_id(), new_id()
    step = DetailStep(
        id="intake",
        kind="conversation",
        persona="analyst",
        skill="s",
        file="PRD.md",
        status="waiting for her",
        line="",
        turns=[Turn(attempt_id, run_id, 1, 1, "done", "hi", "hello", AT, AT)],
        files=[StepFile("initiatives/snake/PRD.md", True)],
    )
    detail = InitiativeDetail(
        row=a_row(),
        first_message="make it",
        round=1,
        created_at=AT,
        cancelled_at=None,
        branch_cleanup_error=None,
        pr_merged_at=None,
        package="p",
        sha="abc",
        park_seq=PARK_SEQ,
        workflows=[
            DetailWorkflow(1, "spec", "p/spec", 2, "interactive", "needs_you", run_id, [step])
        ],
        runs=[DetailRun(run_id, "p/spec", 2, 1, 1, "needs_you", AT)],
    )

    out = InitiativeDetailOut.of(detail).model_dump(mode="json")

    assert out["park_seq"] == PARK_SEQ
    assert out["status"] == "running"
    (workflow,) = out["workflows"]
    assert workflow["run_id"] == str(run_id)
    (mapped,) = workflow["steps"]
    # Revised by story 6 of epic 7 (2026-11-22): the turn gains `author`, `defects`, `owner`,
    # `model` and `failure_reason`; every old key keeps its value.
    assert mapped["turns"][0] == {
        "attempt_id": str(attempt_id),
        "run_id": str(run_id),
        "round": 1,
        "n": 1,
        "status": "done",
        "message": "hi",
        "reply": "hello",
        "started_at": "2026-11-24T09:00:00Z",
        "ended_at": "2026-11-24T09:00:00Z",
        "author": "operator",
        "defects": None,
        "owner": None,
        "model": None,
        "failure_reason": None,
    }
    # Revised by story 6 of epic 7 (2026-11-22): the file gains `run_id`, `time`, `changed`.
    assert mapped["files"] == [
        {
            "path": "initiatives/snake/PRD.md",
            "draft": True,
            "run_id": None,
            "time": None,
            "changed": False,
        }
    ]
    assert out["runs"][0]["round"] == 1
    assert out["first_message"] == "make it"
    assert out["sha"] == "abc"


def test_a_card_carries_its_initiative_attention_and_template_type() -> None:
    tag = InitiativeTag(id=ID, slug="snake", step="intake", position=1, workflow_count=2)
    card = Card(
        id=ID,
        token="RUN",
        status="running",
        park_kind=None,
        branch="main",
        project_name="Acme",
        repository_slug="hub",
        current_step_label="",
        harness=None,
        template="p/spec",
        version=2,
        progress=None,
        kind_label="p/spec",
        age_seconds=1.0,
        needs_you_since=None,
        initiative=tag,
        attention="your_turn",
        template_type="interactive",
    )

    out = CardOut.of(card)

    assert out.initiative == InitiativeTagOut.of(tag)
    assert (out.attention, out.template_type) == ("your_turn", "interactive")
