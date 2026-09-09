"""`terminal_poll` (SPEC CAP-7, FR-21, AD-13, AD-14): two clean polls resume the Run.

The job's own rule is a counter, and a counter is only interesting at its edges, so what is
asserted here is the whole edge set: the first clean poll counts and sends nothing, the
second sends, and every way a poll can be unclean puts the count back to zero.

**The assertion this module exists for is the last one.** This codebase has now shipped three
signal effects that moved a row and enqueued nothing, leaving the Run unrecoverable —
`continue` on a `plan_stale` park, and both halves of `_budget_raise`. `terminal_resume` moves
the agent row `blocked → done` and is supposed to queue its successor, and "the repository
holds a `queued` row" is not the same claim as "the walk finds work": `use_cases/walk.py::
next_row` has exactly three ways of finding any, and a row can satisfy the repository without
satisfying it. So `test_the_walk_finds_the_successor_after_a_terminal_resume` asks `next_row`
itself, which is the question the walker asks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.jobs.terminal_poll import (
    CLEAN_POLLS_TO_RESUME,
    INDEX_LOCK,
    RESUMED_TEXT,
    TerminalPollPorts,
    run_terminal_poll,
)
from orchestrator.application.steps.context import StepPorts
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.application.use_cases.walk import WalkPorts, next_row
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.workspace import FakeWorkspace

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
SPEC_FOLDER = "specs/gates"
STORY_ID = "1"
STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-answer-the-question.md"
WORKTREE = "/work/acme/orchestrator/wt/epics-1"
HEAD = "c0ffee0000000000000000000000000000000000"
START_SHA = "1111111111111111111111111111111111111111"

DONE_FILE = "---\nstatus: done\n---\n\n# Answer the question\n"
BLOCKED_FILE = "---\nstatus: blocked\n---\n\n## Auto Run Result\n\nBlocking condition: intent gap\n"
#: The brief's own threshold, restated so the constant is compared with a written figure
#: rather than with itself.
BRIEFS_THRESHOLD = 2


def a_parked_world(*, clean_polls: int = 0, **over: object) -> World:
    """A Run stopped `blocked` on `stories[0].build` with a terminal session in progress."""
    fields: dict[str, object] = {
        "park_kind": "blocked",
        "park_path": BUILD,
        "park_reason": "intent gap",
        "worktree_path": WORKTREE,
        "terminal_session": True,
        "terminal_clean_polls": clean_polls,
    }
    fields.update(over)
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        {BUILD: {SPEC_FOLDER_KEY: SPEC_FOLDER, STORY_ID_KEY: STORY_ID}},
        **fields,
    )
    an_attempt(
        world,
        BUILD,
        status="blocked",
        harness="claude",
        session_id="1f0a-session",
        start_sha=START_SHA,
        ended_at=datetime(2026, 9, 7, 9, 30, tzinfo=UTC),
    )
    return world


def poll_ports(
    world: World,
    *,
    files: dict[str, str] | None = None,
    status: str = "",
    head: str | None = HEAD,
) -> TerminalPollPorts:
    workspace = FakeWorkspace(WORKTREE, {STORY_PATH: DONE_FILE} if files is None else files)
    git = FakeGit(status=[status], head_sha=[head])
    return TerminalPollPorts(signal=world.signal_ports, git=git, workspace=lambda _root: workspace)


def stored_polls(world: World) -> int:
    return world.stored_run().terminal_clean_polls


# ── the happy path, one poll at a time ───────────────────────────────────────


def test_the_first_clean_poll_counts_and_sends_nothing() -> None:
    world = a_parked_world()

    resumed = run_terminal_poll(poll_ports(world))

    assert resumed == []
    assert stored_polls(world) == 1
    assert world.status_of(BUILD) == "blocked"
    assert world.stored_run().status == "needs_you"
    assert world.events() == []


def test_the_second_clean_poll_resumes_the_run_from_the_terminal() -> None:
    world = a_parked_world(clean_polls=1)

    resumed = run_terminal_poll(poll_ports(world))

    assert resumed == [world.run.id]
    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"
    assert world.stored_run().status == "running"
    assert world.stored_run().terminal_session is False


def test_the_threshold_is_two_and_the_counter_is_spent_when_it_fires() -> None:
    """Spent rather than kept: a later terminal session on the same Run must count again
    from nothing rather than resume on its very first clean poll."""
    world = a_parked_world(clean_polls=CLEAN_POLLS_TO_RESUME - 1)

    run_terminal_poll(poll_ports(world))

    assert CLEAN_POLLS_TO_RESUME == BRIEFS_THRESHOLD
    assert stored_polls(world) == 0


def test_the_gate_record_names_the_terminal_and_says_what_the_poll_saw() -> None:
    world = a_parked_world(clean_polls=1)

    run_terminal_poll(poll_ports(world))

    record = world.records()[-1]
    assert record.event == "terminal_resume"
    assert record.actor == "terminal"
    assert record.text == RESUMED_TEXT
    assert record.path == BUILD


def test_the_engine_is_woken_so_the_walk_actually_restarts() -> None:
    """`signal_run` calls `engine.signal` only when *this* signal moved the Run to `running`
    — a resume nobody told the engine about is a Run that sits still."""
    world = a_parked_world(clean_polls=1)

    run_terminal_poll(poll_ports(world))

    assert [call[0] for call in world.engine.calls] == ["signal"]


def test_the_walk_finds_the_successor_after_a_terminal_resume() -> None:
    """The failure this codebase keeps repeating: a signal that moves a row and enqueues
    nothing. `next_row` is the question the walker asks, so it is the one asked here."""
    world = a_parked_world(clean_polls=1)

    run_terminal_poll(poll_ports(world))
    walk = WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORKTREE),
    )
    seq = next_row(walk, world.run.id)

    assert seq == world.row(VERIFY).seq


def test_the_attempts_diff_range_is_closed_at_head_so_ad17_still_sees_the_work() -> None:
    """What the Operator did by hand belongs to the parked attempt, so the commit guard's
    protected-path check has to be able to diff it (`rules/protected_paths.py`)."""
    world = a_parked_world(clean_polls=1)

    run_terminal_poll(poll_ports(world))

    attempt = world.attempts_of(BUILD)[-1]
    assert attempt.start_sha == START_SHA
    assert attempt.end_sha == HEAD


# ── every way a poll can be unclean ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "files", "status"),
    [
        ("a dirty tree", {STORY_PATH: DONE_FILE}, " M src/app.py"),
        ("an index lock", {STORY_PATH: DONE_FILE, INDEX_LOCK: ""}, ""),
        ("a story file that is still blocked", {STORY_PATH: BLOCKED_FILE}, ""),
        ("no story file at all", {}, ""),
        (
            "two story files",
            {
                STORY_PATH: DONE_FILE,
                f"{SPEC_FOLDER}/stories/{STORY_ID}-second.md": DONE_FILE,
            },
            "",
        ),
        ("a story file with unreadable frontmatter", {STORY_PATH: "no frontmatter here\n"}, ""),
    ],
    ids=["dirty", "index-lock", "blocked", "missing", "ambiguous", "unreadable"],
)
def test_an_unclean_poll_resets_the_counter_to_zero(
    label: str, files: dict[str, str], status: str
) -> None:
    world = a_parked_world(clean_polls=1)

    resumed = run_terminal_poll(poll_ports(world, files=files, status=status))

    assert resumed == [], label
    assert stored_polls(world) == 0, label
    assert world.status_of(BUILD) == "blocked", label


def test_a_dirty_tree_between_two_clean_polls_starts_the_count_over() -> None:
    """The acceptance criterion's own sequence: clean, dirty, clean — and still no resume."""
    world = a_parked_world()

    run_terminal_poll(poll_ports(world))
    assert stored_polls(world) == 1
    run_terminal_poll(poll_ports(world, status=" M src/app.py"))
    assert stored_polls(world) == 0
    run_terminal_poll(poll_ports(world))

    assert stored_polls(world) == 1
    assert world.status_of(BUILD) == "blocked"
    assert world.stored_run().status == "needs_you"


