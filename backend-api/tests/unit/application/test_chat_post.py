"""`jobs/chat_post.py`: one thread per stop, posted outside any transaction, never reposted,
and the sweep that fails a `posting` row left behind (story 3-3, AD-25)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs.chat_post import (
    INTERRUPTED,
    POSTING_STALE_MINUTES,
    due_kind,
    sweep_posting,
)
from orchestrator.application.rules.chat_message import PAGE_ACTION, REPLY_ACTION
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError
from tests.unit.fakes.chat_world import ALICE, BASE_URL, BOB, TOKEN, World, a_row


def posting_row(world: World, run_id: Any, **overrides: Any) -> ChatThread:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": run_id,
        "park_seq": 3,
        "park_kind": "blocked",
        "provider": "mattermost",
        "channel_id": "c1",
        "ref": None,
        "cursor": None,
        "state": "posting",
        "error": None,
        "last_reminded_at": None,
        "created_at": world.clock.now(),
        "updated_at": world.clock.now(),
    }
    fields.update(overrides)
    thread = ChatThread(**fields)
    world.threads.add(thread)
    return thread


# ── posting ────────────────────────────────────────────────────────────────────────────────


def test_a_blocked_stop_posts_one_thread_naming_every_allowed_user() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    world.add_rows(a_row(run.id, 1, "epics[1].stories[0].build", story_id="2-1"))

    world.poll()

    ((text, mentions),) = world.chat.posts
    assert mentions == (ALICE, BOB)
    assert text.split("\n")[0] == "Run needs you · Mixed Signals / orchestrator · blocked · stop 3"
    assert text.split("\n")[-2:] == [REPLY_ACTION, f"Run: {BASE_URL}/workflows/{run.id}"]
    thread = world.only_thread()
    assert (thread.state, thread.ref, thread.error) == ("open", "thread-1", None)
    assert (thread.run_id, thread.park_seq, thread.park_kind) == (run.id, 3, "blocked")
    assert (thread.provider, thread.channel_id) == ("mattermost", "c1")
    assert thread.created_at == world.clock.now()


def test_the_run_link_is_sent_as_the_trusted_suffix() -> None:
    """Story 3-3 lead review of the build, 2026-11-02: the adapter leaves the system's own
    link line alone, so an IPv6 literal stays a usable link."""
    world = World()
    world.public_base_url = "http://[fd00::1]:4321"
    world.add_channel()
    run = world.add_run()

    world.poll()

    assert world.chat.suffixes == [f"\nRun: http://[fd00::1]:4321/workflows/{run.id}"]
    assert "Run: " not in world.chat.posts[0][0].removesuffix(world.chat.suffixes[0])


@pytest.mark.parametrize("kind", ["checkpoint", "budget", "dependency"])
def test_every_other_stop_posts_and_links_to_the_run_page(kind: str) -> None:
    world = World()
    world.add_channel()
    path = None if kind == "dependency" else "epics[1].stories[0].check"
    run = world.add_run(park_kind=kind, park_path=path)
    if path is not None:
        world.add_rows(a_row(run.id, 1, path, kind="checkpoint"))

    world.poll()

    ((text, _),) = world.chat.posts
    assert PAGE_ACTION in text.split("\n")
    assert ("Row:" in text) is (kind != "dependency")
    assert world.only_thread().park_kind == kind


def test_metadata_only_posts_no_question() -> None:
    world = World()
    world.add_channel(metadata_only=True)
    world.add_run(park_reason="the secret question")

    world.poll()

    ((text, _),) = world.chat.posts
    assert "secret" not in text


def test_no_base_url_leaves_the_run_line_out() -> None:
    world = World()
    world.public_base_url = ""
    world.add_channel()
    world.add_run()

    world.poll()

    assert "Run: " not in world.chat.posts[0][0]


def test_a_second_fire_posts_nothing_for_a_stop_that_has_its_thread() -> None:
    world = World()
    world.add_channel()
    world.add_run()

    world.poll()
    world.poll()

    assert len(world.chat.posts) == 1


def test_a_later_stop_of_the_same_run_gets_its_own_thread() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    world.poll()

    world.update_run(run, park_seq=4)
    world.poll()

    assert [len(world.chat.posts)] == [2]
    assert sorted(t.park_seq for t in world.threads.threads.values()) == [3, 4]


@pytest.mark.parametrize(
    "changes",
    [
        {"park_kind": "paused"},
        {"senior_session": True},
        {"terminal_session": True},
        {"status": "running"},
        {"park_kind": None},
    ],
)
def test_a_paused_locked_or_not_parked_run_is_not_posted(changes: dict[str, Any]) -> None:
    world = World()
    world.add_channel()
    world.add_run(**changes)

    world.poll()

    assert world.chat.posts == []
    assert world.threads.threads == {}


def test_a_stop_whose_lock_clears_at_the_same_park_seq_posts_then() -> None:
    world = World()
    world.add_channel()
    run = world.add_run(senior_session=True)
    world.poll()

    world.update_run(run, senior_session=False)
    world.poll()

    assert len(world.chat.posts) == 1
    assert [world.only_thread().park_seq] == [3]


def test_another_projects_run_is_not_posted_on_this_channel() -> None:
    world = World()
    world.add_channel()
    world.add_run(project_id=world.add_project("Other").id)

    world.poll()

    assert world.chat.posts == []


def test_no_unit_of_work_is_open_while_a_post_is_sent() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    seen: list[bool] = []
    world.chat.on_send = lambda: seen.append(world.uow.is_open)

    world.poll()

    assert seen == [False]


def test_a_fire_overlapping_an_in_flight_post_posts_nothing_and_writes_no_row() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    fired: list[bool] = []

    def second_fire() -> None:
        if not fired:
            fired.append(True)
            world.poll()

    world.chat.on_send = second_fire

    world.poll()

    assert fired == [True]
    assert len(world.chat.posts) == 1
    assert world.only_thread().state == "open"


def test_a_refused_post_fails_the_row_with_the_token_masked_and_is_never_reposted() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.chat.fail_next(ChatError(f"403 bot not in channel {TOKEN} c1"))

    world.poll()
    world.poll()

    thread = world.only_thread()
    assert thread.state == "failed"
    assert thread.error == "403 bot not in channel *** c1"
    assert thread.ref is None
    assert world.chat.posts == []


def test_an_unexpected_failure_fails_the_row_by_class_name() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.chat.fail_next(ValueError("the detail is not kept"))  # type: ignore[arg-type]

    world.poll()

    thread = world.only_thread()
    assert (thread.state, thread.error) == ("failed", "internal: ValueError")


def test_a_failed_post_changes_no_run_and_records_nothing() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    world.chat.fail_next(ChatError("500"))

    world.poll()

    assert world.runs.runs[run.id] == run
    assert world.records.records == {}


def test_an_outcome_for_a_row_that_is_no_longer_posting_is_dropped_and_logged() -> None:
    world = World()
    world.add_channel()
    world.add_run()

    def fail_meanwhile() -> None:
        thread = world.only_thread()
        world.threads.threads[thread.id] = replace(thread, state="failed", error="swept")

    world.chat.on_send = fail_meanwhile

    with capture_logs() as logs:
        world.poll()

    thread = world.only_thread()
    assert (thread.state, thread.error, thread.ref) == ("failed", "swept", None)
    assert [line["event"] for line in logs].count("chat post outcome dropped") == 1


def test_an_outcome_for_a_deleted_row_is_dropped() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.chat.on_send = world.threads.threads.clear

    with capture_logs() as logs:
        world.poll()

    assert world.threads.threads == {}
    assert "chat post outcome dropped" in [line["event"] for line in logs]


def test_the_claim_rechecks_the_run_under_its_lock() -> None:
    world = World()
    world.add_channel()
    first = world.add_run(created_at=world.clock.now() - timedelta(hours=3))
    second = world.add_run()

    def pause_the_second() -> None:
        world.update_run(world.runs.runs[second.id], park_kind="paused")

    world.chat.on_send = pause_the_second

    world.poll()

    assert len(world.chat.posts) == 1
    assert world.only_thread().run_id == first.id


def test_a_claim_that_loses_the_insert_posts_nothing() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.threads.add = lambda thread: False  # type: ignore[method-assign]

    world.poll()

    assert world.chat.posts == []


def test_a_claim_that_raises_is_logged_and_the_next_run_still_posts() -> None:
    world = World()
    world.add_channel()
    broken = world.add_run(created_at=world.clock.now() - timedelta(hours=3))
    world.add_run()
    world.add_rows(a_row(broken.id, 1, "epics[1].stories[0].build", consults={"blocked": 1}))
    original = world.steps.list_for_run

    def explode(run_id: Any) -> Any:
        if run_id == broken.id:
            raise RuntimeError("boom")
        return original(run_id)

    world.steps.list_for_run = explode  # type: ignore[method-assign]

    with capture_logs() as logs:
        world.poll()

    assert len(world.chat.posts) == 1
    failed = [line for line in logs if line["event"] == "chat post failed"]
    assert failed == [
        {
            "event": "chat post failed",
            "log_level": "warning",
            "run_id": str(broken.id),
            "park_seq": 3,
            "error_class": "RuntimeError",
        }
    ]


def test_due_kind_is_the_park_kind_of_a_stop_that_may_post() -> None:
    world = World()
    run = world.add_run(park_kind="checkpoint")

    assert due_kind(run) == "checkpoint"
    assert due_kind(run.model_copy(update={"park_kind": "paused"})) is None


# ── the sweep ──────────────────────────────────────────────────────────────────────────────


def test_a_posting_row_from_before_this_process_started_is_failed_and_not_posted() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    posting_row(world, run.id, created_at=world.started_at - timedelta(seconds=1))

    world.poll()

    thread = world.only_thread()
    assert (thread.state, thread.error) == ("failed", INTERRUPTED)
    assert thread.error == "post interrupted; not reposted; a thread may exist and is not read"
    assert thread.updated_at == world.clock.now()
    assert world.chat.posts == []


def test_a_posting_row_older_than_the_stale_limit_is_failed() -> None:
    world = World()
    run = world.add_run()
    age = timedelta(minutes=POSTING_STALE_MINUTES, seconds=1)
    posting_row(world, run.id, created_at=world.clock.now() - age)

    sweep_posting(world.ports())

    assert world.only_thread().state == "failed"


def test_a_posting_row_in_flight_in_this_process_is_left_alone() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    posting_row(world, run.id, created_at=world.clock.now() - timedelta(minutes=2))

    world.poll()

    assert world.only_thread().state == "posting"
    assert world.chat.posts == []


def test_a_row_that_stopped_posting_before_its_lock_is_left_alone() -> None:
    world = World()
    run = world.add_run()
    thread = posting_row(world, run.id, created_at=world.started_at - timedelta(minutes=1))
    original = world.threads.get_for_update

    def recorded_meanwhile(thread_id: Any) -> Any:
        found = original(thread_id)
        return None if found is None else replace(found, state="open", ref="t")

    world.threads.get_for_update = recorded_meanwhile  # type: ignore[method-assign]

    sweep_posting(world.ports())

    assert world.threads.threads[thread.id].state == "posting"


def test_a_sweep_failure_on_one_row_is_logged_and_the_next_row_is_swept() -> None:
    world = World()
    early = world.started_at - timedelta(minutes=1)
    first = posting_row(world, world.add_run().id, created_at=early)
    second = posting_row(world, world.add_run().id, created_at=early + timedelta(seconds=1))
    original = world.threads.get_for_update

    def explode(thread_id: Any) -> Any:
        if thread_id == first.id:
            raise RuntimeError("boom")
        return original(thread_id)

    world.threads.get_for_update = explode  # type: ignore[method-assign]

    with capture_logs() as logs:
        sweep_posting(world.ports())

    assert world.threads.threads[second.id].state == "failed"
    assert [line["event"] for line in logs].count("chat sweep failed") == 1
