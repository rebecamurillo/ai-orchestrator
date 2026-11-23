"""`walker_deps` hands the walker the redacting `StepLog` adapter (SPEC CAP-1)."""

from __future__ import annotations

from typing import Any

from orchestrator.domain.ports.step_log import StepLog
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.process.step_log import FsStepLog
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT
from tests.unit.fakes.git import FakeGit

STARTUP = REPO_ROOT / "backend-api/src/orchestrator/infrastructure/dbos/startup.py"


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_the_walker_is_handed_an_fs_step_log(env: dict[str, str]) -> None:
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert isinstance(ports.step_log, FsStepLog)
    assert isinstance(ports.step_log, StepLog)


def test_it_is_built_with_the_instance_secrets() -> None:
    assert "FsStepLog(str(settings.work_dir), log_secrets(settings))" in STARTUP.read_text()