def test_a_run_with_no_worktree_is_never_clean() -> None:
    world = a_parked_world(clean_polls=1, worktree_path=None)

    resumed = run_terminal_poll(poll_ports(world))

    assert resumed == []
    assert stored_polls(world) == 0


def test_a_park_that_names_no_row_is_never_clean() -> None:
    """`Park.path` is optional, and a poll that cannot find the row cannot read its Story
    file — so it waits rather than resuming a row it did not identify."""
    world = a_parked_world(clean_polls=1, park_path="nowhere")

    resumed = run_terminal_poll(poll_ports(world))

    assert resumed == []
    assert stored_polls(world) == 0


def test_a_workspace_that_refuses_the_read_is_never_clean() -> None:
    """A rootless `Workspace` raises `WorkspaceError`; a scheduler has no one to report an
    exception to, so the Run waits instead."""
    world = a_parked_world(clean_polls=1)
    ports = TerminalPollPorts(
        signal=world.signal_ports,
        git=FakeGit(head_sha=[HEAD]),
        workspace=lambda _root: FakeWorkspace(None),
    )

    assert run_terminal_poll(ports) == []
    assert stored_polls(world) == 0


# ── which Runs are polled at all ─────────────────────────────────────────────


def test_a_run_without_a_terminal_session_is_not_polled() -> None:
    world = a_parked_world(clean_polls=1)
    world.ports.runs.update(world.run.model_copy(update={"terminal_session": False}))

    resumed = run_terminal_poll(poll_ports(world))

    assert resumed == []
    assert world.status_of(BUILD) == "blocked"
    assert stored_polls(world) == 1


