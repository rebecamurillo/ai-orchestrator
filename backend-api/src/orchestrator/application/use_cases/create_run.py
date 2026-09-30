"""`create_run` (SPEC CAP-4, FR-6, FR-8): persist a whole plan, then enqueue it (AD-7).

*Start run* re-runs pre-flight rather than trusting whatever the New-workflow screen last
showed — the Operator could have left the tab open while something else changed the
Repository or the Template — so a `fail` line still refuses (409) and an unbuildable plan
still refuses (422), each exactly as `POST /runs/preflight` reports it. What is new here is
what happens once neither refusal applies: the whole plan — the Run row and every
`step_run` row *What will run* named — lands in one unit of work, parent first so the
adapter's own flush-per-insert (4.1) makes the row that carries every foreign key exist
before anything that points to it; only once that has committed does `engine.enqueue`
(AD-6) run, and the `engine_ref` it returns is written back in its own, second commit. A
Run a client never saw the response for is still a real, queued Run — it is simply not yet
told where in the engine it landed.

**Reuse, not a second resolver.** `preflight_and_plan` is `application/use_cases/
preflight.py`'s own one resolution pass, exported for exactly this: the pinned tree and the
plan this module persists are the very objects pre-flight built to answer *What will run*,
not a second computation of them — which is also why `plan`/`resolved.tree` below are
asserted rather than checked: a second, independent pass could in principle disagree with
the first, but one pass cannot disagree with itself.

**`pinned_versions` is the whole call tree** (AD-15): `tree.pinned_versions()` is
root first, then every callee in walk order — the exact list `TemplateVersionRepository.
pinned_by` (4.4) counts against.

**`starts_now` and `waiting` are pre-flight's own `queue_note`**, read *before* this Run is
added: `QUEUE_FREE` means nothing holds the Repository and the instance is under its
concurrency cap (`checks.queue_note`, 4.3); anything else is the sentence the Operator reads
under *Start run* explaining what it queues behind.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.dto import DEFAULT_HARNESS
from orchestrator.application.preflight.model import (
    CHECK_HARNESS,
    QUEUE_FREE,
    Line,
    PreflightRequest,
)
from orchestrator.application.rules.signals import row_at
from orchestrator.application.templates.plan_model import Plan
from orchestrator.application.use_cases.preflight import PreflightPorts, preflight_and_plan
from orchestrator.application.use_cases.queue import REASON_SAVED
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.repositories import (
    GateRecordRepository,
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.values import PlannedRow


@dataclass(frozen=True)
class CreateRunPorts:
    """Everything `create_run` reaches the outside world through.

    `preflight` carries `runs`, `repositories`, `projects` and `templates` — every read this
    use case needs beyond the two it owns (`steps`, `engine`) — so nothing here is a second
    copy of a port pre-flight already holds.
    """

    preflight: PreflightPorts
    engine: WorkflowEngine
    steps: StepRunRepository
    uow: UnitOfWork
    clock: Clock
    #: AD-10: a Run for Project `readiness` skips the harness-enabled fail line. Epic 5
    #: is this flag's caller; nothing in this story sets it to `True`.
    skip_harness_check: bool = False
    #: `None` degrades to "no trace opened, `run.trace_id` stays `None`" (AD-11) — every
    #: frozen `CreateRunPorts(...)` construction predating this story keeps working
    #: unchanged. Production wiring (`api/providers.py::create_run_ports`) always sets one.
    tracer: Tracer | None = None


@dataclass(frozen=True)
class CreateRunRequest:
    """`POST /runs`'s body: pre-flight's own request, plus what only creation needs."""

    template_name: str
    template_version: int
    project_id: UUID
    repository_id: UUID
    base_branch: str
    budget_usd: Decimal | None
    inputs: dict[str, Any] | None = None
    harness: str | None = None
    model: str | None = None
    manual_estimate_h: Decimal | None = None
    re_review_done: bool = False
    conflict_consent: bool = False
    #: When `True`, persist the plan but skip `engine.enqueue` — `engine_ref` stays `{}`,
    #: the saved marker per AD-6. The `start` Signal enqueues it later (story 5-3).
    save: bool = False
    #: The Runs this one waits for, a fan-in list (AD-12, spine amendment 2026-09-23).
    #: A non-empty list requires `save=True`: the Run is stored but not enqueued until
    #: every predecessor is `done` (→ enqueue) or one ends `failed | cancelled` (→ park).
    after_run_ids: tuple[UUID, ...] = ()

    def as_preflight_request(self) -> PreflightRequest:
        return PreflightRequest(
            template_name=self.template_name,
            template_version=self.template_version,
            project_id=self.project_id,
            repository_id=self.repository_id,
            base_branch=self.base_branch,
            inputs=dict(self.inputs or {}),
            harness=self.harness,
            model=self.model,
            budget_usd=self.budget_usd,
            re_review_done=self.re_review_done,
        )


@dataclass(frozen=True)
class CreateRunResult:
    """What `POST /runs` answers with: the created Run, and whether it starts now."""

    run: Run
    starts_now: bool
    waiting: str
    #: The **allocated** name of the branch this Run will work on — `plan.branches`'s value
    #: for the first branch the Template declared, which AD-7's `BranchAllocator` made fresh
    #: (`{declared}-{n}`). `run.partition_branch` is the *declared* name, so it cannot answer
    #: this, and no other stored field does either until the `git.worktree` row has run.
    #: A caller that needs the working branch before the `git.worktree` row has run — for
    #: example, one Run's plan referencing the branch another Run was allocated — reads it
    #: from here. `None` for a plan that declares no branch at all.
    working_branch: str | None = None


def create_run(ports: CreateRunPorts, req: CreateRunRequest) -> CreateRunResult:
    """Re-run pre-flight, refuse what it refuses, then persist and enqueue the plan."""
    # A dependency-waiting Run must be saved: `after_run_ids` is meaningless on a Run that
    # the engine picks up immediately — a predecessor might not even exist yet (story 5-4).
    if req.after_run_ids and not req.save:
        raise Conflict("after_run_ids requires save=True")
    preflight_req = req.as_preflight_request()
    preflighted = preflight_and_plan(ports.preflight, preflight_req)
    if preflighted.plan_error is not None:
        raise preflighted.plan_error
    _refuse_failing_lines(preflighted.result.lines, skip_harness_check=ports.skip_harness_check)
    # consent is not required for save=True: the Probe re-read at `start` Signal time checks
    # fail lines only; the Operator's explicit start action implies intent (story 5-3, AD-13).
    if not req.save and preflighted.result.conflict_consent_required and not req.conflict_consent:
        raise Conflict("this can lead to merge conflicts: conflict consent required")

    # Live probe: validate the model against the harness's actual model list (story 2-2).
    # `harness_registry` is a dict on `PreflightPorts`; reuse it rather than re-running
    # pre-flight a second time.  No probe when harness is absent, adapter not in registry,
    # probe.models is empty (gateway-disabled mode), or model is None.
    if (
        req.harness
        and (_probe_adapter := ports.preflight.harness_registry.get(req.harness)) is not None
    ):
        probe_result = _probe_adapter.probe()
        if not probe_result.ok:
            raise Conflict(probe_result.failing_reason or "probe failed")
        if req.model and probe_result.models and req.model not in probe_result.models:
            raise Invalid(f"model {req.model!r} not in probed list: {list(probe_result.models)}")

    resolved = preflighted.resolved
    if resolved.project is None:
        raise NotFound(f"no project {req.project_id}")
    if resolved.repository is None:
        raise NotFound(f"no repository {req.repository_id}")
    project, repository = resolved.project, resolved.repository

    # `plan_error` is `None` (checked above) and both entities resolved (checked above), so
    # `resolve_tree`/`plan_run` inside this one pass (`preflight_and_plan`) succeeded: see
    # that function's own docstring for why a second, divergent pass is not the concern here.
    plan, tree = preflighted.plan, resolved.tree
    assert plan is not None
    assert tree is not None

    run_id: UUID = new_id()
    trace = (
        ports.tracer.create_run_trace(run_id, project.slug, (), name=_trace_name(req))
        if ports.tracer is not None
        else None
    )
    declared_branch = _partition_branch(plan, req.base_branch)
    run = Run(
        id=run_id,
        project_id=project.id,
        repository_id=repository.id,
        template_name=req.template_name,
        template_version=req.template_version,
        pinned_versions=tree.pinned_versions(),
        inputs=_inputs_dict(req),
        status="queued",
        plan_ref=plan.plan_ref,
        plan_refs=dict(plan.plan_refs),
        budget_usd=req.budget_usd,
        manual_estimate_h=req.manual_estimate_h,
        re_review_done=req.re_review_done,
        trace_id=trace.trace_id if trace is not None else None,
        created_at=ports.clock.now(),
        partition_branch=declared_branch,
        after_run_ids=tuple(req.after_run_ids),
    )
    step_rows = [_step_run(run_id, row) for row in plan.rows]

    ports.preflight.runs.add(run)
    ports.steps.add_many(step_rows)
    ports.uow.commit()
    working = _working_branch(plan)

    # A saved run skips enqueue: `engine_ref` stays `{}` (the AD-6 "not yet enqueued" marker).
    # The `start` Signal will enqueue it later (story 5-3).
    if req.save:
        return CreateRunResult(
            run=run, starts_now=False, waiting=REASON_SAVED, working_branch=working
        )

    engine_ref = ports.engine.enqueue(run.id, partition_key=f"{repository.id}:{declared_branch}")
    run = run.model_copy(update={"engine_ref": engine_ref})
    ports.preflight.runs.update(run)
    ports.uow.commit()

    waiting = preflighted.result.queue_note
    starts_now = waiting == QUEUE_FREE
    return CreateRunResult(run=run, starts_now=starts_now, waiting=waiting, working_branch=working)


def _refuse_failing_lines(lines: tuple[Line, ...], *, skip_harness_check: bool) -> None:
    """409, naming every failing line's own text — unless AD-10 says to look past it."""
    failing = [
        line
        for line in lines
        if line.status == "fail" and not (skip_harness_check and line.check == CHECK_HARNESS)
    ]
    if failing:
        raise Conflict("; ".join(line.text for line in failing))


