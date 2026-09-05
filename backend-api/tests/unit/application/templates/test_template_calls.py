"""Cross-template calls: resolution, bindings, depth and cycles.

Every callee is reached through the shared `TemplateVersionRepository` fake, so what these
tests prove is exactly what a use case may assume of the port: a stored version, or `None`.
Below the root the traversal reads `TemplateVersion.calls` — the callee list pinned when
that version was saved — which is why the fake's chains are built from refs and not from
YAML bodies.
"""

from __future__ import annotations

from orchestrator.application.templates.calls import check_calls
from orchestrator.application.templates.model import (
    CALL_CYCLE,
    CALL_DEPTH,
    CALLEE_INPUT_MISMATCH,
    CALLEE_NOT_FOUND,
)
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef
from tests.unit.application.templates import fixture, parsed, reasons
from tests.unit.application.templates.conftest import TRIVIAL, version
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HEAD = "name: caller\nversion: 1\n"

#: Where `HEAD + call(...)` puts the calling step.
CALL_LINE = 4


def call(name: str = "story", number: int = 1, bindings: str = "") -> str:
    body = f"steps:\n  - id: story\n    uses: template\n    with:\n      name: {name}\n"
    return body + f"      version: {number}\n" + bindings


def check(text: str, templates: FakeTemplateVersionRepository) -> list[str]:
    return reasons(check_calls(parsed(text), templates))


# --- resolution ---------------------------------------------------------------------------


def test_a_call_to_a_stored_version_resolves(templates: FakeTemplateVersionRepository) -> None:
    assert check(HEAD + call(), templates) == []


