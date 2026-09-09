"""`terminal_poll`, the 30-second job (SPEC CAP-7, FR-21, AD-13, AD-14): notice that the
Operator finished the Story in a terminal, and resume the Run without her having to say so.

The whole rule, in the brief's own words: over Runs with `terminal_session` and status
`needs_you`, read `stories/{id}-*.md` through `Workspace` and `Git.status(cwd)` plus the
absence of `.git/index.lock`; count a poll clean when the file reads `done` and the tree is
clean, reset the count to zero when it is not, and at two send `terminal_resume`.

**Why two, and why a counter rather than a timestamp.** One poll can catch a tree mid-write:
the editor has saved the Story file and `git add` has not run yet, or a commit is between
`index.lock` and its own release. Two consecutive clean reads, 30 seconds apart, is the
cheapest evidence that the Operator has stopped rather than paused. The count lives on the
Run (`run.terminal_clean_polls`) because this job holds no state of its own between fires and
must survive a backend restart — AD-14's own standard for every scheduled sweep.

**What this job does not write.** Not a Run status and not a row status: `signal_run` is the
one writer of an Operator transition (AD-8), and this job's whole output is the
`terminal_resume` signal it sends. The two writes it does make are the counter and the
attempt's `end_sha`, neither of which is a status.

**`end_sha`, and why the terminal is a path *through* AD-17 rather than around it.** The
work the Operator did by hand is the parked attempt's work — it happened in that attempt's
session, in that attempt's worktree — so the attempt's range has to end at what the worktree
now holds. `rules/protected_paths.py::FrameAnchors` diffs `(start_sha, end_sha)` per attempt,
and without this write everything done in the terminal would be invisible to the commit
guard's protected-path check. With it, a protected path touched by hand parks
`protected_path` exactly as one touched by the agent would, and the Operator accepts it the
same way.

**Nothing here raises on an unreadable Run.** A Run with no worktree, no park row, no Story
file or several is *not clean*, so the counter resets and the Run waits — which is the same
answer the job would give while the Operator is still working, and never a crash inside a
scheduler that has no one to report it to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from orchestrator.application import story_file
from orchestrator.application.rules.routing import DONE
from orchestrator.application.rules.signals import TERMINAL_RESUMED
from orchestrator.application.steps.agent_tail import STORY_FILE_GLOB
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.workspace import Workspace, WorkspaceError
from orchestrator.domain.statuses import SignalKind
from orchestrator.domain.values import Signal

log = structlog.get_logger(__name__)

#: How many consecutive clean polls resume the Run — the brief's own figure.
CLEAN_POLLS_TO_RESUME = 2

#: The file git holds while an index write is in flight. Present, the tree is not clean
#: however empty `git status` looks: the status was read a moment before or after the write.
INDEX_LOCK = ".git/index.lock"

#: The signal two clean polls send (AD-13). `signal_run` reads `Rule.actor` off the table,
#: which says `terminal` for this kind, so the gate record names the terminal and not the
#: Operator — this job passes no actor of its own.
TERMINAL_RESUME: SignalKind = "terminal_resume"

#: What the gate record says, verbatim from the brief. Re-exported rather than restated:
#: AD-13's table is the one statement of what each signal records, and `terminal_resume`'s row
#: carries this sentence because this job is that kind's only sender. A second copy here would
#: be two sentences one edit apart.
RESUMED_TEXT = TERMINAL_RESUMED


@dataclass(frozen=True)
class TerminalPollPorts:
    """What one poll reads and writes through.

    One `SignalPorts` and no unit of work of its own: `signal_run` opens `writers.uow` for
    itself, so this job opens and closes the same scope around each of its own two writes and
    never holds one across the signal. A nested entry would orphan the outer session
    (`infrastructure/db/writers.py::SessionUnitOfWork`, and the fake refuses it outright).
    """

    signal: SignalPorts
    git: Git
    #: A factory, not an instance: the root is one Run's own `worktree_path`, which this job
    #: does not know until it has read the Run (`api/providers.py::run_files_ports`'s own
    #: shape, and `infrastructure/dbos/startup.py::walker_deps`'s).
    workspace: Callable[[str | None], Workspace]


def run_terminal_poll(ports: TerminalPollPorts) -> list[UUID]:
    """One fire of the job. Returns the ids of the Runs it resumed, for the log and a test."""
    resumed: list[UUID] = []
    for run in _polled(ports):
        if _poll_one(ports, run):
            resumed.append(run.id)
    return resumed


def _polled(ports: TerminalPollPorts) -> list[Run]:
    """Every Run with a terminal session open and stopped for the Operator (the brief's set).

    A Run that is `running` with the flag still set is deliberately not polled: the flag is
    cleared by `terminal_resume` and by `terminal_release`, so the only way to see one is a
    Run that moved on some other way, and re-resuming it would be a second signal on a Run
    that never asked for one.
    """
    writers = ports.signal.writers
    return [run for run in writers.runs.list_by_status("needs_you") if run.terminal_session]


def _poll_one(ports: TerminalPollPorts, run: Run) -> bool:
    """Count this Run's poll and, at the threshold, resume it. True when it was resumed."""
    park_row = _park_row(ports, run)
    clean = _is_clean(ports, run, park_row)
    count = run.terminal_clean_polls + 1 if clean else 0
    if count < CLEAN_POLLS_TO_RESUME:
        _store(ports, run, count)
        return False
    # spent, not kept: the flag is about to be cleared, and a later session on this Run has
    # to start counting from nothing rather than resume on its very first clean poll
    _store(ports, run, 0)
    assert park_row is not None  # a clean poll read the park row's own Story file
    _record_end_sha(ports, run, park_row)
    signal_run(ports.signal, run.id, Signal(kind=TERMINAL_RESUME, payload={}))
    log.info("terminal poll resumed", run_id=str(run.id), path=park_row.path)
    return True


def _store(ports: TerminalPollPorts, run: Run, count: int) -> None:
    """Write the counter, unless it already says that — an unchanged Run needs no write."""
    if run.terminal_clean_polls == count:
        return
    writers = ports.signal.writers
    with writers.uow:
        writers.runs.update(run.model_copy(update={"terminal_clean_polls": count}))
        writers.uow.commit()


def _park_row(ports: TerminalPollPorts, run: Run) -> StepRun | None:
    rows = ports.signal.writers.steps.list_for_run(run.id)
    return next((row for row in rows if row.path == run.park_path), None)


def _is_clean(ports: TerminalPollPorts, run: Run, park_row: StepRun | None) -> bool:
    """The Story file reads `done` and the worktree holds nothing uncommitted or in flight."""
    if park_row is None or run.worktree_path is None:
        return False
    try:
        workspace = ports.workspace(run.worktree_path)
        if not _story_is_done(workspace, park_row):
            return False
        if workspace.exists(INDEX_LOCK):
            return False
    except WorkspaceError:
        # a worktree the sweep cannot read is not a clean one; the Run waits
        return False
    return not ports.git.status(Path(run.worktree_path)).strip()


def _story_is_done(workspace: Workspace, park_row: StepRun) -> bool:
    """FR-16's own glob and FR-16's own `done`, read from the worktree the Operator edits.

    Exactly one match, as `rules/routing.py::_liveness` requires: zero is a Story that was
    never written and several is an ambiguity nothing here may resolve — both are "not done
    yet" for a poll, and both are what the `agent` row's own routing would stop on anyway.
    """
    resolved = park_row.with_resolved
    pattern = STORY_FILE_GLOB.format(
        spec_folder=str(resolved.get(SPEC_FOLDER_KEY) or ""),
        story_id=str(resolved.get(STORY_ID_KEY) or park_row.story_id or ""),
    )
    matches = workspace.glob(pattern)
    if len(matches) != 1:
        return False
    parsed = story_file.parse(matches[0], workspace.read(matches[0]) or "")
    return parsed is not None and parsed.status == DONE


def _record_end_sha(ports: TerminalPollPorts, run: Run, park_row: StepRun) -> None:
    """Close the parked attempt's own diff range at what the worktree now holds (AD-17).

    Silent when the row has no attempt or git reports no HEAD: neither is reachable from a
    park this poll can reach — a `blocked` park is written by a dispatch that ran — and
    neither is worth failing a resume over if it ever became so.
    """
    writers = ports.signal.writers
    attempt = writers.attempts.get_latest(park_row.id)
    if attempt is None or run.worktree_path is None:
        return
    head = ports.git.head_sha(Path(run.worktree_path))
    if head is None or head == attempt.end_sha:
        return
    with writers.uow:
        writers.attempts.update(attempt.model_copy(update={"end_sha": head}))
        writers.uow.commit()
