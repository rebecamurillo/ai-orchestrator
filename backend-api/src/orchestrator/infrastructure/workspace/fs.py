"""`FsWorkspace`: the `Workspace` port over the real filesystem, rooted at one worktree.

Every public method starts with `_resolve`, which is the whole safety property of this
class in one place: a `root` that is `None` — a Run whose `git.worktree` row has not run
yet — refuses every call, and a `path` that is absolute or carries a `..` segment refuses
too, before anything here touches a file. There is no second check anywhere below it, which
is what makes the property true of the class rather than of however many of its methods
happened to remember to ask.
"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from orchestrator.domain.ports.workspace import TreeEntry, WorkspaceError

#: What a Workspace with no root yet says when asked to do anything at all.
NO_ROOT = "workspace unavailable: no worktree yet"
#: What an absolute path or a `..` segment is refused with, naming the path asked for.
OUTSIDE_ROOT = "path outside the workspace: {path}"
#: What `write` refuses with when `path` already names a directory — `write_text` raises a
#: plain `IsADirectoryError` (an `OSError`, not this port's `WorkspaceError`), which would
#: otherwise leak past every caller's `except WorkspaceError`.
IS_A_DIRECTORY = "path names a directory: {path}"


class FsWorkspace:
    """Reads and writes rooted at `root`, or refuses every call when `root` is `None`."""

    def __init__(self, root: str | None) -> None:
        self._root = Path(root) if root is not None else None

    def read(self, path: str) -> str | None:
        target = self._resolve(path)
        if not target.is_file():
            return None
        return target.read_text()

    def write(self, path: str, text: str) -> None:
        target = self._resolve(path)
        if target.is_dir():
            raise WorkspaceError(IS_A_DIRECTORY.format(path=path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def glob(self, pattern: str) -> tuple[str, ...]:
        self._require_root()
        _reject_escape(pattern)
        root = self._root
        assert root is not None  # `_require_root` above already refused `None`
        return tuple(sorted(_posix(entry.relative_to(root)) for entry in root.glob(pattern)))

    def move(self, src: str, dst: str) -> None:
        source, destination = self._resolve(src), self._resolve(dst)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)

    def mtime(self, path: str) -> float:
        # `stat` after `_resolve`, and `0.0` for anything that is not there: the caller is
        # ordering files it globbed a moment ago, and a sweep between the two calls must
        # not turn a prepare phase into a traceback.
        target = self._resolve(path)
        try:
            return target.stat().st_mtime
        except OSError:
            return 0.0

    def tree(self, prefix: str = "") -> tuple[TreeEntry, ...]:
        base = self._resolve(prefix) if prefix else self._resolve(".")
        root = self._root
        assert root is not None  # `_resolve` above already refused `None`
        if not base.exists():
            return ()
        entries: list[TreeEntry] = []
        for candidate in sorted(base.rglob("*")):
            try:
                entries.append(_entry(candidate, root))
            except OSError:
                # Gone between the `rglob` listing and this stat/is_dir — a concurrent
                # sweep or commit is not this read's failure (AD-14's "already gone is not
                # a failure", the same discipline `remove`/`mtime` already keep on this
                # port) — the entry is simply not reported rather than crashing the walk.
                continue
        return tuple(entries)

    def remove(self, path: str) -> None:
        target = self._resolve(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    def _resolve(self, path: str) -> Path:
        self._require_root()
        _reject_escape(path)
        root = self._root
        assert root is not None  # `_require_root` above already refused `None`
        return root / path if path not in ("", ".") else root

    def _require_root(self) -> None:
        if self._root is None:
            raise WorkspaceError(NO_ROOT)


def _reject_escape(path: str) -> None:
    """Refuse an absolute path or one carrying a `..` segment, before any file is touched."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise WorkspaceError(OUTSIDE_ROOT.format(path=path))


def _posix(relative: Path) -> str:
    """A relative path in the one separator every caller and every test compares by."""
    return relative.as_posix()


def _entry(entry: Path, root: Path) -> TreeEntry:
    """One `tree()` row: `0`/`0.0` for a directory, `entry.stat()` for a file — the same
    `stat` call `rglob` already needed to sort, read once rather than per field."""
    is_dir = entry.is_dir()
    if is_dir:
        return TreeEntry(path=_posix(entry.relative_to(root)), is_dir=True)
    stat = entry.stat()
    return TreeEntry(
        path=_posix(entry.relative_to(root)), is_dir=False, size=stat.st_size, mtime=stat.st_mtime
    )
