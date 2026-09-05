---
title: 'Templates screen with versions list, editor, validate, and save'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      The CodeMirror mount has no max-height/overflow, so a very large Template YAML would
      grow the whole page rather than scrolling inside the editor pane.
    evidence: |-
      `web-client/src/styles/template-editor.css`'s `.template-editor-mount` sets no
      max-height; none of the four shipped Templates are large enough to expose this today.
    location: 'web-client/src/styles/template-editor.css'
    severity: low
  - summary: >-
      `yamlKeyField`/`yamlStepHighlightField` rebuild decorations by re-scanning the whole
      document on every keystroke or selection move, with no incremental update.
    evidence: |-
      `web-client/src/lib/editor/yamlEditor.ts`'s `buildMarkDecorations`/`buildStepDecorations`
      always call `text.split('\n')` over the full document; fine at shipped-Template scale,
      a likely cost at large scale with no test at that scale to catch a regression.
    location: 'web-client/src/lib/editor/yamlEditor.ts'
    severity: low
  - summary: >-
      Neither the CodeMirror mount nor the readout/error list is marked up for screen-reader
      announcement of async Validate/Save outcomes.
    evidence: |-
      No `aria-live` region and no `aria-label` on `.template-editor-mount`; no accessibility
      requirement is stated in this story's brief or in `web-client/AGENTS.md`'s binding rules.
    location: 'web-client/src/islands/TemplateEditor.tsx'
    severity: low
  - summary: >-
      The e2e stub's `validateYamlText` only recognises block-style `- id:` steps, so a
      flow-style step (`- { id: x, gate: y }`) would be invisible to its reserved-key and
      ungated-step checks.
    evidence: |-
      `web-client/tests/e2e/stub-backend.mjs`'s own comment calls this a stand-in for the real
      backend validator; none of the shipped Templates (`repo-init`, `story`, `epic`,
      `initiative`) use flow style, so this affects test-infrastructure fidelity only, never
      production behaviour (the real validator already exists in backend-api).
    location: 'web-client/tests/e2e/stub-backend.mjs'
    severity: low
baseline_revision: '7571ea7c57ac1422ddb4d65a20af1d5c8cc51347'
---

<intent-contract>

## Intent

**Problem:** The `/templates` route is a hardcoded empty-state stub. The Operator cannot read, edit, validate, or version a Template YAML from the browser.

**Approach:** `index.astro` redirects to the first Template's latest version (or renders empty/unavailable). `[name]/[version].astro` renders VERSIONS/YAML/DIAGRAM+INPUTS columns with one `TemplateEditor` React island (`client:load`) doing CodeMirror 6 editing, Validate, and Save-as-vN+1.

## Boundaries & Constraints

**Always:** Use only `src/api/client.ts` in the island, `src/api/server.ts` in pages (AD-1). Exact test-ids from the brief. `pinned_by` always renders "pinned by 0 runs". Save rewrites the top-level `version:` line to n+1 client-side before POSTing; editor displays stored YAML unchanged otherwise. A failed list/detail fetch renders a distinct `*-UNAVAILABLE`-style `EmptyState`, never an empty list (precedent: `src/pages/projects/index.astro`). Add `@codemirror/state`, `@codemirror/view`, `@codemirror/lang-yaml` to `package.json`/lockfile (absent today). Render validator `reason` strings verbatim.

**Block If:** none identified — brief is unambiguous on scope and copy.

