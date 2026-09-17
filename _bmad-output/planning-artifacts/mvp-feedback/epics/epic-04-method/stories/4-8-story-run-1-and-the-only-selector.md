---
title: story-run@1 and the only selector
type: feature
created: '2026-09-17'
status: done
baseline_revision: ea32720c365555cce53a39d0091e2df094220084
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred:
  - summary: >-
      usesHarness and withTemplate harness tests in newwf-state.test.ts do not assert story-run
    evidence: |-
      usesHarness('story-run') correctly returns true (negative match on 'repo-init') but is
      unasserted. withTemplate harness-clearing tests cover initiative/epic/repo-init only.
      Fixing requires touching newwf-state.test.ts, an existing test file, without current
      operator authorization.
    location: >-
      web-client/tests/unit/newwf-state.test.ts:306-326
    severity: low
---

<intent-contract>

## Intent

**Problem:** There is no way to start a Run for a single story — `for_each` has no plan-time filter, the operator must run a full epic and rely on the already-done rule to skip everything else, and `story.yaml` is a callee-only template with no `git.worktree` step. `story-run` is absent from the web-client dropdown.

**Approach:** Add `only: str | None` to `ForEach` (a plan-time filter, not a runtime conditional — FR-5's no-conditionals rule stands because filtering occurs in `expand_loop` before any step runs); wire unknown-key acceptance in `FOR_EACH_KEYS` and outer-scope expression validation in `_check_for_each`; filter `expand_loop` to the single matching entry raising `PlanError(ONLY_NOT_IN_LIST)` on no match; create `templates/story-run.yaml` per IMP-001 option B; and extend the web-client's `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS`.

## Boundaries & Constraints

**Always:**
- FR-5 no-conditionals rule stands: `only:` is a planning-time list filter (decides which rows exist in the plan), not a per-step runtime condition. The distinction: `expand_loop` runs once at plan time before any step executes.
- TDD: new backend test files fail before backend implementation; `newwf-state.test.ts:74` revision (AGENTS.md exception 4, IMP-001 accepted 2026-09-15) is written first so it fails until `state.ts` is updated.
- Exemplar freeze: `tests/unit/application/templates/fixtures/exemplars/epic.yaml` and existing epic-shape tests are untouched. `plan_fixtures.py` is an anchor — do not modify it.
- `only:` is general — the implementation is not story-specific; it works for any `for_each` loop.
- `contracts/openapi.json` is unaffected (`RunIn.inputs` is already an open object). No new settings.
- No new Python source modules created, so test-pair count is unchanged.
- The shipped `story.yaml` (callee) is not modified.
- The already-done rule applies unchanged: `only:` filters the entry list; `_already_done` then skips a matched entry if its story file is `status: done` (unless `re_review_done` is set). This is "pre-flight behaves as for epic."

**Block If:** Any contradiction between IMP-001 option B template shape and SPEC.md that cannot be resolved without operator input.

**Never:**
- Do not add `"only"` to `CONDITION_KEYS` in `expressions.py` — `only:` reads outer scope, not the loop's `as:` variable.
- Do not implement `task@1` (story 4-9).
- Do not pin shipped template step ids, counts, ordering, or graph shapes in any test.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| `only` matches | `stories.yaml` entries "1","2","3"; `only: "{{story_id}}"`, `story_id="2"` | One story frame for "2" planned | No error |
| `only` no match | Same list; `story_id="99"` | `PlanError(ONLY_NOT_IN_LIST)` | Plan refused before first step |
| `only` absent | Same list; no `only:` | All 3 frames (regression) | No error |
| `only:` literal | `only: "2"` (no `{{ }}`) | Resolves to literal; filters to "2" | No error |
| `only:` bad expression | `only: "{{undeclared}}"` | Validation: unbound-name error | Template rejected at `validate()` |
| `only:` before change | `for_each` node with `only:` | `UNKNOWN_KEY` validation error | Template rejected |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/model.py:168-179` — `ForEach` frozen `BaseModel`; add `only: str | None = None` after `pause_after_item_when: str | None = None` on line 179
- `backend-api/src/orchestrator/application/templates/table.py:31-41` — `FOR_EACH_KEYS` frozenset; add `"only"` so `keys.py`'s `unknown_keys()` call accepts it; no other key table changes
- `backend-api/src/orchestrator/application/templates/validate.py:157-167` — `_entry()`; add `only=_text(node.get("only"))` to `ForEach(...)` construction; `_text()` (line 130) converts Any to `str | None`
- `backend-api/src/orchestrator/application/templates/expressions.py:122-138` — `_check_for_each()`; after the `source` `_scan_text` call on line 132, add: `if isinstance(only_val := node.get("only"), str): errors += _scan_text(only_val, types, key_line(node, "only", node.line))`; uses outer `types` scope (same as `source`), NOT item scope — `only:` is NOT added to `CONDITION_KEYS`
- `backend-api/src/orchestrator/application/templates/plan_model.py:49-51` — reason constants near `CALLEE_NOT_RESOLVED`; add `ONLY_NOT_IN_LIST = "only: id not in list"` after `CALLEE_NOT_RESOLVED`
- `backend-api/src/orchestrator/application/templates/rows.py:58-73` — imports from `plan_model`; add `ONLY_NOT_IN_LIST` to the import group; `ID_KEY` already imported at line 44
- `backend-api/src/orchestrator/application/templates/rows.py:180-192` — `expand_loop()`; after `check_entries` on line 185 and before `outer = replace(...)`, add: `if loop.only is not None: target_id = str(resolve(loop.only, frame.scope)); items = [e for e in items if e.get(ID_KEY) == target_id]; (raise PlanError(reason=ONLY_NOT_IN_LIST, template=frame.template.name, version=frame.template.version, line=loop.line, item=target_id) if not items)`
- `templates/story-run.yaml` — NEW ~45-line template per IMP-001 option B: inputs `project` (project), `repository` (repository), `base_branch` (string, required), `branch` (string, required), `spec_folder` (path, required), `story_id` (string, required), `harness` (enum [claude,codex,local], default claude), `model` (string, optional); steps: `checkout` (git.worktree, with base/branch, gate deterministic), `baseline` (run quality_gate_command, on_fail: fail, timeout_min: 45, gate deterministic), `stories` (for_each `{{spec_folder}}/stories.yaml`, as: story, only: `{{story_id}}`, steps: `story` template call to story@1 identical to epic.yaml's call), `push` (git.push, with branch, gate deterministic), `link` (pr.link, with branch, gate liveness)
- `web-client/src/lib/newwf/state.ts:21` — `TEMPLATE_ORDER` const; add `'story-run'` as fourth element; `TEMPLATE_INPUT_FIELDS` record: add `'story-run'` key with fields `[{key:'branch', label:'WORKING BRANCH'}, {key:'spec_folder', label:'SPEC FOLDER'}, {key:'story_id', label:'STORY ID'}]`
- `web-client/tests/unit/newwf-state.test.ts:73-85` — existing anchor; AGENTS.md exception 4 (IMP-001 accepted 2026-09-15): line 74 pins old 3-template list; line 89 says "three fixed names"; revision updates both to four-template state and names the decision

## Tasks & Acceptance

**Execution (TDD order — failing tests first, then implementation):**

- `backend-api/tests/unit/application/templates/test_only_selector.py` -- CREATE first -- TDD test for `expand_loop` `only:` filter; import `ONLY_NOT_IN_LIST` from `plan_model` (import fails before constant exists — hard gate); local `HEADER` YAML with `story_id: { type: string, required: true }` input and a `for_each: "{{spec_folder}}/stories.yaml"` with `only: "{{story_id}}"` step containing one `git.sync` child; local `plan_run` helper following `test_plan_shipped.py`'s `plan()` function pattern, using `fixtures.epic_git()` and `fixtures.inputs(values={"story_id": ..., "branch": fixtures.EPIC_BRANCH, "spec_folder": fixtures.SPEC_FOLDER})`; write three tests: (a) `test_only_selector_plans_single_matching_frame` — `story_id="2"`, assert `{r.story_id for r in result.rows if r.story_id is not None} == {"2"}`; (b) `test_only_selector_raises_plan_error_on_no_match` — `story_id="99"`, assert `PlanError` raised with `reason == ONLY_NOT_IN_LIST`; (c) `test_for_each_without_only_plans_all_frames` — same template without `only:`, assert three distinct non-None `story_id` values in rows; docstring: "story 4-8 (2026-09-17): only: selector in expand_loop — ONLY_NOT_IN_LIST constant is an architectural anchor"

- `backend-api/tests/unit/application/templates/test_validate_only_key.py` -- CREATE first -- TDD test for validate acceptance and expression check of `only:`; inline YAML template with `story_id: {type: string, required: true}` and a `for_each` block with `only: "{{story_id}}"`; (a) `test_for_each_with_only_passes_validation` — `validate()` returns no `UNKNOWN_KEY` and no unbound-name error; (b) `test_for_each_with_only_rejects_unknown_expression` — `only: "{{undeclared}}"` yields a validation error; docstring: "story 4-8 (2026-09-17): validate.py accepts only: on for_each — outer scope, not item scope"

- `backend-api/tests/unit/application/templates/test_story_run_template.py` -- CREATE first -- TDD test verifying `story-run@1` seeds clean; replicate `seeded()` helper from `test_e2e_generation_gate.py` exactly (same imports, `SHIPPED_DIR`, `AT`, body); (a) `test_story_run_validates_clean` — `max(templates.list_versions("story-run"))` raises `ValueError` before the template exists (hard TDD gate); after implementation: load stored yaml, call `validate(stored.yaml, templates=templates)`, assert `result.template is not None` and `result.errors == []`; (b) `test_story_run_plans_one_story_frame` — build `ResolvedTree(root=story_run_parsed, callees=(story_parsed,))` from seeded(), call `plan_run` with `fixtures.epic_git()` and `fixtures.inputs(values={"story_id":"2", "branch": fixtures.EPIC_BRANCH, "spec_folder": fixtures.SPEC_FOLDER})`, assert `{r.story_id for r in plan.rows if r.story_id is not None} == {"2"}`; docstring: "story 4-8 (2026-09-17): story-run@1 template — ships for_each with only: bound to story_id; template name and only: key are architectural anchors"

- `web-client/tests/unit/newwf-state.test.ts` -- REVISE under AGENTS.md exception 4 (IMP-001 accepted 2026-09-15, FR-33) -- (1) line 73: update `it` description from "three root Templates" to "four root Templates"; (2) line 74: `toEqual(['initiative', 'epic', 'repo-init', 'story-run'])`; (3) line 89: update description to "accepts the four fixed names and refuses anything else"; add `expect(isTemplateName('story-run')).toBe(true)`; (4) in the TEMPLATE_INPUT_FIELDS `it` block: add `expect(TEMPLATE_INPUT_FIELDS['story-run'].map(f => f.key)).toEqual(['branch', 'spec_folder', 'story_id'])`; each revised location adds a comment: `// Updated 2026-09-17 (story 4-8): IMP-001 accepted 2026-09-15 — story-run is the fourth root Template`

- `backend-api/src/orchestrator/application/templates/plan_model.py` -- ADD -- `ONLY_NOT_IN_LIST = "only: id not in list"` after `CALLEE_NOT_RESOLVED`

- `backend-api/src/orchestrator/application/templates/model.py` -- ADD -- `only: str | None = None` to `ForEach` after `pause_after_item_when`

- `backend-api/src/orchestrator/application/templates/table.py` -- ADD -- `"only"` to `FOR_EACH_KEYS` frozenset

- `backend-api/src/orchestrator/application/templates/validate.py` -- ADD -- `only=_text(node.get("only"))` in `_entry()` when constructing `ForEach`

- `backend-api/src/orchestrator/application/templates/expressions.py` -- ADD -- outer-scope `only` scan in `_check_for_each()` after source scan on line 132: `if isinstance(only_val := node.get("only"), str): errors += _scan_text(only_val, types, key_line(node, "only", node.line))`

- `backend-api/src/orchestrator/application/templates/rows.py` -- ADD -- `ONLY_NOT_IN_LIST` to import group (lines 58-73); `only:` filter logic in `expand_loop()` after `check_entries` (line 185); see Code Map for exact logic

- `templates/story-run.yaml` -- CREATE -- per IMP-001 option B; see Code Map for shape; copy the `stories:` for_each block's `steps:` child from `templates/epic.yaml` unchanged (project/repository/branch/spec_folder/story/harness/model bindings)

- `web-client/src/lib/newwf/state.ts` -- ADD -- `'story-run'` to `TEMPLATE_ORDER`; add `'story-run'` entry to `TEMPLATE_INPUT_FIELDS`

**Acceptance Criteria:**
- Given `test_only_selector.py` run before implementation, then import of `ONLY_NOT_IN_LIST` fails (hard gate — test cannot be collected)
- Given `for_each` with `only: "{{story_id}}"`, `story_id="2"`, and a 3-entry stories.yaml, when `plan_run` runs, then `{r.story_id for r in plan.rows if r.story_id is not None} == {"2"}`
- Given `only: "{{story_id}}"` with `story_id="99"` (no match), when `plan_run` runs, then `PlanError` raised with `reason == "only: id not in list"`
- Given an inline template with `only: "{{story_id}}"` and `story_id` declared as a string input, when `validate()` runs, then no `UNKNOWN_KEY` and no unbound-name error
- Given `test_story_run_validates_clean` run before `story-run.yaml` is created, then `max(templates.list_versions("story-run"))` raises `ValueError` (hard TDD gate)
- Given `templates/story-run.yaml` seeded, when `validate()` runs on it, then `result.template is not None` and `result.errors == []`
- Given a story-run@1 plan with `story_id="2"` against `EPIC_STORIES`, then `{r.story_id for r in plan.rows if r.story_id is not None} == {"2"}`
- Given `newwf-state.test.ts` revision run before `state.ts` update, then the `toEqual(['initiative','epic','repo-init','story-run'])` assertion fails
- Given `make lint`, then ruff, mypy, import-linter, env-contract, test-pairs, tsc, eslint, prettier all pass; no new Python source modules (test-pair count unchanged); `newwf-state.test.ts` revision names IMP-001 decision and date in each revised location
- Given `make test`, then all 3 new backend test files and revised `newwf-state.test.ts` pass; domain + application 100% branch coverage

## Design Notes

`only:` is a plan-time filter: `expand_loop` reads the full list, calls `check_entries` on it (so duplicate-id and missing-field errors fire even with `only:` set), then narrows `items` to the single match before the frame loop. A no-match is a `PlanError` — not a silent empty plan — consistent with every other list refusal in `lists.py`.

The key reads outer scope (the template's declared inputs), not item scope (the loop's `as:` variable). This mirrors how `for_each: "{{spec_folder}}/..."` itself is outer-scoped, and is what makes `only: "{{story_id}}"` work — `story_id` is an input, not a field on the matched story entry.

`newwf-state.test.ts:74` pins the 3-template list exactly. IMP-001 (accepted 2026-09-15, FR-33) adds `story-run` as the fourth root template. The revision is exception 4: the new assertion asserts the new behavior and names the decision and date.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter, env-contract, test-pairs all green; tsc and eslint green after state.ts change; no new Python source modules
- `make test` -- expected: 3 new backend test files green, `newwf-state.test.ts` green after revision; domain + application 100% branch coverage; total ~6363+ backend tests passing

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 2: (high 0, medium 0, low 2)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` Outer-scope invariant untested: `only: "{{story}}"` on a loop `as: story` was not asserted to raise `UNBOUND_VARIABLE`. Added `test_for_each_with_only_rejects_as_name` to `test_validate_only_key.py` with fixture `TEMPLATE_ONLY_AS_NAME` using the `as:` name in `only:`.
  - `[low]` `[patch]` I/O matrix row 4 (literal `only:`) had no test. Added `HEADER_LITERAL_ONLY` template and `test_only_selector_with_literal_value_filters_correctly` to `test_only_selector.py`; `only: "2"` (no expression) plans story "2" correctly.

## Auto Run Result

### Summary
Added `only: str | None` plan-time filter to `ForEach`, wired validation (unknown-key acceptance and outer-scope expression check), and added `expand_loop` filtering with `PlanError(ONLY_NOT_IN_LIST)` on no match. Created `templates/story-run.yaml` (IMP-001 option B): a root template that checks out a branch, runs the quality gate, dispatches exactly one story via `only: "{{story_id}}"`, pushes, and creates a PR link. Extended the web-client `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS` with `story-run` as the fourth root template under AGENTS.md exception 4 (IMP-001 accepted 2026-09-15).

### Files changed
- `backend-api/src/orchestrator/application/templates/model.py` — added `only: str | None = None` to `ForEach`
- `backend-api/src/orchestrator/application/templates/table.py` — added `"only"` to `FOR_EACH_KEYS`
- `backend-api/src/orchestrator/application/templates/validate.py` — mapped `only` YAML key in `_entry()`
- `backend-api/src/orchestrator/application/templates/expressions.py` — added outer-scope scan for `only:` in `_check_for_each()`
- `backend-api/src/orchestrator/application/templates/plan_model.py` — added `ONLY_NOT_IN_LIST` constant
- `backend-api/src/orchestrator/application/templates/rows.py` — added `only:` filter block in `expand_loop()`
- `templates/story-run.yaml` — new shipped root template per IMP-001 option B
- `web-client/src/lib/newwf/state.ts` — added `story-run` to `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS`
- `web-client/tests/unit/newwf-state.test.ts` — revised under AGENTS.md exception 4 to assert four-template state
- `backend-api/tests/unit/application/templates/test_only_selector.py` — new; 4 tests covering filter, no-match, regression, literal
- `backend-api/tests/unit/application/templates/test_validate_only_key.py` — new; 3 tests covering pass, unbound, as-name rejection
- `backend-api/tests/unit/application/templates/test_story_run_template.py` — new; validates and plans story-run@1
- `backend-api/tests/unit/fakes/templates.py` — fixed `list()` sort to match path-sort order (smoke test alignment)

### Review findings breakdown
- patches applied: 2 (medium: outer-scope invariant test; low: literal only: test)
- items deferred: 2 (low: `usesHarness('story-run')` and `withTemplate` harness not asserted for `story-run` in existing test file — requires operator authorization to modify)
- items rejected: 9 (noise: duplicate-ID case protected by `check_entries`; non-string `only:` handled by `_text()`; non-string `resolve()` result wrapped by `str()`; check_entries-before-filter is documented design; no-retry is not spec'd; implicit on_fail is framework default; plan-row structure covered by validation test; description wording; intent-alignment false positives from outside this story's diff)

### Follow-up review recommendation
Patched counts: medium 1, low 1. Score: 3×1 + 1×1 = 4 < 5. followup_review_recommended: false.

### Verification
- `make lint`: all checks green (ruff, mypy, import-linter, env-contract, test-pairs, tsc, eslint, prettier)
- `make test`: 6369 backend tests passed, 1348 web-client tests passed; domain + application 100% branch coverage

### Residual risks
- `usesHarness('story-run')` is not explicitly asserted; the function returns `template !== 'repo-init'` so it returns `true` for `story-run` (correct) but without a pinning test. Deferred.
