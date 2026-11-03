"""`use_cases/chat_reply.py::close_thread`, the one close write (story 4-1), extended by 4-3's
review (2026-11-03) with an optional cursor and an optional `error`."""

from __future__ import annotations

from orchestrator.application.use_cases.chat_reply import close_thread
from tests.unit.fakes.chat_world import World


def test_a_close_without_a_cursor_keeps_the_threads_and_stores_the_error() -> None:
    world = World()
    thread = world.add_thread(world.add_run(), cursor="c4")
    world.clock.advance(300)

    close_thread(world.reply_ports(), thread, error="404 gone")

    stored = world.threads.threads[thread.id]
    assert (stored.state, stored.cursor, stored.error) == ("closed", "c4", "404 gone")
    assert stored.updated_at == world.clock.now()


def test_a_close_at_a_cursor_without_an_error_keeps_the_stored_error() -> None:
    world = World()
    thread = world.add_thread(world.add_run(), error="502 earlier")

    close_thread(world.reply_ports(), thread, "c9")

    stored = world.threads.threads[thread.id]
    assert (stored.state, stored.cursor, stored.error) == ("closed", "c9", "502 earlier")
