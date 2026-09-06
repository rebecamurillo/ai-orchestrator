"""`application/steps/checkpoint.py`: the `checkpoint` kind's whole behaviour (AD-9).

One question, one answer: a `checkpoint` row always parks the Run, with the row's own last
label segment as the reason. `checkpoint.py`'s module docstring is why there is no test
here for a `continue` resuming this executor — `signal_run` moves the row straight to
`done` before the walker ever calls it again (`use_cases/signal_effects.py::_continue`).
"""

from __future__ import annotations

from orchestrator.application.steps.checkpoint import CheckpointExecutor
from orchestrator.application.steps.context import StepContext, StepExecutor, StepPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"


def a_row(*, label: str) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=3,
        path="stories[0].after",
        label=label,
        kind="checkpoint",
        gate="human",
        status="running",
        with_resolved={},
        frame="stories[0]",
        story_id="4-1",
    )


def a_context(row: StepRun) -> StepContext:
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=None,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(id=new_id(), run_id=row.run_id, step_run_id=row.id, n=1, status="running"),
        resume_signal=None,
        ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def test_the_executor_satisfies_the_protocol() -> None:
    assert isinstance(CheckpointExecutor(), StepExecutor)


def test_an_after_item_checkpoint_parks_with_done_checkpoint_as_the_reason() -> None:
    row = a_row(label="epic 1 · story 4-1 · done checkpoint")

    result = CheckpointExecutor().execute(a_context(row))

    assert result.status == "checkpoint"
    assert result.gate == "human"
    assert result.reason == "done checkpoint"
    assert result.park is not None
    assert result.park.kind == "checkpoint"
    assert result.park.reason == "done checkpoint"
    assert result.park.path == row.path


def test_a_before_item_checkpoint_parks_with_before_as_the_reason() -> None:
    row = a_row(label="epic 1 · before")

    result = CheckpointExecutor().execute(a_context(row))

    assert result.reason == "before"
    assert result.park is not None
    assert result.park.reason == "before"
