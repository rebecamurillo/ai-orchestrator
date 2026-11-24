"""The package port and the widened template port are satisfied by their fakes (story 3, epic 6)."""

from __future__ import annotations

from orchestrator.domain.ports.packages import ProjectPackageRepository
from orchestrator.domain.ports.templates import TemplateVersionRepository
from tests.unit.fakes.packages import FakeProjectPackageRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository


def test_the_fakes_satisfy_the_ports() -> None:
    assert isinstance(FakeProjectPackageRepository(), ProjectPackageRepository)
    assert isinstance(FakeTemplateVersionRepository(), TemplateVersionRepository)
