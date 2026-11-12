"""AD-35 schema half: the format schemas are generated from the checks `validate()` reads."""

import dataclasses
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from orchestrator.application import format_schemas
from orchestrator.application.format_schemas import spec_folder_schema, workflow_schema
from orchestrator.application.steps import (
    KIND_META,
    SHELL_KIND,
    TEMPLATE_CALL_KIND,
    TEMPLATE_KINDS,
)
from orchestrator.application.templates.lists import (
    EPICS_KIND,
    REQUIRED_FIELDS,
    STORIES_KIND,
)
from orchestrator.application.templates.model import UNKNOWN_KEY
from orchestrator.application.templates.table import (
    AGENT_DISPATCH_KEYS,
    AGENT_INTENT_KEYS,
    AGENT_KEYS,
    CONSULT_KEYS,
    CONSULT_PROMPTS_KEYS,
    EXPECT_KEYS,
    FOR_EACH_KEYS,
    INPUT_KEYS,
    PROMPTS_KEYS,
    REDISPATCH_KEYS,
    REDISPATCH_OPTIONAL,
    RETRY_KEYS,
    STEP_KEYS,
    TEMPLATE_KEYS,
)
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

DRAFT = "https://json-schema.org/draft/2020-12/schema"

WORKFLOW = """\
name: fixture-flow
version: 1
description: A fixture the test owns.
inputs:
  target:
    type: string
    description: What to check.
steps:
  - id: build
    uses: shell
    with:
      command: make build
    gate: deterministic
  - id: verify
    run: make test
    on_fail: escalate
  - id: each
    for_each: "{{target}}/stories.yaml"
    as: story
    steps:
      - id: inner
        uses: shell
        with:
          command: echo hi
"""

EPICS = """\
- id: 1
  title: One
  branch: epic-1
  spec_folder: initiatives/one
  surprise: ignored
"""
STORIES = """\
- id: "1-1"
  title: One
  description: First.
"""


def load() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(WORKFLOW)
    return loaded


def accepted(document: dict[str, Any]) -> bool:
    return (
        validate(yaml.safe_dump(document), templates=FakeTemplateVersionRepository()).errors == ()
    )


def rejected_as_unknown(document: dict[str, Any]) -> bool:
    result = validate(yaml.safe_dump(document), templates=FakeTemplateVersionRepository())
    return any(error.reason == UNKNOWN_KEY for error in result.errors)


def test_both_schemas_are_valid_draft_2020_12() -> None:
    for schema, schema_id in (
        (workflow_schema(), "/schemas/workflow.json"),
        (spec_folder_schema(), "/schemas/spec-folder.json"),
    ):
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == DRAFT
        assert schema["$id"] == schema_id
        assert schema["title"]


def test_a_workflow_validate_accepts_passes_the_schema() -> None:
    assert accepted(load())
    Draft202012Validator(workflow_schema()).validate(load())


def test_an_unknown_top_level_key_fails_both() -> None:
    document = load() | {"surprise": 1}
    assert rejected_as_unknown(document)
    assert not Draft202012Validator(workflow_schema()).is_valid(document)


def test_an_unknown_step_key_fails_both() -> None:
    document = load()
    document["steps"][0]["surprise"] = 1
    assert rejected_as_unknown(document)
    assert not Draft202012Validator(workflow_schema()).is_valid(document)


def test_a_call_with_a_timing_key_fails_the_schema() -> None:
    document = load()
    document["steps"].append(
        {"id": "call", "uses": TEMPLATE_CALL_KIND, "with": {"name": "x"}, "timeout_min": 3}
    )
    assert not Draft202012Validator(workflow_schema()).is_valid(document)
    document["steps"][-1].pop("timeout_min")
    assert Draft202012Validator(workflow_schema()).is_valid(document)


def test_a_call_without_a_name_fails_the_schema() -> None:
    document = load()
    document["steps"].append({"id": "call", "uses": TEMPLATE_CALL_KIND, "with": {}})
    assert not Draft202012Validator(workflow_schema()).is_valid(document)


