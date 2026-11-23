"""Step identity on the run graph and the steps table (story 4, AD-40)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.api.schemas.run_views import StepRowOut
from orchestrator.application.graph import build_run_graph
from orchestrator.application.run_order import build_run_order
from orchestrator.application.use_cases.run_graph import run_graph_for
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.run_views import run_detail
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
RUN_ID = UUID("01960000-0000-7000-9000-0000000000aa")


def a_run() -> Run:
    return Run(
        id=RUN_ID,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=NOW,
    )


def a_row(path: str, seq: int, kind: str = "agent") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=RUN_ID,
        seq=seq,
        path=path,
        label=path,
        kind=kind,
        gate="deterministic",
        status="done",
    )


def an_attempt(row: StepRun, n: int) -> Attempt:
    return Attempt(id=new_id(), run_id=RUN_ID, step_run_id=row.id, n=n, status="done")


def test_node_carries_seq_and_attempts_and_root_has_none() -> None:
    first, planned = a_row("build", 1), a_row("verify", 2, "shell")
    attempts = {first.id: [an_attempt(first, 2), an_attempt(first, 1)]}

    graph = build_run_graph([first, planned], a_run(), attempts)

    root, node, bare = graph.nodes
    assert root.seq is None
    assert (node.seq, node.attempt_n, node.attempt_ns) == (1, 2, (1, 2))
    assert (bare.seq, bare.attempt_n, bare.attempt_ns) == (2, None, ())
    assert graph.run_order == build_run_order([first, planned])


def test_attempts_omitted_leaves_every_node_without_attempts() -> None:
    row = a_row("build", 1)
    node = build_run_graph([row], a_run()).nodes[1]
    assert (node.attempt_n, node.attempt_ns) == (None, ())


def ports(rows: list[StepRun], attempts: list[Attempt]) -> RunViewPorts:
    run = a_run()
    runs = FakeRunRepository()
    runs.add(run)
    steps = FakeStepRunRepository()
    steps.add_many(rows)
    return RunViewPorts(
        runs=runs,
        steps=steps,
        attempts=FakeAttemptRepository(attempts),
        gate_records=FakeGateRecordRepository(),
        projects=FakeProjectRepository(),
        repositories=FakeRepositoryRepository(),
        logs=FakeLogReader(),
        clock=FakeClock(NOW),
    )


def test_steps_table_row_and_graph_node_share_attempt_ns() -> None:
    first, planned = a_row("build", 1), a_row("verify", 2, "shell")
    p = ports([first, planned], [an_attempt(first, 1), an_attempt(first, 2)])

    detail = run_detail(p, RUN_ID)
    graph = run_graph_for(p, RUN_ID)

    assert detail.steps[0].attempt_ns == (1, 2)
    assert StepRowOut.of(detail.steps[0]).attempt_ns == [1, 2]
    assert detail.steps[1].attempt_ns == ()
    assert StepRowOut.of(detail.steps[1]).attempt_ns == []
    assert graph.nodes[1].attempt_ns == (1, 2)
