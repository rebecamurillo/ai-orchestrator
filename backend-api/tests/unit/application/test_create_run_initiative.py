"""`create_run`'s initiative key and `before_commit` (story 1, epic 7; AD-36)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.use_cases.create_run import create_run
from orchestrator.domain.entities.initiative import InitiativeKey
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_use_case import Harness, base_request

WAITING = "already created for this initiative step"


def harness() -> Harness:
    h = Harness(git=fixtures.repo_init_git())
    h.ports = replace(h.ports, initiative_runs=h.runs)
    return h


def test_the_new_run_carries_the_three_keys() -> None:
    h = harness()
    key = InitiativeKey(initiative_id=new_id(), round=1, position=0)

    result = h.create(base_request(initiative=key))

    stored = h.runs.get(result.run.id)
    assert stored is not None
    assert (stored.initiative_id, stored.initiative_round, stored.initiative_position) == (
        key.initiative_id,
        1,
        0,
    )


def test_the_same_key_returns_the_first_run_and_writes_nothing() -> None:
    h = harness()
    key = InitiativeKey(initiative_id=new_id(), round=1, position=0)
    first = h.create(base_request(initiative=key))
    runs, steps = len(h.runs.runs), len(h.steps.steps)
    commits, enqueues = h.uow.calls.count("commit"), len(h.engine.calls)
    again = h.create(base_request(initiative=key))

    assert again.run == first.run
    assert (again.starts_now, again.waiting) == (False, WAITING)
    assert (len(h.runs.runs), len(h.steps.steps)) == (runs, steps)
    assert h.uow.calls.count("commit") == commits
    assert len(h.engine.calls) == enqueues


def test_a_run_without_a_key_has_none() -> None:
    h = harness()

    run = h.create(base_request()).run

    assert (run.initiative_id, run.initiative_round, run.initiative_position) == (None,) * 3


def test_a_key_without_the_reads_port_is_a_wiring_error() -> None:
    h = Harness(git=fixtures.repo_init_git())

    with pytest.raises(ValueError, match="initiative_runs"):
        h.create(
            base_request(initiative=InitiativeKey(initiative_id=new_id(), round=1, position=0))
        )


@pytest.mark.parametrize("save", [False, True])
def test_before_commit_runs_once_between_the_adds_and_the_first_commit(save: bool) -> None:
    h = harness()
    seen: list[tuple[int, int, int]] = []

    def hook() -> None:
        seen.append((len(h.runs.runs), len(h.steps.steps), h.uow.calls.count("commit")))

    with h.uow:
        create_run(h.ports, base_request(save=save), before_commit=hook)

    assert len(seen) == 1
    runs, steps, commits = seen[0]
    assert (runs, commits) == (1, 0)
    assert steps > 0


def test_a_raising_before_commit_rolls_everything_back() -> None:
    h = harness()

    def hook() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError), h.uow:
        create_run(h.ports, base_request(), before_commit=hook)

    assert h.uow.committed is False
    assert h.uow.rolled_back is True
    assert h.engine.calls == []
