"""The expression grammar: `{{name}}`, `{{name.field}}`, and nothing else.

Substitution, not evaluation. A Template may name a value and one field of it; it may not
filter, call, concatenate inside the braces or compare. Anything else between `{{` and `}}`
is `expression syntax`, which is what keeps FR-5's promise that a Template means what it
says.

Three scopes decide whether a name is bound:

- the Template's own declared `inputs`, everywhere in the file;
- every enclosing `for_each`'s `as` name (an `item`) and `bind` names (`text`), inside that
  loop's `steps` only — a callee sees only what its caller passes, and a sibling step sees
  nothing of another loop (AD-15). A loop's own `for_each` and `only` see the *enclosing*
  loops' names; its pause conditions and `bind` values also see its own `as`, never its own
  `bind` names;
- `output.status`, and only in `escalate_when`, whose whole grammar is
  `output.status == <token>`.

An entity input exposes a fixed field whitelist, so `{{repository.secret}}` is `unknown
field` rather than something the Run discovers at dispatch time. An `item` is whatever the
list file holds, so its fields are not checked at all.

`pause_when`, `pause_before_item_when` and `pause_after_item_when` are conditions, not
interpolations: they are written bare, as `<name>.<field>`, with no braces.
"""

from __future__ import annotations

import re
from typing import Any

from orchestrator.application.templates.inputs import declared_types
from orchestrator.application.templates.lines import (
    AS_KEY,
    BIND_KEY,
    FOR_EACH_KEY,
    ITEM_TYPE,
    NAME_PATTERN,
    TEXT_TYPE,
    LinedMap,
    Scope,
    as_map,
    as_seq,
    bind_names,
    is_for_each,
    iter_scoped_steps,
    key_line,
)
from orchestrator.application.templates.model import (
    EXPRESSION_SYNTAX,
    INVALID_STATUS_TOKEN,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    STATUS_TOKENS,
    UNBOUND_VARIABLE,
    UNKNOWN_FIELD,
    ValidationError,
)
from orchestrator.application.templates.table import problem

#: What a `{{ }}` may hold, and nothing more.
EXPRESSION = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
NAME = NAME_PATTERN
VARIABLE = re.compile(rf"^\s*({NAME})(?:\.({NAME}))?\s*$")
BARE_FIELD = re.compile(rf"^({NAME})\.({NAME})$")
#: A value that is one variable and nothing else — what a call binds by type.
WHOLE_VARIABLE = re.compile(rf"^\{{\{{\s*({NAME})\s*\}}\}}$")
ESCALATE = re.compile(r"^output\.status\s*==\s*(\S+)$")

#: The fields an entity input exposes (AD-15). Everything else is `unknown field`.
ENTITY_FIELDS: dict[str, frozenset[str]] = {
    "project": frozenset({"name"}),
    "repository": frozenset(
        {"url", "default_branch", "install_command", "quality_gate_command", "unit_test_command"}
    ),
}

#: The step key whose whole grammar is `output.status == <token>`.
ESCALATE_KEY = "escalate_when"

#: The types whose whole value is not text, so a `bind` may not take one.
ENTITY_TYPES = frozenset({ITEM_TYPE, "project", "repository"})

#: The step keys that take a count of minutes, and the input types an expression there may read.
MINUTES_KEYS = ("timeout_min", "stall_min")
MINUTES_TYPES = frozenset({"number", "string", TEXT_TYPE})

#: The braces themselves, for the leftovers an unbalanced pair leaves behind.
OPEN = "{{"
CLOSE = "}}"

#: The input key whose value is substituted into a Run that names no value of its own.
DEFAULT_KEY = "default"

#: The keys written bare as `<name>.<field>` rather than interpolated.
CONDITION_KEYS = ("pause_when", "pause_before_item_when", "pause_after_item_when")
#: The literal that makes a `pause_when` unconditional — no field required.
ALWAYS_LITERAL: str = "always"


def check_expressions(root: LinedMap) -> list[ValidationError]:
    """Every expression offence in the file, each at the line of the key that holds it."""
    types = declared_types(root)
    errors = _check_defaults(root, types)
    for node, loops in iter_scoped_steps(root):
        scope = {**types, **loops}
        if is_for_each(node):
            errors += _check_for_each(node, scope)
            continue
        errors += _check_step(node, scope)
    return errors


def _check_defaults(root: LinedMap, types: dict[str, str]) -> list[ValidationError]:
    """An input default is substituted like any other value, so it is read like one.

    An unbound name in a default survives into every Run that takes it, which is exactly
    the Run nobody looked at.
    """
    inputs = as_map(root.get("inputs"))
    if inputs is None:
        return []
    errors: list[ValidationError] = []
    for name in inputs:
        decl = as_map(inputs[name])
        if decl is None or DEFAULT_KEY not in decl:
            continue
        at = key_line(decl, DEFAULT_KEY, decl.line)
        errors += _scan(decl[DEFAULT_KEY], types, at)
    return errors


