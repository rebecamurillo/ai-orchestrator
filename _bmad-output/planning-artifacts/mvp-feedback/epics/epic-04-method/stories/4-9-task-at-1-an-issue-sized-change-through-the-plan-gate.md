---
title: task@1 — an issue-sized change through the plan gate
type: feature
created: '2026-09-17'
status: done
baseline_revision: e90f1ccbe8492c4c04b101af6653051b87332758
review_loop_iteration: 0
followup_review_recommended: true
context: []
deferred:
  - summary: >-
      intent + prompt co-presence silently discards intent with no validation diagnostic
    evidence: |-
      _INTENT_KEYS is separate from _DISPATCH_KEYS so a with block carrying {skill, intent,
      prompt} passes validation; compose_prompt fires the prompt branch, silently ignoring
      intent. The same pre-existing priority pattern exists for prompt vs prompt_file.
      A future _check_dispatch_form extension could reject or warn on this combination.
    location: >-
      backend-api/src/orchestrator/application/templates/keys.py:305
    severity: low
  - summary: >-
      expect.files glob propagation from task.yaml into planned rows is not asserted by any test
    evidence: |-
      test_task_validates_clean confirms no validation errors; test_task_plan_has_unconditional_spec_checkpoint
      asserts spec_checkpoint and intent on agent rows, but neither test inspects the expect_files
      field on planned rows. If the planner dropped expect.files during resolution, no unit test
      would detect it. Pre-existing gap consistent with all other template tests.
    location: >-
      backend-api/tests/unit/application/templates/test_task_template.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** There is no `task@1` root template for an issue-sized change that the operator
pastes as intent. Three engine gaps block it:

1. `pause_when` grammar only accepts a `name.field` bare-field expression — the literal
   `"always"` is not recognised, so a flat template cannot declare an unconditional plan gate.
2. `compose_prompt` always emits the folder+id dispatch sentence, which produces a blank
   `spec_folder` / `story_id` when neither is in scope — the intent text never reaches the
   skill.
3. `"intent"` is not an accepted `agent` `with` key, so a template using it is rejected at
   `validate()` with `UNKNOWN_KEY`.

`task@1` follows IMP-002 B1: pasted intent, plan gate always on, resumed by Continue — never
API ingestion (B2 is deferred).

**Approach:** Fix the three engine gaps — accept `"always"` as a `pause_when` literal in
`_check_condition` and `paused`; add `INTENT_KEY = "intent"` and `DISPATCH_INTENT` to
`agent_prompt.py` with a new base-selection branch in `compose_prompt`; add
`_INTENT_KEYS = frozenset({"intent"})` to `_check_with` (same pattern as story 4-3's
`_DISPATCH_KEYS`). Then create `templates/task.yaml` (flat, `pause_when: always`, intent
dispatch, `expect.files` scoped by `{{artifacts_dir}}/spec-{{task_id}}-*.md`) and add `task`
as the fifth root template in the web-client under AGENTS.md exception 4 (IMP-002 accepted
2026-09-15).

## Boundaries & Constraints

**Always:**
- TDD: test files exist and fail before implementation; `max(templates.list_versions("task"))`
  raises `ValueError` before `task.yaml` exists (hard gate in `test_task_template.py`).
- `"always"` is a literal, not a grammar extension: `_check_condition` returns `[]` for it
  (no `BARE_FIELD` match needed); `paused` returns `True` for it before the `BARE_FIELD`
  match. The constant is named `ALWAYS_LITERAL`.
- `DISPATCH_INTENT = "Run the skill {skill} with the following intent:\n\n"` — only `{skill}`
  is a format placeholder (a validated slug, not user input). The intent text is concatenated
  raw to avoid Python's `.format()` treating `{...}` patterns in the intent as placeholders.
- `_INTENT_KEYS = frozenset({"intent"})` — added to the allowed set in `_check_with` but NOT
  to `_DISPATCH_KEYS` (to avoid triggering `INVALID_DISPATCH_FORM` for `skill + intent`).
