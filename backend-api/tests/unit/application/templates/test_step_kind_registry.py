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
    # Revised: the shipped-kinds row for `git.worktree` gained `mode`, whose one value
    # `attach` takes the declared branch by its exact name at its origin head
    # (multi-repo initiative S3, spine AD-7/AD-14 amendment, 2026-09-23).
    "git.worktree": ("deterministic", 5, frozenset({"base", "branch", "mode"}), False),
    "git.sync": ("deterministic", 5, frozenset(), False),
    # Added: the shipped-kinds table gained `git.merge` — `with {from}`, merging
    # `origin/{from}` into the current worktree's branch with `--no-ff`
    # (multi-repo initiative S4, spine AD-9/AD-13/AD-14 amendment, 2026-09-23).
    "git.merge": ("deterministic", 5, frozenset({"from"}), False),
    # Added: the shipped-kinds table gained `git.submodule` — bare or `{update: true}` for
    # the init + update of the Run worktree's submodules, exclusive-or
    # `{workdir, branch, base?}` for the create-or-checkout inside one of them
    # (hub-Run initiative H1, spine AD-7/AD-9/AD-14 amendment, 2026-09-23).
    "git.submodule": (
        "deterministic",
        10,
        frozenset({"update", "workdir", "branch", "base"}),
        False,
    ),
    "shell": ("deterministic", 30, frozenset({"command"}), False),
    # Revised: `agent` gained `workdir` — the harness is dispatched inside that submodule's
    # checkout and the attempt's own git bookkeeping happens in its repository, while the hub
    # anchors stay checked at the worktree root (hub-Run initiative H4, spine "Template DSL
    # v1 keys" AD-9/AD-17 amendment, 2026-09-23).
    "agent": (
        "liveness",
        None,  # operator revision 2026-09-15: no wall-clock default (stall detection instead)
        frozenset({"harness", "model", "skill", "args", "prompt_extra", "workdir"}),
        False,
        30,  # stall_default_min
    ),
    # Revised: `git.commit` and `git.push` gained `workdir` — the row runs inside that
    # submodule's own repository instead of the worktree root (hub-Run initiative H2, spine
    # "Template DSL v1 keys" AD-9/AD-14 amendment, 2026-09-23).
    "git.commit": ("deterministic", 5, frozenset({"message", "workdir"}), False),
    "git.push": ("deterministic", 5, frozenset({"branch", "workdir"}), False),
    "pr.link": ("liveness", 5, frozenset({"branch"}), False),
    # Revised: the shipped-kinds row for `checkpoint` gained `when` — a resolved falsy
    # value plans the row `skipped · no checkpoint`, the same plan-time rule the
    # empty-command shell skip already used (multi-repo initiative S5, spine AD-7
    # amendment, 2026-09-23).
    "checkpoint": ("human", None, frozenset({"when"}), False),
    "template": (None, None, frozenset({"name", "version", "inputs"}), False),
    "bmad.install": ("deterministic", 30, frozenset(), False),
}

#: Revised from twelve by the `git.submodule` row above, which was itself revised from
#: eleven by `git.merge` (hub-Run initiative H1, 2026-09-23).
THIRTEEN = 13


def test_the_registry_holds_exactly_the_thirteen_shipped_kinds() -> None:
    assert set(KIND_META) == set(SPINE)
    assert len(KIND_META) == THIRTEEN


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
