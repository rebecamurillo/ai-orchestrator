"""`GatewayModels` and `GatewayUnreachable` (epic 2 story 4, 2026-11-12)."""

from __future__ import annotations

import pytest

from orchestrator.domain.errors import DomainError
from orchestrator.domain.ports.gateway import GatewayModels, GatewayUnreachable
from tests.unit.fakes.gateway import FakeGatewayModels


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeGatewayModels(), GatewayModels)


def test_unreachable_is_a_domain_error() -> None:
    assert issubclass(GatewayUnreachable, DomainError)


def test_the_fake_answers_its_list_and_counts() -> None:
    fake = FakeGatewayModels(("a", "b"))
    assert fake.models() == ("a", "b")
    assert fake.calls == 1


def test_the_fake_raises_its_scripted_error() -> None:
    fake = FakeGatewayModels(error=GatewayUnreachable("down"))
    with pytest.raises(GatewayUnreachable):
        fake.models()
