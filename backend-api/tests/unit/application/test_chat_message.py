"""`rules/chat_message.py`: the stop post, the reminder and the senior-accept line (story 3-3).

Pure functions over `StopFacts` and `AcceptFacts`. They pin the line order, the omissions,
the untrusted-text rules, the caps and the cut order, the marker, and `metadata_only`.
"""

from __future__ import annotations

import re
from uuid import UUID

import pytest

from orchestrator.application.rules.chat_message import (
    ANSWER_CAP,
    CONTINUATION,
    CUT_MARKER,
    FIELD_CAP,
    MAX_POST_CHARS,
    PAGE_ACTION,
    QUESTION_CAP,
    REASON_CAP,
    REPLY_ACTION,
    SENIOR_VIEW_CAP,
    AcceptFacts,
    Answer,
    StopFacts,
    accept_line,
    action_line,
    compose_stop,
    neutralise,
    reminder_text,
    run_link,
)

URL = "https://orch.example.com/workflows/r1"


def facts(**overrides: object) -> StopFacts:
    fields: dict[str, object] = {
        "project": "Mixed Signals",
        "repository": "orchestrator",
        "park_kind": "blocked",
        "park_seq": 3,
        "folder": "specs/gates",
        "epic": 2,
        "story_id": "2-1",
        "row_label": "build",
        "question": "Which schema?",
        "senior_view": None,
        "answers": (),
        "run_url": URL,
    }
    fields.update(overrides)
    return StopFacts(**fields)  # type: ignore[arg-type]


# ── the stop post ──────────────────────────────────────────────────────────────────────────


def test_a_blocked_stop_is_written_one_fact_per_line_in_the_pinned_order() -> None:
    text = compose_stop(
        facts(
            senior_view="senior: needs a product call",
            answers=(Answer("Operator", "use v2"), Answer("Senior", "v2 it is")),
        ),
        metadata_only=False,
    )

    assert text.split("\n") == [
        "Run needs you · Mixed Signals / orchestrator · blocked · stop 3",
        "Initiative: specs/gates",
        "Epic: 2",
        "Story: 2-1",
        "Row: build",
        "Question: Which schema?",
        "Senior's view: senior: needs a product call",
        "Earlier answers in this story:",
        "- Operator: use v2",
        "- Senior: v2 it is",
        REPLY_ACTION,
        f"Run: {URL}",
    ]


@pytest.mark.parametrize("kind", ["checkpoint", "budget", "dependency", "verify_failed"])
def test_every_other_stop_links_to_the_run_page(kind: str) -> None:
    text = compose_stop(facts(park_kind=kind), metadata_only=False)

    assert PAGE_ACTION in text.split("\n")
    assert REPLY_ACTION not in text


def test_the_action_line_invites_a_reply_only_at_a_blocked_stop() -> None:
    assert action_line("blocked") == (
        "Reply in this thread and mention the bot to answer. "
        "The first allowed reply resumes the agent."
    )
    assert action_line("checkpoint") == "Act on the Run page."


def test_a_missing_fact_leaves_its_line_out() -> None:
    text = compose_stop(
        facts(
            park_kind="dependency",
            folder="",
            epic=None,
            story_id=None,
            row_label=None,
            question=None,
            run_url=None,
        ),
        metadata_only=False,
    )

    assert text.split("\n") == [
        "Run needs you · Mixed Signals / orchestrator · dependency · stop 3",
        PAGE_ACTION,
    ]


def test_a_question_that_is_only_control_characters_is_left_out() -> None:
    text = compose_stop(facts(question="\x00\t"), metadata_only=False)

    assert "Question:" not in text


def test_metadata_only_keeps_the_facts_and_drops_the_question_view_and_answers() -> None:
    text = compose_stop(
        facts(
            question="secret question text",
            senior_view="secret senior text",
            answers=(Answer("Operator", "secret answer text"),),
        ),
        metadata_only=True,
    )

    assert text.split("\n") == [
        "Run needs you · Mixed Signals / orchestrator · blocked · stop 3",
        "Initiative: specs/gates",
        "Epic: 2",
        "Story: 2-1",
        "Row: build",
        REPLY_ACTION,
        f"Run: {URL}",
    ]
    assert "secret" not in text


# ── untrusted text ─────────────────────────────────────────────────────────────────────────

HOSTILE = "first\n# h\n```\nrm -rf /\n```\n> q\n@channel\u202e\x00\tend\r\nlast\u2066"


def test_neutralise_drops_controls_and_bidi_and_prefixes_every_continuation_line() -> None:
    assert neutralise("a\x00b\tc\u202ad\u202ee\u2066f\u2069g\x7f\x1bh") == "abcdefgh"
    assert neutralise("one\ntwo\r\nthree") == f"one\n{CONTINUATION}two\n{CONTINUATION}three"


