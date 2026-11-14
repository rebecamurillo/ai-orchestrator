"""The method registry (story 1): `register` adds a key and refuses a bad or repeated one."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.metrics import methods
from orchestrator.application.metrics.methods import METHOD_KEY, REGISTRY, register


@pytest.fixture(autouse=True)
def restore_registry() -> Iterator[None]:
    saved = dict(REGISTRY)
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


# Revised by epic 2 story 4 (2026-11-13): importing the package now registers every catalogued
# part A method, so the epic 1 placeholder "the registry is empty" no longer holds. The full
# equality with the catalogue is asserted in
# tests/unit/infrastructure/test_metrics_methods_registered.py.
def test_the_registry_holds_a_callable_for_every_registered_key() -> None:
    assert methods.REGISTRY
    assert all(callable(method) for method in methods.REGISTRY.values())
    assert all(METHOD_KEY.match(key) and key.endswith("@1") for key in methods.REGISTRY)


def test_register_adds_the_function_under_its_key() -> None:
    @register("cost.gateway@2")
    def compute() -> int:
        return 1

    assert REGISTRY["cost.gateway@2"] is compute
    assert compute() == 1


def test_register_refuses_a_duplicate_key() -> None:
    register("cost.gateway@2")(lambda: 1)
    with pytest.raises(ValueError, match=r"cost\.gateway@2"):
        register("cost.gateway@2")(lambda: 2)


@pytest.mark.parametrize("key", ["cost.gateway", "cost@1", "Cost.gateway@1", "cost.gateway@0", "x"])
def test_register_refuses_a_malformed_key(key: str) -> None:
    with pytest.raises(ValueError, match="malformed"):
        register(key)
