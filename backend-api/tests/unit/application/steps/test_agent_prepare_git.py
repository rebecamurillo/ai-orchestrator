"""The prepare phase against git: what it refuses to ask, and how it reports a refusal.

Both halves come from one production stop — hub Run `01a0d2aa`, 2026-09-25, step
`epics[4].stories[6].build`. The Operator answered a `blocked` agent; the Answer archive
moved the Story file it had written; `agent.py` then staged the rename's source, which was
a path git had never tracked and which the move had just removed:

    git -C … add -A -- initiatives/…/analytics-foundation-07-….md exited 128:
    fatal: pathspec '…' did not match any files

Two defects, and one test section each. **The pathspec** — a rename's source is worth
staging only because the tree at `start_sha` still holds it, which is untrue of a file git
never tracked, so asking about one is asking git a question with no answer. **The report** —
the `GitError` escaped to the executor registry's catch-all, which recorded the exception's
class name, no output and no harness, and parked `internal`: a stop the Operator could not
read and, by AD-13's table, could not answer either, because `internal` admits no `answer`
and the one just given had been consumed.

`agent_workdir.py`'s own sweep is the third layer and is covered by `test_agent_workdir.py`:
with the hub half of the WIP commit in place the source is tracked by the time the archive
runs, so the first section here is the belt to that braces. Both are wanted. Three separate
fixes have now been made to one call site each, and what this module pins is the invariant
underneath them: **an `agent` row never hands git a pathspec it has not established, and
never lets a `GitError` reach the Operator as a class name.**
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.signals import ANSWER_KEY as SIGNAL_ANSWER_KEY
from orchestrator.application.steps import (
    agent_answer,
    agent_prepare,
    agent_workdir,
)
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.story_file import AUTO_RUN_RESULT
from orchestrator.domain.ports.git import GitError
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    ROW_PATH,
    SPEC_FOLDER,
    STORY_ID,
    WORKTREE,
    World,
    a_gate_record,
    a_world,
    an_agent_row,
    an_attempt,
    resolved,
)
from tests.unit.fakes.git import FakeGit

WORKTREE_PATH = Path(WORKTREE)
STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify.md"
ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/{STORY_ID}-attempt-1.md"
CONTEXT_FILE = f"{SPEC_FOLDER}/project-context.md"

#: The row's liveness contract, as `application/templates/agent_row.py` writes it.
EXPECT = {"files": [f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md"], "status_in": ["done", "blocked"]}

BLOCKED_FILE = (
    "---\nstatus: blocked\n---\n\n"
    f"# Story\n\n{AUTO_RUN_RESULT}\n\nStatus: blocked\nBlocking condition: no bash\n"
)

#: What git says about a pathspec matching nothing, and the code it says it with.
PATHSPEC_OUTPUT = f"fatal: pathspec '{STORY_PATH}' did not match any files"
PATHSPEC_EXIT = 128

#: Porcelain for the production tree: the Story file the agent wrote, never committed.
UNTRACKED_STORY = f"?? {STORY_PATH}"

#: A rename is two paths; an untracked one is worth exactly one.
BOTH_ENDS = 2


def an_answer(text: str = "use git rm") -> Any:
    return a_gate_record(an_agent_row(), "answer", {SIGNAL_ANSWER_KEY: text})


def answered(*, git: FakeGit) -> World:
    """A second attempt on a row whose first one blocked, resumed by the Operator's Answer."""
    row = an_agent_row()
    return a_world(
        with_resolved=resolved(expect=EXPECT),
        files={STORY_PATH: BLOCKED_FILE},
        previous=an_attempt(row, 1),
        resume=an_answer(),
        git=git,
    )


def run(world: World) -> Any:
    return AgentExecutor().execute(world.ctx)


# ── the pure rule: which paths git has never heard of ───────────────────────


def test_only_the_question_mark_lines_are_untracked() -> None:
    status = "?? a.md\n M b.md\nA  c.md\nD  d.md\n?? e/f.md\n"

    assert protected_paths.untracked(status) == frozenset({"a.md", "e/f.md"})


def test_an_empty_or_clean_status_names_nothing() -> None:
    assert protected_paths.untracked("") == frozenset()
    assert protected_paths.untracked("   \n\n") == frozenset()


def test_an_added_path_is_tracked_even_though_uncommitted_calls_it_added() -> None:
    """The two functions answer different questions of the same line, and this is the one
    line where they differ: `git add` can be asked about a staged path, not about a `??`."""
    status = "A  staged.md"

    assert protected_paths.untracked(status) == frozenset()
    assert [change.kind for change in protected_paths.uncommitted(status)] == ["added"]


# ── the archive: an untracked source is not a pathspec ──────────────────────


def test_an_untracked_story_file_is_archived_and_only_the_destination_is_staged() -> None:
    """The 2026-09-25 reproduction. The move still happens and the Answer is still appended;
    what does not happen is `git add -A -- {a path that is gone and was never tracked}`."""
    world = answered(git=FakeGit(status=[UNTRACKED_STORY], head_sha=[HEAD_SHA]))

    moved = agent_answer.archive_with_answer(world.ctx)

    assert moved == (ARCHIVED,)
    assert world.workspace.read(STORY_PATH) is None
    assert "use git rm" in (world.workspace.read(ARCHIVED) or "")


def test_a_tracked_story_file_still_reports_both_ends_of_the_rename() -> None:
    """AD-17 unchanged: the tree at `start_sha` holds this one, so the deletion is staged."""
    world = answered(git=FakeGit(status=[f" M {STORY_PATH}"], head_sha=[HEAD_SHA]))

    moved = agent_answer.archive_with_answer(world.ctx)

    assert moved == (STORY_PATH, ARCHIVED)
    assert len(moved) == BOTH_ENDS


