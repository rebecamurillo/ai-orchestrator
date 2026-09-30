"""What the `agent` kind does when it runs a second time at the same row.

Three re-dispatches reach this executor and they are not the same dispatch (AD-9, AD-13):

- a **retry** the Template's own `retry` contract asked for — the harness is resumed in the
  session it was in, or handed the retry prompt in front of a fresh one, and a retry that
  follows an `ambiguous story file` stop archives every match but the newest first;
- a **verify redispatch** — the Story file goes back to `in-progress` with a
  `## Verify Failure` section holding the command, the code and the log tail (FR-10);
- an **operator resume** — a `resume_signal`, which is neither of the above and is 5.4's.

The executor tells them apart from `ctx` alone: AD-9 closes `StepContext`'s field list, so
the discriminator is the previous attempt's own status plus the row's counters.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import StepContext, VerifyFailure
from orchestrator.application.story_file import AUTO_RUN_RESULT, parse
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ports.harness import HarnessCapabilities
from orchestrator.domain.statuses import GateEvent
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    WORKTREE,
    World,
    a_gate_record,
    an_agent_row,
    an_attempt,
    resolved,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    ANSWERS,
    CONTEXT_FILE,
    OTHER_PATH,
    RETRY_PROMPT,
    STORY_PATH,
    a_story,
    a_tail_world,
    contracted,
    redispatched,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

WORKTREE_PATH = Path(WORKTREE)
PREVIOUS_SESSION = "s-previous"
#: The dispatch sentence `compose_prompt` builds for this row, unchanged by any of this.
DISPATCH = (
    "Run the skill bmad-build-auto in folder+id dispatch mode: "
    "spec folder specs/notifications, story id 4-1. Read X."
)
VERIFY_FAILURE = VerifyFailure(
    command="make test", exit_code=1, log_tail=("FAILED tests/a.py", "1 failed")
)
CANNOT_RESUME = HarnessCapabilities(preassign_session=True, resume=False, native_tracing=True)
#: `mark_started` and `mark_finished`, and no `pgid` update between them.
RESUME_WRITES = 2


def a_previous(status: str = "error", **over: object) -> Attempt:
    """The attempt before this one, as `_finish` left it: it came back, so it is no orphan."""
    fields: dict[str, object] = {
        "status": status,
        "session_id": PREVIOUS_SESSION,
        "end_sha": HEAD_SHA,
        "start_sha": HEAD_SHA,
    }
    fields.update(over)
    return an_attempt(an_agent_row(), 1, **fields)


def a_retry_world(**over: object) -> World:
    return a_tail_world(previous=a_previous(), **over)  # type: ignore[arg-type]


def run(ctx: StepContext) -> StepResult:
    return AgentExecutor().execute(ctx)


def failing_verify(world: World, failure: VerifyFailure | None = VERIFY_FAILURE) -> StepContext:
    """The row as the walker hands it over after a `verify` row redispatched to it."""
    ctx = redispatched(world)
    environment = ctx.ports.run_env
    assert environment is not None
    return replace(
        ctx,
        ports=replace(ctx.ports, run_env=replace(environment, verify_failure=failure)),
    )


# ── the retry dispatch ───────────────────────────────────────────────────────


def test_a_retry_resumes_the_session_the_previous_attempt_was_in() -> None:
    world = a_retry_world()

    run(world.ctx)

    assert world.harness.called("start") == []
    resumed = world.harness.called("resume")
    assert len(resumed) == 1
    assert resumed[0]["session_id"] == PREVIOUS_SESSION
    assert resumed[0]["message"] == RETRY_PROMPT
    assert resumed[0]["cwd"] == WORKTREE_PATH


def test_a_resumed_session_never_carries_the_dispatch_prompt_again() -> None:
    """`compose_prompt` is not called for a resume: the session already has that context."""
    world = a_retry_world()

    run(world.ctx)

    assert DISPATCH not in world.harness.called("resume")[0]["message"]


def test_a_resume_is_one_call_so_there_is_no_group_to_commit_between_two() -> None:
    """AD-14's `pgid`-before-await commit exists because `start` and `wait` are two halves;
    `resume` is one call, so the row writes the attempt twice rather than three times."""
    world = a_retry_world()

    run(world.ctx)

    assert [name for name, _ in world.attempts.calls] == [
        "add",
        "add",
        "mark_started",
        "mark_finished",
    ]
    assert len(world.uows) == RESUME_WRITES


def test_a_harness_that_cannot_resume_gets_a_new_session_with_the_prompt_in_front() -> None:
    world = a_retry_world(harness=FakeHarness(capabilities=CANNOT_RESUME))

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == f"{RETRY_PROMPT} {DISPATCH}"


def test_a_contract_that_asked_not_to_resume_gets_a_new_session_too() -> None:
    world = a_retry_world(
        with_resolved=contracted(retry={"max": 2, "prompt": RETRY_PROMPT, "resume_session": False})
    )

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == f"{RETRY_PROMPT} {DISPATCH}"


def test_a_previous_attempt_that_recorded_no_session_starts_a_new_one() -> None:
    world = a_tail_world(previous=a_previous(session_id=None))

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == f"{RETRY_PROMPT} {DISPATCH}"


def test_a_row_with_no_retry_prompt_dispatches_the_ordinary_way() -> None:
    row = contracted()
    del row["retry"]
    world = a_tail_world(previous=a_previous(), with_resolved=row)

    run(world.ctx)

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_an_attempt_after_a_finished_one_is_not_a_retry() -> None:
    """A predecessor that reached `done` was re-queued by a verify failure, not by `retry`."""
    world = a_tail_world(previous=a_previous("done"))

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_an_operator_resume_is_never_a_retry_however_the_last_attempt_ended() -> None:
    world = a_tail_world(previous=a_previous(), resume=a_gate_record(an_agent_row(), "retry"))

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_a_crash_recovered_attempt_is_not_a_retry_and_never_resumes_the_killed_session() -> None:
    """The shape `start_attempt._open_the_row` leaves after a backend restart: the attempt
    it found open is closed `error`, and the walk restarts with no `resume_signal` at all.
    Only `end_sha` separates it from a real retry — it is written by the tail alone, which
    is the same discriminator `_orphan_control` uses and for the same reason `ended_at`
    cannot be one. Reading this as a retry would resume a killed session with the retry
    prompt and never count the attempt against `retry_count`, which AD-9 forbids.
    """
    world = a_tail_world(previous=a_previous(end_sha=None, pgid=4242))

    run(world.ctx)

    assert world.harness.called("resume") == []
    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_an_interrupted_attempt_that_did_come_back_is_still_a_retry() -> None:
    """The pair to the test above: `end_sha` set is exactly "the dispatch came back"."""
    world = a_tail_world(previous=a_previous())

    run(world.ctx)

    assert world.harness.called("resume") != []


def test_a_first_attempt_dispatches_with_no_retry_prompt_at_all() -> None:
    world = a_tail_world()

    run(world.ctx)

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


# ── the de-ambiguation archive (AD-13) ───────────────────────────────────────


def ambiguous(**over: object) -> World:
    """Two files matching the row's glob, the second one written later."""
    return a_tail_world(
        files={OTHER_PATH: a_story("draft")},
        mtimes={STORY_PATH: 100.0, OTHER_PATH: 200.0},
        **over,  # type: ignore[arg-type]
    )


