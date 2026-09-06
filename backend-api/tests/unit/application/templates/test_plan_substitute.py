"""Substitution at plan time: what a `{{ }}` becomes once a Run has values for it.

The one rule that is not obvious is the whole-variable rule. `story: "{{story}}"` binds the
list-file entry itself — a mapping — to the callee's `story` input, because a callee that
received the item's `str()` could not read `story.id` from it. Every other string is text
with holes in it, so each hole becomes text: `""` for a value nobody gave, never the four
characters `None`, which is what a Run would otherwise pass to a shell.

The whitelist is `expressions.ENTITY_FIELDS`, imported rather than restated: substitution
and validation disagreeing about which fields exist is the bug this module cannot have.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.templates.expressions import ENTITY_FIELDS
from orchestrator.application.templates.substitute import lookup, names_field, resolve
from tests.unit.application.templates import plan_fixtures as fixtures

ITEM: dict[str, Any] = {"id": "4-1", "title": "A story", "done_checkpoint": True}

COUNT = 3

SCOPE: dict[str, Any] = {
    "project": fixtures.PROJECT,
    "repository": fixtures.REPOSITORY,
    "branch": "feat/epic-1",
    "story": ITEM,
    "count": COUNT,
}


# --- the whole-variable rule ------------------------------------------------------------------


def test_a_string_that_is_exactly_one_variable_passes_the_value_through_whole() -> None:
    assert resolve("{{story}}", SCOPE) is ITEM


def test_the_whole_variable_rule_ignores_the_spaces_inside_the_braces() -> None:
    assert resolve("{{ story }}", SCOPE) is ITEM


def test_a_whole_variable_of_a_name_nothing_bound_is_the_empty_string() -> None:
    """`model: "{{model}}"` on a Run that named no model is no model, not the word None."""
    assert resolve("{{model}}", SCOPE) == ""


def test_a_whole_variable_keeps_a_non_text_value_as_it_is() -> None:
    assert resolve("{{count}}", SCOPE) == COUNT


# --- interpolation ------------------------------------------------------------------------------


def test_text_around_a_variable_is_kept_and_the_variable_is_filled_in() -> None:
    assert resolve("{{branch}}/stories.yaml", SCOPE) == "feat/epic-1/stories.yaml"


def test_two_variables_in_one_string_are_both_filled_in() -> None:
    assert resolve("{{branch}} — {{story.id}}", SCOPE) == "feat/epic-1 — 4-1"


def test_an_interpolated_value_nobody_bound_is_the_empty_string() -> None:
    assert resolve("model={{model}}", SCOPE) == "model="


def test_an_interpolated_number_is_its_text() -> None:
    assert resolve("n={{count}}", SCOPE) == f"n={COUNT}"


def test_an_expression_the_grammar_never_allowed_interpolates_to_nothing() -> None:
    """`validate()` refuses this text; `resolve` still has to answer something for it."""
    assert resolve("run {{ a b }} now", SCOPE) == "run  now"


def test_a_string_with_no_expression_at_all_is_returned_unchanged() -> None:
    assert resolve("make check", SCOPE) == "make check"


# --- fields --------------------------------------------------------------------------------------


def test_a_whitelisted_entity_field_is_read_off_the_snapshot() -> None:
    assert resolve("{{repository.quality_gate_command}}", SCOPE) == "make check"


def test_the_whitelist_is_the_validators_own() -> None:
    """A field the validator rejects has no value here either, whatever the snapshot holds."""
    assert "slug" not in ENTITY_FIELDS["repository"]
    assert resolve("{{repository.slug}}", SCOPE) == ""


def test_a_project_field_is_read_the_same_way() -> None:
    assert resolve("{{project.name}}", SCOPE) == "My Project"


def test_an_entity_field_the_repository_states_nothing_for_is_the_empty_string() -> None:
    scope = {**SCOPE, "repository": fixtures.NO_QUALITY_GATE}

    assert resolve("{{repository.quality_gate_command}}", scope) == ""


def test_a_field_of_a_list_file_entry_is_read_off_the_entry() -> None:
    assert resolve("{{story.title}}", SCOPE) == "A story"


def test_a_field_the_entry_does_not_hold_is_the_empty_string() -> None:
    assert resolve("{{story.nothing}}", SCOPE) == ""


def test_a_field_of_something_that_has_no_fields_is_nothing() -> None:
    assert lookup("branch", "id", SCOPE) is None


def test_lookup_without_a_field_answers_the_bound_value_itself() -> None:
    assert lookup("story", None, SCOPE) is ITEM


# --- naming a field ----------------------------------------------------------------------------


GATE = ("repository", "quality_gate_command")


def test_a_value_that_asks_for_a_field_by_name_says_so() -> None:
    assert names_field("{{repository.quality_gate_command}}", *GATE) is True


def test_a_value_that_asks_for_another_field_does_not() -> None:
    assert names_field("{{repository.unit_test_command}}", *GATE) is False


def test_a_value_that_asks_another_entity_for_the_same_field_does_not() -> None:
    """A Project has no quality gate to be missing, so this is `no command` (FR-8)."""
    assert names_field("{{project.quality_gate_command}}", *GATE) is False


def test_a_value_that_asks_for_no_field_at_all_does_not() -> None:
    assert names_field("{{extra}} && make check", *GATE) is False


def test_a_value_that_is_not_text_asks_for_nothing() -> None:
    assert names_field(None, *GATE) is False


# --- recursion ------------------------------------------------------------------------------------


def test_a_mapping_is_resolved_key_by_key() -> None:
    resolved = resolve({"base": "main", "branch": "{{branch}}"}, SCOPE)

    assert resolved == {"base": "main", "branch": "feat/epic-1"}


def test_a_sequence_is_resolved_entry_by_entry() -> None:
    assert resolve(["{{story.id}}", "x"], SCOPE) == ["4-1", "x"]


def test_a_nested_structure_is_resolved_all_the_way_down() -> None:
    resolved = resolve({"args": {"ids": ["{{story.id}}"]}}, SCOPE)

    assert resolved == {"args": {"ids": ["4-1"]}}


@pytest.mark.parametrize("value", [COUNT, True, None])
def test_anything_that_is_not_text_a_mapping_or_a_sequence_is_returned_as_it_is(
    value: object,
) -> None:
    assert resolve(value, SCOPE) is value
