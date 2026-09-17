"""`application/steps/__init__.py` — the one enumeration of step kinds there is (AD-9).

The table is asserted whole, against the spine's "Shipped kinds" values, because that is
the point of having one: any other module that wanted a gate default or a `with` key would
be a second copy, and this test is what makes the first one authoritative.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps import (
    AGENT_KIND,
    GATES,
    KIND_META,
    TEMPLATE_CALL_KIND,
    TEMPLATE_KINDS,
    KindMeta,
)

#: The spine's table, restated once so a drift in either direction fails here.
SPINE = {
    "plan.check": ("deterministic", 5, frozenset(), True),
    "git.worktree": ("deterministic", 5, frozenset({"base", "branch"}), False),
    "git.sync": ("deterministic", 5, frozenset(), False),
    "shell": ("deterministic", 30, frozenset({"command"}), False),
    "agent": (
        "liveness",
        None,  # operator revision 2026-09-15: no wall-clock default (stall detection instead)
        frozenset({"harness", "model", "skill", "args", "prompt_extra"}),
        False,
        30,  # stall_default_min
    ),
    "git.commit": ("deterministic", 5, frozenset({"message"}), False),
    "git.push": ("deterministic", 5, frozenset({"branch"}), False),
    "pr.link": ("liveness", 5, frozenset({"branch"}), False),
    "checkpoint": ("human", None, frozenset(), False),
    "template": (None, None, frozenset({"name", "version", "inputs"}), False),
    "bmad.install": ("deterministic", 30, frozenset(), False),
}

ELEVEN = 11


def test_the_registry_holds_exactly_the_eleven_shipped_kinds() -> None:
    assert set(KIND_META) == set(SPINE)
    assert len(KIND_META) == ELEVEN


@pytest.mark.parametrize("kind", sorted(SPINE))
def test_a_kind_carries_the_spine_values(kind: str) -> None:
    """Operator revision 2026-09-15: agent's timeout_default_min is None; stall_default_min=30."""
    spine = SPINE[kind]
    gate, timeout, with_keys, planner_only = spine[:4]
    stall = spine[4] if len(spine) > 4 else None  # type: ignore[misc]  # noqa: PLR2004

    assert KIND_META[kind] == KindMeta(  # type: ignore[arg-type]
        gate, timeout, with_keys, planner_only, stall_default_min=stall
    )


def test_plan_check_is_the_only_kind_a_template_may_not_name() -> None:
    planner_only = {kind for kind, meta in KIND_META.items() if meta.planner_only}

    assert planner_only == {"plan.check"}


def test_the_kinds_a_template_may_name_are_derived_from_the_registry() -> None:
    assert TEMPLATE_KINDS == frozenset(KIND_META) - {"plan.check"}


def test_the_gate_tokens_are_the_three_the_conventions_fix() -> None:
    assert GATES == frozenset({"liveness", "deterministic", "human"})


def test_the_two_kinds_with_rules_of_their_own_are_named_not_spelled_out() -> None:
    assert KIND_META[TEMPLATE_CALL_KIND].gate_default is None
    assert KIND_META[AGENT_KIND].gate_default == "liveness"


def test_a_kind_is_frozen_so_the_table_cannot_be_edited_through_a_row() -> None:
    with pytest.raises(AttributeError):
        KIND_META["shell"].gate_default = "human"  # type: ignore[misc]


def test_planner_only_defaults_to_false_so_a_new_row_is_writable_by_default() -> None:
    assert KindMeta("human", None, frozenset()).planner_only is False