def an_operator(event: GateEvent = "retry") -> GateRecord:
    """The gate record `signal_run` wrote for the signal that resumed this row (AD-13)."""
    return a_gate_record(an_agent_row(), event)


def test_an_operator_retry_after_an_ambiguous_stop_keeps_only_the_newest_match() -> None:
    """The reachable case, and the only one: `ambiguous story file` is a `misconfigured`
    stop, which AD-9 never re-executes automatically — a person choosing Retry is the only
    way this row runs again (FR-16, PRD §4.6)."""
    world = ambiguous(resume=an_operator())

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is None
    assert world.workspace.read(f"{ANSWERS}/4-1-notify.md") is not None
    assert world.workspace.read(OTHER_PATH) is not None


def test_the_archive_happens_before_the_dispatch_so_the_tail_sees_one_file() -> None:
    world = ambiguous(resume=an_operator())

    result = run(world.ctx)

    assert result.status == "error"
    assert result.reason == "unexpected status: draft"


def test_files_of_the_same_age_are_ordered_by_name_so_the_choice_is_never_a_coin_toss() -> None:
    world = a_tail_world(
        files={OTHER_PATH: a_story("draft")},
        mtimes={STORY_PATH: 100.0, OTHER_PATH: 100.0},
        resume=an_operator(),
    )

    run(world.ctx)

    assert world.workspace.read(OTHER_PATH) is not None
    assert world.workspace.read(STORY_PATH) is None


def test_a_single_match_is_left_exactly_where_it_is() -> None:
    world = a_tail_world(resume=an_operator())

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(f"{ANSWERS}/4-1-notify.md") is None


@pytest.mark.parametrize("event", ["answer", "continue"])
def test_a_resume_that_is_not_a_retry_archives_nothing(event: GateEvent) -> None:
    """An Answer archives the Story file itself and re-plans (FR-18); a Continue carries on.
    Neither is the de-ambiguation, and neither may quietly move a file the Operator kept."""
    world = ambiguous(resume=an_operator(event))

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(OTHER_PATH) is not None


