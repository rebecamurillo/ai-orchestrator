"""The `for_each` construct's own rules: its keys, its depth, its `bind`, its names.

Split out of `keys.py` for the module-length limit. A loop may hold one loop among its
`steps` (AD-15 amendment, 2026-11-06): a third level is `nested for_each`, a second loop in
one `steps` list is `second for_each`. `bind` adds names per item; the name rule keeps every
name visible to a step bound exactly once.

A `bind` key is read through `LinedMap.key_order`, which holds every constructed key with
its own line. A key that is not a string (`5`, `~`, a date) is reported there before any
regex or `str` method sees it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from orchestrator.application.templates.lines import (
    AS_KEY,
    BIND_KEY,
    NAME_PATTERN,
    STEPS_KEY,
    LinedMap,
    as_map,
    bind_names,
    child_steps,
    key_line,
)
from orchestrator.application.templates.model import (
    DUPLICATE_STEP_ID,
    EMPTY_STEPS,
    INVALID_SLUG,
    INVALID_VALUE,
    LOOP_NAME_BOUND,
    MISSING_KEY,
    NESTED_FOR_EACH,
    PARALLEL_RESERVED,
    SECOND_FOR_EACH,
    ValidationError,
)
from orchestrator.application.templates.table import FOR_EACH_KEYS, is_slug, problem, unknown_keys

#: What each `for_each` pause key plans a checkpoint row at, as the row's last segment
#: (AD-7: `…stories[n].before` / `…stories[n].after`). Declaring the key reserves the word.
ITEM_CHECKPOINT_IDS: dict[str, str] = {
    "pause_before_item_when": "before",
    "pause_after_item_when": "after",
}

#: How many loops may enclose a loop: a loop inside a loop is allowed, a third level is not.
MAX_ENCLOSING = 1

_NAME = re.compile(NAME_PATTERN)


def reserved_item_ids(node: LinedMap) -> list[ValidationError]:
    """An inner step may not take the path a pause key already plans a row at.

    `pause_after_item_when` plans `{loop}.after`, which is the path an inner step with id
    `after` would also occupy — one path, two rows, and the graph's node ids stop being the
    unique key `unvalidated` joins to (AD-15). That is exactly what two steps sharing an id
    does, so it reports the same reason rather than minting a nineteenth.
    """
    reserved = {word for key, word in ITEM_CHECKPOINT_IDS.items() if key in node}
    return [
        problem(key_line(child, "id", child.line), DUPLICATE_STEP_ID)
        for child in child_steps(node)
        if child.get("id") in reserved
    ]


def check_for_each(
    node: LinedMap,
    enclosing: Sequence[LinedMap],
    *,
    seen_in_list: bool,
    input_names: set[str],
    non_steps: list[ValidationError],
) -> list[ValidationError]:
    """Every loop-level offence of one `for_each` node.

    `enclosing` is the loops around it, outermost first; `seen_in_list` is whether an
    earlier entry of the same `steps` list was a loop. `non_steps` is the offences for
    entries of its `steps` that are not mappings (the caller owns that reader).
    """
    errors = unknown_keys(node, FOR_EACH_KEYS)
    if "parallel" in node:
        errors.append(problem(key_line(node, "parallel", node.line), PARALLEL_RESERVED))
    if len(enclosing) > MAX_ENCLOSING:
        errors.append(problem(node.line, NESTED_FOR_EACH))
    if seen_in_list:
        errors.append(problem(node.line, SECOND_FOR_EACH))
    errors += _check_as(node, enclosing)
    if not child_steps(node):
        errors.append(problem(key_line(node, STEPS_KEY, node.line), EMPTY_STEPS))
    errors += check_bind(node, enclosing, input_names)
    return errors + reserved_item_ids(node) + non_steps


def _check_as(node: LinedMap, enclosing: Sequence[LinedMap]) -> list[ValidationError]:
    if AS_KEY not in node:
        return [problem(node.line, MISSING_KEY)]
    at = key_line(node, AS_KEY, node.line)
    if not is_slug(node[AS_KEY]):
        return [problem(at, INVALID_SLUG)]
    if node[AS_KEY] in _enclosing_names(enclosing):
        return [problem(at, LOOP_NAME_BOUND)]
    return []


def _enclosing_names(enclosing: Sequence[LinedMap]) -> set[str]:
    """Every `as` and `bind` name an enclosing loop already holds."""
    names: set[str] = set()
    for outer in enclosing:
        declared = outer.get(AS_KEY)
        if isinstance(declared, str):
            names.add(declared)
        names.update(bind_names(outer))
    return names


def check_bind(
    node: LinedMap, enclosing: Sequence[LinedMap], input_names: set[str]
) -> list[ValidationError]:
    """The shape of `bind` (a map of names to strings) and the name rule."""
    if BIND_KEY not in node:
        return []
    bound = as_map(node[BIND_KEY])
    if bound is None:
        return [problem(key_line(node, BIND_KEY, node.line), INVALID_VALUE)]
    taken = _enclosing_names(enclosing) | input_names
    own = node.get(AS_KEY)
    if isinstance(own, str):
        taken.add(own)
    errors: list[ValidationError] = []
    seen: set[str] = set()
    for key, line in bound.key_order:
        if not isinstance(key, str) or _NAME.fullmatch(key) is None:
            errors.append(problem(line, INVALID_VALUE))
            continue
        if key in taken or key in seen:
            errors.append(problem(line, LOOP_NAME_BOUND))
        elif not isinstance(bound[key], str):
            errors.append(problem(line, INVALID_VALUE))
        seen.add(key)
    return errors
