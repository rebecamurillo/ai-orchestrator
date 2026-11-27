"""`next_run`: what follows a `done` Run of an initiative (AD-37 "The transitions", "Branches").

Every read (the stored verdict, the build's pre-flight, `ls_remote`, `merge_base`) and every
remote-branch write happens here, before the advance takes the initiative's row lock. A
`Blocked` leaves no branch created: the budget is checked before any git call and
`FEAT_NOT_FROM_MAIN` before any push.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.rules import initiative_transitions as rules
from orchestrator.application.templates.inputs import declared_inputs
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.use_cases.clone_check import BASE_DIRECTORY
from orchestrator.application.use_cases.create_run import CreateRunRequest
from orchestrator.application.use_cases.initiative_advance import (
    AdvancePorts,
    Blocked,
    Decision,
    NextRun,
    gate_verdict_of,
)
from orchestrator.application.use_cases.preflight import run_preflight
from orchestrator.domain.entities.initiative import FrozenWorkflow, Initiative, InitiativeKey
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run

SPEC_PREFIX = "spec"


@dataclass(frozen=True)
class _Ctx:
    """What one decision reads: the ports, the initiative and the done Run it follows."""

    ports: AdvancePorts
    initiative: Initiative
    from_run: Run


def decide(
    ports: AdvancePorts, initiative: Initiative, advance: InitiativeAdvance, from_run: Run
) -> Decision:
    """The decision for the entry the done Run was, read from the frozen sequence alone."""
    entry = initiative.sequence.workflows[advance.position]
    ctx = _Ctx(ports, initiative, from_run)
    if rules.is_spec(entry):
        return _after_spec(ctx, advance)
    if rules.is_merge(entry):
        return _after_merge(ctx, advance)
    if rules.is_build(initiative.sequence, advance.position):
        return None
    return Blocked(rules.NO_TRANSITION.format(workflow=entry.workflow))


def _after_spec(ctx: _Ctx, advance: InitiativeAdvance) -> Decision:
    verdict = gate_verdict_of(ctx.ports, ctx.from_run.id)
    gate = ctx.initiative.sequence.gate
    if verdict is None:
        return Blocked(rules.NO_VERDICT)
    if verdict.word in gate.pass_words:
        return _after_pass(ctx, advance)
    if verdict.word in gate.fail_words:
        owners = verdict.fields.get(gate.owners_key)
        listed = [str(o) for o in owners] if isinstance(owners, list) else []
        return _fail(ctx, advance, listed, verdict.text)
    return Blocked(rules.UNDECLARED_WORD.format(word=verdict.word))


def _fail(ctx: _Ctx, advance: InitiativeAdvance, owners: list[str], first_turn: str) -> Decision:
    initiative = ctx.initiative
    entry = initiative.sequence.workflows[advance.position]
    if not owners:
        return Blocked(rules.NO_OWNER)
    foreign = rules.foreign_owner(owners, entry)
    if foreign is not None:
        return Blocked(rules.FOREIGN_OWNER.format(owner=foreign, template=entry.template))
    round_ = initiative.round + 1
    extra = {
        "round_steps": ",".join(rules.owners_in_order(owners, entry)),
        "first_turn": first_turn,
    }
    request = _request(ctx, advance.position, round_, extra)
    return NextRun(request, new_round=round_)


def _after_pass(ctx: _Ctx, advance: InitiativeAdvance) -> Decision:
    ports, initiative = ctx.ports, ctx.initiative
    sequence = initiative.sequence
    build = rules.first_auto_after(sequence, advance.position)
    if build is not None:
        project, hub = _project_and_hub(ports, initiative)
        result = run_preflight(
            ports.create_run.preflight,
            _build_preflight(ports, initiative, sequence.workflows[build], project, hub),
        )
        defects, other = rules.preflight_failure(result)
        if defects:
            assert ports.steps is not None  # a verdict was read, so the rows were
            owner = rules.tech_step(ports.steps.list_for_run(ctx.from_run.id))
            owners = [] if owner is None else [owner]
            return _fail(ctx, advance, owners, "\n".join(defects))
        if other is not None:
            return Blocked(other)
    return NextRun(_request(ctx, advance.position + 1, initiative.round))


def _after_merge(ctx: _Ctx, advance: InitiativeAdvance) -> Decision:
    ports, initiative = ctx.ports, ctx.initiative
    project, hub = _project_and_hub(ports, initiative)
    if project.default_budget_usd is None:
        return Blocked(rules.NO_PROJECT_BUDGET)
    blocked = _feat_branch(ports, project, hub, initiative.slug)
    if blocked is not None:
        return blocked
    build = rules.first_auto_after(
        initiative.sequence, rules.spec_index(initiative.sequence, advance.position)
    )
    if build is None:
        return Blocked(
            rules.NO_TRANSITION.format(
                workflow=initiative.sequence.workflows[advance.position].workflow
            )
        )
    return NextRun(_request(ctx, build, initiative.round))


def _feat_branch(
    ports: AdvancePorts, project: Project, hub: Repository, slug: str
) -> Blocked | None:
    """Make `feat/{slug}` exist at `main`'s tip: create it, move it forward, or refuse."""
    if ports.branches is None:
        raise RuntimeError("no remote branch port")
    git = ports.create_run.preflight.git
    branch = f"{rules.FEAT_PREFIX}/{slug}"
    main = git.ls_remote(hub.url, hub.default_branch)
    if main is None:
        return Blocked(f"branch {hub.default_branch} is not on the hub's remote")
    base_dir = ports.create_run.preflight.work_dir / project.slug / hub.slug / BASE_DIRECTORY
    if not git.base_exists(base_dir):
        git.clone_base(hub.url, base_dir)
    git.fetch_base(base_dir, hub.default_branch)
    feat = git.ls_remote(hub.url, branch)
    if feat is None:
        ports.branches.create_remote_branch(base_dir, branch, main.sha)
    elif feat.sha == main.sha:
        return None
    elif git.merge_base(base_dir, feat.sha, main.sha) == feat.sha:
        ports.branches.fast_forward_remote_branch(base_dir, branch, main.sha)
    else:
        return Blocked(rules.FEAT_NOT_FROM_MAIN.format(slug=slug))
    return None