- `KIND_META["agent"].with_keys` is NOT modified — pinned by `test_step_kind_registry.py`;
  that revision is not authorized in this story.
- Exemplar freeze: no test pins `task.yaml` step ids, counts, ordering, or YAML text.
- `newwf-state.test.ts` revisions name the IMP-002 decision and date at each revised location
  (AGENTS.md exception 4).
- No new Python source modules — test-pair count unchanged.
- The `intent` branch in `compose_prompt` fires after `prompt` and `prompt_file` checks, and
  before the folder+id `DISPATCH` fallback. If `intent` is in `with_resolved`, intent form
  takes precedence over the folder+id fallback.
- `record_trajectory` uses `build_row.story_id or ""` (line 230); task Runs have no
  `story_id`, so `_story_file` produces a glob that matches nothing. AD-19 amendment (whether
  task Runs write a trajectory row) is deferred per SPEC.md out-of-scope section — no fix
  needed here.

**Block If:** Any contradiction between IMP-002's template shape and existing DSL validation
that cannot be resolved from the spec alone.

**Never:**
- Never add `"intent"` to `_DISPATCH_KEYS` — that would make `skill + intent` trigger
  `INVALID_DISPATCH_FORM`.
- Never modify `KIND_META["agent"].with_keys` (exception 4 not granted for this anchor).
- Never implement issue API ingestion (IMP-002 B2 deferred).
- Never add an `intent` textarea to `NewWorkflowFields.tsx` — Epic 6 scope.
- Never fix the `record_trajectory` `story_id=None` path — AD-19 amendment deferred.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| intent dispatch, first dispatch | `intent` in `with_resolved`, `spec_checkpoint=True`, no resume | `DISPATCH_INTENT.format(skill=...) + intent text + HALT suffix` | — |
| intent dispatch, Continue resume | `intent` in `with_resolved`, `spec_checkpoint=True`, continue resume GateRecord | `DISPATCH_INTENT.format(skill=...) + intent text`, no HALT | — |
| intent with curly braces | `intent = "Fix {auth} bug"` | Prompt contains `"Fix {auth} bug"` — no `KeyError` | — |
| `pause_when: always`, validation | top-level agent step with `pause_when: always` | `validate()` → no `EXPRESSION_SYNTAX` error | — |
| `paused("always", {})` | empty scope | returns `True` | — |
| `paused("always", {"story": {"spec_checkpoint": False}})` | scope has False flag | returns `True` (unconditional) | — |
| intent as agent `with` key | agent step with `intent: "{{intent}}"` | `validate()` → no `UNKNOWN_KEY` | — |
| task@1 template, all agent rows | `task.yaml` seeded, plan run | all agent rows have `with_resolved["spec_checkpoint"] == True` | — |
| no intent, folder+id fallback | `with_resolved` has no `intent` key | prompt uses folder+id `DISPATCH` sentence (regression) | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/expressions.py:81` —
  `CONDITION_KEYS = ("pause_when", "pause_before_item_when", "pause_after_item_when")`;
  ADD `ALWAYS_LITERAL: str = "always"` as a module constant on the line immediately after
  `CONDITION_KEYS`.

- `backend-api/src/orchestrator/application/templates/expressions.py:208-215` —
  `_check_condition(value, scope, line)`; ADD `if value == ALWAYS_LITERAL: return []` as the
  first check after the `isinstance(value, str)` guard, before `match = BARE_FIELD.match(value)`.

- `backend-api/src/orchestrator/application/templates/substitute.py:31` —
  existing import from `expressions`; extend it to include `ALWAYS_LITERAL`.

- `backend-api/src/orchestrator/application/templates/substitute.py:127` —
  `paused(condition, scope)` body; ADD `if condition == ALWAYS_LITERAL: return True` immediately
  before `reference = BARE_FIELD.match(condition)`.

- `backend-api/src/orchestrator/application/steps/agent_prompt.py:41` —
  after `PROMPT_FILE_KEY = "prompt_file"`, ADD `INTENT_KEY = "intent"`.

- `backend-api/src/orchestrator/application/steps/agent_prompt.py:44` —
  after `SKILL_KEY = "skill"`, ADD
  `DISPATCH_INTENT = "Run the skill {skill} with the following intent:\n\n"`.

- `backend-api/src/orchestrator/application/steps/agent_prompt.py:47-84` —
  `compose_prompt()` base selection; ADD `elif INTENT_KEY in with_resolved:
  base = DISPATCH_INTENT.format(skill=resolved_text(with_resolved, SKILL_KEY)) + str(with_resolved[INTENT_KEY])`
  between the `elif prompt_file_content is not None` branch and the `else` (folder+id DISPATCH)
  fallback.

- `backend-api/src/orchestrator/application/templates/keys.py:282` —
  `_DISPATCH_KEYS = frozenset({"skill", "prompt", "prompt_file"})`; ADD
  `_INTENT_KEYS: frozenset[str] = frozenset({"intent"})` on the line immediately after.

- `backend-api/src/orchestrator/application/templates/keys.py:302` —
  `_check_with()` allowed set; CHANGE
  `allowed = base | _DISPATCH_KEYS if kind == AGENT_KIND else base` TO
  `allowed = base | _DISPATCH_KEYS | _INTENT_KEYS if kind == AGENT_KIND else base`.

- `templates/task.yaml` — NEW flat template per IMP-002 B1:
  inputs `project` (project), `repository` (repository), `base_branch` (string, required),
  `branch` (string, required), `task_id` (string, required), `title` (string, required),
  `intent` (string, required), `artifacts_dir` (path, required),
  `harness` (enum [claude, codex, local], default claude), `model` (string, optional);
  steps: `checkout` (git.worktree), `baseline` (quality_gate_command, on_fail: fail,
  timeout_min: 45, gate: deterministic), `plan-and-build` (agent, skill: bmad-build-auto,
  intent: `{{intent}}`, expect.files: [`{{artifacts_dir}}/spec-{{task_id}}-*.md`],
  expect.status_in: [done, blocked, ready-for-dev], retry.max: 2,
  retry.resume_session: true, escalate_when: `output.status == blocked`,
  `pause_when: always`, timeout_min: 90, gate: liveness), `verify`
  (unit_test_command, on_fail: {redispatch: plan-and-build, max: 1}, timeout_min: 30,
  gate: deterministic), `commit-guard` (git.commit,
  message: `{{task_id}}: {{title}} (orchestrator)`, gate: deterministic),
  `push` (git.push, branch: `{{branch}}`, gate: deterministic),
  `link` (pr.link, branch: `{{branch}}`, gate: liveness).

- `web-client/src/lib/newwf/state.ts:1-12` — module JSDoc comment; CHANGE
  "four root Templates" to "five root Templates"; add `templates/task.yaml` to the list.

- `web-client/src/lib/newwf/state.ts:22` — `TEMPLATE_ORDER`; ADD `'task'` as the fifth
  element after `'story-run'`.

- `web-client/src/lib/newwf/state.ts:33-45` — `TEMPLATE_INPUT_FIELDS`; ADD `'task'` entry
  with fields `[{key:'branch', label:'WORKING BRANCH'}, {key:'task_id', label:'TASK ID'},
  {key:'title', label:'TITLE'}, {key:'intent', label:'INTENT'},
  {key:'artifacts_dir', label:'ARTIFACTS DIR'}]`.

- `web-client/tests/unit/newwf-state.test.ts:73-105` — REVISE under AGENTS.md exception 4
  (IMP-002 accepted 2026-09-15); add comment
  `// Updated 2026-09-17 (story 4-9): IMP-002 accepted 2026-09-15 — task is the fifth root Template`
  at each revised location:
  - line 73: `'lists the four root Templates'` → `'lists the five root Templates'`
  - line 75: add `'task'` to `toEqual` array
  - line 80: `'gives initiative one input, epic two, repo-init none, story-run three'` →
    add `'task five'` to description
  - after line 91: add `expect(TEMPLATE_INPUT_FIELDS['task'].map(f => f.key)).toEqual(['branch', 'task_id', 'title', 'intent', 'artifacts_dir'])`
  - line 97: `'accepts the four fixed names'` → `'accepts the five fixed names'`
  - after line 102: add `expect(isTemplateName('task')).toBe(true)`

