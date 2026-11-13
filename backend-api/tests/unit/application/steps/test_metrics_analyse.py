"""`application/steps/metrics_analyse.py`: the row never stops the Run (epic 5 story 4: AC2-3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from orchestrator.application.steps.context import StepContext, StepExecutor, log_path
from orchestrator.application.steps.metrics_analyse import (
    FAILED,
    KIND,
    MetricsAnalyseExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.analysis import Analysis
from tests.unit.fakes.workspace import FakeWorkspace
from tests.unit.step_fixtures import a_context, a_row

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def an_analysis(path: str, status: str = "ok", output: str = "") -> Analysis:
    return Analysis(
        id=UUID(int=abs(hash(path)) % 1000 + 1),
        run_id=UUID(int=1),
        repository_path=path,
        status=status,  # type: ignore[arg-type]
        output=output,
        created_at=NOW,
    )


def a_context_with(
    analysis: object | None, workspace: FakeWorkspace | None = None, gate: str = "unvalidated"
) -> StepContext:
    row = a_row(kind=KIND, with_resolved={}, path="metrics").model_copy(update={"gate": gate})
    context = a_context(row, workspace=workspace if workspace is not None else FakeWorkspace())
    return replace(context, ports=replace(context.ports, analysis=analysis))  # type: ignore[arg-type]


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(MetricsAnalyseExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), MetricsAnalyseExecutor)


def test_two_repositories_analysed_end_the_row_done_with_the_rows_own_gate() -> None:  # AC2
    asked: list[UUID] = []

    def analyse(run_id: UUID) -> Sequence[Analysis]:
        asked.append(run_id)
        return [an_analysis("."), an_analysis("repos/x")]

    context = a_context_with(analyse)

    result = MetricsAnalyseExecutor().execute(context)

    assert asked == [context.attempt.run_id]
    assert result.status == "done"
    assert result.gate == "unvalidated"
    assert result.park is None
    assert result.reason == "2 repositories analysed"
    assert result.log_path is None


def test_an_error_is_done_with_its_first_line_and_the_full_text_in_the_log() -> None:  # AC3
    def analyse(run_id: UUID) -> Sequence[Analysis]:
        raise RuntimeError("tool gone\nsecond line")

    workspace = FakeWorkspace()
    context = a_context_with(analyse, workspace)

    result = MetricsAnalyseExecutor().execute(context)

    assert result.status == "done"
    assert result.gate == "unvalidated"
    assert result.park is None
    assert result.reason == FAILED.format(line="tool gone")
    assert result.reason.startswith("analysis failed: ")  # type: ignore[union-attr]
    assert result.log_path == str(log_path(context))
    logged = workspace.read(log_path(context).name)
    assert logged is not None
    assert "RuntimeError: tool gone" in logged
    assert "second line" in logged
    assert "Traceback" in logged


def test_a_failed_repository_analysis_is_the_first_by_path_and_is_logged_per_analysis() -> None:
    def analyse(run_id: UUID) -> Sequence[Analysis]:
        return [
            an_analysis("repos/z", "failed", "z broke"),
            an_analysis("repos/a", "failed", "a broke\nmore"),
            an_analysis(".", "ok"),
        ]

    workspace = FakeWorkspace()
    context = a_context_with(analyse, workspace, gate="deterministic")

    result = MetricsAnalyseExecutor().execute(context)

    assert (result.status, result.gate, result.park) == ("done", "deterministic", None)
    assert result.reason == "analysis failed: repos/a: a broke"
    logged = workspace.read(log_path(context).name)
    assert logged is not None
    assert logged == "repos/z: failed z broke\nrepos/a: failed a broke\nmore\n.: ok "


def test_an_unset_port_is_a_failed_analysis_not_an_error() -> None:
    context = a_context_with(None)

    result = MetricsAnalyseExecutor().execute(context)

    assert result.status == "done"
    assert result.park is None
    assert result.reason is not None
    assert result.reason.startswith("analysis failed: ")


def test_without_a_workspace_the_log_is_not_claimed() -> None:
    def analyse(run_id: UUID) -> Sequence[Analysis]:
        raise RuntimeError("x")

    context = a_context_with(analyse)
    context = replace(context, ports=replace(context.ports, workspace=None))

    result = MetricsAnalyseExecutor().execute(context)

    assert result.status == "done"
    assert result.log_path is None
