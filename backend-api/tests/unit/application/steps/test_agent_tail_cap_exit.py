"""Regression coverage for 5.11's cap-exit correction
(`_bmad-output/planning-artifacts/mvp/epics/epic-05-dev-loop/stories/5-11-claude-readiness-passes-end-to-end.md`).

5.7 shipped `CAP_EXIT_FIELD = "stop_reason"` / `CAP_EXIT_VALUE = "max_budget"` as a guess,
held behind two constants pending confirmation. 5.11 read the shipped Claude Code 2.1.258
bundle's own error-result schema directly and disproved it: the literal `"max_budget"`
occurs zero times anywhere in the bundle, `stop_reason` never carries it, and the schema's
own `subtype` field is what a `--max-budget-usd` stop actually reports —
`"error_max_budget_usd"`, emitted when `terminal_reason === "budget_exhausted"`. The
constants now read `CAP_EXIT_FIELD = "subtype"` / `CAP_EXIT_VALUE = "error_max_budget_usd"`.

This module isolates `_cap_exit`'s forced-park branch (`budget.forced`, AD-10/FR-14) from
the ordinary over-budget check (`budget.check`, `application/rules/budget.py`) by keeping
every scripted attempt strictly *under* budget: `budget.forced` parks unconditionally,
`budget.check` never parks at or under budget, so a park appearing in these tests can only
be the cap-exit short-circuit itself firing — proof that a given `raw_result` pair is (or
is not) read as the harness's own cap stop, not an artifact of also being over budget.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.application.steps import agent_tail
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import a_run
from tests.unit.application.steps.agent_tail_fixtures import SESSION_ID, a_tail_world
from tests.unit.fakes.gateway import FakeGateway

BUDGET = Decimal("40.00")
UNDER_BUDGET = "5.00"
LOG_PATH = Path("/work/logs/003-1.log")


def test_the_constants_are_5_11s_confirmed_pair_not_5_7s_disproved_guess() -> None:
    """Locks the correction itself: a regression back to `stop_reason`/`max_budget` fails
    here even before either behavioural test below runs."""
    assert agent_tail.CAP_EXIT_FIELD == "subtype"
    assert agent_tail.CAP_EXIT_VALUE == "error_max_budget_usd"


def test_the_old_disproved_pair_is_not_read_as_a_cap_stop_even_under_budget() -> None:
    """The literal pair 5.7 shipped (`{"stop_reason": "max_budget"}`), disproved by 5.11,
    must fall through to the ordinary `budget.check` — which never parks at or under
    budget. A park appearing here would mean the disproved guess is still being matched."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    gateway.script(world.run.id, world.attempt.id, spend(UNDER_BUDGET))
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=1,
        log_path=LOG_PATH,
        raw_result={"stop_reason": "max_budget"},
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.park is None


def test_the_confirmed_pair_forces_a_budget_park_even_under_budget() -> None:
    """The corrected pair (`subtype: "error_max_budget_usd"`), read out of the shipped
    2.1.258 bundle's own schema, must take the `forced` branch: a park appears even though
    the scripted spend never crosses budget — exactly what distinguishes the harness's own
    cap exit (AD-10, FR-14) from an ordinary over-budget stop."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    gateway.script(world.run.id, world.attempt.id, spend(UNDER_BUDGET))
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=1,
        log_path=LOG_PATH,
        raw_result={"subtype": "error_max_budget_usd"},
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "error"
    assert outcome.park is not None
    assert outcome.park.kind == "budget"
    assert outcome.park.reason == "budget $5.00 / $40.00"
    assert outcome.retry is None
    assert outcome.budget_park is None