**Never:** Do not render the diagram (3.6) — `templates-diagram` shows the literal placeholder line `diagram arrives with the next story`. Do not touch any anchor: `tests/e2e/shell.spec.ts`, `tests/e2e/login.spec.ts`, `tests/unit/middleware.test.ts`, `tests/unit/components.test.ts` (all already reference `templates`/`nav-templates`/`templates-empty` — read-only). Extend `tests/e2e/stub-backend.mjs` additively only (new route branches), never edit its existing branches.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bare `/templates`, list empty | `GET /api/v1/templates` → `{items:[]}` | 200, `EmptyState testId="templates-empty" headline="NO TEMPLATES"` | matches frozen `shell.spec.ts` |
| Bare `/templates`, list fetch fails | error/throw | 200, `EmptyState testId="templates-list-error" headline="TEMPLATES UNAVAILABLE"` | never an empty list |
| Bare `/templates`, list non-empty | items present | 302 → `/templates/{first by name}/{latest_version}` | — |
| Detail fetch fails | `GET /templates/{name}/{version}` errors | distinct unavailable readout, no crash | — |
| Validate, invalid YAML | `parallel: 2` added, `gate` removed | bar `1 errors` (red), `templates-errors` lists `line {n} · parallel is reserved`, plus `unvalidated · {path}`; text untouched | reason rendered verbatim |
| Save, valid YAML | Save clicked | `POST /templates/{name}/versions` 201 → browser navigates `/templates/{name}/{n+1}` | — |
| Save, invalid YAML | 422 from backend | errors printed under editor, text kept | never a 500-style crash |

</intent-contract>

## Code Map

- `web-client/src/pages/templates/index.astro` — replace stub: fetch `GET /api/v1/templates`, redirect/empty/unavailable.
- `web-client/src/pages/templates/[name]/[version].astro` — new detail page; fetches version detail (`server.ts`), this-name's versions (`/templates/{name}/versions`), and (best-effort) the summary list for cross-Template rows.
- `web-client/src/lib/templates/index-logic.ts` (new) — pure `selectRedirectTarget(items)`; paired unit test.
- `web-client/src/lib/editor/yamlEditor.ts` (new) — `rewriteVersionLine`, `findStepRange`, `accentRanges`, CodeMirror extension builder.
- `web-client/src/islands/TemplateEditor.tsx` (new) — props `{name, version, yaml, inputs, errorsInitial}`; owns Validate/Save via `api` from `client.ts`, debounced 800ms auto-validate.
- `web-client/src/components/templates/VersionsList.astro`, `InputsTable.astro` (new) — static, fixture-testable (precedent: `tests/unit/projects-components.test.ts` / `ProjectListRow`).
- `web-client/src/styles/template-editor.css` (new, tokens only).
- `web-client/tests/e2e/stub-backend.mjs` — additive routes for the four templates endpoints.
- `web-client/tests/e2e/templates-fixtures.mjs` (new).
- `web-client/tests/e2e/templates.spec.ts`, `tests/unit/{templates-index-logic,yaml-editor,template-editor-island,templates-components}.test.ts` (new).
- `web-client/package.json`, `pnpm-lock.yaml` — add CodeMirror deps.

## Tasks & Acceptance

**Execution:**
- Write failing unit tests for `index-logic.ts`, `yamlEditor.ts` helpers, then implement.
- Write failing `templates.spec.ts` (stub+fixtures first), then implement pages/island/components.
- Wire `pnpm add @codemirror/state @codemirror/view @codemirror/lang-yaml`.

**Acceptance Criteria:** the five Given/When/Then in the brief, plus: given the shared e2e stub forces `GET /api/v1/templates` empty (parity with frozen `shell.spec.ts`), when `/templates/{name}/{version}` renders, then the current Template's own versions (via `/templates/{name}/versions`) still populate correctly end-to-end, and cross-Template rows are proven at the component layer (`VersionsList.astro` with fixture props), not e2e.

## Design Notes

`GET /api/v1/templates` must answer `{items:[]}` unconditionally in the stub (same reasoning `stub-backend.mjs` documents for `/api/v1/projects`): `shell.spec.ts` is frozen and asserts `NO TEMPLATES` at bare `/templates` against this shared, `fullyParallel` stub. This makes the cross-Template "every version of every Template" panel untestable end-to-end; `/templates/{name}/versions` (a different path, unconstrained) is used instead for the *current* Template's own version rows, which is what AC3 ("shows v1 and v2") needs and can prove live. The full multi-Template panel is proven via `VersionsList.astro` rendered directly with fixture props (precedent: `projects-components.test.ts`'s `ProjectListRow`, doc'd the same way in `projects.spec.ts`).