def test_hostile_text_never_starts_a_line_fence_heading_or_quote() -> None:
    text = compose_stop(
        facts(
            question=HOSTILE,
            senior_view=HOSTILE,
            answers=(Answer("Operator", HOSTILE),),
        ),
        metadata_only=False,
    )

    for character in ("\x00", "\t", "\r", "\u202e", "\u2066"):
        assert character not in text
    for line in text.split("\n"):
        assert not re.match(r"\s*(#|```|>)", line), line
    assert f"\n{CONTINUATION}# h" in text
    assert f"\n{CONTINUATION}> q" in text
    assert "@channel" in text  # neutralising a mention is the adapter's job (D1)


def test_the_facts_this_system_wrote_are_cleaned_too() -> None:
    text = compose_stop(facts(project="Mixed\nSignals", row_label="build\x00"), metadata_only=False)

    assert f"Mixed\n{CONTINUATION}Signals" in text
    assert "Row: build\n" in text


# ── length ─────────────────────────────────────────────────────────────────────────────────


def test_each_field_is_capped_and_a_cap_writes_the_marker_once() -> None:
    text = compose_stop(
        facts(
            project="p" * 300,
            repository="r" * 300,
            folder="f" * 300,
            story_id="s" * 300,
            row_label="l" * 300,
            question="q" * 2000,
        ),
        metadata_only=False,
    )

    lines = text.split("\n")
    assert lines[0] == f"Run needs you · {'p' * FIELD_CAP} / {'r' * FIELD_CAP} · blocked · stop 3"
    assert f"Initiative: {'f' * FIELD_CAP}" in lines
    assert f"Story: {'s' * FIELD_CAP}" in lines
    assert f"Row: {'l' * FIELD_CAP}" in lines
    assert f"Question: {'q' * QUESTION_CAP}" in lines
    assert lines.count(CUT_MARKER) == 1
    assert lines[-3:] == [CUT_MARKER, REPLY_ACTION, f"Run: {URL}"]
    assert len(text) <= MAX_POST_CHARS


def test_the_senior_view_and_each_answer_are_capped() -> None:
    text = compose_stop(
        facts(senior_view="v" * 900, answers=(Answer("Operator", "a" * 400),)),
        metadata_only=False,
    )

    lines = text.split("\n")
    assert f"Senior's view: {'v' * SENIOR_VIEW_CAP}" in lines
    assert f"- Operator: {'a' * ANSWER_CAP}" in lines
    assert lines.count(CUT_MARKER) == 1


def test_a_ten_thousand_character_question_fits_with_the_marker_action_and_link() -> None:
    text = compose_stop(facts(question="x" * 10_000), metadata_only=False)

    assert len(text) <= MAX_POST_CHARS
    assert text.split("\n")[-3:] == [CUT_MARKER, REPLY_ACTION, f"Run: {URL}"]


def _answers(count: int, size: int) -> tuple[Answer, ...]:
    return tuple(Answer("Operator", f"{n:03d}" + "a" * (size - 3)) for n in range(count))


def _exactly(length: int, **overrides: object) -> StopFacts:
    """Facts whose uncut text is `length` code points, padded through the question."""
    size = len(compose_stop(facts(question="q", **overrides), metadata_only=False))
    question = "q" * (length - size + 1)
    assert len(question) <= QUESTION_CAP
    return facts(question=question, **overrides)


#: Three capped answers and a capped senior's view, so the padding question stays under its cap.
FULL: dict[str, object] = {
    "answers": _answers(3, ANSWER_CAP),
    "senior_view": "v" * SENIOR_VIEW_CAP,
    "project": "p" * 150,
}


def test_a_text_of_exactly_the_limit_is_sent_whole() -> None:
    sent = _exactly(MAX_POST_CHARS, **FULL)

    text = compose_stop(sent, metadata_only=False)

    assert len(text) == MAX_POST_CHARS
    assert CUT_MARKER not in text


def test_one_code_point_over_cuts_the_oldest_answer_line_first() -> None:
    over = _exactly(MAX_POST_CHARS + 1, **FULL)

    text = compose_stop(over, metadata_only=False)

    assert len(text) <= MAX_POST_CHARS
    assert "- Operator: 000" not in text
    assert "- Operator: 001" in text
    assert "- Operator: 002" in text
    assert f"Senior's view: {'v' * SENIOR_VIEW_CAP}" in text
    assert text.split("\n")[-3:] == [CUT_MARKER, REPLY_ACTION, f"Run: {URL}"]


def test_after_every_answer_the_senior_view_is_cut_from_its_end_then_the_question() -> None:
    long_url = "https://orch.example.com/" + "u" * 1200
    text = compose_stop(
        facts(
            question="Q" * QUESTION_CAP,
            senior_view="V" * SENIOR_VIEW_CAP,
            answers=_answers(3, ANSWER_CAP),
            run_url=long_url,
            project="p" * FIELD_CAP,
            repository="r" * FIELD_CAP,
            folder="f" * FIELD_CAP,
            story_id="s" * FIELD_CAP,
            row_label="l" * FIELD_CAP,
        ),
        metadata_only=False,
    )

    assert len(text) <= MAX_POST_CHARS
    assert "Earlier answers" not in text
    assert "Senior's view:" not in text
    question = next(line for line in text.split("\n") if line.startswith("Question: "))
    assert 0 < len(question) - len("Question: ") < QUESTION_CAP
    assert text.split("\n")[-3:] == [CUT_MARKER, REPLY_ACTION, f"Run: {long_url}"]