def test_a_run_that_is_not_parked_is_not_polled() -> None:
    """`list_by_status("needs_you")` is the whole set, so a Run that moved on some other way
    is never resumed a second time by a flag nobody cleared."""
    world = a_parked_world(clean_polls=1)
    world.ports.runs.update(world.run.model_copy(update={"status": "running"}))

    assert run_terminal_poll(poll_ports(world)) == []
    assert world.status_of(BUILD) == "blocked"


def test_the_poll_reads_the_rows_own_liveness_glob() -> None:
    """FR-16's glob, resolved from the parked row's own `spec_folder`/`story_id` — the same
    pattern the `agent` executor's own routing asked."""
    world = a_parked_world()
    workspace = FakeWorkspace(WORKTREE, {STORY_PATH: DONE_FILE})
    ports = TerminalPollPorts(
        signal=world.signal_ports,
        git=FakeGit(head_sha=[HEAD]),
        workspace=lambda _root: workspace,
    )

    run_terminal_poll(ports)

    assert workspace.globbed == [f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md"]


def test_the_tree_is_read_at_the_runs_own_worktree() -> None:
    world = a_parked_world()
    git = FakeGit(head_sha=[HEAD])
    run_terminal_poll(
        TerminalPollPorts(
            signal=world.signal_ports,
            git=git,
            workspace=lambda _root: FakeWorkspace(WORKTREE, {STORY_PATH: DONE_FILE}),
        )
    )

    assert ("status", (Path(WORKTREE),)) in git.calls


# ── the writes the job makes, and the ones it does not ───────────────────────


def test_a_poll_that_changes_nothing_writes_nothing() -> None:
    """An unclean poll on a Run already at zero — the ordinary steady state while the
    Operator is still typing. A write per Run per 30 s for a counter that did not move would
    be the whole poll set rewritten every fire, for nothing."""
    world = a_parked_world()

    run_terminal_poll(poll_ports(world, files={}, status=""))

    assert stored_polls(world) == 0
    assert ("update", world.run.id) not in world.ports.runs.calls


def test_a_row_that_never_ran_an_attempt_still_resumes() -> None:
    """`end_sha` is best-effort: a park this poll can reach was written by a dispatch, so
    there is always an attempt — and a resume must not be lost if there ever is not."""
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        {BUILD: {SPEC_FOLDER_KEY: SPEC_FOLDER, STORY_ID_KEY: STORY_ID}},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="intent gap",
        worktree_path=WORKTREE,
        terminal_session=True,
        terminal_clean_polls=1,
    )

    assert run_terminal_poll(poll_ports(world)) == [world.run.id]
    assert world.attempts_of(BUILD) == []


def test_an_end_sha_that_is_already_head_is_not_rewritten() -> None:
    """Nothing was committed in the terminal — the Operator only edited the Story file and
    the agent's own commit is still HEAD. The range is already right; leave it."""
    world = a_parked_world(clean_polls=1)
    attempt = world.attempts_of(BUILD)[-1]
    world.ports.attempts.update(attempt.model_copy(update={"end_sha": HEAD}))

    run_terminal_poll(poll_ports(world))

    assert world.attempts_of(BUILD)[-1].end_sha == HEAD
    assert world.stored_run().status == "running"


def test_a_worktree_git_reports_no_head_for_still_resumes() -> None:
    """`head_sha` answers `None` on a repository with no commit at all; the resume is the
    point, and the diff range simply stays where the dispatch left it."""
    world = a_parked_world(clean_polls=1)

    resumed = run_terminal_poll(poll_ports(world, head=None))

    assert resumed == [world.run.id]
    assert world.attempts_of(BUILD)[-1].end_sha is None
