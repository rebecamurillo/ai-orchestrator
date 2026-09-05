"""The `inputs:` block of a Template: one declared type per name, and what may default it.

Split out of `keys.py` for the module-length limit; the rules are the "input" row of the
key table. A declaration that cannot be read is reported and skipped, so a malformed
`inputs:` block never hides the step-level problems in the same file.
"""

from __future__ import annotations

from orchestrator.application.templates.lines import LinedMap, as_map, as_seq, key_line
from orchestrator.application.templates.model import (
    BAD_DEFAULT,
    INPUT_TYPES,
    INVALID_INPUT_TYPE,
    INVALID_VALUE,
    MISSING_KEY,
    UNKNOWN_KEY,
    ValidationError,
)
from orchestrator.application.templates.table import (
    INPUT_KEYS,
    TEXT_TYPES,
    problem,
    unknown_keys,
)

#: The one type whose values are listed in the file rather than known to the system.
ENUM = "enum"
NUMBER = "number"


def check_inputs(root: LinedMap) -> list[ValidationError]:
    """Every offence in the template's `inputs:` map. No block at all is not an offence."""
    if "inputs" not in root:
        return []
    line = key_line(root, "inputs", root.line)
    inputs = as_map(root["inputs"])
    if inputs is None:
        return [problem(line, MISSING_KEY)]
    errors: list[ValidationError] = []
    for name in inputs:
        errors += _check_input(inputs, name)
    return errors


def declared_inputs(root: LinedMap) -> dict[str, tuple[str, bool]]:
    """The declared type of each input that has one, and whether the file requires it.

    Read of the file being validated to know what `{{name}}` may mean, and of a callee's
    stored file to know what a caller must bind. An entry the file did not give a type is
    left out: `check_inputs` has already reported it, and guessing here would report it
    twice under a different reason.
    """
    found: dict[str, tuple[str, bool]] = {}
    inputs = as_map(root.get("inputs"))
    if inputs is None:
        return found
    for name, decl in inputs.items():
        mapping = as_map(decl)
        if mapping is None:
            continue
        declared = mapping.get("type")
        if isinstance(declared, str):
            found[str(name)] = (declared, mapping.get("required") is True)
    return found


def declared_types(root: LinedMap) -> dict[str, str]:
    """The declared type of each input — the caller's scope, for an expression or binding."""
    return {name: declared for name, (declared, _) in declared_inputs(root).items()}


def _check_input(inputs: LinedMap, name: str) -> list[ValidationError]:
    line = key_line(inputs, name, inputs.line)
    decl = as_map(inputs[name])
    if decl is None:
        return [problem(line, MISSING_KEY)]
    errors = unknown_keys(decl, INPUT_KEYS)
    if "type" not in decl:
        return [*errors, problem(line, MISSING_KEY)]
    declared = decl["type"]
    if declared not in INPUT_TYPES:
        return [*errors, problem(key_line(decl, "type", line), INVALID_INPUT_TYPE)]
    errors += _check_values(decl, str(declared), line)
    return errors + _check_default(decl, str(declared), line)


def _check_values(decl: LinedMap, declared: str, line: int) -> list[ValidationError]:
    """`values` belongs to `enum` and to nothing else, and an `enum` needs one."""
    values_line = key_line(decl, "values", line)
    if declared != ENUM:
        if "values" in decl:
            return [problem(values_line, UNKNOWN_KEY)]
        return []
    listed = as_seq(decl.get("values"))
    if listed is None:
        return [problem(values_line, MISSING_KEY)]
    for value in listed:
        if not isinstance(value, str):
            return [problem(values_line, INVALID_VALUE)]
    return []


def _check_default(decl: LinedMap, declared: str, line: int) -> list[ValidationError]:
    if "default" not in decl:
        return []
    if _fits_type(decl["default"], declared, decl.get("values")):
        return []
    return [problem(key_line(decl, "default", line), BAD_DEFAULT)]


def _fits_type(value: object, declared: str, values: object) -> bool:
    """`project`, `repository` and `item` are bound at run time; a default cannot fit one."""
    if declared in TEXT_TYPES:
        return isinstance(value, str)
    if declared == NUMBER:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if declared == ENUM:
        return value in (as_seq(values) or [])
    return False
