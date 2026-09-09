"""The `fake` harness's scenario file: what it reads, and what it refuses to raise about.

A scenario is test *input*, so every malformed shape has to have a stated outcome rather
than an exception — a YAML typo must fail the assertion a test actually makes, not the
dispatch. That is most of this module. The rest pins the two things the schema is keyed by:
the sentence the prompt carries, and which attempt this is.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import DISPATCH
from orchestrator.infrastructure.harness.fake import scenario as scenarios

SPEC_FOLDER = "specs/gates"
STORY_ID = "1"

#: The values the whole-document test scripts, named so the assertions read as one pair.
EXIT_CODE = 3
SLEEP_SECONDS = 0.25
SECOND_ATTEMPT = 2


def a_prompt(spec_folder: str = SPEC_FOLDER, story_id: str = STORY_ID) -> str:
    return DISPATCH.format(skill="bmad-build-auto", spec_folder=spec_folder, story_id=story_id)


# ── the dispatch sentence ───────────────────────────────────────────────────────────────


def test_the_two_facts_are_read_out_of_the_sentence_the_executor_actually_writes() -> None:
    """Built from `agent.py::DISPATCH` itself, so a change to the prompt fails here."""
    found = scenarios.dispatch_of(a_prompt())

    assert found == scenarios.Dispatch(spec_folder=SPEC_FOLDER, story_id=STORY_ID)


def test_the_clauses_a_template_and_an_answer_append_do_not_confuse_the_read() -> None:
    prompt = f"{a_prompt()} Read the brief. Halt after planning."

    assert scenarios.dispatch_of(prompt).story_id == STORY_ID


def test_a_prompt_with_no_dispatch_sentence_names_nothing() -> None:
    assert scenarios.dispatch_of("do something useful") == scenarios.Dispatch()


# ── the document ────────────────────────────────────────────────────────────────────────


def test_a_whole_scenario_is_read_field_for_field() -> None:
    parsed = scenarios.parse(
        'story_file: { slug: notify, content: "body" }\n'
        "files:\n"
        '  - { path: NOTIFY.md, content: "hello" }\n'
        "commit: true\n"
        "exit_code: 3\n"
        "sleep_seconds: 0.25\n"
        "echo_prompt: true\n"
        'usage: { tokens_in: 12, tokens_out: 34, cost_usd: "0.05" }\n'
    )

    assert parsed.story_file == scenarios.StoryFileSpec(slug="notify", content="body")
    assert parsed.files == (scenarios.FileSpec(path="NOTIFY.md", content="hello"),)
    assert parsed.commit is True
    assert parsed.exit_code == EXIT_CODE
    assert parsed.sleep_seconds == SLEEP_SECONDS
    assert parsed.echo_prompt is True
    assert parsed.usage is not None
    assert parsed.usage.cost_usd == Decimal("0.05")


def test_an_empty_document_is_the_do_nothing_scenario() -> None:
    parsed = scenarios.parse("")

    assert parsed == scenarios.Scenario()
    assert parsed.usage is None


@pytest.mark.parametrize(
    "text",
    ["- not: a mapping", "just a string", "key: [unclosed", "story_file: 3", "files: {}"],
    ids=["sequence", "scalar", "unparseable", "wrong-type", "files-not-a-list"],
)
def test_nothing_a_malformed_document_can_do_raises(text: str) -> None:
    parsed = scenarios.parse(text)

    assert parsed.story_file is None
    assert parsed.files == ()


def test_a_story_file_without_a_usable_slug_is_no_story_file() -> None:
    assert scenarios.parse("story_file: { slug: '   ' }").story_file is None
    assert scenarios.parse("story_file: { content: body }").story_file is None


def test_a_file_entry_without_a_path_is_dropped_and_the_rest_are_kept() -> None:
    parsed = scenarios.parse("files:\n  - { content: x }\n  - not-a-mapping\n  - { path: a.md }\n")

    assert parsed.files == (scenarios.FileSpec(path="a.md", content=""),)


def test_a_boolean_is_never_read_as_a_number() -> None:
    """`True` is an `int` in Python; an `exit_code: true` must not become exit code 1."""
    parsed = scenarios.parse("exit_code: true\nsleep_seconds: true\n")

    assert parsed.exit_code == 0
    assert parsed.sleep_seconds == 0.0


def test_usage_that_is_not_a_mapping_or_not_a_number_is_no_usage_at_all() -> None:
    """AD-11: a harness that reported nothing usable reported nothing, never zeroes."""
    assert scenarios.parse("usage: 3").usage is None
    assert scenarios.parse("usage: { cost_usd: 'n/a' }").usage is None


def test_usage_defaults_each_missing_figure_rather_than_dropping_the_whole_block() -> None:
    parsed = scenarios.parse("usage: { cost_usd: '1.50' }")

    assert parsed.usage is not None
    assert (parsed.usage.tokens_in, parsed.usage.tokens_out) == (0, 0)


# ── which scenario is next ──────────────────────────────────────────────────────────────


def test_the_numbered_scenario_wins_and_the_default_is_the_fallback(tmp_path: Path) -> None:
    directory = tmp_path / ".fake-harness" / STORY_ID
    directory.mkdir(parents=True)
    (directory / "default.yaml").write_text("commit: true")
    (directory / "attempt-2.yaml").write_text("commit: false")

    assert scenarios.scenario_path(tmp_path, STORY_ID, 2).name == "attempt-2.yaml"
    assert scenarios.scenario_path(tmp_path, STORY_ID, 1).name == "default.yaml"


def test_a_scenario_file_that_is_not_there_loads_as_the_empty_one(tmp_path: Path) -> None:
    assert scenarios.load(tmp_path / "nothing.yaml") == scenarios.Scenario()


def test_the_counter_advances_per_story_and_per_worktree(tmp_path: Path) -> None:
    work_dir, one, two = tmp_path / "work", tmp_path / "wt-a", tmp_path / "wt-b"

    assert scenarios.next_attempt(work_dir, one, "1") == 1
    assert scenarios.next_attempt(work_dir, one, "1") == SECOND_ATTEMPT
    assert scenarios.next_attempt(work_dir, one, "2") == 1
    assert scenarios.next_attempt(work_dir, two, "1") == 1


def test_the_counter_lives_under_the_work_dir_and_never_in_the_worktree(tmp_path: Path) -> None:
    """A file under `.fake-harness/` would be committed by the next attempt's WIP commit."""
    work_dir, worktree = tmp_path / "work", tmp_path / "wt"
    worktree.mkdir()

    scenarios.next_attempt(work_dir, worktree, STORY_ID)

    assert scenarios.counter_path(work_dir, worktree, STORY_ID).is_file()
    assert list(worktree.iterdir()) == []


def test_a_counter_that_cannot_be_read_starts_over_rather_than_raising(tmp_path: Path) -> None:
    work_dir, worktree = tmp_path / "work", tmp_path / "wt"
    counter = scenarios.counter_path(work_dir, worktree, STORY_ID)
    counter.parent.mkdir(parents=True)
    counter.write_text("not a number")

    assert scenarios.next_attempt(work_dir, worktree, STORY_ID) == 1
