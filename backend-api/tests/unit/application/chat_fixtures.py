"""One in-memory world for story 3-3's chat passes, built from the shared fakes only.

`World` holds every fake a `ChatPollPorts` reaches: the Run repositories, one unit of work,
the clock, the thread and notice fakes, the stored channels, Projects and Repositories, the
crypto and the chat factory. `poll()` runs one fire of `run_chat_poll` against it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.jobs.chat_poll import run_chat_poll
from orchestrator.application.jobs.chat_ports import ChatPollPorts, ChatPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from tests.unit.fakes.chat import FakeChatChannel, FakeChatChannelFactory
from tests.unit.fakes.chat_thread import FakeChatNoticeRepository, FakeChatThreadRepository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.project_channel import FakeProjectChannelRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

START = datetime.fromisoformat("2026-11-02T09:00:00+00:00")
TOKEN = "tok-xoxb-secret"
BASE_URL = "https://orch.example.com"
HOURS = 4
ALICE = ChatUser(id="u1", handle="alice")
BOB = ChatUser(id="u2", handle="bob")


def a_project(name: str = "Mixed Signals") -> Project:
    return Project(
        id=new_id(),
        slug=name.lower().replace(" ", "-"),
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=START,
        updated_at=START,
    )


def a_repository(project_id: UUID, slug: str = "orchestrator") -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
        slug=slug,
        url=f"https://example.invalid/{slug}.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=START, output="", bmad_version="6.11.0"),
        created_at=START,
        updated_at=START,
    )


def a_row(run_id: UUID, seq: int, path: str, **overrides: Any) -> StepRun:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": run_id,
        "seq": seq,
        "path": path,
        "label": path.rsplit(".", 1)[-1],
        "kind": "agent",
        "gate": "deterministic",
        "status": "blocked",
    }
    fields.update(overrides)
    return StepRun(**fields)


class World:
    """The fakes behind one `ChatPollPorts`."""

    def __init__(self) -> None:
        self.clock = FakeClock(START)
        self.uow = FakeUnitOfWork()
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.records = FakeGateRecordRepository()
        self.threads = FakeChatThreadRepository(self.runs)
        self.notices = FakeChatNoticeRepository(self.runs, self.records)
        self.channels = FakeProjectChannelRepository()
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.crypto = FakeCrypto()
        self.chat = FakeChatChannel()
        self.factory = FakeChatChannelFactory(self.chat)
        self.public_base_url = BASE_URL
        self.started_at = START - timedelta(hours=1)
        self.crypto_error: Exception | None = None
        self.project = self.add_project()
        self.repository = self.add_repository(self.project.id)

    # ── building ────────────────────────────────────────────────────────────────────────

    def add_project(self, name: str = "Mixed Signals") -> Project:
        project = a_project(name)
        self.projects.add(project)
        return project

    def add_repository(self, project_id: UUID, slug: str = "orchestrator") -> Repository:
        repository = a_repository(project_id, slug)
        self.repositories.add(repository)
        return repository

    def add_channel(self, project_id: UUID | None = None, **overrides: Any) -> ProjectChannel:
        fields: dict[str, Any] = {
            "project_id": project_id or self.project.id,
            "provider": "mattermost",
            "base_url": "https://chat.example.com",
            "channel_id": "c1",
            "token_enc": self.crypto.encrypt(TOKEN),
            "allowed_users": (ALICE, BOB),
            "metadata_only": False,
            "created_at": START - timedelta(days=1),
            "updated_at": START - timedelta(days=1),
        }
        fields.update(overrides)
        channel = ProjectChannel(**fields)
        self.channels.put(channel)
        return channel

    def add_run(self, **overrides: Any) -> Run:
        fields: dict[str, Any] = {
            "id": new_id(),
            "project_id": self.project.id,
            "repository_id": self.repository.id,
            "template_name": "epic",
            "template_version": 1,
            "status": "needs_you",
            "budget_usd": Decimal("10"),
            "inputs": {"spec_folder": "specs/gates"},
            "park_kind": "blocked",
            "park_path": "epics[1].stories[0].build",
            "park_reason": "Which schema?",
            "park_seq": 3,
            "created_at": START - timedelta(hours=2),
        }
        fields.update(overrides)
        run = Run(**fields)
        self.runs.add(run)
        return run

    def add_rows(self, *rows: StepRun) -> None:
        self.steps.add_many(list(rows))

    def add_record(self, run_id: UUID, **overrides: Any) -> GateRecord:
        fields: dict[str, Any] = {
            "id": new_id(),
            "run_id": run_id,
            "at": self.clock.now(),
            "event": "answer",
            "actor": "operator",
        }
        fields.update(overrides)
        record = GateRecord(**fields)
        self.records.add(record)
        return record

    def update_run(self, run: Run, **changes: Any) -> Run:
        updated = run.model_copy(update=changes)
        self.runs.update(updated)
        return updated

    # ── reading ─────────────────────────────────────────────────────────────────────────

    def only_thread(self) -> ChatThread:
        (thread,) = self.threads.threads.values()
        return thread

    # ── ports ───────────────────────────────────────────────────────────────────────────

    def chat_ports(self) -> ChatPorts:
        return ChatPorts(
            writers=WriterPorts(
                runs=self.runs,
                steps=self.steps,
                attempts=FakeAttemptRepository(),
                records=self.records,
                uow=self.uow,
                clock=self.clock,
            ),
            threads=self.threads,
            channels=self.channels,
            notices=self.notices,
            projects=self.projects,
            repositories=self.repositories,
        )

    def ports(self) -> ChatPollPorts:
        return ChatPollPorts(
            chat=self.chat_ports(),
            factory=self.factory,
            crypto=self._crypto,
            clock=self.clock,
            public_base_url=self.public_base_url,
            reminder_hours=HOURS,
            started_at=self.started_at,
        )

    def poll(self) -> None:
        run_chat_poll(self.ports())

    def _crypto(self) -> FakeCrypto:
        if self.crypto_error is not None:
            raise self.crypto_error
        return self.crypto
