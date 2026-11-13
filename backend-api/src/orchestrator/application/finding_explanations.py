"""One explanation paragraph per reason a check can report, for the generated guide pages.

Keyed by the reason constants, never by their text, so a reworded reason cannot orphan its
paragraph. The reasons in the kit's workflows reference § Validation reasons state its
"Usual cause"; every other paragraph restates the rule the constant's comment and the code
that emits it hold.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.application.templates import model as m
from orchestrator.application.templates import plan_model as p

EXPLANATIONS: Mapping[str, str] = {
    m.UNKNOWN_KEY: (
        "A key the level does not accept, or a `with` key the step kind does not take. "
        "Remove it, or move it to the level that declares it."
    ),
    m.UNBOUND_VARIABLE: (
        "`{{x}}` names something that is not a declared input or a loop name in scope. "
        "Declare the input, or use the name the enclosing loop binds."
    ),
    m.UNKNOWN_KIND: (
        "A step's `uses` names a kind the orchestrator does not ship. "
        "Use one of the step kinds the kind table lists."
    ),
    m.USES_AND_RUN: (
        "A step carries both `uses` and `run`. A step is one or the other: a kind the "
        "orchestrator executes, or a command it runs."
    ),
    m.NESTED_FOR_EACH: (
        "A loop three deep. A loop may hold one loop, and no more; flatten the inner "
        "loops or move one into a called template."
    ),
    m.SECOND_FOR_EACH: (
        "A second loop in one `steps` list. A `steps` list holds at most one `for_each`; "
        "put the second in its own template and call it."
    ),
    m.EXPRESSION_SYNTAX: (
        "Anything inside `{{ }}` beyond `name` or `name.field`. Expressions have no "
        "operators, filters or calls."
    ),
    m.NON_LITERAL_VERSION: (
        "A template call's `version` is an expression. A version is a literal number, so "
        "the pinned tree is known before the Run starts."
    ),
    m.CALL_CYCLE: (
        "A template calls itself, directly or through the templates it calls. A call "
        "chain must end."
    ),
    m.CALL_DEPTH: (
        "Template calls nest more than three deep. Flatten the chain, or inline a callee."
    ),
    m.CALLEE_INPUT_MISMATCH: (
        "A call's `inputs` do not match the callee's declared inputs by name and type. "
        "Pass exactly the inputs the callee declares, with values of the declared types."
    ),
    m.PARALLEL_RESERVED: (
        "`parallel` is a reserved key and has no meaning yet. Write the steps in sequence."
    ),
    m.CALL_TIMING: (
        "A template call carries `timeout_min` or `on_fail`. Those belong to the callee's "
        "own steps; a call has neither a timeout nor a failure route of its own."
    ),
    m.UNKNOWN_FIELD: (
        "A `{{x.field}}` names a field the entity does not have. Use a field from the "
        "entity's list."
    ),
    m.DUPLICATE_STEP_ID: (
        "Two steps share an `id`. Step ids identify a row in the plan, so each must be unique."
    ),
    m.BAD_REDISPATCH: (
        "`on_fail.redispatch` must name an `agent` step written above the step that "
        "routes to it. The target is missing, is not an agent step, or is written below."
    ),
    m.INVALID_ON_FAIL: (
        "`on_fail` is neither one of `escalate`, `fail`, `continue`, nor a "
        "`{redispatch, max}` mapping."
    ),
    m.INVALID_GATE: "`gate` is not one of the gate values the step kinds define.",
    m.INVALID_YAML: (
        "The text is not parseable YAML, or its top level is not a mapping. The line "
        "points at where the parser stopped."
    ),
    m.CALLEE_NOT_FOUND: (
        "A template call names a template with no stored version of that name. Save the "
        "callee first, or correct the name."
    ),
    m.MISSING_KEY: "A key the level requires is absent. Add it.",
    m.INVALID_SLUG: (
        "A name or an `id` is not a slug: lower-case letters, digits and single hyphens. Rename it."
    ),
    m.INVALID_INPUT_TYPE: (
        "An input's `type` is not one of `project`, `repository`, `string`, `path`, "
        "`enum`, `number`, `item`."
    ),
    m.BAD_DEFAULT: "An input's `default` is not a value of the input's declared `type`.",
    m.EMPTY_STEPS: "A `steps` list holds no step. A workflow needs at least one.",
    m.INVALID_TIMEOUT: "`timeout_min` is not a positive integer.",
    m.INVALID_STATUS_TOKEN: (
        "A status named in `expect.status_in` or `escalate_when` is not one of the story "
        "statuses: `draft`, `ready-for-dev`, `in-progress`, `in-review`, `blocked`, `done`."
    ),
    m.INVALID_VALUE: (
        "A key is present but its value has the wrong shape: a scalar inside `expect` or "
        "`retry`, or an entry of an enum's `values`. The key is not missing; its value is "
        "malformed."
    ),
    m.RETRY_PROMPT_REQUIRED: (
        "The `retry` clause that form needs is missing its `prompt`, or the prompt is "
        "empty. A retry is bounded and carries the words it sends."
    ),
    m.INVALID_DISPATCH_FORM: (
        "An agent step's `with` carries more than one of `skill`, `prompt`, "
        "`prompt_file`. Keep the one that says what to send."
    ),
    m.INVALID_SUBMODULE_FORM: (
        "A `git.submodule` step's `with` is neither of the kind's two forms: keys of both "
        "forms together, or `workdir` without `branch`. Write one form."
    ),
    m.ALL_DIGIT_STEP_ID: (
        "A step `id` made only of digits. Plan indices are dot-joined numbers, so an "
        "all-digit id could collide with one. Add a letter."
    ),
    m.CONFLICTING_ROUTE: (
        "A status token appears in more than one of `expect.success`, `expect.blocked`, "
        "`expect.checkpoint`. A status routes one way."
    ),
    m.DISPATCH_PROMPT_REQUIRED: (
        "A skill dispatch with no `prompts.dispatch`. The orchestrator sends no words a "
        "template did not write, so the clause that form needs is missing."
    ),
    m.RENDERED_PROMPT_REQUIRED: (
        "A skill dispatch with no `prompts.rendered`. Without it the agent is never "
        "pointed at the rendered workflow, so the `prompts` clause that form needs is "
        "missing."
    ),
    m.HALT_PROMPT_REQUIRED: (
        "A `pause_when` with no `prompts.halt`. The agent is never asked to stop for the "
        "checkpoint, so the `prompts` clause that form needs is missing."
    ),
    m.INVALID_CONSULT_ON: (
        "`consult.on` is not a non-empty list of the stops a consult may take. It never "
        "names `budget`, `checkpoint`, `misconfigured`, `plan_stale` or `dependency`."
    ),
    m.LOOP_NAME_BOUND: (
        "A loop's `as` or `bind` name is already held by an enclosing loop, the loop's "
        "own `as`, an input, or an earlier key of the same `bind`. Pick another name."
    ),
    m.INVALID_TEMPLATE: (
        "The text could not be checked at all: validating it raised something other than "
        "a finding. The check refuses the file instead of failing."
    ),
    p.LIST_FILE_NOT_FOUND: ("The `for_each` names a file that no candidate ref holds."),
    p.LIST_FILE_NOT_A_LIST: ("The file is there, but it is not a YAML sequence of mappings."),
    p.ENTRY_MISSING_FIELDS: (
        "An entry of a `stories.yaml` or an `epics.yaml` leaves out a field the loop needs."
    ),
    p.DUPLICATE_ENTRY_ID: (
        "Two entries claim the same id, so a row could not say which one it belongs to."
    ),
    p.ID_NOT_PREFIX_FREE: (
        "One id is another id plus `-…`, so `{id}-*.md` would match both stories' files."
    ),
    p.AMBIGUOUS_STORY_FILE: (
        'Two files match one story\'s `{id}-*.md`, so "is it done" has two answers.'
    ),
    p.ONLY_NOT_IN_LIST: "The `only:` id on a `for_each` loop matches no entry in the list file.",
    p.CALLEE_NOT_RESOLVED: (
        "A `uses: template` step names a version the resolved tree does not hold."
    ),
    p.BAD_MINUTES: (
        "A `timeout_min` or `stall_min` expression resolved to something other than a "
        "positive integer."
    ),
    p.BASE_BRANCH_NOT_FOUND: (
        "The Run has no commit to plan from: the remote holds no such base branch."
    ),
    p.NO_FREE_BRANCH: (
        "Every ordinal a declared branch could take is already a branch on the origin, so "
        "the Run has no name of its own to work on."
    ),
    p.REDISPATCH_TARGET_NOT_PLANNED: (
        "A row routes its failure back to a step that is not a row of its own frame. A "
        "step inside a loop may name an earlier agent step outside it, and there is no "
        "such row to go back to."
    ),
    p.DUPLICATE_ROW_PATH: (
        "Two rows expanded to one path, so neither the walker nor the Run's row index "
        "could tell them apart. A step id that collides with an inserted row's, such as "
        "`plan`, `before` or `after`, is the way a template reaches this."
    ),
}
