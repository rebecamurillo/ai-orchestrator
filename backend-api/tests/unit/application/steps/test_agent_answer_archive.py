"""FR-18's Answer, inside the `agent` kind: the archive, the block, and the prompt's clause.

`agent.py`'s own three test modules cover the dispatch around this; what is proven here is
`steps/agent_answer.py` alone — which file moves where, what is appended to it, and the two
values `compose_prompt` reads its Answer clause from — because those are the sentences
FR-18 and the story's acceptance criteria are written in.

The Story-file glob is the row's own (`expect.files`, resolved by the planner), so every
world below writes real paths under `specs/notifications/stories/` and lets
`agent_tail.story_files` find them exactly as a dispatch would.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules.signals import ANSWER_KEY as SIGNAL_ANSWER_KEY
from orchestrator.application.steps import agent_answer
from orchestrator.application.story_file import AUTO_RUN_RESULT
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
from tests.unit.fakes.clock import EPOCH

STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify.md"
OTHER_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify-2.md"
ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/{STORY_ID}-attempt-1.md"

CONDITION = "intent gap"
ANSWER = "Post to the project's channel only"

BLOCKED_FILE = (
    "---\nstatus: blocked\n---\n\n"
    f"# Story\n\n{AUTO_RUN_RESULT}\n\nStatus: blocked\nBlocking condition: {CONDITION}\n"
)

#: The row's liveness contract, as `application/templates/agent_row.py` writes it.
EXPECT = {"files": [f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md"], "status_in": ["done", "blocked"]}

#: A rename is two paths: where the file was, and where it is now.
BOTH_ENDS = 2


def an_answer(text: str = ANSWER) -> Any:
    return a_gate_record(an_agent_row(), "answer", {SIGNAL_ANSWER_KEY: text})


def a_blocked_world(*, files: dict[str, str] | None = None, **over: Any) -> World:
    """A second attempt on a row whose first one wrote a blocked Story file."""
    row = an_agent_row()
    return a_world(
        with_resolved=resolved(expect=EXPECT, **over),
        files=files if files is not None else {STORY_PATH: BLOCKED_FILE},
        previous=an_attempt(row, 1),
        resume=an_answer(),
    )


# ── the archive ─────────────────────────────────────────────────────────────────────────


def test_the_story_file_is_moved_to_the_answers_directory_named_by_the_previous_attempt() -> None:
    world = a_blocked_world()

    moved = agent_answer.archive_with_answer(world.ctx)

    assert moved == (STORY_PATH, ARCHIVED)
    assert world.workspace.read(STORY_PATH) is None
    assert world.workspace.read(ARCHIVED) is not None


def test_the_operators_words_are_appended_under_a_human_answer_heading() -> None:
    """The block FR-18 pins: the heading, the time and the actor, then the text."""
    world = a_blocked_world()

    agent_answer.archive_with_answer(world.ctx)

    archived = world.workspace.read(ARCHIVED) or ""
    assert archived.startswith("---\nstatus: blocked\n---")
    assert archived.endswith(f"## Human Answer\n\n2026-01-01T00:00:00Z · operator\n\n{ANSWER}\n")


def test_the_archive_reports_both_ends_so_the_prepare_commit_can_stage_the_rename() -> None:
    """AD-17: an unstaged move would be in the tree at `start_sha` and read as the agent's."""
    world = a_blocked_world()

    moved = agent_answer.archive_with_answer(world.ctx)

    assert len(moved) == BOTH_ENDS
    assert set(moved) == {STORY_PATH, ARCHIVED}


def test_a_resume_that_is_not_an_answer_archives_nothing() -> None:
    row = an_agent_row()
    world = a_world(
        with_resolved=resolved(expect=EXPECT),
        files={STORY_PATH: BLOCKED_FILE},
        previous=an_attempt(row, 1),
        resume=a_gate_record(row, "continue"),
    )

    assert agent_answer.archive_with_answer(world.ctx) == ()
    assert world.workspace.read(STORY_PATH) is not None


def test_a_dispatch_with_no_resume_at_all_archives_nothing() -> None:
    world = a_world(with_resolved=resolved(expect=EXPECT), files={STORY_PATH: BLOCKED_FILE})

    assert agent_answer.archive_with_answer(world.ctx) == ()
    assert world.workspace.read(STORY_PATH) is not None


