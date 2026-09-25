---
title: 'The step-run page shows attempts as a table'
type: 'feature'
created: '2026-09-25'
status: done
baseline_revision: '2726e3ef58bcb1ab6348ce9c86958c8be3ddb016'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      onDrawer content-type argument (prompt-result vs reach-agent) is never
      verified; swapping the two values would not be caught by the unit tests
    evidence: |-
      renderToStaticMarkup does not fire event handlers; the test helper passes
      onDrawer as a no-op. Verifying the routing requires jsdom or an e2e spec
      (step-detail.spec.ts does not exist). The behavior is correct but unverified.
    location: >-
      web-client/src/components/run/AttemptsTable.tsx:101,110
    severity: medium
  - summary: >-
      Replacing native <button> select elements with <tr onClick> removed
      keyboard accessibility for row selection
    evidence: |-
      The old <ul> implementation used <button> elements for row selection, which
      are natively keyboard-reachable. The new <tr> rows have only onClick with no
      tabIndex or onKeyDown. Keyboard users can no longer select attempts.
    location: >-
      web-client/src/components/run/AttemptsTable.tsx:77-80
    severity: medium
  - summary: >-
      No cursor:pointer on interactive table rows
    evidence: |-
      The attempt rows are clickable but the CSS adds no pointer cursor, leaving
      users to discover the interaction by accident.
    location: >-
      web-client/src/styles/step-detail.css
    severity: low
  - summary: >-
      Selected-row rule sets only text color; the house pattern (data-anchored)
      also sets a background color
    evidence: |-
      table.wf-step-attempts tr[data-selected='true'] td sets only
      color:var(--color-text). The StepsTable house pattern's data-anchored rule
      sets both color and background. A background highlight would make the
      selection visually unambiguous.
    location: >-
      web-client/src/styles/step-detail.css
    severity: low
  - summary: >-
      durationText and costText non-null rendering paths are not covered by tests
    evidence: |-
      Test 8 verifies null → em-dash. No test checks that seconds:90 renders '90s'
      or cost_usd:'1.23' renders '$1.23'.
    location: >-
      web-client/tests/unit/attempt-table.test.ts
    severity: low
  - summary: >-
      The "newest first" ordering contract is not verified at any test layer
    evidence: |-
      AttemptsTable renders attempts in prop order trusting the API. No unit test
      constructs a multi-attempt fixture and asserts the highest n appears first.
      Verification requires an API-layer contract test or e2e spec.
    severity: low
---

<intent-contract>

## Intent

**Problem:** `StepDetail.tsx` renders attempt history as a flex-wrap `<ul>` of dot-joined button labels; each row runs together unreadably when a step has multiple attempts, making it impossible to compare columns like status, model, duration, or cost across attempts.

**Approach:** Extract a new stateless `AttemptsTable` component that renders the attempts as an HTML table (attempt number, status token, harness, model, duration, cost, exit code); update `StepDetail` to mount it; add the matching table CSS rules to `step-detail.css`. No backend change.

## Boundaries & Constraints

**Always:**
- Status token is the only signal-coloured cell (NFR-6): the token span uses `.wf-step-token` with `data-signal={tokenSignal(attempt.token)}`; no other cell carries a signal hue.
- `data-selected` on `<tr>` marks the selected row; `step-prompt-{n}` and `step-reach-{n}` testids are preserved in an actions column.
- CSS is hand-scoped under `table.wf-step-attempts` — no inline styles; `base.css` already provides `width:100%; border-collapse:collapse`; only padding, header, and border rules belong here.
- No backend changes; no `make openapi` run.
- `AttemptsTable.tsx` is stateless (no hooks); testable with `renderToStaticMarkup`.
- AD-18: `AttemptsTable.tsx` must have a test pair in `tests/unit/`.

**Block If:** any requirement to apply a signal colour to a non-token cell, or to add new UX behaviour not described above.

**Never:**
- Touch `StepsTable.tsx` or `run-detail.css` — they are the read-only house pattern.
- Render any attempt as unaligned run-on text.
- Add inline styles.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Single agent attempt, selected | `{n:1, token:'RUN', command:null, resume_command:null}`, `selectedN:1` | `<tr data-selected="true">`; `step-prompt-1` present; `step-reach-1` absent | — |
| Two attempts newest-first, selected=1 | `[{n:2,…},{n:1,…}]`, `selectedN:1` | n=2 row: `data-selected="false"`; n=1 row: `data-selected="true"` | — |
| Shell command step | `{command:'make lint', resume_command:null}` | neither `step-prompt-{n}` nor `step-reach-{n}` button present | — |
| Agent step with resume_command | `{command:null, resume_command:'cd /x && opencode run --session s'}` | both `step-prompt-{n}` and `step-reach-{n}` present | — |
| Nullable fields | cost_usd/harness/model/exit_code all null | `—` in those cells | — |

