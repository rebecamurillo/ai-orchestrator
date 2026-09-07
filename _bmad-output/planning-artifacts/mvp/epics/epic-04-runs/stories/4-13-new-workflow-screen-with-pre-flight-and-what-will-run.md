---
title: 'New workflow screen with pre-flight and What will run'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: '888b02f56c781cabc546e0df20267121fe75e627'
context: []
warnings: []
deferred:
  - summary: >-
      `new.astro` discards `next_cursor` from `GET /templates` and `GET /projects`, so a
      Project past the first page never appears in the New Workflow dropdowns.
    evidence: |-
      Both reads take `data.items` and ignore `data.next_cursor`. For Templates this is now
      covered for the three root names, which are resolved individually by name; for
      Projects there is no such fallback beyond the one `?project=` names, so an instance
      with more Projects than one page cannot select the later ones from this screen. The
      same pattern is already present in `src/pages/templates/[name]/[version].astro`, so
      this is a codebase-wide read-model gap rather than something this story introduced —
      but the New Workflow screen is the first place it blocks an action rather than
      narrowing a display.
    location: 'web-client/src/pages/workflows/new.astro'
    severity: medium
  - summary: >-
      The four-key prefill query contract (`template`, `project`, `repository`, `branch`)
      plus the `in_{key}` template-input encoding is defined only inside
      `src/lib/newwf/query.ts`, with no consumer yet.
    evidence: |-
      The brief names the four top-level keys for "start a new run" links but no encoding
      for a Template's own inputs; `in_{key}` is this story's invention, chosen because
      `epic`'s own `branch` input would otherwise collide with the base-branch key. No other
      screen builds such a link today, so nothing pins it. Whichever story first renders a
      "start a new run" link should import `formStateToQuery` rather than re-deriving the
      shape.
    location: 'web-client/src/lib/newwf/query.ts'
    severity: medium
---

<intent-contract>

## Intent

**Problem:** `/workflows/new` was a permanent `EmptyState` placeholder; the Operator had no
screen to bind a Template's inputs, watch pre-flight re-run on every change, read the whole
plan, and start a Run (SPEC CAP-13, UX-DR8).

**Approach:** Build the `NewWorkflow` island (`client:load`) plus its `new.astro` host: a
form for the three shipped root Templates (`initiative`, `epic`, `repo-init`), a debounced
`POST /runs/preflight` on load and every change, a *What will run* plan table, a harness
list, and *Start run* → `POST /runs`. Consume the three already-shipped endpoints
(`GET /templates`, `GET /projects`, `GET /harnesses`) and pre-flight/create verbatim; add no
route, widen no endpoint.

## Boundaries & Constraints

**Always:** Copy states facts and mechanisms, never congratulates (PRD NFR-8). `skipped` and
`unvalidated` are plain words, never green. Only a `fail` line's `x` word is red. The URL
carries the full form state as query parameters so a reload restores it. The island's logic
lives in `src/lib/newwf/{state,query}.ts`, unit-tested without rendering; `PreflightLines.tsx`
and `PlanTable.tsx` are small, stateless, presentational components. Props ≤ 5, serialisable.

**Block If:** Landing this story would require editing `SPEC.md`, `stories.yaml`,
`epics.yaml`, any `AGENTS.md`, or an existing test file outside the three narrow declared
exceptions (root `AGENTS.md` hard rule 1) — HALT `blocked` with the exact conflict.

