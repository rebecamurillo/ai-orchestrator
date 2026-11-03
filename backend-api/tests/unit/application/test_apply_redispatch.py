"""`use_cases/apply_redispatch.py`: AD-9's bounded route back, read directly. The same rule is
driven through `apply_step_result` in `test_apply_step_result.py`; here each of its three
answers is asserted on the function that gives it."""

from __future__ import annotations

from orchestrator.application.rules.signals import REBASELINE_FAILED
from orchestrator.application.use_cases.apply_redispatch import (
    REDISPATCHED,
    VERIFY_FAILED,
    redispatch,
)
from orchestrator.domain.values import Park, Redispatch
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"


def a_failed_verify(build: str = "done", count: int = 0) -> World:
    world = a_world("running", EPIC_PLAN, {BUILD: build, VERIFY: "error"})  # type: ignore[dict-item]
    world.ports.steps.update(world.row(BUILD).model_copy(update={"redispatch_count": count}))
    return world


def back(world: World, most: int = 2) -> tuple[Park | None, bool]:
    attempt = an_attempt(world, VERIFY, n=1)
    target = Redispatch(target_seq=world.row(BUILD).seq, max=most)
    return redispatch(world.ports, world.stored_run(), world.row(VERIFY), target, attempt)


def test_under_the_bound_the_target_is_queued_counted_and_recorded() -> None:
    world = a_failed_verify()

    assert back(world) == (None, True)

    assert (world.status_of(BUILD), world.row(BUILD).redispatch_count) == ("queued", 1)
    [line] = world.records()
    assert line.text == REDISPATCHED.format(n=1, max=2)


def test_at_the_bound_it_parks_verify_failed() -> None:
    world = a_failed_verify(count=2)

    assert back(world) == (
        Park(kind="verify_failed", reason=VERIFY_FAILED.format(n=3), path=VERIFY),
        False,
    )


def test_a_skipped_target_parks_with_the_rebaseline_reason() -> None:
    world = a_failed_verify("skipped")

    assert back(world) == (Park(kind="verify_failed", reason=REBASELINE_FAILED, path=VERIFY), False)
