"""Which paths of a `git status --porcelain` are still unmerged. Pure."""

from __future__ import annotations

#: The two-letter porcelain codes git reports for a path a merge left unresolved.
UNMERGED_CODES: frozenset[str] = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})

#: Where a porcelain line's path starts, after the two codes and the space.
PATH_START = 3


def unmerged_paths(status: str) -> tuple[str, ...]:
    """The paths whose code is unmerged, in order; untracked and staged files are not."""
    return tuple(line[PATH_START:] for line in status.splitlines() if line[:2] in UNMERGED_CODES)
