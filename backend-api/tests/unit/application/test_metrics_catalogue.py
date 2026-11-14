"""The catalogue validator (story 1, RM-2): pure, collects every error, names file and id."""

from __future__ import annotations

import pytest
import yaml

from orchestrator.application.metrics.catalogue import (
    CatalogueError,
    CatalogueInvalid,
    build_entry,
    check_entry_fields,
    validate_catalogue,
)


def entry_yaml(**overrides: object) -> str:
    fields: dict[str, object] = {
        "id": "cost.gateway",
        "label": "gateway",
        "group": "cost",
        "level": "H",
        "scopes": ["run", "epic"],
        "unit": "USD",
        "source": "gateway",
        "component_of": None,
        "additive": "within_scope_type",
        "missing_words": ["not recorded"],
        "limits": None,
        "fingerprint_group": False,
        "methods": [{"n": 1, "description": "Sum of spend.", "parameters": {}}],
    }
    fields.update(overrides)
    fields = {k: v for k, v in fields.items() if v != "__drop__"}
    return yaml.safe_dump([fields], sort_keys=False)


TWO_ERRORS = 2


def errors_of(*files: tuple[str, str]) -> tuple[CatalogueError, ...]:
    with pytest.raises(CatalogueInvalid) as raised:
        validate_catalogue(files)
    return raised.value.errors


def reasons(errors: tuple[CatalogueError, ...]) -> str:
    return " | ".join(e.reason for e in errors)


def test_a_valid_two_file_catalogue_resolves_component_of_across_files() -> None:
    first = entry_yaml(id="tokens.output", group="tokens")
    second = entry_yaml(id="tokens.thinking", group="tokens", component_of="tokens.output")
    entries = validate_catalogue([("a.yaml", first), ("b.yaml", second)])
    assert [e.id for e in entries] == ["tokens.output", "tokens.thinking"]
    assert entries[1].component_of == "tokens.output"
    assert entries[0].scopes == ("run", "epic")
    assert entries[0].methods[0].n == 1


def test_optional_fields_may_be_left_out() -> None:
    text = (
        "- {id: cost.gateway, label: g, group: cost, level: H, scopes: [run], unit: USD,"
        " source: s, additive: true, missing_words: [], fingerprint_group: false,"
        " methods: [{n: 1, description: d, parameters: {}}]}\n"
    )
    (entry,) = validate_catalogue([("cost.yaml", text)])
    assert entry.component_of is None
    assert entry.limits is None
    assert entry.additive is True


def test_unknown_field_names_file_id_and_field() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(colour="red")))
    assert (error.file, error.metric_id) == ("cost.yaml", "cost.gateway")
    assert "colour" in error.reason


def test_missing_required_field_is_named() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(unit="__drop__")))
    assert error.metric_id == "cost.gateway"
    assert "unit" in error.reason


def test_duplicate_id_names_both_files() -> None:
    errors = errors_of(("cost.yaml", entry_yaml()), ("budget.yaml", entry_yaml()))
    duplicate = [e for e in errors if "duplicate" in e.reason]
    assert len(duplicate) == 1
    assert "cost.yaml" in duplicate[0].reason
    assert "budget.yaml" in duplicate[0].reason
    assert duplicate[0].metric_id == "cost.gateway"


@pytest.mark.parametrize("bad", ["Cost.Gateway", "cost", "cost.gateway.x", "1cost.a"])
def test_malformed_id_names_file_and_id(bad: str) -> None:
    errors = errors_of(("cost.yaml", entry_yaml(id=bad)))
    malformed = [e for e in errors if e.reason.startswith("malformed id")]
    assert [(e.file, e.metric_id) for e in malformed] == [("cost.yaml", bad)]


def test_non_string_id_is_malformed() -> None:
    errors = errors_of(("cost.yaml", entry_yaml(id=7)))
    assert errors[0].reason.startswith("malformed id")
    assert errors[0].metric_id == "7"


def test_group_must_equal_the_id_prefix() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(group="tokens")))
    assert "group" in error.reason


def test_level_must_be_h_or_a() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(level="X")))
    assert "level" in error.reason


def test_scope_must_be_in_the_closed_list() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(scopes=["run", "galaxy"])))
    assert "galaxy" in error.reason


def test_scopes_must_be_a_list() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(scopes="run")))
    assert "scopes" in error.reason


def test_additive_must_be_in_the_closed_set() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(additive="sometimes")))
    assert "additive" in error.reason


def test_missing_words_must_be_a_list_of_strings() -> None:
    (a,) = errors_of(("cost.yaml", entry_yaml(missing_words="not recorded")))
    (b,) = errors_of(("cost.yaml", entry_yaml(missing_words=[1])))
    assert "missing_words" in a.reason
    assert "missing_words" in b.reason