def _project_and_hub(ports: AdvancePorts, initiative: Initiative) -> tuple[Project, Repository]:
    preflight = ports.create_run.preflight
    project = preflight.projects.get(initiative.project_id)
    hub = preflight.repositories.get(initiative.repository_id)
    if project is None or hub is None:
        raise LookupError(f"no project or repository of initiative {initiative.id}")
    return project, hub


def _declared(ports: AdvancePorts, entry: FrozenWorkflow) -> set[str]:
    stored = ports.create_run.preflight.templates.get(entry.template, entry.version)
    if stored is None:
        raise LookupError(f"no template {entry.template} version {entry.version}")
    root = load_with_lines(stored.yaml).root
    assert root is not None  # a stored version parsed when it was saved
    return set(declared_inputs(root))


def _auto_offer(project: Project, hub: Repository, slug: str, branch: str) -> Mapping[str, object]:
    return {
        "slug": slug,
        "branch": branch,
        "initiative_folder": f"{hub.initiative_folder}/{slug}",
        "plan_model": project.default_model,
        "review_model": project.default_model,
        "senior_model": project.default_senior_model,
        "autonomy": project.default_autonomy,
    }


def _build_preflight(
    ports: AdvancePorts,
    initiative: Initiative,
    entry: FrozenWorkflow,
    project: Project,
    hub: Repository,
) -> PreflightRequest:
    spec = f"{SPEC_PREFIX}/{initiative.slug}"
    offered = _auto_offer(project, hub, initiative.slug, spec)
    return PreflightRequest(
        template_name=entry.template,
        template_version=entry.version,
        project_id=project.id,
        repository_id=hub.id,
        base_branch=spec,
        inputs=rules.offered_inputs(_declared(ports, entry), offered),
        harness=project.default_harness,
        model=project.default_model,
        budget_usd=project.default_budget_usd,
    )


def _request(
    ctx: _Ctx, index: int, round_: int, extra: Mapping[str, Any] | None = None
) -> CreateRunRequest:
    """One `CreateRunRequest` for the entry at `index`, inputs limited to what it declares."""
    ports, initiative, from_run = ctx.ports, ctx.initiative, ctx.from_run
    entry = initiative.sequence.workflows[index]
    project, hub = _project_and_hub(ports, initiative)
    slug = initiative.slug
    offered: dict[str, object]
    if entry.type == rules.AUTO:
        offered = dict(_auto_offer(project, hub, slug, f"{rules.FEAT_PREFIX}/{slug}"))
        budget, harness, model = (
            project.default_budget_usd,
            project.default_harness,
            project.default_model,
        )
    else:
        branch = hub.default_branch if rules.is_merge(entry) else f"{SPEC_PREFIX}/{slug}"
        offered = {"slug": slug, "branch": branch, **(extra or {})}
        budget = from_run.budget_usd
        harness, model = from_run.inputs.get("harness"), from_run.inputs.get("model")
    return CreateRunRequest(
        template_name=entry.template,
        template_version=entry.version,
        project_id=project.id,
        repository_id=hub.id,
        base_branch=hub.default_branch,
        budget_usd=budget,
        harness=harness,
        model=model,
        inputs=rules.offered_inputs(_declared(ports, entry), offered),
        conflict_consent=True,
        initiative=InitiativeKey(initiative_id=initiative.id, round=round_, position=index),
    )
