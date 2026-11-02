"""`jobs/chat_remind.py`: a mentioning reply every `CHAT_REMINDER_HOURS` while the Run stays
at its thread's stop, claimed under the Run lock then the thread's, sent outside any
transaction, and never retried (story 3-3, D2, D3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs.chat_remind import claim_reminder
from orchestrator.application.rules.chat_message import PAGE_ACTION, REPLY_ACTION
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError, ThreadRef
from tests.unit.application.chat_fixtures import ALICE, BASE_URL, BOB, HOURS, World

HOUR = 3600


def open_thread(world: World, run: Run, **overrides: Any) -> ChatThread:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": run.id,
        "park_seq": run.park_seq,
        "park_kind": run.park_kind,
        "provider": "mattermost",
        "channel_id": "c1",
        "ref": f"root-{run.id}",
        "cursor": None,
        "state": "open",
        "error": None,
        "last_reminded_at": None,
        "created_at": world.clock.now(),
        "updated_at": world.clock.now(),
    }
    fields.update(overrides)
    thread = ChatThread(**fields)
    world.threads.add(thread)
    return thread


def parked(world: World, **overrides: Any) -> tuple[Run, ChatThread]:
    world.add_channel()
    run = world.add_run(**overrides)
    return run, open_thread(world, run)


def test_a_thread_four_hours_old_gets_one_mentioning_reminder() -> None:
    world = World()
    run, thread = parked(world)
    world.clock.advance(HOURS * HOUR)

    world.poll()

    assert world.chat.replies == [
        (
            ThreadRef(id=thread.ref or ""),
            "\n".join(
                [
                    "Still waiting · blocked · stop 3 · parked 4 h",
                    REPLY_ACTION,
                    f"Run: {BASE_URL}/workflows/{run.id}",
                ]
            ),
        )
    ]
    assert world.chat.reply_mentions == [(ALICE, BOB)]
    stored = world.threads.threads[thread.id]
    assert stored.last_reminded_at == world.clock.now()
    assert stored.updated_at == world.clock.now()


def test_the_next_reminder_waits_another_period() -> None:
    world = World()
    parked(world)
    world.clock.advance(HOURS * HOUR)
    world.poll()

    world.clock.advance(HOURS * HOUR - 1)
    world.poll()
    assert len(world.chat.replies) == 1

    world.clock.advance(1)
    world.poll()
    assert [len(world.chat.replies)] == [2]
    assert "parked 8 h" in world.chat.replies[1][1]


def test_three_hours_fifty_nine_is_not_due() -> None:
    world = World()
    parked(world)
    world.clock.advance(HOURS * HOUR - 60)

    world.poll()

    assert world.chat.replies == []


def test_a_run_that_moved_to_another_stop_is_not_reminded() -> None:
    world = World()
    run, _ = parked(world)
    world.update_run(run, park_seq=4, park_kind="checkpoint")
    world.clock.advance(HOURS * HOUR)

    world.poll()

    assert world.chat.replies == []


@pytest.mark.parametrize(
    "changes", [{"senior_session": True}, {"terminal_session": True}, {"status": "running"}]
)
def test_a_locked_or_moving_run_is_not_reminded(changes: dict[str, Any]) -> None:
    world = World()
    run, _ = parked(world)
    world.update_run(run, **changes)
    world.clock.advance(HOURS * HOUR)

    world.poll()

    assert world.chat.replies == []


def test_a_failed_thread_is_not_reminded() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    open_thread(world, run, state="failed", ref=None, error="403")
    world.clock.advance(HOURS * HOUR)

    world.poll()

    assert world.chat.replies == []


@pytest.mark.parametrize(
    "overrides", [{"channel_id": "c-old"}, {"provider": "slack"}], ids=["channel", "provider"]
)
def test_a_thread_on_another_channel_is_not_reminded(overrides: dict[str, Any]) -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    open_thread(world, run, **overrides)
    world.clock.advance(HOURS * HOUR)

    world.poll()

    assert world.chat.replies == []


def test_the_reminder_copy_is_the_threads_park_kind_at_posting() -> None:
    world = World()
    world.add_channel()
    run = world.add_run(park_kind="blocked")
    open_thread(world, run, park_kind="budget")
    world.clock.advance(HOURS * HOUR)

    world.poll()

    ((_, text),) = world.chat.replies
    assert text.split("\n")[:2] == ["Still waiting · budget · stop 3 · parked 4 h", PAGE_ACTION]


def test_no_unit_of_work_is_open_while_a_reminder_is_sent() -> None:
    world = World()
    parked(world)
    world.clock.advance(HOURS * HOUR)
    seen: list[bool] = []
    world.chat.on_send = lambda: seen.append(world.uow.is_open)

    world.poll()

    assert seen == [False]


def test_two_fires_that_both_saw_it_due_send_one_reminder() -> None:
    world = World()
    _, thread = parked(world)
    world.clock.advance(HOURS * HOUR)
    ports = world.ports()

    first = claim_reminder(ports, thread, world.clock.now())
    second = claim_reminder(ports, thread, world.clock.now())

    assert first is not None
    assert second is None


def test_a_fire_overlapping_an_in_flight_reminder_sends_nothing() -> None:
    world = World()
    parked(world)
    world.clock.advance(HOURS * HOUR)
    fired: list[bool] = []

    def second_fire() -> None:
        if not fired:
            fired.append(True)
            world.poll()

    world.chat.on_send = second_fire

    world.poll()

    assert len(world.chat.replies) == 1


def test_a_claim_on_a_thread_or_run_that_is_gone_sends_nothing() -> None:
    world = World()
    run, thread = parked(world)
    world.clock.advance(HOURS * HOUR)

    world.threads.threads.clear()
    assert claim_reminder(world.ports(), thread, world.clock.now()) is None
    world.runs.runs.pop(run.id)
    assert claim_reminder(world.ports(), thread, world.clock.now()) is None


def test_a_failed_reminder_is_logged_once_not_stored_and_not_retried() -> None:
    world = World()
    run, thread = parked(world)
    world.clock.advance(HOURS * HOUR)
    world.chat.fail_next(ChatError("403 secret detail"))

    with capture_logs() as logs:
        world.poll()
        world.poll()

    failed = [line for line in logs if line["event"] == "chat reminder failed"]
    assert failed == [
        {
            "event": "chat reminder failed",
            "log_level": "warning",
            "run_id": str(run.id),
            "thread_id": str(thread.id),
            "park_seq": 3,
            "error_class": "ChatError",
        }
    ]
    stored = world.threads.threads[thread.id]
    assert stored.error is None
    assert stored.last_reminded_at == world.clock.now()
    assert world.chat.replies == []


def test_one_failing_thread_does_not_stop_the_next() -> None:
    world = World()
    world.add_channel()
    first = world.add_run()
    second = world.add_run()
    open_thread(world, first)
    open_thread(world, second, created_at=world.clock.now() + timedelta(seconds=1))
    world.clock.advance(HOURS * HOUR + 1)
    world.chat.fail_next(ChatError("500"))

    world.poll()

    assert len(world.chat.replies) == 1


def test_a_reminder_hours_count_is_whole_hours_since_posting() -> None:
    world = World()
    _, thread = parked(world)
    world.threads.threads[thread.id] = replace(
        thread, last_reminded_at=world.clock.now() + timedelta(hours=2)
    )
    world.clock.advance(6 * HOUR + 1800)

    world.poll()

    assert "parked 6 h" in world.chat.replies[0][1]
