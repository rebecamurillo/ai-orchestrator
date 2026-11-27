"""The initiative detail the page renders (story 6, epic 7): AC1-AC4 and AC6-AC8."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from orchestrator.application.use_cases.initiative_views import initiative_detail
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.ports.git import Change
from tests.unit.application.initiative_read_world import (
    FOLDER,
    GATE,
    STATUS_MAP,
    WORKTREE,
    ReadWorld,
)
from tests.unit.fakes.git import FakeGit

SPEC_STEPS = ("brief", "prd", "ux", "tech")


def talk(step: str) -> StepDecl:
    return StepDecl(
        id=step,
        kind="conversation",
        skill="s",
        persona=f"personas/{step}-agent.md",
        file=f"{step.upper()}.md",
        writes=(),
    )


def sequence(steps: tuple[str, ...] = SPEC_STEPS) -> FrozenSequence:
    gate = StepDecl(id="gate", kind="automatic", skill=None, persona=None, file=None, writes=())
    return FrozenSequence(
        package="p",
        sha="abc",
        workflows=(
            FrozenWorkflow(
                workflow="spec",
                template="p/spec",
                version=2,
                type="interactive",
                shown_as="workflow",
                steps=(*(talk(s) for s in steps), gate),
            ),
            FrozenWorkflow(
                workflow="merge",
                template="p/merge",
                version=1,
                type="interactive",
                shown_as="step",
                steps=(),
            ),
            FrozenWorkflow(
                workflow="build",
                template="p/build",
                version=1,
                type="auto",
                shown_as="workflow",
                steps=(),
            ),
        ),
        gate=GATE,
        status_map=STATUS_MAP,
    )


def named(step: str) -> dict[str, Any]:
    return {"with_resolved": {"step": step}}


def parked_on_ux(world: ReadWorld, initiative: Initiative, **overrides: Any) -> Any:
    run = world.run(
        initiative,
        status="needs_you",
        park_kind="conversation",
        park_path="steps[3]",
        park_seq=5,
        **overrides,
    )
    world.row(run, 1, status="done", **named("brief"))
    world.row(run, 2, status="done", **named("prd"))
    ux = world.row(run, 3, status="checkpoint", **named("ux"))
    world.turn(ux, 1)
    world.turn(ux, 2)
    return run


def test_ac1_the_header_the_track_lines_and_the_strip() -> None:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence())
    run = parked_on_ux(world, initiative)

    detail = initiative_detail(world.ports, initiative.id)

    assert (detail.current_position, detail.current_step, detail.workflow_count) == (1, "ux", 2)
    assert detail.folder == f"{FOLDER}/snake"
    assert (detail.project.id, detail.project.name) == (world.project.id, world.project.name)  # type: ignore[union-attr]
    assert (detail.hub.id, detail.hub.slug) == (world.hub.id, world.hub.slug)  # type: ignore[union-attr]
    assert detail.sequence_fixed_at == detail.created_at
    spec, build = detail.workflows
    assert spec.line == "step 3 of 6 · ux · your turn"
    assert build.line == "starts by itself when spec is done"
    steps = {s.id: s for s in spec.steps}
    ux = steps["ux"]
    assert (ux.number, ux.agent, ux.token, ux.line, ux.run_id) == (
        "1.3",
        "ux-agent",
        "RUN",
        "your turn · 2 turns",
        run.id,
    )
    assert (steps["tech"].token, steps["tech"].line) == ("QUE", "next")
    assert (steps["gate"].agent, steps["gate"].line) == (None, "starts after tech")
    assert steps["merge"].line == "starts after the gate passes"
    assert [s.number for s in spec.steps] == ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]
    assert (ux.park_seq, ux.park_kind, ux.conflict_files) == (5, "conversation", [])


def test_ac2_owners_and_operator_turns() -> None:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence(), round=2)
    first = parked_on_ux(world, initiative)
    assert first.status == "needs_you"
    world.run(
        initiative,
        minutes=30,
        initiative_round=2,
        status="running",
        inputs={"round_steps": "ux,tech"},
    )

    detail = initiative_detail(world.ports, initiative.id)

    assert detail.owners == ["ux", "tech"]
    turns = [t for s in detail.workflows[0].steps for t in s.turns]
    assert turns and all((t.author, t.defects, t.owner) == ("operator", None, None) for t in turns)

    lone = ReadWorld()
    other = lone.initiative(sequence=sequence())
    lone.run(other)
    assert initiative_detail(lone.ports, other.id).owners == []


def test_ac3_a_turn_reads_queued_running_done_or_failed() -> None:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence())
    run = parked_on_ux(world, initiative)
    ux = world.steps.list_for_run(run.id)[2]
    world.turn(ux, 3, status="error", output_ref="agent exited 1", model="opus")
    world.turn(ux, 4, status="queued")
    world.turn(ux, 5, status="running")

    turns = next(
        s for s in initiative_detail(world.ports, initiative.id).workflows[0].steps if s.id == "ux"
    ).turns

    assert [(t.n, t.status, t.failure_reason, t.model) for t in turns] == [
        (1, "done", None, None),
        (2, "done", None, None),
        (3, "failed", "agent exited 1", "opus"),
        (4, "queued", None, None),
        (5, "running", None, None),
    ]


def merge_conflict_world() -> Any:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence())
    spec = world.run(initiative, status="done")
    world.row(spec, 1, status="done", **named("brief"))
    run = world.run(
        initiative,
        position=1,
        minutes=5,
        status="needs_you",
        park_kind="merge_conflict",
        park_path="steps[1]",
        park_reason="the merge stopped",
        park_seq=7,
    )
    row = world.row(run, 1, kind="git.merge", status="blocked", with_resolved={})
    world.turn(
        row,
        1,
        role="agent",
        status="blocked",
        output_ref="merge failed\nconflicted paths:\ninitiatives/snake/PRD.md\nREADME.md",
    )
    return world, initiative, run


def test_ac4_a_merge_conflict_stop() -> None:
    world, initiative, run = merge_conflict_world()

    steps = {s.id: s for s in initiative_detail(world.ports, initiative.id).workflows[0].steps}

    merge = steps["merge"]
    assert (merge.park_kind, merge.park_seq, merge.park_reason) == (
        "merge_conflict",
        run.park_seq,
        "the merge stopped",
    )
    assert (merge.token, merge.line, merge.run_id) == (
        "BLK",
        "conflict · 2 files · your turn",
        run.id,
    )
    assert merge.conflict_files == ["initiatives/snake/PRD.md", "README.md"]
    for other in (s for s in steps.values() if s.id != "merge"):
        assert other.conflict_files == []
        assert (other.park_seq, other.park_kind, other.park_reason) == (None, None, None)


def build_world(**overrides: Any) -> Any:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence())
    spec = world.run(initiative, status="done")
    world.row(spec, 1, status="done", **named("brief"))
    build = world.run(
        initiative,
        position=2,
        minutes=20,
        worktree_path=WORKTREE,
        inputs={"spec_folder": "specs/snake"},
        **overrides,
    )
    return world, initiative, build


def test_ac6_a_done_build_run_names_its_unmerged_pull_request() -> None:
    world, initiative, build = build_world(status="done", compare_urls=("https://x/pull/1",))

    line = initiative_detail(world.ports, initiative.id).workflows[1].line

    assert line == "Run done · pull request https://x/pull/1 not merged"
    assert build.status == "done"


def test_ac6_a_running_build_run_reads_progress_spend_and_budget() -> None:
    world, initiative, build = build_world(
        status="running", spend_usd=Decimal("1.5"), budget_usd=Decimal("20")
    )
    world.files["specs/snake/stories.yaml"] = "- {id: '1', title: One}\n"
    world.files["specs/snake/stories/1-one.md"] = "x"

    workflow = initiative_detail(world.ports, initiative.id).workflows[1]

    assert workflow.line.endswith("$1.50 / $20.00")
    assert [(f.path, f.run_id) for f in workflow.files] == [
        ("specs/snake/stories/1-one.md", build.id)
    ]


def test_a_workflow_without_history_ports_lists_no_files() -> None:
    world, initiative, _ = build_world(status="running")
    ports = world.ports.__class__(**{**world.ports.__dict__, "history": None})

    assert initiative_detail(ports, initiative.id).workflows[1].files == []


def test_ac7_two_rounds_of_a_step_are_two_sessions_and_two_runs() -> None:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence(), round=2)
    first = world.run(initiative, minutes=0, status="done")
    first_row = world.row(first, 1, status="done", **named("tech"))
    second = world.run(
        initiative,
        minutes=10,
        initiative_round=2,
        status="needs_you",
        senior_session=True,
        park_kind="conversation",
        park_path="steps[1]",
        park_seq=2,
    )
    second_row = world.row(second, 1, status="checkpoint", **named("tech"))
    one = world.session_start(first, first_row, 1, harness="claude", model="m1")
    two = world.session_start(second, second_row, 11, harness="codex", model="m2")

    detail = initiative_detail(world.ports, initiative.id)

    assert [(e.kind, e.id, e.round, e.state) for e in detail.sessions] == [
        ("run", first.id, 1, "done"),
        ("session", one.id, 1, "closed"),
        ("run", second.id, 2, "needs_you"),
        ("session", two.id, 2, "open"),
    ]
    tech = next(s for s in detail.workflows[0].steps if s.id == "tech")
    assert (tech.harness, tech.model) == ("codex", "m2")


def statuses_world(**initiative_overrides: Any) -> Any:
    world = ReadWorld()
    initiative = world.initiative(
        sequence=sequence(("a", "b", "c", "d", "e")), **initiative_overrides
    )
    run = world.run(initiative, status="running")
    world.row(run, 1, status="done", **named("a"))
    world.row(run, 2, status="running", **named("b"))
    world.row(run, 4, status="skipped", reason="skipped, forced · at 21:30", **named("d"))
    world.row(run, 5, status="error", **named("e"))
    return world, initiative


def read_steps(world: ReadWorld, initiative: Initiative) -> dict[str, Any]:
    detail = initiative_detail(world.ports, initiative.id)
    return {s.id: s for s in detail.workflows[0].steps}


def test_ac8_files_state_and_token_follow_the_step_status() -> None:
    world, initiative = statuses_world()

    steps = read_steps(world, initiative)

    got = {k: (steps[k].files_state, steps[k].token) for k in "abcde"}
    assert got == {
        "a": ("done", "DON"),
        "b": ("open", "RUN"),
        "c": ("to come", "QUE"),
        "d": ("skipped, forced", "SKP"),
        "e": ("failed", "ERR"),
    }


def test_ac8_a_cancelled_initiative_cancels_the_steps_that_were_to_run() -> None:
    world, initiative = statuses_world(cancelled_at=datetime(2026, 11, 24, tzinfo=UTC))

    steps = read_steps(world, initiative)

    assert (steps["b"].token, steps["c"].token, steps["a"].token) == ("CAN", "CAN", "DON")


def test_files_carry_their_run_time_and_changed_mark_since_the_last_view() -> None:
    prd = f"{FOLDER}/snake/PRD.md"
    ended = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)
    git = FakeGit(changes={WORKTREE: (Change(prd, "added"),)})
    world = ReadWorld(git=git)
    initiative = world.initiative(sequence=sequence(), last_opened_at=ended - timedelta(minutes=30))
    run = world.run(initiative, status="running", worktree_path=WORKTREE)
    row = world.row(run, 1, status="running", **named("brief"))
    world.turn(row, 1, start_sha="a", end_sha="b", ended_at=ended)

    steps = read_steps(world, initiative)

    (file,) = steps["brief"].files
    assert (file.path, file.run_id, file.time, file.changed) == (prd, run.id, ended, True)