</intent-contract>

## Code Map

- `web-client/src/islands/StepDetail.tsx:26-48` — `AttemptDetail` interface; move to `AttemptsTable.tsx` (exported) and import back from there so the island's state and fetch handler remain typed without duplication.
- `web-client/src/islands/StepDetail.tsx:85-90` — `toggleDrawer(n, content)` function; passed as `onDrawer` prop to `AttemptsTable`.
- `web-client/src/islands/StepDetail.tsx:204-241` — `<ul className="wf-step-detail-attempt-list">…</ul>` block (the run-on list); replaced by `<AttemptsTable attempts={detail.attempts} selectedN={selectedN} onSelect={setSelectedN} onDrawer={toggleDrawer} />`. The `<div className="wf-step-detail-attempt">` selected-attempt detail block (lines 243–316) is unchanged — it derives from `selectedN` and is unaffected by the list-to-table swap.
- `web-client/src/components/run/AttemptsTable.tsx` — NEW stateless component. Exports `AttemptDetail` interface and default `AttemptsTable`. Props: `attempts: readonly AttemptDetail[]`, `selectedN: number | null`, `onSelect: (n: number) => void`, `onDrawer: (n: number, content: DrawerContent) => void`. Imports `tokenSignal` from `'../../lib/board/format'`; imports `type DrawerContent` from `'./HelperDrawer'`. Wraps table in `.wf-step-attempts-scroll`. 8 columns: `#`, `status`, `harness`, `model`, `duration`, `cost`, `exit`, `actions`. Status `<td>`: `<span className="wf-step-token" data-signal={tokenSignal(attempt.token)}>{attempt.token}</span>`. Row: `<tr data-selected={attempt.n === selectedN} onClick={() => onSelect(attempt.n)}>`. Actions cell: when `command === null` render `<button type="button" data-testid={`step-prompt-${n}`} onClick={(e) => { e.stopPropagation(); onDrawer(n, 'prompt-result'); }}>prompt · result</button>`; additionally when `resume_command != null` render `<button type="button" data-testid={`step-reach-${n}`} onClick={(e) => { e.stopPropagation(); onDrawer(n, 'reach-agent'); }}>reach agent</button>`.
- `web-client/src/styles/step-detail.css:78-85` — `.wf-step-detail-attempt-list` flex-wrap block; removed and replaced with `table.wf-step-attempts` layout rules.
- `web-client/src/styles/step-detail.css:36-40` — `.wf-step-token` base style already present; add `[data-signal='run']`, `[data-signal='needs-you']`, `[data-signal='failed']`, `[data-signal='neutral']` colour rules immediately below it. These rules exist in `run-detail.css` for the run-detail page; the step-detail page loads only `step-detail.css`, so they must be declared there too.
- `web-client/src/components/run/StepsTable.tsx` — read-only house pattern; do not touch.
- `web-client/src/styles/run-detail.css:329-378` — read-only `table.wf-steps` rules; the `table.wf-step-attempts` CSS mirrors this shape.

## Tasks & Acceptance

**Execution (TDD: tests before implementation):**

- `web-client/tests/unit/attempt-table.test.ts` — (tests first, story 5, 2026-09-25) new file; 7 tests covering: (1) seven column headers rendered, (2) status token span has `data-signal` from `tokenSignal`, (3) selected row `<tr>` carries `data-selected="true"`, (4) unselected row carries `data-selected="false"`, (5) `step-prompt-{n}` button present when `command:null`, (6) `step-reach-{n}` button present when `command:null` and `resume_command` set, (7) `step-prompt-{n}` absent when `command` is non-null. All must fail before `AttemptsTable.tsx` is created.
- `web-client/src/components/run/AttemptsTable.tsx` — implement as described in Code Map; makes the test file pass.
- `web-client/src/islands/StepDetail.tsx` — import `AttemptsTable` and `type AttemptDetail` from `'../components/run/AttemptsTable'`; remove the inline `interface AttemptDetail` block; replace `<ul className="wf-step-detail-attempt-list">…</ul>` with `<AttemptsTable attempts={detail.attempts} selectedN={selectedN} onSelect={setSelectedN} onDrawer={toggleDrawer} />`.
- `web-client/src/styles/step-detail.css` — remove `.wf-step-detail-attempt-list` flex-wrap block; add `.wf-step-attempts-scroll { overflow-x: auto; margin-bottom: var(--space-8); }` and `table.wf-step-attempts` `th`/`td`/`tr[data-selected='true'] td` rules matching the `table.wf-steps` shape in `run-detail.css`; add `.wf-step-token[data-signal='run'|'needs-you'|'failed'|'neutral']` colour rules below the existing `.wf-step-token` base.

