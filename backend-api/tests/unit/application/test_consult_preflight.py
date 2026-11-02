"""Pre-flight checks a consult's skill is installed (story 1-4, spine AD-22, 2026-11-02): a
senior handed a skill name the harness cannot resolve improvises, the same reason the row's
own skill is checked."""

from __future__ import annotations

from typing import Any

from orchestrator.application.preflight import lists
from orchestrator.domain.values import PlannedRow
from tests.unit.fakes.skill_catalog import FakeSkillCatalog
from tests.unit.test_preflight_installed_skill import _ctx, _plan


def a_row(with_resolved: dict[str, Any]) -> PlannedRow:
    return PlannedRow(
        seq=1,
        path="build",
        label="build",
        kind="agent",
        gate="liveness",
        status="planned",
        reason=None,
        with_resolved=with_resolved,
        frame=None,
        story_id=None,
    )


def lines_for(installed: frozenset[str], with_resolved: dict[str, Any]) -> list[tuple[str, str]]:
    ctx = _ctx(plan=_plan(a_row(with_resolved)), skill_catalog=FakeSkillCatalog(installed))
    return [(line.status, line.text) for line in lists.installed_skill_lines(ctx)]


def test_a_missing_consult_skill_fails_preflight() -> None:
    resolved = {"skill": "staged-plan", "consult": {"skill": "senior-consult"}}

    assert lines_for(frozenset({"staged-plan"}), resolved) == [
        ("fail", "not installed: senior-consult")
    ]


def test_an_installed_consult_skill_passes() -> None:
    resolved = {"skill": "staged-plan", "consult": {"skill": "senior-consult"}}

    assert lines_for(frozenset({"staged-plan", "senior-consult"}), resolved) == [("ok", "ok")]


def test_a_consult_on_a_row_with_its_own_prompt_is_still_checked() -> None:
    resolved = {"prompt": "do it", "consult": {"skill": "senior-consult"}}

    assert lines_for(frozenset(), resolved) == [("fail", "not installed: senior-consult")]


def test_a_consult_block_without_a_skill_adds_nothing() -> None:
    assert lines_for(frozenset(), {"consult": {"model": "m"}}) == []
    assert lines_for(frozenset(), {"consult": "junk"}) == []
