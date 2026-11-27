"""`_Guarded.get_by_package_sha` forwards and wraps a raise as `PortRaised` (story 3, epic 6)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.template_judge import PortRaised, _Guarded
from tests.unit.fakes.templates import FakeTemplateVersionRepository


class Raising(FakeTemplateVersionRepository):
    def get_by_package_sha(self, name: str, sha: str) -> None:  # type: ignore[override]
        raise RuntimeError("down")


def test_it_forwards() -> None:
    assert _Guarded(FakeTemplateVersionRepository()).get_by_package_sha("n", "s") is None


def test_a_raise_becomes_port_raised() -> None:
    with pytest.raises(PortRaised):
        _Guarded(Raising()).get_by_package_sha("n", "s")
