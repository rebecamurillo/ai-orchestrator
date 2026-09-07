"""Plans, Runs and wired fakes for the three status writers (4.5).

The two plans below are the shipped ones the writers actually have to survive: `epic@1`
over two Stories, and `initiative@1` over two epics of one Story each. Their paths, kinds
and frame shapes are copied from `tests/unit/application/templates/test_plan_shipped.py`,
hyphenated step id included, so a rule that reads a frame is exercised against the same
strings the planner really produces.

`World` is one wired set of the shared fakes (AD-18) plus the stored Run: a test moves the
statuses it cares about, calls a writer, and reads the result back out of the repositories
rather than out of the object it passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import RunStatus, StepStatus
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

#: `epic@1` over two Stories, the second carrying a done checkpoint: `(path, kind)`.
EPIC_PLAN: tuple[tuple[str, str], ...] = (
    ("plan", "plan.check"),
    ("checkout", "git.worktree"),
    ("baseline", "shell"),
    ("stories[0].sync", "git.sync"),
    ("stories[0].build", "agent"),
    ("stories[0].verify", "shell"),
    ("stories[0].commit-guard", "git.commit"),
    ("stories[1].sync", "git.sync"),
    ("stories[1].build", "agent"),
    ("stories[1].verify", "shell"),
    ("stories[1].commit-guard", "git.commit"),
    ("stories[1].after", "checkpoint"),
    ("push", "git.push"),
    ("link", "pr.link"),
)

#: `initiative@1` over two epics of one Story each.
INITIATIVE_PLAN: tuple[tuple[str, str], ...] = (
    ("plan", "plan.check"),
    ("epics[0].checkout", "git.worktree"),
    ("epics[0].baseline", "shell"),
    ("epics[0].stories[0].build", "agent"),
    ("epics[0].stories[0].verify", "shell"),
    ("epics[0].stories[0].commit-guard", "git.commit"),
    ("epics[0].stories[1].build", "agent"),
    ("epics[0].stories[1].verify", "shell"),
    ("epics[0].push", "git.push"),
    ("epics[0].link", "pr.link"),
    ("epics[1].checkout", "git.worktree"),
    ("epics[1].stories[0].build", "agent"),
    ("epics[1].stories[0].verify", "shell"),
    ("epics[1].push", "git.push"),
)

#: The two-row plan the brief's first acceptance criterion names.
PAIR_PLAN: tuple[tuple[str, str], ...] = (("plan", "plan.check"), ("checkout", "git.worktree"))


def story_id_of(path: str) -> str | None:
    """`"1"` for a row of `stories[0]`, `"2"` for `stories[1]`, `None` outside a frame."""
    marker = "stories["
    if marker not in path:
        return None
    index = path[path.rindex(marker) + len(marker) :]
    return str(int(index[: index.index("]")]) + 1)


def frame_of(path: str) -> str | None:
    """The innermost loop prefix the planner writes on the row, as `PlannedRow.frame` is."""
    for marker in ("stories[", "epics["):
        if marker in path:
            cut = path.rindex(marker)
            return path[: path.index("]", cut) + 1]
    return None


def build_rows(
    run_id: UUID,
    plan: tuple[tuple[str, str], ...] = EPIC_PLAN,
    statuses: dict[str, StepStatus] | None = None,
    with_resolved: dict[str, dict[str, Any]] | None = None,
) -> list[StepRun]:
    """One `StepRun` per plan entry, `planned` unless `statuses` says otherwise."""
    given = statuses or {}
    extras = with_resolved or {}
    return [
        StepRun(
            id=new_id(),
            run_id=run_id,
            seq=seq,
            path=path,
            label=path,
            kind=kind,
            gate="deterministic",
            status=given.get(path, "planned"),
            with_resolved=extras.get(path, {}),
            frame=frame_of(path),
            story_id=story_id_of(path),
        )
        for seq, (path, kind) in enumerate(plan, start=1)
    ]


def build_run(status: RunStatus = "queued", **over: Any) -> Run:
    """A stored Run with everything the columns require and nothing a test did not ask for."""
    fields: dict[str, Any] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": status,
        "budget_usd": Decimal("10.00"),
        "created_at": EPOCH,
    }
    fields.update(over)
    return Run(**fields)


@dataclass
class World:
    """One wired set of fakes: the ports the writers take, and what they wrote."""

    run: Run
    ports: WriterPorts
    engine: FakeWorkflowEngine
    clock: FakeClock

    @property
    def signal_ports(self) -> SignalPorts:
        return SignalPorts(writers=self.ports, engine=self.engine)

    def stored_run(self) -> Run:
        stored = self.ports.runs.get(self.run.id)
        assert stored is not None
        return stored

    def row(self, path: str) -> StepRun:
        stored = next(row for row in self.ports.steps.list_for_run(self.run.id) if row.path == path)
        return stored

    def status_of(self, path: str) -> StepStatus:
        return self.row(path).status

    def records(self) -> list[GateRecord]:
        return self.ports.records.list_for_run(self.run.id)

    def events(self) -> list[str]:
        return [record.event for record in self.records()]

    def attempts_of(self, path: str) -> list[Attempt]:
        return self.ports.attempts.list_for_row(self.row(path).id)


def a_world(
    status: RunStatus = "queued",
    plan: tuple[tuple[str, str], ...] = EPIC_PLAN,
    statuses: dict[str, StepStatus] | None = None,
    with_resolved: dict[str, dict[str, Any]] | None = None,
    **over: Any,
) -> World:
    """A stored Run, its rows, and the fakes every writer reaches them through."""
    run = build_run(status, **over)
    rows = build_rows(run.id, plan, statuses, with_resolved)
    clock = FakeClock()
    uow = FakeUnitOfWork()
    ports = WriterPorts(
        runs=FakeRunRepository([run]),
        steps=FakeStepRunRepository(rows),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=uow,
        clock=clock,
    )
    return World(
        run=run,
        ports=ports,
        engine=FakeWorkflowEngine(clock=clock, uow=uow),
        clock=clock,
    )


def an_attempt(world: World, path: str, n: int = 1, **over: Any) -> Attempt:
    """Store one running Attempt on a row, the way `start_attempt` would have."""
    row = world.row(path)
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": world.run.id,
        "step_run_id": row.id,
        "n": n,
        "status": "running",
        "started_at": world.clock.now(),
    }
    fields.update(over)
    attempt = Attempt(**fields)
    world.ports.attempts.add(attempt)
    return attempt
