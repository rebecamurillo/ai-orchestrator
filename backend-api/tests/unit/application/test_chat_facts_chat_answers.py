"""`jobs/chat_facts.py` and `rules/chat_message.py::chat_author`: an answer a thread reply
gave is shown as `{author} via {platform}` among a stop's earlier answers (story 4-1, AD-8's
2026-11-01 amendment; the rendering 3-3's review moved here)."""

from __future__ import annotations

from orchestrator.application.jobs.chat_facts import stop_facts
from orchestrator.application.rules.chat_message import Answer, chat_author
from tests.unit.fakes.chat_world import World

STORY = "epics[1].stories[0]"


def test_a_chat_answer_is_shown_by_its_author_and_platform() -> None:
    world = World()
    run = world.add_run()
    world.add_record(
        run.id, event="answer", actor="operator", path=f"{STORY}.build", payload={"text": "first"}
    )
    world.add_record(
        run.id,
        event="answer",
        actor="chat",
        path=f"{STORY}.build",
        payload={"text": "fix X", "platform": "slack", "author_id": "U1", "author": "alice"},
    )

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.answers == (Answer("Operator", "first"), Answer("alice via slack", "fix X"))


def test_the_author_and_platform_are_cleaned_and_kept_to_one_line() -> None:
    assert chat_author("al\u202eice\nbob", "matter\x00most") == "alice bob via mattermost"
