"""`mode="session"` on Answer and Retry: the resume-without-re-plan path (story 3-3).

Two load-bearing claims about Answer mode=session (revised 2026-09-26 — the QA gate's
`make e2e` caught session mode silently dropping both of FR-18's obligations on every
Answer redispatch, real harnesses included, not only the `fake` one it happened to surface
on; Operator-authorized fix, same pass):
1. The archive still runs, and still lands in the prepare commit — only the
   context-document and verify-failure writes are trimmed, because those exist for a
   fresh dispatch's sake and a live session already has that context.
2. The dispatch message still carries FR-18's Answer clause verbatim, its condition read
   back from that same archive — `agent_tail.finish` runs in full afterwards exactly as
   before, `mark_finished` included.

Two load-bearing claims about operator mode overriding the template:
3. `mode="restart"` on a Retry overrides `template.retry.resume_session=True` → fresh dispatch.
4. `mode="session"` on a Retry forces resume even when `template.retry.resume_session=False`.

The first two are asserted through what the `FakeGit`, `FakeHarness` and
`FakeAttemptRepository` call logs record; the latter two through whether
`FakeHarness.called("resume")` is non-empty.
"""

from __future__ import annotations

from orchestrator.application.steps import agent_answer, agent_prompt
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    STORY_ID,
    World,
    a_gate_record,
    an_agent_row,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    ANSWERS,
    DONE_STORY,
    END_SHA,
    RETRY_PROMPT,
    STORY_PATH,
    a_story,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

#: A session id no real harness would produce, so an assertion on it cannot pass by coincidence.
PREV_SESSION = "s-prev-3-3"
#: The answer text the operator sends via mode=session.
ANSWER_TEXT = "use the psycopg adapter"
#: The `Blocking condition:` line the archived file carries, and the Answer clause quotes back.
CONDITION = "missing driver"
#: `agent_answer.archive_path`'s own formula, restated for the `FakeGit` status script below
#: — it has to name the archived path before `world.ctx` exists to build one from it.
ARCHIVED_PATH = f"{ANSWERS}/{STORY_ID}-attempt-1.md"


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
    """A world where the operator chose mode=session on an Answer signal.

    `story` seeds the *blocked* file the archive moves away before the resumed dispatch —
    what a real Answer always finds at that path — and `on_resume` writes the terminal one
    back, standing in for what the resumed session's own work would leave, so
    `agent_tail.finish` still has a Story file to route on afterwards.
    """
    resume = a_gate_record(an_agent_row(), "answer", {"mode": "session", "text": ANSWER_TEXT})
    harness = FakeHarness()
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        story=a_story(status="blocked", condition=CONDITION),
        harness=harness,
        git=FakeGit(status=["", f"A  {ARCHIVED_PATH}"], head_sha=[HEAD_SHA, END_SHA]),
        **over,  # type: ignore[arg-type]
    )
    harness.on_resume = lambda: world.workspace.write(STORY_PATH, DONE_STORY)
    return world


# ── 1: _prepare_writes is skipped for mode=session Answer ────────────────────


def test_session_answer_still_archives_and_commits_before_dispatch() -> None:
    """FR-18's archive still runs and still lands in the prepare commit, even though the
    context-document and verify-failure writes `_prepare_writes` also makes are trimmed:
    the archive is the orchestrator's own bookkeeping, not context for the agent, and the
    Answer clause's condition is read back out of it (`agent_answer`'s own module docstring)."""
    world = _session_answer_world()

    run(world)

    staged = {path for _, path in world.git.called("stage")}
    assert staged == {STORY_PATH, agent_answer.archive_path(world.ctx)}
    prepare_commits = [msg for _, msg in world.git.called("commit") if "prepare" in msg]
    assert len(prepare_commits) == 1


def test_session_answer_resume_carries_inherited_session_and_the_answer_clause() -> None:
    """`Harness.resume` inherits the previous session_id, and its message still carries
    FR-18's Answer clause verbatim — not the operator's bare text — quoting back the
    condition the archived file recorded."""
    world = _session_answer_world()

    run(world)

    resumed = world.harness.called("resume")
    assert len(resumed) == 1
    assert resumed[0]["session_id"] == PREV_SESSION
    expected = agent_prompt.ANSWER.format(condition=CONDITION, answer=ANSWER_TEXT).strip()
    assert resumed[0]["message"] == expected


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


# ── 5: session retry message uses operator text (story 4, 2026-09-25) ────────


def test_session_retry_message_uses_operator_text_when_provided() -> None:
    """Retry mode=session with operator text → resume receives operator text, not template prompt.

    story 4, 2026-09-25: _session_message prefers signal.payload["text"] over retry.prompt.
    """
    operator_instruction = "fix the enum"
    payload = {"mode": "session", "text": operator_instruction}
    resume = a_gate_record(an_agent_row(), "retry", payload)
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
    )

    run(world)

    resumed = world.harness.called("resume")
    assert len(resumed) == 1
    assert resumed[0]["message"] == operator_instruction


# ── 6: restart retry uses operator text in front of dispatch (story 4, 2026-09-25) ──


def test_restart_retry_uses_operator_text_in_front_of_dispatch() -> None:
    """Retry mode=restart with operator text → start prompt begins with the operator's text.

    story 4, 2026-09-25: _planned restart path uses operator_text over retry.prompt when provided.
    mode=restart forces the fresh-dispatch path regardless of harness resume capability.
    """
    operator_instruction = "use psycopg"
    payload = {"mode": "restart", "text": operator_instruction}
    resume = a_gate_record(an_agent_row(), "retry", payload)
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
    )

    run(world)

    started = world.harness.called("start")
    assert len(started) == 1
    assert started[0]["prompt"].startswith(operator_instruction + " ")


# ── 7: restart retry, no text, template hint used (story 4, 2026-09-25) ──────


def test_restart_retry_no_text_uses_template_retry_prompt_as_hint() -> None:
    """Retry mode=restart, no operator text, template has retry prompt → prompt starts with it.

    story 4, 2026-09-25: I/O matrix row 4 — when the operator supplies no text, the template
    retry.prompt stands in as the hint prefix (unchanged from template-auto-retry behaviour).
    """
    resume = a_gate_record(an_agent_row(), "retry", {"mode": "restart"})
    world = a_tail_world(
        previous=_a_previous(),
        resume=resume,
        git=FakeGit(status=["", ""], head_sha=[HEAD_SHA, END_SHA]),
        # with_resolved uses contracted() default which carries retry.prompt = RETRY_PROMPT
    )

    run(world)

    started = world.harness.called("start")
    assert len(started) == 1
    assert started[0]["prompt"].startswith(RETRY_PROMPT + " ")