def test_agent_steps_carry_their_extra_keys_and_consult_shapes() -> None:
    document = load()
    document["steps"].insert(
        0,
        {
            "id": "dev",
            "uses": "agent",
            "with": {"skill": "s", "intent": "i"},
            "expect": {"files": ["a"]},
            "retry": {"max": 1},
            "prompts": {"dispatch": "d"},
            "consult": {
                "model": "m",
                "skill": "s",
                "on": ["blocked"],
                "prompts": {"dispatch": "d", "answer": "a"},
            },
        },
    )
    document["steps"][2]["on_fail"] = {
        "redispatch": "dev",
        "max": 2,
        "consult": {"model": "m", "skill": "s", "prompts": {"dispatch": "d", "answer": "a"}},
    }
    check = Draft202012Validator(workflow_schema())
    assert check.is_valid(document)
    document["steps"][0]["expect"]["surprise"] = 1
    assert not check.is_valid(document)


def test_on_fail_redispatch_consult_is_only_for_the_run_form() -> None:
    consult = {"model": "m", "skill": "s", "prompts": {"dispatch": "d", "answer": "a"}}
    agent = {"id": "dev", "uses": "agent", "with": {"skill": "s"}}
    on_fail = {"redispatch": "dev", "max": 1, "consult": consult}
    check = Draft202012Validator(workflow_schema())
    document = load()
    document["steps"] = [
        agent,
        {"id": "v", "uses": "shell", "with": {"command": "x"}, "on_fail": on_fail},
    ]
    assert check.is_valid(document)
    document["steps"][1] = {"id": "w", "uses": "agent", "with": {"skill": "s"}, "on_fail": on_fail}
    assert not check.is_valid(document)


def keys_of(schema: object) -> set[str]:
    found: set[str] = set()
    if isinstance(schema, dict):
        found |= set(schema.get("properties", {}))
        for value in schema.values():
            found |= keys_of(value)
    elif isinstance(schema, list):
        for item in schema:
            found |= keys_of(item)
    return found


def test_every_key_of_the_tables_appears_in_the_schema() -> None:
    present = keys_of(workflow_schema())
    tables = [
        TEMPLATE_KEYS,
        INPUT_KEYS,
        STEP_KEYS,
        AGENT_KEYS,
        FOR_EACH_KEYS,
        EXPECT_KEYS,
        RETRY_KEYS,
        PROMPTS_KEYS,
        CONSULT_KEYS,
        CONSULT_PROMPTS_KEYS,
        REDISPATCH_KEYS | REDISPATCH_OPTIONAL,
        AGENT_DISPATCH_KEYS | AGENT_INTENT_KEYS,
        *(KIND_META[kind].with_keys for kind in TEMPLATE_KINDS),
    ]
    for table in tables:
        assert table <= present


def test_a_key_added_to_a_table_reaches_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "zz-added" not in keys_of(workflow_schema())
    monkeypatch.setattr(format_schemas, "STEP_KEYS", STEP_KEYS | {"zz-added"})
    meta = dataclasses.replace(
        KIND_META[SHELL_KIND], with_keys=KIND_META[SHELL_KIND].with_keys | {"zz-with"}
    )
    monkeypatch.setitem(KIND_META, SHELL_KIND, meta)
    present = keys_of(workflow_schema())
    assert {"zz-added", "zz-with"} <= present


def test_the_required_fields_equal_the_reader_s() -> None:
    defs = spec_folder_schema()["$defs"]
    assert defs[EPICS_KIND]["items"]["required"] == list(REQUIRED_FIELDS[EPICS_KIND])
    assert defs[STORIES_KIND]["items"]["required"] == list(REQUIRED_FIELDS[STORIES_KIND])


def against(kind: str) -> Draft202012Validator:
    schema = {"$schema": DRAFT, "$defs": spec_folder_schema()["$defs"], "$ref": f"#/$defs/{kind}"}
    return Draft202012Validator(schema)


def test_lists_missing_a_required_field_are_rejected() -> None:
    epics = yaml.safe_load(EPICS)
    stories = yaml.safe_load(STORIES)
    assert against(EPICS_KIND).is_valid(epics)
    assert against(STORIES_KIND).is_valid(stories)
    del epics[0]["branch"]
    del stories[0]["title"]
    assert not against(EPICS_KIND).is_valid(epics)
    assert not against(STORIES_KIND).is_valid(stories)
