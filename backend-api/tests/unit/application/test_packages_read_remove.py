"""`get_package`, `hub_of` and `remove_package` (story 3 of epic 6, AC8)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases import packages as use_cases
from orchestrator.domain.errors import NotFound
from tests.unit.application.package_fixtures import PATH
from tests.unit.application.package_world import World


def installed() -> World:
    world = World()
    use_cases.install_package(
        world.ports, world.project.id, repository_id=world.hub.id, path=PATH, ref="main"
    )
    return world


def test_get_package_returns_the_record_and_its_hub() -> None:
    world = installed()

    record = use_cases.get_package(world.ports, world.project.id)

    assert record.name == "acme"
    assert use_cases.hub_of(world.ports, record) == world.hub


def test_none_installed_is_not_found() -> None:
    world = World()
    with pytest.raises(NotFound, match="no package installed"):
        use_cases.get_package(world.ports, world.project.id)
    with pytest.raises(NotFound, match="no package installed"):
        use_cases.remove_package(world.ports, world.project.id)


def test_a_record_whose_hub_is_gone_is_not_found() -> None:
    world = installed()
    record = use_cases.get_package(world.ports, world.project.id)
    del world.repositories.repositories[world.hub.id]
    with pytest.raises(NotFound):
        use_cases.hub_of(world.ports, record)


def test_remove_deletes_the_record_and_no_template_version() -> None:
    world = installed()
    versions = dict(world.templates.versions)
    commits = world.uow.calls.count("commit")

    use_cases.remove_package(world.ports, world.project.id)

    assert world.packages.get(world.project.id) is None
    assert world.templates.versions == versions
    assert world.uow.calls.count("commit") == commits + 1
