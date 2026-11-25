"""The two optional keys of a `git.push` step: `with.allow_default_branch` and `retry`.

Split out of `keys.py` for the module-length limit. `allow_default_branch` pushes the default
branch, so it exists only in an `interactive` template (AD-14 amendment, AD-37); `retry` is
`{max, sync_first: true}` with `max` 1 to 3, declared so that a rejected push syncs and pushes
again rather than retrying silently (hard rule 7).
"""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.application.steps import (
    PUSH_ALLOW_DEFAULT_KEY,
    PUSH_KIND,
    PUSH_RETRY_KEY,
    PUSH_RETRY_KEYS,
)
from orchestrator.application.templates.lines import LinedMap, as_map, key_line
from orchestrator.application.templates.model import (
    INVALID_VALUE,
    MISSING_KEY,
    UNKNOWN_KEY,
    ValidationError,
)
from orchestrator.application.templates.table import (
    DEFAULT_TEMPLATE_TYPE,
    TEMPLATE_TYPE_KEY,
    USES_KEY,
    WITH_KEY,
    problem,
)

PUSH_DEFAULT_NEEDS_INTERACTIVE = "git.push allow_default_branch needs type: interactive"
INTERACTIVE = "interactive"
MAX_KEY = "max"
SYNC_KEY = "sync_first"
RETRY_MAX = 3

Walked = Sequence[tuple[LinedMap, tuple[LinedMap, ...]]]


def check_push_keys(root: LinedMap, walked: Walked) -> list[ValidationError]:
    """The offences of every `git.push` step's two optional keys."""
    interactive = root.get(TEMPLATE_TYPE_KEY, DEFAULT_TEMPLATE_TYPE) == INTERACTIVE
    errors: list[ValidationError] = []
    for node, _enclosing in walked:
        if node.get(USES_KEY) != PUSH_KIND:
            continue
        errors += _check_default(node, interactive=interactive)
        errors += _check_retry(node)
    return errors


def _check_default(node: LinedMap, *, interactive: bool) -> list[ValidationError]:
    params = as_map(node.get(WITH_KEY))
    if interactive or params is None or not params.get(PUSH_ALLOW_DEFAULT_KEY):
        return []
    return [
        problem(
            key_line(params, PUSH_ALLOW_DEFAULT_KEY, params.line), PUSH_DEFAULT_NEEDS_INTERACTIVE
        )
    ]


def _check_retry(node: LinedMap) -> list[ValidationError]:
    if PUSH_RETRY_KEY not in node:
        return []
    line = key_line(node, PUSH_RETRY_KEY, node.line)
    retry = as_map(node[PUSH_RETRY_KEY])
    if retry is None:
        return [problem(line, MISSING_KEY)]
    errors = [
        problem(key_line(retry, str(key), retry.line), UNKNOWN_KEY)
        for key in retry
        if key not in PUSH_RETRY_KEYS
    ]
    errors += [problem(line, MISSING_KEY) for key in sorted(PUSH_RETRY_KEYS) if key not in retry]
    if MAX_KEY in retry and not _is_max(retry[MAX_KEY]):
        errors.append(problem(key_line(retry, MAX_KEY, line), INVALID_VALUE))
    if SYNC_KEY in retry and retry[SYNC_KEY] is not True:
        errors.append(problem(key_line(retry, SYNC_KEY, line), INVALID_VALUE))
    return errors


def _is_max(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= RETRY_MAX
