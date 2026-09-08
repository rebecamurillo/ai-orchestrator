"""`read_run_environment`'s Epic 5 half: the Run, the Project and the test globs (5.4).

`tests/unit/test_run_environment_reader.py` is frozen and covers the four columns the git
kinds read; these are the four the `agent` kind adds. The one that carries a rule is
`env_vars`: AD-5 stores a Project's variables encrypted at rest, and `domain/ports/crypto.py`
says they are decrypted "only when a Run is about to hand the value to a harness process" —
which is this function, and nowhere else. The `Crypto` adapter arrives as a *factory* rather
than an instance because `FernetCrypto` refuses the contract's placeholder key at
construction, and `walker_deps(Settings(), ...)` is built in unit tests that never dispatch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from orchestrator.domain.entities.project import EncryptedEnvVar, Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db import environment as module
from orchestrator.infrastructure.db.environment import read_run_environment
from tests.unit.fakes.crypto import FakeCrypto

NOW = datetime(2026, 9, 8, tzinfo=UTC)
BMAD_VERSION = "6.11.0"


class RecordingSession:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _Answering:
    def __init__(self, answer: object) -> None:
        self.answer = answer

    def get(self, _id: UUID) -> object:
        return self.answer


def a_project(crypto: FakeCrypto | None = None, **over: Any) -> Project:
    variables: tuple[EncryptedEnvVar, ...] = ()
    if crypto is not None:
        variables = (EncryptedEnvVar(name="MY_VAR", value_enc=crypto.encrypt("v")),)
    fields: dict[str, Any] = {
        "id": new_id(),
        "name": "Acme",
        "slug": "acme",
        "context_text": "read the handbook",
        "context_paths": ("docs/handbook.md",),
        "env_vars_enc": variables,
        "log_prompt_content": True,
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(over)
    return Project(**fields)


def a_repository(project_id: UUID) -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
        slug="widgets",
        url="https://github.com/acme/widgets.git",
        default_branch="main",
        install_command="uv sync",
        quality_gate_command="make check",
        unit_test_command="make test",
        test_globs=("tests/**", "**/*_test.py"),
        package_manager="uv",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(project: Project, repository: Repository) -> Run:
    return Run(
        id=new_id(),
        project_id=project.id,
        repository_id=repository.id,
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10.00"),
        spend_usd=Decimal("2.50"),
        created_at=NOW,
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


def wire(monkeypatch: pytest.MonkeyPatch, run: Run, project: Project, repo: Repository) -> None:
    monkeypatch.setattr(module, "SQLAlchemyRunRepository", lambda _s: _Answering(run))
    monkeypatch.setattr(module, "SQLAlchemyProjectRepository", lambda _s: _Answering(project))
    monkeypatch.setattr(module, "SQLAlchemyRepositoryRepository", lambda _s: _Answering(repo))


def test_the_run_itself_travels_because_three_readers_need_the_entity(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    """`env_for(run=…)`, `attempt_span(run, …)` and `budget - spend` all take the Run."""
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run, project, repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id)

    assert env is not None
    assert env.run is run
    assert env.test_globs == ("tests/**", "**/*_test.py")


def test_the_project_context_is_what_a_dispatch_hands_to_the_harness(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run, project, repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id)

    assert env is not None
    assert env.project.context_text == "read the handbook"
    assert env.project.context_paths == ("docs/handbook.md",)
    assert env.project.log_prompt_content is True


def test_a_projects_variables_are_decrypted_here_and_only_here(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    crypto = FakeCrypto()
    project = a_project(crypto)
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run, project, repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id, crypto=lambda: crypto)

    assert env is not None
    assert env.project.env_vars == {"MY_VAR": "v"}
    assert len(crypto.decrypted) == 1


def test_a_project_with_no_variables_never_builds_a_key(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    """A misconfigured `ORCHESTRATOR_SECRET_KEY` must not stop a Run that has no secret."""
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run, project, repository)

    def refuse() -> Any:
        raise AssertionError("no Crypto is built for a Project with no variables")

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id, crypto=refuse)

    assert env is not None
    assert env.project.env_vars == {}


def test_without_a_crypto_factory_the_variables_read_as_none_at_all(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    """The three-positional call every git-kind test makes: no key, and no plaintext."""
    crypto = FakeCrypto()
    project = a_project(crypto)
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(monkeypatch, run, project, repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id)

    assert env is not None
    assert env.project.env_vars == {}
    assert crypto.decrypted == []