def test_an_ambiguity_on_a_first_attempt_is_reported_rather_than_tidied_away() -> None:
    """Nothing is archived until an Operator or the contract asked for the re-run."""
    world = ambiguous()

    result = run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_a_crash_recovered_attempt_archives_nothing() -> None:
    """`start_attempt` closes an interrupted attempt `error` with no `end_sha`, and the walk
    restarts with no signal: that is not a re-run anybody asked for."""
    world = ambiguous(previous=a_previous(end_sha=None, pgid=4242))

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(OTHER_PATH) is not None


def test_the_templates_own_retry_arm_sees_one_file_and_moves_nothing() -> None:
    """Kept because it is honest, not because it fires: the automatic path is only ever
    reached after a route that found exactly one file."""
    world = a_tail_world(previous=a_previous())

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None


def test_a_row_that_declared_no_contract_archives_nothing() -> None:
    world = a_tail_world(
        files={OTHER_PATH: a_story("draft")}, with_resolved=resolved(), resume=an_operator()
    )

    run(world.ctx)

    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(OTHER_PATH) is not None


# ── the archive is one of this row's own writes (AD-17, FR-31) ───────────────


def test_both_ends_of_the_rename_are_staged_into_the_prepare_commit() -> None:
    """An unstaged move is still in the tree at `start_sha`, so 5.6's
    `diff_names(start_sha, end_sha)` would read the orchestrator's own rename as the
    agent's — which AD-17 and FR-31 forbid."""
    world = ambiguous(
        resume=an_operator(),
        # A first dispatch has no predecessor, so the WIP check reads no status (Operator
        # revision, 2026-09-16). Two answers are read, in this order (Operator decision,
        # 2026-09-26): the archive's own "which of these paths has git never tracked" —
        # clean, so both of them are tracked and both ends of the rename are reported —
        # and then the prepare commit's own check. Same assertions as before, one more
        # scripted answer in front of them.
        git=FakeGit(
            status=["", " R specs/notifications/stories/4-1-notify.md", ""],
            head_sha=[HEAD_SHA],
        ),
    )

    run(world.ctx)

    assert world.git.called("stage") == [
        (WORKTREE_PATH, STORY_PATH),
        (WORKTREE_PATH, f"{ANSWERS}/4-1-notify.md"),
        (WORKTREE_PATH, CONTEXT_FILE),
    ]
    assert world.git.called("commit") == [
        (WORKTREE_PATH, "orchestrator: prepare story 4-1 attempt 1")
    ]


def test_an_archive_that_changed_nothing_else_still_leaves_no_empty_commit() -> None:
    """The guard is the whole tree, and `git commit` on an empty index exits non-zero: the
    property that has to survive staging the rename is "no change, no commit"."""
    world = ambiguous(resume=an_operator(), git=FakeGit(status=[""], head_sha=[HEAD_SHA]))

    run(world.ctx)

    assert world.git.called("commit") == []


# ── the verify-failure append (FR-10) ────────────────────────────────────────


def test_a_redispatched_attempt_starts_from_a_file_that_says_in_progress() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world))

    parsed = parse(STORY_PATH, world.workspace.read(STORY_PATH) or "")
    assert parsed is not None
    assert parsed.status == "in-progress"


def test_the_section_names_the_command_the_code_and_the_log_tail() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world))

    written = world.workspace.read(STORY_PATH) or ""
    assert "## Verify Failure" in written
    assert "Command: make test" in written
    assert "Exit code: 1" in written
    assert "FAILED tests/a.py" in written
    assert "1 failed" in written


def test_the_prepare_commit_carries_the_story_file_it_rewrote() -> None:
    world = a_tail_world(
        previous=a_previous("done"),
        git=FakeGit(status=["", f"M  {STORY_PATH}", ""], head_sha=[HEAD_SHA]),
    )

    run(failing_verify(world))

    assert (WORKTREE_PATH, STORY_PATH) in world.git.called("stage")
    assert world.git.called("commit") == [
        (WORKTREE_PATH, "orchestrator: prepare story 4-1 attempt 2")
    ]


def test_the_rest_of_the_file_is_left_exactly_as_the_agent_wrote_it() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world))

    written = world.workspace.read(STORY_PATH) or ""
    assert AUTO_RUN_RESULT in written
    assert "# Story 4-1" in written


def test_a_redispatch_the_walker_could_resolve_no_facts_for_appends_nothing() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world, failure=None))

    assert world.workspace.read(STORY_PATH) == a_story()


