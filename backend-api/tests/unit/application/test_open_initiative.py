"""`open_initiative`: her last view, the one write of the page's read (story 6, epic 7; AC5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.application.use_cases.open_initiative import (
    OpenInitiativePorts,
    open_initiative,
)
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import NOW, ReadWorld


class RecordingUow:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def ports(world: ReadWorld) -> tuple[OpenInitiativePorts, RecordingUow]:
    uow = RecordingUow()
    return OpenInitiativePorts(world.initiatives, uow, world.clock), uow  # type: ignore[arg-type]


def test_it_stamps_now_and_answers_the_value_it_found() -> None:
    world = ReadWorld()
    before = NOW - timedelta(hours=1)
    initiative = world.initiative(last_opened_at=before)
    wired, uow = ports(world)

    prior = open_initiative(wired, initiative.id)

    stored = world.initiatives.get(initiative.id)
    assert prior.at == before
    assert stored is not None and stored.last_opened_at == NOW
    assert uow.commits == 1


def test_it_writes_only_last_opened_at_and_no_run() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    run = world.run(initiative)
    wired, _ = ports(world)

    prior = open_initiative(wired, initiative.id)

    stored = world.initiatives.get(initiative.id)
    assert prior.at is None
    assert stored is not None
    assert stored.model_copy(update={"last_opened_at": None}) == initiative
    assert world.runs.get(run.id) == run


def test_it_takes_the_initiative_lock_first() -> None:
    world = ReadWorld()
    initiative = world.initiative()
    wired, _ = ports(world)

    open_initiative(wired, initiative.id)

    names = [call[0] for call in world.initiatives.calls]
    assert names.index("get_for_update") < names.index("update")


def test_an_unknown_initiative_is_not_found_and_nothing_commits() -> None:
    world = ReadWorld()
    wired, uow = ports(world)

    with pytest.raises(NotFound):
        open_initiative(wired, new_id())

    assert uow.commits == 0
