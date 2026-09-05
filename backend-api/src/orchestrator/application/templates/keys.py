"""The key table: which keys a Template may write, where, and with what value.

This is the "Template DSL v1 keys" table of the Structural Seed, made executable. Nothing
here enumerates a step kind: the accepted kinds and the `with` keys of each come from
`application/steps.KIND_META`, which is the only enumeration there is (AD-9). The `inputs:`
block is `inputs.py` and the shared nouns are `table.py`; both were split off this module
for the 400-line limit, not because the table is in more than one place.

Three rules shape every function below:

- **Nothing raises.** A subtree that is not the shape the table describes is reported and
  then skipped, so one malformed step does not hide the problems in the next one.
- **A key or its scalar value is reported at the key's own line**, a nested mapping or
  sequence at its own; `lines.key_line` and `LinedMap.line` are the two readers for that.
- **A missing `gate` is not an error.** It is a path in `unvalidated` (NFR-2), collected for
  every executable step — a `for_each` construct and a `uses: template` step are not rows,
  so they are never reported.
"""

from __future__ import annotations

from orchestrator.application.steps import (
    AGENT_KIND,
    GATES,
    KIND_META,
    TEMPLATE_CALL_KIND,
    TEMPLATE_KINDS,
)
from orchestrator.application.templates.agent import check_agent_extras
from orchestrator.application.templates.inputs import check_inputs
from orchestrator.application.templates.lines import (
    AS_KEY,
    STEPS_KEY,
    LinedMap,
    as_map,
    as_seq,
    child_steps,
    is_for_each,
    key_line,
    line_of,
)
from orchestrator.application.templates.model import (
    BAD_REDISPATCH,
    CALL_TIMING,
    DUPLICATE_STEP_ID,
    EMPTY_STEPS,
    INVALID_GATE,
    INVALID_ON_FAIL,
    INVALID_SLUG,
    INVALID_TIMEOUT,
    MISSING_KEY,
    NESTED_FOR_EACH,
    NON_LITERAL_VERSION,
    ON_FAIL_ACTIONS,
    PARALLEL_RESERVED,
    SECOND_FOR_EACH,
    UNKNOWN_KEY,
    UNKNOWN_KIND,
    USES_AND_RUN,
    ValidationError,
)
from orchestrator.application.templates.table import (
    AGENT_KEYS,
    CALL_TIMING_KEYS,
    FOR_EACH_KEYS,
    REDISPATCH_KEYS,
    RUN_KEY,
    RUN_SUGAR_KIND,
    STEP_KEYS,
    TEMPLATE_KEYS,
    is_count,
    is_slug,
    problem,
    unknown_keys,
)


def check_keys(root: LinedMap) -> tuple[list[ValidationError], list[str]]:
    """Every key-table offence in the file, and the path of every step with no `gate`."""
    unvalidated: list[str] = []
    errors = _check_template(root)
    errors += check_inputs(root)
    errors += _check_steps(root, unvalidated)
    return errors, unvalidated


# --- template level -----------------------------------------------------------------------


def _check_template(root: LinedMap) -> list[ValidationError]:
    errors = unknown_keys(root, TEMPLATE_KEYS)
    if "name" not in root:
        errors.append(problem(root.line, MISSING_KEY))
    elif not is_slug(root["name"]):
        errors.append(problem(key_line(root, "name", root.line), INVALID_SLUG))
    if "version" not in root:
        errors.append(problem(root.line, MISSING_KEY))
    elif not is_count(root["version"]):
        errors.append(problem(key_line(root, "version", root.line), NON_LITERAL_VERSION))
    return errors


# --- walking the steps --------------------------------------------------------------------


def _id_of(node: LinedMap) -> str:
    declared = node.get("id")
    return declared if isinstance(declared, str) else ""


def _path(node: LinedMap, parent: LinedMap | None) -> str | None:
    """A step's index-free path: its id, under the enclosing `for_each` id (AD-15).

    `None` when any segment is not a name. These paths are the node ids 3.4 joins a graph
    to, so an empty segment would be a defect at that seam rather than a harmless blank —
    and the id itself is already reported as `invalid slug`.
    """
    if not is_slug(node.get("id")):
        return None
    if parent is None:
        return _id_of(node)
    if not is_slug(parent.get("id")):
        return None
    return f"{_id_of(parent)}.{_id_of(node)}"


