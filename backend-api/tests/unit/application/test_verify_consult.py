"""`use_cases/verify_consult.py` (story 1-6, spine AD-8/AD-9/AD-22, 2026-11-02): the offer made
when a `run` row's redispatch bound is used up and its `on_fail` declares a consult, driven
through `apply_step_result` the way the walker drives it.

The consult attempt belongs to the redispatch *target*: it is the row with the harness, the
session history and the story's tree. The entry is marked on it, so a second `verify_failed`
never consults again, while the stop itself parks on the verify row. The writer touches rows
only: the sweep and the snapshot are the executor's (`test_verify_consult_run.py`), and a
review ruling (2026-11-02) keeps git out of the writer's unit of work."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases import verify_consult
from orchestrator.application.use_cases.apply_redispatch import VERIFY_FAILED
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import Park
from tests.unit.application.verify_consult_fixtures import (
    BLOCK,
    BUILD,
    MAX,
    QUESTION,
    VERIFY,
    a_failed_verify,
    a_verify_world,
)
from tests.unit.application.writer_fixtures import World, an_attempt
from tests.unit.fakes.git import FakeGit


def fail_verify(world: World) -> None:
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
            "declared": BLOCK,
            "park_path": VERIFY,
        }
    }


def test_the_run_stays_running_and_the_verify_row_keeps_its_error() -> None:
    world = a_verify_world()

    fail_verify(world)

    assert world.stored_run().status == "running"
    assert world.status_of(VERIFY) == "error"


def test_the_writer_runs_no_git_and_records_nothing_yet() -> None:
    git = FakeGit(status=[" M src/a.py", ""])
    world = a_verify_world(git=git)

    fail_verify(world)

    assert git.calls == []
    assert world.records() == []


def test_the_offer_needs_neither_a_git_port_nor_a_worktree() -> None:
    world = a_verify_world(worktree=None)
    world.ports = replace(world.ports, git=None)

    fail_verify(world)

    assert world.row(BUILD).consults["verify_failed"]["state"] == "due"


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
    ],
    ids=["no consult declared", "already escalated", "already answered"],
)
def test_every_other_stop_parks_as_it_always_did(setup: dict[str, Any]) -> None:
    world = a_verify_world(**setup)
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


def test_offer_answers_the_exhausted_park_unchanged_when_it_offers_nothing() -> None:
    world = a_verify_world(block=None)
    exhausted = Park(kind="verify_failed", reason=QUESTION, path=VERIFY)

    answer = verify_consult.offer(world.ports, world.row(VERIFY), world.row(BUILD), exhausted)

    assert answer == (exhausted, False)
