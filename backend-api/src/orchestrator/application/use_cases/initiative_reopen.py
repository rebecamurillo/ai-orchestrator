"""Reopen a conversation step of an initiative as a new round (SPEC CAP-2; AD-37).

The refusals and the branch decision come first and write nothing. The lock is released before
any signal: a cancel inserts an advance whose foreign key waits on the initiative's row lock.
The row is locked again to read the round, and the new Run, the round and the consumed advances
are stored in one unit of work.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.rules import initiative_transitions as rules
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.templates.inputs import declared_inputs
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.use_cases.create_run import CreateRunRequest, create_run
from orchestrator.application.use_cases.initiative_facts import conversation_step
from orchestrator.application.use_cases.initiatives import InitiativePorts, _base_dir, _branch
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.domain.entities.initiative import FrozenWorkflow, Initiative, InitiativeKey
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import Signal


def _open(ports: InitiativePorts, initiative_id: UUID) -> Initiative:
    initiative = ports.initiatives.get_for_update(initiative_id)
    if initiative is None:
        raise NotFound(f"no initiative {initiative_id}")
    if initiative.cancelled_at is not None or initiative.pr_merged_at is not None:
        state = "cancelled" if initiative.cancelled_at is not None else "done"
        raise Conflict(rules.REOPEN_CLOSED.format(slug=initiative.slug, state=state))
    return initiative


def _spec_index(initiative: Initiative, step_id: str) -> int:
    for index, entry in enumerate(initiative.sequence.workflows):
        if rules.is_spec(entry) and any(
            s.id == step_id and s.kind == CONVERSATION_KIND for s in entry.steps
        ):
            return index
    raise Invalid(rules.REOPEN_NOT_A_STEP.format(step=step_id))


def _hub_and_project(ports: InitiativePorts, initiative: Initiative) -> tuple[Repository, Project]:
    hub = ports.repositories.get(initiative.repository_id)
    project = ports.projects.get(initiative.project_id)
    if hub is None or project is None:
        raise NotFound(f"no project or repository of initiative {initiative.id}")
    return hub, project


def _cancel_live(ports: InitiativePorts, initiative_id: UUID, signal: Signal) -> None:
    for run in ports.runs.list_for_initiative(initiative_id):
        if run.status in TERMINAL_RUN:
            continue
        try:
            handle_signal(ports.signals, run.id, signal)
        except Conflict:
            continue  # ended by itself meanwhile


def _create_branch(
    ports: InitiativePorts, project: Project, hub: Repository, initiative: Initiative
) -> None:
    tip = ports.git.ls_remote(hub.url, hub.default_branch)
    if tip is None:
        raise Conflict(f"branch {hub.default_branch} is not on the hub's remote")
    base_dir = _base_dir(ports, project, hub)
    if not ports.git.base_exists(base_dir):
        ports.git.clone_base(hub.url, base_dir)
    ports.git.fetch_base(base_dir, hub.default_branch)
    ports.branches.create_remote_branch(base_dir, _branch(initiative.slug), tip.sha)


def _done_steps(ports: InitiativePorts, initiative_id: UUID) -> set[str]:
    steps = ports.signals.signal.writers.steps
    return {
        conversation_step(row)
        for run in ports.runs.list_for_initiative(initiative_id)
        for row in steps.list_for_run(run.id)
        if row.kind == CONVERSATION_KIND and row.status == "done"
    }


def _declared(ports: InitiativePorts, entry: FrozenWorkflow) -> set[str]:
    stored = ports.templates.get(entry.template, entry.version)
    root = None if stored is None else load_with_lines(stored.yaml).root
    return set(declared_inputs(root)) if root is not None else set()


def _request(
    ports: InitiativePorts, initiative: Initiative, index: int, extra: dict[str, object]
) -> CreateRunRequest:
    hub, project = _hub_and_project(ports, initiative)
    entry = initiative.sequence.workflows[index]
    at = [
        r for r in ports.runs.list_for_initiative(initiative.id) if r.initiative_position == index
    ]
    latest: Run | None = max(at, key=lambda r: r.created_at, default=None)
    offered: dict[str, object] = {
        "slug": initiative.slug,
        "branch": _branch(initiative.slug),
        **extra,
    }
    return CreateRunRequest(
        template_name=entry.template,
        template_version=entry.version,
        project_id=project.id,
        repository_id=hub.id,
        base_branch=hub.default_branch,
        budget_usd=project.default_budget_usd if latest is None else latest.budget_usd,
        harness=project.default_harness if latest is None else latest.inputs.get("harness"),
        model=project.default_model if latest is None else latest.inputs.get("model"),
        inputs=rules.offered_inputs(_declared(ports, entry), offered),
        conflict_consent=True,
        initiative=InitiativeKey(
            initiative_id=initiative.id, round=initiative.round + 1, position=index
        ),
    )


def reopen_initiative(
    ports: InitiativePorts, initiative_id: UUID, step_id: str, reason: str
) -> Run:
    """Cancel every live Run, then create the spec Run of the next round for `step_id`."""
    try:
        initiative = _open(ports, initiative_id)
        if not reason.strip():
            raise Invalid(rules.REOPEN_NO_REASON)
        index = _spec_index(initiative, step_id)
        hub, project = _hub_and_project(ports, initiative)
        held = ports.git.ls_remote(hub.url, _branch(initiative.slug)) is not None
    except Exception:
        ports.uow.rollback()
        raise
    branch = rules.BRANCH_ATTACHED if held else rules.BRANCH_CREATED
    ports.uow.commit()

    payload = {"reason": rules.REOPEN_REASON, "step": step_id, "branch": branch}
    _cancel_live(ports, initiative_id, Signal(kind="cancel", payload=payload))
    try:
        if not held:
            _create_branch(ports, project, hub, initiative)
        return _create(ports, initiative_id, step_id, reason, index)
    except Exception:
        ports.uow.rollback()
        raise


def _create(
    ports: InitiativePorts, initiative_id: UUID, step_id: str, reason: str, index: int
) -> Run:
    locked = _open(ports, initiative_id)
    runs = ports.runs.list_for_initiative(initiative_id)
    live = [run for run in runs if run.status not in TERMINAL_RUN]
    if live:
        # A Run started between the cancels and this lock (an advance applied in that window,
        # or a concurrent reopen) would otherwise run beside the new round.
        raise Conflict(f"Run {live[0].id} is still live; reopen again to cancel it")
    entry = locked.sequence.workflows[index]
    round_steps = rules.reopen_round_steps(entry.steps, _done_steps(ports, initiative_id), step_id)
    request = _request(
        ports,
        locked,
        index,
        {"round_steps": ",".join(round_steps), "first_turn": reason},
    )

    def settle() -> None:
        now = ports.clock.now()
        ports.initiatives.update(
            locked.model_copy(update={"round": locked.round + 1, "updated_at": now})
        )
        for advance in ports.advances.list_for_initiative(initiative_id):
            if advance.consumed_at is None:
                ports.advances.update(advance.model_copy(update={"consumed_at": now}))

    return create_run(ports.create_run, request, before_commit=settle).run
