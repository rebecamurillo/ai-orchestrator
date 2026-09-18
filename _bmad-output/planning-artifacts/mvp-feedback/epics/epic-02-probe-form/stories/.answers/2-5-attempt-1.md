---
title: 'Form tooltips and mandatory marks'
type: 'feature'
created: '2026-09-17'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
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
- The re-review checkbox (`newwf-rereview`) carries a `title` tooltip but no mandatory/optional suffix — a boolean toggle's optionality is self-evident.
- Template input fields: add `tooltip: string` to `TemplateInputField` interface and populate it in `TEMPLATE_INPUT_FIELDS`; the loop renders `title={field.tooltip}` on each `<label>`. This is a purely additive change; `newwf-state.test.ts` tests function behaviour, not the constant's shape.
- Anchor tests — `newwf-fields.test.ts`, `newwf-state.test.ts`, `harness-list.test.ts`, `harness-list-probe.test.ts`, `harness-list-readiness.test.ts` — must pass unchanged. Verified safe: no anchor assertion pins exact label text, title attributes, or legend text beyond `toContain('HARNESS')` (which `HARNESS (optional)` still satisfies).
- TDD: new test file exists and fails before implementation.

**Block If:**
- Any existing anchor test fails after the changes — classify before touching anything (AGENTS.md: classify as (a) or report blocked).

**Never:**
- Introduce a new tooltip component, new CSS class, or visible description element.
- Add `(optional)` to the budget field label in this story.
- Modify any existing test file.

</intent-contract>

## Code Map

- `web-client/src/lib/newwf/state.ts:27-40` — `TemplateInputField` interface (line 27) and `TEMPLATE_INPUT_FIELDS` constant (line 33); add `tooltip: string` to interface; populate for `initiative_folder`, `branch`, `spec_folder`
- `web-client/src/components/NewWorkflowFields.tsx:62-204` — all field `<label>` elements; add `title=` to each, append ` *` or ` (optional)` to each `<span className="newwf-field-label">`; template-input loop uses `field.tooltip` and appends ` *`
- `web-client/src/components/HarnessList.tsx:57-58` — `<fieldset>` and `<legend>HARNESS</legend>`; add `title=` to `<fieldset>`; change legend text to `HARNESS (optional)`
- `web-client/tests/unit/newwf-fields.test.ts` — READ-ONLY anchor; asserts test IDs, placeholder, `required` attr, template options — none affected by `title` or label text additions
- `web-client/tests/unit/harness-list.test.ts:54-60` — READ-ONLY anchor; `toContain('HARNESS')` — satisfied by `HARNESS (optional)`; no exact-match assertion on legend text
- `web-client/tests/unit/newwf-state.test.ts` — READ-ONLY anchor; tests `withTemplate`, `withInput`, etc., not `TEMPLATE_INPUT_FIELDS` shape

## Tasks & Acceptance

**Execution:**

Tests first — must exist and fail before implementation:

- `web-client/tests/unit/newwf-fields-tooltips.test.ts` — create — using `renderToStaticMarkup` (same pattern as `newwf-fields.test.ts`), assert:
  - Template `<label>` contains ` *` and `title=` with non-empty value
  - Project `<label>` contains ` *` and `title=` with non-empty value
  - Repository `<label>` contains ` *` and `title=` with non-empty value
  - Base branch `<label>` contains ` *` and `title=` with non-empty value
  - Budget `<label>` contains ` *` and `title=` with non-empty value
  - Model `<label>` contains ` (optional)` and `title=` with non-empty value
  - Manual estimate `<label>` contains ` (optional)` and `title=` with non-empty value
  - Initiative template: `<label>` for `newwf-input-initiative_folder` contains ` *` and `title=`
  - Epic template (use `withTemplate(defaultFormState(), 'epic')`): labels for `newwf-input-branch` and `newwf-input-spec_folder` each contain ` *` and `title=`
  - Re-review `<label>` (containing `newwf-rereview`) has `title=` with non-empty value
  - For the HARNESS section: render `HarnessList` with `renderToStaticMarkup`; assert markup contains `HARNESS (optional)` and `<fieldset` with `title=` attribute
  - Spot-check: no `title` value contains the word "please" or "successfully" (NFR-8)

Implementation (all after test exists and fails):

- `web-client/src/lib/newwf/state.ts` — add `tooltip: string` to `TemplateInputField` interface; set tooltip strings in `TEMPLATE_INPUT_FIELDS`:
  - `initiative_folder`: `"Path in the repository where planning output lands. Passed to the template as initiative_folder."`
  - `branch`: `"Branch the harness creates and pushes story commits to. Passed to the template as branch."`
  - `spec_folder`: `"Path holding the epic's stories.yaml and story spec files. Passed to the template as spec_folder."`

