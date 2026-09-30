"""The `plan.check` kind: row 1 of every plan, proving the branch is still what it planned
from (AD-7, FR-8).

**What the planner hands this row is what makes it possible.** `plan.check` runs before
`git.worktree` — there is no worktree yet, and `StepContext.cwd` is `None` — so everything
it needs to ask `Git` again comes from `with_resolved`, filled once by `plan_run`
(`application/templates/plan.py::plan_check_row`) at the same moment it reads the files the
first time: the base clone's path, the repository's URL, the base branch, and — per list
file the plan actually read (`Run.plan_refs`, `{path: sha}`) — the branch each one came
from. A file read directly off the root frame's own ref (no branch fallback needed) records
`None` for its branch, which means exactly the base branch: `plan_ref` itself falls back to
it whenever the Template names none or a declared one is not there yet.

**A `continue` never re-reads.** AD-13 admits `continue` on a `plan_stale` park, and its own
effect is "the recorded plan proceeds" — the Operator looked, decided the drift does not
matter, and this row simply reports what it already reported once: `done`.

**Every file recorded is checked by its content, not its commit.** Two different commits
can hold the same text — a change to an unrelated file, a merge that touched nothing here —
and a plan that called that "stale" would park Runs a mistaken Operator has to re-approve
for no reason. The content at the branch's current head is what decides it.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps.context import StepContext
from orchestrator.application.steps.registry import register
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "plan.check"

#: The `with_resolved` keys `plan_check_row` writes and this executor reads, and nothing
#: else does — they exist only for this row, to answer this row's own question.
BASE_DIR_KEY = "base_dir"
URL_KEY = "url"
BASE_BRANCH_KEY = "base_branch"
#: `{path: sha}` — `Run.plan_refs`, copied in at plan time (`plan_run` prepends this row
#: before `create_run` ever persists the Run, so the row carries its own copy).
PLAN_REFS_KEY = "plan_refs"
#: `{path: branch | None}` — which branch each recorded file came from; `None` means the
#: base branch (see the module docstring).
LIST_BRANCHES_KEY = "list_branches"

#: The signal event that resumes this row without re-reading anything (AD-13).
CONTINUE = "continue"

#: What a drifted list file parks the Run with, naming the file the Operator re-reads.
PLAN_STALE = "plan stale: {path}"


class PlanCheckExecutor:
    """Re-read every list file the plan recorded, at its branch's current head."""

    def execute(self, ctx: StepContext) -> StepResult:
        if ctx.resume_signal is not None and ctx.resume_signal.event == CONTINUE:
            return StepResult(status="done", gate=ctx.row.gate)
        stale = self._first_stale_path(ctx)
        if stale is not None:
            reason = PLAN_STALE.format(path=stale)
            return StepResult(
                status="error",
                gate=ctx.row.gate,
                reason=reason,
                park=Park(kind="plan_stale", reason=reason, path=ctx.row.path),
            )
        return StepResult(status="done", gate=ctx.row.gate)

    def _first_stale_path(self, ctx: StepContext) -> str | None:
        resolved = ctx.with_resolved
        git = ctx.ports.git
        base_dir = Path(resolved[BASE_DIR_KEY])
        url = resolved[URL_KEY]
        base_branch = resolved[BASE_BRANCH_KEY]
        plan_refs: dict[str, str] = resolved.get(PLAN_REFS_KEY, {})
        list_branches: dict[str, str | None] = resolved.get(LIST_BRANCHES_KEY, {})
        for path in sorted(plan_refs):
            branch = list_branches.get(path) or base_branch
            head = git.ls_remote(url, branch)
            current = git.read_file(base_dir, head.sha, path) if head is not None else None
            original = git.read_file(base_dir, plan_refs[path], path)
            if current != original:
                return path
        return None


register(KIND, PlanCheckExecutor())
