"""Private helpers of `create_run`, in a module of their own to keep that one small."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from orchestrator.application.templates.plan_model import Plan
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import PlannedRow


class _Named(Protocol):
    """The three fields of a `CreateRunRequest` that name a trace."""

    @property
    def template_name(self) -> str: ...

    @property
    def template_version(self) -> int: ...

    @property
    def base_branch(self) -> str: ...


def _trace_name(req: _Named) -> str:
    """`run {template}@{version} {branch}` — AD-11's own identity line for the root
    observation `create_run_trace` opens. The brief's literal port signature
    (`create_run_trace(run_id, project_slug, tags)`) has nowhere to carry this, so it is
    added keyword-only (5.1's own precedent for `env_for`'s `traceparent`/`story_id`): keep
    every brief-named parameter, add the one missing, stated fact rather than inventing an
    unrelated shape."""
    return f"run {req.template_name}@{req.template_version} {req.base_branch}"


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
        role=row.role,
    )
