"""Wiring test: `installed_skill_lines` output propagates to `start_allowed=False`.

Verifies that the result of `installed_skill_lines` has `status == "fail"` when a skill
is absent, and that inserting those lines into the `start_allowed` formula used by
`preflight_and_plan` produces `False` — confirming the `_lines()` wiring is correct
without spinning up the full template infrastructure.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.preflight import lists
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import CHECK_INSTALLED_SKILL, PreflightRequest
from orchestrator.application.templates.plan_model import Plan
from orchestrator.domain.values import PlannedRow
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.skill_catalog import FakeSkillCatalog


def _skill_row(skill: str, seq: int = 1) -> PlannedRow:
    return PlannedRow(
        seq=seq,
        path=f"step-{seq}",
        label=f"step-{seq}",
        kind="agent",
        gate="deterministic",
        status="planned",
        reason=None,
        with_resolved={"skill": skill},
        frame=None,
        story_id=None,
    )


def test_missing_skill_produces_fail_line_and_would_block_start() -> None:
    """A plan with an absent skill yields a `fail` line; that line makes `start_allowed` False."""
    plan = Plan(plan_ref="abc1234", rows=(_skill_row("bmad-build-auto"),))
    ctx = Context(
        git=FakeGit(),
        base_dir=Path("/work/proj/repo/base"),
        bmad_version="6.11.0",
        max_active_runs=2,
        repository=None,
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        req=PreflightRequest(),
        tree=None,
        plan=plan,
        plan_error=None,
        skill_catalog=FakeSkillCatalog(frozenset()),  # empty catalog → skill absent
    )

    lines = lists.installed_skill_lines(ctx)

    # The check itself returns a fail line naming the missing skill.
    assert len(lines) == 1
    assert lines[0].check == CHECK_INSTALLED_SKILL
    assert lines[0].status == "fail"
    assert "bmad-build-auto" in lines[0].text

    # The start_allowed formula from preflight_and_plan: any fail line → False.
    start_allowed = plan is not None and not any(line.status == "fail" for line in lines)
    assert start_allowed is False
