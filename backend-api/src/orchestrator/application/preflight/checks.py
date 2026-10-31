"""The pre-flight line-builders that need no list file: origin, branches, harness, and the
rest of FR-8's single-line checks. List-file-shaped checks (`epics.yaml`, `stories.yaml`,
`SPEC.md`, existing story files) live in `application/preflight/lists.py`, which this
module's `Context` is also built for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from orchestrator.application.preflight.model import (
    CHECK_BASE_BRANCH,
    CHECK_BRANCH,
    CHECK_CHECKPOINTS,
    CHECK_CLONE_CHECK,
    CHECK_EPICS_YAML,
    CHECK_HARNESS,
    CHECK_ORIGIN,
    CHECK_STORIES_YAML,
    CHECK_WHAT_WILL_RUN,
    QUEUE_FREE,
    Line,
    PreflightRequest,
)
from orchestrator.application.steps import AGENT_KIND, CHECKPOINT_KIND, WORKTREE_KIND
from orchestrator.application.templates.lists import EPICS_KIND, list_kind
from orchestrator.application.templates.model import ForEach
from orchestrator.application.templates.plan_model import (
    AFTER_LABEL,
    Plan,
    PlanError,
    ResolvedTree,
)
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.harness import Harness as HarnessAdapter
from orchestrator.domain.ports.harnesses import HarnessRepository
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.skill_catalog import SkillCatalog
from orchestrator.domain.values import PlannedRow

#: What a git command can fail with, same convention as `use_cases/clone_check.py`.
STEP_FAILURES = (GitError, OSError)

#: The reasons a `PlanError` names a list file, wherever the loop that failed declared it.
LIST_FILE_REASONS = frozenset(
    {
        "list file not found",
        "list file is not a list",
        "entry is missing a required field",
        "duplicate entry id",
        "entry ids are not prefix-free",
        "ambiguous story file",
    }
)

#: What a Run this harness/repository check has no readiness run to report says.
NO_READINESS_RUN = "no readiness run"


@dataclass(frozen=True)
class Context:
    """Everything a line-builder needs, bundled so no function threads six arguments."""

    git: Git
    base_dir: Path
    max_active_runs: int
    repository: Repository | None
    runs: RunRepository
    harnesses: HarnessRepository
    req: PreflightRequest
    tree: ResolvedTree | None
    plan: Plan | None
    plan_error: PlanError | None
    #: Live harness adapters keyed by name — used by `harness_probe_line` (story 2-2).
    #: Defaults to empty so every existing `Context(...)` construction keeps compiling.
    harness_registry: dict[str, HarnessAdapter] = field(default_factory=dict)
    #: `None` when no catalog is configured at all, which only a unit test's context is —
    #: `installed_skill_lines` `skip`s that, and `fail`s a catalog it cannot read (hub-Run
    #: operations, skills install fix, 2026-09-24).
    skill_catalog: SkillCatalog | None = None

    @property
    def reads_epics_list(self) -> bool:
        """Whether this plan loops over an epics list — what makes line 4 apply, and what
        puts a list-file `PlanError` on that line rather than on line 5. Read off the
        resolved tree's own `for_each` sources, never off the root Template's name (Operator
        decision 2026-09-30: no template name hardcoded in product code), and off the *tree*
        rather than off `plan.plan_refs` because the case this most has to answer — a list
        file that could not be read — is the case with no plan to ask. Any Template with that
        loop now gets line 4 and the per-epic `SPEC.md` checks, the intended widening.
        """
        if self.tree is None:
            return False
        return any(
            list_kind(loop.source) == EPICS_KIND
            for parsed in (self.tree.root, *self.tree.callees)
            for loop in parsed.steps
            if isinstance(loop, ForEach)
        )


def failure_text(error: Exception) -> str:
    """The sentence a failed line carries — `GitError`'s own words, or the class and message.

    Public because `use_cases/preflight.py::_build_plan` answers the same failures with the
    same sentence: a git command that fails while *planning* says what one that fails on a
    *line* says, rather than inventing a second wording for one event.
    """
    if isinstance(error, GitError):
        return error.output
    return f"{type(error).__name__}: {error}"


def origin_reachable(ctx: Context) -> Line:
    """Line 1: `Git.ls_remote(url)` — the cheapest proof the URL resolves (FR-8)."""
    if ctx.repository is None:
        return Line(CHECK_ORIGIN, "skip", "no repository")
    try:
        ref = ctx.git.ls_remote(ctx.repository.url)
    except STEP_FAILURES as error:
        return Line(
            CHECK_ORIGIN, "fail", failure_text(error), fix="check the URL and the instance token"
        )
    if ref is None:
        return Line(
            CHECK_ORIGIN,
            "fail",
            f"{ctx.repository.url}: the remote answered no refs",
            fix="check the URL and the instance token",
        )
    return Line(CHECK_ORIGIN, "ok", f"reachable, HEAD at {ref.sha}")


def base_branch_line(ctx: Context) -> Line:
    """Line 2: the base branch exists on origin. No fix on failure (the brief states none)."""
    base = ctx.req.base_branch
    if ctx.repository is None or base is None:
        return Line(CHECK_BASE_BRANCH, "skip", "no repository or base_branch")
    try:
        ref = ctx.git.ls_remote(ctx.repository.url, base)
    except STEP_FAILURES as error:
        return Line(CHECK_BASE_BRANCH, "fail", failure_text(error))
    if ref is None:
        return Line(CHECK_BASE_BRANCH, "fail", "branch does not exist on origin")
    return Line(CHECK_BASE_BRANCH, "ok", f"{base} at {ref.sha}")


def plan_branches(plan: Plan | None) -> tuple[str, ...]:
    """Every branch a `git.worktree` row of the plan checks out, in order, deduplicated."""
    seen: list[str] = []
    if plan is None:
        return ()
    for row in plan.rows:
        if row.kind != WORKTREE_KIND:
            continue
        branch = row.with_resolved.get("branch")
        if isinstance(branch, str) and branch and branch not in seen:
            seen.append(branch)
    return tuple(seen)


def branch_lines(ctx: Context) -> list[Line]:
    """Line 3: one per branch the plan checks out, or one `skip` when the plan is unknown."""
    branches = plan_branches(ctx.plan)
    if ctx.plan is None:
        if ctx.plan_error is not None or ctx.repository is None or ctx.req.base_branch is None:
            reason = "no repository or base_branch" if ctx.repository is None else "plan not built"
            return [Line(CHECK_BRANCH, "skip", reason)]
        return []
    return [_branch_line(ctx, ctx.plan, branch) for branch in branches]


def _branch_line(ctx: Context, plan: Plan, branch: str) -> Line:
    """One branch the plan creates: who is holding it, and where it starts from.
    The plan creates a branch nobody has used (`templates/branches.py`), so `held by run`
    is asked of the name the Template *declared* — `Plan.branches` maps the two — and never
    of the fresh one, which by construction no Run can be holding. AD-14's refusal is about
    two Runs working the same branch, and that is still what it reports.
    """
    declared = _declared(plan, branch)
    holder = _holding_run(ctx.runs, ctx.repository, declared, exclude_run_id=ctx.req.exclude_run_id)
    if holder is not None:
        return Line(
            CHECK_BRANCH,
            "fail",
            f"held by run {run_label(holder)}",
            fix="wait for that run or cancel it",
        )
    assert ctx.repository is not None  # a branch line only exists once the plan built
    try:
        starts_at = ctx.git.ls_remote(ctx.repository.url, declared) is not None
    except STEP_FAILURES as error:
        return Line(CHECK_BRANCH, "fail", failure_text(error))
    start = declared if starts_at else ctx.req.base_branch
    return Line(CHECK_BRANCH, "ok", f"{branch} · will create from {start}")


def _declared(plan: Plan, branch: str) -> str:
    """The declared name for `branch` in the plan's allocations, or `branch` itself."""
    return {created: named for named, created in plan.branches.items()}.get(branch, branch)


