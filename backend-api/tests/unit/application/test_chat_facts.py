"""`jobs/chat_facts.py::stop_facts`: what a stop's post is made of, read inside the claim
(story 3-3). Header facts, the epic's position, the consult entry that owns the stop, and the
last three answers of the stop's Story frame."""

from __future__ import annotations

from datetime import timedelta

from orchestrator.application.jobs.chat_facts import stop_facts
from orchestrator.application.rules.chat_message import Answer
from tests.unit.fakes.chat_world import World, a_row

URL = "https://orch.example.com/workflows/r"
STORY = "epics[1].stories[0]"


def test_the_header_facts_come_from_the_run_its_project_its_repository_and_its_row() -> None:
    world = World()
    run = world.add_run()
    world.add_rows(a_row(run.id, 1, f"{STORY}.build", label="build · 2-1", story_id="2-1"))

    facts = stop_facts(world.chat_ports(), run, URL)

    assert facts.project == "Mixed Signals"
    assert facts.repository == "orchestrator"
    assert facts.park_kind == "blocked"
    assert (facts.park_seq, facts.epic) == (3, 2)
    assert facts.folder == "specs/gates"
    assert facts.story_id == "2-1"
    assert facts.row_label == "build · 2-1"
    assert facts.question == "Which schema?"
    assert facts.senior_view is None
    assert facts.answers == ()
    assert facts.run_url == URL


def test_the_folder_falls_back_to_the_initiative_folder() -> None:
    world = World()
    run = world.add_run(inputs={"initiative_folder": "initiatives/x"})

    assert stop_facts(world.chat_ports(), run, None).folder == "initiatives/x"


def test_a_dependency_stop_has_no_row_no_epic_and_no_answers() -> None:
    world = World()
    run = world.add_run(park_kind="dependency", park_path=None, park_reason="waits on r0")

    facts = stop_facts(world.chat_ports(), run, None)

    assert (facts.row_label, facts.story_id, facts.epic, facts.answers) == (None, None, None, ())
    assert facts.question == "waits on r0"


def test_a_stop_with_no_project_repository_or_reason_reads_blank() -> None:
    world = World()
    run = world.add_run(project_id=world.add_project("Other").id, park_reason=None)
    world.projects.projects.clear()
    world.repositories.repositories.clear()

    facts = stop_facts(world.chat_ports(), run, None)

    assert (facts.project, facts.repository, facts.question) == ("", "", None)


def test_an_escalated_consult_on_the_park_row_splits_the_question_from_the_senior_view() -> None:
    world = World()
    run = world.add_run(park_reason="Q · senior: needs a product call")
    world.add_rows(
        a_row(
            run.id,
            1,
            f"{STORY}.build",
            consults={"blocked": {"state": "escalate", "question": "Q"}},
        )
    )

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.question == "Q"
    assert facts.senior_view == "senior: needs a product call"


def test_a_failed_consult_on_the_redispatch_target_owns_a_verify_failed_stop() -> None:
    world = World()
    verify = f"{STORY}.verify"
    run = world.add_run(
        park_kind="verify_failed",
        park_path=verify,
        park_reason="tests fail · consult failed: exited 1",
    )
    entry = {"state": "failed", "question": "tests fail", "park_path": verify}
    world.add_rows(
        a_row(run.id, 1, f"{STORY}.build", status="done", consults={"verify_failed": entry}),
        a_row(run.id, 2, verify, kind="shell"),
    )

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.question == "tests fail"
    assert facts.senior_view == "consult failed: exited 1"


def test_a_consult_that_is_not_escalated_or_does_not_prefix_the_reason_is_not_split() -> None:
    world = World()
    run = world.add_run(park_reason="Q · senior: x")
    world.add_rows(
        a_row(run.id, 1, f"{STORY}.build", consults={"blocked": {"state": "due", "question": "Q"}}),
        a_row(
            run.id,
            2,
            f"{STORY}.other",
            consults={"blocked": {"state": "escalate", "question": "Z", "park_path": "x"}},
        ),
        a_row(run.id, 3, f"{STORY}.third", consults={"blocked": "not an entry"}),
    )

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.question == "Q · senior: x"
    assert facts.senior_view is None


def test_an_escalated_entry_whose_question_does_not_prefix_the_reason_is_not_split() -> None:
    world = World()
    run = world.add_run(park_reason="the reason was rewritten")
    world.add_rows(
        a_row(
            run.id,
            1,
            f"{STORY}.build",
            consults={"blocked": {"state": "escalate", "question": "Q"}},
        )
    )

    facts = stop_facts(world.chat_ports(), run, None)

    assert (facts.question, facts.senior_view) == ("the reason was rewritten", None)


def test_the_last_three_answers_of_the_story_frame_oldest_first() -> None:
    world = World()
    run = world.add_run()
    build = f"{STORY}.build"
    answers = [
        ("answer", "operator", build, {"text": "one"}, ""),
        ("answer", "terminal", build, {"text": "two"}, ""),
        ("senior_answer", "senior", build, {"text": "clause"}, "three"),
        ("answer", "operator", "epics[1].stories[1].build", {"text": "outside"}, ""),
        ("answer", "operator", f"{STORY}.verify", {"text": "four"}, ""),
        ("continue", "operator", build, {}, "not an answer"),
        ("senior_answer", "senior", build, {}, "five"),
    ]
    for minute, (event, actor, path, payload, text) in enumerate(answers):
        world.add_record(
            run.id,
            event=event,
            actor=actor,
            path=path,
            payload=payload,
            text=text,
            at=world.clock.now() + timedelta(minutes=minute),
        )
    world.add_record(run.id, event="answer", actor="operator", path=None, payload={"text": "x"})

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.answers == (
        Answer("Senior", "three"),
        Answer("Operator", "four"),
        Answer("Senior", "five"),
    )


def test_an_answer_by_an_actor_with_no_label_is_left_out() -> None:
    world = World()
    run = world.add_run()
    world.add_record(
        run.id, event="answer", actor="machine", path=f"{STORY}.build", payload={"text": "x"}
    )

    assert stop_facts(world.chat_ports(), run, None).answers == ()


def test_a_stop_outside_any_story_frame_has_no_answers() -> None:
    world = World()
    run = world.add_run(park_path="epics[0].push", park_kind="push_rejected")
    world.add_record(run.id, event="answer", path="epics[0].push", payload={"text": "x"})

    facts = stop_facts(world.chat_ports(), run, None)

    assert facts.answers == ()
    assert facts.epic == 1
