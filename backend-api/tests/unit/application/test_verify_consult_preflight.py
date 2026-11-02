"""Pre-flight checks the skill a `verify_failed` consult dispatches is installed (story 1-6,
spine AD-22, 2026-11-02): the block lives on a `run` row's `on_fail`, not on an `agent` row,
and a senior handed a skill its harness cannot resolve improvises."""

from __future__ import annotations

from typing import Any

from orchestrator.application.preflight import lists
from orchestrator.domain.values import PlannedRow
from tests.unit.fakes.skill_catalog import FakeSkillCatalog
from tests.unit.test_preflight_installed_skill import _ctx, _plan


def a_row(kind: str, with_resolved: dict[str, Any]) -> PlannedRow:
    return PlannedRow(
        seq=1,
        path="verify",
        label="verify",
        kind=kind,
        gate="deterministic",
        status="planned",
        reason=None,
        with_resolved=with_resolved,
        frame=None,
        story_id=None,
    )


def lines_for(installed: frozenset[str], row: PlannedRow) -> list[tuple[str, str]]:
    ctx = _ctx(plan=_plan(row), skill_catalog=FakeSkillCatalog(installed))
    return [(line.status, line.text) for line in lists.installed_skill_lines(ctx)]


ROUTE = {"target_seq": 1, "max": 2, "consult": {"skill": "senior-consult"}}


def test_a_missing_verify_consult_skill_fails_preflight() -> None:
    row = a_row("shell", {"on_fail": ROUTE})

    assert lines_for(frozenset(), row) == [("fail", "not installed: senior-consult")]


def test_an_installed_verify_consult_skill_passes() -> None:
    row = a_row("shell", {"on_fail": ROUTE})

    assert lines_for(frozenset({"senior-consult"}), row) == [("ok", "ok")]


def test_a_skill_named_twice_is_checked_once() -> None:
    both = a_row("agent", {"skill": "senior-consult", "on_fail": ROUTE})

    assert lines_for(frozenset(), both) == [("fail", "not installed: senior-consult")]


def test_a_redispatch_without_a_consult_adds_nothing() -> None:
    row = a_row("shell", {"on_fail": {"target_seq": 1, "max": 2}})

    assert lines_for(frozenset(), row) == []
    assert lines_for(frozenset(), a_row("shell", {"on_fail": "fail"})) == []


def test_a_consult_block_without_a_skill_adds_nothing() -> None:
    row = a_row("shell", {"on_fail": {"consult": {"model": "m"}}})

    assert lines_for(frozenset(), row) == []
