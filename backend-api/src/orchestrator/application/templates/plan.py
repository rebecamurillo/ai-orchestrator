"""`plan_run`: the whole Run planned from one commit, before any of it starts (AD-7).

The public function of the planner. Everything it can do is `Git.ls_remote`,
`Git.read_file` and `Git.list_files`, all of them through `PlanReader`: no clock, no
randomness, no filesystem, no YAML file of its own. Two calls with the same tree, the same
inputs and the same scripted `Git` return equal `Plan`s, which is what makes *What will
run* a promise rather than a preview.

**Why `base_dir` is an argument.** `Git.read_file` and `Git.list_files` take the base
clone's path — `{work_dir}/{project.slug}/{repository.slug}/base` (AD-14) — and
`application/` may not read the environment (AD-20), so the path arrives from the caller
like `work_dir` and `bmad_version` do in `use_cases/clone_check.py`.

**`plan_ref` is one rule, not three.** It is the SHA of the branch the Template works on
when the remote holds it, and of the base branch otherwise. An initialisation plan names a
fixed branch, which does not exist the first time, so it plans from the base; a dev-loop plan
names `{{branch}}`, which does; a plan with an epic loop may name no branch at all — its
worktree is
inside the epic frame — so it plans from the base too.

**The branch the Template names is not the branch this Run creates.** `BranchAllocator`
turns each declared name into the first free ordinal of it — `chore/bmad-init-1`, then
`-2` — and every `git.*` row carries that instead, so two Runs of one Template never meet
on one branch (`branches.py`). The declared name is still what `plan_ref` above asks the
remote about, and still where the fresh branch starts from. A checkout declaring
`with {mode: attach}` is the one exemption: it works on the declared branch by its exact
name, which is how a Run joins a repository's shared integration branch (AD-7, AD-14).

**The scope holds no `None`.** A Run that chose no model has no `model` to substitute, so
the name is simply unbound and `{{model}}` resolves to `""` rather than to the four
characters `None`. That is the same rule that turns an unset `quality_gate_command` into a
`skipped` row rather than into a shell command reading `None`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.application.dto import RunInputs
from orchestrator.application.steps import KIND_META, PLAN_KIND
from orchestrator.application.steps.plan_check import (
    BASE_BRANCH_KEY,
    BASE_DIR_KEY,
    LIST_BRANCHES_KEY,
    PLAN_REFS_KEY,
    URL_KEY,
)
from orchestrator.application.templates.branches import BranchAllocator, frame_branch
from orchestrator.application.templates.defaults import with_defaults
from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan_model import (
    BASE_BRANCH_NOT_FOUND,
    DUPLICATE_ROW_PATH,
    INSERTED_GATE,
    ON_FAIL_KEY,
    PLAN_PATH,
    REDISPATCH_MAX,
    REDISPATCH_TARGET_NOT_PLANNED,
    REDISPATCH_TARGET_SEQ,
    Plan,
    PlanError,
    Redispatched,
    ResolvedTree,
    attach_mode,
    working_branch,
)
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.templates.rows import (
    PLANNED,
    TIMEOUT_KEY,
    Context,
    Frame,
    expand,
)
from orchestrator.domain.ports.git import Git
from orchestrator.domain.values import PlannedRow

#: The names every Template can bind, whatever else it declares.
PROJECT_NAME = "project"
REPOSITORY_NAME = "repository"
BASE_BRANCH_NAME = "base_branch"
HARNESS_NAME = "harness"
MODEL_NAME = "model"

#: Where the dense numbering of `seq` starts (AD-7: row 1 is always the plan check).
FIRST_SEQ = 1


def plan_run(
    tree: ResolvedTree,
    inputs: RunInputs,
    *,
    git: Git,
    base_dir: Path,
    bmad_version: str,
) -> Plan:
    """Every row this Run will execute, read from one commit of one branch."""
    reader = PlanReader(git, base=base_dir, url=inputs.repository.url)
    allocator = BranchAllocator(reader)
    # literal defaults only: an expression default is validated, never substituted
    scope = with_defaults(tree.root, root_scope(inputs))
    branch = working_branch(tree.root, scope)
    ref = plan_ref(reader, branch, inputs.base_branch)
    name, start = frame_branch(
        allocator, branch, inputs.base_branch, attach=attach_mode(tree.root, scope)
    )
    frame = Frame(
        prefix="",
        labels=(),
        ref=ref,
        scope=scope,
        template=tree.root,
        branch=branch,
        fresh_branch=name,
        fresh_from=start,
    )
    context = Context(
        tree=tree,
        inputs=inputs,
        reader=reader,
        allocator=allocator,
        bmad_version=bmad_version,
    )
    # `expand` runs first so `reader.plan_refs`/`plan_branches` are populated by the time
    # `plan_check_row` reads them — row 1 carries a copy of what the rest of the walk
    # recorded, because `plan.check` runs before any other row and cannot re-derive it.
    expanded = expand(tree.root.steps, frame, context)
    check = plan_check_row(
        base_dir=base_dir,
        url=inputs.repository.url,
        base_branch=inputs.base_branch,
        plan_refs=dict(reader.plan_refs),
        list_branches=dict(reader.plan_branches),
    )
    rows = [check, *expanded]
    return Plan(
        plan_ref=ref,
        plan_refs=dict(reader.plan_refs),
        rows=numbered(rows, tree.root),
        branches=allocator.allocated,
    )


def root_scope(inputs: RunInputs) -> dict[str, Any]:
    """What a `{{ }}` in the root Template resolves against.

    A name bound to nothing is not bound: see the module docstring on why `None` never
    enters a scope.
    """
    named: dict[str, Any] = {
        **inputs.values,
        # last, so a Template input the Operator happened to call `repository` cannot
        # replace the snapshot the Run was created from
        PROJECT_NAME: inputs.project,
        REPOSITORY_NAME: inputs.repository,
        BASE_BRANCH_NAME: inputs.base_branch,
        HARNESS_NAME: inputs.harness,
        MODEL_NAME: inputs.model,
    }
    return {name: value for name, value in named.items() if value is not None}


def plan_ref(reader: PlanReader, branch: str | None, base_branch: str) -> str:
    """The commit the whole plan is read at, and the one refusal it can end in."""
    if branch is not None:
        working = reader.sha(branch)
        if working is not None:
            return working
    base = reader.sha(base_branch)
    if base is None:
        raise PlanError(reason=BASE_BRANCH_NOT_FOUND, item=base_branch)
    return base


def numbered(rows: list[PlannedRow], root: ParsedTemplate) -> tuple[PlannedRow, ...]:
    """`seq` dense from 1, and every backwards route resolved to the row it goes back to.

    The two happen together because they need the same thing. `seq` is a property of the
    finished list, so a row that redispatches cannot know its target's number while the walk
    is still running — and 4.7's executor may not go looking for it afterwards, since it sees
    one row and never the plan (AD-7). This is the one place both facts exist at once.
    """
    seqs = _each_row_named_once(rows, root)
    return tuple(
        row.model_copy(update={"seq": seq, "with_resolved": _routed(row, seqs)})
        for seq, row in enumerate(rows, start=FIRST_SEQ)
    )


def _each_row_named_once(rows: list[PlannedRow], root: ParsedTemplate) -> dict[str, int]:
    """Every row's `seq` by its path, refusing a plan two of whose rows share one.

    `step_run` is stored with a unique `(run_id, path)` (4.1), so a collision that reached
    persistence would be a 500 on a Run the Operator could have been told about here. The
    validator already reserves `before` and `after` inside a paused loop; it cannot reserve
    `plan`, because the plan check is a row no Template can see, so a top-level step called
    `plan` is the way a valid file still reaches this.
    """
    seqs: dict[str, int] = {}
    for seq, row in enumerate(rows, start=FIRST_SEQ):
        if row.path in seqs:
            raise PlanError(
                reason=DUPLICATE_ROW_PATH,
                template=root.name,
                version=root.version,
                line=root.line,
                item=row.path,
            )
        seqs[row.path] = seq
    return seqs


def _routed(row: PlannedRow, seqs: dict[str, int]) -> dict[str, Any]:
    """One row's `with_resolved`, with a redispatch target turned into that row's `seq`.

    A target the frame does not hold is a refusal rather than a wider search: the validator
    keeps one flat set of earlier `agent` steps for the whole file, so a step inside a loop
    may legally name one outside it — and going back to another frame's row is not a thing
    a Run can do. The refusal is named from the route's own Template, because the frame that
    declared it is gone by the time the plan is numbered.
    """
    route = row.with_resolved.get(ON_FAIL_KEY)
    if not isinstance(route, Redispatched):
        return row.with_resolved
    target = seqs.get(route.target_path)
    if target is None:
        raise PlanError(
            reason=REDISPATCH_TARGET_NOT_PLANNED,
            template=route.template,
            version=route.version,
            line=route.line,
            item=route.target_path,
        )
    return {
        **row.with_resolved,
        ON_FAIL_KEY: {REDISPATCH_TARGET_SEQ: target, REDISPATCH_MAX: route.max},
    }


def plan_check_row(
    *,
    base_dir: Path,
    url: str,
    base_branch: str,
    plan_refs: dict[str, str],
    list_branches: dict[str, str | None],
) -> PlannedRow:
    """Row 1 of every plan: the check that the branch still is what was planned (AD-7).

    Everything `plan.check` needs to ask `Git` again — its own copy, since the row runs
    before any other and cannot read the Run it will become part of.
    """
    timeout = KIND_META[PLAN_KIND].timeout_default_min
    return PlannedRow(
        seq=FIRST_SEQ,
        path=PLAN_PATH,
        label=PLAN_PATH,
        kind=PLAN_KIND,
        gate=INSERTED_GATE[PLAN_KIND],
        status=PLANNED,
        reason=None,
        with_resolved={
            TIMEOUT_KEY: timeout,
            BASE_DIR_KEY: str(base_dir),
            URL_KEY: url,
            BASE_BRANCH_KEY: base_branch,
            PLAN_REFS_KEY: plan_refs,
            LIST_BRANCHES_KEY: list_branches,
        },
        frame=None,
        story_id=None,
    )
