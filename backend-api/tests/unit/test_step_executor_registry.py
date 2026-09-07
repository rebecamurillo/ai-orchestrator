"""The executor registry (`application/steps/registry.py`): the walker's one way into a kind.

What is asserted here is the *seam*, not the table's contents: that a kind can be bound to an
executor and reached again, and that the three ways an execution can fail to produce a usable
result are described outcomes with reasons on them rather than exceptions escaping into the
walker. Nothing asserts which kinds are registered — 4.7 and 4.8 fill the table, and an
assertion about today's emptiness would be one they had to come back and edit.

`register` mutates a module-level table, so every test that touches it restores what it
found; the `registry` fixture does that once for all of them.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from orchestrator.application.steps import KIND_META, StepContext, StepPorts, execute
from orchestrator.application.steps import registry as registry_module
from orchestrator.application.steps.context import StepExecutor
from orchestrator.application.steps.registry import (
    EXECUTORS,
    INTERNAL,
    MISREPORTED,
    NO_EXECUTOR,
    executor_for,
    register,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

KIND = "shell"
WORK_DIR = "/work"


@pytest.fixture
def registry() -> Iterator[dict[str, Any]]:
    """The registry, restored afterwards: it is process-wide state, like the engine's own."""
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    yield EXECUTORS
    EXECUTORS.clear()
    EXECUTORS.update(kept)


class Recording:
    """An executor that answers with whatever it was built with, and records the context."""

    def __init__(self, result: StepResult | None = None, raises: Exception | None = None) -> None:
        self.result = result or StepResult(status="done", gate="deterministic")
        self.raises = raises
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        if self.raises is not None:
            raise self.raises
        return self.result


def a_context(kind: str = KIND) -> StepContext:
    run_id, row_id = new_id(), new_id()
    row = StepRun(
        id=row_id,
        run_id=run_id,
        seq=1,
        path="steps[0]",
        label="touch",
        kind=kind,
        gate="deterministic",
        status="running",
        with_resolved={"command": "true"},
    )
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=None,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(id=new_id(), run_id=run_id, step_run_id=row_id, n=1, status="running"),
        resume_signal=None,
        ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def test_a_registered_executor_is_the_one_that_runs(registry: dict[str, Any]) -> None:
    executor = Recording()
    register(KIND, executor)

    result = execute(a_context())

    assert executor_for(KIND) is executor
    assert len(executor.seen) == 1
    assert result.status == "done"


def test_registering_a_kind_twice_is_refused(registry: dict[str, Any]) -> None:
    register(KIND, Recording())

    with pytest.raises(ValueError, match=KIND):
        register(KIND, Recording())


def test_an_unregistered_kind_parks_misconfigured_naming_the_kind(
    registry: dict[str, Any],
) -> None:
    result = execute(a_context())

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == NO_EXECUTOR.format(kind=KIND)
    assert result.park.path == "steps[0]"
    assert result.reason == NO_EXECUTOR.format(kind=KIND)


def test_an_unregistered_kind_keeps_the_gate_the_planner_recorded(
    registry: dict[str, Any],
) -> None:
    """A failure does not re-decide how the step's success is judged (AD-7)."""
    assert execute(a_context()).gate == "deterministic"


def test_an_executor_that_raises_parks_internal_with_the_class_and_not_the_message(
    registry: dict[str, Any],
) -> None:
    """The message can carry a path, a command line or a token; the class cannot (AD-5)."""
    register(KIND, Recording(raises=RuntimeError("token abc123 was rejected")))

    result = execute(a_context())

    assert result.park is not None
    assert result.park.kind == "internal"
    assert result.park.reason == INTERNAL.format(name="RuntimeError")
    assert "abc123" not in str(result.model_dump())


def test_an_executor_that_raises_is_logged_with_its_traceback(
    registry: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    register(KIND, Recording(raises=RuntimeError("boom")))

    execute(a_context())

    out = capsys.readouterr().out
    assert registry_module.EXECUTOR_RAISED in out
    assert "RuntimeError" in out


def test_executor_for_answers_none_rather_than_a_stub(registry: dict[str, Any]) -> None:
    assert executor_for("git.push") is None


def test_a_recording_executor_satisfies_the_protocol() -> None:
    assert isinstance(Recording(), StepExecutor)


def test_every_registered_kind_is_a_kind_the_system_knows() -> None:
    """The registry may not invent a kind: `KIND_META` is the one enumeration (AD-9)."""
    assert set(EXECUTORS) <= set(KIND_META)


def test_a_result_reporting_a_status_no_row_can_end_in_is_refused(
    registry: dict[str, Any],
) -> None:
    """`apply_step_result` would raise on one, inside a durable step, with nothing recorded."""
    register(KIND, Recording(StepResult(status="running", gate="deterministic")))

    result = execute(a_context())

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "internal"
    assert result.park.reason == MISREPORTED.format(status="running")


@pytest.mark.parametrize("status", ["done", "blocked", "checkpoint", "error", "skipped"])
def test_every_status_a_row_can_end_in_is_passed_through(
    registry: dict[str, Any], status: str
) -> None:
    register(KIND, Recording(StepResult(status=status, gate="deterministic")))

    assert execute(a_context()).status == status
