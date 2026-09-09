"""What the Operator's Answer does to a whole `agent` dispatch (FR-18, AD-9, AD-13).

`test_agent_answer_archive.py` covers `steps/agent_answer.py` on its own. This module runs
the executor, because two of the story's acceptance criteria are about the *order* the
kind does things in and not about any one function: that the rename is inside the prepare
commit — staged by name, before `start_sha` is read, so 5.6 attributes it to the
orchestrator and not to the agent (AD-17, FR-31) — and that the sentence the harness
receives ends with the Answer clause `compose_prompt` builds.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules.signals import ANSWER_KEY
from orchestrator.application.steps.agent import PREPARE_MESSAGE, AgentExecutor
from orchestrator.application.story_file import AUTO_RUN_RESULT
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    SPEC_FOLDER,
    STORY_ID,
    World,
    a_gate_record,
    a_world,
    an_agent_row,
    an_attempt,
    resolved,
)
from tests.unit.fakes.git import FakeGit

STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify.md"
ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/{STORY_ID}-attempt-1.md"

CONDITION = "intent gap"
ANSWER = "Post to the project's channel only"

BLOCKED_FILE = (
    "---\nstatus: blocked\n---\n\n"
    f"# Story\n\n{AUTO_RUN_RESULT}\n\nStatus: blocked\nBlocking condition: {CONDITION}\n"
)

EXPECT = {"files": [f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md"], "status_in": ["done", "blocked"]}

#: The whole sentence FR-14 pins for this row, with the Answer clause FR-18 adds.
ANSWERED_PROMPT = (
    f"Run the skill bmad-build-auto in folder+id dispatch mode: spec folder {SPEC_FOLDER}, "
    f"story id {STORY_ID}. Read X. Answer from the operator to the blocking condition "
    f'"{CONDITION}": {ANSWER}'
)


def an_answered_world(**over: Any) -> World:
    """A second attempt resumed by an Answer, on a worktree the first one left clean.

    The two `status` answers are the two the executor asks for, in order: `_wip_commit`'s,
    before it has written anything (clean — the blocked agent's file was already committed),
    and `_prepare_writes`', after it has staged the rename (the rename itself).
    """
    row = an_agent_row()
    return a_world(
        with_resolved=resolved(expect=EXPECT, **over),
        files={STORY_PATH: BLOCKED_FILE},
        git=FakeGit(status=["", f"R  {STORY_PATH} -> {ARCHIVED}"], head_sha=[HEAD_SHA]),
        previous=an_attempt(row, 1),
        resume=a_gate_record(row, "answer", {ANSWER_KEY: ANSWER}),
    )


def staged(world: World) -> list[str]:
    """Every pathspec the executor staged by name, in the order it staged them.

    `FakeGit.calls` is `(method, arguments)`; `stage(worktree, pathspec)` puts the pathspec
    second, and a whole-tree staging passes `None` there.
    """
    return [
        arguments[1]
        for method, arguments in world.git.calls
        if method == "stage" and arguments[1] is not None
    ]


def prompts(world: World) -> list[str]:
    """What each dispatch asked, in order — `wait` entries carry no prompt of their own."""
    return [call["prompt"] for call in world.harness.calls if call["method"] == "start"]


def commit_messages(world: World) -> list[str]:
    return [arguments[1] for method, arguments in world.git.calls if method == "commit"]


def test_the_dispatch_carries_the_answer_clause_with_the_archived_files_condition() -> None:
    world = an_answered_world()

    AgentExecutor().execute(world.ctx)

    assert prompts(world) == [ANSWERED_PROMPT]


def test_both_ends_of_the_rename_are_staged_into_the_prepare_commit() -> None:
    world = an_answered_world()

    AgentExecutor().execute(world.ctx)

    assert STORY_PATH in staged(world)
    assert ARCHIVED in staged(world)
    assert PREPARE_MESSAGE.format(id=STORY_ID, n=2) in commit_messages(world)


def test_the_glob_is_empty_when_the_harness_is_dispatched_so_it_plans_fresh() -> None:
    """The whole mechanism: no `stories/{id}-*.md` remains, so this is a first dispatch."""
    seen: list[tuple[str, ...]] = []
    world = an_answered_world()
    original = world.harness.start

    def recording_start(**kwargs: Any) -> Any:
        seen.append(world.workspace.glob(EXPECT["files"][0]))
        return original(**kwargs)

    world.harness.start = recording_start  # type: ignore[method-assign]

    AgentExecutor().execute(world.ctx)

    assert seen == [()]
    assert world.workspace.read(ARCHIVED) is not None


def test_a_spec_checkpoint_answer_quotes_spec_rejected_and_halts_again() -> None:
    """6.2's Reject: the plan was sent back, not approved, so `spec_checkpoint` is still
    true and the re-plan halts again — a rejected spec that re-planned straight through to
    implementation would make a declared spec checkpoint fire once instead of every time."""
    world = an_answered_world(spec_checkpoint=True)

    AgentExecutor().execute(world.ctx)

    prompt = prompts(world)[0]
    assert prompt.endswith(f'blocking condition "spec rejected": {ANSWER} Halt after planning.')
