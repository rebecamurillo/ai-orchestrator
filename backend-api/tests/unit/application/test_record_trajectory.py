"""`record_trajectory` (SPEC CAP-9, AD-19, FR-32): the brief's five acceptance criteria,
driven directly against the use case — the same way `apply_step_result`'s own tests are.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from orchestrator.application.use_cases.record_trajectory import record_trajectory
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    PAIR_PLAN,
    World,
    a_world,
    an_attempt,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.trajectories import FakeTrajectoryRepository

FRAME = "stories[0]"
BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
COMMIT_GUARD = "stories[0].commit-guard"

ATTEMPT_COUNT = 2
TOKENS_IN = 100
TOKENS_OUT = 50


def _world(**statuses: str) -> World:
    merged = {
        "stories[0].sync": "done",
        BUILD: "done",
        VERIFY: "done",
        COMMIT_GUARD: "done",
        **statuses,
    }
    return a_world(
        "running",
        EPIC_PLAN,
        statuses=merged,  # type: ignore[arg-type]
        with_resolved={BUILD: {"spec_folder": "specs/notifications"}},
        worktree_path="/work/wt/a",
    )


def _record(
    world: World,
    frame: str = FRAME,
    *,
    run_id: object = None,
    git: FakeGit | None = None,
    trajectories: FakeTrajectoryRepository | None = None,
) -> FakeTrajectoryRepository:
    store = trajectories if trajectories is not None else FakeTrajectoryRepository()
    ports: WriterPorts = replace(world.ports, git=git, trajectories=store)
    record_trajectory(
        run_id if run_id is not None else world.run.id,  # type: ignore[arg-type]
        frame,
        runs=ports.runs,
        steps=ports.steps,
        attempts=ports.attempts,
        gate_records=ports.records,
        git=ports.git,
        trajectories=ports.trajectories,
        clock=ports.clock,
    )
    return store


def _park(world: World, path: str, event: str, actor: str = "machine") -> None:
    world.ports.records.add(
        GateRecord(  # type: ignore[arg-type]
            id=new_id(),
            run_id=world.run.id,
            at=world.clock.now(),
            path=path,
            event=event,
            actor=actor,
        )
    )


# ── AC1: build done after two attempts, verify done ──────────────────────────


def test_a_frame_whose_build_and_verify_both_ended_done_records_one_row() -> None:
    world = _world()
    # interrupted: `started_at` recorded, no `ended_at` — `_wall_clock` must not count it.
    an_attempt(world, BUILD, n=1, status="error", started_at=world.clock.now())
    an_attempt(
        world,
        BUILD,
        n=2,
        status="done",
        start_sha="aaa",
        end_sha="bbb",
        started_at=world.clock.now(),
        ended_at=world.clock.now(),
        cost_usd=Decimal("0.5"),
        tokens_in=100,
        tokens_out=50,
    )
    git = FakeGit(
        head_sha=["ccc"],
        listings={("ccc", "specs/notifications/stories"): ["specs/notifications/stories/1-x.md"]},
        files={("ccc", "specs/notifications/stories/1-x.md"): "status: done\n"},
    )

    store = _record(world, git=git)

    (trajectory,) = store.trajectories
    assert len(trajectory.attempts) == ATTEMPT_COUNT
    assert [a.route for a in trajectory.attempts] == ["error", "done"]
    assert trajectory.gate_results.verify == "done"
    assert trajectory.story_file == "status: done\n"
    assert trajectory.start_sha == "aaa"
    assert trajectory.end_sha == "ccc"
    assert trajectory.cost_usd == Decimal("0.5")
    assert trajectory.tokens_in == TOKENS_IN
    assert trajectory.tokens_out == TOKENS_OUT
    assert trajectory.human_actions == ()


# ── AC2: a blocked stop the Operator answered ────────────────────────────────


def test_a_blocked_stop_answered_by_the_operator_is_two_human_actions() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    _park(world, BUILD, "blocked")
    _park(world, BUILD, "answer", actor="operator")

    store = _record(world)

    (trajectory,) = store.trajectories
    assert {action.event for action in trajectory.human_actions} == {"blocked", "answer"}


def test_automatic_bookkeeping_records_are_not_human_actions() -> None:
    """`redispatch`/`retry_auto` are AD-9's own automatic re-executions, never a person."""
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    _park(world, VERIFY, "redispatch")
    _park(world, BUILD, "retry_auto")

    store = _record(world)

    (trajectory,) = store.trajectories
    assert trajectory.human_actions == ()


