"""The parsed Template tree, and the vocabulary a validation reports in.

Every node carries the `line` it began on, so a caller can point at the file rather than
describe it. The tree is frozen: a `ParsedTemplate` is what the YAML said, and changing it
would mean the Run and the file disagreed.

`ValidationError` is a **value**, not an exception. `validate()` never raises on bad input —
malformed YAML is a record with `reason = "invalid yaml"` like any other problem — and
`domain/errors.py` stays the only exception vocabulary this system has.

The reason strings are fixed here, in one place, because they are the contract: FR-5 names
thirteen, the story brief adds five, and the nine below them cover rules those eighteen
cannot name. A rule that needs a new reason adds it here first. The 28th, `invalid value`,
was added after the fact to stop `missing key` from describing a value that is present but
malformed — inside `expect`, inside `retry`, or an enum's `values` entries — instead of a
key that is genuinely absent.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict

from orchestrator.application.steps import Gate, KindMeta

#: The declared type of a Template input (brief, key table "input").
InputType = Literal["project", "repository", "string", "path", "enum", "number", "item"]

#: What a step does when it fails, in its plain form. The `{redispatch, max}` form is two
#: fields on `Step`, because a two-key mapping is not a third action.
OnFailAction = Literal["escalate", "fail", "continue"]

#: What a Template may write as a scalar: an input default, or one call binding.
Scalar = str | int | float | bool

#: The input types, derived from the alias so the table and the checker cannot disagree.
INPUT_TYPES: frozenset[str] = frozenset(get_args(InputType))

#: The plain `on_fail` actions, derived the same way.
ON_FAIL_ACTIONS: frozenset[str] = frozenset(get_args(OnFailAction))

#: The story statuses an `expect.status_in` list and an `escalate_when` may name (FR-16).
STATUS_TOKENS: frozenset[str] = frozenset(
    {"draft", "ready-for-dev", "in-progress", "in-review", "blocked", "done"}
)

# --- the reason strings (FR-5, plus what the key table needs to say) --------------------

#: FR-5's thirteen.
UNKNOWN_KEY = "unknown key"
UNBOUND_VARIABLE = "unbound variable"
UNKNOWN_KIND = "unknown kind"
USES_AND_RUN = "uses and run on the same step"
NESTED_FOR_EACH = "nested for_each"
SECOND_FOR_EACH = "second for_each"
EXPRESSION_SYNTAX = "expression syntax"
NON_LITERAL_VERSION = "non-literal version"
CALL_CYCLE = "call cycle"
CALL_DEPTH = "call depth over 3"
CALLEE_INPUT_MISMATCH = "callee input mismatch"
PARALLEL_RESERVED = "parallel is reserved"
CALL_TIMING = "timeout_min or on_fail on a template call"

#: The five the brief adds.
UNKNOWN_FIELD = "unknown field"
DUPLICATE_STEP_ID = "duplicate step id"
BAD_REDISPATCH = "redispatch target not an earlier agent step"
INVALID_ON_FAIL = "invalid on_fail"
INVALID_GATE = "invalid gate"

#: The nine the key table states rules for but has no phrase for.
INVALID_YAML = "invalid yaml"
CALLEE_NOT_FOUND = "callee not found"
MISSING_KEY = "missing key"
INVALID_SLUG = "invalid slug"
INVALID_INPUT_TYPE = "invalid input type"
BAD_DEFAULT = "default does not match type"
EMPTY_STEPS = "empty steps"
INVALID_TIMEOUT = "invalid timeout_min"
INVALID_STATUS_TOKEN = "invalid status_in token"

#: The 28th: a value that is present but the wrong shape, where `missing key` would
#: misdescribe a key that is there. Only three contexts get no deeper type check than this
#: (an `expect` scalar, a `retry` scalar, an enum's `values` entries); everywhere else a
#: malformed value already has its own reason.
INVALID_VALUE = "invalid value"

#: A retry block must carry a non-empty `prompt` — absent or empty is not a recoverable
#: default (story 3-5).
RETRY_PROMPT_REQUIRED = "retry prompt required"

# --- the tree ---------------------------------------------------------------------------


class InputDecl(BaseModel):
    """One entry of the template's `inputs:` map."""

    model_config = ConfigDict(frozen=True)

    line: int
    name: str
    type: InputType
    required: bool = False
    default: Scalar | None = None
    values: tuple[str, ...] = ()


class AgentExtras(BaseModel):
    """The step-level siblings of `with` that only a `uses: agent` step may carry.

    Flat rather than nested: `expect` and `retry` are two keys with fixed sub-keys, and a
    model per sub-map would be two more shapes for the same information.
    """

    model_config = ConfigDict(frozen=True)

    line: int
    expect_files: tuple[str, ...] = ()
    expect_status_in: tuple[str, ...] = ()
    retry_max: int | None = None
    retry_prompt: str | None = None
    retry_resume_session: bool = True
    escalate_when: str | None = None
    pause_when: str | None = None
    writes: tuple[str, ...] = ()


class TemplateCall(BaseModel):
    """A `uses: template` step's `with`: which version, bound to what."""

    model_config = ConfigDict(frozen=True)

    line: int
    name: str
    version: int
    inputs: tuple[tuple[str, Scalar], ...] = ()


class Step(BaseModel):
    """One step of a Template, with its kind's metadata resolved (AD-9)."""

    model_config = ConfigDict(frozen=True)

    line: int
    id: str
    uses: str
    meta: KindMeta
    #: The `with` map as pairs, in file order; empty for a `uses: template` step, whose
    #: `with` is the `call` below.
    params: tuple[tuple[str, Any], ...] = ()
    #: What the file declared. `None` means the step is in `unvalidated` (NFR-2); it is
    #: never filled in from `meta.gate_default`.
    gate: Gate | None = None
    timeout_min: int | None = None
    stall_min: int | None = None
    on_fail: OnFailAction | None = None
    redispatch: str | None = None
    redispatch_max: int | None = None
    agent: AgentExtras | None = None
    call: TemplateCall | None = None


class ForEach(BaseModel):
    """The one loop construct a Template may hold. Not a step: it is a path segment."""

    model_config = ConfigDict(frozen=True)

    line: int
    id: str
    source: str
    as_name: str
    steps: tuple[Step, ...] = ()
    pause_before_item_when: str | None = None
    pause_after_item_when: str | None = None


class ParsedTemplate(BaseModel):
    """A Template file that said exactly what it meant."""

    model_config = ConfigDict(frozen=True)

    line: int
    name: str
    version: int
    description: str | None = None
    inputs: tuple[InputDecl, ...] = ()
    steps: tuple[Step | ForEach, ...] = ()


# --- the result --------------------------------------------------------------------------


class ValidationError(BaseModel):
    """One problem, named by line and reason. A value; never raised."""

    model_config = ConfigDict(frozen=True)

    template: str | None = None
    version: int | None = None
    line: int
    reason: str


class ValidationResult(BaseModel):
    """What `validate()` returns: the tree, every problem, and every unchecked step.

    `template` is `None` whenever `errors` is non-empty — there is no half-parsed tree.
    `unvalidated` holds the path of every executable step that declared no `gate`; those
    are not errors (NFR-2), and they are reported whether or not errors exist.
    """

    model_config = ConfigDict(frozen=True)

    template: ParsedTemplate | None = None
    errors: tuple[ValidationError, ...] = ()
    unvalidated: tuple[str, ...] = ()