def _walk(root: LinedMap) -> list[tuple[LinedMap, LinedMap | None]]:
    """Every step mapping in document order, with the `for_each` it sits inside."""
    found: list[tuple[LinedMap, LinedMap | None]] = []
    for node in child_steps(root):
        found.append((node, None))
        if is_for_each(node):
            for nested in child_steps(node):
                found.append((nested, node))
    return found


def _entries_that_are_not_steps(node: LinedMap) -> list[ValidationError]:
    """A `steps:` entry that is not a mapping is a step that would vanish from the plan."""
    entries = as_seq(node.get(STEPS_KEY))
    if entries is None:
        return []
    errors: list[ValidationError] = []
    for entry in entries:
        if as_map(entry) is None:
            errors.append(problem(line_of(entry, entries.line), MISSING_KEY))
    return errors


def _check_steps(root: LinedMap, unvalidated: list[str]) -> list[ValidationError]:
    if not as_seq(root.get(STEPS_KEY)):
        return [problem(key_line(root, STEPS_KEY, root.line), EMPTY_STEPS)]
    walked = _walk(root)
    errors = _entries_that_are_not_steps(root) + _check_ids(walked)
    earlier_agents: set[str] = set()
    seen_for_each = False
    for node, parent in walked:
        if is_for_each(node):
            errors += _check_for_each(node, parent, seen_for_each=seen_for_each)
            seen_for_each = seen_for_each or parent is None
            continue
        errors += _check_step(node, parent, earlier_agents, unvalidated)
        if node.get("uses") == AGENT_KIND:
            earlier_agents.add(_id_of(node))
    return errors


def _check_ids(walked: list[tuple[LinedMap, LinedMap | None]]) -> list[ValidationError]:
    """An id is a slug, unique across the whole file — the loop construct's id included."""
    errors: list[ValidationError] = []
    seen: set[str] = set()
    for node, _ in walked:
        if "id" not in node:
            errors.append(problem(node.line, MISSING_KEY))
            continue
        line = key_line(node, "id", node.line)
        if not is_slug(node["id"]):
            errors.append(problem(line, INVALID_SLUG))
            continue
        if node["id"] in seen:
            errors.append(problem(line, DUPLICATE_STEP_ID))
        seen.add(node["id"])
    return errors


#: What each `for_each` pause key plans a checkpoint row at, as the row's last segment
#: (AD-7: `…stories[n].before` / `…stories[n].after`). Declaring the key reserves the word.
ITEM_CHECKPOINT_IDS: dict[str, str] = {
    "pause_before_item_when": "before",
    "pause_after_item_when": "after",
}


def _reserved_item_ids(node: LinedMap) -> list[ValidationError]:
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


def _check_for_each(
    node: LinedMap, parent: LinedMap | None, *, seen_for_each: bool
) -> list[ValidationError]:
    errors = unknown_keys(node, FOR_EACH_KEYS)
    if "parallel" in node:
        errors.append(problem(key_line(node, "parallel", node.line), PARALLEL_RESERVED))
    if parent is not None:
        errors.append(problem(node.line, NESTED_FOR_EACH))
    elif seen_for_each:
        errors.append(problem(node.line, SECOND_FOR_EACH))
    if AS_KEY not in node:
        errors.append(problem(node.line, MISSING_KEY))
    elif not is_slug(node[AS_KEY]):
        errors.append(problem(key_line(node, AS_KEY, node.line), INVALID_SLUG))
    if not child_steps(node):
        errors.append(problem(key_line(node, STEPS_KEY, node.line), EMPTY_STEPS))
    return errors + _reserved_item_ids(node) + _entries_that_are_not_steps(node)


# --- one step -----------------------------------------------------------------------------


def _check_step(
    node: LinedMap,
    parent: LinedMap | None,
    earlier_agents: set[str],
    unvalidated: list[str],
) -> list[ValidationError]:
    kind, errors = _kind_of(node)
    errors += unknown_keys(node, STEP_KEYS | AGENT_KEYS if kind == AGENT_KIND else STEP_KEYS)
    if kind is None:
        return errors
    errors += _check_with(node, kind)
    errors += _check_gate(node, parent, kind, unvalidated)
    if kind == TEMPLATE_CALL_KIND:
        return errors + _call_timing(node)
    if kind == AGENT_KIND:
        errors += check_agent_extras(node)
    errors += _check_timeout(node)
    return errors + _check_on_fail(node, earlier_agents)


