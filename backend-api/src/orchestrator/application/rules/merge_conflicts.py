"""The unmerged paths a `git.merge` attempt lists when it stops on a conflict. Pure."""

from __future__ import annotations

#: What the listing is put under, so a reader can tell git's own words from the index's.
CONFLICTED_HEADING = "conflicted paths:"


def conflict_files(output: str | None) -> list[str]:
    """The non-empty lines after the last heading, in order; `[]` with no heading."""
    if output is None:
        return []
    lines = output.splitlines()
    starts = [i for i, line in enumerate(lines) if line == CONFLICTED_HEADING]
    if not starts:
        return []
    return [line for line in lines[starts[-1] + 1 :] if line.strip()]
