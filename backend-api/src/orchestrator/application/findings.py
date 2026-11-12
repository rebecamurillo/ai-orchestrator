"""The finding-code registry: one stable code per reason a check can report (AD-15 amended).

A code is `{area}-{slug of the reason}`; a guide page is `errors/{code}`. The registry is
derived from `CODE_BY_REASON` and the explanation table, so the explanation a reader finds
comes from the same release as the check that raised it. Refusal codes are hand-named and their
entries written here. Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from orchestrator.application.finding_explanations import EXPLANATIONS
from orchestrator.application.templates import model as m
from orchestrator.application.templates import plan_model as p

#: What a code must look like.
CODE_PATTERN = r"^(template|spec|refusal)-[a-z0-9]+(-[a-z0-9]+)*$"

Area = Literal["template", "spec", "refusal"]
Source = Literal["check", "agent"]


@dataclass(frozen=True)
class CodeEntry:
    code: str
    area: Area
    message: str
    explanation: str
    source: Source


TEMPLATE_UNKNOWN_KEY = "template-unknown-key"
TEMPLATE_UNBOUND_VARIABLE = "template-unbound-variable"
TEMPLATE_UNKNOWN_KIND = "template-unknown-kind"
TEMPLATE_USES_AND_RUN_ON_THE_SAME_STEP = "template-uses-and-run-on-the-same-step"
TEMPLATE_NESTED_FOR_EACH = "template-nested-for-each"
TEMPLATE_SECOND_FOR_EACH = "template-second-for-each"
TEMPLATE_EXPRESSION_SYNTAX = "template-expression-syntax"
TEMPLATE_NON_LITERAL_VERSION = "template-non-literal-version"
TEMPLATE_CALL_CYCLE = "template-call-cycle"
TEMPLATE_CALL_DEPTH_OVER_3 = "template-call-depth-over-3"
TEMPLATE_CALLEE_INPUT_MISMATCH = "template-callee-input-mismatch"
TEMPLATE_PARALLEL_IS_RESERVED = "template-parallel-is-reserved"
TEMPLATE_TIMEOUT_MIN_OR_ON_FAIL_ON_A_TEMPLATE_CALL = (
    "template-timeout-min-or-on-fail-on-a-template-call"
)
TEMPLATE_UNKNOWN_FIELD = "template-unknown-field"
TEMPLATE_DUPLICATE_STEP_ID = "template-duplicate-step-id"
TEMPLATE_REDISPATCH_TARGET_NOT_AN_EARLIER_AGENT_STEP = (
    "template-redispatch-target-not-an-earlier-agent-step"
)
TEMPLATE_INVALID_ON_FAIL = "template-invalid-on-fail"
TEMPLATE_INVALID_GATE = "template-invalid-gate"
TEMPLATE_INVALID_YAML = "template-invalid-yaml"
TEMPLATE_CALLEE_NOT_FOUND = "template-callee-not-found"
TEMPLATE_MISSING_KEY = "template-missing-key"
TEMPLATE_INVALID_SLUG = "template-invalid-slug"
TEMPLATE_INVALID_INPUT_TYPE = "template-invalid-input-type"
TEMPLATE_DEFAULT_DOES_NOT_MATCH_TYPE = "template-default-does-not-match-type"
TEMPLATE_EMPTY_STEPS = "template-empty-steps"
TEMPLATE_INVALID_TIMEOUT_MIN = "template-invalid-timeout-min"
TEMPLATE_INVALID_STATUS_IN_TOKEN = "template-invalid-status-in-token"
TEMPLATE_INVALID_VALUE = "template-invalid-value"
TEMPLATE_RETRY_PROMPT_REQUIRED = "template-retry-prompt-required"
TEMPLATE_INVALID_DISPATCH_FORM = "template-invalid-dispatch-form"
TEMPLATE_INVALID_GIT_SUBMODULE_FORM = "template-invalid-git-submodule-form"
TEMPLATE_ALL_DIGIT_STEP_ID = "template-all-digit-step-id"
TEMPLATE_STATUS_ROUTED_TWICE = "template-status-routed-twice"
TEMPLATE_DISPATCH_PROMPT_REQUIRED = "template-dispatch-prompt-required"
TEMPLATE_RENDERED_PROMPT_REQUIRED = "template-rendered-prompt-required"
TEMPLATE_HALT_PROMPT_REQUIRED = "template-halt-prompt-required"
TEMPLATE_INVALID_CONSULT_ON = "template-invalid-consult-on"
TEMPLATE_LOOP_NAME_ALREADY_BOUND = "template-loop-name-already-bound"
TEMPLATE_INVALID_TEMPLATE = "template-invalid-template"
SPEC_LIST_FILE_NOT_FOUND = "spec-list-file-not-found"
SPEC_LIST_FILE_IS_NOT_A_LIST = "spec-list-file-is-not-a-list"
SPEC_ENTRY_IS_MISSING_A_REQUIRED_FIELD = "spec-entry-is-missing-a-required-field"
SPEC_DUPLICATE_ENTRY_ID = "spec-duplicate-entry-id"
SPEC_ENTRY_IDS_ARE_NOT_PREFIX_FREE = "spec-entry-ids-are-not-prefix-free"
SPEC_AMBIGUOUS_STORY_FILE = "spec-ambiguous-story-file"
SPEC_ONLY_ID_NOT_IN_LIST = "spec-only-id-not-in-list"
TEMPLATE_CALLEE_NOT_RESOLVED = "template-callee-not-resolved"
TEMPLATE_TIMEOUT_MIN_OR_STALL_MIN_IS_NOT_A_POSITIVE_INTEGER = (
    "template-timeout-min-or-stall-min-is-not-a-positive-integer"
)
TEMPLATE_BASE_BRANCH_NOT_FOUND = "template-base-branch-not-found"
TEMPLATE_NO_FREE_BRANCH_NAME = "template-no-free-branch-name"
TEMPLATE_REDISPATCH_TARGET_IS_NOT_A_ROW_OF_THIS_FRAME = (
    "template-redispatch-target-is-not-a-row-of-this-frame"
)
TEMPLATE_DUPLICATE_ROW_PATH = "template-duplicate-row-path"
REFUSAL_GUIDE_UNAVAILABLE = "refusal-guide-unavailable"
REFUSAL_LOCAL_ONLY = "refusal-local-only"
REFUSAL_BOOTSTRAP_CONTRACT = "refusal-bootstrap-contract"
REFUSAL_TEMPLATE_IN_FOLDER = "refusal-template-in-folder"
REFUSAL_SPEC_MD_MISSING = "refusal-spec-md-missing"
REFUSAL_MODELS_UNLISTED = "refusal-models-unlisted"
REFUSAL_MODELS_GATEWAY_UNREACHABLE = "refusal-models-gateway-unreachable"

#: Reason text -> code, written out so a reworded reason is a visible change here.
CODE_BY_REASON: Mapping[str, str] = {
    m.UNKNOWN_KEY: TEMPLATE_UNKNOWN_KEY,
    m.UNBOUND_VARIABLE: TEMPLATE_UNBOUND_VARIABLE,
    m.UNKNOWN_KIND: TEMPLATE_UNKNOWN_KIND,
    m.USES_AND_RUN: TEMPLATE_USES_AND_RUN_ON_THE_SAME_STEP,
    m.NESTED_FOR_EACH: TEMPLATE_NESTED_FOR_EACH,
    m.SECOND_FOR_EACH: TEMPLATE_SECOND_FOR_EACH,
    m.EXPRESSION_SYNTAX: TEMPLATE_EXPRESSION_SYNTAX,
    m.NON_LITERAL_VERSION: TEMPLATE_NON_LITERAL_VERSION,
    m.CALL_CYCLE: TEMPLATE_CALL_CYCLE,
    m.CALL_DEPTH: TEMPLATE_CALL_DEPTH_OVER_3,
    m.CALLEE_INPUT_MISMATCH: TEMPLATE_CALLEE_INPUT_MISMATCH,
    m.PARALLEL_RESERVED: TEMPLATE_PARALLEL_IS_RESERVED,
    m.CALL_TIMING: TEMPLATE_TIMEOUT_MIN_OR_ON_FAIL_ON_A_TEMPLATE_CALL,
    m.UNKNOWN_FIELD: TEMPLATE_UNKNOWN_FIELD,
    m.DUPLICATE_STEP_ID: TEMPLATE_DUPLICATE_STEP_ID,
    m.BAD_REDISPATCH: TEMPLATE_REDISPATCH_TARGET_NOT_AN_EARLIER_AGENT_STEP,
    m.INVALID_ON_FAIL: TEMPLATE_INVALID_ON_FAIL,
    m.INVALID_GATE: TEMPLATE_INVALID_GATE,
    m.INVALID_YAML: TEMPLATE_INVALID_YAML,
    m.CALLEE_NOT_FOUND: TEMPLATE_CALLEE_NOT_FOUND,
    m.MISSING_KEY: TEMPLATE_MISSING_KEY,
    m.INVALID_SLUG: TEMPLATE_INVALID_SLUG,
    m.INVALID_INPUT_TYPE: TEMPLATE_INVALID_INPUT_TYPE,
    m.BAD_DEFAULT: TEMPLATE_DEFAULT_DOES_NOT_MATCH_TYPE,
    m.EMPTY_STEPS: TEMPLATE_EMPTY_STEPS,
    m.INVALID_TIMEOUT: TEMPLATE_INVALID_TIMEOUT_MIN,
    m.INVALID_STATUS_TOKEN: TEMPLATE_INVALID_STATUS_IN_TOKEN,
    m.INVALID_VALUE: TEMPLATE_INVALID_VALUE,
    m.RETRY_PROMPT_REQUIRED: TEMPLATE_RETRY_PROMPT_REQUIRED,
    m.INVALID_DISPATCH_FORM: TEMPLATE_INVALID_DISPATCH_FORM,
    m.INVALID_SUBMODULE_FORM: TEMPLATE_INVALID_GIT_SUBMODULE_FORM,
    m.ALL_DIGIT_STEP_ID: TEMPLATE_ALL_DIGIT_STEP_ID,
    m.CONFLICTING_ROUTE: TEMPLATE_STATUS_ROUTED_TWICE,
    m.DISPATCH_PROMPT_REQUIRED: TEMPLATE_DISPATCH_PROMPT_REQUIRED,
    m.RENDERED_PROMPT_REQUIRED: TEMPLATE_RENDERED_PROMPT_REQUIRED,
    m.HALT_PROMPT_REQUIRED: TEMPLATE_HALT_PROMPT_REQUIRED,
    m.INVALID_CONSULT_ON: TEMPLATE_INVALID_CONSULT_ON,
    m.LOOP_NAME_BOUND: TEMPLATE_LOOP_NAME_ALREADY_BOUND,
    m.INVALID_TEMPLATE: TEMPLATE_INVALID_TEMPLATE,
    p.LIST_FILE_NOT_FOUND: SPEC_LIST_FILE_NOT_FOUND,
    p.LIST_FILE_NOT_A_LIST: SPEC_LIST_FILE_IS_NOT_A_LIST,
    p.ENTRY_MISSING_FIELDS: SPEC_ENTRY_IS_MISSING_A_REQUIRED_FIELD,
    p.DUPLICATE_ENTRY_ID: SPEC_DUPLICATE_ENTRY_ID,
    p.ID_NOT_PREFIX_FREE: SPEC_ENTRY_IDS_ARE_NOT_PREFIX_FREE,
    p.AMBIGUOUS_STORY_FILE: SPEC_AMBIGUOUS_STORY_FILE,
    p.ONLY_NOT_IN_LIST: SPEC_ONLY_ID_NOT_IN_LIST,
    p.CALLEE_NOT_RESOLVED: TEMPLATE_CALLEE_NOT_RESOLVED,
    p.BAD_MINUTES: TEMPLATE_TIMEOUT_MIN_OR_STALL_MIN_IS_NOT_A_POSITIVE_INTEGER,
    p.BASE_BRANCH_NOT_FOUND: TEMPLATE_BASE_BRANCH_NOT_FOUND,
    p.NO_FREE_BRANCH: TEMPLATE_NO_FREE_BRANCH_NAME,
    p.REDISPATCH_TARGET_NOT_PLANNED: TEMPLATE_REDISPATCH_TARGET_IS_NOT_A_ROW_OF_THIS_FRAME,
    p.DUPLICATE_ROW_PATH: TEMPLATE_DUPLICATE_ROW_PATH,
}

_AREA_OF: Mapping[str, Area] = {
    code: "spec" if code.startswith("spec-") else "template" for code in CODE_BY_REASON.values()
}


def _entry(reason: str, code: str) -> CodeEntry:
    return CodeEntry(code, _AREA_OF[code], reason, EXPLANATIONS[reason], "check")


#: Hand-named refusal codes, not reasons, so not in `CODE_BY_REASON`: those an open route answers
#: with (`check`) and those an agent reports (`agent`).
REFUSALS: Mapping[str, CodeEntry] = {
    REFUSAL_GUIDE_UNAVAILABLE: CodeEntry(
        REFUSAL_GUIDE_UNAVAILABLE,
        "refusal",
        "guide page or schema not available",
        "The page id is not listed in `/llms.txt`, or this instance was started from a source "
        "tree where `make guide` has not run, so there is no built guide to serve.",
        "check",
    ),
    REFUSAL_LOCAL_ONLY: CodeEntry(
        REFUSAL_LOCAL_ONLY,
        "refusal",
        "this is done on the host only",
        "No instance tool or route upgrades, restarts or reconfigures the instance; the host "
        "agent or the user does it from the deploy folder, following the `host/*` pages.",
        "agent",
    ),
    REFUSAL_BOOTSTRAP_CONTRACT: CodeEntry(
        REFUSAL_BOOTSTRAP_CONTRACT,
        "refusal",
        "this instance serves a newer bootstrap contract",
        "The installed bootstrap keeps working; re-run the bootstrap installer to move to the "
        "newer contract when convenient.",
        "agent",
    ),
    REFUSAL_TEMPLATE_IN_FOLDER: CodeEntry(
        REFUSAL_TEMPLATE_IN_FOLDER,
        "refusal",
        "template held in the operator folder",
        "The operator's template folder governs this name: a version saved here would be "
        "superseded by the file at the next reload or start-up. The file is edited on the host, "
        "then `reload_templates` (`POST /templates/reload`) stores it as the next version.",
        "check",
    ),
    REFUSAL_SPEC_MD_MISSING: CodeEntry(
        REFUSAL_SPEC_MD_MISSING,
        "refusal",
        "SPEC.md missing from a spec folder",
        "Every spec folder a Run reads holds a `SPEC.md`, and pre-flight answers `fail · missing` "
        "for a folder without one.",
        "check",
    ),
    REFUSAL_MODELS_UNLISTED: CodeEntry(
        REFUSAL_MODELS_UNLISTED,
        "refusal",
        "this harness cannot list its models here",
        "No LiteLLM gateway is configured on this instance, so there is no list to read for "
        "this harness: pass a model name the harness accepts, and ask the user for it rather "
        "than guessing one.",
        "check",
    ),
    REFUSAL_MODELS_GATEWAY_UNREACHABLE: CodeEntry(
        REFUSAL_MODELS_GATEWAY_UNREACHABLE,
        "refusal",
        "the LiteLLM gateway could not be read",
        "A gateway is configured but `GET /v1/models` failed or answered a body that is not a "
        "model list, so the list is unknown; nothing is guessed in its place. Try again, or "
        "check the gateway from the host.",
        "check",
    ),
}

REGISTRY: Mapping[str, CodeEntry] = {
    **{code: _entry(reason, code) for reason, code in CODE_BY_REASON.items()},
    **REFUSALS,
}


def entry(code: str) -> CodeEntry:
    """The registry entry of `code`; `KeyError` when no such code exists."""
    return REGISTRY[code]


def guide_id(code: str) -> str:
    """The guide page that explains `code`."""
    return f"errors/{entry(code).code}"


def code_for(reason: str) -> str | None:
    """The code of a reason text, or `None` for a reason that has none."""
    return CODE_BY_REASON.get(reason)