Save rewrite: `rewriteVersionLine(yamlText, n+1)` replaces the anchored `^version:\s*\d+` line only (never a nested key).

## Verification

**Commands:**
- `make lint` -- 0
- `make test` -- 0 (unit, both components)
- `make e2e-ui` -- 0 (existing + new `templates.spec.ts`)

### 2026-09-06 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 14 (high 1, medium 7, low 6)
- defer: 4 (low 4)
- reject: 4
- addressed_findings:
  - `[high]` `[patch]` Save failure that carries no `errors[]` (e.g. 404/500) rendered the readout as "valid" — fixed to always show a failure state on any Save error.
  - `[medium]` `[patch]` No try/catch around the island's own `api.POST` calls in `validate()`/`save()` — a thrown network error left `saving` stuck `true` forever with no feedback.
  - `[medium]` `[patch]` No sequencing guard between a manual Validate click and the 800ms debounce, and the Validate button stayed enabled while a request was in flight.
  - `[medium]` `[patch]` Detail-page header count used the merged cross-Template row total instead of the current Template's own version count.
  - `[medium]` `[patch]` `ownVersions` could omit the currently loaded version if the versions-list fetch succeeded without it, dropping that row from the panel.
  - `[medium]` `[patch]` `templates/index.astro`'s real redirect-on-non-empty-list branch and its `TEMPLATES UNAVAILABLE` branch were unexercised by any test (mirrors `projects-page.test.ts` precedent) — added `templates-page.test.ts`.
  - `[medium]` `[patch]` `buildVersionRows`'s cross-Template merge precedence was unexercised with non-empty data at any layer — moved to a lib module and unit-tested directly.
  - `[medium]` `[patch]` The brief's required "editing as v{n+1}" banner line was missing from the implementation entirely — added, verbatim.
  - `[low]` `[patch]` `save()` did not cancel its pending debounce timer, risking a stale Validate clobbering Save's just-set error state.
  - `[low]` `[patch]` Template name was not URL-encoded when building the redirect target, VersionsList row hrefs, and post-save navigation.
  - `[low]` `[patch]` `save()`'s success path read `data.version` without confirming `data` was present.
  - `[low]` `[patch]` `inputs` prop on `TemplateEditor` was accepted but never read — documented as intentional (InputsTable renders it independently; kept for prop-shape parity with the brief).
  - `[low]` `[patch]` `errorRows`/`readoutTime` had no direct unit test, unlike the sibling pure helpers in `yamlEditor.ts`.
  - `[low]` `[patch]` No test for a malformed `version` URL segment (e.g. `/templates/demo/abc`).

## Auto Run Result

**Summary of implemented change:** Bare `/templates` now redirects to the latest version of the first Template by name (or renders a distinct `NO TEMPLATES` / `TEMPLATES UNAVAILABLE` state). `/templates/{name}/{version}` renders the VERSIONS / YAML / DIAGRAM+INPUTS three-column layout, with one `TemplateEditor` React island (CodeMirror 6, `client:load`) doing Validate (on click and 800ms debounce), Save-as-v{n+1} (client-side version-line rewrite before POST), a line-numbered error/unvalidated list, key/`uses:`/`run:` syntax colouring, cursor-scoped step highlighting, and the `editing as v{n+1}` banner. `templates-diagram` renders the literal placeholder line for story 3.6.

