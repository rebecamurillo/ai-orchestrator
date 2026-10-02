"""`uses: template` calls: does the callee exist, is it bound correctly, and how deep?

Composition is what makes `initiative -> epic -> story` one Run instead of three, so the
things that go wrong with it are checked here and nowhere else:

- **The callee must exist.** It is fetched through `TemplateVersionRepository`; this module
  performs no I/O of its own (AD-2). A version that is not stored is `callee not found`.
- **A call with no `version` is unpinned.** It resolves to the callee's highest stored
  version here, and again when a Run is planned; a name with no stored version at all is
  `callee not found`. An integer `version` is a pin and is never followed.
- **A callee's new version must not strand its unpinned callers.** `check_callers` is the
  save-time reverse check: every caller that follows the callee is re-bound against the new
  text, and a mismatch names the caller (`save_version` refuses the save on it).
- **Depth counts templates, root inclusive.** The root is 1, so `a -> b -> c -> d` reaches
  4 and is `call depth over 3`, while `initiative -> epic -> story` is 3 and passes.
- **A cycle is measured along the current call path**, pushed and popped around each
  descent. A global visited set would call a diamond — two steps of one file calling the
  same callee — a cycle, which it is not.
- **A callee sees only what it is passed.** Every `required` input of the callee must be
  bound, an input it does not declare is a mismatch, and a `{{name}}` that is the whole
  value binds by exact type equality: that is what makes a `number` bound to a `path` an
  error rather than a coercion at run time.

Below the root, the traversal reads `TemplateVersion.calls` — the callee list pinned when
that version was saved, which is exactly why the field exists. A callee's YAML is loaded
only to read its `inputs:` block; its body was validated when it was saved and is never
re-validated here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.application.steps import TEMPLATE_CALL_KIND
from orchestrator.application.templates.expressions import ITEM_TYPE, WHOLE_VARIABLE
from orchestrator.application.templates.inputs import declared_inputs, declared_types
from orchestrator.application.templates.lines import (
    LinedMap,
    as_map,
    iter_steps,
    key_line,
    load_with_lines,
)
from orchestrator.application.templates.model import (
    CALL_CYCLE,
    CALL_DEPTH,
    CALLEE_INPUT_MISMATCH,
    CALLEE_NOT_FOUND,
    ValidationError,
)
from orchestrator.application.templates.table import is_count, problem
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ports.templates import TemplateVersionRepository

#: The deepest chain of Templates a Run may be planned from, root inclusive (AD-15).
MAX_DEPTH = 3

#: The depth of the first callee: the root is 1, so the file it calls is 2.
FIRST_CALLEE_DEPTH = 2

#: A `(name, version)` pair, the key a cycle is measured on.
Ref = tuple[str, int]

#: A call as a file wrote it: the callee's name, and its version or `None` when unpinned.
Call = tuple[str, int | None]

#: The callee input types a bare literal can bind. `project`, `repository` and `item` accept
#: only a variable of exactly that type.
TEXT_BINDABLE = frozenset({"string", "path", "enum"})
NUMBER_BINDABLE = "number"


def resolve_callee(
    templates: TemplateVersionRepository, name: str, version: int | None
) -> int | None:
    """The version a call means: its pin, or the latest stored under `name`; `None` if none."""
    if version is not None:
        return version
    stored = templates.list_versions(name)
    return max(stored) if stored else None


def check_calls(root: LinedMap, templates: TemplateVersionRepository) -> list[ValidationError]:
    """Every call offence in the file, each at the line of the calling step."""
    errors: list[ValidationError] = []
    for node, item in iter_steps(root):
        if node.get("uses") != TEMPLATE_CALL_KIND:
            continue
        errors += _check_call(node, root, templates, item)
    return errors


def _root_ref(root: LinedMap) -> tuple[Ref, ...]:
    """The root's own `(name, version)`, when the file gave both — else nothing to push."""
    name, version = root.get("name"), root.get("version")
    if isinstance(name, str) and isinstance(version, int) and is_count(version):
        return ((name, version),)
    return ()


def _check_call(
    node: LinedMap,
    root: LinedMap,
    templates: TemplateVersionRepository,
    item: str | None,
) -> list[ValidationError]:
    params = as_map(node.get("with"))
    if params is None:
        return []
    name, written = params.get("name"), params.get("version")
    if not isinstance(name, str) or (written is not None and not is_count(written)):
        return []
    version = resolve_callee(templates, name, written)
    callee = templates.get(name, version) if version is not None else None
    if callee is None or version is None:
        return [problem(node.line, CALLEE_NOT_FOUND)]
    errors = _check_bindings(params, callee.yaml, root, item, node.line)
    path = _root_ref(root)
    if (name, version) in path:
        return [*errors, problem(node.line, CALL_CYCLE)]
    path = (*path, (name, version))
    for call in callee.calls:
        errors += _descend(
            (call.name, call.version), FIRST_CALLEE_DEPTH + 1, path, templates, node.line
        )
    return errors


