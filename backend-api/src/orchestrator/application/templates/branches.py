"""Fresh branch names: no Run ever works on a branch name another Run has used.

A Template names the branch it wants — `chore/bmad-init`, or whatever `epics.yaml` wrote —
and that name is a *declaration*, not the name that gets created. The planner appends the
first free ordinal to it (`chore/bmad-init-1`, then `-2`, …) and every `git.*` row of the
frame carries that name instead. Three things follow from doing it here rather than in the
YAML or in the executor:

**A second Run cannot land on the first Run's branch.** That is the whole point: a branch
that is still open on the origin — a pull request nobody merged, a Run that was cancelled
after it pushed — used to be checked out again, and the second Run's push was rejected
against work nobody had looked at. A name that is free on the origin cannot be rejected for
being someone else's.

**The suffix is an ordinal, not a clock.** `plan_run` is pure (AD-7): two calls with the
same tree, the same inputs and the same scripted `Git` return equal `Plan`s, and a timestamp
would make the plan an Operator previewed a different plan from the one they started. The
ordinal is read off the remote through `PlanReader`, which is a read the planner is already
allowed to make and already memoises.

**A fresh branch starts where the plan was read.** `plan_ref` is the declared branch's head
when the remote holds it and the base branch otherwise (`plan.py::plan_ref`), so the
`git.worktree` row's `base` is rewritten to match: a Run that planned from
`origin/chore/bmad-init` creates `chore/bmad-init-2` *from that commit*, not from `main`.
Leaving `base` alone would plan against one tree and check out another — the list files the
plan read would not be in the worktree the agent works in.

The declared name keeps every other job it had. `Frame.branch` is still what `read_list`
falls back to for a list file the base does not hold, and still what `plan_ref` asks the
remote about; only the rows that create, push and link a branch see the fresh name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orchestrator.application.steps import WORKTREE_KIND
from orchestrator.application.templates.model import Step
from orchestrator.application.templates.plan_model import (
    BRANCH_KEY,
    NO_FREE_BRANCH,
    PlanError,
)
from orchestrator.application.templates.reader import PlanReader

if TYPE_CHECKING:  # a frame is the walker's; naming it here would be a second one
    from orchestrator.application.templates.rows import Frame

#: What joins a declared branch name to its ordinal. A branch name may hold one already —
#: `feat/epic-1` — which is why the ordinal is only ever read back off the remote and never
#: parsed out of a name the Operator wrote.
SUFFIX_SEPARATOR = "-"

#: The first ordinal tried, and the last. Every Run gets one — there is no bare-name case,
#: so `chore/bmad-init` itself is never created and a Repository initialised twice reads
#: `-1` then `-2` rather than `-1` then a collision. The ceiling is a refusal rather than an
#: unbounded walk of the remote: a hundred open branches of one name is a repository nobody
#: is tidying, and one more Run is not the fix.
FIRST_SUFFIX = 1
MAX_SUFFIX = 99

#: The `with` key `git.worktree` names its start point in.
BASE_KEY = "base"


class BranchAllocator:
    """One fresh name per declared branch, for the whole plan.

    Memoised by the declared name, because `git.worktree`, `git.push` and `pr.link` all
    name the same branch and three independent allocations would be three branches. The
    names handed out are remembered too: a plan whose Templates declare both `feat/x` and
    `feat/x-1` must not answer `feat/x-1` twice.
    """

    def __init__(self, reader: PlanReader) -> None:
        self._reader = reader
        self._fresh: dict[str, str] = {}
        self._handed_out: set[str] = set()

    @property
    def allocated(self) -> dict[str, str]:
        """`{declared: created}` — what `Plan.branches` carries, for pre-flight (AD-14)."""
        return dict(self._fresh)

    def fresh(self, declared: str | None) -> str | None:
        """The name this Run creates for a declared branch; `None` for a Template with none.

        `initiative@1` checks nothing out itself — its worktree is inside the epic frame —
        so it declares no branch and gets no name, exactly as `working_branch` reports it.
        """
        if declared is None:
            return None
        if declared in self._fresh:
            return self._fresh[declared]
        for ordinal in range(FIRST_SUFFIX, MAX_SUFFIX + 1):
            candidate = f"{declared}{SUFFIX_SEPARATOR}{ordinal}"
            if candidate in self._handed_out or self._reader.sha(candidate) is not None:
                continue
            self._fresh[declared] = candidate
            self._handed_out.add(candidate)
            return candidate
        raise PlanError(reason=NO_FREE_BRANCH, item=declared)

    def start_point(self, declared: str | None, base: str) -> str:
        """Where the fresh branch begins: the declared branch, or the Template's own base.

        The same rule `plan_ref` follows, and for the same reason — see the module
        docstring. `base` is whatever the row resolved, so a Template that named something
        other than `{{base_branch}}` keeps what it named.
        """
        if declared is not None and self._reader.sha(declared) is not None:
            return declared
        return base


def fresh_params(step: Step, frame: Frame, resolved: dict[str, Any]) -> dict[str, Any]:
    """One row's `with_resolved`, with the declared branch replaced by this Run's own.

    Only a row that names *this frame's* branch is rewritten. A Template that pushed some
    other branch would be naming a branch this Run neither created nor planned from, and
    inventing a fresh name for it would push work somewhere nobody asked for.
    """
    if frame.branch is None or frame.fresh_branch is None:
        return resolved
    if resolved.get(BRANCH_KEY) != frame.branch:
        return resolved
    rewritten = {**resolved, BRANCH_KEY: frame.fresh_branch}
    if step.uses == WORKTREE_KIND and BASE_KEY in rewritten:
        rewritten[BASE_KEY] = frame.fresh_from or str(resolved[BASE_KEY])
    return rewritten