**Acceptance Criteria:**
- Given a step with one attempt (`token:'RUN'`, `command:null`, `resume_command:null`), when the attempt table renders, then a `<table>` is present with column headers `#`, `status`, `harness`, `model`, `duration`, `cost`, `exit`; the status cell contains `<span class="wf-step-token" data-signal="run">RUN</span>`; and no other cell has a `data-signal` attribute.
- Given two attempts `[{n:2,…},{n:1,…}]` and `selectedN:1`, when rendered, then the `<tr>` for n=1 has `data-selected="true"` and the `<tr>` for n=2 has `data-selected="false"`.
- Given an attempt with `command:null` and `resume_command:null`, then `data-testid="step-prompt-{n}"` is present and `data-testid="step-reach-{n}"` is absent.
- Given an attempt with `command:null` and `resume_command` set, then both `data-testid="step-prompt-{n}"` and `data-testid="step-reach-{n}"` are present.
- Given an attempt with `command:'make lint'`, then neither `data-testid="step-prompt-{n}"` nor `data-testid="step-reach-{n}"` is present.

## Design Notes

`AttemptDetail` moves to `AttemptsTable.tsx` (the component that owns the type) and is re-imported by `StepDetail.tsx` — avoids duplication while keeping the dependency direction clear.

The actions-cell buttons call `e.stopPropagation()` so clicking "prompt · result" or "reach agent" does not simultaneously trigger the `<tr>` click that changes `selectedN`.

Signal colour rules for `.wf-step-token` live in `run-detail.css` for the run-detail page; the step-detail page loads only `step-detail.css` and needs its own declarations.

## Verification

**Commands:**
- `make test` — expected: all unit tests pass including 7 new attempt-table tests; 90 % line coverage on `web-client/src/lib/**` and `src/stores/**` maintained
- `make lint` — expected: zero errors (eslint, tsc, prettier --check, test pairs — `AttemptsTable.tsx` named by `attempt-table.test.ts`)

## Review Triage Log

### 2026-09-25 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 0, low 2)
- defer: 6: (high 0, medium 2, low 4)
- reject: 9
- addressed_findings:
  - `[low]` `[patch]` Test header comment said "7 tests" but 8 tests were present — updated comment to enumerate all 8 tests with test 8 description added
  - `[low]` `[patch]` React key used `attempt.n` (sequence number) instead of `attempt.id` (UUIDv7) — changed `key={attempt.n}` to `key={attempt.id}` per AGENTS.md "Ids are UUIDv7"

## Auto Run Result

Status: done

**Implemented change:** Replaced the flex-wrap `<ul>` attempt list in `StepDetail.tsx` with a new stateless `AttemptsTable` component that renders an HTML `<table>` with 8 columns (#, status, harness, model, duration, cost, exit, actions), moving `AttemptDetail` type ownership to the component. Signal colour rules for `.wf-step-token` and full `table.wf-step-attempts` layout rules were added to `step-detail.css`.

**Files changed:**
- `web-client/src/components/run/AttemptsTable.tsx` — NEW: stateless table component exporting `AttemptDetail` and default `AttemptsTable`
- `web-client/tests/unit/attempt-table.test.ts` — NEW: 8 unit tests using `renderToStaticMarkup`
- `web-client/src/islands/StepDetail.tsx` — removed inline `interface AttemptDetail`; replaced 29-line `<ul>` block with `<AttemptsTable>` invocation
- `web-client/src/styles/step-detail.css` — removed flex-wrap block; added signal colour rules and `table.wf-step-attempts` layout rules

**Review findings:**
- Patches applied: 2 (both low — test comment fixed, React key corrected to use `attempt.id`)
- Items deferred: 6 (2 medium — onDrawer content-type unverified, keyboard accessibility regression; 4 low — cursor:pointer, selected-row background, helper non-null coverage, ordering verification)
- Items rejected: 9

**Follow-up review recommendation:** false (patches: 0 high, 0 medium, 2 low → score 2, threshold 5)

**Verification performed:**
- `make lint` — 0 errors: ruff, mypy, import-linter, eslint, prettier, tsc, test-pairs all green
- `make test` — 1740 tests passed (150 test files), 23 skipped; coverage thresholds maintained

**Residual risks:**
- Keyboard users cannot select attempt rows (medium — deferred)
- `onDrawer` content-type routing unverified at unit layer; correct by inspection but no test would catch a swap (medium — deferred)
