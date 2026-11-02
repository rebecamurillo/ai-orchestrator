"""`jobs/chat_notice.py`: one channel line, with no mention, when the senior accepts test
edits; claimed by its gate record before it is posted, posted once, its failure kept
(story 3-3, D4)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from structlog.testing import capture_logs

from orchestrator.application.jobs.chat_notice import INTERNAL, post_notices
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.chat import ChatError
from tests.unit.fakes.chat_world import BASE_URL, TOKEN, World, a_row

BUILD = "epics[1].stories[0].build"


def accepted(world: World, run: Run, **overrides: Any) -> GateRecord:
    fields: dict[str, Any] = {
        "event": "senior_accept",
        "actor": "senior",
        "path": BUILD,
        "text": "accepted by the senior: tests/a.py · renamed",
        "payload": {"files": ["tests/a.py"], "reason": "renamed", "kind": "blocked"},
    }
    fields.update(overrides)
    return world.add_record(run.id, **fields)


def running(world: World) -> Run:
    run = world.add_run(status="running", park_kind=None, park_path=None, park_reason=None)
    world.add_rows(a_row(run.id, 1, BUILD, story_id="2-1", status="running"))
    return run


def test_an_accept_posts_one_channel_line_with_no_mention() -> None:
    world = World()
    world.add_channel()
    run = running(world)
    record = accepted(world, run)

    world.poll()

    assert world.chat.posts == [
        (
            "Mixed Signals / orchestrator · story 2-1 · the senior accepted test edits: "
            f"tests/a.py · renamed · {BASE_URL}/workflows/{run.id}",
            (),
        )
    ]
    notice = world.notices.notices[record.id]
    assert (notice.run_id, notice.created_at, notice.error) == (run.id, world.clock.now(), None)
    assert world.chat.suffixes == [f" · {BASE_URL}/workflows/{run.id}"]
    assert world.threads.threads == {}


def test_the_pass_alone_posts_the_projects_accepts_on_the_channel_it_is_given() -> None:
    world = World()
    channel = world.add_channel()
    accepted(world, running(world))

    post_notices(world.ports(), channel, world.chat, "")

    assert len(world.chat.posts) == 1


def test_a_second_fire_posts_nothing_more() -> None:
    world = World()
    world.add_channel()
    accepted(world, running(world))

    world.poll()
    world.poll()

    assert len(world.chat.posts) == 1


def test_an_accept_on_a_run_that_has_ended_is_still_posted() -> None:
    world = World()
    world.add_channel()
    run = running(world)
    world.update_run(run, status="done")
    accepted(world, run)

    world.poll()

    assert len(world.chat.posts) == 1


def test_an_accept_from_before_the_channel_existed_is_not_posted() -> None:
    world = World()
    channel = world.add_channel()
    accepted(world, running(world), at=channel.created_at - timedelta(seconds=1))

    world.poll()

    assert world.chat.posts == []


def test_fourteen_files_and_a_long_reason_are_cut() -> None:
    world = World()
    world.add_channel()
    files = [f"tests/t{n:02d}.py" for n in range(14)]
    accepted(world, running(world), payload={"files": files, "reason": "r" * 900})

    world.poll()

    ((line, _),) = world.chat.posts
    assert f"{', '.join(files[:10])} and 4 more · {'r' * 600} · " in line


def test_metadata_only_counts_the_files() -> None:
    world = World()
    world.add_channel(metadata_only=True)
    accepted(world, running(world), payload={"files": ["a", "b"], "reason": "secret"})

    world.poll()

    ((line, _),) = world.chat.posts
    assert "the senior accepted test edits to 2 files" in line
    assert "secret" not in line


def test_a_record_with_no_row_files_or_reason_still_posts() -> None:
    world = World()
    world.public_base_url = ""
    world.add_channel()
    accepted(world, running(world), path=None, payload={"files": "not a list"})

    world.poll()

    ((line, _),) = world.chat.posts
    assert line == "Mixed Signals / orchestrator · the senior accepted test edits: "


def test_no_unit_of_work_is_open_while_a_notice_is_sent() -> None:
    world = World()
    world.add_channel()
    accepted(world, running(world))
    seen: list[bool] = []
    world.chat.on_send = lambda: seen.append(world.uow.is_open)

    world.poll()

    assert seen == [False]


def test_a_refused_notice_keeps_its_masked_error_and_is_never_reposted() -> None:
    world = World()
    world.add_channel()
    record = accepted(world, running(world))
    world.chat.fail_next(ChatError(f"403 {TOKEN}"))

    world.poll()
    world.poll()

    assert world.notices.notices[record.id].error == "403 ***"
    assert world.chat.posts == []


def test_an_unexpected_notice_failure_keeps_its_class_name() -> None:
    world = World()
    world.add_channel()
    record = accepted(world, running(world))
    world.chat.fail_next(KeyError("x"))  # type: ignore[arg-type]

    with capture_logs() as logs:
        world.poll()

    assert world.notices.notices[record.id].error == "internal: KeyError"
    assert INTERNAL.format(name="KeyError") == "internal: KeyError"
    failed = [line for line in logs if line["event"] == "chat notice failed"]
    assert failed == [
        {
            "event": "chat notice failed",
            "log_level": "warning",
            "run_id": str(record.run_id),
            "gate_record_id": str(record.id),
            "error_class": "KeyError",
        }
    ]


def test_a_notice_another_fire_claimed_first_is_not_posted() -> None:
    world = World()
    world.add_channel()
    accepted(world, running(world))
    world.notices.add = lambda notice: False  # type: ignore[method-assign]

    world.poll()

    assert world.chat.posts == []


def test_a_claim_that_raises_is_logged_and_the_next_notice_still_posts() -> None:
    world = World()
    world.add_channel()
    run = running(world)
    first = accepted(world, run)
    accepted(world, run, at=world.clock.now() + timedelta(seconds=1))
    original = world.notices.add

    def explode(notice: Any) -> bool:
        if notice.gate_record_id == first.id:
            raise RuntimeError("boom")
        return original(notice)

    world.notices.add = explode  # type: ignore[method-assign]

    with capture_logs() as logs:
        world.poll()

    assert len(world.chat.posts) == 1
    assert [line["event"] for line in logs].count("chat notice failed") == 1
