"""The vocabulary the key table is written in: the accepted key sets, and four readers.

Split out of `keys.py` so that neither it nor `inputs.py` exceeds the 400-line module limit
`backend-api/AGENTS.md` puts on a module. Nothing here decides anything; it is the table's
nouns, in one place, so the two checkers that read them cannot disagree about what a key is
called or what counts as a slug.
"""

from __future__ import annotations

import re

from orchestrator.application.templates.lines import (
    AS_KEY,
    FOR_EACH_KEY,
    STEPS_KEY,
    LinedMap,
    key_line,
)
from orchestrator.application.templates.model import UNKNOWN_KEY, ValidationError

#: A Template `name`, a step `id` and a `for_each` `as` name are all slugs.
SLUG = re.compile(r"^[a-z][a-z0-9-]*$")

TEMPLATE_KEYS = frozenset({"name", "version", "description", "inputs", STEPS_KEY})
INPUT_KEYS = frozenset({"type", "required", "default", "values"})
STEP_KEYS = frozenset({"id", "uses", "run", "with", "gate", "timeout_min", "stall_min", "on_fail"})
WRITES_KEY = "writes"

#: The `prompts` block: the prose a dispatch is composed from, one clause per moment
#: (Operator decision, 2026-09-27 — prompt prose lives in the Template). `redispatch` is
#: the fifth: what a fresh dispatch is told when a `verify` row has just sent it back
#: (FR-10, story "a redispatch prompt clause").
PROMPTS_KEY = "prompts"
PROMPTS_KEYS = frozenset({"dispatch", "rendered", "answer", "halt", "redispatch"})

AGENT_KEYS = frozenset({"expect", "retry", "escalate_when", "pause_when", WRITES_KEY, PROMPTS_KEY})
FOR_EACH_KEYS = frozenset(
    {
        "id",
        FOR_EACH_KEY,
        AS_KEY,
        STEPS_KEY,
        "pause_before_item_when",
        "pause_after_item_when",
        "parallel",
        "only",
    }
)
EXPECT_KEYS = frozenset(
    {"files", "status_in", "success", "blocked", "checkpoint", "misconfigured_when"}
)
RETRY_KEYS = frozenset({"max", "prompt", "resume_session"})
REDISPATCH_KEYS = frozenset({"redispatch", "max"})

#: The input types a text default fits. `number` and `enum` have rules of their own;
#: `project`, `repository` and `item` are bound at run time and fit no default at all.
TEXT_TYPES = frozenset({"string", "path"})

#: The step keys a `uses: template` step may not carry: a call is not timed and does
#: not fail on its own — the callee's steps do.
CALL_TIMING_KEYS = ("timeout_min", "stall_min", "on_fail")

#: Deep type checking inside `expect` and `retry` is out of scope; membership is not.
#: `prompts` joins them for membership; its clause values are checked to be text, because
#: a clause is handed to the harness verbatim and a list is not a sentence.
SUB_MAPS = (("expect", EXPECT_KEYS), ("retry", RETRY_KEYS), (PROMPTS_KEY, PROMPTS_KEYS))

#: The lowest `on_fail.max`, `timeout_min` and `version` a Template may write.
MIN_COUNT = 1

#: The two spellings of what a step does, and the map its kind is parameterised by.
RUN_KEY = "run"
WITH_KEY = "with"

#: The kind a bare `run: <command>` desugars to.
RUN_SUGAR_KIND = "shell"


def problem(line: int, reason: str) -> ValidationError:
    """One record. A value the caller collects, never something raised."""
    return ValidationError(line=line, reason=reason)


def is_slug(value: object) -> bool:
    return isinstance(value, str) and SLUG.match(value) is not None


def is_count(value: object) -> bool:
    """A positive integer literal. `True` is an `int` in Python and is not one here."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= MIN_COUNT


def unknown_keys(mapping: LinedMap, allowed: frozenset[str]) -> list[ValidationError]:
    """One `unknown key` per key the level does not accept, at that key's own line."""
    errors = []
    for key in mapping:
        if key not in allowed:
            errors.append(problem(key_line(mapping, key, mapping.line), UNKNOWN_KEY))
    return errors
