"""`use_cases/verify_consult.py` (story 1-6, spine AD-9/AD-22, 2026-11-02): the offer made when
a `run` row's redispatch bound is used up and its `on_fail` declares a consult, driven through
`apply_step_result` the way the walker drives it.

The consult attempt belongs to the redispatch *target*: it is the row with the harness, the
session history and the story's tree. The entry is marked on it, so a second `verify_failed`
never consults again, while the stop itself parks on the verify row."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.use_cases import verify_consult
from orchestrator.application.use_cases.apply_redispatch import VERIFY_FAILED
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.ports.git import GitError
from tests.unit.application.verify_consult_fixtures import (
    BLOCK,
    BUILD,
    HEAD,
    MAX,
    QUESTION,
    VERIFY,
    WORKTREE,
    a_failed_verify,
    a_verify_world,
    clean_git,
)
from tests.unit.application.writer_fixtures import World, an_attempt
from tests.unit.fakes.git import FakeGit


def fail_verify(world: World, built: int | None = 3) -> None:
    """The verify row fails; `built` is the newest `agent` attempt on the build row, if any."""
    if built is not None:
        an_attempt(world, BUILD, n=built, status="done")
    an_attempt(world, VERIFY, n=1)
    apply_step_result(world.ports, world.run.id, world.row(VERIFY).seq, a_failed_verify())


def parked_reason(world: World) -> str | None:
    return world.stored_run().park_reason


# ── the offer ────────────────────────────────────────────────────────────────


def test_a_used_up_bound_offers_the_consult_to_the_target_row() -> None:
    world = a_verify_world()

    fail_verify(world)

    build = world.row(BUILD)
    assert build.status == "queued"
    assert build.redispatch_count == MAX
    assert build.consults == {
        "verify_failed": {
            "state": "due",
            "question": QUESTION,
            "snapshot": {"tree": {"head": HEAD, "status": ""}},
            "declared": BLOCK,
            "park_path": VERIFY,
        }
    }


def test_the_run_stays_running_and_the_verify_row_keeps_its_error() -> None:
    world = a_verify_world()

    fail_verify(world)

    assert world.stored_run().status == "running"
    assert world.status_of(VERIFY) == "error"


def test_the_offer_is_recorded_as_a_machine_consult_on_the_target() -> None:
    world = a_verify_world()

    fail_verify(world)

    [line] = world.records()
    assert (line.event, line.actor, line.path, line.attempt_n) == ("consult", "machine", BUILD, 3)
    assert (line.text, line.payload) == (QUESTION, {"kind": "verify_failed"})


def test_a_target_that_never_ran_an_agent_attempt_is_still_consulted() -> None:
    git = FakeGit(status=[" M src/a.py", ""], head_sha=[HEAD])
    world = a_verify_world(git=git)

    fail_verify(world, built=None)

    [line] = world.records()
    assert line.attempt_n is None
    assert git.called("commit") == [(Path(WORKTREE), "wip: story 1 attempt 0 (consult)")]


def test_the_trees_are_swept_into_a_consult_wip_commit_first() -> None:
    git = FakeGit(status=[" M src/a.py", ""], head_sha=[HEAD])
    world = a_verify_world(git=git)

    fail_verify(world)

    assert git.called("commit") == [
        (Path(WORKTREE), "wip: story 1 attempt 3 (consult)"),
    ]


def test_a_workdir_target_snapshots_both_trees() -> None:
    member = f"{WORKTREE}/repos/member"
    git = clean_git(
        heads={member: ["b" * 40], WORKTREE: [HEAD]}, statuses={member: "", WORKTREE: ""}
    )
    world = a_verify_world(git=git, workdir="repos/member")

    fail_verify(world)

    snapshot = world.row(BUILD).consults["verify_failed"]["snapshot"]
    assert snapshot == {
        "tree": {"head": "b" * 40, "status": ""},
        "root": {"head": HEAD, "status": ""},
    }


# ── what is not offered ──────────────────────────────────────────────────────


def test_under_the_bound_the_redispatch_is_the_templates_own_and_no_consult_is_due() -> None:
    world = a_verify_world(count=MAX - 1)

    fail_verify(world)

    build = world.row(BUILD)
    assert (build.status, build.redispatch_count, build.consults) == ("queued", MAX, {})
    assert world.events() == ["redispatch"]


@pytest.mark.parametrize(
    "setup",
    [
        {"block": None},
        {"consults": {"verify_failed": {"state": "escalate"}}},
        {"consults": {"verify_failed": {"state": "answer", "answered_by": 3}}},
        {"git": None},
        {"worktree": None},
    ],
    ids=["no consult declared", "already escalated", "already answered", "no git", "no worktree"],
)
def test_every_other_stop_parks_as_it_always_did(setup: dict[str, Any]) -> None:
    world = a_verify_world(**{key: value for key, value in setup.items() if key != "git"})
    if "git" in setup:
        world.ports = replace(world.ports, git=None)
    before = dict(world.row(BUILD).consults)

    fail_verify(world)

    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_path) == ("needs_you", "verify_failed", VERIFY)
    assert run.park_reason == VERIFY_FAILED.format(n=MAX + 1)
    assert world.row(BUILD).consults == before
    assert world.events() == ["verify_failed"]


def test_the_park_counts_a_diagnosed_redispatch_too() -> None:
    entry = {"state": "answer", "answered_by": 3}
    world = a_verify_world(count=MAX + 1, consults={"verify_failed": entry})

    fail_verify(world)

    assert parked_reason(world) == VERIFY_FAILED.format(n=MAX + 2)


def test_a_skipped_target_is_never_consulted() -> None:
    world = a_verify_world(build="skipped")

    fail_verify(world)

    assert world.row(BUILD).consults == {}
    assert world.stored_run().park_kind == "verify_failed"


def test_a_sweep_that_git_refuses_parks_with_git_s_words() -> None:
    git = FakeGit(status=[GitError(command="git add", exit_code=128, output="index locked")])
    world = a_verify_world(git=git)

    fail_verify(world)

    run = world.stored_run()
    assert run.park_kind == "verify_failed"
    assert run.park_reason == f"{VERIFY_FAILED.format(n=MAX + 1)} · consult failed: index locked"
    assert world.row(BUILD).consults == {}


def test_a_sweep_error_without_output_names_the_error() -> None:
    git = FakeGit(status=[GitError(command="git status", exit_code=1, output="")])
    world = a_verify_world(git=git)

    fail_verify(world)

    assert "consult failed: git status exited 1" in (parked_reason(world) or "")


def test_the_offer_is_one_function_of_the_exhausted_park() -> None:
    assert verify_consult.KIND == "verify_failed"