def _check_for_each(node: LinedMap, outer: Scope) -> list[ValidationError]:
    """`for_each` and `only` read the enclosing scope; pauses and `bind` values add the item.

    `outer` is the inputs plus the names of the loops around this one. A loop's own `as`
    is not visible to its own `for_each`, and its own `bind` names to nothing of its own.
    """
    errors: list[ValidationError] = []
    source = node.get(FOR_EACH_KEY)
    at = key_line(node, FOR_EACH_KEY, node.line)
    if not isinstance(source, str):
        errors.append(problem(at, EXPRESSION_SYNTAX))
    else:
        if "{{" not in source:
            errors.append(problem(at, EXPRESSION_SYNTAX))
        errors += _scan_text(source, outer, at)
    if isinstance(only_val := node.get("only"), str):
        errors += _scan_text(only_val, outer, key_line(node, "only", node.line))
    declared = node.get(AS_KEY)
    inner = {**outer, declared: ITEM_TYPE} if isinstance(declared, str) else outer
    for key in CONDITION_KEYS:
        if key in node:
            errors += _check_condition(node[key], inner, key_line(node, key, node.line))
    return errors + _check_bind_values(node, inner)


def _check_bind_values(node: LinedMap, scope: Scope) -> list[ValidationError]:
    """Each `bind` value is text read against `scope`; a whole entity is not text."""
    bound = as_map(node.get(BIND_KEY))
    if bound is None:
        return []
    errors: list[ValidationError] = []
    for name in bind_names(node):
        value = bound[name]
        if not isinstance(value, str):
            continue
        at = key_line(bound, name, node.line)
        errors += _scan_text(value, scope, at)
        whole = WHOLE_VARIABLE.match(value)
        if whole is not None and scope.get(whole.group(1)) in ENTITY_TYPES:
            errors.append(problem(at, INVALID_VALUE))
    return errors


def _check_step(node: LinedMap, scope: dict[str, str]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key, value in node.items():
        at = key_line(node, key, node.line)
        if key == ESCALATE_KEY:
            errors += _check_escalate(value, at)
        elif key in CONDITION_KEYS:
            errors += _check_condition(value, scope, at)
        else:
            errors += _scan(value, scope, at)
        if key in MINUTES_KEYS:
            errors += _check_minutes_types(value, scope, at)
    return errors


def _check_minutes_types(value: Any, scope: dict[str, str], line: int) -> list[ValidationError]:
    """A limit reads a `number` or `string` input, or a field of a loop item, never an entity."""
    if not isinstance(value, str):
        return []
    errors: list[ValidationError] = []
    for inner in EXPRESSION.findall(value):
        match = VARIABLE.match(inner)
        if match is None or match.group(1) not in scope:
            continue
        declared, field = scope[match.group(1)], match.group(2)
        readable = declared == ITEM_TYPE if field else declared in MINUTES_TYPES
        if not readable:
            errors.append(problem(line, INVALID_TIMEOUT))
    return errors


def _scan(value: Any, scope: dict[str, str], line: int) -> list[ValidationError]:
    """Every `{{ }}` anywhere under this value, reported at the nearest key's line."""
    if isinstance(value, str):
        return _scan_text(value, scope, line)
    errors: list[ValidationError] = []
    mapping = as_map(value)
    if mapping is not None:
        for key, sub in mapping.items():
            errors += _scan(sub, scope, key_line(mapping, key, line))
        return errors
    sequence = as_seq(value)
    if sequence is not None:
        for item in sequence:
            errors += _scan(item, scope, line)
    return errors


def _scan_text(text: str, scope: dict[str, str], line: int) -> list[ValidationError]:
    """Every complete `{{ }}` in the text, and then whatever braces were left over.

    An unbalanced `{{` is not an expression the grammar rejects — it is text the grammar
    never saw, which would reach a harness verbatim. It is reported like any other one.
    """
    errors: list[ValidationError] = []
    for inner in EXPRESSION.findall(text):
        match = VARIABLE.match(inner)
        if match is None:
            errors.append(problem(line, EXPRESSION_SYNTAX))
            continue
        errors += _check_reference(match.group(1), match.group(2), scope, line)
    remainder = EXPRESSION.sub("", text)
    if OPEN in remainder or CLOSE in remainder:
        errors.append(problem(line, EXPRESSION_SYNTAX))
    return errors


def _check_reference(
    name: str, field: str | None, scope: dict[str, str], line: int
) -> list[ValidationError]:
    if name not in scope:
        return [problem(line, UNBOUND_VARIABLE)]
    if field is None:
        return []
    if scope[name] == ITEM_TYPE:
        return []
    if field in ENTITY_FIELDS.get(scope[name], frozenset()):
        return []
    return [problem(line, UNKNOWN_FIELD)]


def _check_condition(value: Any, scope: dict[str, str], line: int) -> list[ValidationError]:
    """A single item field, written bare: `story.spec_checkpoint`, never in braces.

    The literal `"always"` is also accepted — it makes a condition unconditional, with no
    field to check. Everything else that does not match `BARE_FIELD` is `expression syntax`.
    """
    if not isinstance(value, str):
        return []
    if value == ALWAYS_LITERAL:
        return []
    match = BARE_FIELD.match(value)
    if match is None:
        return [problem(line, EXPRESSION_SYNTAX)]
    return _check_reference(match.group(1), match.group(2), scope, line)


def _check_escalate(value: Any, line: int) -> list[ValidationError]:
    """`output.status == <token>` — the one comparison the grammar allows (FR-16)."""
    if not isinstance(value, str):
        return []
    match = ESCALATE.match(value)
    if match is None:
        return [problem(line, EXPRESSION_SYNTAX)]
    if match.group(1) in STATUS_TOKENS:
        return []
    return [problem(line, INVALID_STATUS_TOKEN)]
