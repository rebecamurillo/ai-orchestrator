"""`RunFileOut`/`RunFileEntryOut`/`RunFilesTreeOut`/`RunFileIn` (story 6-2 read, story 6-3
tree + write) — the wire projections of `run_files.py`'s own use-case types.

`RunFileEntryChangedOut` and `RunFilesTreeChangedOut` (story 8-3) are subclasses of the
frozen schema types: `RunFileEntryOut` is not modified (frozen tests assert its exact
`model_dump()` shape); the changed flag lives only on the new subclass."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from orchestrator.application.use_cases.run_files import RunFile, RunFileDiff, RunFilesTree
from orchestrator.domain.ports.workspace import TreeEntry


class RunFileOut(BaseModel):
    """`{path, content, size, mtime}` — the resolved path (a glob is expanded server-side,
    so this is never the pattern the request named), the file's whole text, its byte length
    and its `mtime` (`Workspace.mtime`'s own POSIX timestamp)."""

    path: str
    content: str
    size: int
    mtime: float

    @classmethod
    def of(cls, file: RunFile) -> RunFileOut:
        return cls(path=file.path, content=file.content, size=file.size, mtime=file.mtime)


class RunFileEntryOut(BaseModel):
    """One row of a `RunFilesTreeOut`, or the result of a `PUT` (6-3) — the same shape
    either way: `path`, `kind` (`"file"`/`"dir"`, from `TreeEntry.is_dir`), `size`, `mtime`."""

    path: str
    kind: Literal["file", "dir"]
    size: int
    mtime: float

    @classmethod
    def of(cls, entry: TreeEntry) -> RunFileEntryOut:
        return cls(
            path=entry.path,
            kind="dir" if entry.is_dir else "file",
            size=entry.size,
            mtime=entry.mtime,
        )


class RunFilesTreeOut(BaseModel):
    """`GET /runs/{id}/files` with no `path` (6-3): `{root, entries[]}` over the Run's own
    scope folder."""

    root: str
    entries: list[RunFileEntryOut]

    @classmethod
    def of(cls, tree: RunFilesTree) -> RunFilesTreeOut:
        return cls(root=tree.root, entries=[RunFileEntryOut.of(entry) for entry in tree.entries])


class RunFileDiffOut(BaseModel):
    """`GET /runs/{id}/files?path=&diff=1` (6.6): one protected path's unified diff, and the
    attempt `start_sha` it is measured from. The diff is git's own text, rendered verbatim."""

    path: str
    from_sha: str
    diff: str

    @classmethod
    def of(cls, answer: RunFileDiff) -> RunFileDiffOut:
        return cls(path=answer.path, from_sha=answer.from_sha, diff=answer.diff)


class RunFileEntryChangedOut(RunFileEntryOut):
    """`RunFileEntryOut` plus `changed: bool` for the 8-3 changed-marks feature.

    `RunFileEntryOut` is not modified (frozen tests assert its exact `model_dump()` shape):
    the subclass approach keeps the base class untouched, and only the tree branch and
    `RunFilesTreeChangedOut.of()` use this type.
    """

    changed: bool = False

    @classmethod
    def of_changed(cls, entry: TreeEntry, *, changed: bool) -> RunFileEntryChangedOut:
        return cls(
            path=entry.path,
            kind="dir" if entry.is_dir else "file",
            size=entry.size,
            mtime=entry.mtime,
            changed=changed,
        )


class RunFilesTreeChangedOut(BaseModel):
    """`GET /runs/{id}/files` with no `path` (8-3): `{root, entries[]}` with `changed` marks.

    The tree branch of `GET /runs/{run_id}/files` returns this type instead of
    `RunFilesTreeOut`; all other branches are unchanged.
    """

    root: str
    entries: list[RunFileEntryChangedOut]

    @classmethod
    def of(cls, tree: RunFilesTree) -> RunFilesTreeChangedOut:
        """Build from a `RunFilesTree`, computing `changed` per entry.

        `changed=True` only for files (`entry.is_dir=False`) whose `mtime` is strictly
        greater than `tree.last_opened_before.timestamp()`.  Directories are never marked.
        `changed=False` for every entry when `last_opened_before` is `None` (first visit).
        """
        lb = tree.last_opened_before
        cutoff = lb.timestamp() if lb is not None else None
        entries = []
        for entry in tree.entries:
            if cutoff is not None and not entry.is_dir and entry.mtime > cutoff:
                changed = True
            else:
                changed = False
            entries.append(RunFileEntryChangedOut.of_changed(entry, changed=changed))
        return cls(root=tree.root, entries=entries)


class RunFileIn(BaseModel):
    """`PUT /runs/{id}/files`'s own body (6-3): the path to write, and its whole new text."""

    path: str
    content: str