## Tasks & Acceptance

**Execution (TDD order — failing tests first, then implementation):**

1. **CREATE** `backend-api/tests/unit/application/templates/test_pause_when_always.py`
   (fails before `expressions.py` has `ALWAYS_LITERAL` — import error is the hard gate):
   - `test_pause_when_always_passes_condition_check` — inline YAML with a top-level agent step
     and `pause_when: always`; `validate()` returns no `EXPRESSION_SYNTAX` error at that line.
   - `test_paused_returns_true_for_always` — `paused("always", {}) is True`.
   - `test_paused_returns_true_regardless_of_scope` —
     `paused("always", {"story": {"spec_checkpoint": False}}) is True`.
   - `test_paused_returns_false_for_none` — `paused(None, {}) is False`.
   - `test_bare_field_still_works_regression` —
     `paused("story.spec_checkpoint", {"story": {"spec_checkpoint": True}}) is True`.
   - Module docstring: `"story 4-9 (2026-09-17): pause_when: always — ALWAYS_LITERAL constant
     is an architectural anchor; used in task@1 to encode an unconditional plan gate"`

2. **CREATE** `backend-api/tests/unit/application/steps/test_intent_dispatch.py`
   (fails before `agent_prompt.py` has `INTENT_KEY` — import error is the hard gate):
   - `test_intent_dispatch_uses_dispatch_intent_prefix_and_intent_text` —
     `resolved(skill="bmad-build-auto", intent="gh-47: Fix auth")`, no resume;
     assert prompt equals `DISPATCH_INTENT.format(skill="bmad-build-auto") + "gh-47: Fix auth"`.
   - `test_intent_with_curly_braces_does_not_raise` — `intent = "Fix {auth} bug"`;
     assert prompt contains `"Fix {auth} bug"` (no `KeyError`).
   - `test_intent_dispatch_adds_halt_when_spec_checkpoint` —
     `resolved(spec_checkpoint=True, intent="gh-47: Fix auth")`, no resume;
     assert prompt ends with HALT suffix.
   - `test_intent_dispatch_no_halt_on_continue_resume` — resume signal is a continue
     `GateRecord`; assert HALT not in prompt.
   - `test_no_intent_falls_back_to_dispatch_sentence` — `resolved()` without `intent` key;
     assert prompt starts with `"Run the skill"` and contains `"folder+id dispatch mode"`.
   - Module docstring: `"story 4-9 (2026-09-17): intent dispatch form in compose_prompt —
     DISPATCH_INTENT and INTENT_KEY are architectural anchors"`