def test_a_redispatch_with_no_story_file_to_rewrite_still_dispatches() -> None:
    world = a_tail_world(story=None, previous=a_previous("done"))

    result = run(failing_verify(world))

    assert world.harness.called("start") != []
    assert result.park is not None
    assert result.park.reason == "no story file"


def test_two_matching_files_are_never_rewritten_on_a_guess() -> None:
    world = a_tail_world(files={OTHER_PATH: a_story()}, previous=a_previous("done"))

    run(failing_verify(world))

    assert world.workspace.read(STORY_PATH) == a_story()
    assert world.workspace.read(OTHER_PATH) == a_story()


def test_a_retry_is_not_a_redispatch_and_appends_nothing() -> None:
    """This attempt's predecessor is `error`, so the verify failure was two attempts ago and
    the section it left is already in the file."""
    world = a_tail_world(previous=a_previous())

    run(failing_verify(world))

    assert world.workspace.read(STORY_PATH) == a_story()


def test_a_row_that_was_never_sent_back_appends_nothing() -> None:
    world = a_tail_world(previous=a_previous("done"))
    environment = world.ctx.ports.run_env
    assert environment is not None
    ctx = replace(
        world.ctx,
        ports=replace(world.ctx.ports, run_env=replace(environment, verify_failure=VERIFY_FAILURE)),
    )

    run(ctx)

    assert world.workspace.read(STORY_PATH) == a_story()


# ── the `redispatch` prompt clause (FR-10, story "a redispatch prompt clause") ───────────

REDISPATCH_PROMPT_CLAUSE = "Verify failed: {command} (exit {code}).\n{tail}"
REDISPATCH_CLAUSE_FILLED = "Verify failed: make test (exit 1).\nFAILED tests/a.py\n1 failed"


def with_redispatch_clause(**over: object) -> dict[str, object]:
    row = contracted(**over)
    row["prompts"] = {**row["prompts"], "redispatch": REDISPATCH_PROMPT_CLAUSE}
    return row


def test_a_redispatched_fresh_dispatch_leads_with_the_filled_clause() -> None:
    """`previous.status == "done"` already makes `retrying(ctx)` false, so the row's own
    `retry:` contract (carried by `contracted()`) changes nothing here — only the clause
    fires, once, in front of the row's own prompt."""
    world = a_tail_world(previous=a_previous("done"), with_resolved=with_redispatch_clause())

    run(failing_verify(world))

    assert world.harness.called("start")[0]["prompt"] == f"{REDISPATCH_CLAUSE_FILLED} {DISPATCH}"


def test_a_redispatched_row_with_no_clause_declared_sends_the_plain_prompt() -> None:
    world = a_tail_world(previous=a_previous("done"))

    run(failing_verify(world))

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_a_redispatched_row_whose_verify_failure_is_none_sends_the_plain_prompt() -> None:
    world = a_tail_world(previous=a_previous("done"), with_resolved=with_redispatch_clause())

    run(failing_verify(world, failure=None))

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_a_row_that_was_not_redispatched_but_declares_a_clause_sends_the_plain_prompt() -> None:
    """The clause is declared, but this row's own `redispatch_count` never moved: the same
    shape `test_a_row_that_was_never_sent_back_appends_nothing` reads for the story file."""
    world = a_tail_world(previous=a_previous("done"), with_resolved=with_redispatch_clause())
    environment = world.ctx.ports.run_env
    assert environment is not None
    ctx = replace(
        world.ctx,
        ports=replace(world.ctx.ports, run_env=replace(environment, verify_failure=VERIFY_FAILURE)),
    )

    run(ctx)

    assert world.harness.called("start")[0]["prompt"] == DISPATCH


def test_a_retry_that_follows_a_redispatch_does_not_repeat_the_clause() -> None:
    """The prompt's own mirror of `test_a_retry_is_not_a_redispatch_and_appends_nothing`:
    this attempt's predecessor is `error`, not `done`, so `redispatched(ctx)` reads `False`
    even though the row's `redispatch_count` is still above zero and `verify_failure` is
    still resolved — the clause was already said once, on the attempt that came back `done`
    and does not repeat on this one (context.py's `redispatched`: "nothing is appended
    twice"). The harness cannot resume, so the Template's own retry text still leads."""
    world = a_tail_world(
        previous=a_previous(),
        with_resolved=with_redispatch_clause(),
        harness=FakeHarness(capabilities=CANNOT_RESUME),
    )

    run(failing_verify(world))

    assert world.harness.called("start")[0]["prompt"] == f"{RETRY_PROMPT} {DISPATCH}"
