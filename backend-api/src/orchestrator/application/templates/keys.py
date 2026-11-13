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

from collections.abc import Sequence

from orchestrator.application.steps import (
    AGENT_KIND,
    GATES,
    KIND_META,
    SUBMODULE_BRANCH_KEY,
    SUBMODULE_CHECKOUT_KEYS,
    SUBMODULE_KIND,
    SUBMODULE_UPDATE_KEY,
    SUBMODULE_WORKDIR_KEY,
    TEMPLATE_CALL_KIND,
    TEMPLATE_KINDS,
)
from orchestrator.application.templates.agent import check_agent_extras
from orchestrator.application.templates.inputs import check_inputs, declared_types
from orchestrator.application.templates.lines import (
    STEPS_KEY,
    LinedMap,
    as_map,
    as_seq,
    child_steps,
    is_for_each,
    key_line,
    line_of,
)
from orchestrator.application.templates.loops import check_for_each
from orchestrator.application.templates.model import (
    ALL_DIGIT_STEP_ID,
    CALL_TIMING,
    DUPLICATE_STEP_ID,
    EMPTY_STEPS,
    INVALID_DISPATCH_FORM,
    INVALID_GATE,
    INVALID_SLUG,
    INVALID_SUBMODULE_FORM,
    INVALID_TIMEOUT,
    MISSING_KEY,
    NON_LITERAL_VERSION,
    UNKNOWN_KEY,
    UNKNOWN_KIND,
    USES_AND_RUN,
    ValidationError,
    unknown_role,
)
from orchestrator.application.templates.on_fail import check_on_fail
from orchestrator.application.templates.table import (
    AGENT_DISPATCH_KEYS,
    AGENT_INTENT_KEYS,
    AGENT_KEYS,
    CALL_TIMING_KEYS,
    ID_KEY,
    NAME_KEY,
    ROLE_KEY,
    RUN_KEY,
    RUN_SUGAR_KIND,
    STEP_KEYS,
    STEP_ROLES,
    TEMPLATE_KEYS,
    USES_KEY,
    VERSION_KEY,
    is_count,
    is_minutes,
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
    if NAME_KEY not in root:
        errors.append(problem(root.line, MISSING_KEY))
    elif not is_slug(root[NAME_KEY]):
        errors.append(problem(key_line(root, NAME_KEY, root.line), INVALID_SLUG))
    if VERSION_KEY not in root:
        errors.append(problem(root.line, MISSING_KEY))
    elif not is_count(root[VERSION_KEY]):
        errors.append(problem(key_line(root, VERSION_KEY, root.line), NON_LITERAL_VERSION))
    return errors


# --- walking the steps --------------------------------------------------------------------


def _id_of(node: LinedMap) -> str:
    declared = node.get(ID_KEY)
    return declared if isinstance(declared, str) else ""


def _path(node: LinedMap, enclosing: Sequence[LinedMap]) -> str | None:
    """A step's index-free path: its id under every enclosing `for_each` id (AD-15).

    `None` when any segment is not a name. These paths are the node ids 3.4 joins a graph
    to, so an empty segment would be a defect at that seam rather than a harmless blank —
    and the id itself is already reported as `invalid slug`.
    """
    segments = [*enclosing, node]
    if not all(is_slug(segment.get(ID_KEY)) for segment in segments):
        return None
    return ".".join(_id_of(segment) for segment in segments)


def _walk(root: LinedMap) -> list[tuple[LinedMap, tuple[LinedMap, ...]]]:
    """Every step mapping in document order, with the `for_each` loops it sits inside."""
    found: list[tuple[LinedMap, tuple[LinedMap, ...]]] = []

    def visit(parent: LinedMap, enclosing: tuple[LinedMap, ...]) -> None:
        for node in child_steps(parent):
            found.append((node, enclosing))
            if is_for_each(node):
                visit(node, (*enclosing, node))

    visit(root, ())
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
    errors = _entries_that_are_not_steps(root) + _check_ids(root, walked)
    input_names = set(declared_types(root))
    earlier_agents: set[str] = set()
    lists_with_loop: set[int] = set()
    for node, enclosing in walked:
        if is_for_each(node):
            owner = id(enclosing[-1] if enclosing else root)
            errors += check_for_each(
                node,
                enclosing,
                seen_in_list=owner in lists_with_loop,
                input_names=input_names,
                non_steps=_entries_that_are_not_steps(node),
            )
            lists_with_loop.add(owner)
            continue
        errors += _check_step(node, enclosing, earlier_agents, unvalidated)
        if node.get(USES_KEY) == AGENT_KIND:
            earlier_agents.add(_id_of(node))
    return errors


def _check_ids(
    root: LinedMap, walked: list[tuple[LinedMap, tuple[LinedMap, ...]]]
) -> list[ValidationError]:
    """An id is a slug, unique within its own `steps` list — a loop's id included.

    The same id may appear in the root list and inside a loop; the index-free path
    (`epics.setup`) tells them apart.
    """
    errors: list[ValidationError] = []
    seen: dict[int, set[str]] = {}
    for node, enclosing in walked:
        if ID_KEY not in node:
            errors.append(problem(node.line, MISSING_KEY))
            continue
        line = key_line(node, ID_KEY, node.line)
        if isinstance(node[ID_KEY], str) and node[ID_KEY].isdigit() and node[ID_KEY].isascii():
            errors.append(problem(line, ALL_DIGIT_STEP_ID))
            continue
        if not is_slug(node[ID_KEY]):
            errors.append(problem(line, INVALID_SLUG))
            continue
        ids = seen.setdefault(id(enclosing[-1] if enclosing else root), set())
        if node[ID_KEY] in ids:
            errors.append(problem(line, DUPLICATE_STEP_ID))
        ids.add(node[ID_KEY])
    return errors


# --- one step -----------------------------------------------------------------------------


def _check_step(
    node: LinedMap,
    enclosing: tuple[LinedMap, ...],
    earlier_agents: set[str],
    unvalidated: list[str],
) -> list[ValidationError]:
    kind, errors = _kind_of(node)
    errors += unknown_keys(node, STEP_KEYS | AGENT_KEYS if kind == AGENT_KIND else STEP_KEYS)
    errors += _check_role(node)
    if kind is None:
        return errors
    errors += _check_with(node, kind)
    errors += _check_gate(node, enclosing, kind, unvalidated)
    if kind == TEMPLATE_CALL_KIND:
        return errors + _call_timing(node)
    if kind == AGENT_KIND:
        errors += check_agent_extras(node)
    errors += _check_minutes(node, "timeout_min") + _check_minutes(node, "stall_min")
    return errors + check_on_fail(node, earlier_agents, kind)


def _check_role(node: LinedMap) -> list[ValidationError]:
    if ROLE_KEY not in node:
        return []
    value = node[ROLE_KEY]
    if isinstance(value, str) and value in STEP_ROLES:
        return []
    return [problem(key_line(node, ROLE_KEY, node.line), unknown_role(value))]


def _kind_of(node: LinedMap) -> tuple[str | None, list[ValidationError]]:
    """The step's kind, resolving the `run:` sugar; `None` when the file does not say."""
    has_uses, has_run = USES_KEY in node, "run" in node
    if has_uses and has_run:
        return None, [problem(key_line(node, "run", node.line), USES_AND_RUN)]
    if has_run:
        return _run_sugar(node)
    if not has_uses:
        return None, [problem(node.line, MISSING_KEY)]
    if node[USES_KEY] in TEMPLATE_KINDS:
        return str(node[USES_KEY]), []
    return None, [problem(key_line(node, USES_KEY, node.line), UNKNOWN_KIND)]


def _run_sugar(node: LinedMap) -> tuple[str | None, list[ValidationError]]:
    """`run: <command>` is a `shell` step. The command is the whole of what it says."""
    command = node[RUN_KEY]
    if not isinstance(command, str) or not command:
        return None, [problem(key_line(node, RUN_KEY, node.line), MISSING_KEY)]
    if "with" in node:
        return RUN_SUGAR_KIND, [problem(key_line(node, "with", node.line), UNKNOWN_KEY)]
    return RUN_SUGAR_KIND, []


def _check_dispatch_form(params: LinedMap, with_line: int) -> list[ValidationError]:
    """More than one dispatch key in the same `with` block is ambiguous and rejected."""
    if sum(1 for k in params if k in AGENT_DISPATCH_KEYS) > 1:
        return [problem(with_line, INVALID_DISPATCH_FORM)]
    return []


def _check_submodule_form(params: LinedMap, with_line: int) -> list[ValidationError]:
    """A `git.submodule` `with` is one of the kind's two forms, never a mixture of them.

    The spine's DSL row, verbatim: "the two forms are told apart by their keys; keys of both
    forms together, or `workdir` without `branch`, is a validation error". Only those two
    shapes are judged here, because only those two are what the spine fixes; every other way
    of writing the block is decided against the *resolved* row by `steps/git_submodule.py`,
    which is where a value rather than a key can be looked at at all.
    """
    present = set(params) & (SUBMODULE_CHECKOUT_KEYS | {SUBMODULE_UPDATE_KEY})
    mixed = SUBMODULE_UPDATE_KEY in present and bool(present & SUBMODULE_CHECKOUT_KEYS)
    if mixed or (SUBMODULE_WORKDIR_KEY in present and SUBMODULE_BRANCH_KEY not in present):
        return [problem(with_line, INVALID_SUBMODULE_FORM)]
    return []


def _check_with(node: LinedMap, kind: str) -> list[ValidationError]:
    if "with" not in node:
        if kind == TEMPLATE_CALL_KIND:
            return [problem(node.line, MISSING_KEY)]
        return []
    line = key_line(node, "with", node.line)
    params = as_map(node["with"])
    if params is None:
        return [problem(line, MISSING_KEY)]
    base = KIND_META[kind].with_keys
    allowed = base | AGENT_DISPATCH_KEYS | AGENT_INTENT_KEYS if kind == AGENT_KIND else base
    errors = unknown_keys(params, allowed)
    if kind == AGENT_KIND:
        errors += _check_dispatch_form(params, line)
    if kind == SUBMODULE_KIND:
        errors += _check_submodule_form(params, line)
    if kind == TEMPLATE_CALL_KIND:
        errors += _check_call_with(params)
    return errors


def _check_call_with(params: LinedMap) -> list[ValidationError]:
    """A call names its callee with a literal name; a `version`, when written, is a literal.

    No `version` is an unpinned call, resolved to the callee's latest by `calls.py`.
    """
    errors: list[ValidationError] = []
    if not isinstance(params.get(NAME_KEY), str):
        errors.append(problem(key_line(params, NAME_KEY, params.line), MISSING_KEY))
    if VERSION_KEY in params and not is_count(params[VERSION_KEY]):
        errors.append(problem(key_line(params, VERSION_KEY, params.line), NON_LITERAL_VERSION))
    return errors


def _check_gate(
    node: LinedMap, enclosing: tuple[LinedMap, ...], kind: str, unvalidated: list[str]
) -> list[ValidationError]:
    if "gate" not in node:
        path = _path(node, enclosing)
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


def _check_minutes(node: LinedMap, key: str) -> list[ValidationError]:
    if key not in node or is_minutes(node[key]):
        return []
    return [problem(key_line(node, key, node.line), INVALID_TIMEOUT)]
