"""`jobs/chat_poll.py::run_chat_poll`: one fire, the passes in the order sweep, post, remind,
notice, each Project isolated from the next, and nothing raised out (story 3-3, AD-25)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from structlog.testing import capture_logs

from orchestrator.application.jobs import chat_poll
from orchestrator.application.jobs.chat_ports import ChatPollPorts, redacted
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError
from tests.unit.application.chat_fixtures import HOURS, TOKEN, World, a_row

HOUR = 3600


def test_the_poll_ports_are_re_exported_where_4_3_extends_them() -> None:
    assert chat_poll.ChatPollPorts is ChatPollPorts


def test_a_project_with_no_channel_is_not_polled() -> None:
    world = World()
    world.add_run()

    world.poll()

    assert world.factory.opened == []
    assert world.chat.posts == []


def test_the_channel_is_opened_once_per_fire_with_the_decrypted_token() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.add_run(park_seq=5)

    world.poll()

    assert world.factory.opened == [("mattermost", "https://chat.example.com", "c1", TOKEN)]
    assert [len(world.chat.posts)] == [2]


def test_the_passes_run_sweep_post_remind_notice() -> None:
    world = World()
    world.add_channel()
    stale = world.add_run()
    world.threads.add(_thread(world, stale.id, state="posting", created_at=world.started_at))
    reminded = world.add_run(park_seq=7)
    world.threads.add(
        _thread(
            world,
            reminded.id,
            park_seq=7,
            ref="root",
            created_at=world.clock.now() - timedelta(hours=HOURS),
        )
    )
    posted = world.add_run(park_seq=9)
    world.add_record(posted.id, event="senior_accept", actor="senior", payload={"files": ["t"]})

    with capture_logs() as logs:
        world.poll()

    events = [line["event"] for line in logs]
    assert events.index("chat post interrupted") < events.index("chat thread posted")
    assert events.index("chat thread posted") < events.index("chat reminder sent")
    assert events.index("chat reminder sent") < events.index("chat notice posted")
    assert world.threads.get_by_stop(stale.id, 3).state == "failed"  # type: ignore[union-attr]


def test_one_projects_undecryptable_token_fails_its_due_stop_and_spares_the_next() -> None:
    world = World()
    a = world.project
    b = world.add_project("Beta")
    b_repository = world.add_repository(b.id, "beta")
    world.add_channel(a.id, token_enc="never-issued")
    world.add_channel(b.id)
    a_run = world.add_run()
    b_run = world.add_run(project_id=b.id, repository_id=b_repository.id)

    with capture_logs() as logs:
        world.poll()

    a_thread = world.threads.get_by_stop(a_run.id, 3)
    assert a_thread is not None
    assert (a_thread.state, a_thread.error, a_thread.ref) == (
        "failed",
        "channel could not be opened: DecryptionError",
        None,
    )
    assert world.threads.get_by_stop(b_run.id, 3).state == "open"  # type: ignore[union-attr]
    assert len(world.chat.posts) == 1
    naming_a = [line for line in logs if line.get("project_id") == str(a.id)]
    assert naming_a == [
        {
            "event": "chat channel could not be opened",
            "log_level": "warning",
            "project_id": str(a.id),
            "error_class": "DecryptionError",
        }
    ]


def test_a_refused_open_claims_due_stops_failed_with_its_redacted_detail() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    world.factory.error = ChatError(f"a Slack base URL must use https {TOKEN}")

    world.poll()

    thread = world.threads.get_by_stop(run.id, 3)
    assert thread is not None
    assert (thread.state, thread.error) == ("failed", "a Slack base URL must use https ***")


def test_an_unopened_channel_skips_the_remind_and_notice_passes() -> None:
    world = World()
    world.add_channel(token_enc="never-issued")
    run = world.add_run(park_seq=7)
    world.threads.add(
        _thread(world, run.id, park_seq=7, ref="r", created_at=world.started_at - timedelta(days=1))
    )
    world.add_record(run.id, event="senior_accept", actor="senior", payload={"files": ["t"]})

    world.poll()

    assert world.chat.replies == []
    assert world.notices.notices == {}


def test_a_failed_stop_stays_failed_after_the_channel_is_fixed() -> None:
    world = World()
    world.add_channel(token_enc="never-issued")
    world.add_run()
    world.poll()

    world.add_channel()
    world.poll()

    assert world.chat.posts == []
    assert world.only_thread().state == "failed"


def test_a_crypto_that_cannot_be_built_ends_the_fire_quietly() -> None:
    world = World()
    world.add_channel()
    world.add_run()
    world.crypto_error = ValueError("the key is the placeholder")

    with capture_logs() as logs:
        world.poll()

    assert world.chat.posts == []
    assert logs == [
        {"event": "chat poll failed", "log_level": "warning", "error_class": "ValueError"}
    ]


def test_a_failing_sweep_is_logged_and_the_fire_goes_on() -> None:
    world = World()
    world.add_channel()
    world.add_run()

    def explode(state: Any) -> Any:
        raise RuntimeError("boom")

    world.threads.list_by_state = explode  # type: ignore[method-assign]

    with capture_logs() as logs:
        world.poll()

    assert len(world.chat.posts) == 1
    assert "chat sweep failed" in [line["event"] for line in logs]


def test_a_project_whose_pass_raises_is_logged_and_the_next_project_is_polled() -> None:
    world = World()
    b = world.add_project("Beta")
    b_repository = world.add_repository(b.id, "beta")
    first = min(world.project.id, b.id)
    world.add_channel(world.project.id)
    world.add_channel(b.id)
    world.add_run()
    world.add_run(project_id=b.id, repository_id=b_repository.id)
    original = world.runs.list_by_status
    calls: list[int] = []

    def explode_once(status: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return original(status)

    world.runs.list_by_status = explode_once  # type: ignore[method-assign]

    with capture_logs() as logs:
        world.poll()

    assert len(world.chat.posts) == 1
    failed = [line for line in logs if line["event"] == "chat project failed"]
    assert failed == [
        {
            "event": "chat project failed",
            "log_level": "warning",
            "project_id": str(first),
            "error_class": "RuntimeError",
        }
    ]


def test_no_line_of_a_fire_carries_a_token_text_or_error_detail() -> None:
    world = World()
    world.add_channel()
    secret_question = "the-question-text-SECRET"
    run = world.add_run(park_reason=secret_question)
    world.add_rows(a_row(run.id, 1, "epics[1].stories[0].build"))
    other = world.add_run(park_seq=8, park_reason=secret_question)
    world.threads.add(
        _thread(
            world, other.id, park_seq=8, ref="r", created_at=world.started_at - timedelta(days=1)
        )
    )
    world.add_record(
        run.id, event="senior_accept", actor="senior", payload={"files": [secret_question]}
    )
    world.chat.fail_next(ChatError(f"403 {TOKEN} detail-SECRET"))
    world.add_project("Gamma")

    with capture_logs() as logs:
        world.poll()
        world.clock.advance(HOURS * HOUR)
        world.chat.fail_next(ChatError(f"500 {TOKEN} detail-SECRET"))
        world.poll()

    assert logs
    rendered = repr(logs)
    for secret in (TOKEN, "SECRET", "detail", secret_question):
        assert secret not in rendered


def test_the_token_is_masked_only_when_there_is_one() -> None:
    assert redacted("403 tok tok", "tok") == "403 *** ***"
    assert redacted("403 detail", "") == "403 detail"


def _thread(world: World, run_id: Any, **overrides: Any) -> ChatThread:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": run_id,
        "park_seq": 3,
        "park_kind": "blocked",
        "provider": "mattermost",
        "channel_id": "c1",
        "ref": None,
        "cursor": None,
        "state": "open",
        "error": None,
        "last_reminded_at": None,
        "created_at": world.clock.now(),
        "updated_at": world.clock.now(),
    }
    fields.update(overrides)
    return ChatThread(**fields)
