"""The method registry (story 1): `register` adds a key and refuses a bad or repeated one."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.metrics import methods
from orchestrator.application.metrics.methods import REGISTRY, register


@pytest.fixture(autouse=True)
def restore_registry() -> Iterator[None]:
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_the_registry_holds_nothing_in_this_story() -> None:
    assert methods.REGISTRY == {}


def test_register_adds_the_function_under_its_key() -> None:
    @register("cost.gateway@1")
    def compute() -> int:
        return 1

    assert REGISTRY["cost.gateway@1"] is compute
    assert compute() == 1


def test_register_refuses_a_duplicate_key() -> None:
    register("cost.gateway@1")(lambda: 1)
    with pytest.raises(ValueError, match=r"cost\.gateway@1"):
        register("cost.gateway@1")(lambda: 2)


@pytest.mark.parametrize("key", ["cost.gateway", "cost@1", "Cost.gateway@1", "cost.gateway@0", "x"])
def test_register_refuses_a_malformed_key(key: str) -> None:
    with pytest.raises(ValueError, match="malformed"):
        register(key)
