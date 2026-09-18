---
title: 'Form tooltips and mandatory marks'
type: 'feature'
created: '2026-09-17'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      No HTML required= attribute on mandatory fields; HTML5 native validation is not engaged
    evidence: |-
      TEMPLATE, PROJECT, REPOSITORY, BASE BRANCH, BUDGET, and template-input fields carry *
      in their label text but no required= attribute on the underlying <input>/<select>. The
      browser will not block submission for empty mandatory fields via native validation. This
      story's scope was title= and label text only; required= is a separate product decision.
    severity: low
  - summary: >-
      No accessible fallback for title= tooltip; screen readers do not reliably surface it
    evidence: |-
      title= is not reliably announced by assistive technology (NVDA, VoiceOver, JAWS).
      No aria-describedby, aria-label, or visible hint element was added. Touch-device users
      also cannot trigger title= tooltips. The change is purely visual (hover/pointer only).
      Adding ARIA fallbacks is an accessibility story beyond this scope.
    severity: low
baseline_revision: '4c3cc15e67e43b515f1224d7e1915b3e52284faf'
---

<intent-contract>

## Intent

**Problem:** The New-workflow form gives no contextual guidance on what each input does or which inputs are required; operators discover constraints only at submit time or by reading external documentation.

**Approach:** Add HTML `title` attributes with factual descriptions to every field's `<label>` or `<fieldset>`, append ` *` to mandatory field label spans, and append ` (optional)` to optional field label spans and the HARNESS legend. No new component, CSS class, or dependency is introduced.

## Boundaries & Constraints

**Always:**
- Every `<label>` wrapping a form input (and the HARNESS `<fieldset>`) carries a non-empty `title` attribute stating why the input matters and what consumes its value (NFR-8: facts and mechanisms, never congratulatory).
- Mandatory fields — template, project, repository, base branch, all template inputs, budget — have ` *` appended to their `<span className="newwf-field-label">` text.
- Optional fields — harness, model, manual estimate — have ` (optional)` appended to their label text (legend for harness, `<span className="newwf-field-label">` for model and manual estimate).
- Budget stays mandatory and carries `*`; the `(optional)` mark for budget arrives with epic 3 story 3-2 — do not add it here.
- The re-review checkbox (`newwf-rereview`) carries a `title` tooltip but no mandatory/optional suffix.
- Template input fields: `tooltip: string` is in `TemplateInputField` interface and populated in `TEMPLATE_INPUT_FIELDS`; the loop renders `title={field.tooltip}` on each `<label>`.
- Anchor tests — `newwf-fields.test.ts`, `newwf-state.test.ts`, `harness-list.test.ts`, `harness-list-probe.test.ts`, `harness-list-readiness.test.ts` — must pass unchanged except the single exception-4 formatting-only edit below.
- TDD: `newwf-fields-tooltips.test.ts` must exist and pass.

**Block If:**
- Any existing anchor test fails after the changes (classify per AGENTS.md before touching anything).

**Never:**
- Introduce a new tooltip component, new CSS class, or visible description element.
- Add `(optional)` to the budget field label in this story.
- Modify any existing test file except the exception-4 formatting fix below.

Exception-4 revision — **AUTHORIZED** (Operator decision 2026-09-17, Prettier compliance — formatting only, no assertion change):
- `web-client/tests/unit/harness-list-readiness.test.ts` — apply `prettier --write` formatting only; no assertion, import, or logic change permitted.

</intent-contract>

## Code Map

- `web-client/src/lib/newwf/state.ts:27-55` — `TemplateInputField` interface has `tooltip: string` (line 30); `TEMPLATE_INPUT_FIELDS` populates `tooltip` for `initiative_folder`, `branch`, `spec_folder` (lines 39, 47, 53)
- `web-client/src/components/NewWorkflowFields.tsx:64-200` — all field `<label>` elements carry `title=`; mandatory spans have ` *`; model and manual-estimate spans have ` (optional)` — implementation complete from commit 7ac5c00
- `web-client/src/components/HarnessList.tsx:54-60` — `<fieldset title="...">` and `<legend>HARNESS (optional)</legend>` — implementation complete from commit 7ac5c00
- `web-client/tests/unit/newwf-fields-tooltips.test.ts` — new test file (163 lines) asserting title= attributes and mandatory/optional marks; uses `renderToStaticMarkup` — complete from commit 7ac5c00
- `web-client/tests/unit/harness-list-readiness.test.ts` — READ-ONLY anchor (story 2-4); exception-4 formatting fix only; `noteText()` helper on line 41 contains a 107-char expression that Prettier reformats; no assertion change

## Tasks & Acceptance

**Execution:**

Remaining task — all other implementation was completed in commit 7ac5c00:

- `web-client/tests/unit/harness-list-readiness.test.ts` — format only — apply `prettier --write` (exception-4, Operator decision 2026-09-17); verify zero assertion or logic change; this resolves the pre-existing `make lint` failure introduced in story 2-4