def test_a_cut_senior_view_keeps_its_start() -> None:
    text = compose_stop(
        facts(
            question="Q" * QUESTION_CAP,
            senior_view="start" + "V" * (SENIOR_VIEW_CAP - 5),
            run_url="https://orch.example.com/" + "u" * 800,
            project="p" * FIELD_CAP,
            repository="r" * FIELD_CAP,
        ),
        metadata_only=False,
    )

    assert len(text) <= MAX_POST_CHARS
    view = next(line for line in text.split("\n") if line.startswith("Senior's view: "))
    assert view.startswith("Senior's view: start")
    assert f"Question: {'Q' * QUESTION_CAP}" in text


def test_a_cut_that_empties_the_question_drops_its_line() -> None:
    text = compose_stop(
        facts(question="Q" * 10, run_url="https://orch.example.com/" + "u" * 2_900),
        metadata_only=False,
    )

    assert "Question:" not in text
    assert CUT_MARKER in text


# ── the reminder ───────────────────────────────────────────────────────────────────────────


def test_a_reminder_names_the_stop_its_age_the_action_and_the_link() -> None:
    assert reminder_text("blocked", 3, 4, URL).split("\n") == [
        "Still waiting · blocked · stop 3 · parked 4 h",
        REPLY_ACTION,
        f"Run: {URL}",
    ]


def test_a_reminder_with_no_link_and_another_kind_links_to_the_page() -> None:
    assert reminder_text("budget", 7, 12, None).split("\n") == [
        "Still waiting · budget · stop 7 · parked 12 h",
        PAGE_ACTION,
    ]


# ── the senior-accept line ─────────────────────────────────────────────────────────────────


def accept(**overrides: object) -> AcceptFacts:
    fields: dict[str, object] = {
        "project": "Mixed Signals",
        "repository": "orchestrator",
        "story_id": "2-1",
        "files": ("tests/a.py", "tests/b.py"),
        "reason": "the story renames the field",
        "run_url": URL,
    }
    fields.update(overrides)
    return AcceptFacts(**fields)  # type: ignore[arg-type]


def test_the_accept_line_names_the_files_the_reason_and_the_link() -> None:
    assert accept_line(accept(), metadata_only=False) == (
        "Mixed Signals / orchestrator · story 2-1 · the senior accepted test edits: "
        f"tests/a.py, tests/b.py · the story renames the field · {URL}"
    )


def test_fourteen_files_show_ten_names_and_a_long_reason_is_cut_to_six_hundred() -> None:
    files = tuple(f"tests/t{n:02d}.py" for n in range(14))

    line = accept_line(accept(files=files, reason="r" * 900), metadata_only=False)

    names = ", ".join(files[:10])
    assert f"edits: {names} and 4 more · {'r' * REASON_CAP} · {URL}" in line
    assert "r" * (REASON_CAP + 1) not in line
    assert "tests/t10.py" not in line


def test_the_accept_line_with_no_story_no_reason_and_no_link() -> None:
    line = accept_line(accept(story_id=None, reason="", run_url=None), metadata_only=False)

    assert line == (
        "Mixed Signals / orchestrator · the senior accepted test edits: tests/a.py, tests/b.py"
    )


def test_metadata_only_counts_the_files_and_names_none() -> None:
    line = accept_line(accept(), metadata_only=True)

    assert line == (
        "Mixed Signals / orchestrator · story 2-1 · the senior accepted test edits to 2 files"
        f" · {URL}"
    )


def test_the_accept_line_neutralises_its_untrusted_text() -> None:
    line = accept_line(
        accept(files=("tests/\u202ea.py",), reason="why\n# heading\x00"), metadata_only=False
    )

    assert "\u202e" not in line
    assert "\x00" not in line
    assert f"why\n{CONTINUATION}# heading" in line


def test_the_accept_line_never_exceeds_the_limit_and_keeps_its_link() -> None:
    files = tuple("tests/" + "n" * 400 + f"{n}.py" for n in range(10))

    line = accept_line(accept(files=files), metadata_only=False)

    assert len(line) <= MAX_POST_CHARS
    assert line.endswith(f" · {URL}")


# ── the link ───────────────────────────────────────────────────────────────────────────────


def test_the_run_link_is_the_web_clients_path_or_none_without_a_base() -> None:
    run_id = UUID(int=1)

    assert run_link("https://orch.example.com/", run_id) == (
        f"https://orch.example.com/workflows/{run_id}"
    )
    assert run_link("  ", run_id) is None
