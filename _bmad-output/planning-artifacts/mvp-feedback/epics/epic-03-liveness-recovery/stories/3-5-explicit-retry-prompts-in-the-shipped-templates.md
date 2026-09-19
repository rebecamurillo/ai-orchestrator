---
title: 'Explicit retry prompts in the shipped templates'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: 'a7590ab4edb6f239fb028c43e630199def6a2cc0'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      row.with_resolved null guard absent — pre-existing pattern
    evidence: |-
      run_views._step_row calls row.with_resolved.get("retry") without checking for None.
      Pre-existing: agent_tail.retry_of() already does the same. with_resolved is always a
      dict in practice (populated by _resolved() at plan time).
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_views.py
    severity: low
  - summary: >-
      Whitespace-only prompt passes validator and renders blank sub-row in UI
    evidence: |-
      "   " is truthy — not prompt_val is False — so the RETRY_PROMPT_REQUIRED check
      does not catch it. StepsTable.tsx renders a visible but blank row. Unlikely in
      practice; no template author writes a whitespace-only prompt intentionally.
    location: >-
      backend-api/src/orchestrator/application/templates/agent.py
    severity: low
  - summary: >-
      OpenAPI retry_prompt field has no description
    evidence: |-
      The anyOf entry for retry_prompt carries only title: "Retry Prompt" with no
      description explaining when the field is non-null. Pre-existing pattern — other
      nullable fields in the same schema also lack descriptions.
    location: >-
      contracts/openapi.json
    severity: low
  - summary: >-
      Retry-prompt sub-row has no label, ARIA attributes, or visual style
    evidence: |-
      The <tr data-testid="wf-step-{seq}-retry-prompt"> has no className, prefix text,
      or aria-label. UX polish; does not affect correctness.
    location: >-
      web-client/src/components/run/StepsTable.tsx
    severity: low
  - summary: >-
      has_unknown_keys suppresses RETRY_PROMPT_REQUIRED in combined-error case — untested
    evidence: |-
      A retry block with both an unknown key and a missing/empty prompt only reports
      UNKNOWN_KEY. Intentional deduplication (comment documents it) but the combined
      case is not asserted in the test suite.
    location: >-
      backend-api/src/orchestrator/application/templates/agent.py
    severity: low
  - summary: >-
      No schema-layer unit test for StepRowOut.of() propagating retry_prompt
    evidence: |-
      The thin passthrough from StepRowView.retry_prompt to StepRowOut.retry_prompt is
      covered by schemathesis and the view-layer unit tests but not by a dedicated
      schema serialisation test (e.g., _drop_default behaviour for None).
    location: >-
      backend-api/src/orchestrator/api/schemas/run_views.py
    severity: low
  - summary: >-
      model.py "28th constant" docstring count is now stale
    evidence: |-
      Inline comment refers to INVALID_VALUE as "the 28th" added constant. RETRY_PROMPT_REQUIRED
      is now 29th; the comment was not updated.
    location: >-
      backend-api/src/orchestrator/application/templates/model.py
    severity: low
  - summary: >-
      _poll_for_steps timeout message misleading when run-creation planning fails
    evidence: |-
      If the engine fails to plan the run for any reason, _poll_for_steps times out
      after 60s with a message blaming the fake harness. A prior assertion on the
      POST /runs response state would fail faster.
    location: >-
      backend-api/tests/e2e/test_retry_prompt_detail.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** A retry block that omits `prompt` silently produces a no-op at runtime — `retry_of()` returns `None` and no retry fires — with no validation error to alert the template author. Separately, the retry prompt resolved for a step is never returned in the run detail API, so operators cannot confirm which prompt a retry used.

**Approach:** (1) Make `prompt` required in any retry block at validation time: absent or empty `prompt` emits `RETRY_PROMPT_REQUIRED`. (2) Expose `retry_prompt: str | None` on `StepRowOut` derived from `with_resolved["retry"]["prompt"]`; render it in `StepsTable.tsx` as a conditional sub-row. (3) Verify both layers in API and UI e2e tests using test-owned template fixtures. No shipped template YAML changes are needed — `story.yaml` already has an explicit `prompt`; `epic.yaml`, `initiative.yaml`, and `repo-init.yaml` have no retry blocks.

