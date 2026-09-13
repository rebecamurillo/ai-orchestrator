"""`GET`/`PUT /runs/{id}/files` (story 6-2 read, story 6-3 tree + write; SPEC CAP-2, FR-19):
a look inside a Run's own spec folder — the planned story file a spec checkpoint shows
inline (6-2), the tree an Operator browses and the file they edit while parked (6-3).

Three refusals over the read/tree scope, in the order this module checks them so
`path=../x` is always 422 even though it would also fail the narrower `{spec_folder}` scope
check: a path that escapes the workspace at all (`..`, absolute) is `Invalid` regardless of
which Run asked; a well-formed path outside this Run's own `{spec_folder}`/
`{initiative_folder}` is `Forbidden`; a path inside it that names nothing is `NotFound` —
the same three-way split `Workspace` itself draws between a malformed path and one that is
merely absent (`domain/ports/workspace.py`'s own docstring).

**The one path this endpoint resolves a glob for.** The spec-checkpoint body asks for
`{spec_folder}/stories/{id}-*.md` — the brief's own words — because the screen does not
know the planned file's slug. Resolved here rather than on the wire, the same reasoning
`agent_answer.archive_with_answer` already applies to the identical glob: zero matches is
`NotFound`, more than one is not `misconfigured` (this is a read, not a routing decision) —
the newest is shown, `Workspace.mtime`'s own purpose.

**`write_run_file` (6-3): the direct worktree write outside `signal_run`.** Five checks, in
this order — 404 (no such Run), 422 (the path escapes the workspace), 403 (well formed but
outside the Run's own scope folder), 409 (the path names a list file the plan already read,
which would silently desync `run.plan_refs`), 409 (the Run is not parked without a terminal
session) — then `Workspace.write`, `Git.stage(worktree, pathspec=path)`,
`Git.commit(worktree, ...)` (staging only `path` is what keeps the commit to "only that
path"), one `GateRecord(event="spec_edit")`, and `uow.commit()`. The result is the same
shape a tree row is (`path`, `kind`, `size`, `mtime`), so `write_run_file` returns a
`TreeEntry` too rather than a fourth dataclass.

**`diff_run_file` (6.6): the one read that is deliberately *not* spec-folder scoped.** The
protected-path body links each file AD-17 flagged to its own unified diff, and AD-17's
anchors are `AGENTS.md` wherever it is and every frozen test file (`rules/protected_paths.py
::build`/`check`) — every one of them outside the Run's spec folder by construction. Running
`_within_spec_folder` here would 403 exactly the paths the mode exists to show. The honest
answer is not a wider scope but a different, tighter one: the path has to be one of the hits
**this Run's own park recorded**, which is a list the Run wrote itself and is strictly
narrower than "any file in the worktree". `_escapes` is reused unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

from orchestrator.application.rules.protected_paths import hit_paths, park_record_payload
from orchestrator.application.rules.signals import row_at
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, Forbidden, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.ports.workspace import TreeEntry, Workspace, WorkspaceError

INVALID_PATH = "path escapes the workspace: {path}"
OUTSIDE_SPEC_FOLDER = "path outside the run's spec folder: {path}"
NO_SUCH_FILE = "no file at {path}"
#: The `diff` mode's own two refusals (6.6).
NOT_A_PROTECTED_HIT = "path is not one of this run's protected paths: {path}"
NO_ATTEMPT_SHA = "the parked step recorded no start commit to diff against"
#: The write's own two 409s (the Always section, verbatim).
PLANNED_AT = "planned at {sha} — start a new run to change the list"
PARKED_REQUIRED = "editing requires a parked run without a terminal session"
#: The commit message every operator edit lands under, verbatim (the Always section).
COMMIT_MESSAGE = "spec: operator edit (orchestrator)"

#: Glob metacharacters `Path.glob` treats specially — the one thing that makes a `path` a
#: pattern rather than a literal file to read (`agent_answer.archive_path`'s own `*-*.md`).
_GLOB_CHARS = frozenset("*?[")


@dataclass(frozen=True)
class RunFile:
    path: str
    content: str
    size: int
    mtime: float


@dataclass(frozen=True)
class RunFilesTree:
    """`GET /runs/{id}/files` with no `path`: every entry under the Run's own scope folder."""

    root: str
    entries: tuple[TreeEntry, ...]
    #: The Run's prior visit timestamp — the cutoff for changed-marks computation (story 8-3).
    #: `None` when the Run has never been opened before (`last_opened_before` is `None`).
    last_opened_before: datetime | None = None