def _holding_run(
    runs: RunRepository,
    repository: Repository | None,
    branch: str,
    exclude_run_id: UUID | None = None,
) -> Run | None:
    """Non-terminal Run holding `branch` on this Repository (AD-14, story 5-1).

    # Revised: a saved Run holds no branch (multi-repo initiative S2, spine AD-14
    # amendment, 2026-09-23). A Run whose `engine_ref` is empty has entered no engine and
    # materialised nothing; it is never the holder. It can enter the engine only through
    # `start` (which re-runs exactly this check) or dependency resolution, serialized by
    # AD-12's partition.
    """
    if repository is None:
        return None
    for r in runs.list_by_repository_non_terminal(repository.id):
        if r.id != exclude_run_id and r.partition_branch == branch and r.engine_ref:
            return r
    return None


def run_label(run: Run) -> str:
    """`"{template} · {branch}"` — the label pre-flight names a holding Run with."""
    if run.partition_branch is not None:
        branch = run.partition_branch
    elif run.worktrees:
        branch = run.worktrees[0].branch
    else:
        branch = str(run.inputs.get("branch") or run.inputs.get("base_branch") or "")
    return f"{run.template_name} · {branch}"


def queue_note(ctx: Context) -> str:
    """Line-less: what a new Run against this Repository would wait behind, if anything."""
    if ctx.repository is None:
        return QUEUE_FREE
    holders = ctx.runs.list_by_repository_non_terminal(ctx.repository.id)
    if holders:
        return f"queues behind {run_label(holders[0])}"
    active = [
        run for run in (*ctx.runs.list_by_status("running"), *ctx.runs.list_by_status("needs_you"))
    ]
    if len(active) >= ctx.max_active_runs:
        labels = ", ".join(run_label(run) for run in active)
        return f"queues: global concurrency, held by {labels}"
    return QUEUE_FREE