**Acceptance Criteria:**
- Given the form is rendered with default state, when any mandatory field label is inspected (template, project, repository, base branch, budget), then the label text contains ` *` and the enclosing `<label>` element has a non-empty `title` attribute
- Given the form is rendered, when the model or manual estimate label is inspected, then the label text contains ` (optional)` and the `<label>` has a non-empty `title` attribute
- Given the form is rendered with the initiative template, when the initiative folder input is inspected, then the enclosing `<label>` has a non-empty `title` attribute and the label text contains ` *`
- Given the form is rendered with the epic template, when the branch and spec_folder inputs are inspected, then each enclosing `<label>` has a non-empty `title` attribute and the label text contains ` *`
- Given the HARNESS fieldset is rendered, when inspected, then the legend reads `HARNESS (optional)` and the `<fieldset>` has a non-empty `title` attribute
- Given the re-review checkbox is rendered, when the `<label>` is inspected, then it has a non-empty `title` attribute with no suffix change to the checkbox label text
- Given the budget field is rendered, when inspected, then the label contains ` *` (no `(optional)` — that is story 3-2)
- Given `make lint` runs, then tsc, eslint, prettier, check_test_pairs all pass
- Given `make test` runs, then all unit tests pass including `newwf-fields-tooltips.test.ts` and all existing anchor tests

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 2: (high 0, medium 0, low 2)
- reject: 17
- addressed_findings:
  - none

## Design Notes

**`title` on `<label>` wrapping an `<input>`:** `title` is a global HTML attribute valid on any element. Browsers render it as a hover tooltip. Screen readers surface it as supplemental text for the associated control. No CSS or JavaScript needed.

**`TemplateInputField.tooltip` is a required field in the interface:** all three entries in `TEMPLATE_INPUT_FIELDS` are populated, so TypeScript catches any future omission at compile time.

**Re-review checkbox suffix:** The checkbox label `re-review done stories` reads as a factual description; no mandatory/optional suffix adds information. The `title` attribute carries the explanatory text.

**Exception-4 formatting fix:** `harness-list-readiness.test.ts` was introduced by story 2-4 with a 107-character line (line 41's `noteText` regex) that exceeds `printWidth: 100`. Prettier reformats it; no test logic changes. The operator authorized this on 2026-09-17 as a Prettier compliance fix (exception-4 rule).

## Auto Run Result

**Date:** 2026-09-17
**Status:** done
**Review loop iterations:** 0 (no patch/bad_spec/intent_gap findings)

**Changes delivered (attempt 1, commit 7ac5c00):**
- `web-client/src/lib/newwf/state.ts` — `TemplateInputField` interface gains `tooltip: string`; all three `TEMPLATE_INPUT_FIELDS` entries populated with factual consumer-naming tooltip strings
- `web-client/src/components/NewWorkflowFields.tsx` — all `<label>` elements carry non-empty `title=` attributes; mandatory fields (TEMPLATE, PROJECT, REPOSITORY, BASE BRANCH, BUDGET, template inputs) carry ` *`; optional fields (MODEL, MANUAL ESTIMATE) carry ` (optional)`; re-review checkbox `<label>` gains `title=` with no suffix
- `web-client/src/components/HarnessList.tsx` — `<fieldset title="...">` and `<legend>HARNESS (optional)</legend>`

**Changes delivered (attempt 2, commit 521e4b2):**
- `web-client/tests/unit/harness-list-readiness.test.ts` — Prettier formatting fix only (exception-4, Operator decision 2026-09-17); `noteText()` return wrapped in parentheses to satisfy `printWidth: 100`; no assertion or logic change

**New test files:**
- `web-client/tests/unit/newwf-fields-tooltips.test.ts` — 163 lines asserting tooltip presence, mandatory ` *` marks, optional ` (optional)` marks, and NFR-8 spot-check across all form fields

**Review findings:** 0 patch, 2 deferred (low), 17 rejected. No patches applied.

**Follow-up review score:** 0 patched findings → `followup_review_recommended: false`

**Verification:**
- `make lint` — green: ruff, mypy, import-linter, prettier, tsc, eslint, check_test_pairs, gen:api --check all pass
- `make test` — green: 6345 backend tests (23 skipped), 1382 frontend tests (116 files) — all pass

**Residual risks:**
- Mandatory fields carry ` *` in label text but no `required=` HTML attribute; browser native validation is not engaged (deferred)
- `title=` tooltips are not accessible to touch users or screen readers without mouse hover (deferred)

## Verification

**Commands:**
- `make lint` — expected: prettier, tsc, eslint, check_test_pairs all pass; no formatting violations
- `make test` — expected: all unit tests green including `newwf-fields-tooltips.test.ts`; all anchor tests unchanged