def test_the_dispatch_that_crashed_in_production_now_reaches_the_harness() -> None:
    """End to end over the same worktree: the archive's source is never staged, so nothing
    exits 128, and the row goes on to dispatch instead of parking.

    Three status answers, in the order the dispatch reads them: the WIP sweep's, the
    archive's own, and the prepare commit's. The second is still `??` on purpose — the fake
    scripts answers rather than simulating git, and what this pins is the belt, not the
    braces: even with the sweep's tracking undone the phase asks git nothing it cannot
    answer. `None` is the sweep's own whole-tree stage."""
    world = answered(
        git=FakeGit(
            status=[UNTRACKED_STORY, UNTRACKED_STORY, f"A  {ARCHIVED}"], head_sha=[HEAD_SHA]
        )
    )

    result = run(world)

    assert [call[1] for call in world.git.called("stage")] == [None, ARCHIVED, CONTEXT_FILE]
    assert [call["method"] for call in world.harness.calls] == ["start", "wait"]
    # the harness ran, so whatever this row ends as is the tail's verdict on what it wrote —
    # what the crash made impossible was getting this far at all.
    assert result.reason != agent_prepare.PREPARE_FAILED


def test_de_ambiguation_reports_an_untracked_loser_as_its_destination_alone() -> None:
    """AD-13's archive reads by the same rule as FR-18's: two Story files, the newest kept,
    and the one moved away staged only at the end git can be asked about."""
    other = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify-2.md"
    row = an_agent_row()
    world = a_world(
        with_resolved=resolved(expect=EXPECT, retry={"max": 2, "prompt": "again"}),
        files={STORY_PATH: BLOCKED_FILE, other: BLOCKED_FILE},
        previous=an_attempt(row, 1, status="error"),
        resume=a_gate_record(row, "retry"),
        git=FakeGit(status=[f"?? {other}"], head_sha=[HEAD_SHA]),
    )

    moved = agent_answer.archive_ambiguous(world.ctx)

    # the tie is broken by name, so `STORY_PATH` is kept and `other` — the `??` one — moves
    assert moved == (f"{SPEC_FOLDER}/stories/.answers/{STORY_ID}-notify-2.md",)


def test_de_ambiguation_without_a_derivable_archive_directory_moves_nothing() -> None:
    """Operator decision, 2026-09-27: the archive directory is the declared glob's parent;
    a parent that is itself a pattern names no directory, so the ambiguity is left for the
    routing to report rather than archived into a path that does not exist."""
    other = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify-2.md"
    row = an_agent_row()
    world = a_world(
        with_resolved=resolved(
            expect={"files": [f"specs/*/stories/{STORY_ID}-*.md"], "status_in": []},
            retry={"max": 2, "prompt": "again"},
        ),
        files={STORY_PATH: BLOCKED_FILE, other: BLOCKED_FILE},
        previous=an_attempt(row, 1, status="error"),
        resume=a_gate_record(row, "retry"),
        git=FakeGit(status=[f"?? {other}"], head_sha=[HEAD_SHA]),
    )

    assert agent_answer.archive_ambiguous(world.ctx) == ()
    assert world.workspace.read(STORY_PATH) is not None
    assert world.workspace.read(other) is not None


# ── the report: git's own words, never an exception class ───────────────────


def a_refusal() -> GitError:
    return GitError(command="git add", exit_code=PATHSPEC_EXIT, output=PATHSPEC_OUTPUT)


def test_a_staging_failure_parks_misconfigured_and_carries_gits_output() -> None:
    world = a_world(git=FakeGit(stage=[a_refusal()], status=[""], head_sha=[HEAD_SHA]))

    result = run(world)

    assert result.status == "error"
    assert result.reason == agent_prepare.PREPARE_FAILED
    assert result.output_ref == PATHSPEC_OUTPUT
    assert result.park is not None
    assert (result.park.kind, result.park.path) == ("misconfigured", ROW_PATH)


def test_a_commit_failure_in_the_prepare_phase_parks_the_same_way() -> None:
    world = a_world(
        git=FakeGit(
            commit=[GitError(command="git commit", exit_code=1, output="nothing added")],
            status=[f"A  {CONTEXT_FILE}"],
            head_sha=[HEAD_SHA],
        )
    )

    result = run(world)

    assert result.reason == agent_prepare.PREPARE_FAILED
    assert result.output_ref == "nothing added"


def test_a_status_failure_inside_the_archive_is_caught_by_the_same_guard() -> None:
    """Every git call the phase makes is inside one `except`, including the archive's own.
    The first answer is the WIP sweep's, which must succeed for the phase to be reached."""
    world = answered(git=FakeGit(status=["", a_refusal()], head_sha=[HEAD_SHA]))

    result = run(world)

    assert result.reason == agent_prepare.PREPARE_FAILED
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_the_wip_sweep_is_under_the_same_rule_one_phase_earlier() -> None:
    """AD-9's second side effect makes git calls too, and an unhandled one there would
    reach the Operator exactly as the prepare phase's did."""
    world = answered(git=FakeGit(status=[UNTRACKED_STORY], stage=[a_refusal()]))

    result = run(world)

    assert result.reason == agent_workdir.WIP_FAILED
    assert result.output_ref == PATHSPEC_OUTPUT
    assert result.park is not None
    assert result.park.kind == "misconfigured"


def test_a_park_here_starts_no_harness_and_records_no_start_sha() -> None:
    """The phase is before `_start` in AD-9's order, and a park must leave it that way."""
    world = a_world(git=FakeGit(stage=[a_refusal()], status=[""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.harness.calls == []
    assert world.attempts.attempts[world.attempt.id].start_sha is None
