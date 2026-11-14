"""The shipped `code.test_first_order` entry: its fields and the three limits verbatim (epic 6
story 3, AC9). The entry is a per-story log signal, so it is not held to the tool analyses'
shape in `test_metrics_catalogue_code.py`."""

from __future__ import annotations

from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue

#: Research A.5, "Limits to print with any TDD signal", lines 1-3, word for word.
LIMITS = (
    "1. Test-first order did not predict quality in humans (K45).",
    "2. When the workflow template itself instructs the agent to write tests first, the signal\n"
    "   measures **compliance with the template**, not the model's own habit. Runs compared on it\n"
    "   must use the same instruction.",
    "3. An agent can write a failing test and later weaken it, so the signal is read next to the\n"
    "   test-tampering markers (§2.9).",
)


def entry():  # type: ignore[no-untyped-def]
    [found] = [e for e in PackageCatalogue().entries() if e.id == "code.test_first_order"]
    return found


def test_the_entry_states_its_method_scopes_and_flags() -> None:
    found = entry()

    assert [m.n for m in found.methods] == [1]
    assert found.methods[0].description.strip()
    assert found.scopes == ("run", "story")
    assert found.additive is False
    assert found.fingerprint_group is False
    assert found.unit == "stories"
    assert found.level == "A"
    assert found.missing_words == ("n/a", "not readable")


def test_each_of_the_three_limits_is_present_verbatim_and_in_order() -> None:
    limits = entry().limits or ""

    positions = [limits.index(limit) for limit in LIMITS]
    assert positions == sorted(positions)


def test_the_method_description_names_the_default_classifier() -> None:
    assert "default classifier" in entry().methods[0].description


def test_the_registry_holds_its_first_method() -> None:
    assert "code.test_first_order@1" in REGISTRY
