"""The `StepLog` port and its shared fake (SPEC CAP-1)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.step_log import StepLog
from orchestrator.infrastructure.process.step_log import FsStepLog
from tests.unit.fakes.step_log import FakeStepLog
from tests.unit.step_fixtures import WORK_DIR, a_context, a_row


def test_the_fake_satisfies_the_port_and_records_each_write(tmp_path: Path) -> None:
    run_id = new_id()
    fake = FakeStepLog(str(tmp_path))

    path = fake.write(run_id, 7, 2, ["a", "b"])

    assert isinstance(fake, StepLog)
    assert fake.writes == [(run_id, 7, 2, ("a", "b"))]
    assert list(tmp_path.iterdir()) == []
    assert path == str(tmp_path / "logs" / str(run_id) / "007-2.log")


def test_the_fake_returns_the_path_the_adapter_returns(tmp_path: Path) -> None:
    run_id = new_id()

    assert FakeStepLog("/work").write(run_id, 7, 2, []) == str(
        Path("/work") / "logs" / str(run_id) / "007-2.log"
    )
    assert FakeStepLog(str(tmp_path)).write(run_id, 7, 2, []) == FsStepLog(str(tmp_path)).write(
        run_id, 7, 2, []
    )


def test_the_shared_context_carries_a_fake_step_log() -> None:
    ctx = a_context(a_row(kind="git.checkout", with_resolved={}))

    assert isinstance(ctx.ports.step_log, FakeStepLog)
    assert ctx.ports.step_log.write(new_id(), 1, 1, []).startswith(f"{WORK_DIR}/logs/")
