"""Loops within loops, and `bind` (story 2, 2026-11-06, AD-15 amendment).

Cases are written as inline YAML so each one names the single line it reports at.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.templates.lines import LinedMap, load_with_lines
from orchestrator.application.templates.loops import check_bind, check_for_each
from orchestrator.application.templates.model import (
    CALLEE_INPUT_MISMATCH,
    DUPLICATE_STEP_ID,
    INVALID_SLUG,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    LOOP_NAME_BOUND,
    NESTED_FOR_EACH,
    SECOND_FOR_EACH,
    UNBOUND_VARIABLE,
    UNKNOWN_FIELD,
    ValidationError,
)
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.templates import FakeTemplateVersionRepository

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "nested"

HEAD = """name: t
version: 1
inputs:
  spec_folder: { type: path, required: true }
  branch: { type: string, required: true }
"""

SYNC = "uses: git.sync\n"
GATE = "gate: deterministic\n"


def errors_of(
    text: str, repo: FakeTemplateVersionRepository | None = None
) -> list[tuple[int, str]]:
    result = validate(text, templates=repo or FakeTemplateVersionRepository())
    return [(error.line, error.reason) for error in result.errors]


def loop(  # noqa: PLR0913 - one keyword per part of the YAML a case needs to vary
    ident: str,
    source: str,
    as_name: str,
    inner: str,
    *,
    extra: str = "",
    indent: int = 2,
) -> str:
    """One loop whose body is `inner` (already indented for it)."""
    pad = " " * indent
    return (
        f"{pad}- id: {ident}\n{pad}  for_each: '{source}'\n{pad}  as: {as_name}\n{extra}"
        f"{pad}  steps:\n{inner}"
    )


def sync(ident: str, indent: int) -> str:
    pad = " " * indent
    return f"{pad}- id: {ident}\n{pad}  {SYNC}{pad}  {GATE}"


# --- AC1 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["depth-0", "depth-1", "depth-2", "depth-2-pre-post"])
def test_each_owned_fixture_validates(name: str) -> None:
    text = (FIXTURES / f"{name}.yaml").read_text()

    assert errors_of(text) == []


# --- AC5 ----------------------------------------------------------------------------------


def test_a_loop_three_deep_is_refused_at_the_third_loops_line() -> None:
    third = loop("c", "{{spec_folder}}/c.yaml", "z", sync("s", 10), indent=8)
    second = loop("b", "{{spec_folder}}/b.yaml", "y", third, indent=4)
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "x", second)

    lines = text.splitlines()
    third_line = next(i for i, row in enumerate(lines, 1) if row.strip() == "- id: c")
    assert errors_of(text) == [(third_line, NESTED_FOR_EACH)]


def test_two_loops_in_one_list_are_a_second_for_each() -> None:
    first = loop("a", "{{spec_folder}}/a.yaml", "x", sync("s", 6))
    second = loop("b", "{{spec_folder}}/b.yaml", "y", sync("t", 6))
    text = HEAD + "steps:\n" + first + second

    assert [reason for _, reason in errors_of(text)] == [SECOND_FOR_EACH]


def test_two_loops_in_an_inner_list_are_a_second_for_each() -> None:
    inner = loop("b", "{{spec_folder}}/b.yaml", "y", sync("s", 10), indent=6) + loop(
        "c", "{{spec_folder}}/c.yaml", "z", sync("t", 10), indent=6
    )
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "x", inner)

    assert [reason for _, reason in errors_of(text)] == [SECOND_FOR_EACH]


# --- AC6 ----------------------------------------------------------------------------------


def test_an_inner_as_equal_to_an_outer_as_is_bound_already() -> None:
    inner = loop("b", "{{spec_folder}}/b.yaml", "epic", sync("s", 10), indent=6)
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "epic", inner)

    lines = text.splitlines()
    as_line = [i for i, row in enumerate(lines, 1) if row.strip() == "as: epic"][1]
    assert errors_of(text) == [(as_line, LOOP_NAME_BOUND)]


def test_a_bind_name_equal_to_an_input_is_bound_already() -> None:
    text = (
        HEAD
        + "steps:\n"
        + loop(
            "a", "{{spec_folder}}/a.yaml", "x", sync("s", 6), extra="    bind: { branch: 'x' }\n"
        )
    )

    lines = text.splitlines()
    bind_line = next(i for i, row in enumerate(lines, 1) if row.strip().startswith("bind:"))
    assert errors_of(text) == [(bind_line, LOOP_NAME_BOUND)]


def test_a_bind_name_equal_to_its_own_as_is_bound_already() -> None:
    text = (
        HEAD
        + "steps:\n"
        + loop(
            "a", "{{spec_folder}}/a.yaml", "epic", sync("s", 6), extra="    bind: { epic: 'x' }\n"
        )
    )

    assert [reason for _, reason in errors_of(text)] == [LOOP_NAME_BOUND]


def test_a_bind_name_equal_to_an_outer_bind_name_is_bound_already() -> None:
    inner = loop(
        "b",
        "{{spec_folder}}/b.yaml",
        "y",
        sync("s", 10),
        extra="        bind: { folder: 'q' }\n",
        indent=6,
    )
    text = (
        HEAD
        + "steps:\n"
        + loop("a", "{{spec_folder}}/a.yaml", "x", inner, extra="    bind: { folder: 'p' }\n")
    )

    assert [reason for _, reason in errors_of(text)] == [LOOP_NAME_BOUND]


def test_an_as_equal_to_an_input_name_stays_allowed() -> None:
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "branch", sync("s", 6))

    assert errors_of(text) == []


def test_a_bind_name_written_twice_is_reported_at_the_second_occurrence() -> None:
    bind = "    bind:\n      folder: one\n      other: two\n      folder: three\n"
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "x", sync("s", 6), extra=bind)

    lines = text.splitlines()
    second = [i for i, row in enumerate(lines, 1) if row.strip().startswith("folder:")][1]
    assert errors_of(text) == [(second, LOOP_NAME_BOUND)]


# --- AC7 ----------------------------------------------------------------------------------


def test_the_same_id_in_the_root_list_and_a_loop_is_valid() -> None:
    body = sync("setup", 6)
    text = (
        HEAD + "steps:\n" + sync("setup", 2) + loop("epics", "{{spec_folder}}/e.yaml", "epic", body)
    )

    assert errors_of(text) == []


def test_two_equal_ids_in_one_list_are_a_duplicate() -> None:
    text = HEAD + "steps:\n" + sync("setup", 2) + sync("setup", 2)

    assert [reason for _, reason in errors_of(text)] == [DUPLICATE_STEP_ID]


# --- AC8 ----------------------------------------------------------------------------------


def with_bind(bind: str, steps: str | None = None) -> str:
    return (
        HEAD
        + "steps:\n"
        + loop(
            "a",
            "{{spec_folder}}/a.yaml",
            "epic",
            steps or sync("s", 6),
            extra=f"    bind: {bind}\n",
        )
    )


def test_a_field_of_a_bind_name_is_an_unknown_field() -> None:
    body = "      - id: s\n        run: 'echo {{folder.x}}'\n        gate: deterministic\n"

    assert [r for _, r in errors_of(with_bind("{ folder: 'q' }", body))] == [UNKNOWN_FIELD]


def test_a_non_string_bind_value_is_invalid() -> None:
    assert [r for _, r in errors_of(with_bind("{ folder: 5 }"))] == [INVALID_VALUE]


def test_a_whole_item_as_a_bind_value_is_invalid() -> None:
    assert [r for _, r in errors_of(with_bind("{ folder: '{{epic}}' }"))] == [INVALID_VALUE]


def test_a_whole_input_entity_as_a_bind_value_is_invalid() -> None:
    text = HEAD.replace("inputs:\n", "inputs:\n  repo: { type: repository, required: true }\n")
    text += "steps:\n" + loop(
        "a",
        "{{spec_folder}}/a.yaml",
        "epic",
        sync("s", 6),
        extra="    bind: { folder: '{{repo}}' }\n",
    )

    assert [r for _, r in errors_of(text)] == [INVALID_VALUE]


def test_a_bind_key_with_a_hyphen_is_invalid() -> None:
    assert [r for _, r in errors_of(with_bind("{ spec-folder: 'q' }"))] == [INVALID_VALUE]


def test_a_bind_that_is_not_a_map_is_invalid() -> None:
    assert [r for _, r in errors_of(with_bind("[a, b]"))] == [INVALID_VALUE]


@pytest.mark.parametrize("key", ["5", "~", "2026-01-01"])
def test_a_non_string_bind_key_is_reported_at_its_own_line_without_raising(key: str) -> None:
    text = with_bind("\n      ok: 'x'\n      " + key + ": x")

    result = errors_of(text)
    lines = text.splitlines()
    at = next(i for i, row in enumerate(lines, 1) if row.strip().startswith(f"{key}:"))
    assert result == [(at, INVALID_VALUE)]


# --- AC9 ----------------------------------------------------------------------------------

CALLEE = """name: callee
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: sync
    uses: git.sync
    gate: deterministic
