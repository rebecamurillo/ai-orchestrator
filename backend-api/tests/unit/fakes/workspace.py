"""In-memory `Workspace` — the one fake for that port (AD-18). Reuse it; do not write
another.

A dict of `path -> text` stands in for the worktree, so a test builds one pre-populated
rather than writing real files to assert a read. The same path rules `FsWorkspace` enforces
apply here too — `..`, an absolute path, or a Workspace built with no root all raise
`WorkspaceError` — because a use case tested against a weaker double would pass here and
fail against the real filesystem.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

from orchestrator.domain.ports.workspace import TreeEntry, WorkspaceError

NO_ROOT = "workspace unavailable: no worktree yet"
OUTSIDE_ROOT = "path outside the workspace: {path}"
#: What `write` refuses with when `path` is already a directory in this fake's own model —
#: the prefix of some other stored file — mirroring `FsWorkspace.write`'s own
#: `IsADirectoryError` guard (story 6-3).
IS_A_DIRECTORY = "path names a directory: {path}"


class FakeWorkspace:
    """An in-memory tree: `path -> text`, rooted and traversal-checked like the real one."""

    def __init__(
        self,
        root: str | None = "/work/wt/fake",
        files: dict[str, str] | None = None,
        mtimes: dict[str, float] | None = None,
    ) -> None:
        self._rooted = root is not None
        self._files: dict[str, str] = dict(files or {})
        #: Public, so a test can populate it on a workspace someone else built; a file the
        #: mapping does not name is `0.0`, which is what the real adapter answers for one
        #: that is not there.
        self.mtimes: dict[str, float] = dict(mtimes or {})
        #: Every pattern `glob` was asked, in order — "the row's own glob was the one
        #: asked" is an assertion about the call, not about what came back.
        self.globbed: list[str] = []

    def read(self, path: str) -> str | None:
        self._checked(path)
        return self._files.get(path)

    def write(self, path: str, text: str) -> None:
        self._checked(path)
        if any(stored.startswith(f"{path}/") for stored in self._files):
            raise WorkspaceError(IS_A_DIRECTORY.format(path=path))
        self._files[path] = text

    def exists(self, path: str) -> bool:
        self._checked(path)
        return path in self._files or any(p.startswith(f"{path}/") for p in self._files)

    def glob(self, pattern: str) -> tuple[str, ...]:
        self._checked(pattern)
        self.globbed.append(pattern)
        return tuple(sorted(path for path in self._files if fnmatch(path, pattern)))

    def mtime(self, path: str) -> float:
        self._checked(path)
        return self.mtimes.get(path, 0.0)

    def move(self, src: str, dst: str) -> None:
        self._checked(src)
        self._checked(dst)
        if src in self._files:
            self._files[dst] = self._files.pop(src)
            self.mtimes[dst] = self.mtimes.pop(src, 0.0)

    def tree(self, prefix: str = "") -> tuple[TreeEntry, ...]:
        """`size`/`mtime` for every file the way `mtime()` already answers them (story 6-3),
        plus a synthesised `is_dir=True` row for every ancestor directory under `prefix` —
        there is no real filesystem here to `rglob`, so a test that wants to assert `kind:
        "dir"` rows needs this fake to invent them from the paths it already holds."""
        self._checked(prefix or ".")
        under = [
            path
            for path in self._files
            if not prefix or path == prefix or path.startswith(f"{prefix}/")
        ]
        dirs: set[str] = set()
        for path in under:
            relative = path[len(prefix) + 1 :] if prefix and path != prefix else path
            parts = relative.split("/")[:-1]
            built = prefix
            for part in parts:
                built = f"{built}/{part}" if built else part
                dirs.add(built)
        entries = [
            TreeEntry(
                path=path,
                is_dir=False,
                size=len(self._files[path].encode("utf-8")),
                mtime=self.mtimes.get(path, 0.0),
            )
            for path in under
        ]
        entries.extend(TreeEntry(path=directory, is_dir=True) for directory in dirs)
        return tuple(sorted(entries, key=lambda entry: entry.path))

    def remove(self, path: str) -> None:
        self._checked(path)
        for stored in [p for p in self._files if p == path or p.startswith(f"{path}/")]:
            del self._files[stored]

    def _checked(self, path: str) -> None:
        if not self._rooted:
            raise WorkspaceError(NO_ROOT)
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts:
            raise WorkspaceError(OUTSIDE_ROOT.format(path=path))
