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
when the remote holds it, and of the base branch otherwise. `repo-init@1` names
`chore/bmad-init`, which does not exist yet, so it plans from the base; `epic@1` names
`{{branch}}`, which does; `initiative@1` names no branch at all — its worktree is inside
the epic frame — so it plans from the base too.

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
from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan_model import (
    BASE_BRANCH_NOT_FOUND,
    DUPLICATE_ROW_PATH,
    INSERTED_GATE,
    PLAN_PATH,
    Plan,
    PlanError,
    ResolvedTree,
)
from orchestrator.application.templates.reader import PlanReader
from orchestrator.application.templates.rows import (
    PLANNED,
    TIMEOUT_KEY,
    Context,
    Frame,
    expand,
    working_branch,
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
    scope = root_scope(inputs)
    branch = working_branch(tree.root, scope)
    ref = plan_ref(reader, branch, inputs.base_branch)
    frame = Frame(prefix="", labels=(), ref=ref, scope=scope, template=tree.root, branch=branch)
    context = Context(tree=tree, inputs=inputs, reader=reader, bmad_version=bmad_version)
    rows = [plan_check_row(), *expand(tree.root.steps, frame, context)]
    _each_row_named_once(rows, tree.root)
    return Plan(
        plan_ref=ref,
        plan_refs=dict(reader.plan_refs),
        rows=tuple(
            row.model_copy(update={"seq": seq}) for seq, row in enumerate(rows, start=FIRST_SEQ)
        ),
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


def _each_row_named_once(rows: list[PlannedRow], root: ParsedTemplate) -> None:
    """Refuse a plan two of whose rows would answer to one path.

    `step_run` is stored with a unique `(run_id, path)` (4.1), so a collision that reached
    persistence would be a 500 on a Run the Operator could have been told about here. The
    validator already reserves `before` and `after` inside a paused loop; it cannot reserve
    `plan`, because the plan check is a row no Template can see, so a top-level step called
    `plan` is the way a valid file still reaches this.
    """
    seen: set[str] = set()
    for row in rows:
        if row.path in seen:
            raise PlanError(
                reason=DUPLICATE_ROW_PATH,
                template=root.name,
                version=root.version,
                line=root.line,
                item=row.path,
            )
        seen.add(row.path)


def plan_check_row() -> PlannedRow:
    """Row 1 of every plan: the check that the branch still is what was planned (AD-7)."""
    timeout = KIND_META[PLAN_KIND].timeout_default_min
    return PlannedRow(
        seq=FIRST_SEQ,
        path=PLAN_PATH,
        label=PLAN_PATH,
        kind=PLAN_KIND,
        gate=INSERTED_GATE[PLAN_KIND],
        status=PLANNED,
        reason=None,
        with_resolved={TIMEOUT_KEY: timeout},
        frame=None,
        story_id=None,
    )
