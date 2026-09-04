"""The one rule a path pattern must satisfy to be stored as a `test_globs` entry.

Mirrors `api/schemas/projects.py::_repo_relative`: a pattern that could name something
outside the worktree it protects is refused before it is ever compared against a real path.
The rule is pure so a later story's protected-path check (the brief names it explicitly)
can reuse it without importing anything that talks to the outside world.
"""

from __future__ import annotations

from pathlib import PurePosixPath

#: The segment that would walk out of the worktree one hop at a time.
PARENT_SEGMENT = ".."

#: Said back to the Operator when a glob is refused.
GLOB_REASON = "no leading `/`, no `..` segment"


def is_valid_glob(glob: str) -> bool:
    """True when `glob` can only ever match paths inside the worktree it is stored beside."""
    if not glob:
        return False
    pure = PurePosixPath(glob)
    return not pure.is_absolute() and PARENT_SEGMENT not in pure.parts