**Files changed** (relative to `web-client/` unless noted):
- `src/pages/templates/index.astro` — replaced the empty-state stub with the redirect/empty/unavailable page.
- `src/pages/templates/[name]/[version].astro` — new detail page; three best-effort/required backend reads, assembles the VERSIONS panel via `buildVersionRows`.
- `src/lib/templates/index-logic.ts` — pure `selectRedirectTarget`.
- `src/lib/templates/version-rows.ts` — pure `buildVersionRows` (extracted during review so it is unit-testable with non-empty cross-Template data).
- `src/lib/editor/yamlEditor.ts` — `rewriteVersionLine`, `findStepRange`, `keyRanges`, `accentRanges`, CodeMirror extension/state builders.
- `src/islands/TemplateEditor.tsx` — the one island; Validate/Save, request-sequencing guard, try/catch with a generic-failure fallback, `errorsFromProblem` (never masks a failed Save as valid), the version banner.
- `src/components/templates/VersionsList.astro`, `InputsTable.astro`, `version-row.ts` — static, fixture-testable components.
- `src/styles/template-editor.css` — tokens only.
- `tests/e2e/stub-backend.mjs` — additive routes for the four `/templates` endpoint families (verified: no existing branch touched).
- `tests/e2e/templates-fixtures.mjs`, `tests/e2e/templates.spec.ts` — fixtures and the 7-scenario e2e suite.
- `tests/unit/templates-index-logic.test.ts`, `yaml-editor.test.ts`, `template-editor-island.test.ts`, `templates-components.test.ts`, `templates-page.test.ts`, `version-rows.test.ts` — unit coverage.
- `package.json`, `pnpm-lock.yaml` — added `@codemirror/state@6.7.2`, `@codemirror/view@6.43.10`, `@codemirror/lang-yaml@6.1.3`.

**Review findings breakdown:** 14 patch (1 high, 7 medium, 6 low) — all fixed and re-verified green; 4 defer (all low: CodeMirror mount scroll cap, full-document decoration rebuild cost, no `aria-live` on async state, stub validator's block-style-only step detection); 4 reject (the brief's own literal "1 errors" grammar; loose numeric coercion of the version segment, which already degrades safely to the unavailable state; the readout correctly counting only `errors[]` per the brief's own worked AC2 example, not `unvalidated[]`; an `InputDeclOut.default` shape the generated contract makes type-impossible).

**Follow-up review recommendation:** `true`. One patched finding was `high` severity (Save failure masked as "valid"), which alone triggers it; the score (`3×7 medium + 1×6 low = 27`) confirms it independently.

**Verification performed (this pass, on the current tree, by the orchestrating session — not taken on the subagent's word):**
- `make lint` -- exit 0 (ruff, mypy, import-linter, env-contract, `gen:api --check`, astro check, tsc, eslint, prettier, check-test-pairs all clean).
- `make test` -- exit 0. Backend: 2128 passed, 1 skipped; `domain`/`application` 100% branch coverage. Web-client: 652 passed (29 files); `src/lib/templates/{index-logic,version-rows}.ts` confirmed at 100% line coverage via `coverage/coverage-summary.json` (the printed text table omits fully-covered files under a partially-covered parent's siblings, which is a reporter display quirk, not a gap).
- `make e2e-ui` -- exit 0. 61/61 Playwright tests, including the frozen `shell.spec.ts` (bare `/templates` still renders `templates-empty`/`NO TEMPLATES`) and all 7 `templates.spec.ts` scenarios. (The host's `ai-orchestrator-web-client-1` docker container was briefly stopped to free port 4321 for the gate's own preview server, then restarted afterward.)
- Matrix Test Audit: all 7 I/O & Edge-Case Matrix rows are covered by a test that ran and passed in the above (bare-empty and bare-unavailable and bare-redirect by `templates-page.test.ts`; detail-fetch-fails by `templates.spec.ts`'s unknown-Template and malformed-version-segment tests; Validate/Save valid/invalid by `templates.spec.ts`).

**Residual risks:** the four deferred items above (all low severity, none blocking); the cross-Template half of "every version of every Template" (AC1) is real in production but is proven only at the component/unit layer, never end-to-end, because the frozen `shell.spec.ts` requires the shared e2e stub's `GET /api/v1/templates` to stay unconditionally empty — this is a structural test-environment constraint documented in Design Notes, not a code defect.
