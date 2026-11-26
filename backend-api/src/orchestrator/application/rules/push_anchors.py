"""AD-17 at the merge Run's push to the default branch (epic 8 retrospective R1, Operator
ruling 2026-11-26).

Every path a merge Run brings to `main` meets here, whoever wrote it: the `git.merge`
executor's commit, the merge agent's own `git commit`, edits after a `merge --abort`. An
anchor or an existing test file in `origin/{branch}..HEAD` is a hit when HEAD's content is not
the content at the tip of the merge's source branch; the Operator's `continue` naming it lets
it stand through `run.accepted_paths`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from orchestrator.application.rules.protected_paths import DOCUMENTS
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.git import Change

#: The `blocked` park of a push the check cannot read a source for: it fails closed.
NO_MERGE_SOURCE = "no merge source for the anchor check"


def initiative_run(run: Run | None) -> bool:
    """Whether the Run belongs to an initiative, the only Runs epic 8 story 4 changed."""
    return run is not None and run.initiative_id is not None


def checked(changes: Sequence[Change], test_globs: Sequence[str]) -> tuple[Change, ...]:
    """The paths of the range the check reads: every document, and every test file the range
    did not add."""
    return tuple(
        change
        for change in changes
        if PurePosixPath(change.path).name in DOCUMENTS
        or (change.kind != "added" and _is_test(change.path, test_globs))
    )


def hits(
    changes: Sequence[Change],
    head: Mapping[str, str | None],
    source: Mapping[str, str | None],
    accepted: Sequence[str],
) -> tuple[Change, ...]:
    """The checked paths whose HEAD content is not the source's, minus what she accepted."""
    excluded = frozenset(accepted)
    return tuple(
        change
        for change in changes
        if change.path not in excluded and head.get(change.path) != source.get(change.path)
    )


def _is_test(path: str, globs: Sequence[str]) -> bool:
    return any(PurePosixPath(path).full_match(glob) for glob in globs)