def test_no_story_file_is_logged_and_proceeds_as_a_first_dispatch() -> None:
    """The brief: an agent that blocked before writing its file leaves nothing to archive."""
    world = a_blocked_world(files={})

    assert agent_answer.archive_with_answer(world.ctx) == ()


def test_two_matches_are_left_alone_rather_than_chosen_between() -> None:
    """Two files is `ambiguous story file`, which only a Retry's de-ambiguation may resolve
    (`agent_tail.archive_ambiguous`); guessing here would make that choice invisibly."""
    world = a_blocked_world(files={STORY_PATH: BLOCKED_FILE, OTHER_PATH: BLOCKED_FILE})

    assert agent_answer.archive_with_answer(world.ctx) == ()
    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(OTHER_PATH) is not None


def test_the_archived_name_falls_back_to_the_attempt_before_this_one() -> None:
    """A context that recorded no previous attempt still names a file rather than raising."""
    world = a_world(with_resolved=resolved(expect=EXPECT), resume=an_answer())

    assert agent_answer.previous_n(world.ctx) == 1
    assert agent_answer.archive_path(world.ctx).endswith(f"{STORY_ID}-attempt-1.md")


# ── what the prompt is told ─────────────────────────────────────────────────────────────


def test_the_condition_is_read_back_out_of_the_archived_file() -> None:
    world = a_blocked_world()
    agent_answer.archive_with_answer(world.ctx)

    assert agent_answer.condition(world.ctx) == CONDITION


def test_a_spec_checkpoint_answers_spec_rejected_without_reading_a_file() -> None:
    """Nothing failed at a checkpoint, so there is no `Blocking condition:` line to read."""
    world = a_blocked_world(spec_checkpoint=True)

    assert agent_answer.condition(world.ctx) == agent_answer.SPEC_REJECTED


def test_a_file_that_states_no_condition_renders_an_empty_one() -> None:
    world = a_blocked_world(files={STORY_PATH: "---\nstatus: blocked\n---\n"})
    agent_answer.archive_with_answer(world.ctx)

    assert agent_answer.condition(world.ctx) == ""


def test_the_resolved_signal_carries_the_condition_and_the_text_compose_prompt_reads() -> None:
    world = a_blocked_world()
    agent_answer.archive_with_answer(world.ctx)

    resolved_signal = agent_answer.resolved_signal(world.ctx)

    assert resolved_signal is not None
    assert resolved_signal.payload[agent_answer.CONDITION_KEY] == CONDITION
    assert resolved_signal.payload[agent_answer.ANSWER_KEY] == ANSWER
    assert resolved_signal.at == EPOCH


def test_the_operators_own_payload_key_is_kept_beside_the_resolved_ones() -> None:
    """The record is copied, never rewritten: `signal_run`'s own key is still on it."""
    world = a_blocked_world()

    resolved_signal = agent_answer.resolved_signal(world.ctx)

    assert resolved_signal is not None
    assert resolved_signal.payload[SIGNAL_ANSWER_KEY] == ANSWER


def test_an_answer_with_no_text_at_all_resolves_to_an_empty_clause() -> None:
    row = an_agent_row()
    world = a_world(
        with_resolved=resolved(expect=EXPECT),
        files={STORY_PATH: BLOCKED_FILE},
        previous=an_attempt(row, 1),
        resume=a_gate_record(row, "answer"),
    )

    resolved_signal = agent_answer.resolved_signal(world.ctx)

    assert resolved_signal is not None
    assert resolved_signal.payload[agent_answer.ANSWER_KEY] == ""


def test_every_other_resume_is_handed_back_untouched() -> None:
    row = an_agent_row()
    record = a_gate_record(row, "continue")
    world = a_world(with_resolved=resolved(expect=EXPECT), resume=record)

    assert agent_answer.resolved_signal(world.ctx) is record


def test_a_dispatch_with_no_resume_resolves_to_none() -> None:
    world = a_world(with_resolved=resolved(expect=EXPECT))

    assert agent_answer.resolved_signal(world.ctx) is None


def test_the_payload_key_matches_the_one_signal_run_actually_stores() -> None:
    """This module reads the signal's storage contract rather than importing it; the two are
    asserted equal here so a rename of either fails one test instead of no test."""
    assert agent_answer.TEXT_KEY == SIGNAL_ANSWER_KEY