@dataclass(frozen=True)
class RunFileDiff:
    """One protected path's unified diff, and the commit it is measured from."""

    path: str
    from_sha: str
    diff: str


@dataclass(frozen=True)
class RunFilesPorts:
    runs: RunRepository
    #: A `Workspace` factory, rooted per Run (`FsWorkspace` itself, the class — the same
    #: "port is the class" shape `StepPorts.workspace` already uses) — this use case cannot
    #: build one until it has read the Run's own `worktree_path`.
    workspace: Callable[[str | None], Workspace]


@dataclass(frozen=True)
class RunFilesWritePorts:
    """`PUT /runs/{id}/files`'s own ports: `RunFilesPorts`' shape, plus what a write needs —
    `Git` to stage and commit, a `GateRecordRepository` for the `spec_edit` line, a `Clock`
    for its `at`, and the `UnitOfWork` itself so the use case can `commit()`."""

    runs: RunRepository
    workspace: Callable[[str | None], Workspace]
    git: Git
    records: GateRecordRepository
    clock: Clock
    uow: UnitOfWork


@dataclass(frozen=True)
class RunFilesDiffPorts:
    """`GET /runs/{id}/files?diff=1`'s own ports. No `Workspace`: `Git` reads the tree.

    `steps`/`attempts` are what resolve the attempt whose `start_sha` the diff runs from —
    the same "before the harness started" end AD-17's own check uses (`steps/agent_tail.py::
    _changes`), so the Operator reads exactly the change the Run stopped for.
    """

    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    records: GateRecordRepository
    git: Git


def read_run_file(ports: RunFilesPorts, run_id: UUID, path: str) -> RunFile:
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    if _escapes(path):
        raise Invalid(INVALID_PATH.format(path=path))
    if not _within_spec_folder(path, run):
        raise Forbidden(OUTSIDE_SPEC_FOLDER.format(path=path))
    workspace = ports.workspace(run.worktree_path)
    try:
        found = _read(workspace, path)
    except WorkspaceError as error:
        # A rootless Workspace (no `git.worktree` row yet) refuses every call the same way
        # an escaping path does — caught around the whole read, not just `_resolve`, so a
        # literal path (which never touches the workspace inside `_resolve` itself) is
        # covered too.
        raise Invalid(str(error)) from error
    if found is None:
        raise NotFound(NO_SUCH_FILE.format(path=path))
    return found


def list_files_tree(ports: RunFilesPorts, run_id: UUID) -> RunFilesTree:
    """`GET /runs/{id}/files` with no `path` (6-3): every entry under this Run's own scope
    folder, recursively. No write capability needed, so this reuses `RunFilesPorts` as is.

    A Run with no `spec_folder`/`initiative_folder` at all (`_scope_folder` answers `""`)
    answers an empty tree rather than `workspace.tree("")` — every other path this module
    (and `_within_spec_folder`, the read's own gate) refuses admits nothing for that Run;
    listing the whole worktree in that one case would be the loophole the refusal exists to
    close.
    """
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    folder = _scope_folder(run)
    if not folder:
        return RunFilesTree(root="", entries=(), last_opened_before=run.last_opened_before)
    workspace = ports.workspace(run.worktree_path)
    try:
        entries = workspace.tree(folder)
    except WorkspaceError as error:
        raise Invalid(str(error)) from error
    return RunFilesTree(root=folder, entries=entries, last_opened_before=run.last_opened_before)


