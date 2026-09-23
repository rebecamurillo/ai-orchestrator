"""Initiative dispatch (AD-12, ratified 2026-09-23): one `epics.yaml` becomes many Runs.

`preflight_initiative` is pure and `dispatch_initiative` writes; both run the one read pass
`initiatives/validate.py` holds, so a dispatch cannot succeed on a graph the pre-flight would
have refused.

**What is created, per AD-12's own sentence.** "One use case creates every member Run of an
initiative **saved**, in topological order of `epics.yaml`'s `depends_on` (AD-7) — one Run
per epic on the epic's `repo`, one merge Run per epic on that repository's integration
branch, and at most one go-live checkpoint Run — wiring `after_run_ids` as it goes: a merge
Run after its epic Run, an epic Run after the merge Runs of its `depends_on`, the go-live
Run after the merge Runs of every `go_live` epic. Only the Runs with no dependencies are
enqueued, and only once every row exists."

**The crash posture, stated because it is a choice and not an accident.** Every refusal is
computed before the first write: the file is parsed, the graph is checked, every repository
is resolved, every integration branch is proved pushable, every spec folder is proved
present, and every would-be epic Run is pre-flighted — any `fail` line among them refuses the
whole dispatch (409). Only then does anything happen, in three phases: the integration
branches are pushed (adopt-or-create, AD-14 — a no-op for a branch the origin already holds,
so the phase is idempotent), every Run is created in topological order, and **nothing** is
enqueued until every row exists. A crash between two `create_run` calls therefore leaves
inert saved Runs — `engine_ref` null, which AD-12 says holds neither a queue slot nor a
branch — and never a half-started initiative. Re-dispatching after such a crash creates a
second set of Runs; cancelling the inert ones is the Operator's, and the initiative `cancel`
signal is the endpoint for it.

**Roles are stored, never derived.** The three Template names are request inputs with
defaults, resolved to their *latest* stored version at dispatch time (AD-7, AD-15), so
nothing downstream may read a member Run's part from its `template_name`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.initiatives.model import (
    ROLE_EPIC,
    ROLE_GOLIVE,
    ROLE_MERGE,
    DispatchResult,
    InitiativePreflight,
    InitiativeRequest,
    MemberRun,
)
from orchestrator.application.initiatives.plan import (
    DEVELOP_BRANCH_INPUT,
    FROM_BRANCH_INPUT,
    HOLDS_INPUT,
    Member,
    epic_inputs,
)
from orchestrator.application.initiatives.validate import Validated, validate_initiative
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.writers import WriterPorts, enqueue_saved_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.engine import WorkflowEngine


@dataclass(frozen=True)
class DispatchPorts:
    """Everything `dispatch_initiative` reaches the outside world through.

    `create` carries pre-flight's own ports (git, templates, repositories, projects, runs)
    plus the engine and the step writer, so nothing here is a second copy of a port the
    creation path already holds. `writers` exists for one call — the wave-0 enqueue, which
    reuses `use_cases/writers.py::enqueue_saved_run`, the same two-phase commit dependency
    resolution and the `start` Signal already go through (AD-8, AD-12).
    """

    create: CreateRunPorts
    writers: WriterPorts

    @property
    def preflight(self) -> PreflightPorts:
        """The read ports the validation pass runs on — `create`'s own, not a second set."""
        return self.create.preflight

    @property
    def engine(self) -> WorkflowEngine:
        """The durable engine the wave-0 enqueue goes through (AD-6)."""
        return self.create.engine


def preflight_initiative(ports: PreflightPorts, req: InitiativeRequest) -> InitiativePreflight:
    """Every reason this initiative could not be dispatched, and what it would create."""
    return validate_initiative(ports, req).preflight


def dispatch_initiative(ports: DispatchPorts, req: InitiativeRequest) -> DispatchResult:
    """Validate, push the integration branches, create every Run, enqueue wave 0."""
    validated = validate_initiative(ports.preflight, req)
    failing = validated.preflight.failing
    if failing:
        raise Conflict("; ".join(line.text for line in failing))
    _push_integration_branches(ports, validated.members)
    created, wave = _create_members(ports, req, validated)
    _enqueue_wave_zero(ports, wave)
    return DispatchResult(
        slug=req.slug,
        members=tuple(created.values()),
        started=tuple(epic.id for epic in validated.epics if not epic.depends_on),
    )


def _push_integration_branches(ports: DispatchPorts, members: tuple[Member, ...]) -> None:
    """Adopt-or-create each repository's integration branch, once per repository (AD-14).

    Before any Run exists, so an epic Run planned in the next phase has a base branch the
    origin really holds. It touches no worktree, which is why AD-13's "only worktree writes
    outside an engine step" still stands.
    """
    pushed: set[UUID] = set()
    for member in members:
        if member.repository.id in pushed:
            continue
        pushed.add(member.repository.id)
        ports.preflight.git.push_branch(member.base_dir, member.branch, member.at_ref)


