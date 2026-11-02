"""The trajectory row and consult attempts (story 1-4, spine AD-19/AD-21, 2026-11-02).

AD-19 says the row records the Story's *agent* attempts, so `attempts`, `harness`, `model`
and `start_sha` read `agent` attempts only — a senior's session is not the trajectory of the
agent that built the Story. Cost, tokens and wall clock are what the Story took, and AD-21
has spend read every role, so those sum over every attempt."""

from __future__ import annotations

from decimal import Decimal

from tests.unit.application.test_record_trajectory import BUILD, _record, _world
from tests.unit.application.writer_fixtures import an_attempt
from tests.unit.fakes.git import FakeGit

THREE_MINUTES = 180


def test_a_consult_attempt_is_billed_but_not_listed() -> None:
    world = _world()
    start, later = world.clock.now(), world.clock.advance(60)
    an_attempt(
        world,
        BUILD,
        n=1,
        status="error",
        harness="claude",
        model="agent-model",
        start_sha="aaa",
        started_at=start,
        ended_at=later,
        cost_usd=Decimal("1.00"),
        tokens_in=10,
        tokens_out=5,
    )
    an_attempt(
        world,
        BUILD,
        n=2,
        role="consult",
        status="error",
        harness="codex",
        model="senior-model",
        started_at=later,
        ended_at=world.clock.advance(60),
        cost_usd=Decimal("3.00"),
        tokens_in=100,
        tokens_out=50,
    )
    an_attempt(
        world,
        BUILD,
        n=3,
        status="done",
        harness="claude",
        model="agent-model",
        start_sha="ccc",
        started_at=world.clock.now(),
        ended_at=world.clock.advance(60),
        cost_usd=Decimal("0.50"),
        tokens_in=1,
        tokens_out=1,
    )

    store = _record(world, git=FakeGit(head_sha=["ddd"]))

    (trajectory,) = store.trajectories
    assert [attempt.n for attempt in trajectory.attempts] == [1, 3]
    assert (trajectory.harness, trajectory.model) == ("claude", "agent-model")
    assert trajectory.start_sha == "aaa"
    assert trajectory.cost_usd == Decimal("4.50")
    assert (trajectory.tokens_in, trajectory.tokens_out) == (111, 56)
    assert trajectory.wall_clock_seconds == THREE_MINUTES
