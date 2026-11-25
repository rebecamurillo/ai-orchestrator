"""A `spec-gate` row's verdict, read from the step file its row routed on (AD-37)."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from orchestrator.application.story_file import STATUS_KEY, body, frontmatter, parse
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.values import GateVerdict, StepResult

SPEC_GATE_ROLE = "spec-gate"
VERDICT_TEXT_MAX = 65_536
#: Budget for the stored mapping: one unit per node plus one per character. The loader shares
#: aliased nodes, so a few hundred bytes of nested aliases expand without bound here.
VERDICT_FIELDS_MAX = 65_536
NUL = "\x00"


class _TooLarge(Exception):
    pass


def _clean(text: str, budget: list[int]) -> str:
    """`text` without NUL, which neither Postgres `text` nor JSONB accepts."""
    budget[0] -= len(text)
    if budget[0] < 0:
        raise _TooLarge
    return text.replace(NUL, "")


def _plain(value: Any, budget: list[int]) -> Any:
    """JSON-safe copy: YAML dates, line-tracking maps and NaN must not reach JSONB."""
    budget[0] -= 1
    if budget[0] < 0:
        raise _TooLarge
    if isinstance(value, dict):
        return {_clean(str(key), budget): _plain(item, budget) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item, budget) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, int | float | bool):
        return value
    return _clean(str(value), budget)


def _fields(root: Any, word: str) -> dict[str, Any]:
    """The frontmatter mapping, or only its word when the mapping exceeds the budget."""
    try:
        plain: dict[str, Any] = _plain(root, [VERDICT_FIELDS_MAX])
    except _TooLarge:
        return {STATUS_KEY: word}
    return plain


def verdict_of(row: StepRun, story_path: str, story_text: str) -> GateVerdict | None:
    """The verdict when `row` is a `spec-gate` row and its file parses, else `None`."""
    if row.role != SPEC_GATE_ROLE:
        return None
    parsed = parse(story_path, story_text)
    head = frontmatter(story_text)
    if parsed is None or head is None:
        return None
    fields = _fields(load_with_lines(head).root, parsed.status)
    text = (body(story_text) or "")[:VERDICT_TEXT_MAX].replace(NUL, "")
    return GateVerdict(word=parsed.status, fields=fields, text=text)


def routed_with_verdict(
    routed: StepResult, row: StepRun, path: str | None, read: Callable[[str], str | None]
) -> StepResult:
    """`routed` with its verdict when it is `done`; otherwise `routed` itself."""
    if routed.status != "done" or path is None or row.role != SPEC_GATE_ROLE:
        return routed
    text = read(path)
    verdict = None if text is None else verdict_of(row, path, text)
    return routed if verdict is None else routed.model_copy(update={"verdict": verdict})
