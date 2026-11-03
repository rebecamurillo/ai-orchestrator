"""`apply_reply_batch` reads the channel and the step rows fresh under the lock (story 4-1
review, 2026-11-03): the session a fire shares keeps its identity map across commits, so a
plain read could hand a later batch the `allowed_users` or rows an earlier one saw."""

from __future__ import annotations

from orchestrator.application.use_cases.chat_reply import apply_reply_batch
from tests.unit.fakes.chat_world import World, a_reply, a_row

BUILD = "epics[1].stories[0].build"


def test_the_channel_and_the_rows_are_read_through_the_fresh_reads() -> None:
    world = World()
    world.add_channel()
    run = world.add_run()
    world.add_rows(a_row(run.id, 1, BUILD))
    thread = world.add_thread(run)

    apply_reply_batch(world.reply_ports(), thread, [a_reply(1)])

    assert world.channels.calls[:1] == [("get_current", run.project_id)]
    assert ("list_for_run_current", run.id) in world.steps.calls
    assert ("get", run.project_id) not in world.channels.calls
