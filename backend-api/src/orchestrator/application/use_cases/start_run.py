"""`start_saved_run` (story 5-3): re-probe pre-flight and start a saved (not-enqueued) Run.

A saved Run has `status="queued"` and `engine_ref={}`. The Operator calls this after the
pre-condition they were waiting for is met (a predecessor Run completed, a branch is merged,
etc.). This function re-probes pre-flight so that a clone check that has since failed, or a
new concurrent Run on the same partition branch, still blocks the start.

**Two-commit pattern** (mirrors `create_run` lines 182-189): the first commit records the
gate event and transitions the status; the second commit writes back `engine_ref` after
`engine.enqueue` succeeds. This ensures the gate record exists even if the engine call fails.

**`start_saved_run` is a read + writer for operator transitions** (story 5-3, AD-8): it is
the only function that transitions `queued → running` from the operator side (all execution
transitions stay in `apply_step_result`). The gate event `"started_by_operator"` records it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.use_cases.preflight import PreflightPorts, preflight_and_plan
from orchestrator.application.use_cases.signal_run import SignalOutcome
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    record,
    require_run,
    set_run,
)
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.statuses import run_transition


@dataclass(frozen=True)
class StartRunPorts:
    """What `start_saved_run` reaches the outside world through."""

    writers: WriterPorts
    engine: WorkflowEngine
    preflight: PreflightPorts


def start_saved_run(ports: StartRunPorts, run_id: UUID) -> SignalOutcome:
    """Re-probe pre-flight and start a saved Run, or refuse with the reason (409).

    Validates that the Run is in saved state (`status="queued"`, `engine_ref={}`), re-runs
    pre-flight against the stored fields, then applies the two-commit start transition.
    """
    writers = ports.writers
    run = require_run(writers, run_id)

    # Validate saved state before touching anything
    if run.status != "queued":
        raise Conflict(f"run {run_id} is not in queued status (status={run.status!r})")
    if run.engine_ref:
        raise Conflict(f"run {run_id} is already enqueued; use a signal to resume it")

    # Re-probe pre-flight — refuses if clone check failed, branch is gone, etc.
    preflight_req = PreflightRequest(
        template_name=run.template_name,
        template_version=run.template_version,
        project_id=run.project_id,
        repository_id=run.repository_id,
        base_branch=run.partition_branch or str(run.inputs.get("base_branch", "")),
        inputs=dict(run.inputs),
        budget_usd=run.budget_usd,
        re_review_done=run.re_review_done,
    )
    preflighted = preflight_and_plan(ports.preflight, preflight_req)
    if preflighted.plan_error is not None or not preflighted.result.start_allowed:
        raise Conflict("pre-flight check did not allow start")

    # First commit: gate record + status transition + clear after_run_id
    record(writers, run, Entry(event="started_by_operator", actor="operator"))
    run = set_run(
        writers,
        run,
        status=run_transition("queued", "start"),
        after_run_id=None,
    )
    writers.uow.commit()

    # Second commit: enqueue in the engine and write back engine_ref
    partition_key = f"{run.repository_id}:{run.partition_branch}"
    engine_ref = ports.engine.enqueue(run.id, partition_key=partition_key)
    run = set_run(writers, run, engine_ref=engine_ref)
    writers.uow.commit()

    return SignalOutcome(run=run, resumed=True)
