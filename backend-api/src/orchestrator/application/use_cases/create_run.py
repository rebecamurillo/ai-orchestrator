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
from orchestrator.application.use_cases.preflight import PreflightPorts, preflight_and_plan
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.repositories import RunRepository, StepRunRepository
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


@dataclass(frozen=True)
class CreateRunRequest:
    """`POST /runs`'s body: pre-flight's own request, plus what only creation needs."""

    template_name: str
    template_version: int
    project_id: UUID
    repository_id: UUID
    base_branch: str
    budget_usd: Decimal
    inputs: dict[str, Any] | None = None
    harness: str | None = None
    model: str | None = None
    manual_estimate_h: Decimal | None = None
    re_review_done: bool = False

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


def create_run(ports: CreateRunPorts, req: CreateRunRequest) -> CreateRunResult:
    """Re-run pre-flight, refuse what it refuses, then persist and enqueue the plan."""
    preflight_req = req.as_preflight_request()
    preflighted = preflight_and_plan(ports.preflight, preflight_req)
    if preflighted.plan_error is not None:
        raise preflighted.plan_error
    _refuse_failing_lines(preflighted.result.lines, skip_harness_check=ports.skip_harness_check)

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
        created_at=ports.clock.now(),
    )
    step_rows = [_step_run(run_id, row) for row in plan.rows]

    ports.preflight.runs.add(run)
    ports.steps.add_many(step_rows)
    ports.uow.commit()

    engine_ref = ports.engine.enqueue(run.id, partition_key=repository.id)
    run = run.model_copy(update={"engine_ref": engine_ref})
    ports.preflight.runs.update(run)
    ports.uow.commit()

    waiting = preflighted.result.queue_note
    starts_now = waiting == QUEUE_FREE
    return CreateRunResult(run=run, starts_now=starts_now, waiting=waiting)


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
    """What `GET /runs/{id}` reads through — nothing this route writes."""

    runs: RunRepository


def get_run(ports: RunReadPorts, run_id: UUID) -> Run:
    """One stored Run, or `NotFound` (404) — the minimal read model 4.12 replaces."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    return run


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
