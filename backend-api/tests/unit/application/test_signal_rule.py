"""`signal_rule` holds `Rule` and `PARKED`; `signals_table` re-exports them."""

from __future__ import annotations

from orchestrator.application.rules import signal_rule, signals_table


def test_the_table_re_exports_the_same_objects() -> None:
    assert signals_table.Rule is signal_rule.Rule
    assert signals_table.PARKED is signal_rule.PARKED


def test_a_rule_defaults_to_the_parked_statuses() -> None:
    assert signal_rule.Rule(park_kinds=frozenset()).run_statuses == signal_rule.PARKED
