"""Run transitions into `needs_you` and the terminal statuses are announced, once each."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from orchestrator.application.use_cases.announce import UNKNOWN, Announcer
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.writers import expire_run, resolve_dependent, set_run
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    SUGGESTED_TEST_GLOBS,
    CloneCheck,
    Repository,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.notifier import Notifier
from orchestrator.domain.values import Park, Signal, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.notifier import FakeNotifier
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

ROW = "checkout"
DONE = StepResult(status="done", gate="deterministic")
PARK = StepResult(
    status="error",
    gate="liveness",
    reason="protected path touched",
    park=Park(kind="protected_path", reason="protected path touched", path=ROW),
)


def a_project(project_id: UUID) -> Project:
    return Project(
        id=project_id,
        slug="les-martines",
        name="Les Martines",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=EPOCH,
        updated_at=EPOCH,
    )


def a_repository(world: World) -> Repository:
    return Repository(
        id=world.run.repository_id,
        project_id=world.run.project_id,
        slug="my-repo",
        url="https://github.com/org/my-repo.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=SUGGESTED_TEST_GLOBS,
        package_manager=DEFAULT_PACKAGE_MANAGER,
        clone_check=CloneCheck.pending(),
        created_at=EPOCH,
        updated_at=EPOCH,
    )


def announced(world: World, *, known: bool = True) -> FakeNotifier:
    """Wire an `Announcer` over the world's fakes; `known=False` leaves the names unstored."""
    notifier = FakeNotifier()
    projects = FakeProjectRepository([a_project(world.run.project_id)] if known else [])
    repositories = FakeRepositoryRepository([a_repository(world)] if known else [])
    announcer = Announcer(
        notifier=notifier,
        projects=projects,
        repositories=repositories,
        attempts=world.ports.attempts,
        clock=world.clock,
    )
    object.__setattr__(world.ports, "announcer", announcer)
    return notifier


def a_pair() -> World:
    return a_world("running", PAIR_PLAN, {"plan": "running"}, spend_usd=Decimal("1.50"))


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeNotifier(), Notifier)


def test_a_park_emits_exactly_one_needs_you_event_with_its_fields() -> None:
    world = a_world("running", PAIR_PLAN, {ROW: "running"}, spend_usd=Decimal("1.50"))
    notifier = announced(world)
    attempt = an_attempt(world, ROW)

    apply_step_result(world.ports, world.run.id, world.row(ROW).seq, PARK)

    [event] = notifier.events
    assert event.run_id == world.run.id
    assert (event.project, event.repository) == ("Les Martines", "my-repo")
    assert event.template == "epic"
    assert event.status == "needs_you"
    assert event.park_kind == "protected_path"
    assert event.reason == "protected path touched"
    assert event.step_path == ROW
    assert event.attempt_id == attempt.id
    assert event.spend_usd == Decimal("1.50")
    assert event.occurred_at == world.clock.now()


def test_a_transition_between_running_states_emits_nothing() -> None:
    world = a_pair()
    notifier = announced(world)

    apply_step_result(world.ports, world.run.id, 1, DONE)

    assert world.stored_run().status == "running"
    assert notifier.events == []


def test_the_run_ending_done_is_announced() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    notifier = announced(world)

    apply_step_result(world.ports, world.run.id, 2, DONE)

    assert [(e.status, e.park_kind, e.attempt_id) for e in notifier.events] == [
        ("done", None, None)
    ]


def test_an_operator_cancel_is_announced() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    notifier = announced(world)

    signal_run(world.signal_ports, world.run.id, Signal(kind="cancel"))

    assert [e.status for e in notifier.events] == ["cancelled"]


def test_a_failed_run_carries_the_reason_its_row_gave() -> None:
    world = a_world(
        "running",
        PAIR_PLAN,
        {"plan": "running"},
        with_resolved={"plan": {"on_fail": "fail"}},
    )
    notifier = announced(world)
    failing = StepResult(status="error", gate="deterministic", reason="install exited 1")

    apply_step_result(world.ports, world.run.id, 1, failing)

    [event] = notifier.events
    assert (event.status, event.reason) == ("failed", "install exited 1")


def test_an_expired_park_is_announced_failed() -> None:
    world = a_world("needs_you", PAIR_PLAN, {ROW: "blocked"}, park_kind="blocked", park_path=ROW)
    notifier = announced(world)

    expire_run(world.ports, world.run)

    [event] = notifier.events
    assert (event.status, event.reason) == ("failed", "parked 30 days")


def test_a_second_park_rewrite_under_the_same_status_is_not_announced_again() -> None:
    world = a_world("needs_you", PAIR_PLAN, {ROW: "blocked"}, park_kind="blocked", park_path=ROW)
    notifier = announced(world)

    set_run(world.ports, world.run, park_kind="budget", park_reason="over")

    assert notifier.events == []


def test_names_that_no_longer_resolve_are_called_unknown() -> None:
    world = a_world("running", PAIR_PLAN, {ROW: "running"})
    notifier = announced(world, known=False)

    apply_step_result(world.ports, world.run.id, world.row(ROW).seq, PARK)

    [event] = notifier.events
    assert (event.project, event.repository) == (UNKNOWN, UNKNOWN)


def test_a_dependency_park_from_queued_is_announced() -> None:
    pred_id = new_id()
    world = a_world("queued", PAIR_PLAN, {}, after_run_ids=(pred_id,))
    notifier = announced(world)

    resolve_dependent(world.ports, None, world.run)

    [event] = notifier.events
    assert (event.status, event.park_kind) == ("needs_you", "dependency")
