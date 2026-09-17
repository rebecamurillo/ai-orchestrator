"""`mode="session"` on Answer and Retry: the resume-without-re-plan path (story 3-3).

Two load-bearing claims about Answer mode=session:
1. `_prepare_writes` is skipped — no archive, no prepare commit, no context-document write.
2. `agent_tail.finish` runs in full — `mark_finished` is called, so the attempt is closed.

Two load-bearing claims about operator mode overriding the template:
3. `mode="restart"` on a Retry overrides `template.retry.resume_session=True` → fresh dispatch.
4. `mode="session"` on a Retry forces resume even when `template.retry.resume_session=False`.

The first two are asserted through what the `FakeGit` and `FakeAttemptRepository` call logs
record; the latter two through whether `FakeHarness.called("resume")` is non-empty.
"""

from __future__ import annotations

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    World,
    a_gate_record,
    an_agent_row,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    END_SHA,
    RETRY_PROMPT,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.git import FakeGit

#: A session id no real harness would produce, so an assertion on it cannot pass by coincidence.
PREV_SESSION = "s-prev-3-3"
#: The answer text the operator sends via mode=session.
ANSWER_TEXT = "use the psycopg adapter"


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def _a_previous(**over: object) -> Attempt:
    """The attempt before this one: ended error, came back (end_sha set), has a session."""
    row = an_agent_row()
    fields: dict[str, object] = {
        "status": "error",
        "session_id": PREV_SESSION,
        "end_sha": HEAD_SHA,
        "start_sha": HEAD_SHA,
    }
    fields.update(over)
    return an_attempt(row, 1, **fields)


def _session_answer_world(**over: object) -> World:
    """A world where the operator chose mode=session on an Answer signal."""
    resume = a_gate_record(an_agent_row(), "answer", {"mode": "session", "text": ANSWER_TEXT})
    return a_tail_world(
        previous=_a_previous(),
        resume=resume,
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
        **over,  # type: ignore[arg-type]
    )


# ── 1: _prepare_writes is skipped for mode=session Answer ────────────────────


def test_session_answer_skips_archive_and_prepare_commit() -> None:
    """`_prepare_writes` is not called: no staging or prepare-commit for the archive.

    The WIP commit guard runs (clean tree → no commit), and the session mode guard skips
    `_prepare_writes` entirely, so neither `git.stage` nor the prepare `git.commit` appear
    in the call log.
    """
    world = _session_answer_world()

    run(world)

    # No staging for archive (prepare_writes skipped)
    assert world.git.called("stage") == []
    # No prepare commit (prepare_writes skipped)
    prepare_commits = [msg for _, msg in world.git.called("commit") if "prepare" in msg]
    assert prepare_commits == []


def test_session_answer_calls_harness_resume_with_inherited_session_and_answer_text() -> None:
    """Harness.resume is called with the previous session_id and the operator's answer text."""
    world = _session_answer_world()

    run(world)

    resumed = world.harness.called("resume")
    assert len(resumed) == 1
    assert resumed[0]["session_id"] == PREV_SESSION
    assert resumed[0]["message"] == ANSWER_TEXT


# ── 2: agent_tail.finish runs for mode=session Answer ────────────────────────


def test_session_answer_mark_finished_is_called() -> None:
    """`agent_tail.finish` executes in full: mark_finished is recorded on the new attempt."""
    world = _session_answer_world()

    run(world)

    assert any(name == "mark_finished" for name, _ in world.attempts.calls)


def test_session_answer_result_is_done_on_clean_exit() -> None:
    """The executor returns a `done` result, the same as any other clean dispatch."""
    world = _session_answer_world()

    result = run(world)

    assert result.status == "done"


# ── 3: mode=restart overrides template.retry.resume_session=True ─────────────


def test_mode_restart_overrides_template_resume_session_true() -> None:
    """Explicit mode=restart takes the fresh-dispatch path even when the template says resume.

    Template: `retry.resume_session=True` (contracted() default).
    Operator:  payload `{"mode": "restart"}` on the Retry signal.
    Expected:  `harness.start` is called (fresh), `harness.resume` is not.
    """
    resume = a_gate_record(an_agent_row(), "retry", {"mode": "restart"})
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
        # with_resolved uses contracted() default which has resume_session=True
    )

    run(world)

    assert world.harness.called("resume") == []
    assert world.harness.called("start") != []


# ── 4: mode=session overrides template.retry.resume_session=False ────────────


def test_mode_session_overrides_template_resume_session_false() -> None:
    """Explicit mode=session takes the resume path even when the template says do not resume.

    Template: `retry.resume_session=False`.
    Operator:  payload `{"mode": "session"}` on the Retry signal.
    Expected:  `harness.resume` is called with the inherited session_id.
    """
    resume = a_gate_record(an_agent_row(), "retry", {"mode": "session"})
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        with_resolved=contracted(retry={"max": 2, "prompt": RETRY_PROMPT, "resume_session": False}),
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
    )

    run(world)

    resumed = world.harness.called("resume")
    assert len(resumed) == 1
    assert resumed[0]["session_id"] == PREV_SESSION
    assert resumed[0]["message"] == RETRY_PROMPT
    assert world.harness.called("start") == []
