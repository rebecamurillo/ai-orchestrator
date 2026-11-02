"""A senior's `approved_files` at a `blocked` consult (story 1-5, spine AD-17/AD-22, hard rule 1
as amended 2026-11-02): only frozen test files of the frame's anchor set, never a document,
spelled `{workdir}/…` on a hub row. One bad path fails the whole consult."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.values import Consult, StepResult
from tests.unit.application.consult_fixtures import (
    DECISION,
    QUESTION,
    SNAP_HEAD,
    World,
    a_consult_world,
    consulting,
    due_entry,
    planned,
)
from tests.unit.application.steps.agent_fixtures import ROW_PATH, SPEC_FOLDER, WORKTREE
from tests.unit.fakes.git import FakeGit

ANCHORS = frozenset({"tests/a.py", "tests/b.py", f"{SPEC_FOLDER}/SPEC.md"})
MEMBER = f"{WORKTREE}/repos/member"


def approving(files: str, status: str = "answer", reason: str = "") -> str:
    said = f"reason: {reason}\n" if reason else ""
    head = f"status: {status}\napproved_files: {files}\n{said}"
    return f"---\n{head}---\n\nRevise tests/a.py's status assertion.\n"


def with_anchors(world: World, anchors: frozenset[str] = ANCHORS) -> World:
    environment = world.ctx.ports.run_env
    assert environment is not None
    ports = replace(world.ctx.ports, run_env=replace(environment, anchors=anchors))
    return replace(world, ctx=replace(world.ctx, ports=ports))


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def fails_closed(world: World, why: str) -> None:
    result = run(world)

    reason = f"{QUESTION} · consult failed: {why}"
    assert result.status == "blocked"
    assert result.reason == reason
    assert result.park is not None
    assert (result.park.kind, result.park.reason, result.park.path) == ("blocked", reason, ROW_PATH)
    assert result.consult == Consult(kind="blocked", question=QUESTION, outcome="failed")


def test_an_answer_carries_the_frozen_files_it_approves_and_its_reason() -> None:
    world = with_anchors(
        a_consult_world(decision=approving("[tests/a.py, tests/b.py]", reason="story says so"))
    )

    result = run(world)

    assert result.park is None
    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert result.consult.approved_files == ("tests/a.py", "tests/b.py")
    assert result.consult.reason == "story says so"


def test_an_answer_with_no_files_carries_none() -> None:
    world = with_anchors(a_consult_world(decision="---\nstatus: answer\n---\n\nGo on.\n"))

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert result.consult.approved_files == ()


@pytest.mark.parametrize("path", [f"{SPEC_FOLDER}/SPEC.md", "AGENTS.md", "tests/AGENTS.md"])
def test_a_document_is_never_approved(path: str) -> None:
    world = with_anchors(a_consult_world(decision=approving(f"[{path}]")))

    fails_closed(world, f"approved file is an anchor: {path}")


def test_a_file_that_is_not_frozen_is_never_approved() -> None:
    world = with_anchors(a_consult_world(decision=approving("[tests/new.py]")))

    fails_closed(world, "approved file is not a frozen test file: tests/new.py")


def test_one_bad_path_fails_the_whole_consult() -> None:
    world = with_anchors(a_consult_world(decision=approving("[tests/a.py, tests/new.py]")))

    fails_closed(world, "approved file is not a frozen test file: tests/new.py")


@pytest.mark.parametrize("files", ["tests/a.py", "[tests/a.py, 7]", "{tests/a.py: 1}"])
def test_a_list_that_is_not_strings_is_no_readable_decision(files: str) -> None:
    world = with_anchors(a_consult_world(decision=approving(files)))

    fails_closed(world, "no readable decision")


def test_an_escalation_naming_files_parks_and_carries_none() -> None:
    world = with_anchors(
        a_consult_world(decision=approving("[tests/a.py]", status="escalate", reason="unsure"))
    )

    result = run(world)

    assert result.status == "blocked"
    assert result.reason == f"{QUESTION} · senior: unsure"
    assert result.consult == Consult(kind="blocked", question=QUESTION, outcome="escalate")


# ── a hub row ────────────────────────────────────────────────────────────────


def a_hub_world(decision: str) -> World:
    git = FakeGit(
        heads={MEMBER: [SNAP_HEAD], WORKTREE: ["9" * 40]},
        statuses={MEMBER: "", WORKTREE: ""},
    )
    entry = due_entry(
        snapshot={
            "tree": {"head": SNAP_HEAD, "status": ""},
            "root": {"head": "9" * 40, "status": ""},
        }
    )
    world = a_consult_world(
        decision=decision,
        git=git,
        entry=entry,
        with_resolved=consulting(workdir="repos/member"),
    )
    return with_anchors(world, frozenset({"repos/member/tests/a.py", "tests/a.py"}))


def test_a_hub_row_approves_the_workdir_spelling() -> None:
    result = run(a_hub_world(approving("[repos/member/tests/a.py]", reason="AC 2")))

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert result.consult.approved_files == ("repos/member/tests/a.py",)


def test_a_hub_row_refuses_a_path_outside_its_workdir_even_when_frozen() -> None:
    fails_closed(
        a_hub_world(approving("[tests/a.py]")),
        "approved file is not a frozen test file: tests/a.py",
    )


# ── the planted decision file ────────────────────────────────────────────────


def test_a_decision_placed_before_dispatch_is_removed_and_reads_as_no_decision() -> None:
    """The old fixture shape (a decision present before `run`) is now the planted case."""
    world = with_anchors(a_consult_world())
    world.workspace.write(DECISION, approving("[tests/a.py]"))
    seen: list[str | None] = []
    world.harness.on_wait = lambda: seen.append(world.workspace.read(DECISION))

    fails_closed(world, "no readable decision")

    assert seen == [None]
    assert world.workspace.read(DECISION) is None


# ── a verify_failed consult approves nothing ─────────────────────────────────


def test_a_verify_failed_answer_carries_no_files() -> None:
    entry: dict[str, Any] = {
        **due_entry(question="verify failed 3/3"),
        "declared": planned(on=["verify_failed"]),
        "park_path": "stories[0].verify",
    }
    world = with_anchors(a_consult_world(decision=approving("[tests/a.py]")))
    row = world.row.model_copy(update={"consults": {"verify_failed": entry}})
    world = replace(world, row=row, ctx=replace(world.ctx, row=row))

    result = run(world)

    assert result.consult is not None
    assert result.consult.outcome == "answer"
    assert result.consult.approved_files == ()