**Never:** Add, widen, or reshape a backend-api route. Re-derive the pre-flight or planner
rules client-side. Enable a harness (Epic 5's job). Read another story's brief.

</intent-contract>

## Code Map

- `web-client/src/pages/workflows/new.astro` — the page; SSR-loads `GET /templates`,
  `GET /projects`, `GET /harnesses` together (best effort), then completes the three-name
  root-Template set through `GET /templates/{name}/versions` and resolves a deep-linked
  Project through `GET /projects/{project_id}`. The completion step is gated on the list read
  already carrying a Template or a link naming one, so a bare visit against an instance whose
  list is empty still renders the same `EmptyState` (`newwf-empty` / `NO TEMPLATE TO BIND`)
  the frozen `tests/e2e/shell.spec.ts` measures. A separate `newwf-unavailable` readout
  distinguishes "could not be read" from "nothing is stored" (NFR-8).
- `web-client/src/islands/NewWorkflow.tsx` — the island (216 lines); `TemplateEditor.tsx`'s
  `requestSeqRef` staleness-guard pattern applied to pre-flight, its own debounce (400 ms)
  copied from the same file, plus a `pending` gate that keeps *Start run* off a stale
  authorisation.
- `web-client/src/lib/newwf/state.ts`, `query.ts` — pure form-state, URL round-trip, and the
  `reconcileInitial` that reconciles a link's values against what actually loaded.
- `web-client/src/components/{PreflightLines,PlanTable,HarnessList,NewWorkflowFields}.tsx` —
  presentational, `renderToStaticMarkup`-testable (the `Diagram.tsx` precedent). The last two
  exist so every file stays inside `web-client/AGENTS.md`'s "a component file ≤ 300 lines".
- `web-client/tests/e2e/stub-backend.mjs` — additive `GET /api/v1/harnesses` (brand new
  route, no frozen constraint); `POST /runs/preflight` and `POST /runs` are deliberately not
  stubbed — `new-workflow.spec.ts` mocks both with `page.route()` (the
  `template-diagram.spec.ts` precedent), since there is no engine here to walk a real plan.
- `web-client/tests/e2e/templates-fixtures.mjs` — additive `initiative` and `repo-init`
  entries in `TEMPLATES`, mirroring 3.6's own `epic` addition, so
  `GET /templates/{name}/versions` answers for all three root Templates.
- `web-client/tests/e2e/new-workflow.spec.ts` — every interacting test opens through an
  `openForm` helper that waits for the `client:load` island to hydrate; without it a
  `selectOption` is written straight back by React's controlled `value`.
- `backend-api/src/orchestrator/api/schemas/{preflight,runs,harnesses,templates,projects}.py`
  — read-only: the exact response/request shapes consumed (`PreflightIn`/`Out`, `RunIn`,
  `CreateRunOut`, `HarnessOut`, `TemplateSummaryOut`, `ProjectRead`/`RepositoryOut`).

## Tasks & Acceptance

**Execution:**
- `web-client/src/lib/newwf/state.ts` -- fixed Template enum/inputs, form-state transitions,
  request-body builders, line-word/harness-line formatting -- keeps the island free of
  business logic so it unit-tests without a DOM
- `web-client/src/lib/newwf/query.ts` -- URL query round-trip, `in_{key}`-prefixed template
  inputs to avoid the `branch` (base) / `branch` (epic's own working branch) collision --
  UX-DR8's "a reload restores it"
- `web-client/src/components/PreflightLines.tsx`, `PlanTable.tsx` -- stateless rendering of
  `lines[]` and `rows[]`/`plan_error` -- reusable, DOM-free unit coverage
- `web-client/src/islands/NewWorkflow.tsx` -- the form, debounced pre-flight, harness list,
  decision bar, Start run -- the screen itself
- `web-client/src/pages/workflows/new.astro` -- SSR data load + EmptyState gate -- keeps the
  frozen empty-state reading of a bare visit true unchanged
- `web-client/tests/unit/{newwf-state,newwf-query,newwf-island,preflight-lines,plan-table}.test.ts`
  -- unit coverage for every module above
- `web-client/tests/e2e/new-workflow.spec.ts` -- the interactive form in a real browser
- `web-client/tests/e2e/stub-backend.mjs`, `templates-fixtures.mjs` -- additive fixtures the
  new spec needs

**Acceptance Criteria:** the six Given/When/Then scenarios in
`_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-13-new-workflow-screen.md`,
verbatim.

## Spec Change Log

## Review Triage Log

### 2026-09-07 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1 (low)
- defer: 0
- reject: 0
- addressed_findings:
  - `[low]` `[patch]` `new.astro`'s deep-link resolve for `?template=` did not check the
    value against the fixed three-name enum before calling
    `GET /templates/{name}/versions` — a value naming a real but non-selectable Template
    (e.g. `story`, which exists as its own shipped root file) would resolve and merge into
    the SSR `templates` list even though the island's own dropdown can never show or select
    it. Guarded with `isTemplateName(templateParam)` before the resolve; re-ran
    `astro check`, the full `pnpm lint`, a rebuild, and `new-workflow.spec.ts` +
    `shell.spec.ts` (24/24 passed) to confirm no regression.

Review performed directly by the primary agent against the four review-layer questions
(missing/wrong, edge cases, verification gaps, intent alignment) rather than via the
skill's parallel subagent layer: this session's `Agent` tool launches every subagent
asynchronously, with its completion notification arriving as a separate later turn: the
operator's own explicit, overriding instruction for this dispatch is to work synchronously
and never end the turn with work uncommitted or a subagent still in flight, on pain of
repeating the exact stall an earlier agent in this epic caused. One `blind-hunter` subagent
was launched before this was recognised (`aa9f0a018`, general-purpose, model opus); its
findings landed after the first commit and are triaged in the second pass below.

### 2026-09-07 — Review pass (blind-hunter findings)
- intent_gap: 0
- bad_spec: 0
- patch: 12 (high 3, medium 6, low 3)
- defer: 2 (medium 2)
- reject: 9
- addressed_findings:
  - `[high]` `[patch]` The `re-run readiness` link was rendered as inert trailing text.
    The brief's Scope keeps the *link* in ("here the link points to it and shows
    `not available yet` if 404") and puts only the wiring out. Now a real anchor at
    `/api/harnesses/{name}/readiness` with the note beside it, in `HarnessList.tsx`. The
    note is stated rather than probed: the route is absent from `contracts/openapi.json`,
    so `src/api/client.ts` has no method for it and `eslint.config.js` forbids the raw
    `fetch` that a probe would need (AD-1) — a route the contract does not carry is one
    this build provably does not serve.
  - `[high]` `[patch]` The Template dropdown offered all three root names while only the
    deep-linked one had a resolvable `latest_version`, so switching to another left
    `template_version: null` in pre-flight and made *Start run* unable to build a body at
    all. `new.astro` now completes the three-name set through
    `GET /templates/{name}/versions`. Gated on the list read already carrying a Template or
    a link naming one, so a bare visit still renders the frozen `NO TEMPLATE TO BIND`.
  - `[high]` `[patch]` *Start run* could silently do nothing: `runBody()` returning `null`
    hit a bare `return`. It now states the reason in `newwf-start-error`.
  - `[medium]` `[patch]` A pre-flight that failed wiped the column to blank. It now renders
    `pre-flight could not be read from backend-api` (NFR-8).
  - `[medium]` `[patch]` `state.harness` survived a switch to `repo-init`, whose form hides
    the harness list, and was still posted. `withTemplate` clears it.
  - `[medium]` `[patch]` `?harness=` could check a disabled harness and post it, against the
    brief's "a disabled harness is not selectable". New `reconcileInitial` drops it.
  - `[medium]` `[patch]` *Start run* stayed live against a stale pre-flight during the
    debounce and the request behind it. A `pending` gate now disables it; its own race —
    an in-flight response clearing `pending` while a newer debounce was already queued —
    is closed by checking `timerRef.current` in the same guard.
  - `[medium]` `[patch]` A deep-linked repository belonging to another Project displayed as
    `—` while its id stayed in state and would have been posted. `reconcileInitial` drops it.
  - `[medium]` `[patch]` A link naming a repository but no branch opened with BASE BRANCH
    empty, so nothing could start. `reconcileInitial` seeds it from `default_branch`.
  - `[low]` `[patch]` `gateCell` rendered a dangling `skipped · ` when `reason` was null.
  - `[low]` `[patch]` `PreflightLines` keyed rows on the free-form `check` alone; now
    `${check}-${index}`. `checkSlug` folds every non-alphanumeric run to a dash, so
    `SPEC.md` gives `spec-md` rather than an id carrying a dot.
  - `[low]` `[patch]` Stub/fixture accuracy: harness `version_pin`s now match
    `.env.example` (`2.1.258`/`0.152.1`/`1.18.26`), the comment names the real constant
    `HARNESS_VERSION_SETTINGS`, and the fixture prose fragment is fixed.
  - `[medium]` `[patch]` `NewWorkflow.tsx` was 324 lines, over `web-client/AGENTS.md`'s
    "a component file ≤ 300 lines". Split into `NewWorkflowFields.tsx` (173) and
    `HarnessList.tsx` (78); the island is now 216.
  - `[medium]` `[patch]` Accessibility and layout: the radio group is a
    `<fieldset>`/`<legend>` rather than an unnamed `<div>`; both right-column sections
    carry headings; the plan table scrolls inside its own container; the dead `newwf` and
    `newwf-preflight-row` hooks are gone.
  - `[medium]` `[patch]` Test gaps closed — the reviewer was right that the suite proved
    too little. Added: the `queue_note` rendered verbatim, the `Cancel` href, the body
    actually posted to `/runs` (`template_version` and `inputs` asserted), switching to a
    non-deep-linked template still resolving its version, *Start run* on an incomplete form,
    the readiness link and its note, the pre-flight failure readout, `plan_error` in a
    browser, the base-branch default, a foreign repository being dropped, and the 400 ms
    debounce coalescing a burst into one call. Unit suites added for `HarnessList` and
    `NewWorkflowFields`. Web-client unit tests 778 → 803; `e2e-ui` 82 → 92.
  - `[high]` `[patch]` Fixing the above exposed a hydration race the original suite had
    hidden: `selectOption` before the `client:load` island hydrated was written straight
    back by React's controlled `value`, so the swapped-in template inputs never appeared
    and the test hung to its 30 s timeout — reproducible roughly one full-suite run in two.
    Every interacting test now opens through an `openForm` helper that waits for the island
    to be live. Four consecutive full `e2e-ui` runs clean at 5.2 s (from 31 s on a failing run).

Rejected as design disagreements the brief itself settles: driving the form from each
Template's API-served `inputs:` declarations (the brief enumerates the fields verbatim, and
`TEMPLATE_INPUT_FIELDS` is that enumeration); defaulting `harness` to `claude` per the
shipped YAML (every harness is seeded disabled, so that would select an unselectable one);
posting `/runs` through an Astro Action (the brief's island rule is "calls `client.ts`
only"); client-side enforcement of required template inputs (pre-flight is the authority and
answers a `fail` line); and re-seeding the base branch on every repository change (kept as
the documented seed-when-empty reading).

## Design Notes

**Why the bare-list-forced-empty constraint didn't need a workaround.** `GET /templates` and
`GET /projects` answer unconditionally empty in the shared `make e2e-ui` stub, protecting the
frozen `shell.spec.ts`'s "NO TEMPLATE TO BIND" reading of bare `/workflows/new`
(2.4/3.5 Design Notes; `templates/[name]/[version].astro`'s own module doc states the same
constraint for its cross-Template rows). Rather than special-casing test-only behaviour into
production code, `new.astro` treats a deep-linked Template/Project name from the brief's own
prefill query parameters (`?template=&project=&repository=&branch=`) as reason to resolve
that one entity through an already-existing, non-list route
(`GET /templates/{name}/versions`, `GET /projects/{project_id}`) and fold it into what
renders — the same shape `templates/[name]/[version].astro` and `projects/[id].astro`
already use. A bare visit carries none of these parameters, so this resolution never runs,
and the frozen assertion is unaffected. `tests/e2e/new-workflow.spec.ts` therefore opens with
`?template=initiative&project=<MIXED_ID>` throughout, mirroring exactly how a real
"start a new run" link would land.

**Template dropdown is a fixed three-name enum, not list-driven.** The brief's own binding
rule ("template (`initiative` latest pre-selected; `epic`, `repo-init`; never `story`)") names
a closed set — the only three root Templates this epic ships. `TEMPLATE_ORDER` in `state.ts`
is that fixed enum; the `templates` prop is consulted only to resolve `latest_version` for
whichever name is selected. This keeps template-switching (AC1) testable purely client-side,
independent of how much of the SSR-loaded `templates` list happens to be populated.

**Harness selection is real but inert in this epic.** All three harnesses are seeded
`enabled: false` and nothing before Epic 5 flips one; `harness` is optional on both
`PreflightIn` and `RunIn`. The harness list renders each line and its (always-disabled) radio
control per the brief; no scenario in this story can select one, matching the operator's own
"design the harness list for the disabled case being normal, not exceptional."

**`queue_note` is rendered verbatim**, per the binding rule, with no client-side formula —
`checks.queue_note`'s three possible sentences (free / behind a name / global concurrency)
are backend-api's own words.

**Base branch defaults once, then holds whatever the Operator has.** The brief says "base
branch (default: repository default branch)" without saying whether that default re-applies
on every repository change or only seeds an empty field. `NewWorkflow.tsx`'s repository
`onChange` only fills `baseBranch` when it is still empty, so a later repository switch never
clobbers a value the Operator already typed or edited. Defensible but unpinned, in 4.3's own
sense — the alternative (always re-seeding from the newly selected repository) is equally
readable from the brief and would need the same amount of code to write.

## Verification

**Commands:**
- `make lint` -- ruff/mypy/import-linter/eslint/prettier/tsc/env-contract, all clean; 0
  drift in `pnpm gen:api --check`
- `make test` -- backend 4056 passed/23 skipped, 100% domain+application coverage;
  web-client 803 passed, `src/lib/newwf/**` 100% lines
- `make openapi` -- `contracts/openapi.json` and `schema.d.ts` byte-identical (no route
  touched)
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- 144 passed, 34 subtests passed
- `make e2e-ui` -- 92 passed, including 17 in `new-workflow.spec.ts`; the frozen
  `shell.spec.ts`'s 17 tests pass unchanged, `/workflows/new` still `NO TEMPLATE TO BIND` at
  a bare visit. Run four consecutive times clean after the hydration-race fix (5.2 s each);
  before it, roughly one run in two hung a test to its 30 s timeout.

## Auto Run Result

**Summary:** Built the real `/workflows/new` screen (`NewWorkflow.tsx` + `new.astro`): the
template-dependent form, debounced pre-flight on load and every change, the harness list,
*What will run*, and *Start run* with the queue note — consuming `GET /templates`,
`GET /projects`, `GET /harnesses`, `POST /runs/preflight`, `POST /runs` exactly as shipped,
adding no route.

**Files changed:**
- `web-client/src/pages/workflows/new.astro` -- rewritten: SSR data load + deep-link resolve
  + EmptyState gate, replacing the story-1/2-era permanent placeholder
- `web-client/src/islands/NewWorkflow.tsx` -- new: the form, pre-flight, harness list,
  decision bar, Start run
- `web-client/src/lib/newwf/state.ts`, `query.ts` -- new: pure form-state and URL logic
- `web-client/src/components/PreflightLines.tsx`, `PlanTable.tsx` -- new: presentational
  sub-components
- `web-client/src/styles/new-workflow.css` -- new: token-only styling for the screen
- `web-client/tests/unit/{newwf-state,newwf-query,newwf-island,preflight-lines,plan-table}.test.ts`
  -- new: unit coverage (100% lines on `src/lib/newwf/**`)
- `web-client/tests/e2e/new-workflow.spec.ts` -- new: the six brief ACs, in a real browser
- `web-client/tests/e2e/stub-backend.mjs` -- additive: `GET /api/v1/harnesses`
- `web-client/tests/e2e/templates-fixtures.mjs` -- additive: `initiative`, `repo-init`
  fixture entries (mirrors 3.6's own `epic` addition)

**Review findings breakdown:** two passes. Pass 1: 1 patch (low). Pass 2, from the
blind-hunter layer: 12 patches applied (high 3, medium 6, low 3), 2 deferred (medium), 9
rejected as design disagreements the brief itself settles. See the Review Triage Log.

**Follow-up review recommendation:** `true` — pass 2 patched three high-severity findings.

**Verification performed:** see `## Verification` above; every command re-run after the one
patch, all green. `make openapi` confirms zero contract drift (no route touched).

**Residual risks:**
- The four-parameter query-string prefill contract (`template`, `project`, `repository`,
  `branch`) and the `in_{key}`-prefixed template-input encoding are this story's own
  invention (the brief names the four top-level keys but not an encoding for template
  inputs); 4.14-4.16 do not read `/workflows/new`'s URL, so this is not a cross-story
  contract, but a future story that *does* build "start a new run" links should read
  `src/lib/newwf/query.ts` rather than re-deriving the query shape.
- The `blind-hunter` findings arrived after the first commit and were triaged and patched in
  a second pass (commit below). Nine of its findings were rejected as design disagreements
  the brief settles; two were deferred to frontmatter. No further review layer has run over
  the second pass's own diff, which is why `followup_review_recommended` is `true`.