def _kind_of(node: LinedMap) -> tuple[str | None, list[ValidationError]]:
    """The step's kind, resolving the `run:` sugar; `None` when the file does not say."""
    has_uses, has_run = "uses" in node, "run" in node
    if has_uses and has_run:
        return None, [problem(key_line(node, "run", node.line), USES_AND_RUN)]
    if has_run:
        return _run_sugar(node)
    if not has_uses:
        return None, [problem(node.line, MISSING_KEY)]
    if node["uses"] in TEMPLATE_KINDS:
        return str(node["uses"]), []
    return None, [problem(key_line(node, "uses", node.line), UNKNOWN_KIND)]


def _run_sugar(node: LinedMap) -> tuple[str | None, list[ValidationError]]:
    """`run: <command>` is a `shell` step. The command is the whole of what it says."""
    command = node[RUN_KEY]
    if not isinstance(command, str) or not command:
        return None, [problem(key_line(node, RUN_KEY, node.line), MISSING_KEY)]
    if "with" in node:
        return RUN_SUGAR_KIND, [problem(key_line(node, "with", node.line), UNKNOWN_KEY)]
    return RUN_SUGAR_KIND, []


def _check_with(node: LinedMap, kind: str) -> list[ValidationError]:
    if "with" not in node:
        if kind == TEMPLATE_CALL_KIND:
            return [problem(node.line, MISSING_KEY)]
        return []
    line = key_line(node, "with", node.line)
    params = as_map(node["with"])
    if params is None:
        return [problem(line, MISSING_KEY)]
    errors = unknown_keys(params, KIND_META[kind].with_keys)
    if kind == TEMPLATE_CALL_KIND:
        errors += _check_call_with(params)
    return errors


def _check_call_with(params: LinedMap) -> list[ValidationError]:
    """A call names its callee with a literal name and a literal version."""
    errors: list[ValidationError] = []
    if not isinstance(params.get("name"), str):
        errors.append(problem(key_line(params, "name", params.line), MISSING_KEY))
    if "version" not in params:
        errors.append(problem(params.line, MISSING_KEY))
    elif not is_count(params["version"]):
        errors.append(problem(key_line(params, "version", params.line), NON_LITERAL_VERSION))
    return errors


def _check_gate(
    node: LinedMap, parent: LinedMap | None, kind: str, unvalidated: list[str]
) -> list[ValidationError]:
    if "gate" not in node:
        path = _path(node, parent)
        if kind != TEMPLATE_CALL_KIND and path is not None and path not in unvalidated:
            unvalidated.append(path)
        return []
    if node["gate"] in GATES:
        return []
    return [problem(key_line(node, "gate", node.line), INVALID_GATE)]


def _call_timing(node: LinedMap) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for key in CALL_TIMING_KEYS:
        if key in node:
            errors.append(problem(key_line(node, key, node.line), CALL_TIMING))
    return errors


def _check_timeout(node: LinedMap) -> list[ValidationError]:
    if "timeout_min" not in node or is_count(node["timeout_min"]):
        return []
    return [problem(key_line(node, "timeout_min", node.line), INVALID_TIMEOUT)]


def _check_on_fail(node: LinedMap, earlier_agents: set[str]) -> list[ValidationError]:
    """`escalate | fail | continue`, or a redispatch to an `agent` step written earlier."""
    if "on_fail" not in node:
        return []
    line = key_line(node, "on_fail", node.line)
    value = node["on_fail"]
    if isinstance(value, str):
        return [] if value in ON_FAIL_ACTIONS else [problem(line, INVALID_ON_FAIL)]
    redispatch = as_map(value)
    if redispatch is None or set(redispatch) != REDISPATCH_KEYS:
        return [problem(line, INVALID_ON_FAIL)]
    if not is_count(redispatch["max"]):
        return [problem(line, INVALID_ON_FAIL)]
    if redispatch["redispatch"] in earlier_agents:
        return []
    return [problem(line, BAD_REDISPATCH)]