@dataclass(frozen=True)
class RunReadPorts:
    """What `GET /runs`, `GET /runs/{id}` and `GET /runs?view=board` (4.12) read through —
    nothing any of them writes."""

    runs: RunRepository
    #: `None` for a caller that only ever reads a Run — `test_run_router.py` (4.4)
    #: constructs `RunReadPorts(runs=...)` alone. Set, a reader can also look up the parked
    #: row's own `kind` for `RunSummaryOut.admitted_signals` (4.9), and the Board (4.12)
    #: reads a Run's rows for its progress and current-step label.
    steps: StepRunRepository | None = None
    #: `None` for the same reason `steps` can be: the Board (4.12) names and slugs each
    #: card with these, gracefully blank when unwired, the way `application/use_cases/
    #: project_runs.py::embedded_runs` degrades rather than fails a read `runs`/`steps`
    #: alone can already answer.
    projects: ProjectRepository | None = None
    repositories: RepositoryRepository | None = None
    #: `None` likewise; the Board (4.12) reads this for `needs_you_since` alone.
    gate_records: GateRecordRepository | None = None


def get_run(ports: RunReadPorts, run_id: UUID) -> Run:
    """One stored Run, or `NotFound` (404) — the minimal read model 4.12 replaces."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    return run


def run_rows(ports: RunReadPorts, run: Run) -> list[StepRun]:
    """Every row of this Run, or `[]` when no `StepRunRepository` was wired (4.4's own read
    ports). A single-Run read model wants them for the one question the Run row alone cannot
    answer: whether the whole plan is one epic, which is what admits *Skip epic* at a stop
    with no `epics[n]` frame under it (`rules/frames.py::run_is_one_epic`, Operator decision
    2026-09-30: no template name hardcoded in product code)."""
    return [] if ports.steps is None else list(ports.steps.list_for_run(run.id))


def park_row_in(run: Run, rows: Sequence[StepRun]) -> StepRun | None:
    """The row this Run is parked on, out of rows already read — the pure half of
    `park_row_of`, so a caller that needs both asks the repository once."""
    if run.status != "needs_you":
        return None
    return row_at(rows, run.park_path)


def park_row_of(ports: RunReadPorts, run: Run) -> StepRun | None:
    """The row this Run is parked on, for `RunSummaryOut.of`'s two row arguments (4.9, and
    the `skip_step` offer's own `park_row_status` — Operator, 2026-09-26).

    `None` whenever there is nothing useful to look up: the Run is not `needs_you`, no
    `StepRunRepository` was wired (4.4's own read ports), or — a stored Run should never
    reach this, but a read model does not assert it — the row `park_path` names is gone.
    """
    if ports.steps is None:
        return None
    return park_row_in(run, run_rows(ports, run))


def park_row_kind_of(ports: RunReadPorts, run: Run) -> str | None:
    """The parked row's `kind` alone — `park_row_of`'s answer read for the one field 4.9
    named, kept for the callers that ask only that."""
    row = park_row_of(ports, run)
    return row.kind if row is not None else None


def _trace_name(req: CreateRunRequest) -> str:
    """`run {template}@{version} {branch}` — AD-11's own identity line for the root
    observation `create_run_trace` opens. The brief's literal port signature
    (`create_run_trace(run_id, project_slug, tags)`) has nowhere to carry this, so it is
    added keyword-only (5.1's own precedent for `env_for`'s `traceparent`/`story_id`): keep
    every brief-named parameter, add the one missing, stated fact rather than inventing an
    unrelated shape."""
    return f"run {req.template_name}@{req.template_version} {req.base_branch}"


def _inputs_dict(req: CreateRunRequest) -> dict[str, Any]:
    """`Run.inputs`: the bound `base_branch`, `harness`, `model`, and the Template's own
    declared inputs — never the Project or Repository snapshot, which the Run's own foreign
    keys already name."""
    return {
        "base_branch": req.base_branch,
        "harness": req.harness or DEFAULT_HARNESS,
        "model": req.model,
        **(req.inputs or {}),
    }


def _partition_branch(plan: Plan, base_branch: str) -> str:
    """The declared branch this Run partitions its queue slot by (AD-12).

    `plan.branches` maps each branch a Template declared to the fresh name `plan_run`
    allocated for it (AD-7), and the FIRST declared branch is the partition key — the same
    branch the pre-flight branch-line check reads. A story or epic plan declares one; an
    initiative plan declares one per epic frame, and the first of them is the key, exactly
    as for any other multi-branch Template. `base_branch` is the fallback for the only
    remaining case, a plan that declares no branch at all (no `git.worktree` row).
    """
    return next(iter(plan.branches), base_branch)


def _working_branch(plan: Plan) -> str | None:
    """The allocated name of the first branch the Template declared (AD-7), or `None`.

    `_partition_branch` reads the same mapping's *key*; this reads its *value*. A merge Run's
    `from_branch` is the epic Run's allocated branch and nothing else can supply it before
    the epic's `git.worktree` row has run (AD-12, S6).
    """
    return next(iter(plan.branches.values()), None)


def _step_run(run_id: UUID, row: PlannedRow) -> StepRun:
    """One planned row, as `StepRunRepository.add_many` (4.1) stores it."""
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=row.seq,
        path=row.path,
        label=row.label,
        kind=row.kind,
        gate=row.gate,
        status=row.status,
        reason=row.reason,
        with_resolved=row.with_resolved,
        frame=row.frame,
        story_id=row.story_id,
    )
