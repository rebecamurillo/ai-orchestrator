"""`lines.py` — the loader that records positions, and the readers of what it returns.

Two things are proved here. That a line number is the line the Operator has to look at:
a key's own line for a key or its scalar value, and a child's own line for a nested mapping
or sequence. And that nothing raises: text that is not YAML, text that is empty, and a root
that is not a mapping are all answered as "no document" with a line to report it at.
"""

from __future__ import annotations

import yaml

from orchestrator.application.templates.lines import (
    FIRST_LINE,
    LinedMap,
    LinedSeq,
    LineLoader,
    _error_line,
    as_map,
    as_seq,
    child_steps,
    is_for_each,
    iter_steps,
    key_line,
    line_of,
    load_with_lines,
)
from tests.unit.application.templates import parsed

#: Where each node of `TEMPLATE` below begins, so no assertion carries a bare number.
VERSION_LINE = 2
BRANCH_INPUT_LINE = 5
STEPS_LINE = 7
USES_LINE = 8
GATE_LINE = 9

#: A line no node of `TEMPLATE` begins on, offered as the fallback.
ABSENT = 99

TEMPLATE = """name: story
version: 1
inputs:
  branch:
    type: string
steps:
  - id: sync
    uses: git.sync
    gate: deterministic
"""


def test_the_root_mapping_starts_on_the_first_line() -> None:
    assert parsed(TEMPLATE).line == 1


def test_each_key_carries_its_own_line() -> None:
    assert parsed(TEMPLATE).key_lines == {"name": 1, "version": 2, "inputs": 3, "steps": 6}


def test_a_nested_mapping_carries_the_line_it_began_on() -> None:
    root = parsed(TEMPLATE)

    assert as_map(root["inputs"])["branch"].line == BRANCH_INPUT_LINE  # type: ignore[index]


def test_a_sequence_carries_the_line_it_began_on() -> None:
    assert as_seq(parsed(TEMPLATE)["steps"]).line == STEPS_LINE  # type: ignore[union-attr]


def test_a_step_mapping_carries_the_line_of_each_of_its_keys() -> None:
    step = child_steps(parsed(TEMPLATE))[0]

    assert step.key_lines == {"id": STEPS_LINE, "uses": USES_LINE, "gate": GATE_LINE}


def test_the_loader_constructs_no_arbitrary_object() -> None:
    """It subclasses `SafeLoader`, so a python tag is refused rather than executed."""
    assert issubclass(LineLoader, yaml.SafeLoader)
    assert load_with_lines("!!python/object/apply:os.system ['echo']\n").root is None


# --- what is not a document ---------------------------------------------------------------


def test_text_that_does_not_parse_is_reported_at_the_line_the_loader_stopped_on() -> None:
    loaded = load_with_lines("name: story\nsteps:\n  - id: a\n   uses: shell\n")

    assert loaded.root is None
    assert loaded.line > FIRST_LINE


def test_empty_text_is_no_document_at_all() -> None:
    loaded = load_with_lines("")

    assert loaded.root is None
    assert loaded.line == FIRST_LINE


def test_a_root_that_is_not_a_mapping_is_no_document_either() -> None:
    loaded = load_with_lines("- one\n- two\n")

    assert loaded.root is None
    assert loaded.line == FIRST_LINE


def test_a_failure_that_names_no_position_is_reported_on_the_first_line() -> None:
    """A `ReaderError` — an unacceptable character — carries no mark of any kind."""
    loaded = load_with_lines("name: story\ndescription: \x00\n")

    assert loaded.root is None
    assert loaded.line == FIRST_LINE


def test_the_line_of_a_failure_is_read_from_its_mark_when_it_has_one() -> None:
    assert _error_line(yaml.YAMLError("no mark at all")) == FIRST_LINE


# --- the readers ---------------------------------------------------------------------------


def test_a_mapping_reads_back_as_a_mapping_and_anything_else_as_nothing() -> None:
    assert as_map(parsed(TEMPLATE)) is not None
    assert as_map("steps") is None


def test_a_sequence_reads_back_as_a_sequence_and_anything_else_as_nothing() -> None:
    assert as_seq(parsed(TEMPLATE)["steps"]) is not None
    assert as_seq({"a": 1}) is None


def test_a_node_with_no_position_of_its_own_falls_back_to_the_line_offered() -> None:
    assert line_of(parsed(TEMPLATE), ABSENT) == FIRST_LINE
    assert line_of("a scalar", ABSENT) == ABSENT


def test_a_key_the_mapping_does_not_hold_falls_back_to_the_line_offered() -> None:
    root = parsed(TEMPLATE)

    assert key_line(root, "version", ABSENT) == VERSION_LINE
    assert key_line(root, "schedule", ABSENT) == ABSENT


def test_a_containers_own_defaults_are_the_first_line_until_the_loader_sets_them() -> None:
    assert LinedMap().line == FIRST_LINE
    assert LinedMap().key_lines == {}
    assert LinedSeq().line == FIRST_LINE


def test_a_file_with_no_steps_key_has_no_child_steps() -> None:
    assert child_steps(parsed("name: story\nversion: 1\n")) == []


def test_a_steps_key_that_is_not_a_list_has_no_child_steps() -> None:
    assert child_steps(parsed("name: story\nsteps: everything\n")) == []


def test_an_entry_of_steps_that_is_not_a_mapping_is_skipped() -> None:
    root = parsed("name: story\nsteps:\n  - sync\n  - id: verify\n    uses: git.sync\n")

    assert [step["id"] for step in child_steps(root)] == ["verify"]


def test_the_loop_construct_is_recognised_by_its_key() -> None:
    root = parsed(
        "name: story\nsteps:\n  - id: epics\n    for_each: '{{f}}'\n    as: epic\n"
        "    steps:\n      - id: sync\n        uses: git.sync\n"
    )

    assert is_for_each(child_steps(root)[0])
    assert not is_for_each(child_steps(root)[0]["steps"][0])


def test_walking_the_file_pairs_each_nested_step_with_the_item_in_scope() -> None:
    root = parsed(
        "name: story\nsteps:\n  - id: checkout\n    uses: git.sync\n"
        "  - id: epics\n    for_each: '{{f}}'\n    as: epic\n"
        "    steps:\n      - id: sync\n        uses: git.sync\n"
    )

    assert [(node["id"], item) for node, item in iter_steps(root)] == [
        ("checkout", None),
        ("epics", None),
        ("sync", "epic"),
    ]


def test_a_loop_whose_as_name_is_not_a_name_binds_nothing() -> None:
    root = parsed(
        "name: story\nsteps:\n  - id: epics\n    for_each: '{{f}}'\n    as: 3\n"
        "    steps:\n      - id: sync\n        uses: git.sync\n"
    )

    assert [item for _, item in iter_steps(root)] == [None, None]