def test_fingerprint_group_must_be_a_bool() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(fingerprint_group="yes")))
    assert "fingerprint_group" in error.reason


@pytest.mark.parametrize("field", ["label", "unit", "source"])
def test_text_fields_must_be_non_blank_strings(field: str) -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(**{field: " "})))
    assert field in error.reason


def test_limits_must_be_text_or_null() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(limits=3)))
    assert "limits" in error.reason


def test_unknown_component_of_names_the_missing_id() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(component_of="tokens.missing")))
    assert "tokens.missing" in error.reason
    assert (error.file, error.metric_id) == ("cost.yaml", "cost.gateway")


@pytest.mark.parametrize("description", ["", "   ", "__drop__"])
def test_method_without_a_description_is_refused(description: str) -> None:
    method: dict[str, object] = {"n": 1, "description": description, "parameters": {}}
    if description == "__drop__":
        del method["description"]
    (error,) = errors_of(("cost.yaml", entry_yaml(methods=[method])))
    assert error.metric_id == "cost.gateway"
    assert "description" in error.reason


def test_method_list_must_be_non_empty() -> None:
    (error,) = errors_of(("cost.yaml", entry_yaml(methods=[])))
    assert "methods" in error.reason


def test_methods_must_be_a_list_of_mappings() -> None:
    (a,) = errors_of(("cost.yaml", entry_yaml(methods="one")))
    (b,) = errors_of(("cost.yaml", entry_yaml(methods=["one"])))
    assert "methods" in a.reason
    assert "method" in b.reason


def test_method_unknown_field_and_bad_parameters_are_refused() -> None:
    method = {"n": 1, "description": "d", "parameters": [], "colour": "red"}
    errors = errors_of(("cost.yaml", entry_yaml(methods=[method])))
    text = reasons(errors)
    assert "colour" in text
    assert "parameters" in text


@pytest.mark.parametrize("numbers", [[0], ["1"], [True], [1, 1], [2, 1]])
def test_method_numbers_are_ints_from_one_strictly_ascending(numbers: list[object]) -> None:
    methods = [{"n": n, "description": "d", "parameters": {}} for n in numbers]
    (error,) = errors_of(("cost.yaml", entry_yaml(methods=methods)))
    assert "n" in error.reason


def test_method_number_missing_is_refused() -> None:
    (error,) = errors_of(
        ("cost.yaml", entry_yaml(methods=[{"description": "d", "parameters": {}}]))
    )
    assert "n" in error.reason


def test_a_file_must_be_a_list_of_mappings() -> None:
    (a,) = errors_of(("cost.yaml", "a: 1\n"))
    (b,) = errors_of(("cost.yaml", "- just text\n"))
    assert a.file == b.file == "cost.yaml"
    assert "list" in a.reason
    assert "mapping" in b.reason


def test_invalid_yaml_is_an_error_naming_the_file() -> None:
    (error,) = errors_of(("cost.yaml", "- [unclosed\n"))
    assert error.file == "cost.yaml"
    assert "yaml" in error.reason.lower()


def test_no_files_is_an_error() -> None:
    (error,) = errors_of()
    assert error.reason == "no catalogue files"


def test_every_error_is_collected_and_listed_in_the_message() -> None:
    bad_a = entry_yaml(colour="red")
    bad_b = entry_yaml(id="tokens.x", group="tokens", level="X")
    with pytest.raises(CatalogueInvalid) as raised:
        validate_catalogue([("a.yaml", bad_a), ("b.yaml", bad_b)])
    assert len(raised.value.errors) == TWO_ERRORS
    message = str(raised.value)
    assert "a.yaml: cost.gateway:" in message
    assert "b.yaml: tokens.x:" in message


def test_a_method_without_parameters_builds_with_empty_parameters() -> None:
    """`parameters` is optional on a method; leaving it out means none, not a crash."""
    (entry,) = validate_catalogue(
        [("cost.yaml", entry_yaml(methods=[{"n": 1, "description": "d"}]))]
    )
    assert entry.methods[0].parameters == {}


def test_check_entry_fields_leaves_the_id_pattern_to_the_caller() -> None:
    [fields] = yaml.safe_load(entry_yaml(id="step.bench.heldout_tests", group="step"))

    assert check_entry_fields(fields) == []


def test_check_entry_fields_names_every_field_offence() -> None:
    [fields] = yaml.safe_load(entry_yaml(label="__drop__", level="Z"))

    assert check_entry_fields(fields) == ["missing field label", "level must be one of H, A"]


def test_build_entry_makes_the_entry_of_a_checked_mapping() -> None:
    [fields] = yaml.safe_load(entry_yaml(scopes=["run"], limits="a limit"))

    built = build_entry(fields)

    assert (built.id, built.scopes, built.limits) == ("cost.gateway", ("run",), "a limit")
    assert [m.n for m in built.methods] == [1]
