"""The dispatch half of the `agent` kind: the span, the environment, the group, the record.

Two of these are the story's own load-bearing claims and neither can be settled by looking
at one object. AD-14 wants `attempt.pgid` committed *before* the process is awaited, which
is a statement about the interleaving of two call logs — `FakeAttemptRepository.calls` and
`FakeHarness.calls` — and AD-5 wants the harness to receive exactly what the environment
builder returned, which only the harness's own call log can show.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import ProjectContext
from orchestrator.domain.ports.harness import HarnessResult, HarnessUsage
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    BUDGET,
    HEAD_SHA,
    PROJECT_SLUG,
    ROW_PATH,
    SPEND,
    STORY_ID,
    WORKTREE,
    World,
    WriteFailed,
    a_run,
    a_world,
    an_agent_row,
    an_attempt,
    resolved,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import DEFAULT_PGID, FakeHarness
from tests.unit.fakes.tracer import FakeTracer, trace_id_of

LOG_PATH = Path("/work/logs")
END_SHA = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"
#: `KIND_META["agent"]`'s own timeout, which `templates/story.yaml` also writes on the row.
TIMEOUT_MIN = 90
#: A group no real process would be in, so the assertion cannot pass by coincidence.
OTHER_PGID = 9191
#: Ids in this system are UUIDv7 (Consistency Conventions — Ids & keys).
UUID_VERSION = 7


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def a_result(world: World, **over: object) -> HarnessResult:
    fields: dict[str, object] = {
        "session_id": "s-1",
        "exit_code": 0,
        "log_path": LOG_PATH / "003-1.log",
    }
    fields.update(over)
    return HarnessResult(**fields)  # type: ignore[arg-type]


def dispatched(**over: object) -> World:
    """A world whose HEAD moves between `mark_started` and `mark_finished`."""
    return a_world(git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]), **over)  # type: ignore[arg-type]


# ── the span and the environment ─────────────────────────────────────────────


def test_the_attempt_span_wraps_the_dispatch_and_its_traceparent_reaches_the_harness() -> None:
    tracer = FakeTracer()
    world = dispatched(tracer=tracer)

    run(world)

    assert world.tracer is tracer
    assert tracer.attempt_span_calls == [(world.run.id, ROW_PATH, world.attempt.id)]
    expected = f"00-{trace_id_of(world.run.id)}-{1:016x}-01"
    assert world.harness_env.calls[0]["traceparent"] == expected
    assert world.harness.called("start")[0]["env"]["TRACEPARENT"] == expected


def test_without_a_tracer_the_dispatch_still_happens_with_an_empty_traceparent() -> None:
    world = dispatched()

    result = run(world)

    assert result.status == "done"
    assert world.harness.called("start")[0]["env"]["TRACEPARENT"] == ""


def test_the_harness_receives_exactly_what_the_environment_builder_returned() -> None:
    """AD-5: this executor adds no name of its own to what `HarnessEnv` answered."""
    world = dispatched(project=ProjectContext(env_vars={"MY_VAR": "v"}, log_prompt_content=True))

    run(world)

    call = world.harness_env.calls[0]
    assert call["project_slug"] == PROJECT_SLUG
    assert call["project_env"] == {"MY_VAR": "v"}
    assert call["log_content"] is True
    assert call["story_id"] == STORY_ID
    assert world.harness.called("start")[0]["env"] == {
        "ORCH_PROJECT": PROJECT_SLUG,
        "ORCH_STORY_ID": STORY_ID,
        "TRACEPARENT": "",
        "MY_VAR": "v",
    }


def test_a_row_outside_a_story_frame_names_no_story_to_the_environment() -> None:
    world = dispatched(with_resolved=resolved(story_id=""))

    run(world)

    assert world.harness_env.calls[0]["story_id"] is None


# ── what the dispatch itself carries ─────────────────────────────────────────


def test_the_dispatch_carries_a_fresh_session_the_remainder_and_the_rows_deadline() -> None:
    world = dispatched()

    run(world)

    call = world.harness.called("start")[0]
    assert call["cwd"] == Path(WORKTREE)
    assert call["model"] == "claude-opus-5"
    assert call["timeout_min"] == TIMEOUT_MIN
    assert call["budget_usd_remaining"] == BUDGET - SPEND
    assert call["log_path"] == Path("/work/logs") / str(world.run.id) / "003-1.log"


def test_the_session_id_is_a_fresh_uuid_v7_and_not_the_attempts_own() -> None:
    world = dispatched()

    run(world)

    session_id = world.harness.called("start")[0]["session_id"]
    assert UUID(session_id).version == UUID_VERSION
    assert session_id != str(world.attempt.id)


def test_a_row_carrying_no_resolved_timeout_gets_the_kinds_own_default() -> None:
    without = resolved()
    del without["timeout_min"]
    world = dispatched(with_resolved=without)

    run(world)

    assert world.harness.called("start")[0]["timeout_min"] == TIMEOUT_MIN


def test_a_row_carrying_an_explicit_null_timeout_gets_the_default_too() -> None:
    """`None` would reach `Harness.start` and the timeout sentence as the word `None`."""
    world = dispatched(with_resolved=resolved(timeout_min=None))

    run(world)

    assert world.harness.called("start")[0]["timeout_min"] == TIMEOUT_MIN


def test_the_prompt_the_harness_receives_is_the_composed_one() -> None:
    world = dispatched()

    run(world)

    assert world.harness.called("start")[0]["prompt"] == (
        "Run the skill bmad-build-auto in folder+id dispatch mode: "
        "spec folder specs/notifications, story id 4-1. Read X."
    )


# ── the pgid, and when it is committed ───────────────────────────────────────


def test_the_group_is_committed_before_the_await_begins() -> None:
    """AD-14's central guarantee, read at the instant it is about.

    Comparing the two call logs *after* the row has finished cannot distinguish "committed
    between `start` and `wait`" from "committed after both" — the finished sequences are
    identical either way. `on_wait` runs as the first statement of `FakeHarness.wait`, so
    the snapshot it takes is the state of the world at the moment the caller began to block.
    """
    seen: list[list[str]] = []
    harness = FakeHarness()
    world = dispatched(harness=harness)
    harness.on_wait = lambda: seen.append([name for name, _ in world.attempts.calls])

    run(world)

    assert seen == [["add", "mark_started", "update"]]
    assert world.uows[1].committed
    assert [name for name, _ in world.attempts.calls] == [
        "add",
        "mark_started",
        "update",
        "mark_finished",
    ]
    assert [call["method"] for call in world.harness.calls] == ["start", "wait"]
    assert world.attempts.attempts[world.attempt.id].pgid == DEFAULT_PGID


def test_the_session_is_stored_with_the_group_so_a_dead_backend_leaves_a_resumable_row() -> None:
    """FR-21 writes `resume_command` from `attempt.session_id`; an attempt with a group and
    no session is exactly the one an Operator would need it for."""
    seen: list[str | None] = []
    harness = FakeHarness()
    world = dispatched(harness=harness)
    harness.on_wait = lambda: seen.append(world.attempts.attempts[world.attempt.id].session_id)

    run(world)

    assert seen == [world.harness.called("start")[0]["session_id"]]


def test_the_group_stored_is_the_one_the_handle_reported() -> None:
    world = dispatched(harness=FakeHarness(pgid=OTHER_PGID))

    run(world)

    assert world.attempts.attempts[world.attempt.id].pgid == OTHER_PGID


def test_a_failed_pgid_write_kills_the_group_before_the_exception_escapes() -> None:
    """The executor is the only frame holding the handle between `start` and `wait`, so the
    adapter's own guard never sees this one: an escape without a kill is AD-14's orphan."""
    world = dispatched(writes_failing_on=2)

    with pytest.raises(WriteFailed):
        run(world)

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": DEFAULT_PGID}]
    assert [call["method"] for call in world.harness.calls] == ["start"]


# ── mark_finished ────────────────────────────────────────────────────────────


def test_a_clean_exit_records_the_range_the_session_the_log_and_the_usage() -> None:
    usage = HarnessUsage(tokens_in=120, tokens_out=45, cost_usd=Decimal("0.0342"))
    harness = FakeHarness()
    world = dispatched(harness=harness)
    harness.results.append(a_result(world, session_id="s-7", exit_code=0, usage=usage))

    result = run(world)

    finished = world.attempts.attempts[world.attempt.id]
    assert finished.start_sha == HEAD_SHA
    assert finished.end_sha == END_SHA
    assert finished.exit_code == 0
    assert finished.session_id == "s-7"
    assert finished.log_path == str(LOG_PATH / "003-1.log")
    assert (finished.tokens_in, finished.tokens_out) == (120, 45)
    assert finished.cost_usd == Decimal("0.0342")
    assert finished.cost_provisional is True
    assert result == StepResult(
        status="done", gate="liveness", output_ref=str(LOG_PATH / "003-1.log")
    )


def test_a_harness_that_reported_no_usage_leaves_the_token_columns_untouched() -> None:
    harness = FakeHarness()
    world = dispatched(harness=harness)
    harness.results.append(a_result(world, usage=None))

    run(world)

    finished = world.attempts.attempts[world.attempt.id]
    assert (finished.tokens_in, finished.tokens_out, finished.cost_usd) == (None, None, None)
    assert finished.cost_provisional is False


def test_a_timeout_is_recorded_in_full_and_then_parks_the_run() -> None:
    harness = FakeHarness()
    world = dispatched(harness=harness)
    harness.results.append(a_result(world, exit_code=None, timed_out=True))

    result = run(world)

    finished = world.attempts.attempts[world.attempt.id]
    assert finished.ended_at is not None
    assert finished.end_sha == END_SHA
    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "timeout"
    assert result.park.reason == "timeout epics[0].stories[3].build after 90 min"
    assert result.park.path == ROW_PATH


def test_the_executor_writes_no_status_onto_the_attempt_it_is_running() -> None:
    """AD-8: `apply_step_result` closes this attempt from the `StepResult`, not this row."""
    world = dispatched()

    run(world)

    assert world.attempts.attempts[world.attempt.id].status == "running"


def test_a_later_attempt_dispatches_the_same_way_the_first_one_did() -> None:
    row = an_agent_row()
    world = a_world(
        previous=an_attempt(row, 1),
        git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]),
        run=a_run(spend_usd=Decimal("9.00")),
    )

    run(world)

    assert world.harness.called("start")[0]["budget_usd_remaining"] == Decimal("1.00")
