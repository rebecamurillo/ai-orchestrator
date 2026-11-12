"""JSON Schemas of the two formats the instance accepts (AD-35, schema half).

Every key name comes from the table `validate()` or the list reader uses, so a key added there
reaches the schema with no edit here. Built on each call, written by `tools/build_guide.py` at
build time and never committed.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps import (
    AGENT_KIND,
    GATES,
    KIND_META,
    TEMPLATE_CALL_KIND,
    TEMPLATE_KINDS,
)
from orchestrator.application.templates import consult
from orchestrator.application.templates.lines import AS_KEY, STEPS_KEY
from orchestrator.application.templates.lists import (
    EPICS_KIND,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    STORIES_KIND,
)
from orchestrator.application.templates.lists import ID_KEY as LIST_ID_KEY
from orchestrator.application.templates.model import INPUT_TYPES, ON_FAIL_ACTIONS
from orchestrator.application.templates.on_fail import ON_FAIL_KEY, RUN_KIND
from orchestrator.application.templates.table import (
    AGENT_DISPATCH_KEYS,
    AGENT_INTENT_KEYS,
    AGENT_KEYS,
    CALL_TIMING_KEYS,
    CONSULT_KEY,
    CONSULT_KEYS,
    CONSULT_PROMPTS_KEYS,
    CONSULT_REQUIRED,
    DESCRIPTION_KEY,
    FOR_EACH_KEYS,
    GATE_KEY,
    INPUT_KEYS,
    INPUT_TYPE_KEY,
    INPUTS_KEY,
    MAX_COUNT,
    MIN_COUNT,
    NAME_KEY,
    PROMPTS_KEY,
    REDISPATCH_CONSULT_REQUIRED,
    REDISPATCH_KEYS,
    REDISPATCH_OPTIONAL,
    REQUIRED_FOR_EACH_KEYS,
    REQUIRED_INPUT_KEYS,
    REQUIRED_STEP_KEYS,
    REQUIRED_TEMPLATE_KEYS,
    RUN_KEY,
    SLUG,
    STEP_KEYS,
    SUB_MAPS,
    TEMPLATE_KEYS,
    USES_KEY,
    VERSION_KEY,
    WITH_KEY,
)

DRAFT = "https://json-schema.org/draft/2020-12/schema"
WORKFLOW_ID = "/schemas/workflow.json"
SPEC_FOLDER_ID = "/schemas/spec-folder.json"
WORKFLOW_TITLE = "Workflow (Template) file"
SPEC_FOLDER_TITLE = "Spec folder list files (epics.yaml, stories.yaml)"

Schema = dict[str, Any]


def _ref(name: str) -> Schema:
    return {"$ref": f"#/$defs/{name}"}


def _closed(
    keys: set[str] | frozenset[str], values: dict[str, Schema], required: list[str]
) -> Schema:
    properties = {key: values.get(key, {}) for key in sorted(keys)}
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _steps_array() -> Schema:
    return {"type": "array", "minItems": 1, "items": _ref("step")}


def _slug() -> Schema:
    return {"type": "string", "pattern": SLUG.pattern}


def _template_root() -> Schema:
    values = {
        NAME_KEY: _slug(),
        VERSION_KEY: {"type": "integer", "minimum": MIN_COUNT, "maximum": MAX_COUNT},
        STEPS_KEY: _steps_array(),
        INPUTS_KEY: {"type": "object", "additionalProperties": _ref("input")},
    }
    required = [*REQUIRED_TEMPLATE_KEYS, STEPS_KEY]
    return _closed(TEMPLATE_KEYS, values, required)


def _input() -> Schema:
    values: dict[str, Schema] = {
        INPUT_TYPE_KEY: {"enum": sorted(INPUT_TYPES)},
        DESCRIPTION_KEY: {"type": "string"},
    }
    return _closed(INPUT_KEYS, values, list(REQUIRED_INPUT_KEYS))


def _shared(on_fail: str) -> dict[str, Schema]:
    values: dict[str, Schema] = {
        GATE_KEY: {"enum": sorted(GATES)},
        ON_FAIL_KEY: _ref(on_fail),
        CONSULT_KEY: _ref("consult"),
    }
    for key, keys in SUB_MAPS:
        values[key] = _closed(keys, {}, [])
    return values


def _kind_branch(kind: str) -> Schema:
    keys = STEP_KEYS - {RUN_KEY}
    if kind == AGENT_KIND:
        keys = keys | AGENT_KEYS
    if kind == TEMPLATE_CALL_KIND:
        keys = keys - set(CALL_TIMING_KEYS)
    with_keys = KIND_META[kind].with_keys
    if kind == AGENT_KIND:
        with_keys = with_keys | AGENT_DISPATCH_KEYS | AGENT_INTENT_KEYS
    required = [*REQUIRED_STEP_KEYS, USES_KEY]
    with_required: list[str] = []
    if kind == TEMPLATE_CALL_KIND:
        required.append(WITH_KEY)
        with_required = [NAME_KEY]
    values = _shared("on_fail_shell" if kind == RUN_KIND else "on_fail")
    values[USES_KEY] = {"const": kind}
    values[WITH_KEY] = _closed(with_keys, {}, with_required)
    return _closed(keys, values, required)


def _run_branch() -> Schema:
    keys = STEP_KEYS - {USES_KEY, WITH_KEY}
    values = _shared("on_fail_shell")
    values[RUN_KEY] = {"type": "string", "minLength": 1}
    return _closed(keys, values, [*REQUIRED_STEP_KEYS, RUN_KEY])


def _for_each_branch() -> Schema:
    values = {STEPS_KEY: _steps_array(), AS_KEY: _slug()}
    return _closed(FOR_EACH_KEYS, values, list(REQUIRED_FOR_EACH_KEYS))


def _step() -> Schema:
    branches = [_kind_branch(kind) for kind in sorted(TEMPLATE_KINDS)]
    return {"oneOf": [*branches, _run_branch(), _for_each_branch()]}


def _redispatch(*, with_consult: bool) -> Schema:
    keys = REDISPATCH_KEYS | REDISPATCH_OPTIONAL if with_consult else REDISPATCH_KEYS
    values = {CONSULT_KEY: _ref("redispatch_consult")} if with_consult else {}
    return _closed(keys, values, sorted(REDISPATCH_KEYS))


def _consult(required: tuple[str, ...]) -> Schema:
    prompts = _closed(CONSULT_PROMPTS_KEYS, {}, [consult.DISPATCH, consult.ANSWER])
    return _closed(CONSULT_KEYS, {PROMPTS_KEY: prompts}, list(required))


def workflow_schema() -> Schema:
    """The workflow file, closed at every level `validate()` closes."""
    root = _template_root()
    root["$schema"] = DRAFT
    root["$id"] = WORKFLOW_ID
    root["title"] = WORKFLOW_TITLE
    root["$defs"] = {
        "input": _input(),
        "step": _step(),
        "on_fail": {"oneOf": [{"enum": sorted(ON_FAIL_ACTIONS)}, _redispatch(with_consult=False)]},
        "on_fail_shell": {
            "oneOf": [{"enum": sorted(ON_FAIL_ACTIONS)}, _redispatch(with_consult=True)]
        },
        "consult": _consult(CONSULT_REQUIRED),
        "redispatch_consult": _consult(REDISPATCH_CONSULT_REQUIRED),
    }
    return root


def spec_folder_schema() -> Schema:
    """The two list files: entries need the fields the planner requires and may carry more."""
    defs: Schema = {}
    for kind in (EPICS_KIND, STORIES_KIND):
        required = REQUIRED_FIELDS[kind]
        fields = [*required, *OPTIONAL_FIELDS[kind]]
        properties: Schema = {field: {} for field in fields}
        properties[LIST_ID_KEY] = {"type": ["string", "integer"]}
        defs[kind] = {
            "type": "array",
            "items": {
                "type": "object",
                "required": list(required),
                "properties": properties,
                "additionalProperties": True,
            },
        }
    return {"$schema": DRAFT, "$id": SPEC_FOLDER_ID, "title": SPEC_FOLDER_TITLE, "$defs": defs}
