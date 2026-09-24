"""`application/steps/agent_skill.py` — the last line of defence before a dispatch.

Why (hub-Run operations, skills install fix, 2026-09-24): a harness handed a skill name it
cannot resolve does not fail.  It improvises.  In the live Run this module was written for,
`claude` was dispatched with `skill: spec-gate`, could not resolve it, worked for 177
seconds, edited a protected `SPEC.md`, produced none of the expected artifact, and the row
only then parked `misconfigured: no story file`.  Pre-flight is the first line of defence and
now fails such a Run before it is created; this module refuses the same row at dispatch time,
for the Run that was already planned when the catalog changed underneath it.

What it must not do is refuse the dispatch forms that name no skill at all — `prompt:` and
`intent:` rows carry no `skill` key (`application/templates/agent_row.py`) and are dispatched
exactly as before.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps import agent_skill
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import StepContext, StepPorts
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import a_world, an_agent_row, an_attempt
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.skill_catalog import FakeSkillCatalog

SKILL = "bmad-build-auto"


def _ctx(with_resolved: dict[str, Any], catalog: Any) -> StepContext:
    """The smallest context `agent_skill.verify` reads: a row, and a catalog port."""
    row = an_agent_row(with_resolved)
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd="/work/wt",
        frame_start_sha=None,
        previous_attempt=None,
        attempt=an_attempt(row, 1),
        resume_signal=None,
        ports=StepPorts(
            git=FakeGit(),
            clock=FakeClock(),
            work_dir="/work",
            skill_catalog=catalog,
        ),
    )


def _resolved(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"harness": "claude", "model": "m", "skill": SKILL}
    row.update(over)
    return row


# ── the refusal ───────────────────────────────────────────────────────────────


def test_verify_parks_misconfigured_when_the_catalog_does_not_list_the_skill() -> None:
    ctx = _ctx(_resolved(skill="spec-gate"), FakeSkillCatalog(frozenset({SKILL})))

    result = agent_skill.verify(ctx)

    assert isinstance(result, StepResult)
    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert "spec-gate" in result.park.reason
    assert result.park.path == ctx.row.path


def test_verify_keeps_the_rows_own_gate() -> None:
    ctx = _ctx(_resolved(skill="spec-gate"), FakeSkillCatalog(frozenset()))

    result = agent_skill.verify(ctx)

    assert result is not None
    assert result.gate == ctx.row.gate


# ── what it must never refuse ─────────────────────────────────────────────────


def test_verify_passes_a_skill_the_catalog_lists() -> None:
    ctx = _ctx(_resolved(), FakeSkillCatalog(frozenset({SKILL})))

    assert agent_skill.verify(ctx) is None


def test_verify_passes_a_row_that_names_no_skill() -> None:
    """The `prompt:` and `intent:` dispatch forms carry no `skill` key."""
    resolved = _resolved()
    del resolved["skill"]
    ctx = _ctx(resolved, FakeSkillCatalog(frozenset()))

    assert agent_skill.verify(ctx) is None


def test_verify_passes_a_row_whose_skill_is_blank() -> None:
    ctx = _ctx(_resolved(skill=""), FakeSkillCatalog(frozenset()))

    assert agent_skill.verify(ctx) is None


def test_verify_passes_a_row_whose_skill_is_not_a_string() -> None:
    ctx = _ctx(_resolved(skill=7), FakeSkillCatalog(frozenset()))

    assert agent_skill.verify(ctx) is None


def test_verify_passes_when_no_catalog_is_wired() -> None:
    """`StepPorts.skill_catalog` is `None` in every process that wired none — the same
    degradation `tracer` has.  Pre-flight is where an unreadable catalog is refused."""
    ctx = _ctx(_resolved(skill="spec-gate"), None)

    assert agent_skill.verify(ctx) is None


def test_verify_passes_when_the_catalog_is_unavailable() -> None:
    """A manifest that cannot be read says nothing about the skill, and a row already
    planned and running must not be parked on no evidence."""
    ctx = _ctx(_resolved(skill="spec-gate"), FakeSkillCatalog(None))

    assert agent_skill.verify(ctx) is None


# ── through the executor: before any commit is made ───────────────────────────


def test_the_agent_kind_parks_before_it_commits_anything() -> None:
    """Beside the harness lookup and for its reason (AD-9): a row that cannot run must park
    without leaving a WIP commit, a prepare commit or an attempt behind."""
    world = a_world(skill_catalog=FakeSkillCatalog(frozenset({"bmad-dev-story"})))

    result = AgentExecutor().execute(world.ctx)

    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert "bmad-build-auto" in result.park.reason
    assert world.harness.calls == []
    assert world.git.called("commit") == []


def test_the_agent_kind_dispatches_when_the_catalog_lists_the_skill() -> None:
    world = a_world(skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    result = AgentExecutor().execute(world.ctx)

    assert result.park is None or result.park.kind != "misconfigured"
    assert world.harness.calls != []