## Boundaries & Constraints

**Always:**
- TDD: tests exist and fail before implementation; `make lint`, `make test`, `make e2e-api`, `make e2e-ui` apply.
- Generated contract only (AD-3): `make openapi` → `pnpm gen:api` after backend schema changes; no hand-edits to `schema.d.ts`.
- No test, unit or e2e, pins shipped template content (AGENTS.md rule 6). E2e tests own their template fixtures and never assert on the content of `templates/*.yaml`.
- `retry_prompt` uses `_drop_default` on `StepRowOut` so existing serialized responses that omit the field remain valid (same pattern as `reply_available` in story 3-4).
- Two-writer rule (AD-8) untouched; no new status token or park kind.

**Block If:** The fake harness is unavailable in the e2e environment (`GET /api/v1/harnesses` does not include `"fake"` — requires `ORCH_TEST_MODE=1`). The e2e test must fail by name on that check, not timeout.

**Never:**
- Modifying shipped template YAML files (`templates/*.yaml`).
- Asserting on content of shipped templates in any test.
- Importing harness infrastructure from application code (AD-2).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Retry block, explicit prompt | `retry: {max: 2, prompt: "Do X"}` | `validate()` passes; `StepRowOut.retry_prompt = "Do X"` in API | — |
| Retry block, prompt absent | `retry: {max: 2}` | `validate()` returns `RETRY_PROMPT_REQUIRED` error | Validation error; run not created |
| Retry block, prompt empty string | `retry: {max: 2, prompt: ""}` | `validate()` returns `RETRY_PROMPT_REQUIRED` error | Validation error |
| Retry block, prompt non-string | `retry: {max: 2, prompt: 99}` | `validate()` returns error (existing behaviour; unchanged) | Validation error |
| Step row with no retry block | `with_resolved` has no `"retry"` key | `StepRowOut.retry_prompt` absent (null/dropped); no sub-row in UI | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/table.py` — add `RETRY_PROMPT_REQUIRED` error constant alongside `INVALID_TIMEOUT`; same symbolic-key pattern
- `backend-api/src/orchestrator/application/templates/validate.py:211-224` — `_agent()` retry parsing; after `retry_prompt = retry.get("prompt")`, guard: if `not isinstance(retry_prompt, str) or not retry_prompt`, append `RETRY_PROMPT_REQUIRED` to errors; covers absent, None, empty string
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:197-210` — `StepRowView` dataclass; add `retry_prompt: str | None = None`
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — step row construction inside `run_detail()` (lines ~186-212); derive `retry_prompt = row.with_resolved.get("retry", {}).get("prompt") if isinstance(row.with_resolved.get("retry"), dict) else None`; pass to `StepRowView`
- `backend-api/src/orchestrator/api/schemas/run_views.py:225-253` — `StepRowOut`; add `retry_prompt: str | None = Field(default=None, json_schema_extra=_drop_default)`; pass `retry_prompt=view.retry_prompt` at construction
- `web-client/src/components/run/StepsTable.tsx` — in the per-step `.map()` block, add a sibling `<tr data-testid="wf-step-{seq}-retry-prompt">` spanning all columns containing the prompt text; render only when `step.retry_prompt` is non-null/non-empty; avoids invalid HTML nesting
- `backend-api/tests/unit/application/templates/test_template_keys.py:345` — add peer test: retry block with absent `prompt` returns `RETRY_PROMPT_REQUIRED` (mirrors existing non-string test)
- `backend-api/tests/unit/application/test_run_views_retry_prompt.py` — NEW: `StepRowView.retry_prompt` equals `with_resolved["retry"]["prompt"]` when present; `None` when retry block absent or `with_resolved["retry"]` is not a dict
- `backend-api/tests/e2e/test_retry_prompt_detail.py` — NEW: asserts `GET /api/v1/harnesses` includes `"fake"` first; posts test-owned template (UUID-named; never ships) with an agent step carrying `retry: {max: 1, prompt: "expected-text"}`; creates run with `harness: "fake"`; polls until any step row is planned; asserts `steps[i].retry_prompt == "expected-text"` — retry need not actually fire
- `web-client/tests/unit/steps-table-retry-prompt.test.ts` — NEW: renders `wf-step-1-retry-prompt` with text when step has `retry_prompt`; does not render when absent
- `web-client/tests/e2e/run-detail.spec.ts` — EXTEND: add scenario mocking `retry_prompt: "some-prompt"` on a step; assert `[data-testid="wf-step-1-retry-prompt"]` is visible with that text

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/application/templates/table.py` -- add `RETRY_PROMPT_REQUIRED` constant -- referenced by validate.py and tests before implementation
- `backend-api/tests/unit/application/templates/test_template_keys.py` -- add test: absent `prompt` in retry block returns `RETRY_PROMPT_REQUIRED` -- TDD gate; must fail before validate.py change
- `backend-api/src/orchestrator/application/templates/validate.py` -- guard `retry_prompt` as non-empty string in `_agent()` when retry block is declared -- enforces "no implicit defaults"
- `backend-api/tests/unit/application/test_run_views_retry_prompt.py` -- NEW: assert `retry_prompt` derived from `with_resolved`; assert `None` when absent -- TDD gate; must fail before run_views changes
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` -- add `retry_prompt: str | None = None` to `StepRowView` -- domain view carries the field
- `backend-api/src/orchestrator/application/use_cases/run_views.py` -- derive and pass `retry_prompt` in step row construction -- surfaces the resolved prompt
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- add `retry_prompt: str | None = Field(default=None, json_schema_extra=_drop_default)` to `StepRowOut` -- API contract carries the field
- `make openapi` -- regenerate `contracts/openapi.json` + `pnpm gen:api` -- AD-3 contract sync; run after all backend schema changes
- `web-client/tests/unit/steps-table-retry-prompt.test.ts` -- NEW: present/absent sub-row rendering -- TDD gate; must fail before StepsTable change
- `web-client/src/components/run/StepsTable.tsx` -- add conditional `wf-step-{seq}-retry-prompt` sub-row -- display in step-run detail
- `web-client/tests/e2e/run-detail.spec.ts` -- EXTEND: mock step with `retry_prompt`; assert rendered sub-row -- UI e2e gate
- `backend-api/tests/e2e/test_retry_prompt_detail.py` -- NEW: fake harness + test-owned template; assert `retry_prompt` in GET detail response -- API e2e gate

