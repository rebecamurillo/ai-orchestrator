"""Attempt roles (story 1-7, spine AD-21, ratified 2026-11-01).

Every reader that picks a session, numbers an archive, counts a retry or builds an AD-17 range
reads `agent` attempts only. The parked row in each test below holds attempt 1 (`agent`,
session `s1`) and a newer attempt 2 (`consult`, session `s2`): each reader must answer with
attempt 1. The same readers given only `agent` attempts answer exactly as before.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from orchestrator.application.jobs.terminal_poll import TerminalPollPorts, run_terminal_poll
from orchestrator.application.rules.protected_paths import hits_payload
from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY, STORY_ID_KEY
from orchestrator.application.use_cases.announce import Announcer
from orchestrator.application.use_cases.run_files import RunFilesDiffPorts, diff_run_file
from orchestrator.application.use_cases.run_views import RunViewPorts, run_detail
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.terminal import TerminalPorts, resume_command
from orchestrator.application.use_cases.walk import WalkPorts, attempt_row, run_row
from orchestrator.application.use_cases.walk_frame import frame_start_sha, read_frame
from orchestrator.application.use_cases.writers import Entry, record
from orchestrator.domain.entities.attempt import Attempt, agent_attempts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.harness import TerminalEnvironment
from orchestrator.domain.statuses import ATTEMPT_ROLES, AttemptRole
from orchestrator.domain.values import Signal, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.notifier import FakeNotifier
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeAttemptRepository
from tests.unit.fakes.workspace import FakeWorkspace

BUILD = "stories[0].build"
WORKTREE = "/work/acme/widgets/wt/roles"
AGENT_SESSION = "s1"
CONSULT_SESSION = "s2"
AGENT_START = "a" * 40
AGENT_END = "b" * 40
CONSULT_START = "c" * 40
CONSULT_END = "d" * 40
HEAD = "e" * 40
SPEC_FOLDER = "specs/roles"
STORY_ID = "1"
STORY_PATH = f"{SPEC_FOLDER}/stories/{STORY_ID}-roles.md"
DONE_FILE = "---\nstatus: done\n---\n\n# Roles\n"
AGENT_MODEL = "agent-model"
CONSULT_MODEL = "senior-model"
ENDED = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
#: The newer of the two stored attempts, and the one `start_attempt` opens after them.
SECOND = 2
THIRD = 3


def a_parked_world(
    second_role: AttemptRole = "consult",
    *,
    consult_session: str | None = CONSULT_SESSION,
    **over: Any,
) -> World:
    """A Run parked `blocked` on `BUILD`: attempt 1 `agent`, attempt 2 of `second_role`."""
    fields: dict[str, Any] = {
        "park_kind": "blocked",
        "park_path": BUILD,
        "park_reason": "intent gap",
        "worktree_path": WORKTREE,
    }
    fields.update(over)
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        {BUILD: {SPEC_FOLDER_KEY: SPEC_FOLDER, STORY_ID_KEY: STORY_ID}},
        **fields,
    )
    an_attempt(
        world,
        BUILD,
        n=1,
        status="blocked",
        harness="claude",
        model=AGENT_MODEL,
        session_id=AGENT_SESSION,
        start_sha=AGENT_START,
        end_sha=AGENT_END,
        ended_at=ENDED,
    )
    an_attempt(
        world,
        BUILD,
        n=2,
        role=second_role,
        status="blocked",
        harness="claude",
        model=CONSULT_MODEL,
        session_id=consult_session,
        start_sha=CONSULT_START,
        end_sha=CONSULT_END,
        ended_at=ENDED,
    )
    return world


def an_agent_only_world() -> World:
    """The same park with two `agent` attempts: every reader answers with attempt 2."""
    return a_parked_world("agent")


def view_ports(world: World, *, resumable: bool = True) -> RunViewPorts:
    return RunViewPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        gate_records=world.ports.records,
        projects=FakeProjectRepository([]),
        repositories=FakeRepositoryRepository([]),
        logs=FakeLogReader(),
        clock=world.clock,
        terminal=terminal_ports(),
        harness_is_resumable=lambda name: resumable,
    )


def terminal_ports() -> TerminalPorts:
    return TerminalPorts(
        env=lambda attempt, **_: TerminalEnvironment(identifiers=(), exports=()),
        harnesses={"claude": FakeHarness()},
    )


def signal_ports(world: World) -> SignalPorts:
    return SignalPorts(
        writers=world.ports,
        engine=world.engine,
        harness_is_resumable=lambda name: True,
        latest_attempt_for_run=world.ports.attempts.latest_for_run,
    )


class Recording:
    """An `agent` executor that answers `done` and keeps the context it was handed."""

    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("agent", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def walk_ports(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )


# ── the role and the filter ──────────────────────────────────────────────────


def test_the_roles_are_agent_consult_and_session() -> None:
    assert ATTEMPT_ROLES == ("agent", "consult", "session")


def test_an_attempt_is_an_agent_attempt_unless_it_says_otherwise() -> None:
    attempt = Attempt(id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="running")

    assert attempt.role == "agent"


def test_agent_attempts_keeps_only_agent_attempts_in_their_order() -> None:
    world = a_parked_world("session")
    an_attempt(world, BUILD, n=3)

    kept = agent_attempts(world.attempts_of(BUILD))

    assert [attempt.n for attempt in kept] == [1, THIRD]


# ── the repository reads ─────────────────────────────────────────────────────


def test_get_latest_agent_skips_a_newer_consult() -> None:
    world = a_parked_world()
    attempts = world.ports.attempts

    latest = attempts.get_latest_agent(world.row(BUILD).id)

    assert latest is not None
    assert latest.n == 1
    assert attempts.get_latest(world.row(BUILD).id).n == SECOND  # type: ignore[union-attr]


def test_get_latest_agent_is_none_for_a_row_with_no_agent_attempt() -> None:
    attempts = FakeAttemptRepository()

    assert attempts.get_latest_agent(new_id()) is None


def test_latest_for_run_reads_agent_attempts_only() -> None:
    world = a_parked_world()

    latest = world.ports.attempts.latest_for_run(world.run.id)

    assert latest is not None
    assert latest.session_id == AGENT_SESSION


def test_latest_for_run_is_none_when_the_run_holds_only_other_roles() -> None:
    world = a_world("running")
    an_attempt(world, BUILD, role="consult")

    assert world.ports.attempts.latest_for_run(world.run.id) is None


def test_latest_for_run_is_unchanged_when_every_attempt_is_agent() -> None:
    world = an_agent_only_world()

    latest = world.ports.attempts.latest_for_run(world.run.id)

    assert latest is not None
    assert latest.session_id == CONSULT_SESSION


# ── previous_attempt, and the acceptance path through `answer` ───────────────


def test_answer_with_no_mode_resumes_the_agent_attempt_s_session(executor: Recording) -> None:
    world = a_parked_world(consult_session=None)
    signal = Signal(kind="answer", payload={"text": "use the adapter"})

    signal_run(signal_ports(world), world.run.id, signal)
    attempt_row(walk_ports(world), world.run.id, world.row(BUILD).seq, {}, "answer")

    assert world.records()[-1].payload["mode"] == "session"
    context = executor.seen[0]
    assert context.attempt.n == THIRD
    assert context.attempt.role == "agent"
    assert context.previous_attempt is not None
    assert context.previous_attempt.session_id == AGENT_SESSION


def test_previous_attempt_is_the_newest_earlier_attempt_when_all_are_agent(
    executor: Recording,
) -> None:
    world = an_agent_only_world()
    an_attempt(world, BUILD, n=THIRD)
    record(world.ports, world.run, Entry(event="answer", actor="operator", text="go"))

    run_row(walk_ports(world), world.run.id, world.row(BUILD).seq, "answer")

    previous = executor.seen[0].previous_attempt
    assert previous is not None
    assert previous.n == SECOND


def test_a_row_whose_only_earlier_attempt_is_a_consult_has_no_previous_attempt(
    executor: Recording,
) -> None:
    world = a_world("running", statuses={BUILD: "running"})
    an_attempt(world, BUILD, n=1, role="consult", ended_at=ENDED)
    an_attempt(world, BUILD, n=2)

    run_row(walk_ports(world), world.run.id, world.row(BUILD).seq)

    assert executor.seen[0].previous_attempt is None


# ── AD-17: the frame's attempts ──────────────────────────────────────────────


def test_the_frame_reads_agent_attempts_only() -> None:
    world = a_parked_world()

    frame = read_frame(world.ports, world.run.id, world.row(BUILD))

    assert [(a.start_sha, a.end_sha) for a in frame.attempts] == [(AGENT_START, AGENT_END)]


def test_the_frame_start_is_never_a_consult_s_start() -> None:
    world = a_world("running", statuses={BUILD: "running"})
    an_attempt(world, BUILD, n=1, role="consult", start_sha=CONSULT_START)
    an_attempt(world, BUILD, n=2, start_sha=AGENT_START)

    frame = read_frame(world.ports, world.run.id, world.row(BUILD))

    assert frame_start_sha(frame.attempts) == AGENT_START


def test_the_frame_keeps_every_attempt_when_all_are_agent() -> None:
    world = an_agent_only_world()

    frame = read_frame(world.ports, world.run.id, world.row(BUILD))

    assert [a.n for a in frame.attempts] == [1, 2]


# ── reply_available, the alert and the terminal on the Run detail ────────────


def test_run_detail_reads_the_agent_attempt_for_reply_alert_and_terminal() -> None:
    world = a_parked_world(consult_session=None)

    detail = run_detail(view_ports(world), world.run.id)

    assert detail.reply_available is True
    assert detail.alert is not None
    assert detail.alert.attribution is not None
    assert detail.alert.attribution.model == AGENT_MODEL
    assert detail.terminal is not None
    assert detail.terminal.command.endswith(f"--resume {AGENT_SESSION}'")


def test_run_detail_reads_the_newest_attempt_when_all_are_agent() -> None:
    world = an_agent_only_world()

    detail = run_detail(view_ports(world), world.run.id)

    assert detail.alert is not None
    assert detail.alert.attribution is not None
    assert detail.alert.attribution.model == CONSULT_MODEL
    assert detail.terminal is not None
    assert detail.terminal.command.endswith(f"--resume {CONSULT_SESSION}'")


@pytest.mark.parametrize("role", ["consult", "session"])
def test_no_terminal_command_resumes_an_attempt_that_is_not_the_agent_s(role: str) -> None:
    world = a_parked_world(role)  # type: ignore[arg-type]
    row = world.row(BUILD)
    consult = world.attempts_of(BUILD)[-1]

    command = resume_command(terminal_ports(), world.run, row, consult, project_slug="acme")

    assert command is None


# ── the announcement ─────────────────────────────────────────────────────────


def test_the_announcement_names_the_agent_attempt() -> None:
    world = a_parked_world()
    notifier = FakeNotifier()
    announcer = Announcer(
        notifier=notifier,
        projects=FakeProjectRepository([]),
        repositories=FakeRepositoryRepository([]),
        attempts=world.ports.attempts,
        clock=world.clock,
    )
    before = world.run.model_copy(update={"status": "running"})

    announcer.transition(before, world.run)

    (event,) = notifier.events
    assert event.attempt_id == world.attempts_of(BUILD)[0].id


# ── the park diff and the terminal poll's end SHA ────────────────────────────


def diff_world(second_role: AttemptRole) -> tuple[World, RunFilesDiffPorts, FakeGit]:
    world = a_parked_world(second_role, park_kind="protected_path")
    world.ports.records.add(_park_record(world, (Change(path="AGENTS.md", kind="modified"),)))
    git = FakeGit(diff=["diff"])
    ports = RunFilesDiffPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        records=world.ports.records,
        git=git,
    )
    return world, ports, git


def _park_record(world: World, hits: tuple[Change, ...]) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=world.run.id,
        at=ENDED,
        path=BUILD,
        event="protected_path",
        actor="machine",
        text="protected path modified",
        payload=hits_payload(hits),
    )


@pytest.mark.parametrize(
    ("second_role", "expected"), [("consult", AGENT_START), ("agent", CONSULT_START)]
)
def test_the_park_diff_starts_at_the_agent_attempt(second_role: str, expected: str) -> None:
    world, ports, _ = diff_world(second_role)  # type: ignore[arg-type]

    diff = diff_run_file(ports, world.run.id, "AGENTS.md")

    assert diff.from_sha == expected


def poll_world(second_role: AttemptRole) -> tuple[World, TerminalPollPorts]:
    world = a_parked_world(second_role, terminal_session=True, terminal_clean_polls=1)
    workspace = FakeWorkspace(WORKTREE, {STORY_PATH: DONE_FILE})
    ports = TerminalPollPorts(
        signal=world.signal_ports,
        git=FakeGit(status=[""], head_sha=[HEAD]),
        workspace=lambda _root: workspace,
    )
    return world, ports


def test_the_terminal_poll_closes_the_agent_attempt_s_range() -> None:
    world, ports = poll_world("consult")

    run_terminal_poll(ports)

    agent, consult = world.attempts_of(BUILD)
    assert agent.end_sha == HEAD
    assert consult.end_sha == CONSULT_END


def test_the_terminal_poll_closes_the_newest_attempt_when_all_are_agent() -> None:
    world, ports = poll_world("agent")

    run_terminal_poll(ports)

    first, second = world.attempts_of(BUILD)
    assert first.end_sha == AGENT_END
    assert second.end_sha == HEAD