# ── AC3: replay is idempotent ─────────────────────────────────────────────────


def test_calling_record_trajectory_twice_writes_only_one_row() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    store = FakeTrajectoryRepository()

    _record(world, trajectories=store)
    _record(world, trajectories=store)

    assert len(store.trajectories) == 1


# ── AC4: verify skipped (no quality_gate_command) ────────────────────────────


def test_a_skipped_verify_reports_gate_results_verify_skipped() -> None:
    world = _world(**{VERIFY: "skipped"})  # type: ignore[arg-type]
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )

    store = _record(world)

    (trajectory,) = store.trajectories
    assert trajectory.gate_results.verify == "skipped"


# ── commit-guard's own outcome ────────────────────────────────────────────────


def test_a_commit_guard_row_with_no_changes_reports_that_reason() -> None:
    world = _world()
    world.ports.steps.update(world.row(COMMIT_GUARD).model_copy(update={"reason": "no changes"}))
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )

    store = _record(world)

    (trajectory,) = store.trajectories
    assert trajectory.gate_results.commit_guard == "no changes"


# ── degrade and safety-belt behaviour ─────────────────────────────────────────


def test_no_trajectories_port_wired_records_nothing() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    ports = replace(world.ports, trajectories=None)

    record_trajectory(
        world.run.id,
        FRAME,
        runs=ports.runs,
        steps=ports.steps,
        attempts=ports.attempts,
        gate_records=ports.records,
        git=None,
        trajectories=None,
        clock=ports.clock,
    )
    # nothing to assert on a store that was never wired — reaching here without an
    # AttributeError is the assertion.


def test_a_build_row_that_has_not_finished_is_left_unrecorded() -> None:
    world = _world(**{BUILD: "running"})  # type: ignore[arg-type]

    store = _record(world)

    assert store.trajectories == []


def test_an_unknown_run_id_records_nothing() -> None:
    world = _world()

    store = _record(world, run_id=new_id())

    assert store.trajectories == []


def test_a_frame_with_no_matching_rows_records_nothing() -> None:
    """A frame naming no `build`/`verify`/`commit-guard` row at all — `PAIR_PLAN` has none."""
    world = a_world("running", PAIR_PLAN, worktree_path="/work/wt/a")

    store = _record(world, frame="stories[0]")

    assert store.trajectories == []


def test_a_protected_path_hit_inside_the_frame_is_carried_onto_gate_results() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    world.ports.records.add(
        GateRecord(  # type: ignore[arg-type]
            id=new_id(),
            run_id=world.run.id,
            at=world.clock.now(),
            path=BUILD,
            event="protected_path",
            actor="machine",
            payload={"hits": [{"path": "tests/unit/a.py", "kind": "modified"}]},
        )
    )

    store = _record(world)

    (trajectory,) = store.trajectories
    (hit,) = trajectory.gate_results.protected_paths.hits
    assert hit.path == "tests/unit/a.py"
    assert hit.kind == "modified"


def test_git_wired_but_no_story_file_at_the_head_leaves_it_empty() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    git = FakeGit(head_sha=["ccc"], listings={("ccc", "specs/notifications/stories"): []})

    store = _record(world, git=git)

    (trajectory,) = store.trajectories
    assert trajectory.story_file == ""


def test_no_git_wired_still_records_the_row_with_an_empty_story_file() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )

    store = _record(world)

    (trajectory,) = store.trajectories
    assert trajectory.story_file == ""
    assert trajectory.end_sha is None


# ── epic_index, read off the frame's own `epics[n]` prefix ───────────────────


def test_epic_index_is_read_off_the_frames_own_epics_prefix() -> None:
    frame = "epics[0].stories[0]"
    world = a_world(
        "running",
        INITIATIVE_PLAN,
        statuses={
            f"{frame}.build": "done",
            f"{frame}.verify": "done",
            f"{frame}.commit-guard": "done",
        },
    )
    an_attempt(
        world,
        f"{frame}.build",
        n=1,
        status="done",
        started_at=world.clock.now(),
        ended_at=world.clock.now(),
    )

    store = _record(world, frame=frame)

    (trajectory,) = store.trajectories
    assert trajectory.epic_index == 0
