"""Pre-flight's `docker` line (`application/preflight/docker.py`), feat/docker-for-verify.

A repository whose verify commands run `docker compose` cannot pass on an instance with no
Docker daemon, and nothing said so before the agent had spent its attempt. The line is a
guess from two signs — a `shell` row naming docker, a compose file at the repository root —
so it is `warn` at most, and absent when neither sign is there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.docker import COMPOSE_FILES, docker_line
from orchestrator.application.preflight.model import CHECK_DOCKER, PreflightRequest
from orchestrator.application.templates.plan_model import Plan
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.values import PlannedRow
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

PLAN_REF = "a" * 40
BASE_DIR = Path("/work/p/r/base")


def row(kind: str, command: object = None, path: str = "verify") -> PlannedRow:
    return PlannedRow(
        seq=1,
        path=path,
        label=path,
        kind=kind,
        gate="deterministic",
        status="planned",
        reason=None,
        with_resolved={} if command is None else {"command": command},
        frame=None,
        story_id=None,
    )


def ctx(*rows: PlannedRow, git: FakeGit | None = None, planned: bool = True) -> Context:
    return Context(
        git=git or FakeGit(files={}),
        base_dir=BASE_DIR,
        max_active_runs=2,
        repository=None,
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        req=PreflightRequest(),
        tree=None,
        plan=Plan(plan_ref=PLAN_REF, rows=rows) if planned else None,
        plan_error=None,
    )


# ── no sign, no line ─────────────────────────────────────────────────────────


def test_no_plan_no_line() -> None:
    assert docker_line(ctx(planned=False), verify_docker=False) is None


def test_a_plan_with_no_sign_has_no_line() -> None:
    plan_ctx = ctx(row("shell", "make check"), row("agent", "docker compose up"))

    assert docker_line(plan_ctx, verify_docker=False) is None


@pytest.mark.parametrize("command", ["dockerfile-lint .", "./my-docker-thing", "echo dockers"])
def test_a_word_that_only_contains_docker_is_no_sign(command: str) -> None:
    assert docker_line(ctx(row("shell", command)), verify_docker=False) is None


# ── a shell row that names docker ────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "docker compose up -d --wait && pytest",
        "scripts/check.sh && docker-compose -f e2e.yml run tests",
        "cd backend; docker build .",
    ],
)
def test_a_shell_row_naming_docker_warns_while_the_daemon_is_off(command: str) -> None:
    found = docker_line(ctx(row("shell", command, path="epic.verify")), verify_docker=False)

    assert found is not None
    assert found.check == CHECK_DOCKER
    assert found.status == "warn"
    assert found.text.startswith("epic.verify runs docker · ")
    assert "VERIFY_DOCKER=true" in found.text
    assert "./install.sh start --with-docker" in found.text


def test_the_same_row_is_ok_while_the_daemon_is_on() -> None:
    found = docker_line(ctx(row("shell", "docker compose up")), verify_docker=True)

    assert found is not None
    assert found.status == "ok"
    assert "the docker service" in found.text


def test_a_shell_row_sign_needs_no_git_read() -> None:
    git = FakeGit(files={})

    docker_line(ctx(row("shell", "docker compose up"), git=git), verify_docker=False)

    assert git.calls == []


# ── a compose file at the repository root ────────────────────────────────────


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_a_compose_file_at_the_plan_commit_is_a_sign(name: str) -> None:
    """The quality gate is often `scripts/check.sh`, which runs compose out of sight."""
    git = FakeGit(files={(PLAN_REF, name): "services: {}\n"})

    found = docker_line(ctx(row("shell", "scripts/check.sh"), git=git), verify_docker=False)

    assert found is not None
    assert found.status == "warn"
    assert found.text.startswith(f"{name} at the repository root · ")


def test_the_compose_file_is_read_at_the_plan_commit_from_the_base_clone() -> None:
    git = FakeGit(files={})

    docker_line(ctx(git=git), verify_docker=False)

    assert [call for call in git.calls if call[0] == "read_file"] == [
        ("read_file", (BASE_DIR, PLAN_REF, name)) for name in COMPOSE_FILES
    ]


@pytest.mark.parametrize(
    "failure", [GitError(command="git show", exit_code=128, output="fatal: bad object"), OSError()]
)
def test_a_git_failure_is_no_sign_rather_than_a_crash(failure: Exception) -> None:
    """Origin and base-branch lines already report the git failure itself."""
    git = FakeGit(read_file=[failure])

    assert docker_line(ctx(git=git), verify_docker=False) is None