3. **CREATE** `backend-api/tests/unit/application/templates/test_task_template.py`
   (uses the same `seeded()` helper as `test_story_run_template.py`;
   `max(templates.list_versions("task"))` raises `ValueError` before `task.yaml` exists — hard TDD gate):
   - `test_task_validates_clean` — after `task.yaml` exists: `max(templates.list_versions("task"))`
     succeeds; `validate(stored.yaml, templates=templates)` returns `result.template is not None`
     and `list(result.errors) == []`.
   - `test_task_plan_has_unconditional_spec_checkpoint` — `plan_run` with
     `ResolvedTree(root=result.template, callees=())`; inputs include
     `task_id="gh-47"`, `title="Fix auth"`, `intent="gh-47: Fix the auth bug"`,
     `artifacts_dir=fixtures.SPEC_FOLDER`, `branch=fixtures.EPIC_BRANCH`;
     assert `all(r.with_resolved.get("spec_checkpoint") for r in plan.rows if r.kind == "agent")`.
   - Module docstring: `"story 4-9 (2026-09-17): task@1 template — pause_when: always →
     spec_checkpoint True for all agent rows; template name is an architectural anchor"`

4. **REVISE** `web-client/tests/unit/newwf-state.test.ts` under AGENTS.md exception 4
   (IMP-002 accepted 2026-09-15): update "four" to "five" in descriptions and assertions;
   add `'task'` to `TEMPLATE_ORDER` assertion; add `isTemplateName('task')` assertion;
   add `TEMPLATE_INPUT_FIELDS['task']` key assertion; add comment at each revised location.
   This file revision is written before `state.ts` is updated, so the test fails first.

