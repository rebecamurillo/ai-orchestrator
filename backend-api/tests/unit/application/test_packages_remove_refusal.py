"""`remove_package` refuses while an open initiative uses the package (story 1, epic 7; AD-39)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from orchestrator.application.use_cases import packages as use_cases
from orchestrator.domain.errors import Conflict
from tests.unit.application.package_fixtures import PATH
from tests.unit.application.package_world import World
from tests.unit.fakes.initiatives import FakeInitiativeRepository
from tests.unit.initiative_fixtures import AT, a_sequence, an_initiative


def installed() -> World:
    world = World()
    use_cases.install_package(
        world.ports, world.project.id, repository_id=world.hub.id, path=PATH, ref="main"
    )
    return world


def remove(world: World, *initiatives: object) -> None:
    ports = replace(world.ports, initiatives=FakeInitiativeRepository(list(initiatives)))  # type: ignore[arg-type]
    use_cases.remove_package(ports, world.project.id)


def mine(world: World, **kw: object):  # type: ignore[no-untyped-def]
    return an_initiative(project_id=world.project.id, sequence=a_sequence("acme"), **kw)


def test_one_open_initiative_refuses_and_deletes_nothing() -> None:
    world = installed()

    with pytest.raises(Conflict) as refused:
        remove(world, mine(world, slug="snake"))

    assert str(refused.value) == "refused: 1 open initiatives use this package — snake"
    assert world.packages.deletes == 0


def test_two_open_name_both_in_creation_order() -> None:
    world = installed()

    with pytest.raises(Conflict) as refused:
        remove(
            world,
            mine(world, slug="b", created_at=AT + timedelta(minutes=1)),
            mine(world, slug="a"),
        )

    assert str(refused.value) == "refused: 2 open initiatives use this package — a, b"


def test_cancelled_merged_and_other_package_do_not_refuse() -> None:
    world = installed()

    remove(
        world,
        mine(world, slug="a", cancelled_at=AT),
        mine(world, slug="b", pr_merged_at=AT),
        an_initiative(project_id=world.project.id, slug="c", sequence=a_sequence("other")),
    )

    assert world.packages.deletes == 1


def test_without_the_port_the_delete_proceeds() -> None:
    world = installed()

    use_cases.remove_package(world.ports, world.project.id)

    assert world.packages.deletes == 1