- `web-client/src/components/NewWorkflowFields.tsx` — add `title=` to each `<label>` and marks to each `<span className="newwf-field-label">`:
  - TEMPLATE: title `"Selects which BMAD workflow the Run executes. Controls the step sequence and which inputs the form shows."`, label `TEMPLATE *`
  - PROJECT: title `"Billing and authorisation scope for the Run. Limits the repository list."`, label `PROJECT *`
  - REPOSITORY: title `"Target repository. The harness checks it out for every Run."`, label `REPOSITORY *`
  - BASE BRANCH: title `"The branch the harness starts from when creating per-story working branches."`, label `BASE BRANCH *`
  - Template-input loop: `title={field.tooltip}` on `<label>`; label span text `{field.label} *`
  - MODEL: title `"LLM model the harness calls. Blank uses the harness default; the list shows only what the live probe returned."`, label `MODEL (optional)`
  - BUDGET: title `"Maximum LLM spend in USD for this Run. The Run enters needs_you when this limit is reached."`, label `BUDGET (USD) *`
  - Re-review: title `"Adds a review pass after each story the harness marks done. Increases run time."` on the `<label>`; no suffix change to the checkbox span text
  - MANUAL ESTIMATE: title `"Hours estimate recorded in the run report. Has no effect on execution."`, label `MANUAL ESTIMATE (H) (optional)`

- `web-client/src/components/HarnessList.tsx` — add `title="Coding-agent that executes the story steps. Probed live on selection and again at submit."` to the `<fieldset>` element; change `<legend>HARNESS</legend>` to `<legend>HARNESS (optional)</legend>`

**Acceptance Criteria:**
- Given the form is rendered with default state, when any mandatory field label is inspected (template, project, repository, base branch, budget), then the label text contains ` *` and the enclosing `<label>` element has a non-empty `title` attribute
- Given the form is rendered, when the model or manual estimate label is inspected, then the label text contains ` (optional)` and the `<label>` has a non-empty `title` attribute
- Given the form is rendered with the initiative template, when the initiative folder input is inspected, then the enclosing `<label>` has a non-empty `title` attribute and the label text contains ` *`
- Given the form is rendered with the epic template, when the branch and spec_folder inputs are inspected, then each enclosing `<label>` has a non-empty `title` attribute and the label text contains ` *`
- Given the HARNESS fieldset is rendered, when inspected, then the legend reads `HARNESS (optional)` and the `<fieldset>` has a non-empty `title` attribute
- Given the re-review checkbox is rendered, when the `<label>` is inspected, then it has a non-empty `title` attribute with no suffix change to the checkbox label text
- Given the budget field is rendered, when inspected, then the label contains ` *` (no `(optional)` — that is story 3-2)
- Given `make lint` runs, then tsc, eslint, prettier, check_test_pairs all pass (TemplateInputField extended with required `tooltip` field — all entries populated, no type error)
- Given `make test` runs, then all unit tests pass including `newwf-fields-tooltips.test.ts` and all existing anchor tests

## Design Notes

**`title` on `<label>` wrapping an `<input>`:** `title` is a global HTML attribute valid on any element. Browsers render it as a hover tooltip. Screen readers surface it as supplemental text for the associated control. No CSS or JavaScript needed.

**`TemplateInputField.tooltip` is a required field in the interface:** all three entries in `TEMPLATE_INPUT_FIELDS` are populated, so no runtime fallback needed. TypeScript will catch any future entry that omits `tooltip` at compile time.

**Re-review checkbox suffix:** The checkbox label `re-review done stories` already reads as a factual description of what it does; it is not a mandatory or optional field in the same sense (it is always present and always optional). A suffix would not add information. The `title` attribute carries the explanatory text.

## Verification

**Commands:**
- `make lint` -- expected: tsc, eslint, prettier, check_test_pairs all pass; no type errors from `TemplateInputField` extension
- `make test` -- expected: all unit tests green including new `newwf-fields-tooltips.test.ts`; all anchor tests unchanged

## Auto Run Result

Status: blocked
Blocking condition: implementation verification failed

`make lint` fails with a Prettier formatting violation in `web-client/tests/unit/harness-list-readiness.test.ts`:

```
[warn] tests/unit/harness-list-readiness.test.ts
[warn] Code style issues found in the above file. Run Prettier with --write to fix.
```

This file is a read-only anchor introduced by story 2-4 (commit `4c3cc15`). The failure pre-dates story 2-5 — `git log` confirms this file was last changed in `4c3cc15`, the baseline revision. Editing it to fix the formatting would violate AGENTS.md.

Story 2-5's implementation is otherwise complete: all 1382 unit tests pass (116 test files), tsc/eslint/prettier pass on all changed files, and all anchor tests pass unchanged.

Operator action required: either authorize a formatting-only fix to `web-client/tests/unit/harness-list-readiness.test.ts` (exception-4, Prettier compliance — no assertion change), or accept the pre-existing lint failure as a defect from story 2-4.

## Human Answer

2026-09-17T07:26:22.494664Z · operator

YES authorize a formatting-only fix to `web-client/tests/unit/harness-list-readiness.test.ts`
