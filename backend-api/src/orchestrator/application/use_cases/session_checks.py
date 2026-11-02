"""What refuses `session_start` and `session_end` before a row moves, and the session's
anchor edits (AD-10, AD-17, AD-23).

`signals._refuse_early` calls `refuse` after `validate`, so the table's own refusals keep
their text. Nothing here writes: the start's checks read the registry and re-read the Probe,
and the close's read both trees through `Git`. The one thing handed on is `turns`, written
into the close's payload so the effect can re-count under the row lock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from orchestrator.application.rules import protected_paths, session
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.application.use_cases.walk_frame import INITIATIVE_FOLDER_INPUT, row_workdir
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.git import Change, Git
from orchestrator.domain.ports.harness import Harness
from orchestrator.domain.values import Signal

UNKNOWN_SCOPE = "unknown scope {scope}: one of {scopes}"
NO_FRAME = "no {scope} frame at {path}"
UNKNOWN_HARNESS = "unknown harness {name}"
NO_RESUME = "harness {name} cannot resume a session"
PROBE_FAILED = "probe failed"
MODEL_UNLISTED = "model {model!r} not in probed list: {models}"
NO_WORKTREE = "no worktree yet"
NO_BUDGET = "no remaining budget"
UNCONFIRMED = "anchor edits neither confirmed nor reverted: {paths}"
NOT_AN_EDIT = "not an anchor edit of this session: {paths}"

#: The Run input naming its spec folder, as `infrastructure/db/environment.py` reads it.
SPEC_FOLDER_INPUT = "spec_folder"


@dataclass(frozen=True)
class SessionPorts:
    """The writers' reads, the `Git` the trees are diffed through, and the live registry."""

    writers: WriterPorts
    git: Git
    harnesses: Mapping[str, Harness] = field(default_factory=dict)


def refuse(
    ports: SessionPorts, run: Run, rows: Sequence[StepRun], row: StepRun | None, signal: Signal
) -> None:
    """Raise the first refusal that applies to a session kind; any other kind passes."""
    if signal.kind == "session_start":
        _refuse_start(ports, run, rows, signal)
    elif signal.kind == "session_end":
        _refuse_end(ports, run, rows, row, signal)


def turns(ports: SessionPorts, run: Run, row: StepRun | None) -> tuple[Attempt, ...]:
    """The open session's attempts on the parked row (AD-21: role `session`)."""
    if row is None:
        return ()
    attempts = ports.writers.attempts.list_for_row(row.id)
    return session.session_attempts(attempts, ports.writers.records.list_for_run(run.id))


def anchor_edits(
    ports: SessionPorts, run: Run, rows: Sequence[StepRun], row: StepRun | None
) -> tuple[Change, ...]:
    """Every anchor the session's attempts changed and did not revert, tests excluded.

    Each tree is diffed from the session's first start SHA in it to its HEAD, unioned with
    what it holds uncommitted, and spelled the way `steps/agent_workdir.changes` spells an
    attempt's changes. A tree with no start SHA contributes nothing.
    """
    if run.worktree_path is None:
        return ()
    start_sha, root_start_sha = session.first_shas(turns(ports, run, row))
    root = Path(run.worktree_path)
    workdir = row_workdir(row)
    changes = list(_tree_changes(ports.git, root / workdir if workdir else root, start_sha))
    if workdir:
        changes = [replace(change, path=f"{workdir}/{change.path}") for change in changes]
        changes.extend(
            change
            for change in _tree_changes(ports.git, root, root_start_sha)
            if change.path != workdir and not change.path.startswith(f"{workdir}/")
        )
    return session.anchor_edits(changes, _anchors(run, rows))


def _refuse_start(ports: SessionPorts, run: Run, rows: Sequence[StepRun], signal: Signal) -> None:
    scope = str(signal.payload.get(session.SCOPE_KEY, ""))
    if scope not in session.SCOPES:
        raise Invalid(UNKNOWN_SCOPE.format(scope=scope, scopes=", ".join(session.SCOPES)))
    if scope not in session.scopes_at(run.park_path, rows):
        raise Invalid(NO_FRAME.format(scope=scope, path=run.park_path))
    name = str(signal.payload.get(session.HARNESS_KEY, ""))
    harness = ports.harnesses.get(name)
    if harness is None:
        raise Invalid(UNKNOWN_HARNESS.format(name=name))
    if not harness.capabilities.resume:
        raise Invalid(NO_RESUME.format(name=name))
    probe = harness.probe()
    if not probe.ok:
        raise Invalid(probe.failing_reason or PROBE_FAILED)
    model = signal.payload.get(session.MODEL_KEY)
    if model and probe.models and model not in probe.models:
        raise Invalid(MODEL_UNLISTED.format(model=model, models=list(probe.models)))
    if run.worktree_path is None:
        raise Conflict(NO_WORKTREE)
    if run.budget_usd is not None and run.budget_usd - run.spend_usd <= 0:
        raise Conflict(NO_BUDGET)


def _refuse_end(
    ports: SessionPorts, run: Run, rows: Sequence[StepRun], row: StepRun | None, signal: Signal
) -> None:
    read = turns(ports, run, row)
    if session.turn_open(read):
        raise Conflict(TURN_RUNNING)
    edits = [edit.path for edit in anchor_edits(ports, run, rows, row)]
    confirmed = session.confirmed_paths(signal.payload)
    extra = [path for path in confirmed if path not in edits]
    if extra:
        raise Invalid(NOT_AN_EDIT.format(paths=", ".join(extra)))
    unconfirmed = [path for path in edits if path not in confirmed]
    if unconfirmed:
        raise Conflict(UNCONFIRMED.format(paths=", ".join(unconfirmed)))
    signal.payload[session.TURNS_KEY] = len(read)


def _tree_changes(git: Git, tree: Path, start_sha: str | None) -> tuple[Change, ...]:
    if start_sha is None:
        return ()
    head = git.head_sha(tree)
    ranged = git.diff_changes(tree, start_sha, head) if head is not None else ()
    return (*ranged, *protected_paths.uncommitted(git.status(tree)))


def _anchors(run: Run, rows: Sequence[StepRun]) -> frozenset[str]:
    folders = {str(run.inputs.get(SPEC_FOLDER_INPUT) or "")}
    folders.update(str(row.with_resolved.get(SPEC_FOLDER_KEY) or "") for row in rows)
    return protected_paths.build(
        spec_folders=sorted(folder for folder in folders if folder),
        initiative_folder=str(run.inputs.get(INITIATIVE_FOLDER_INPUT) or ""),
        frozen_test_files=(),
    )
