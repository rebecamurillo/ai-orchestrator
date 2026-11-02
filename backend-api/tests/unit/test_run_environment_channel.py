"""The harness env path never reads `project_channel` (story 3-4, AD-5 amendment).

`read_run_environment` builds the `ProjectContext` a dispatch hands to `env_for(attempt)`. A
Project with a channel and one variable must reach it with exactly that variable, and the
module must name no channel repository at all.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from orchestrator.domain.entities.project import EncryptedEnvVar, Project
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.infrastructure.db import environment as module
from orchestrator.infrastructure.db.environment import read_run_environment
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.project_channel import FakeProjectChannelRepository

NOW = datetime(2026, 11, 2, tzinfo=UTC)


class RecordingSession:
    def close(self) -> None:
        pass


class _Answering:
    def __init__(self, answer: object) -> None:
        self.answer = answer

    def get(self, _id: UUID) -> object:
        return self.answer

    def list_by_repository_non_terminal(self, _id: UUID) -> list[object]:
        return []


def test_a_project_with_a_channel_hands_the_harness_only_its_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crypto = FakeCrypto()
    token = f"tok-{uuid4()}"
    project = Project(
        id=new_id(),
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(EncryptedEnvVar(name="MY_VAR", value_enc=crypto.encrypt("v")),),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )
    channels = FakeProjectChannelRepository(
        [
            ProjectChannel(
                project_id=project.id,
                provider="mattermost",
                base_url="https://chat.example.com",
                channel_id="c1",
                token_enc=crypto.encrypt(token),
                allowed_users=(ChatUser(id="u1", handle="alice"),),
                metadata_only=False,
                created_at=NOW,
                updated_at=NOW,
            )
        ]
    )
    repository = Repository(
        id=new_id(),
        project_id=project.id,
        slug="widgets",
        url="https://github.com/acme/widgets.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )
    run = Run(
        id=new_id(),
        project_id=project.id,
        repository_id=repository.id,
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("1.00"),
        spend_usd=Decimal("0.00"),
        created_at=NOW,
    )
    monkeypatch.setattr(module, "SQLAlchemyRunRepository", lambda _s: _Answering(run))
    monkeypatch.setattr(module, "SQLAlchemyProjectRepository", lambda _s: _Answering(project))
    monkeypatch.setattr(module, "SQLAlchemyRepositoryRepository", lambda _s: _Answering(repository))

    env = read_run_environment(RecordingSession, "6.11.0", run.id, crypto=lambda: crypto)

    assert env is not None
    assert env.project.env_vars == {"MY_VAR": "v"}
    assert token not in repr(env)
    assert channels.get(project.id) is not None


def test_the_environment_reader_names_no_channel_storage() -> None:
    source = inspect.getsource(module)
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "project_channel" not in source
    assert not any("Channel" in name for name in imported)
