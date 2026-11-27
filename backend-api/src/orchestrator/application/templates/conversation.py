"""The `uses: conversation` step: its checker, its parser and its planned-row extras (AD-15).

Every refusal reads `step {id}: {sentence}` and sits at the offending key's own line, so the
Operator finds the step and the key from the reason alone. The generic step-level
`unknown key` is skipped for this kind (`keys.py`): the checker below names the step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.templates.agent import check_route_lists
from orchestrator.application.templates.conversation_model import ConversationExtras
from orchestrator.application.templates.lines import (
    LinedMap,
    as_map,
    as_seq,
    child_steps,
    is_for_each,
    key_line,
)
from orchestrator.application.templates.model import ValidationError
from orchestrator.application.templates.substitute import resolve
from orchestrator.application.templates.table import (
    CONVERSATION_EXPECT_KEYS,
    CONVERSATION_KEYS,
    CONVERSATION_PROMPTS_KEYS,
    DEFAULT_TEMPLATE_TYPE,
    ID_KEY,
    PROMPTS_KEY,
    ROLE_KEY,
    STEP_KEYS,
    TEMPLATE_TYPE_KEY,
    USES_KEY,
    WITH_KEY,
    WRITES_KEY,
    is_slug,
    problem,
)

if TYPE_CHECKING:  # a frame is the walker's; naming it here would be a second one
    from orchestrator.application.templates.rows import Frame

EXPECT_KEY = "expect"
GLOB_CHARACTERS = "*?["
ATTEMPT_TOKEN = "{attempt_id}"
PLAN_ROLE = "plan"


def check_conversations(root: LinedMap) -> list[ValidationError]:
    """Every conversation step of the file, at any loop depth."""
    template_type = root.get(TEMPLATE_TYPE_KEY, DEFAULT_TEMPLATE_TYPE)
    return _under(root, template_type)


def _under(parent: LinedMap, template_type: object) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for node in child_steps(parent):
        if is_for_each(node):
            errors += _under(node, template_type)
        elif node.get(USES_KEY) == CONVERSATION_KIND:
            errors += check_conversation(node, template_type)
    return errors


def check_conversation(node: LinedMap, template_type: object) -> list[ValidationError]:
    """The shape AD-15 amended states for one conversation step."""
    name = str(node.get(ID_KEY))
    found: list[ValidationError] = []
    if template_type != "interactive":
        found.append(_refusal(node, USES_KEY, name, "conversation needs type: interactive"))
    found += _check_with(node, name)
    found += _check_expect(node, name)
    found += _check_prompts(node, name)
    found += _check_writes(node, name)
    if node.get(ROLE_KEY) != PLAN_ROLE:
        found.append(_refusal(node, ROLE_KEY, name, "role must be plan"))
    allowed = STEP_KEYS | CONVERSATION_KEYS
    for key in node:
        if key not in allowed:
            found.append(_refusal(node, key, name, f"{key}: unknown key"))
    return found + check_route_lists(node)


def _refusal(node: LinedMap, key: str, name: str, sentence: str) -> ValidationError:
    return problem(key_line(node, key, node.line), f"step {name}: {sentence}")


def _check_with(node: LinedMap, name: str) -> list[ValidationError]:
    params = as_map(node.get(WITH_KEY)) or LinedMap()
    found: list[ValidationError] = []
    if not is_slug(params.get("step")):
        found.append(_refusal(node, WITH_KEY, name, "with.step must be a slug"))
    for key in ("skill", "persona"):
        if not isinstance(params.get(key), str):
            found.append(_refusal(node, WITH_KEY, name, f"with.{key} is text"))
    return found


def _block(node: LinedMap, key: str) -> LinedMap:
    """The sub-map under `key`; when absent, an empty one placed at the key's line or the step's."""
    found = as_map(node.get(key))
    if found is not None:
        return found
    empty = LinedMap()
    empty.line = key_line(node, key, node.line)
    return empty


def _is_literal_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and not any(c in value for c in GLOB_CHARACTERS)


def _expect_files(expect: LinedMap) -> list[Any]:
    value = expect.get("files")
    listed = as_seq(value)
    return list(listed) if listed is not None else [value]


def _check_expect(node: LinedMap, name: str) -> list[ValidationError]:
    expect = _block(node, EXPECT_KEY)
    found: list[ValidationError] = []
    files = _expect_files(expect)
    if len(files) != 1 or not _is_literal_path(files[0]):
        found.append(_refusal(expect, "files", name, "expect.files is one literal path"))
    if not as_seq(expect.get("success")):
        found.append(_refusal(expect, "success", name, "expect.success needs one word"))
    for key in expect:
        if key not in CONVERSATION_EXPECT_KEYS:
            found.append(_refusal(expect, key, name, f"expect.{key}: unknown key"))
    return found


def _check_prompts(node: LinedMap, name: str) -> list[ValidationError]:
    prompts = _block(node, PROMPTS_KEY)
    found: list[ValidationError] = []
    for key in sorted(CONVERSATION_PROMPTS_KEYS):
        if not isinstance(prompts.get(key), str):
            found.append(_refusal(prompts, key, name, f"prompts.{key} is required"))
    close = prompts.get("close")
    if isinstance(close, str) and ATTEMPT_TOKEN not in close:
        found.append(_refusal(prompts, "close", name, "prompts.close must name {attempt_id}"))
    for key in prompts:
        if key not in CONVERSATION_PROMPTS_KEYS:
            found.append(_refusal(prompts, key, name, f"prompts.{key}: unknown key"))
    return found


def _check_writes(node: LinedMap, name: str) -> list[ValidationError]:
    if WRITES_KEY not in node:
        return []
    paths = as_seq(node[WRITES_KEY])
    if paths is None or not all(isinstance(path, str) for path in paths):
        return [_refusal(node, WRITES_KEY, name, "writes is a list of text")]
    return []


def parse_conversation(node: LinedMap) -> ConversationExtras:
    """The frozen extras of a step that has already passed `check_conversation`."""
    expect = as_map(node.get(EXPECT_KEY)) or LinedMap()
    prompts = as_map(node.get(PROMPTS_KEY)) or LinedMap()
    return ConversationExtras(
        line=node.line,
        expect_files=tuple(str(path) for path in _expect_files(expect)),
        expect_success=tuple(as_seq(expect.get("success")) or ()),
        expect_blocked=tuple(as_seq(expect.get("blocked")) or ()),
        writes=tuple(as_seq(node.get(WRITES_KEY)) or ()),
        prompt_open=prompts["open"],
        prompt_close=prompts["close"],
    )


def conversation_extras(extras: ConversationExtras, frame: Frame) -> dict[str, Any]:
    """What a conversation row carries beside its `with`, `{{ }}` resolved at plan time."""
    return {
        EXPECT_KEY: {
            "files": [resolve(path, frame.scope) for path in extras.expect_files],
            "success": list(extras.expect_success),
            "blocked": list(extras.expect_blocked),
        },
        WRITES_KEY: [resolve(path, frame.scope) for path in extras.writes],
        PROMPTS_KEY: {
            "open": resolve(extras.prompt_open, frame.scope),
            "close": resolve(extras.prompt_close, frame.scope),
        },
    }
