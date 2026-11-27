"""The shared initiative fakes mirror the two partial unique indexes (AD-36)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.domain.entities.initiative import InitiativeKey
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.initiative_runs import InitiativeRunReads
from orchestrator.domain.ports.initiatives import (
    InitiativeAdvanceRepository,
    InitiativeRepository,
)
from tests.unit.fakes.initiatives import FakeInitiativeAdvanceRepository, FakeInitiativeRepository
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.initiative_fixtures import AT, a_run, a_sequence, an_initiative


def test_round_trip() -> None:
    repo = FakeInitiativeRepository()
    initiative = an_initiative()
    repo.add(initiative)

    assert repo.get(initiative.id) == initiative
    assert repo.get_for_update(initiative.id) == initiative
    assert repo.get(new_id()) is None
    assert repo.get_for_update(new_id()) is None
    assert [name for name, _ in repo.calls] == [
        "add",
        "get",
        "get_for_update",
        "get",
        "get_for_update",
    ]


def test_duplicate_id_and_second_open_slug_are_refused() -> None:
    repo = FakeInitiativeRepository()
    first = an_initiative()
    repo.add(first)

    with pytest.raises(ValueError, match="already stored"):
        repo.add(first)
    with pytest.raises(ValueError, match="open initiative"):
        repo.add(an_initiative(repository_id=first.repository_id))


def test_same_slug_on_another_hub_is_fine() -> None:
    repo = FakeInitiativeRepository([an_initiative(), an_initiative()])

    assert len(repo.list()) == 2  # noqa: PLR2004


def test_a_cancelled_initiative_frees_the_slug() -> None:
    repo = FakeInitiativeRepository()
    first = an_initiative()
    repo.add(first)
    repo.update(first.model_copy(update={"cancelled_at": AT}))
    second = an_initiative(repository_id=first.repository_id, created_at=AT + timedelta(minutes=1))
    repo.add(second)

    assert repo.get_open_by_slug(first.repository_id, "snake") == second
    assert [i.id for i in repo.list_by_slug(first.repository_id, "snake")] == [first.id, second.id]
    assert repo.get_open_by_slug(first.repository_id, "other") is None
    # a cancelled row stays cancelled even when stored beside an open one
    repo.update(first.model_copy(update={"cancelled_at": AT, "name": "renamed"}))


def test_reopening_a_cancelled_slug_held_by_another_is_refused() -> None:
    repo = FakeInitiativeRepository()
    first = an_initiative(cancelled_at=AT)
    repo.add(first)
    repo.add(an_initiative(repository_id=first.repository_id))

    with pytest.raises(ValueError, match="open initiative"):
        repo.update(first.model_copy(update={"cancelled_at": None}))


def test_update_refuses_an_unknown_id() -> None:
    with pytest.raises(ValueError, match="no initiative"):
        FakeInitiativeRepository().update(an_initiative())


def test_list_open_for_package() -> None:
    project = new_id()
    mine = an_initiative(project_id=project, slug="a")
    later = an_initiative(project_id=project, slug="b", created_at=AT + timedelta(minutes=1))
    repo = FakeInitiativeRepository(
        [
            later,
            mine,
            an_initiative(project_id=project, slug="c", cancelled_at=AT),
            an_initiative(project_id=project, slug="d", pr_merged_at=AT),
            an_initiative(project_id=project, slug="e", sequence=a_sequence("other")),
            an_initiative(slug="f"),
        ]
    )

    assert [i.slug for i in repo.list_open_for_package(project, "p")] == ["a", "b"]


def test_list_filters_by_project_newest_first() -> None:
    project = new_id()
    old = an_initiative(project_id=project, slug="a")
    new = an_initiative(project_id=project, slug="b", created_at=AT + timedelta(minutes=1))
    repo = FakeInitiativeRepository([old, new, an_initiative()])

    assert [i.slug for i in repo.list(project_id=project)] == ["b", "a"]
    assert len(repo.list()) == 3  # noqa: PLR2004


def test_advances_are_unique_per_key_and_listed_in_order() -> None:
    repo = FakeInitiativeAdvanceRepository()
    initiative_id, run_id = new_id(), new_id()

    def advance(position: int, **kw: object) -> InitiativeAdvance:
        return InitiativeAdvance(
            id=new_id(),
            initiative_id=initiative_id,
            from_run_id=run_id,
            round=1,
            position=position,
            **kw,  # type: ignore[arg-type]
        )

    second, first = advance(1), advance(0, consumed_at=AT)
    repo.add(second)
    repo.add(first)
    other = InitiativeAdvance(
        id=new_id(), initiative_id=new_id(), from_run_id=run_id, round=1, position=0
    )
    repo.add(other)

    assert [a.position for a in repo.list_for_initiative(initiative_id)] == [0, 1]
    assert repo.list_unconsumed() == [other, second]
    with pytest.raises(ValueError, match="already stored"):
        repo.add(advance(1))
    with pytest.raises(ValueError, match="already stored"):
        repo.add(second)


def test_the_run_fake_refuses_a_second_run_at_one_key_and_reads_by_key() -> None:
    initiative_id = new_id()
    key = InitiativeKey(initiative_id=initiative_id, round=1, position=0)
    first = a_run(initiative_id=initiative_id, initiative_round=1, initiative_position=0)
    later = a_run(minutes=5, initiative_id=initiative_id, initiative_round=1, initiative_position=1)
    runs = FakeRunRepository([later, first, a_run()])

    assert runs.get_by_initiative_key(key) == first
    assert runs.get_by_initiative_key(key.model_copy(update={"round": 2})) is None
    assert runs.list_for_initiative(initiative_id) == [first, later]
    assert runs.list_for_initiative(new_id()) == []
    with pytest.raises(ValueError, match="initiative key"):
        runs.add(a_run(initiative_id=initiative_id, initiative_round=1, initiative_position=0))
    runs.add(a_run())  # runs without keys never collide


def test_the_fakes_satisfy_their_ports() -> None:
    assert isinstance(FakeInitiativeRepository(), InitiativeRepository)
    assert isinstance(FakeInitiativeAdvanceRepository(), InitiativeAdvanceRepository)
    assert isinstance(FakeRunRepository(), InitiativeRunReads)
