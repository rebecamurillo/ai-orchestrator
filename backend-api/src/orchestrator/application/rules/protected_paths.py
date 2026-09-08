"""AD-17's frozen anchors, as a rule: what is protected, what changed, and which is a hit.

`domain/ports/protected_paths.py` declared the *seam* in Epic 4 — `git.commit` already
routes a hit to `status: error, park: protected_path` — and said the rule itself belongs
here, because it needs a Story frame's first attempt and its frozen test set to say anything
at all. This is that rule, and it is pure: `build` composes the anchor set out of the folders
a Run names, `uncommitted` reads `git status --porcelain`, and `check` subtracts the
Operator's accepted files and reports what is left.

**Why `AGENTS.md` is not in the set.** AD-17 protects *every* `AGENTS.md`, and "creating one
is a hit" — a path that does not exist yet cannot be enumerated, so the rule asks about the
file's name rather than looking it up. Everything else is a literal path: a Run's spec
folders, its initiative folder's epic list, and the test files the frame froze.

**Why `FrameAnchors` exists.** The two call sites AD-17 names check different ranges on
purpose: the agent tail checks "what this attempt just did", the commit-guard checks
"everything the agent did in this frame, plus whatever is still uncommitted". The tail
computes its own range and calls `check` directly, because it needs each hit's *kind* for
the record. The commit-guard cannot: `git_commit.py` knows only what it staged, and the
`ProtectedPaths` protocol is frozen by an existing test at one path-only method. So the
walker binds the frame's facts — its anchors, its worktree and the ranges its attempts
recorded — into this object, and `git.commit` reaches AD-17's full scope through the call it
already makes, unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from orchestrator.domain.ports.git import Change, ChangeKind, Git

#: The three documents a folder contributes, as AD-17 names them.
SPEC_FILENAME = "SPEC.md"
STORIES_FILENAME = "stories.yaml"
EPICS_FILENAME = "epics.yaml"

#: The constitution, protected wherever it is and whether or not it exists yet.
AGENTS_FILENAME = "AGENTS.md"

#: What `git status --porcelain` separates its status letters from the path with: `XY path`.
STATUS_PREFIX = 3

#: How porcelain writes a rename or a copy — the only two lines that carry *two* paths. The
#: arrow alone is not the discriminator: an ordinary tracked file may hold those four bytes
#: in its name, and splitting on it would invent two paths and drop the real one.
RENAME_ARROW = " -> "
RENAMED = "R"
COPIED = "C"

#: The status letters a code can carry, for the kind each line reports.
UNTRACKED = "??"
ADDED = "A"
DELETED = "D"


def build(
    *,
    spec_folders: Sequence[str],
    initiative_folder: str,
    frozen_test_files: Sequence[str],
) -> frozenset[str]:
    """The literal paths this Run's agents may not touch (AD-17).

    `spec_folders` is plural because `initiative@1` binds one per epic; an empty string is
    the Run that declares none (`repo-init@1`) rather than a folder named `""`. The frozen
    test files arrive already resolved — they are the tree at the frame's first attempt, as
    `Git.list_files` answered it, so nothing here globs a filesystem.
    """
    anchors = {path for path in frozen_test_files if path}
    for folder in spec_folders:
        if folder:
            anchors.add(f"{folder}/{SPEC_FILENAME}")
            anchors.add(f"{folder}/{STORIES_FILENAME}")
    if initiative_folder:
        anchors.add(f"{initiative_folder}/{EPICS_FILENAME}")
    return frozenset(anchors)


def uncommitted(status: str) -> tuple[Change, ...]:
    """What the worktree holds that no commit does, as `git status --porcelain` says it.

    Untracked files included — an anchor an agent wrote and never committed is the same hit
    as one it committed — and a rename split into the two ends AD-17 reads it as.
    """
    changes: list[Change] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        code, path = line[:STATUS_PREFIX].strip(), line[STATUS_PREFIX:].strip()
        if (RENAMED in code or COPIED in code) and RENAME_ARROW in path:
            changes.extend(_two_ends(path))
            continue
        changes.append(Change(path=path, kind=_kind(code)))
    return tuple(changes)


def check(
    changed: Sequence[Change], protected: frozenset[str], accepted: Sequence[str]
) -> tuple[Change, ...]:
    """The protected paths among `changed`, minus the ones the Operator accepted (AD-9).

    One entry per path: the callers union a commit range with the uncommitted tree, so the
    same file can arrive twice, and what the Operator reads is a list of files rather than a
    list of observations. The first mention wins, which is the range's own order.
    """
    excluded = frozenset(accepted)
    hits: dict[str, Change] = {}
    for change in changed:
        if change.path in excluded or change.path in hits:
            continue
        if change.path in protected or PurePosixPath(change.path).name == AGENTS_FILENAME:
            hits[change.path] = change
    return tuple(hits.values())


@dataclass(frozen=True)
class FrameAnchors:
    """One Story frame's anchors and agent ranges, as `StepPorts.protected_paths` (AD-17).

    The `ProtectedPaths` the walker binds per row. `check` keeps the protocol's path-only
    signature — `tests/unit/test_run_environment.py` fixes the member set — and supplies
    what `git_commit.py` cannot know: every `start_sha .. end_sha` an attempt of this frame
    recorded, resolved through the same `Git` port everything else uses.
    """

    git: Git
    #: The worktree the frame's rows run in; the ranges are diffed inside it.
    worktree: Path
    anchors: frozenset[str] = field(default_factory=frozenset)
    #: `(start_sha, end_sha)` per attempt of the frame that recorded both (AD-8's two halves).
    ranges: tuple[tuple[str, str], ...] = ()

    def check(self, *, changed: Sequence[str], accepted: Sequence[str]) -> tuple[str, ...]:
        """AD-17's second call site: the frame's agent ranges, plus what the row staged."""
        agent: list[Change] = []
        for start, end in self.ranges:
            agent.extend(self.git.diff_changes(self.worktree, start, end))
        return tuple(hit.path for hit in check([*agent, *_staged(changed)], self.anchors, accepted))


def _staged(changed: Sequence[str]) -> list[Change]:
    """What the commit-guard staged, as changes. `git_commit.py` strips porcelain's status
    letters and keeps the remainder, so a *rename* of an anchor arrives as the single string
    `old -> new`, which matches no anchor and no basename — and the code that would say
    whether it is one is the part that was stripped. Both readings are therefore offered:
    the string as it came, and the two ends AD-17 reads a rename as. Only a real anchor is a
    hit, so the reading that was wrong costs nothing.

    The kind is `modified` for the string itself: the commit-guard reports paths and not
    kinds, and nothing downstream of it reads one.
    """
    changes: list[Change] = []
    for entry in changed:
        changes.append(Change(path=entry, kind="modified"))
        if RENAME_ARROW in entry:
            changes.extend(_two_ends(entry))
    return changes


def _two_ends(path: str) -> tuple[Change, ...]:
    """One `old -> new` line as the two changes AD-17 reads it as: moving a protected file
    away is losing it, and what arrived under the new name is a new file."""
    old, new = path.split(RENAME_ARROW, 1)
    return (Change(path=old.strip(), kind="deleted"), Change(path=new.strip(), kind="added"))


def _kind(code: str) -> ChangeKind:
    """One porcelain status code as a change kind; anything unlisted is a modification."""
    if code == UNTRACKED or ADDED in code:
        return "added"
    if DELETED in code:
        return "deleted"
    return "modified"
