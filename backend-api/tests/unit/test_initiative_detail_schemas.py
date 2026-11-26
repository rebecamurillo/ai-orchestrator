"""The initiative detail's own `*Out.of`, field for field (story 6, epic 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.api.schemas import initiative_detail, initiatives
from orchestrator.api.schemas.initiative_detail import (
    DetailStepOut,
    DetailWorkflowOut,
    HubRefOut,
    ProjectRefOut,
    SessionEntryOut,
    StepFileOut,
    TurnOut,
    WorkflowFileOut,
)
from orchestrator.application.use_cases.initiative_view_types import (
    DetailStep,
    DetailWorkflow,
    HubRef,
    ProjectRef,
    SessionEntry,
    StepFile,
    Turn,
    WorkflowFile,
)

AT = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)
ID = UUID("01960000-0000-7000-9000-000000000001")
STAMP = "2026-11-24T21:30:00Z"


def test_a_turn_maps_every_field() -> None:
    turn = Turn(ID, ID, 2, 3, "failed", "m", "r", AT, AT, "gate", 4, "ux", "opus", "agent exited 1")

    assert TurnOut.of(turn).model_dump(mode="json") == {
        "attempt_id": str(ID),
        "run_id": str(ID),
        "round": 2,
        "n": 3,
        "status": "failed",
        "message": "m",
        "reply": "r",
        "started_at": STAMP,
        "ended_at": STAMP,
        "author": "gate",
        "defects": 4,
        "owner": "ux",
        "model": "opus",
        "failure_reason": "agent exited 1",
    }


def test_a_file_maps_its_run_time_and_mark() -> None:
    file = StepFile("a.md", False, ID, AT, True)

    assert StepFileOut.of(file).model_dump(mode="json") == {
        "path": "a.md",
        "draft": False,
        "run_id": str(ID),
        "time": STAMP,
        "changed": True,
    }


def test_a_step_maps_its_new_fields() -> None:
    step = DetailStep(
        "merge",
        "automatic",
        None,
        None,
        None,
        "waiting for her",
        "conflict · 1 file · your turn",
        [],
        [],
        number="1.6",
        agent=None,
        harness="claude",
        model="opus",
        run_id=ID,
        park_seq=7,
        park_kind="merge_conflict",
        park_reason="stopped",
        token="BLK",
        files_state="open",
        conflict_files=["README.md"],
    )

    out = DetailStepOut.of(step).model_dump(mode="json")

    assert {k: out[k] for k in out if k not in ("turns", "files")} == {
        "id": "merge",
        "kind": "automatic",
        "persona": None,
        "skill": None,
        "file": None,
        "status": "waiting for her",
        "line": "conflict · 1 file · your turn",
        "number": "1.6",
        "agent": None,
        "harness": "claude",
        "model": "opus",
        "run_id": str(ID),
        "park_seq": 7,
        "park_kind": "merge_conflict",
        "park_reason": "stopped",
        "token": "BLK",
        "files_state": "open",
        "conflict_files": ["README.md"],
        # story 2 of epic 9, 2026-11-26: the step maps `reopened_after`.
        "reopened_after": None,
    }


def test_a_workflow_maps_its_line_and_files() -> None:
    workflow = DetailWorkflow(
        1, "build", "p/build", 1, "auto", "running", ID, [], "Run done", [WorkflowFile("s.md", ID)]
    )

    out = DetailWorkflowOut.of(workflow).model_dump(mode="json")

    assert out["line"] == "Run done"
    assert out["files"] == [{"path": "s.md", "run_id": str(ID)}]


def test_the_refs_and_a_session_entry_map_field_for_field() -> None:
    assert ProjectRefOut.of(ProjectRef(ID, "Acme")).model_dump(mode="json") == {
        "id": str(ID),
        "name": "Acme",
    }
    assert HubRefOut.of(HubRef(ID, "hub")).model_dump(mode="json") == {"id": str(ID), "slug": "hub"}
    assert WorkflowFileOut.of(WorkflowFile("s.md", ID)).model_dump(mode="json") == {
        "path": "s.md",
        "run_id": str(ID),
    }
    assert SessionEntryOut.of(SessionEntry("spec", "ux", "session", ID, 2, "open")).model_dump(
        mode="json"
    ) == {
        "workflow": "spec",
        "step": "ux",
        "kind": "session",
        "id": str(ID),
        "round": 2,
        "state": "open",
    }


def test_the_classes_the_detail_re_exports_are_the_moved_ones() -> None:
    for name in ("TurnOut", "StepFileOut", "DetailStepOut", "DetailWorkflowOut"):
        assert getattr(initiatives, name) is getattr(initiative_detail, name)
