"""The `consult` block an `agent` row may declare (AD-22): its shape, its parsed form, and
the planned block a row carries.

`consult {model, harness?, skill, on, timeout_min?, prompts {dispatch, answer}}`. A row
plans the block only when its model resolves non-empty, so a Run that names no senior
model consults nobody and every stop reaches a person as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.application.templates.lines import LinedMap, as_map, as_seq, key_line
from orchestrator.application.templates.model import (
    INVALID_CONSULT_ON,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    MISSING_KEY,
    ConsultDecl,
    ValidationError,
)
from orchestrator.application.templates.plan_model import BAD_MINUTES, PlanError
from orchestrator.application.templates.substitute import resolve
from orchestrator.application.templates.table import (
    CONSULT_KEY,
    CONSULT_KEYS,
    CONSULT_ON,
    CONSULT_PROMPTS_KEYS,
    CONSULT_REQUIRED,
    MIN_COUNT,
    PROMPTS_KEY,
    is_minutes,
    problem,
    unknown_keys,
)

#: The sub-keys whose value is handed on as text.
TEXT_KEYS = ("model", "harness", "skill")
ON_KEY = "on"
TIMEOUT_KEY = "timeout_min"
DISPATCH = "dispatch"
ANSWER = "answer"


def check_consult(
    node: LinedMap,
    stops: frozenset[str] = CONSULT_ON,
    required: tuple[str, ...] = CONSULT_REQUIRED,
) -> list[ValidationError]:
    """Every offence in one row's `consult` block, each at the line of the key holding it.

    `stops` and `required` are an agent row's by default; a `run` row's `on_fail` passes its
    own (`templates/on_fail.py`), where the one stop is implied.
    """
    if CONSULT_KEY not in node:
        return []
    line = key_line(node, CONSULT_KEY, node.line)
    block = as_map(node[CONSULT_KEY])
    if block is None:
        return [problem(line, INVALID_VALUE)]
    errors = unknown_keys(block, CONSULT_KEYS)
    errors += [problem(line, MISSING_KEY) for key in required if key not in block]
    for key in TEXT_KEYS:
        if key in block and not isinstance(block[key], str):
            errors.append(problem(key_line(block, key, line), INVALID_VALUE))
    if ON_KEY in block and not _known_stops(block[ON_KEY], stops):
        errors.append(problem(key_line(block, ON_KEY, line), INVALID_CONSULT_ON))
    if TIMEOUT_KEY in block and not is_minutes(block[TIMEOUT_KEY]):
        errors.append(problem(key_line(block, TIMEOUT_KEY, line), INVALID_TIMEOUT))
    if PROMPTS_KEY in block:
        errors += _check_prompts(block, key_line(block, PROMPTS_KEY, line))
    return errors


def _known_stops(value: Any, known: frozenset[str]) -> bool:
    stops = as_seq(value)
    return bool(stops) and all(stop in known for stop in stops or ())


def _check_prompts(block: LinedMap, line: int) -> list[ValidationError]:
    prompts = as_map(block[PROMPTS_KEY])
    if prompts is None:
        return [problem(line, INVALID_VALUE)]
    errors = unknown_keys(prompts, CONSULT_PROMPTS_KEYS)
    errors += [problem(line, MISSING_KEY) for key in (DISPATCH, ANSWER) if key not in prompts]
    for key, value in prompts.items():
        if key in CONSULT_PROMPTS_KEYS and not isinstance(value, str):
            errors.append(problem(key_line(prompts, key, line), INVALID_VALUE))
    return errors


def parse_consult(node: LinedMap, implied: tuple[str, ...] = ()) -> ConsultDecl | None:
    """The block of a row that has passed `check_consult`, or `None` when it declares none.
    `implied` is the stop list a block that names none stands for."""
    block = as_map(node.get(CONSULT_KEY))
    if block is None:
        return None
    prompts = as_map(block[PROMPTS_KEY]) or LinedMap()
    return ConsultDecl(
        line=key_line(node, CONSULT_KEY, node.line),
        model=block["model"],
        harness=block.get("harness"),
        skill=block["skill"],
        on=tuple(as_seq(block.get(ON_KEY)) or implied),
        timeout_min=block.get(TIMEOUT_KEY),
        prompt_dispatch=prompts[DISPATCH],
        prompt_answer=prompts[ANSWER],
    )


def plan_consult(decl: ConsultDecl | None, scope: Mapping[str, Any]) -> dict[str, Any] | None:
    """The block a row carries, plan-time resolved (AD-7), or `None` for a blank model."""
    if decl is None:
        return None
    model = str(resolve(decl.model, scope) or "").strip()
    if not model:
        return None
    harness = resolve(decl.harness, scope) if decl.harness is not None else ""
    return {
        "model": model,
        "harness": str(harness or "").strip(),
        "skill": str(resolve(decl.skill, scope)),
        ON_KEY: list(decl.on),
        TIMEOUT_KEY: _minutes(decl, scope),
        PROMPTS_KEY: {
            DISPATCH: str(resolve(decl.prompt_dispatch, scope)),
            ANSWER: str(resolve(decl.prompt_answer, scope)),
        },
    }


def _minutes(decl: ConsultDecl, scope: Mapping[str, Any]) -> int | None:
    """The senior's wall-clock limit; one nobody bound is no limit at all."""
    declared = decl.timeout_min
    value = resolve(declared, scope) if isinstance(declared, str) else declared
    if value is None or value == "":
        return None
    text = str(value).strip()
    counted = not isinstance(value, bool) and text.isascii() and text.isdigit()
    if not counted or int(text) < MIN_COUNT:
        raise PlanError(reason=BAD_MINUTES, line=decl.line, item=f"consult: {value!r}")
    return int(text)
