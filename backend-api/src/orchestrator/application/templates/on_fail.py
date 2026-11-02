"""A step's `on_fail` (AD-9): a plain action, or a redispatch to an earlier `agent` step.

The redispatch may carry a `consult` (AD-22, story 1-6): the block a senior is dispatched
with once the redispatch bound is used up, on a `shell` row only. Its shape is the agent
row's, with the one stop implied: `on` is optional and may only name `verify_failed`.
"""

from __future__ import annotations

from orchestrator.application.templates.consult import check_consult, parse_consult
from orchestrator.application.templates.lines import LinedMap, as_map, key_line
from orchestrator.application.templates.model import (
    BAD_REDISPATCH,
    INVALID_ON_FAIL,
    ON_FAIL_ACTIONS,
    ConsultDecl,
    ValidationError,
)
from orchestrator.application.templates.table import (
    CONSULT_KEY,
    REDISPATCH_CONSULT_ON,
    REDISPATCH_CONSULT_REQUIRED,
    REDISPATCH_KEYS,
    REDISPATCH_OPTIONAL,
    is_count,
    problem,
)

ON_FAIL_KEY = "on_fail"

#: The one kind whose failure can carry a consult: the deterministic `verify`.
RUN_KIND = "shell"

#: The stops a redispatch consult may name, as the planned block lists them.
VERIFY_FAILED_STOPS = tuple(sorted(REDISPATCH_CONSULT_ON))


def check_on_fail(node: LinedMap, earlier_agents: set[str], kind: str) -> list[ValidationError]:
    """`escalate | fail | continue`, or a redispatch to an `agent` step written earlier."""
    if ON_FAIL_KEY not in node:
        return []
    line = key_line(node, ON_FAIL_KEY, node.line)
    value = node[ON_FAIL_KEY]
    if isinstance(value, str):
        return [] if value in ON_FAIL_ACTIONS else [problem(line, INVALID_ON_FAIL)]
    redispatch = as_map(value)
    if redispatch is None or not _keys_fit(redispatch, kind):
        return [problem(line, INVALID_ON_FAIL)]
    if not is_count(redispatch["max"]):
        return [problem(line, INVALID_ON_FAIL)]
    if redispatch["redispatch"] not in earlier_agents:
        return [problem(line, BAD_REDISPATCH)]
    return check_consult(redispatch, REDISPATCH_CONSULT_ON, REDISPATCH_CONSULT_REQUIRED)


def _keys_fit(redispatch: LinedMap, kind: str) -> bool:
    """Both required keys, nothing but the optional `consult` beside them, and that only on a
    `shell` row."""
    keys = set(redispatch)
    if not REDISPATCH_KEYS <= keys or keys - REDISPATCH_KEYS - REDISPATCH_OPTIONAL:
        return False
    return CONSULT_KEY not in keys or kind == RUN_KIND


def parse_redispatch_consult(node: LinedMap) -> ConsultDecl | None:
    """The consult of a step that has passed `check_on_fail`, or `None` when it has none."""
    redispatch = as_map(node.get(ON_FAIL_KEY))
    if redispatch is None:
        return None
    return parse_consult(redispatch, VERIFY_FAILED_STOPS)