def test_a_call_to_a_version_that_is_not_stored_is_not_found(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check(HEAD + call(number=9), templates) == [CALLEE_NOT_FOUND]


def test_a_call_is_reported_at_the_line_of_the_calling_step(
    templates: FakeTemplateVersionRepository,
) -> None:
    found = check_calls(parsed(HEAD + call(number=9)), templates)

    assert [record.line for record in found] == [CALL_LINE]


def test_a_step_that_is_not_a_call_is_not_resolved(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check(HEAD + "steps:\n  - id: sync\n    uses: git.sync\n", templates) == []


def test_a_call_with_no_readable_with_is_left_to_the_key_table(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check(HEAD + "steps:\n  - id: s\n    uses: template\n", templates) == []


def test_a_call_whose_name_or_version_is_not_a_literal_is_left_to_the_key_table(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check(HEAD + call(number=0), templates) == []
    assert check(HEAD + call(name="[a]"), templates) == []


# --- bindings ------------------------------------------------------------------------------


def test_binding_an_input_the_callee_declares_is_accepted(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs:\n        spec_folder: docs/spec\n"

    assert check(HEAD + call(bindings=bindings), templates) == []


def test_binding_a_name_the_callee_does_not_declare_is_a_mismatch(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs:\n        wrong_name: anything\n"

    assert check(HEAD + call(bindings=bindings), templates) == [CALLEE_INPUT_MISMATCH]


def test_a_required_callee_input_that_is_never_bound_is_a_mismatch(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs: {}\n"

    assert check(HEAD + call(name="strict", bindings=bindings), templates) == [
        CALLEE_INPUT_MISMATCH
    ]


def test_a_call_with_no_inputs_block_still_owes_the_callee_what_it_requires(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check(HEAD + call(name="strict"), templates) == [CALLEE_INPUT_MISMATCH]


def test_a_number_bound_to_a_path_is_a_mismatch(
    templates: FakeTemplateVersionRepository,
) -> None:
    text = (
        HEAD
        + "inputs:\n  attempts:\n    type: number\n"
        + call(bindings="      inputs:\n        spec_folder: '{{attempts}}'\n")
    )

    assert check(text, templates) == [CALLEE_INPUT_MISMATCH]


def test_a_variable_of_the_declared_type_binds(
    templates: FakeTemplateVersionRepository,
) -> None:
    text = (
        HEAD
        + "inputs:\n  folder:\n    type: path\n"
        + call(bindings="      inputs:\n        spec_folder: '{{folder}}'\n")
    )

    assert check(text, templates) == []


def test_a_name_the_caller_never_declared_is_left_to_the_expression_rules(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs:\n        spec_folder: '{{missing}}'\n"

    assert check(HEAD + call(bindings=bindings), templates) == []


def test_text_with_interpolation_inside_it_binds_as_text(
    templates: FakeTemplateVersionRepository,
) -> None:
    text = (
        HEAD
        + "inputs:\n  folder:\n    type: path\n"
        + call(bindings="      inputs:\n        spec_folder: '{{folder}}/stories'\n")
    )

    assert check(text, templates) == []


def test_an_entity_input_takes_only_a_variable_of_exactly_that_type(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs:\n        repository: my-repo\n"
    text = HEAD + call(number=2, bindings=bindings)

    assert CALLEE_INPUT_MISMATCH in check(text, templates)


def test_a_number_literal_binds_a_number(templates: FakeTemplateVersionRepository) -> None:
    bindings = (
        "      inputs:\n"
        "        repository: '{{repository}}'\n"
        "        spec_folder: '{{folder}}'\n"
        "        story: '{{item}}'\n"
        "        attempts: 3\n"
    )
    text = (
        HEAD
        + "inputs:\n  repository:\n    type: repository\n"
        + "  folder:\n    type: path\n  item:\n    type: item\n"
        + call(number=2, bindings=bindings)
    )

    assert check(text, templates) == []


def test_a_value_that_is_neither_text_nor_a_number_binds_nothing(
    templates: FakeTemplateVersionRepository,
) -> None:
    bindings = "      inputs:\n        spec_folder: true\n"

    assert check(HEAD + call(bindings=bindings), templates) == [CALLEE_INPUT_MISMATCH]


def test_the_item_of_a_loop_binds_an_item_input(
    templates: FakeTemplateVersionRepository,
) -> None:
    text = (
        "name: epic\nversion: 1\n"
        + "inputs:\n  repository:\n    type: repository\n  spec_folder:\n    type: path\n"
        + "steps:\n  - id: stories\n    for_each: '{{spec_folder}}/stories.yaml'\n    as: story\n"
        + "    steps:\n      - id: story\n        uses: template\n        with:\n"
        + "          name: story\n          version: 2\n          inputs:\n"
        + "            repository: '{{repository}}'\n"
        + "            spec_folder: '{{spec_folder}}'\n"
        + "            story: '{{story}}'\n"
    )

    assert check(text, templates) == []


def test_a_callee_whose_body_does_not_parse_declares_nothing(
    templates: FakeTemplateVersionRepository,
) -> None:
    templates.add(version("broken", 1, "name: broken\n  version: 1\n"))
    bindings = "      inputs:\n        anything: 1\n"

    assert check(HEAD + call(name="broken", bindings=bindings), templates) == [
        CALLEE_INPUT_MISMATCH
    ]


# --- depth and cycles ------------------------------------------------------------------------


def test_a_chain_of_three_templates_is_the_deepest_that_passes(
    templates: FakeTemplateVersionRepository,
) -> None:
    """initiative -> epic -> story: the root is 1, so this reaches 3."""
    assert check(fixture("initiative-chain"), templates) == []


def test_a_fourth_template_in_the_chain_is_too_deep(
    templates: FakeTemplateVersionRepository,
) -> None:
    """a -> b -> c -> d reaches 4."""
    assert check(fixture("call-depth-over-3"), templates) == [CALL_DEPTH]


def test_a_chain_that_returns_to_the_root_is_a_cycle(
    templates: FakeTemplateVersionRepository,
) -> None:
    assert check("name: a\nversion: 1\n" + call(name="cycle-b"), templates) == [CALL_CYCLE]


def test_a_chain_that_returns_to_a_middle_template_is_a_cycle_too(
    templates: FakeTemplateVersionRepository,
) -> None:
    templates.add(version("ring", 1, TRIVIAL, TemplateRef(name="ring-back", version=1)))
    templates.add(version("ring-back", 1, TRIVIAL, TemplateRef(name="ring", version=1)))

    assert check(HEAD + call(name="ring"), templates) == [CALL_CYCLE]


def test_two_steps_calling_the_same_callee_are_a_diamond_and_not_a_cycle(
    templates: FakeTemplateVersionRepository,
) -> None:
    templates.add(
        version(
            "fan",
            1,
            TRIVIAL,
            TemplateRef(name="story", version=1),
            TemplateRef(name="story", version=1),
        )
    )

    assert check(HEAD + call(name="fan"), templates) == []


def test_a_callee_pinned_by_a_callee_that_is_no_longer_stored_is_not_found(
    templates: FakeTemplateVersionRepository,
) -> None:
    templates.add(version("dangling", 1, TRIVIAL, TemplateRef(name="gone", version=1)))

    assert check(HEAD + call(name="dangling"), templates) == [CALLEE_NOT_FOUND]


def test_a_root_that_never_named_itself_pushes_nothing_onto_the_call_path(
    templates: FakeTemplateVersionRepository,
) -> None:
    """A file with no `name` is already an error; the descent still runs and still ends."""
    assert check(call(name="epic"), templates) == []
    assert check(call(number=9), templates) == [CALLEE_NOT_FOUND]


def test_a_template_that_calls_itself_is_a_cycle(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The shortest cycle there is, and the one a pinned `calls` list never has to show."""
    templates.add(version("self", 1, TRIVIAL))

    assert check("name: self\nversion: 1\n" + call(name="self"), templates) == [CALL_CYCLE]


def test_a_template_calling_a_different_version_of_itself_is_not_a_cycle(
    templates: FakeTemplateVersionRepository,
) -> None:
    templates.add(version("story", 3, TRIVIAL))

    assert check("name: story\nversion: 1\n" + call(name="story", number=3), templates) == []


def test_one_missing_callee_pinned_twice_is_reported_once(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Two identical records for one mistake; the matrix promises one error per row."""
    gone = TemplateRef(name="gone", version=1)
    templates.add(version("pins-twice", 1, TRIVIAL, gone, gone))
    result = validate("name: c\nversion: 1\n" + call(name="pins-twice"), templates=templates)

    assert [(record.reason, record.line) for record in result.errors] == [
        (CALLEE_NOT_FOUND, CALL_LINE)
    ]