def _descend(
    call: Call,
    depth: int,
    path: tuple[Ref, ...],
    templates: TemplateVersionRepository,
    line: int,
) -> list[ValidationError]:
    """Walk one callee's recorded calls, reporting at the root call site that reached it."""
    name, written = call
    number = resolve_callee(templates, name, written)
    if number is None:
        return [problem(line, CALLEE_NOT_FOUND)]
    ref: Ref = (name, number)
    if ref in path:
        return [problem(line, CALL_CYCLE)]
    if depth > MAX_DEPTH:
        return [problem(line, CALL_DEPTH)]
    version = templates.get(name, number)
    if version is None:
        return [problem(line, CALLEE_NOT_FOUND)]
    errors: list[ValidationError] = []
    for next_call in version.calls:
        errors += _descend(
            (next_call.name, next_call.version), depth + 1, (*path, ref), templates, line
        )
    return errors


# --- the reverse check: a new callee version against the callers that follow it --------------


def check_callers(
    name: str, callee_yaml: str, callers: Sequence[tuple[TemplateRef, str]]
) -> list[ValidationError]:
    """Every binding offence an unpinned call to `name` would have against `callee_yaml`.

    Each error is stamped with the caller's own `(name, version)` and line, since the text
    at fault is the caller's and the save being refused is the callee's. A caller whose text
    no longer parses is skipped: it was stored valid, and it is not this save's to fix.
    """
    errors: list[ValidationError] = []
    for ref, text in callers:
        loaded = load_with_lines(text)
        if loaded.root is None:
            continue
        for node, item in iter_steps(loaded.root):
            params = as_map(node.get("with"))
            if node.get("uses") != TEMPLATE_CALL_KIND or params is None:
                continue
            if params.get("name") != name or params.get("version") is not None:
                continue
            found = _check_bindings(params, callee_yaml, loaded.root, item, node.line)
            errors += [
                error.model_copy(update={"template": ref.name, "version": ref.version})
                for error in found
            ]
    return errors


# --- the bindings --------------------------------------------------------------------------


def _check_bindings(
    params: LinedMap, callee_yaml: str, root: LinedMap, item: str | None, line: int
) -> list[ValidationError]:
    declared = _callee_inputs(callee_yaml)
    caller = declared_types(root)
    if item is not None:
        caller[item] = ITEM_TYPE
    bindings = as_map(params.get("inputs"))
    if bindings is None:
        return _check_required(declared, set(), line)
    errors = _check_given(bindings, declared, caller, line)
    return errors + _check_required(declared, set(bindings), line)


def _callee_inputs(callee_yaml: str) -> dict[str, tuple[str, bool]]:
    """The callee's declared inputs. Its body is not re-validated — only read."""
    loaded = load_with_lines(callee_yaml)
    if loaded.root is None:
        return {}
    return declared_inputs(loaded.root)


def _check_given(
    bindings: LinedMap, declared: dict[str, tuple[str, bool]], caller: dict[str, str], line: int
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, value in bindings.items():
        at = key_line(bindings, name, line)
        if name not in declared:
            errors.append(problem(at, CALLEE_INPUT_MISMATCH))
        elif not _binds(value, declared[name][0], caller):
            errors.append(problem(at, CALLEE_INPUT_MISMATCH))
    return errors


def _check_required(
    declared: dict[str, tuple[str, bool]], given: set[Any], line: int
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for name, (_, required) in declared.items():
        if required and name not in given:
            errors.append(problem(line, CALLEE_INPUT_MISMATCH))
    return errors


def _binds(value: Any, callee_type: str, caller: dict[str, str]) -> bool:
    """Whether what the caller wrote can be the callee's declared type.

    A whole-value `{{name}}` binds by exact type equality; a name the caller never declared
    is left alone, because `check_expressions` already reports it as `unbound variable` and
    two reasons for one mistake help nobody.
    """
    if isinstance(value, str):
        match = WHOLE_VARIABLE.match(value)
        if match is None:
            return callee_type in TEXT_BINDABLE
        declared = caller.get(match.group(1))
        return declared is None or declared == callee_type
    if isinstance(value, int | float) and not isinstance(value, bool):
        return callee_type == NUMBER_BINDABLE
    return False
