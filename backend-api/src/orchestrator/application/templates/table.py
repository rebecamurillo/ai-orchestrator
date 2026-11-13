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
    BIND_KEY,
    FOR_EACH_KEY,
    STEPS_KEY,
    LinedMap,
    key_line,
)
from orchestrator.application.templates.model import UNKNOWN_KEY, ValidationError

#: A Template `name`, a step `id` and a `for_each` `as` name are all slugs.
SLUG = re.compile(r"^[a-z][a-z0-9-]*$")

NAME_KEY = "name"
VERSION_KEY = "version"
INPUTS_KEY = "inputs"
ID_KEY = "id"
USES_KEY = "uses"
GATE_KEY = "gate"
INPUT_TYPE_KEY = "type"
DESCRIPTION_KEY = "description"

TEMPLATE_KEYS = frozenset({NAME_KEY, VERSION_KEY, DESCRIPTION_KEY, INPUTS_KEY, STEPS_KEY})
INPUT_KEYS = frozenset({INPUT_TYPE_KEY, "required", "default", "values", DESCRIPTION_KEY})
STEP_KEYS = frozenset(
    {ID_KEY, USES_KEY, "run", "with", GATE_KEY, "timeout_min", "stall_min", "on_fail"}
)

#: What `validate()` refuses a level for lacking, by level.
REQUIRED_TEMPLATE_KEYS = (NAME_KEY, VERSION_KEY)
REQUIRED_STEP_KEYS = (ID_KEY,)
REQUIRED_INPUT_KEYS = (INPUT_TYPE_KEY,)
REQUIRED_FOR_EACH_KEYS = (ID_KEY, FOR_EACH_KEY, AS_KEY, STEPS_KEY)

WRITES_KEY = "writes"

#: The `prompts` block: the prose a dispatch is composed from, one clause per moment
#: (Operator decision, 2026-09-27 — prompt prose lives in the Template). `redispatch` is
#: the fifth: what a fresh dispatch is told when a `verify` row has just sent it back
#: (FR-10, story "a redispatch prompt clause").
PROMPTS_KEY = "prompts"
PROMPTS_KEYS = frozenset({"dispatch", "rendered", "answer", "halt", "redispatch"})

#: AD-22's `consult {model, harness?, skill, on, timeout_min?, prompts {dispatch, answer}}`.
#: `on` names the stops a senior may take instead of a person.
CONSULT_KEY = "consult"
CONSULT_KEYS = frozenset({"model", "harness", "skill", "on", "timeout_min", PROMPTS_KEY})
CONSULT_REQUIRED = ("model", "skill", "on", PROMPTS_KEY)
CONSULT_PROMPTS_KEYS = frozenset({"dispatch", "answer"})
CONSULT_ON = frozenset({"blocked", "protected_path"})
#: The same block under a `run` row's `on_fail {redispatch, max, consult}` (story 1-6): the
#: stop is implied, so `on` is optional and may only name it.
REDISPATCH_CONSULT_ON = frozenset({"verify_failed"})
REDISPATCH_CONSULT_REQUIRED = ("model", "skill", PROMPTS_KEY)

#: The three dispatch forms an `agent` `with` block may carry — only one at a time.
AGENT_DISPATCH_KEYS: frozenset[str] = frozenset({"skill", "prompt", "prompt_file"})
#: The intent key for the intent dispatch form (IMP-002 accepted 2026-09-15).
#: NOT added to AGENT_DISPATCH_KEYS to avoid triggering INVALID_DISPATCH_FORM for skill+intent.
AGENT_INTENT_KEYS: frozenset[str] = frozenset({"intent"})

AGENT_KEYS = frozenset(
    {"expect", "retry", "escalate_when", "pause_when", WRITES_KEY, PROMPTS_KEY, CONSULT_KEY}
)
FOR_EACH_KEYS = frozenset(
    {
        ID_KEY,
        FOR_EACH_KEY,
        AS_KEY,
        STEPS_KEY,
        "pause_before_item_when",
        "pause_after_item_when",
        "parallel",
        "only",
        BIND_KEY,
    }
)
EXPECT_KEYS = frozenset(
    {"files", "status_in", "success", "blocked", "checkpoint", "misconfigured_when"}
)
RETRY_KEYS = frozenset({"max", "prompt", "resume_session"})
REDISPATCH_KEYS = frozenset({"redispatch", "max"})
REDISPATCH_OPTIONAL = frozenset({CONSULT_KEY})

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

#: The largest count a stored row's `int4` column holds (`version`, `timeout_min`, ...).
MAX_COUNT = 2**31 - 1

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
    """A positive integer literal that fits a stored `int4`. `True` is not one here."""
    return (
        isinstance(value, int) and not isinstance(value, bool) and MIN_COUNT <= value <= MAX_COUNT
    )


def is_minutes(value: object) -> bool:
    """A `timeout_min` or `stall_min`: a positive integer literal, or text holding a `{{ }}`.

    What the expression resolves to is only known when a Run is planned.
    """
    return is_count(value) or (isinstance(value, str) and "{{" in value)


def unknown_keys(mapping: LinedMap, allowed: frozenset[str]) -> list[ValidationError]:
    """One `unknown key` per key the level does not accept, at that key's own line."""
    errors = []
    for key in mapping:
        if key not in allowed:
            errors.append(problem(key_line(mapping, key, mapping.line), UNKNOWN_KEY))
    return errors
