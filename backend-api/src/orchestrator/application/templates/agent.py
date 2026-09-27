"""The step-level extras only a `uses: agent` step may carry.

`expect`, `retry`, `escalate_when` and `pause_when` are siblings of `with`, not keys inside
it, and they belong to one kind. Split out of `keys.py` for the module-length limit.

The brief draws the boundary at sub-key membership and `status_in` tokens — no deep type
checking — with one exception that is not a deeper check but the invariant itself: a value
`parse()` hands to `AgentExtras` must already be the type that model declares, or
`validate()` would raise instead of returning a record.
"""

from __future__ import annotations

from orchestrator.application.templates.lines import LinedMap, as_map, as_seq, key_line
from orchestrator.application.templates.model import (
    CONFLICTING_ROUTE,
    INVALID_STATUS_TOKEN,
    INVALID_VALUE,
    MISSING_KEY,
    RETRY_PROMPT_REQUIRED,
    STATUS_TOKENS,
    ValidationError,
)
from orchestrator.application.templates.table import (
    PROMPTS_KEY,
    RETRY_KEYS,
    SUB_MAPS,
    WRITES_KEY,
    problem,
    unknown_keys,
)

#: The `retry` sub-keys `parse()` builds `AgentExtras` from, and the type each must be.
RETRY_SHAPES: tuple[tuple[str, type], ...] = (
    ("max", int),
    ("prompt", str),
    ("resume_session", bool),
)

EXPECT_KEY = "expect"
RETRY_KEY = "retry"
FILES_KEY = "files"
STATUS_IN_KEY = "status_in"

#: The three routing lists (Operator decision, 2026-09-27). Tokens are free-form — a
#: non-BMAD method names its own — so the only checks are text-shaped entries and no token
#: routed two ways at once. `misconfigured_when` is checked for shape alone: its entries
#: are blocking-condition sentences, not status tokens, so the cross-list rule ignores it.
ROUTE_KEYS = ("success", "blocked", "checkpoint")
MISCONFIGURED_WHEN_KEY = "misconfigured_when"


def check_agent_extras(node: LinedMap) -> list[ValidationError]:
    """Sub-key membership and `status_in` tokens; nothing deeper (the brief's boundary)."""
    errors: list[ValidationError] = []
    for key, allowed in SUB_MAPS:
        if key not in node:
            continue
        sub = as_map(node[key])
        if sub is None:
            errors.append(problem(key_line(node, key, node.line), MISSING_KEY))
            continue
        errors += unknown_keys(sub, allowed)
    errors += _check_status_tokens(node)
    errors += _check_expect_files(node)
    errors += _check_route_lists(node)
    errors += _check_writes(node)
    errors += _check_prompt_clauses(node)
    return errors + _check_retry_shapes(node)


def _is_exactly(value: object, kind: type) -> bool:
    """`True` is an `int` in Python, and is never the integer a `max` asks for."""
    if kind is bool:
        return isinstance(value, bool)
    return isinstance(value, kind) and not isinstance(value, bool)


def _check_expect_files(node: LinedMap) -> list[ValidationError]:
    """Membership is the boundary, but a glob that is not text is not a glob."""
    expect = as_map(node.get(EXPECT_KEY))
    if expect is None:
        return []
    globs = as_seq(expect.get(FILES_KEY))
    if globs is None:
        return []
    line = key_line(expect, FILES_KEY, expect.line)
    errors: list[ValidationError] = []
    for glob in globs:
        if not isinstance(glob, str):
            errors.append(problem(line, INVALID_VALUE))
    return errors


def _check_writes(node: LinedMap) -> list[ValidationError]:
    if WRITES_KEY not in node:
        return []
    line = key_line(node, WRITES_KEY, node.line)
    paths = as_seq(node[WRITES_KEY])
    if paths is None:
        return [problem(line, INVALID_VALUE)]
    return [problem(line, INVALID_VALUE) for path in paths if not isinstance(path, str)]


def _check_route_lists(node: LinedMap) -> list[ValidationError]:
    """Entries are non-empty text, and no status token routes two ways at once."""
    expect = as_map(node.get(EXPECT_KEY))
    if expect is None:
        return []
    errors: list[ValidationError] = []
    seen: dict[str, str] = {}
    for key in (*ROUTE_KEYS, MISCONFIGURED_WHEN_KEY):
        tokens = as_seq(expect.get(key))
        if tokens is None:
            continue
        line = key_line(expect, key, expect.line)
        for token in tokens:
            if not isinstance(token, str) or not token:
                errors.append(problem(line, INVALID_VALUE))
            elif key != MISCONFIGURED_WHEN_KEY:
                if token in seen and seen[token] != key:
                    errors.append(problem(line, CONFLICTING_ROUTE))
                seen[token] = key
    return errors


def _check_prompt_clauses(node: LinedMap) -> list[ValidationError]:
    """A clause is handed to the harness verbatim, so a value that is not text is not a
    clause (Operator decision, 2026-09-27). Membership is `SUB_MAPS`'s, above."""
    prompts = as_map(node.get(PROMPTS_KEY))
    if prompts is None:
        return []
    errors: list[ValidationError] = []
    for key, value in prompts.items():
        if not isinstance(value, str):
            errors.append(problem(key_line(prompts, key, prompts.line), INVALID_VALUE))
    return errors


def _check_retry_shapes(node: LinedMap) -> list[ValidationError]:
    retry = as_map(node.get(RETRY_KEY))
    if retry is None:
        return []
    errors: list[ValidationError] = []
    for key, kind in RETRY_SHAPES:
        if key in retry and not _is_exactly(retry[key], kind):
            errors.append(problem(key_line(retry, key, retry.line), INVALID_VALUE))
    # A retry block must carry an explicit, non-empty prompt (story 3-5).
    # A wrong-type prompt is already reported as INVALID_VALUE by the shape loop above.
    # Skip the prompt-required check when the block already has shape errors or unknown keys
    # so that each violation is reported as exactly one error per input.
    has_unknown_keys = any(k not in RETRY_KEYS for k in retry)
    if not errors and not has_unknown_keys:
        prompt_val = retry.get("prompt")
        if prompt_val is None or (isinstance(prompt_val, str) and not prompt_val):
            errors.append(problem(retry.line, RETRY_PROMPT_REQUIRED))
    return errors


def _check_status_tokens(node: LinedMap) -> list[ValidationError]:
    expect = as_map(node.get(EXPECT_KEY))
    if expect is None:
        return []
    tokens = as_seq(expect.get(STATUS_IN_KEY))
    if tokens is None:
        return []
    line = key_line(expect, STATUS_IN_KEY, expect.line)
    errors: list[ValidationError] = []
    for token in tokens:
        if token not in STATUS_TOKENS:
            errors.append(problem(line, INVALID_STATUS_TOKEN))
    return errors
