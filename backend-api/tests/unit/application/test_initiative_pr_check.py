"""`application/jobs/initiative_pr_check.py` — epic 9 story 1, AC1 to AC6."""

from __future__ import annotations

from typing import Any

from structlog.testing import capture_logs

from orchestrator.application.jobs.initiative_pr_check import (
    InitiativePrCheckPorts,
    run_initiative_pr_check,
)
from orchestrator.domain.entities.initiative import FrozenSequence, Initiative
from orchestrator.domain.entities.run import Run
from tests.unit.application.initiative_transition_world import (
    BUILD,
    TransitionWorld,
    entry,
    sequence,
)
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.pull_requests import FakePullRequests

URL_A = "https://github.com/o/a/compare/main...feat/x"
URL_B = "https://github.com/o/b/compare/main...feat/x"
KEY_A = ("o", "a", "feat/x")
KEY_B = ("o", "b", "feat/x")
BUILD_POSITION = 2


def ports_for(world: TransitionWorld, pull_requests: FakePullRequests) -> InitiativePrCheckPorts:
    return InitiativePrCheckPorts(
        uow=world.uow,
        initiatives=world.initiatives,
        runs=world.runs,
        pull_requests=pull_requests,
        clock=FakeClock(),
    )


def stored(world: TransitionWorld) -> Initiative:
    found = world.initiatives.get(world.initiative_row.id)
    assert found is not None
    return found


def build_run(world: TransitionWorld, *urls: str, status: str = "done", **fields: Any) -> Run:
    return world.ended_run(BUILD_POSITION, status=status, compare_urls=urls, **fields)


def writes(world: TransitionWorld) -> list[str]:
    return [name for name, _ in world.initiatives.calls if name in ("update", "get_for_update")]


def test_every_compare_url_merged_sets_pr_merged_at_once_and_only_that() -> None:
    world = TransitionWorld()
    build_run(world, URL_A, URL_B)
    before = stored(world)
    pull_requests = FakePullRequests({KEY_A: True, KEY_B: True})
    ports = ports_for(world, pull_requests)

    marked = run_initiative_pr_check(ports)

    assert marked == (before.id,)
    assert stored(world) == before.model_copy(update={"pr_merged_at": ports.clock.now()})
    assert world.uow.committed
    assert pull_requests.calls == [KEY_A, KEY_B]

    assert run_initiative_pr_check(ports) == ()
    assert pull_requests.calls == [KEY_A, KEY_B]
    assert writes(world) == ["get_for_update", "update"]


def test_one_url_not_merged_leaves_the_initiative_open() -> None:
    world = TransitionWorld()
    build_run(world, URL_A, URL_B)

    assert run_initiative_pr_check(ports_for(world, FakePullRequests({KEY_A: True}))) == ()

    assert stored(world).pr_merged_at is None
    assert writes(world) == []


def test_an_unreadable_url_writes_nothing_and_logs_the_reason() -> None:
    world = TransitionWorld()
    build_run(world, URL_A, URL_B)
    pull_requests = FakePullRequests({KEY_A: True}, unreadable=[KEY_B])

    with capture_logs() as logs:
        assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert stored(world).pr_merged_at is None
    assert writes(world) == []
    assert {
        "event": "initiative_pr_check",
        "reason": "GitHub unreadable",
        "initiative_id": str(world.initiative_row.id),
        "log_level": "warning",
    } in logs


def test_a_cancelled_initiative_is_not_asked_about() -> None:
    world = TransitionWorld()
    build_run(world, URL_A)
    world.initiatives.update(
        world.initiative_row.model_copy(update={"cancelled_at": FakeClock().now()})
    )
    pull_requests = FakePullRequests({KEY_A: True})

    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert pull_requests.calls == []
    assert stored(world).pr_merged_at is None


def test_no_build_run_or_a_build_run_not_done_is_not_asked_about() -> None:
    world = TransitionWorld()
    pull_requests = FakePullRequests({KEY_A: True})
    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    build_run(world, URL_A, status="running")
    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert pull_requests.calls == []
    assert writes(world) == []


def test_the_latest_run_at_the_build_position_decides_not_an_older_done_one() -> None:
    world = TransitionWorld()
    older = build_run(world, URL_A)
    world.runs.runs[older.id] = older.model_copy(update={"created_at": FakeClock().now()})
    newer = build_run(world, URL_B, status="running", round_=2)
    world.runs.runs[newer.id] = newer.model_copy(
        update={"created_at": FakeClock(FakeClock().now()).advance(60)}
    )
    pull_requests = FakePullRequests({KEY_A: True, KEY_B: True})

    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert pull_requests.calls == []


def test_only_the_build_runs_compare_urls_are_checked() -> None:
    world = TransitionWorld()
    world.initiative_row = world.initiatives.initiatives[world.initiative_row.id] = (
        world.initiative_row.model_copy(
            update={
                "sequence": FrozenSequence(
                    **{
                        **sequence().model_dump(),
                        "workflows": (
                            *sequence().workflows,
                            entry(("fx.deploy", 1), type_="auto", shown="step"),
                        ),
                    }
                )
            }
        )
    )
    build_run(world, URL_A)
    world.ended_run(3, compare_urls=("https://github.com/o/d/compare/main...feat/d",))
    pull_requests = FakePullRequests({KEY_A: True})

    assert run_initiative_pr_check(ports_for(world, pull_requests)) == (world.initiative_row.id,)

    assert pull_requests.calls == [KEY_A]


def test_an_initiative_with_no_build_entry_is_skipped() -> None:
    world = TransitionWorld()
    spec_only = sequence().model_copy(update={"workflows": sequence().workflows[:2]})
    world.initiatives.update(world.initiative_row.model_copy(update={"sequence": spec_only}))
    pull_requests = FakePullRequests()

    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert pull_requests.calls == []


def test_no_compare_url_or_only_unparsable_ones_write_nothing() -> None:
    world = TransitionWorld()
    pull_requests = FakePullRequests()
    run = build_run(world)
    assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    world.runs.runs[run.id] = run.model_copy(update={"compare_urls": ("not a url",)})
    with capture_logs() as logs:
        assert run_initiative_pr_check(ports_for(world, pull_requests)) == ()

    assert pull_requests.calls == []
    assert stored(world).pr_merged_at is None
    assert any(
        e["event"] == "initiative_pr_check" and e["reason"] == "unparsable compare url"
        for e in logs
    )


def test_an_unparsable_url_is_skipped_and_the_parsable_one_decides() -> None:
    world = TransitionWorld()
    build_run(world, "https://example.com/x", URL_A)

    assert run_initiative_pr_check(ports_for(world, FakePullRequests({KEY_A: True}))) == (
        world.initiative_row.id,
    )


def test_an_initiative_closed_between_the_read_and_the_write_is_left_alone() -> None:
    world = TransitionWorld()
    build_run(world, URL_A)
    initiatives = world.initiatives
    original = initiatives.get_for_update

    def cancelled_meanwhile(initiative_id: Any) -> Initiative | None:
        found = original(initiative_id)
        assert found is not None
        return found.model_copy(update={"cancelled_at": FakeClock().now()})

    initiatives.get_for_update = cancelled_meanwhile  # type: ignore[method-assign]

    assert run_initiative_pr_check(ports_for(world, FakePullRequests({KEY_A: True}))) == ()

    assert "update" not in [name for name, _ in initiatives.calls]


def test_the_build_entry_is_the_one_the_fixture_names() -> None:
    assert sequence(BUILD).workflows[BUILD_POSITION].template == BUILD[0]
