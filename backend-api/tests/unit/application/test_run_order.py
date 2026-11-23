"""`build_run_order` — the plan's own order of deterministic steps around each agent
(story 4, AD-40 "The order")."""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.run_order import STEP_TOKENS, build_run_order
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id

RUN_ID = UUID("01960000-0000-7000-9000-0000000000aa")


def row(path: str, seq: int, kind: str = "shell", status: str = "planned") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=RUN_ID,
        seq=seq,
        path=path,
        label=path.rsplit(".", maxsplit=1)[-1],
        kind=kind,
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


def story(prefix: str, start: int) -> list[StepRun]:
    names = ["sync", "build", "verify", "commit", "push"]
    return [
        row(f"{prefix}.{name}", start + i, "agent" if name == "build" else "shell")
        for i, name in enumerate(names)
    ]


def test_story_frame_reads_before_agent_after() -> None:
    rows = story("stories[0]", 1)
    rows[1] = row("stories[0].build", 2, "agent", "done")

    (entry,) = build_run_order(rows)

    assert entry.frame == "stories[0]"
    assert [r.path for r in entry.rows] == [r.path for r in rows]
    assert [r.phase for r in entry.rows] == ["BEFORE", "AGENT", "AFTER", "AFTER", "AFTER"]
    assert entry.rows[1].token == STEP_TOKENS["done"]
    assert entry.rows[0].token == STEP_TOKENS["planned"]


def test_epic_frame_lists_only_its_own_rows() -> None:
    rows = [
        row("epics[0].branch", 1),
        row("epics[0].setup", 2),
        row("epics[0].baseline", 3),
        *story("epics[0].stories[0]", 4),
        row("epics[0].commit-e2e", 9),
        row("epics[0].e2e", 10),
        row("epics[0].push", 11),
    ]

    entries = build_run_order(rows)

    assert [e.frame for e in entries] == ["epics[0]", "epics[0].stories[0]"]
    epic = entries[0]
    assert [r.phase for r in epic.rows] == ["BEFORE"] * 3 + ["AFTER"] * 3
    assert all(".stories[" not in r.path for r in epic.rows)
    assert [r.seq for r in epic.rows] == [1, 2, 3, 9, 10, 11]


def test_frame_without_agent_is_omitted_and_agentless_plan_is_empty() -> None:
    rows = [*story("stories[0]", 1), row("stories[1].sync", 6), row("stories[1].push", 7)]
    assert [e.frame for e in build_run_order(rows)] == ["stories[0]"]
    assert build_run_order([row("a", 1), row("b", 2)]) == ()


def test_root_frame_with_loops_splits_around_first_nested_row() -> None:
    rows = [
        row("plan.check", 1),
        *story("stories[0]", 2),
        row("finish", 7),
    ]

    entries = build_run_order(rows)

    assert entries[0].frame == "root"
    assert [(r.path, r.phase) for r in entries[0].rows] == [
        ("plan.check", "BEFORE"),
        ("finish", "AFTER"),
    ]
    assert entries[1].frame == "stories[0]"


def test_loop_free_root_uses_the_own_agent_rule_with_several_agents() -> None:
    rows = [
        row("sync", 1),
        row("a", 2, "agent"),
        row("mid", 3),
        row("b", 4, "agent"),
        row("end", 5),
    ]

    (entry,) = build_run_order(rows)

    assert entry.frame == "root"
    assert [r.phase for r in entry.rows] == ["BEFORE", "AGENT", "AFTER", "AGENT", "AFTER"]


def test_frames_follow_plan_order_epic_before_its_first_story() -> None:
    rows = [*story("epics[1].stories[0]", 1), *story("epics[0].stories[0]", 6)]
    rows.insert(0, row("epics[1].branch", 0))

    frames = [e.frame for e in build_run_order(rows)]

    assert frames == ["epics[1]", "epics[1].stories[0]", "epics[0].stories[0]"]