"""


def callee_repo() -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository(
        [TemplateVersion(name="callee", version=1, yaml=CALLEE, hash="sha", calls=())]
    )


CALL = (
    "      - id: c\n        uses: template\n        with:\n          name: callee\n"
    "          inputs:\n            folder: '{{folder}}'\n"
)


def test_a_bind_name_binds_a_callee_input_of_type_path() -> None:
    text = with_bind("{ folder: '{{spec_folder}}' }", CALL)

    assert errors_of(text, callee_repo()) == []


def test_a_bind_name_does_not_bind_a_callee_number_input() -> None:
    callee = CALLEE.replace("type: path", "type: number")
    repo = FakeTemplateVersionRepository(
        [TemplateVersion(name="callee", version=1, yaml=callee, hash="sha", calls=())]
    )

    result = errors_of(with_bind("{ folder: '{{spec_folder}}' }", CALL), repo)

    assert [r for _, r in result] == [CALLEE_INPUT_MISMATCH]


def timed(limit: str) -> str:
    return (
        f"      - id: s\n        run: echo\n        timeout_min: '{limit}'\n"
        "        gate: deterministic\n"
    )


def test_a_bind_name_reads_as_text_in_a_timeout() -> None:
    body = timed("{{mins}}")

    assert errors_of(with_bind("{ mins: '5' }", body)) == []


def test_an_item_reads_as_no_timeout_without_a_field() -> None:
    body = timed("{{epic}}")

    assert [r for _, r in errors_of(with_bind("{ mins: '5' }", body))] == [INVALID_TIMEOUT]


def test_an_inner_for_each_sees_the_outer_bind() -> None:
    inner = loop("b", "{{folder}}/stories.yaml", "story", sync("s", 10), indent=6)
    text = (
        HEAD
        + "steps:\n"
        + loop(
            "a",
            "{{spec_folder}}/a.yaml",
            "epic",
            inner,
            extra="    bind: { folder: '{{spec_folder}}/{{epic.dir}}' }\n",
        )
    )

    assert errors_of(text) == []


def test_a_loops_own_for_each_naming_its_own_as_is_unbound() -> None:
    text = HEAD + "steps:\n" + loop("a", "{{epic.dir}}/a.yaml", "epic", sync("s", 6))

    assert [r for _, r in errors_of(text)] == [UNBOUND_VARIABLE]


def test_a_loops_own_for_each_naming_its_own_bind_is_unbound() -> None:
    text = (
        HEAD
        + "steps:\n"
        + loop("a", "{{folder}}/a.yaml", "epic", sync("s", 6), extra="    bind: { folder: 'q' }\n")
    )

    assert [r for _, r in errors_of(text)] == [UNBOUND_VARIABLE]


def test_a_bind_value_naming_a_sibling_bind_is_unbound() -> None:
    text = with_bind("{ one: 'q', two: '{{one}}' }")

    assert [r for _, r in errors_of(text)] == [UNBOUND_VARIABLE]


def test_a_loops_own_pause_after_naming_its_own_as_field_validates() -> None:
    text = (
        HEAD
        + "steps:\n"
        + loop(
            "a",
            "{{spec_folder}}/a.yaml",
            "epic",
            sync("s", 6),
            extra="    pause_after_item_when: epic.done\n",
        )
    )

    assert errors_of(text) == []


# --- the loop checker, directly -----------------------------------------------------------


def parsed_loop(text: str) -> LinedMap:
    root = load_with_lines(text).root
    assert root is not None
    node = root["steps"][0]
    assert isinstance(node, LinedMap)
    return node


def test_check_bind_without_a_bind_key_reports_nothing() -> None:
    node = parsed_loop(HEAD + "steps:\n" + loop("a", "{{x}}", "epic", sync("s", 6)))

    assert check_bind(node, (), set()) == []


def test_check_for_each_hands_back_the_callers_non_step_errors() -> None:
    node = parsed_loop(HEAD + "steps:\n" + loop("a", "{{x}}", "epic", sync("s", 6)))
    carried = ValidationError(line=99, reason=INVALID_VALUE)

    found = check_for_each(node, (), seen_in_list=False, input_names=set(), non_steps=[carried])

    assert found == [carried]


def test_an_enclosing_loop_whose_as_is_not_a_name_holds_no_name() -> None:
    inner = loop("b", "{{spec_folder}}/b.yaml", "y", sync("s", 10), indent=6)
    text = HEAD + "steps:\n" + loop("a", "{{spec_folder}}/a.yaml", "5", inner)
    text = text.replace("as: 5", "as: 5.5")

    assert [reason for _, reason in errors_of(text)] == [INVALID_SLUG]


def test_a_bind_beside_an_as_that_is_not_a_name_still_checks_the_bind() -> None:
    text = (
        HEAD
        + "steps:\n"
        + loop(
            "a", "{{spec_folder}}/a.yaml", "5.5", sync("s", 6), extra="    bind: { folder: 7 }\n"
        )
    )

    assert sorted(reason for _, reason in errors_of(text)) == sorted([INVALID_SLUG, INVALID_VALUE])