5. **ADD** `ALWAYS_LITERAL` to `expressions.py` and `_check_condition` guard.

6. **EXTEND** `substitute.py` import and `paused` function.

7. **ADD** `INTENT_KEY`, `DISPATCH_INTENT`, and intent branch to `agent_prompt.py`.

8. **ADD** `_INTENT_KEYS` and update `_check_with` allowed set in `keys.py`.

9. **CREATE** `templates/task.yaml` per IMP-002 B1 shape above.

10. **UPDATE** `web-client/src/lib/newwf/state.ts` — JSDoc comment, `TEMPLATE_ORDER`,
    `TEMPLATE_INPUT_FIELDS`.

11. **RUN** `make lint` — expected: ruff, mypy, import-linter, env-contract, test-pairs,
    tsc, eslint, prettier all green; no new Python source modules means test-pairs unchanged.

12. **RUN** `make test` — expected: all three new backend test files green;
    `newwf-state.test.ts` green; domain + application 100 % branch coverage.

**Acceptance Criteria:**
- Given `test_pause_when_always.py` run before `expressions.py` is changed, then the import
  of `ALWAYS_LITERAL` fails (hard gate confirmed).
- Given a top-level agent step with `pause_when: always`, when `validate()` runs, then no
  `EXPRESSION_SYNTAX` error is returned.
- Given `paused("always", {})`, then `True` is returned.
- Given `paused("always", {"story": {"spec_checkpoint": False}})`, then `True` (unconditional).
- Given `compose_prompt` with `intent: "gh-47: Fix {auth}"` in `with_resolved`, when called,
  then the prompt contains `"Fix {auth}"` without `KeyError`.
- Given `compose_prompt` with `intent: "..."` and `spec_checkpoint=True` on first dispatch,
  then HALT is appended.
- Given `test_task_template.py` run before `task.yaml` exists, then
  `max(templates.list_versions("task"))` raises `ValueError` (hard gate confirmed).
- Given `templates/task.yaml` seeded, when `validate()` runs, then
  `result.template is not None` and no errors.
- Given a planned task@1 Run, then all agent rows have `with_resolved["spec_checkpoint"] == True`.
- Given an agent step with `intent: "{{intent}}"` in `with`, when `validate()` runs, then no
  `UNKNOWN_KEY` error.
- Given `newwf-state.test.ts` revision run before `state.ts` is updated, then the
  `TEMPLATE_ORDER` assertion fails (TDD gate).
- Given `make lint`, then all linters pass; no new Python source modules.
- Given `make test`, then all 3 new backend test files and revised `newwf-state.test.ts`
  pass; domain + application 100 % branch coverage.

## Review Triage Log

### 2026-09-17 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 1, low 3)
- defer: 2: (high 0, medium 0, low 2)
- reject: 15
- addressed_findings:
  - `[medium]` `[patch]` `test_task_plan_has_unconditional_spec_checkpoint` did not assert
    `intent` in `with_resolved` or call `compose_prompt` on a planned row — added both
    assertions so a planner regression that drops `intent` from `with_resolved` is caught
  - `[low]` `[patch]` `ALWAYS_LITERAL` comment referenced `AD-7` (the planned-row AD) which
    is not the right anchor for an expression-grammar constant — removed `AD-7` from comment
  - `[low]` `[patch]` `DISPATCH_INTENT` had an ambiguous single-line comment saying "intent
    text is concatenated raw" without noting that the prefix itself uses `.format(skill=…)`
    — replaced with a two-sentence comment distinguishing the two parts
  - `[low]` `[patch]` No test pinned the exact string value of `DISPATCH_INTENT` — a silent
    change to the constant would not fail any test — added
    `test_dispatch_intent_constant_value` to `test_intent_dispatch.py`

