"""`read_run_environment` reports the image's BMAD installer only when the file exists (AD-16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.steps.context import RunEnvironment
from orchestrator.infrastructure.db import environment as module
from orchestrator.infrastructure.db.environment import read_run_environment
from tests.unit.test_run_environment_reader import (
    BMAD_VERSION,
    RecordingSession,
    a_project,
    a_repository,
    a_run,
    wire,
)


def _read(monkeypatch: pytest.MonkeyPatch, bin_path: Path) -> RunEnvironment | None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run=run, project=project, repository=repository)
    monkeypatch.setattr(module, "BMAD_BIN", bin_path)
    return read_run_environment(RecordingSession, BMAD_VERSION, run.id)


def test_an_existing_executable_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exe = tmp_path / "bmad-method"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    env = _read(monkeypatch, exe)

    assert env is not None
    assert env.bmad_bin == str(exe)


def test_a_missing_path_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = _read(monkeypatch, tmp_path / "absent")

    assert env is not None
    assert env.bmad_bin is None


def test_a_file_that_is_not_executable_is_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plain = tmp_path / "bmad-method"
    plain.write_text("#!/bin/sh\n")
    plain.chmod(0o644)

    env = _read(monkeypatch, plain)

    assert env is not None
    assert env.bmad_bin is None
