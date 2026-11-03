"""`chat_poll`'s pass order with 4-2's passes (story 4-2, AD-25): per fire, the sweeps then
the close pass over every open thread; then per Project with a channel, post, remind,
accept notice, read, closing notice and watch, the watch skipped after a failed read."""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from orchestrator.application.jobs import chat_poll
from tests.unit.fakes.chat_world import World

PASSES = (
    "sweep_posting",
    "sweep_notices",
    "close_threads",
    "post_stops",
    "remind_threads",
    "post_notices",
    "read_replies",
    "post_close_notices",
    "watch_threads",
)


def recording(
    monkeypatch: pytest.MonkeyPatch, *, read_failed: bool = False, raising: str = ""
) -> list[str]:
    calls: list[str] = []
    for name in PASSES:

        def record(*_: Any, _name: str = name, **__: Any) -> bool:
            calls.append(_name)
            if _name == raising:
                raise RuntimeError("boom")
            return read_failed if _name == "read_replies" else False

        monkeypatch.setattr(chat_poll, name, record)
    return calls


def test_the_passes_run_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World()
    world.add_channel()
    calls = recording(monkeypatch)

    world.poll()

    assert calls == list(PASSES)


def test_the_watch_is_skipped_after_a_failed_read(monkeypatch: pytest.MonkeyPatch) -> None:
    world = World()
    world.add_channel()
    calls = recording(monkeypatch, read_failed=True)

    world.poll()

    assert calls == list(PASSES[:-1])


def test_the_close_pass_runs_once_per_fire_whatever_the_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    world.add_channel()
    other = world.add_project("Other")
    world.add_channel(other.id, channel_id="c2")
    calls = recording(monkeypatch)

    world.poll()

    assert calls.count("close_threads") == 1
    assert calls.count("watch_threads") == len(world.channels.list_all())

    calls.clear()
    world.channels.delete(world.project.id)
    world.channels.delete(other.id)
    world.poll()

    assert calls == ["sweep_posting", "sweep_notices", "close_threads"]


def test_an_unopened_channel_skips_the_notice_and_watch_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    world.add_channel(token_enc="never-issued")
    calls = recording(monkeypatch)

    world.poll()

    assert calls == ["sweep_posting", "sweep_notices", "close_threads", "post_stops"]


@pytest.mark.parametrize("raising", ["sweep_notices", "close_threads"])
def test_a_raising_fire_level_pass_is_logged_and_the_fire_goes_on(
    monkeypatch: pytest.MonkeyPatch, raising: str
) -> None:
    world = World()
    world.add_channel()
    calls = recording(monkeypatch, raising=raising)

    with capture_logs() as logs:
        world.poll()

    assert calls == list(PASSES)
    assert [line["error_class"] for line in logs if line["log_level"] == "warning"] == [
        "RuntimeError"
    ]