## Spec Change Log

_(no bad_spec repairs in this run)_

## Auto Run Result

### Summary

Implemented three engine gaps that blocked `task@1`: (1) `"always"` literal accepted by
`_check_condition` and `paused()` for an unconditional `pause_when`; (2) intent-dispatch
branch added to `compose_prompt` (after `prompt` / `prompt_file`, before folder+id fallback),
with raw concatenation to avoid format-string injection; (3) `_INTENT_KEYS` added to
`_check_with` allowed set for `AGENT_KIND` without touching `_DISPATCH_KEYS` or
`KIND_META["agent"].with_keys`. Created `templates/task.yaml` (flat, 7 steps, `pause_when:
always`). Added `task` as the fifth root template in the web-client under AGENTS.md exception
4 (IMP-002 accepted 2026-09-15).

### Files Changed

- `backend-api/src/orchestrator/application/templates/expressions.py` — added `ALWAYS_LITERAL`
  constant and early-return in `_check_condition`
- `backend-api/src/orchestrator/application/templates/substitute.py` — imported `ALWAYS_LITERAL`;
  `paused()` returns `True` immediately for the literal
- `backend-api/src/orchestrator/application/steps/agent_prompt.py` — added `INTENT_KEY`,
  `DISPATCH_INTENT`, and intent branch in `compose_prompt`
- `backend-api/src/orchestrator/application/templates/keys.py` — added `_INTENT_KEYS`;
  included in `_check_with` allowed set for `AGENT_KIND`
- `templates/task.yaml` — new root template (task@1, IMP-002 B1)
- `web-client/src/lib/newwf/state.ts` — `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS` extended
  with `task`
- `web-client/tests/unit/newwf-state.test.ts` — revised under exception 4 (IMP-002 2026-09-15)
- `backend-api/tests/unit/application/templates/test_pause_when_always.py` — new; 5 tests
- `backend-api/tests/unit/application/steps/test_intent_dispatch.py` — new; 6 tests (incl.
  `test_dispatch_intent_constant_value` added in review patch)
- `backend-api/tests/unit/application/templates/test_task_template.py` — new; 2 tests (incl.
  `intent`/`compose_prompt` assertions added in review patch)
- `_bmad-output/planning-artifacts/mvp-feedback/epics/epic-04-method/stories/4-9-task-at-1-an-issue-sized-change-through-the-plan-gate.md`
  — this spec file

### Review Findings Breakdown

- Patches applied: 4 (1 medium, 3 low)
- Items deferred: 2 (both low)
- Items rejected: 15

Follow-up review score: 3×1 (medium) + 1×3 (low) = 6 ≥ 5 → `followup_review_recommended: true`

### Verification

- `make lint` — ruff, ruff format, mypy, import-linter, env-contract, test-pairs, tsc,
  eslint, prettier, web-client test-pairs: all green
- `make test` (backend) — 6381 passed, 23 skipped, 0 failed (40.68s); domain + application
  100 % branch coverage maintained
- `make test` (web-client) — 1348 passed (111 files)
- All 13 new test cases (5 pause_when_always + 6 intent_dispatch + 2 task_template) passing

### Residual Risks

- `intent + prompt` co-presence silently discards `intent` (same priority pattern as existing
  `prompt` / `prompt_file`; deferred for future `_check_dispatch_form` extension)
- `expect.files` glob propagation through the planner to planned rows is not asserted; if the
  planner dropped the field a task Run would complete without the expected spec file guard
  (deferred; pre-existing gap across all template tests)