def write_run_file(ports: RunFilesWritePorts, run_id: UUID, path: str, content: str) -> TreeEntry:
    """`PUT /runs/{id}/files` (6-3): see the module docstring for the five checks and their
    order. Returns the written file as a `TreeEntry` — "the response carries the new mtime"
    (AC1), and the write's own result is the same shape a tree row is."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    if _escapes(path):
        raise Invalid(INVALID_PATH.format(path=path))
    if not _within_spec_folder(path, run):
        raise Forbidden(OUTSIDE_SPEC_FOLDER.format(path=path))
    if path in run.plan_refs:
        raise Conflict(PLANNED_AT.format(sha=run.plan_refs[path]))
    if run.status != "needs_you" or run.terminal_session:
        raise Conflict(PARKED_REQUIRED)
    workspace = ports.workspace(run.worktree_path)
    try:
        current = workspace.read(path)
        if current == content:
            # Byte-identical to what is already there: `git commit` exits non-zero with
            # nothing staged ("nothing to commit"), so writing, staging and committing a
            # no-op would crash rather than succeed. A Save that changed nothing is still a
            # 200 with the file's own current entry — no commit, no gate record.
            return TreeEntry(
                path=path,
                is_dir=False,
                size=len(content.encode("utf-8")),
                mtime=workspace.mtime(path),
            )
        workspace.write(path, content)
        mtime = workspace.mtime(path)
    except WorkspaceError as error:
        raise Invalid(str(error)) from error
    assert run.worktree_path is not None  # the read/write above already refused a rootless one
    worktree = Path(run.worktree_path)
    ports.git.stage(worktree, pathspec=path)
    ports.git.commit(worktree, COMMIT_MESSAGE)
    ports.records.add(
        GateRecord(
            id=new_id(),
            run_id=run.id,
            at=ports.clock.now(),
            # The row this record is about is the parked one (AD-8's own rule), not the file
            # that was just edited.
            path=run.park_path,
            event="spec_edit",
            actor="operator",
            text=f"edited {path}",
        )
    )
    ports.uow.commit()
    # Byte length, not `len(content)` (character count): `RunFilesTree`'s own rows are
    # `stat.st_size` (`FsWorkspace.tree`'s own `_entry`), and this response is documented as
    # "the same shape a tree row is" — a character count would silently disagree with that
    # for any multi-byte UTF-8 content.
    return TreeEntry(path=path, is_dir=False, size=len(content.encode("utf-8")), mtime=mtime)


def _escapes(path: str) -> bool:
    pure = PurePosixPath(path)
    return pure.is_absolute() or ".." in pure.parts


def _scope_folder(run: Run) -> str:
    """The one folder every read, tree and write is scoped to: the Run's own `spec_folder`,
    falling back to `initiative_folder` — `run_views.py::_header`'s own fallback, read the
    same way here."""
    return str(run.inputs.get("spec_folder") or run.inputs.get("initiative_folder") or "")


def _within_spec_folder(path: str, run: Run) -> bool:
    folder = _scope_folder(run)
    return bool(folder) and (path == folder or path.startswith(f"{folder}/"))


def _read(workspace: Workspace, path: str) -> RunFile | None:
    resolved = _resolve(workspace, path)
    if resolved is None:
        return None
    content = workspace.read(resolved)
    if content is None:
        return None
    return RunFile(
        path=resolved,
        content=content,
        size=len(content.encode("utf-8")),
        mtime=workspace.mtime(resolved),
    )


def _resolve(workspace: Workspace, path: str) -> str | None:
    if not any(char in path for char in _GLOB_CHARS):
        return path
    matches = workspace.glob(path)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return max(matches, key=workspace.mtime)


def diff_run_file(ports: RunFilesDiffPorts, run_id: UUID, path: str) -> RunFileDiff:
    """`GET /runs/{id}/files?path=&diff=1` (6.6): one protected path's unified diff.

    Refusals in the same shape `read_run_file` uses, and in the same order: 404 (no such
    Run), 422 (the path escapes the workspace), 403 (the path is not one of this park's own
    recorded hits — see the module docstring for why the spec-folder scope cannot be the
    gate here), 404 (the parked row recorded no `start_sha`, so there is no range to read).
    """
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    if _escapes(path):
        raise Invalid(INVALID_PATH.format(path=path))
    hits = hit_paths(park_record_payload(ports.records.list_for_run(run_id), run))
    if path not in hits:
        raise Forbidden(NOT_A_PROTECTED_HIT.format(path=path))
    attempt = _park_attempt(ports, run)
    if attempt is None or attempt.start_sha is None or run.worktree_path is None:
        raise NotFound(NO_ATTEMPT_SHA)
    diff = ports.git.diff(Path(run.worktree_path), attempt.start_sha, path)
    return RunFileDiff(path=path, from_sha=attempt.start_sha, diff=diff)


def _park_attempt(ports: RunFilesDiffPorts, run: Run) -> Attempt | None:
    """The latest Attempt of the row the Run parked on, or `None` when it made none."""
    row = row_at(ports.steps.list_for_run(run.id), run.park_path)
    if row is None:
        return None
    attempts = ports.attempts.list_for_row(row.id)
    return max(attempts, key=lambda attempt: attempt.n, default=None)
