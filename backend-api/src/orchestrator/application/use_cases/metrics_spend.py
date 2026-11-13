"""The Metrics section's home: spend this month per project, and a project's Runs to select
from (epic 4 story 1). Reads stored Run totals and fact sets; writes nothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.metrics.subscription import group_subscription, run_subscription
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.run_records import ROOT_PATH
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository
from orchestrator.domain.ports.metric_results import ResultVersionRepository
from orchestrator.domain.ports.repositories import ProjectRepository, RunRepository
from orchestrator.domain.ports.run_records import RunRepositoryRecords
from orchestrator.domain.statuses import TERMINAL_RUN


@dataclass(frozen=True)
class MetricsHomePorts:
    projects: ProjectRepository
    runs: RunRepository
    versions: ResultVersionRepository
    fact_sets: FactSetRepository
    run_records: RunRepositoryRecords
    clock: Clock


@dataclass(frozen=True)
class CancelledSpend:
    gateway: str
    harness: str
    runs: int


@dataclass(frozen=True)
class ProjectSpend:
    project_id: UUID
    project_name: str
    gateway: str
    harness: str
    runs: int
    cancelled: CancelledSpend
    gateway_reported: bool
    harness_reported: bool
    subscription: bool | None


@dataclass(frozen=True)
class MetricsRun:
    id: UUID
    label: str
    label_set_by_operator: bool
    status: str
    template_name: str
    template_version: int
    harness: str | None
    base_branch: str | None
    branch: str | None
    wall_clock_seconds: int | None
    gateway: str
    harness_spend: str
    latest_version: int | None
    subscription: bool | None
    selectable: bool


def _money(value: Decimal) -> str:
    return format(value, "f")


def _month_start(now: datetime) -> datetime:
    utc = now.astimezone(UTC)
    return datetime(utc.year, utc.month, 1, tzinfo=UTC)


def _subscriptions(ports: MetricsHomePorts, runs: list[Run]) -> dict[UUID, bool | None]:
    flags = ports.fact_sets.subscriptions([run.id for run in runs])
    return {run.id: run_subscription(flags.get(run.id, [])) for run in runs}


def spend_this_month(ports: MetricsHomePorts) -> list[ProjectSpend]:
    start = _month_start(ports.clock.now())
    spend: list[ProjectSpend] = []
    for project in ports.projects.list():
        runs = [
            run
            for run in ports.runs.list(project_id=project.id)
            if run.started_at is not None and run.started_at >= start
        ]
        flags = _subscriptions(ports, runs)
        cancelled = [run for run in runs if run.status == "cancelled"]
        spend.append(
            ProjectSpend(
                project_id=project.id,
                project_name=project.name,
                gateway=_money(sum((r.gateway_spend_usd for r in runs), Decimal(0))),
                harness=_money(sum((r.harness_spend_usd for r in runs), Decimal(0))),
                runs=len(runs),
                cancelled=CancelledSpend(
                    gateway=_money(sum((r.gateway_spend_usd for r in cancelled), Decimal(0))),
                    harness=_money(sum((r.harness_spend_usd for r in cancelled), Decimal(0))),
                    runs=len(cancelled),
                ),
                gateway_reported=any(r.gateway_reported for r in runs),
                harness_reported=any(r.harness_reported for r in runs),
                subscription=group_subscription(list(flags.values())),
            )
        )
    return spend


def _wall_clock(run: Run, now: datetime) -> int | None:
    if run.started_at is None:
        return None
    return int(((run.ended_at or now) - run.started_at).total_seconds())


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def project_runs(ports: MetricsHomePorts, project_id: UUID) -> list[MetricsRun]:
    if ports.projects.get(project_id) is None:
        raise NotFound(f"no project {project_id}")
    runs = ports.runs.list(project_id=project_id)
    flags = _subscriptions(ports, runs)
    now = ports.clock.now()
    items: list[MetricsRun] = []
    for run in runs:
        record = ports.run_records.get(run.id, ROOT_PATH)
        latest = ports.versions.latest(run.id)
        items.append(
            MetricsRun(
                id=run.id,
                label=run.label,
                label_set_by_operator=run.label_set_by_operator,
                status=run.status,
                template_name=run.template_name,
                template_version=run.template_version,
                harness=_text(run.inputs.get("harness")),
                base_branch=_text(run.inputs.get("base_branch")),
                branch=None if record is None else record.branch,
                wall_clock_seconds=_wall_clock(run, now),
                gateway=_money(run.gateway_spend_usd),
                harness_spend=_money(run.harness_spend_usd),
                latest_version=None if latest is None else latest.n,
                subscription=flags[run.id],
                selectable=run.status in TERMINAL_RUN,
            )
        )
    return items
