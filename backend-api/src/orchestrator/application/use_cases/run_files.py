"""`GET /runs/{id}/files` (story 6-2, SPEC CAP-2, FR-19): a read-only look at one file
inside a Run's own spec folder — the planned story file a spec checkpoint shows inline.
No write here; 6-3 is the story that adds one.

Three refusals, in the order this module checks them so `path=../x` is always 422 even
though it would also fail the narrower `{spec_folder}` scope check: a path that escapes the
workspace at all (`..`, absolute) is `Invalid` regardless of which Run asked; a well-formed
path outside this Run's own `{spec_folder}`/`{initiative_folder}` is `Forbidden`; a path
inside it that names nothing is `NotFound` — the same three-way split `Workspace` itself
draws between a malformed path and one that is merely absent (`domain/ports/workspace.py`'s
own docstring).

**The one path this endpoint resolves a glob for.** The spec-checkpoint body asks for
`{spec_folder}/stories/{id}-*.md` — the brief's own words — because the screen does not
know the planned file's slug. Resolved here rather than on the wire, the same reasoning
`agent_answer.archive_with_answer` already applies to the identical glob: zero matches is
`NotFound`, more than one is not `misconfigured` (this is a read, not a routing decision) —
the newest is shown, `Workspace.mtime`'s own purpose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Forbidden, Invalid, NotFound
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.workspace import Workspace, WorkspaceError

INVALID_PATH = "path escapes the workspace: {path}"
OUTSIDE_SPEC_FOLDER = "path outside the run's spec folder: {path}"
NO_SUCH_FILE = "no file at {path}"

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
class RunFilesPorts:
    runs: RunRepository
    #: A `Workspace` factory, rooted per Run (`FsWorkspace` itself, the class — the same
    #: "port is the class" shape `StepPorts.workspace` already uses) — this use case cannot
    #: build one until it has read the Run's own `worktree_path`.
    workspace: Callable[[str | None], Workspace]


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


def _escapes(path: str) -> bool:
    pure = PurePosixPath(path)
    return pure.is_absolute() or ".." in pure.parts


def _within_spec_folder(path: str, run: Run) -> bool:
    folder = str(run.inputs.get("spec_folder") or run.inputs.get("initiative_folder") or "")
    return bool(folder) and (path == folder or path.startswith(f"{folder}/"))


def _read(workspace: Workspace, path: str) -> RunFile | None:
    resolved = _resolve(workspace, path)
    if resolved is None:
        return None
    content = workspace.read(resolved)
    if content is None:
        return None
    return RunFile(
        path=resolved, content=content, size=len(content), mtime=workspace.mtime(resolved)
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