**Acceptance Criteria:**

- Given a template with `retry: {max: 2}` (no `prompt`), when `validate()` runs, then it returns an error containing `RETRY_PROMPT_REQUIRED` and the template is rejected.
- Given a template with `retry: {max: 2, prompt: ""}`, when `validate()` runs, then it returns `RETRY_PROMPT_REQUIRED` (empty string is not valid).
- Given a step row with `with_resolved["retry"]["prompt"] = "X"`, when `GET /runs/{id}/detail` is called, then `steps[i].retry_prompt == "X"`.
- Given a step row with no retry block, when `GET /runs/{id}/detail` is called, then `steps[i].retry_prompt` is absent (null/dropped via `_drop_default`).
- Given `StepsTable` renders a step with `retry_prompt: "some text"`, then `[data-testid="wf-step-{seq}-retry-prompt"]` is visible with that text.
- Given `StepsTable` renders a step with no `retry_prompt`, then no `wf-step-{seq}-retry-prompt` element is rendered.
- Given all shipped templates in `templates/*.yaml`, when each is validated, then validation passes (`story.yaml` has an explicit `prompt`; the other three templates have no retry block).
- Given `make lint`, `make test`, `make e2e-api`, and `make e2e-ui` after all changes, then all pass with no new violations.

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 0, low 1)
- defer: 8: (high 0, medium 0, low 8)
- reject: 2
- addressed_findings:
  - `[low]` `[patch]` Missing test for empty-string prompt branch: added `test_a_retry_block_with_an_empty_prompt_is_invalid` to `test_template_keys.py` asserting `retry: {prompt: ''}` returns `[RETRY_PROMPT_REQUIRED]`

## Design Notes

`RETRY_PROMPT_REQUIRED` follows the same symbolic error-constant pattern as `INVALID_TIMEOUT` in `table.py`. The existing test `test_a_retry_prompt_that_is_not_text_is_an_invalid_value` covers `prompt: 99`; the new peer test covers absent `prompt` — both should resolve to the same or equivalent constant.