def _has_agent_step(tree: ResolvedTree) -> bool:
    """Whether the resolved tree dispatches a harness anywhere (root or a callee)."""
    for template in (tree.root, *tree.callees):
        for entry in template.steps:
            steps = entry.steps if isinstance(entry, ForEach) else (entry,)
            if any(step.uses == AGENT_KIND for step in steps):
                return True
    return False


def harness_line(ctx: Context) -> Line:
    """Line 8: `skip` when the request named none, the Repository is unresolved (every line
    is `skip` once it is — AC5), or the tree dispatches no harness at all."""
    name = ctx.req.harness
    if name is None:
        return Line(CHECK_HARNESS, "skip", "no harness")
    if ctx.repository is None:
        return Line(CHECK_HARNESS, "skip", "no repository")
    if ctx.tree is None or not _has_agent_step(ctx.tree):
        return Line(CHECK_HARNESS, "skip", "no agent step")
    harness = ctx.harnesses.get(name)
    if harness is None or not harness.enabled:
        failing = _failing_check(harness)
        return Line(
            CHECK_HARNESS, "fail", f"disabled: {failing}", fix="re-run readiness on this screen"
        )
    return Line(CHECK_HARNESS, "ok", "enabled")


def _failing_check(harness: Harness | None) -> str:
    """What a disabled or unknown harness's line names as the reason."""
    if harness is not None and harness.failing_check:
        return harness.failing_check
    return NO_READINESS_RUN


def harness_probe_line(ctx: Context) -> Line:
    """Line 8 (story 2-2): live probe replacing the `enabled`-flag check.

    Same skip guards as `harness_line()` — name None → skip, repository None → skip,
    no agent step → skip — then looks up the adapter in `ctx.harness_registry` and calls
    `probe()`.  Missing from the registry is a hard fail (the harness is not available on
    this instance), not a skip.

    `harness_line()` is left unchanged (its tests are read-only anchors); `_lines()` in
    `preflight.py` is what switches to this function.
    """
    name = ctx.req.harness
    if name is None:
        return Line(CHECK_HARNESS, "skip", "no harness")
    if ctx.repository is None:
        return Line(CHECK_HARNESS, "skip", "no repository")
    if ctx.tree is None or not _has_agent_step(ctx.tree):
        return Line(CHECK_HARNESS, "skip", "no agent step")
    adapter = ctx.harness_registry.get(name)
    if adapter is None:
        return Line(CHECK_HARNESS, "fail", "harness not available")
    result = adapter.probe()
    if not result.ok:
        return Line(CHECK_HARNESS, "fail", result.failing_reason or "probe failed")
    return Line(CHECK_HARNESS, "ok", f"probe ok · {result.version}")


def checkpoints_line(ctx: Context) -> Line:
    """Line 6: every declared pause, or `ok · none declared`."""
    if ctx.plan is None:
        return Line(CHECK_CHECKPOINTS, "skip", "plan not built")
    items = [item for row in ctx.plan.rows for item in _checkpoint_items(row)]
    if not items:
        return Line(CHECK_CHECKPOINTS, "ok", "none declared")
    return Line(CHECK_CHECKPOINTS, "warn", "; ".join(items))


def _checkpoint_items(row: PlannedRow) -> list[str]:
    """The zero or one checkpoint phrases this row contributes to line 6."""
    if row.kind == CHECKPOINT_KIND and row.label.endswith(AFTER_LABEL):
        if row.story_id is not None:
            return [f"story {row.story_id} · done checkpoint"]
        return [row.label]
    if (
        row.kind == AGENT_KIND
        and row.story_id is not None
        and row.with_resolved.get("spec_checkpoint")
    ):
        return [f"story {row.story_id} · spec checkpoint"]
    return []


def clone_check_line(ctx: Context) -> Line:
    """Line 11: the Repository's own last clone check."""
    if ctx.repository is None:
        return Line(CHECK_CLONE_CHECK, "skip", "no repository")
    status = ctx.repository.clone_check.status
    if status == "ok":
        return Line(CHECK_CLONE_CHECK, "ok", "ok")
    if status == "pending":
        return Line(CHECK_CLONE_CHECK, "fail", "pending · save the project")
    return Line(CHECK_CLONE_CHECK, "fail", "failed", fix="re-run the clone check on the project")


def what_will_run_line(ctx: Context) -> Line:
    """Line 12: the rows `plan_run` would persist, or the `plan_error` naming why not."""
    if ctx.plan is not None:
        return Line(CHECK_WHAT_WILL_RUN, "ok", f"{len(ctx.plan.rows)} rows")
    if ctx.plan_error is not None:
        return Line(CHECK_WHAT_WILL_RUN, "fail", str(ctx.plan_error))
    return Line(CHECK_WHAT_WILL_RUN, "skip", "missing required fields")


def list_error_target(ctx: Context) -> str | None:
    """Which list-file check line a `PlanError` about a list file belongs to, if any."""
    if ctx.plan_error is None or ctx.plan_error.reason not in LIST_FILE_REASONS:
        return None
    return CHECK_EPICS_YAML if ctx.reads_epics_list else CHECK_STORIES_YAML
