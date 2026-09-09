"""`run_views_alert.py` on its own (story 6-2): `run_token`, and `build_alert`'s row-kind
and checkpoint-story computation, direct — `test_run_views_checkpoint.py` proves the same
facts through `run_detail()`'s whole join; this module is the unit-level counterpart AD-18
asks every source module to have (`tests/unit/test_check_test_pairs.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.run_views_alert import build_alert, run_token
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run: Run, path: str, *, seq: int, kind: str, story_id: str | None = None) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=path,
        label=path,
        kind=kind,
        gate="deterministic",
        status="done",
        story_id=story_id,
    )


def test_run_token_is_blk_or_chk_only_while_parked() -> None:
    assert run_token(a_run(status="running")) == "RUN"
    assert run_token(a_run(status="done")) == "DON"
    assert run_token(a_run(status="failed")) == "ERR"
    assert run_token(a_run(status="cancelled")) == "CAN"
    assert run_token(a_run(status="needs_you", park_kind="blocked")) == "BLK"
    assert run_token(a_run(status="needs_you", park_kind="checkpoint")) == "CHK"


def test_build_alert_is_none_when_the_run_is_not_parked() -> None:
    run = a_run(status="running")

    alert = build_alert(run, None, row_kind=None, rows=(), park_row=None, attempts_by_row={})

    assert alert is None


def test_build_alert_carries_the_row_kind_with_no_summary_on_a_spec_checkpoint() -> None:
    run = a_run(status="needs_you", park_kind="checkpoint", park_reason="planned")
    build = a_row(run, "stories[0].build", seq=1, kind="agent", story_id="1")

    alert = build_alert(
        run, None, row_kind="agent", rows=[build], park_row=build, attempts_by_row={}
    )

    assert alert is not None
    assert alert.row_kind == "agent"
    assert alert.checkpoint_story is None


def test_build_alert_builds_a_checkpoint_story_on_a_done_checkpoint() -> None:
    run = a_run(status="needs_you", park_kind="checkpoint")
    build = a_row(run, "stories[0].build", seq=1, kind="agent", story_id="7")
    verify = a_row(run, "stories[0].verify", seq=2, kind="shell", story_id="7")
    commit = a_row(run, "stories[0].commit-guard", seq=3, kind="git.commit", story_id="7")
    commit = commit.model_copy(
        update={"with_resolved": {"message": "story 7: Ship it (orchestrator)"}}
    )
    checkpoint = a_row(run, "stories[0].after", seq=4, kind="checkpoint", story_id="7")
    attempt = Attempt(
        id=new_id(), run_id=run.id, step_run_id=build.id, n=1, status="done", cost_usd=Decimal("3")
    )

    alert = build_alert(
        run,
        None,
        row_kind="checkpoint",
        rows=[build, verify, commit, checkpoint],
        park_row=checkpoint,
        attempts_by_row={build.id: [attempt]},
    )

    assert alert is not None
    story = alert.checkpoint_story
    assert story is not None
    assert story.story_id == "7"
    assert story.title == "Ship it"
    assert story.attempts == 1
    assert story.cost_usd == Decimal("3")
    assert story.verify == "done"


def test_build_alert_leaves_title_and_attempts_blank_with_no_build_or_commit_row() -> None:
    """A frame missing its own `build`/`commit-guard` rows is not something a shipped
    Template produces, but `_checkpoint_story` must still answer rather than raise: no
    title to parse, no attempts to count."""
    run = a_run(status="needs_you", park_kind="checkpoint")
    verify = a_row(run, "stories[0].verify", seq=1, kind="shell", story_id="9")
    checkpoint = a_row(run, "stories[0].after", seq=2, kind="checkpoint", story_id="9")

    alert = build_alert(
        run,
        None,
        row_kind="checkpoint",
        rows=[verify, checkpoint],
        park_row=checkpoint,
        attempts_by_row={},
    )

    assert alert is not None
    story = alert.checkpoint_story
    assert story is not None
    assert story.title == ""
    assert story.attempts == 0
    assert story.verify == "done"


def test_build_alert_answers_no_summary_when_the_park_row_is_outside_any_story_frame() -> None:
    """A checkpoint row can exist outside `stories[i]` in principle (`story_frame` returns
    `None`); `build_alert` must not raise, only leave `checkpoint_story` unset."""
    run = a_run(status="needs_you", park_kind="checkpoint")
    row = a_row(run, "push", seq=1, kind="checkpoint")

    alert = build_alert(
        run, None, row_kind="checkpoint", rows=[row], park_row=row, attempts_by_row={}
    )

    assert alert is not None
    assert alert.checkpoint_story is None