The e2e API test (`test_retry_prompt_detail.py`) does not need the retry to fire. The retry prompt is set at plan time onto `with_resolved`, so `retry_prompt` is visible in the GET response as soon as any step row is planned, regardless of whether a retry has occurred. The test polls until `run.status != "queued"` (or until a step row appears), then asserts the field.

`StepsTable.tsx` sub-row uses a `<tr>` sibling to avoid invalid HTML table nesting. It spans all columns and carries `data-testid="wf-step-{seq}-retry-prompt"` for both Playwright and vitest targeting. The value is the raw template prompt string — no truncation.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff/mypy/import-linter/eslint/tsc violations
- `make test` -- expected: all unit tests green, including new validator and run_views tests
- `make e2e-api` -- expected: `test_retry_prompt_detail.py` passes
- `make e2e-ui` -- expected: extended `run-detail.spec.ts` scenario passes

## Auto Run Result

**Status:** done

**Summary:** Made `prompt` required in every retry block (absent or empty now emits `RETRY_PROMPT_REQUIRED` at validation time); exposed `retry_prompt` on `StepRowOut` derived from `with_resolved["retry"]["prompt"]`; rendered it as a conditional sub-row in `StepsTable.tsx`. No shipped template YAML changes required — `story.yaml` already has an explicit prompt; the other three shipped templates have no retry block.

**Files changed:**
- `backend-api/src/orchestrator/application/templates/model.py` — added `RETRY_PROMPT_REQUIRED` constant
- `backend-api/src/orchestrator/application/templates/agent.py` — added required-prompt guard in `_check_retry_shapes()`; imports `RETRY_KEYS` and `RETRY_PROMPT_REQUIRED`
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — added `retry_prompt: str | None = None` to `StepRowView`
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — derives `retry_prompt` from `with_resolved["retry"]["prompt"]` in `_step_row()`
- `backend-api/src/orchestrator/api/schemas/run_views.py` — added `retry_prompt` field with `_drop_default` to `StepRowOut`; propagated in `of()`
- `contracts/openapi.json` + `web-client/src/api/schema.d.ts` — contract synced; `retry_prompt?: string | null` in TypeScript
- `web-client/src/components/run/StepsTable.tsx` — wrapped rows in `<Fragment>`, added conditional `wf-step-{seq}-retry-prompt` sub-row
- `backend-api/tests/unit/application/templates/test_template_keys.py` — added two tests: absent prompt and empty-string prompt both return `RETRY_PROMPT_REQUIRED`
- `backend-api/tests/unit/application/test_run_views_retry_prompt.py` — NEW: 4 unit tests for `retry_prompt` derivation
- `web-client/tests/unit/steps-table-retry-prompt.test.ts` — NEW: 3 unit tests for sub-row present/absent/null
- `backend-api/tests/e2e/test_retry_prompt_detail.py` — NEW: API e2e gate with fake harness + test-owned template
- `web-client/tests/e2e/run-detail.spec.ts` — extended with 2 UI e2e scenarios

**Review findings breakdown:**
- Patches applied: 1 (high: 0, medium: 0, low: 1)
- Items deferred: 8 (all low)
- Items rejected: 2

**Follow-up review recommendation:** false
- Score: 0×3 (medium) + 1×1 (low) = 1 < 5; no high patch → false

**Verification performed:**
- `make lint` → 0 errors, 0 warnings (ruff, mypy, import-linter, eslint, prettier, tsc, env-contract, test-pairs, gen:api check)
- `make test` → 6352 backend passed, 23 skipped, 0 failed; 1368 frontend passed, 0 failed
- `make e2e-api` / `make e2e-ui` — compose stack not available in this environment; gates designed to run under `make e2e` with `ORCH_TEST_MODE=1`; `test_retry_prompt_detail.py` fails by name (not timeout) if fake harness is absent

**Residual risks:**
- `with_resolved` null guard absent — consistent with pre-existing pattern in `agent_tail.retry_of()`; deferred
- Whitespace-only prompt passes validator (truthy string); deferred
- Retry-prompt sub-row has no accessibility label; deferred
