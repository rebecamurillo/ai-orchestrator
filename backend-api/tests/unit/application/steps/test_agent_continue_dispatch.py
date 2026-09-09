"""What `continue` does to a whole `agent` dispatch, at a spec checkpoint (story 6-2, SPEC
CAP-2, FR-19, AD-13).

`test_agent_prompt.py::test_a_resumed_spec_checkpoint_does_not_halt_again` already pins the
prompt in isolation. This module runs the executor, the way `test_agent_answer_dispatch.py`
does for the Answer/Reject side: the acceptance criterion is about the whole dispatch — a
*new* session, no archive, and the gate record's own `continue` — none of which a
`compose_prompt`-only test can show.
"""

from __future__ import annotations

from orchestrator.application.steps.agent import AgentExecutor
from tests.unit.application.steps.agent_fixtures import (
    SPEC_FOLDER,
    STORY_ID,
    World,
    a_gate_record,
    a_world,
    an_agent_row,
    an_attempt,
    resolved,
)

STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify.md"
READY_FILE = "---\nstatus: ready-for-dev\n---\n\n# Story\n"

PREVIOUS_SESSION = "session-attempt-1"


def a_continued_world() -> World:
    """A second attempt resumed by `continue` on a spec-checkpoint row: the plan was
    approved, so nothing is archived and the same Story file is still there to implement."""
    row = an_agent_row()
    return a_world(
        with_resolved=resolved(spec_checkpoint=True),
        files={STORY_PATH: READY_FILE},
        previous=an_attempt(row, 1, session_id=PREVIOUS_SESSION),
        resume=a_gate_record(row, "continue"),
    )


def prompts(world: World) -> list[str]:
    return [call["prompt"] for call in world.harness.calls if call["method"] == "start"]


def session_ids(world: World) -> list[str]:
    return [call["session_id"] for call in world.harness.calls if call["method"] == "start"]


def staged(world: World) -> list[str]:
    return [
        arguments[1]
        for method, arguments in world.git.calls
        if method == "stage" and arguments[1] is not None
    ]


def test_the_redispatch_carries_no_halt_suffix() -> None:
    world = a_continued_world()

    AgentExecutor().execute(world.ctx)

    assert "Halt after planning." not in prompts(world)[0]


def test_the_redispatch_opens_a_new_session_rather_than_resuming_the_old_one() -> None:
    """`continue` is not a Template `retry:` and never resumes a session (AD-9): attempt 2
    is a fresh dispatch, the same way a Reject's re-plan is."""
    world = a_continued_world()

    AgentExecutor().execute(world.ctx)

    assert session_ids(world) == [session_ids(world)[0]]  # exactly one dispatch happened
    assert session_ids(world)[0] != PREVIOUS_SESSION


def test_nothing_is_archived_on_a_continue() -> None:
    """Reject reuses the Answer's archive; Continue must not — the Story file the checkpoint
    already approved stays exactly where the agent left it."""
    world = a_continued_world()

    AgentExecutor().execute(world.ctx)

    assert STORY_PATH not in staged(world)
    assert world.workspace.read(STORY_PATH) == READY_FILE