def _create_members(
    ports: DispatchPorts, req: InitiativeRequest, validated: Validated
) -> tuple[dict[UUID, MemberRun], list[Run]]:
    """Every Run of the initiative, saved, in topological order (AD-12).

    The second half of the answer is wave 0 — the epic Runs that waited for nothing — as the
    `Run` entities `create_run` just returned. Carried out rather than looked up again: the
    enqueue phase has to name the Runs it starts, and re-reading them would be a repository
    call whose "not found" case cannot happen and therefore cannot be tested.
    """
    by_id = {member.epic.id: member for member in validated.members}
    merge_runs: dict[str, UUID] = {}
    created: dict[UUID, MemberRun] = {}
    wave: list[Run] = []
    for epic_id in validated.preflight.order:
        member = by_id[epic_id]
        after = tuple(merge_runs[dep] for dep in member.epic.depends_on)
        epic_run, stored = _create_epic_run(ports, req, validated, member, after)
        created[epic_run.run_id] = epic_run
        if not after:
            wave.append(stored)
        merge_run = _create_merge_run(ports, req, validated, member, epic_run)
        created[merge_run.run_id] = merge_run
        merge_runs[epic_id] = merge_run.run_id
    golive = _create_golive_run(ports, req, validated, merge_runs)
    if golive is not None:
        created[golive.run_id] = golive
    return created, wave


def _create_epic_run(
    ports: DispatchPorts,
    req: InitiativeRequest,
    validated: Validated,
    member: Member,
    after: tuple[UUID, ...],
) -> tuple[MemberRun, Run]:
    """One epic Run: the integration branch as its base, its own working branch on top.

    Answers with the stored `Run` beside the reported member, so the wave-0 enqueue can name
    it without a second read.
    """
    result = create_run(
        ports.create,
        CreateRunRequest(
            template_name=req.epic_template,
            template_version=validated.versions[req.epic_template],
            project_id=req.project_id,
            repository_id=member.repository.id,
            base_branch=member.branch,
            budget_usd=req.budget_usd_per_epic,
            inputs=dict(epic_inputs(member)),
            harness=req.harness,
            model=req.model,
            save=True,
            after_run_ids=after,
            initiative=req.slug,
            initiative_role=ROLE_EPIC,
            initiative_epic_id=member.epic.id,
        ),
    )
    return (
        MemberRun(
            run_id=result.run.id,
            epic_id=member.epic.id,
            role=ROLE_EPIC,
            repository_id=member.repository.id,
            after_run_ids=after,
            # the branch AD-7 allocated for this Run — the merge Run's `from_branch`, and
            # the one thing no stored field can answer until the `git.worktree` row has run.
            # The declared name is the fallback for a plan that allocated none, which an
            # epic Template never is: it declares exactly one branch.
            working_branch=result.working_branch or member.working_branch,
        ),
        result.run,
    )


def _create_merge_run(
    ports: DispatchPorts,
    req: InitiativeRequest,
    validated: Validated,
    member: Member,
    epic_run: MemberRun,
) -> MemberRun:
    """One merge Run: the epic's allocated branch, into the repository's integration branch.

    `harness` is `None` on purpose. `merge@1` declares no `agent` row, pre-flight's harness
    line answers `skip` for a plan that has none, and `create_run`'s live probe is skipped
    for a request that names no harness — so a merge Run needs no harness to exist on this
    instance, and giving it one would make a Run that dispatches nothing depend on a CLI.
    """
    after = (epic_run.run_id,)
    result = create_run(
        ports.create,
        CreateRunRequest(
            template_name=req.merge_template,
            template_version=validated.versions[req.merge_template],
            project_id=req.project_id,
            repository_id=member.repository.id,
            base_branch=member.repository.default_branch,
            budget_usd=None,
            inputs={
                DEVELOP_BRANCH_INPUT: member.branch,
                FROM_BRANCH_INPUT: epic_run.working_branch or "",
            },
            save=True,
            after_run_ids=after,
            initiative=req.slug,
            initiative_role=ROLE_MERGE,
            initiative_epic_id=member.epic.id,
        ),
    )
    return MemberRun(
        run_id=result.run.id,
        epic_id=member.epic.id,
        role=ROLE_MERGE,
        repository_id=member.repository.id,
        after_run_ids=after,
    )


def _create_golive_run(
    ports: DispatchPorts,
    req: InitiativeRequest,
    validated: Validated,
    merge_runs: dict[str, UUID],
) -> MemberRun | None:
    """The one go-live checkpoint, when any epic declared `checkpoint: go_live`.

    On the **hub** repository and its base branch: the stop is the initiative's, not any one
    repository's, and `golive@1` checks nothing out — `create_run`'s partition key falls back
    to the Run's base branch for a plan that declares no branch (AD-12, S5).
    """
    holding = [epic.id for epic in validated.epics if epic.goes_live]
    if not holding:
        return None
    assert validated.hub is not None  # `validate_initiative` raises `NotFound` before this
    after = tuple(merge_runs[epic_id] for epic_id in holding)
    result = create_run(
        ports.create,
        CreateRunRequest(
            template_name=req.golive_template,
            template_version=validated.versions[req.golive_template],
            project_id=req.project_id,
            repository_id=validated.hub.id,
            base_branch=req.base_branch,
            budget_usd=None,
            inputs={HOLDS_INPUT: ", ".join(holding)},
            save=True,
            after_run_ids=after,
            initiative=req.slug,
            initiative_role=ROLE_GOLIVE,
        ),
    )
    return MemberRun(
        run_id=result.run.id,
        epic_id=None,
        role=ROLE_GOLIVE,
        repository_id=validated.hub.id,
        after_run_ids=after,
    )


def _enqueue_wave_zero(ports: DispatchPorts, wave: list[Run]) -> None:
    """Enqueue the epic Runs nothing waits for — after every row of the initiative exists.

    `enqueue_saved_run` is `use_cases/writers.py`'s own two-phase commit, the one dependency
    resolution and the `start` Signal already use: enqueue, then write the returned
    `engine_ref` back in its own unit of work. There is no third variant of it.
    """
    for run in wave:
        enqueue_saved_run(ports.writers, ports.engine, run)
