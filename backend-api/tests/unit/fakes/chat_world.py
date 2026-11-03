"""One in-memory world for the chat passes, built from the shared fakes only (AD-18).

`World` holds every fake a `ChatPollPorts` reaches: the Run repositories, one unit of work,
the clock, the thread and notice fakes, the stored channels, Projects and Repositories, the
crypto and the chat factory. `poll()` runs one fire of `run_chat_poll` against it. Later
chat stories extend this fake (4-3's `signal`, for one) rather than writing another.

`ports().signal` carries the world's two mode callables, `resumable` and `latest_attempt`,
which a test sets so an answer resumes a session (4-3). `reply_ports()` is 4-1's
`ReplyPorts` over the same fakes. The engine fake shares the world's
unit of work, so a test sees whether the answer had committed when the engine was told.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.jobs.chat_poll import run_chat_poll
from orchestrator.application.jobs.chat_ports import ChatPollPorts, ChatPorts
from orchestrator.application.use_cases.chat_reply import ReplyPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser, Reply
from tests.unit.fakes.chat import FakeChatChannel, FakeChatChannelFactory
from tests.unit.fakes.chat_thread import FakeChatNoticeRepository, FakeChatThreadRepository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
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


def a_reply(n: int, body: str = "fix X", **overrides: Any) -> Reply:
    """The `n`th reply of a thread: Alice's, mentioning the bot, its cursor just after it."""
    fields: dict[str, Any] = {
        "id": f"r{n}",
        "author_id": ALICE.id,
        "mentions_bot": True,
        "text": f"@bot {body}",
        "body": body,
        "cursor": f"c{n}",
    }
    fields.update(overrides)
    return Reply(**fields)


def _never_resumable(_: str) -> bool:
    return False


def _no_attempt(_: UUID) -> Attempt | None:
    return None


class World:
    """The fakes behind one `ChatPollPorts`."""

    def __init__(self) -> None:
        self.clock = FakeClock(START)
        self.uow = FakeUnitOfWork()
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.records = FakeGateRecordRepository()
        self.attempts = FakeAttemptRepository()
        self.engine = FakeWorkflowEngine(clock=self.clock, uow=self.uow)
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
        self.resumable: Callable[[str], bool] = _never_resumable
        self.latest_attempt: Callable[[UUID], Attempt | None] = _no_attempt
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

    def add_thread(self, run: Run, **overrides: Any) -> ChatThread:
        """An `open` thread at the Run's current stop, on the default channel."""
        fields: dict[str, Any] = {
            "id": new_id(),
            "run_id": run.id,
            "park_seq": run.park_seq,
            "park_kind": run.park_kind,
            "provider": "mattermost",
            "channel_id": "c1",
            "ref": f"root-{run.id}",
            "cursor": None,
            "state": "open",
            "error": None,
            "last_reminded_at": None,
            "created_at": self.clock.now(),
            "updated_at": self.clock.now(),
        }
        fields.update(overrides)
        thread = ChatThread(**fields)
        self.threads.add(thread)
        return thread

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
                attempts=self.attempts,
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
        chat = self.chat_ports()
        return ChatPollPorts(
            chat=chat,
            signal=SignalPorts(
                writers=chat.writers,
                engine=self.engine,
                harness_is_resumable=self.resumable,
                latest_attempt_for_run=self.latest_attempt,
            ),
            factory=self.factory,
            crypto=self._crypto,
            clock=self.clock,
            public_base_url=self.public_base_url,
            reminder_hours=HOURS,
            started_at=self.started_at,
        )

    def reply_ports(
        self,
        *,
        harness_is_resumable: Callable[[str], bool] = _never_resumable,
        latest_attempt_for_run: Callable[[UUID], Attempt | None] = _no_attempt,
    ) -> ReplyPorts:
        chat = self.chat_ports()
        return ReplyPorts(
            signal=SignalPorts(
                writers=chat.writers,
                engine=self.engine,
                harness_is_resumable=harness_is_resumable,
                latest_attempt_for_run=latest_attempt_for_run,
            ),
            threads=self.threads,
            channels=self.channels,
        )

    def poll(self) -> None:
        run_chat_poll(self.ports())

    def _crypto(self) -> FakeCrypto:
        if self.crypto_error is not None:
            raise self.crypto_error
        return self.crypto
