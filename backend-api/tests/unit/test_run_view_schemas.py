"""`api/schemas/run_views.py` — the wire shape of the Board and the Run detail (4.12).

`tests/unit/test_run_board_view_router.py` and `test_run_detail_router.py` prove these
render correctly over ASGI; what is asserted here is the part a request-level test would
not think to check on its own: each `.of()` projects every field of its application-layer
counterpart, including the ones easy to forget (`WorktreeOut`, `GateRecordOut`, a `None`
`latest`/`progress`/`alert`/`summary`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.api.schemas.run_views import (
    BoardOut,
    CardOut,
    CostOut,
    GateRecordOut,
    HeaderOut,
    RunDetailOut,
    StepRowOut,
    WorktreeOut,
)
from orchestrator.application.use_cases.run_view_types import (
    BoardColumns,
    BoardCounts,
    BoardView,
    Card,
    Cost,
    Header,
    RunDetailView,
    StepRowView,
    Summary,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree

NOW = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID("01960000-0000-7000-9000-0000000000d1")


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": RUN_ID,
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_card(**overrides: object) -> Card:
    # `initiative`/`initiative_role` were here and `test_a_card_projects_its_initiative_
    # membership` asserted them below: Operator decision 2026-09-30 removed the fan-in
    # Initiative feature entirely, so `Card` carries neither field any more.
    fields: dict[str, object] = {
        "id": RUN_ID,
        "token": "RUN",
        "status": "running",
        "park_kind": None,
        "branch": "main",
        "project_name": "Acme",
        "repository_slug": "acme-app",
        "current_step_label": "build",
        "harness": "claude",
        "template": "repo-init",
        "version": 1,
        "progress": None,
        "kind_label": "repo-init",
        "age_seconds": 12.0,
        "needs_you_since": None,
    }
    fields.update(overrides)
    return Card(**fields)  # type: ignore[arg-type]


def test_a_worktree_carries_every_field() -> None:
    out = WorktreeOut.of(
        Worktree(branch="feat/x", path="/work/x", created_branch=True, pushed=False)
    )

    assert out.model_dump() == {
        "branch": "feat/x",
        "path": "/work/x",
        "created_branch": True,
        "pushed": False,
    }


def test_a_card_with_no_progress_or_needs_you_since_stays_none() -> None:
    out = CardOut.of(a_card())

    assert out.progress is None
    assert out.needs_you_since is None
    assert out.id == RUN_ID


def test_a_board_view_projects_every_column() -> None:
    view = BoardView(
        columns=BoardColumns(queued=[a_card()], running=[], needs_you=[], done=[], failed=[]),
        counts=BoardCounts(running=0, queued=1, needs_you=0),
        generated_at=NOW,
    )

    out = BoardOut.of(view)

    assert len(out.columns.queued) == 1
    assert out.counts.queued == 1
    assert out.generated_at == NOW


def test_a_gate_record_carries_every_field() -> None:
    record = GateRecord(
        id=new_id(),
        run_id=RUN_ID,
        at=NOW,
        path="build",
        event="checkpoint",
        actor="machine",
        text="parked for review",
        attempt_n=2,
    )

    out = GateRecordOut.of(record)

    assert out.path == "build"
    assert out.event == "checkpoint"
    assert out.actor == "machine"
    assert out.text == "parked for review"
    assert out.attempt_n == 2  # noqa: PLR2004


def test_a_step_row_with_no_attempts_has_no_latest() -> None:
    row = StepRowView(
        seq=1,
        path="build",
        label="build",
        kind="agent",
        gate="liveness",
        status="planned",
        token="QUE",
        reason=None,
        attempts=0,
        latest=None,
    )

    out = StepRowOut.of(row)

    assert out.latest is None
    assert out.attempts == 0


def test_the_run_detail_projects_a_null_alert_and_summary_when_absent() -> None:
    run = a_run()
    header = Header(
        project="Acme",
        repository="acme-app",
        base_branch="main",
        folder="",
        template="repo-init",
        version=1,
        harness=None,
        started_at=None,
        worktree_path=None,
    )
    cost = Cost(
        spent_usd=Decimal("0"),
        budget_usd=Decimal("10"),
        tokens_in=0,
        tokens_out=0,
        wall_clock_seconds=0.0,
        active_seconds=0,
        provisional=False,
    )
    detail = RunDetailView(
        run=run,
        header=header,
        alert=None,
        steps=[],
        stories=[],
        cost=cost,
        gate_record=[],
        admitted_signals=("cancel",),
        summary=None,
    )

    out = RunDetailOut.of(detail)

    assert out.alert is None
    assert out.summary is None
    assert out.run.id == RUN_ID
    assert out.run.admitted_signals == ("cancel",)
    assert isinstance(out.cost, CostOut)
    assert isinstance(out.header, HeaderOut)


def test_summary_is_projected_when_present() -> None:
    run = a_run(status="done")
    detail = RunDetailView(
        run=run,
        header=Header(
            project="Acme",
            repository="acme-app",
            base_branch="main",
            folder="",
            template="repo-init",
            version=1,
            harness=None,
            started_at=None,
            worktree_path=None,
        ),
        alert=None,
        steps=[],
        stories=[],
        cost=Cost(
            spent_usd=Decimal("0"),
            budget_usd=Decimal("10"),
            tokens_in=0,
            tokens_out=0,
            wall_clock_seconds=0.0,
            active_seconds=0,
            provisional=False,
        ),
        gate_record=[],
        admitted_signals=(),
        summary=Summary(progress=None, links=["https://example.invalid"], skipped=["4-2"]),
    )

    out = RunDetailOut.of(detail)

    assert out.summary is not None
    assert out.summary.skipped == ["4-2"]
    assert out.summary.links == ["https://example.invalid"]


def test_gate_record_of_extracts_mode_from_payload() -> None:
    record = GateRecord(
        id=new_id(),
        run_id=RUN_ID,
        at=NOW,
        path="build",
        event="answer",
        actor="operator",
        text="let's go",
        attempt_n=1,
        payload={"mode": "session"},
    )

    out = GateRecordOut.of(record)

    assert out.mode == "session"


def test_gate_record_of_mode_is_none_when_payload_has_no_mode() -> None:
    record = GateRecord(
        id=new_id(),
        run_id=RUN_ID,
        at=NOW,
        path="build",
        event="start",
        actor="machine",
        text="started",
        attempt_n=None,
    )

    out = GateRecordOut.of(record)

    assert out.mode is None


def test_run_detail_out_includes_reply_available_true_in_serialized_output() -> None:
    run = a_run()
    detail = RunDetailView(
        run=run,
        header=Header(
            project="Acme",
            repository="acme-app",
            base_branch="main",
            folder="",
            template="repo-init",
            version=1,
            harness=None,
            started_at=None,
            worktree_path=None,
        ),
        alert=None,
        steps=[],
        stories=[],
        cost=Cost(
            spent_usd=Decimal("0"),
            budget_usd=Decimal("10"),
            tokens_in=0,
            tokens_out=0,
            wall_clock_seconds=0.0,
            active_seconds=0,
            provisional=False,
        ),
        gate_record=[],
        admitted_signals=(),
        summary=None,
        reply_available=True,
    )

    dumped = RunDetailOut.of(detail).model_dump()

    assert dumped["reply_available"] is True


def test_run_detail_out_omits_reply_available_when_false() -> None:
    run = a_run()
    detail = RunDetailView(
        run=run,
        header=Header(
            project="Acme",
            repository="acme-app",
            base_branch="main",
            folder="",
            template="repo-init",
            version=1,
            harness=None,
            started_at=None,
            worktree_path=None,
        ),
        alert=None,
        steps=[],
        stories=[],
        cost=Cost(
            spent_usd=Decimal("0"),
            budget_usd=Decimal("10"),
            tokens_in=0,
            tokens_out=0,
            wall_clock_seconds=0.0,
            active_seconds=0,
            provisional=False,
        ),
        gate_record=[],
        admitted_signals=(),
        summary=None,
    )

    dumped = RunDetailOut.of(detail).model_dump()

    assert "reply_available" not in dumped


def _a_detail(**over: object) -> RunDetailView:
    """Minimal `RunDetailView` for serializer-level assertions."""
    return RunDetailView(
        run=a_run(),
        header=Header(
            project="Acme",
            repository="acme-app",
            base_branch="main",
            folder="",
            template="repo-init",
            version=1,
            harness=None,
            started_at=None,
            worktree_path=None,
        ),
        alert=None,
        steps=[],
        stories=[],
        cost=Cost(
            spent_usd=Decimal("0"),
            budget_usd=None,
            tokens_in=0,
            tokens_out=0,
            wall_clock_seconds=0.0,
            active_seconds=0,
            provisional=False,
        ),
        gate_record=[],
        admitted_signals=(),
        summary=None,
        **over,  # type: ignore[arg-type]
    )


# ── resume_unavailable_reason serialization (story 4, 2026-09-25) ────────────


def test_resume_unavailable_reason_included_in_serialized_output_when_set() -> None:
    """resume_unavailable_reason='no_session' → key is present in model_dump().

    story 4, 2026-09-25: _omit_false_reply_available only pops the field when None;
    a non-None value must survive serialization so the web-client sees it.
    """
    detail = _a_detail(resume_unavailable_reason="no_session")

    dumped = RunDetailOut.of(detail).model_dump()

    assert dumped["resume_unavailable_reason"] == "no_session"


def test_resume_unavailable_reason_omitted_when_none() -> None:
    """resume_unavailable_reason=None → key is absent from model_dump().

    story 4, 2026-09-25: _omit_false_reply_available pops the field when None
    to keep the response schema compact (same pattern as reply_available=False).
    """
    detail = _a_detail()  # resume_unavailable_reason defaults to None

    dumped = RunDetailOut.of(detail).model_dump()

    assert "resume_unavailable_reason" not in dumped


def test_resume_unavailable_reason_no_capability_included_in_serialized_output() -> None:
    """resume_unavailable_reason='no_capability' → key is present in model_dump()."""
    detail = _a_detail(resume_unavailable_reason="no_capability")

    dumped = RunDetailOut.of(detail).model_dump()

    assert dumped["resume_unavailable_reason"] == "no_capability"
