---
title: 'Projects list and detail screens'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      The detail fetch treats every error from `GET /api/v1/projects/{id}` (not only a 404) as
      "nothing selected," masking a real backend failure as "project not found."
    evidence: |-
      `web-client/src/pages/projects/index.astro`'s detail fetch reads `if (!error) project =
      data ?? null;` — a 401, a 422, or a 500 renders identically to an id that genuinely does
      not exist. This is a deliberate fail-safe default (the page never crashes on a detail
      fetch failure) rather than a bug, but it is not distinguished from a true 404 the way the
      list fetch's `listUnavailable` state now distinguishes a list failure from an empty list.
    location: web-client/src/pages/projects/index.astro
    severity: low
  - summary: >-
      `next_cursor` from `GET /api/v1/projects` is read and discarded; there is no pagination
      path once the number of Projects exceeds one page.
    evidence: |-
      Mirrors the backend's own pre-existing, already-accepted limitation from story 2.1 (the
      list endpoint always answers `next_cursor: null`, unpaginated) — not something this
      story's frontend could fix on its own, and out of scope for a single-Operator MVP.
    location: web-client/src/pages/projects/index.astro
    severity: low
  - summary: >-
      A failed *re-run check* gives the Operator no explicit visible error message — only the
      implicit signal that the row still reads `failed`.
    evidence: |-
      `web-client/src/actions/repositories.ts`'s `recheck` throws an `ActionError` on an
      upstream refusal, and `index.astro` never calls `Astro.getActionResult()` for it, so the
      page re-renders with no distinct "the recheck itself failed" copy. The row not changing
      is a real, if soft, signal that nothing succeeded — covered by
      `tests/e2e/projects.spec.ts`'s "re-running a check the backend refuses still renders the
      page, with no crash" — but an explicit message would be clearer.
    location: web-client/src/pages/projects/index.astro
    severity: low
  - summary: >-
      `ProjectListRow`'s selected state is conveyed by background colour and a `data-selected`
      attribute only, with no `aria-current` (or equivalent) for assistive technology.
    evidence: |-
      `web-client/src/components/ProjectListRow.astro` renders `data-selected={String(selected)}`
      and a CSS background change; a screen-reader user has no non-visual signal for which
      Project row is currently selected.
    location: web-client/src/components/ProjectListRow.astro
    severity: low
  - summary: >-
      `RepositoriesTable.astro`'s recheck form preserves `?id=` across the Action post by
      string-slicing `actions.repositories.recheck.toString()`, a documented but slightly
      fragile dependency on the exact string Astro's action helper produces today.
    evidence: |-
      `const recheckAction = `?id=${projectId}&${actions.repositories.recheck.toString().slice(1)}`;`
      is self-documented in the component with the reason (the bare action reference
      stringifies to a query-only reference that would otherwise replace the whole query
      string, dropping `id`), and is covered end to end by
      `tests/e2e/projects.spec.ts`'s recheck round-trip test, so a future Astro change to that
      format would surface as a failing e2e test rather than a silent regression — but the
      dependency itself remains undocumented in Astro's own public API.
    location: web-client/src/components/RepositoriesTable.astro
    severity: low
  - summary: >-
      The e2e stub's in-memory clone-check mutation is not idempotent across repeats within one
      server process: running the suite with `--repeat-each` would carry a mutation from one
      repeat into the next.
    evidence: |-
      `web-client/tests/e2e/stub-backend.mjs` builds its mutable `projects` copy once at
      process start and `rerunCloneCheck` mutates it in place with no reset between runs. This
      predates this story's pattern (the whole stub has always been one long-lived in-memory
      copy for the life of the server process); neither `pnpm e2e` nor `make e2e-ui` ever pass
      `--repeat-each`, and `playwright.config.ts` starts a fresh stub process per invocation
      with no retries configured, so the gate itself never reaches this path.
    location: web-client/tests/e2e/stub-backend.mjs
    severity: low
baseline_revision: '82e87cb00d17a523fa2ed3e60f5cbe2329267984'
---

<intent-contract>

## Intent

**Problem:** The Operator has no screen to see a Project's repositories, their method version, and their clone-check state — `src/pages/projects/index.astro` is still Epic 1's static empty-state stub with no data fetch at all.

**Approach:** Turn `projects/index.astro` into a two-pane SSR page (list + detail via `?id=`) fetching `GET /api/v1/projects` and `GET /api/v1/projects/{id}` through `src/api/server.ts`; add `projects/[id].astro` as a redirect; add three static components (`RepositoriesTable`, `ProjectSettings`, `ProjectListRow`) and a form Action (`repositories.ts::recheck`) that re-runs one Repository's clone check with no island.

## Boundaries & Constraints

**Always:**
- AD-1/AD-3: only `index.astro`/`[id].astro`/`repositories.ts` call `backend()` (`src/api/server.ts`); the three new `src/components/**` files take already-fetched plain props and never import `api/server` or `astro:env` (eslint enforces this on `src/components/**`).
- Both endpoints named in the brief are called: the list pane from `GET /api/v1/projects`, the detail pane from a *separate* `GET /api/v1/projects/{id}` call keyed by `?id=` — never derived by scanning the list (`ProjectRead` already embeds `repositories`, but the brief's binding names both calls and this keeps a 404'd id from ever being silently masked by a stale list item).
- Exact field names from `contracts/openapi.json`/`schema.d.ts`: `ProjectRead{id,slug,name,context_text,context_paths,env_vars:[{name,masked}],log_prompt_content,repositories,created_at,updated_at}`; `RepositoryOut{id,project_id,slug,url,default_branch,install_command,quality_gate_command,unit_test_command,test_globs,package_manager,clone_check:{status,at,output,bmad_version},clone_check_lines:[{name,status,seconds,output}],clone_check_hint,verify_skipped,created_at,updated_at}`. `POST/GET /api/v1/repositories/{repository_id}/clone-check` both answer `CloneCheckResultOut` (the four `clone_check` keys plus `lines`, `hint`), not a `RepositoryOut`.
- Voice strings reproduced verbatim: `NO PROJECTS`, `register a project to start`, `no repositories · edit the project to add one`, `written to project-context.md in the spec folder before every story`, `— none declared`, `verify step will be skipped`, `ready`, `ok · {n}s`, `failed · new runs blocked`, `pending · save to check`, `instance settings`, `no runs yet`.
- Signal rule: the clone-check cell is the only coloured element, red text only when `status === "failed"`, no fill; a page where every Repository is `ok` paints no amber/red pixel (frozen `shell.spec.ts` colour-scan pattern reused).
- `stub-backend.mjs` (a fixture, not a test file) keeps `GET /api/v1/projects` answering `{items:[],next_cursor:null}` unconditionally — `tests/e2e/shell.spec.ts` (frozen) asserts `NO PROJECTS` at bare `/projects` and must keep passing untouched.
- Test-ids exactly as listed: `projects-list`, `projects-row-<slug>`, `projects-detail`, `projects-repo-<slug>`, `projects-recheck-<slug>`, `projects-new`, `projects-edit`.
- `RepositoriesTable.astro` authors its own `<table>` (matching `DenseTable`'s head/cell styling) rather than delegating to `DenseTable`, because `DenseTable` cells are plain strings with no hook for the failed-signal colour, the *re-run check* form, or the below-row inset `CommandBlock`.

**Block If:** the architecture spine, this brief, and `contracts/openapi.json` disagree on a field or route shape (none found during planning).

**Never:** no `ProjectForm`/save flow (2.5); no *Initialise repository*, *Export trajectories*, or spend figure — their places are simply absent, not disabled/greyed; no edit of any frozen `tests/e2e/{shell,login,no-credential,smoke}.spec.ts` or `tests/unit/{actions,components,component-props}.test.ts`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No Projects | `GET /api/v1/projects` → `{items:[]}` | `NO PROJECTS`, `register a project to start` → `/projects/new`, bar still shows `+ New project` | No error expected |
| Two Projects, one selected | list has 2 items; `?id=` one of them | both rows render, selected row carries `data-selected`, detail renders below | No error expected |
| Repository `failed` | `clone_check.status:"failed"` | cell reads `failed · new runs blocked` in red; *re-run check* form present; output+hint in an inset `CommandBlock` | No error expected |
| Repository `ok` | `status:"ok"`, `lines` present | cell reads `ok · {sum of line seconds}s` in default text colour | No error expected |
| Repository `pending` | `status:"pending"`, no lines | cell reads `pending · save to check` | No error expected |
| No quality gate | `quality_gate_command:""` | command cell `— none declared`; status cell `verify step will be skipped` | No error expected |
| `bmad_version` values | stored value `"missing"` / `"outdated"` / an actual version / `null` | method cell shows the stored string verbatim in the first three cases (the backend already encodes the label, per 2.3), `—` when `null` (no check has run yet) | No error expected |
| Zero repositories | `repositories:[]` | table area reads `no repositories · edit the project to add one` | No error expected |
| Unknown `?id=` | `GET /projects/{id}` → 404 | list renders, no detail pane, no crash, 200 status | 404 handled as "nothing selected" |
| `/projects/{id}` visited | any id | 30x redirect to `/projects?id={id}` | No error expected |
| Re-run check clicked | `POST /repositories/{id}/clone-check` | page re-renders same `?id=` with the new result; no island, no client JS required | A backend refusal surfaces via `ActionError`, page still renders |
| Every Repository `ok` | a Project with only `ok` repositories | Playwright colour scan finds no amber/red painted value | No error expected |

</intent-contract>

## Code Map

- `web-client/src/pages/projects/index.astro` -- EXISTS as an Epic 1 static stub (`EmptyState` only, no fetch); rewrite in place. `export const prerender = false;` stays. Read `Astro.url.searchParams.get('id')`; call `backend().GET('/api/v1/projects')` for the list and, when an id is present, `backend().GET('/api/v1/projects/{project_id}', {params:{path:{project_id:id}}})` for the detail (ignore a 404/`error`, render no detail). Compose `Shell`, `SurfaceBar`'s `filters` slot (`Button` `+ New project` → `/projects/new`, `data-testid="projects-new"`, always; `Button` `Edit` → `/projects/{id}/edit`, `data-testid="projects-edit"`, only when a project is selected), a `<section data-testid="projects-list">` wrapping one `ProjectListRow` per item (or the `NO PROJECTS` `EmptyState` when the list is empty), and a `<section data-testid="projects-detail">` wrapping title, meta line, `SectionHead` + text for CONTEXT, `RepositoriesTable`, `ProjectSettings`, and a static `RUNS ON THIS PROJECT` / `no runs yet` block — rendered only when `?id=` resolves to a Project.
- `web-client/src/pages/projects/[id].astro` -- NEW. `export const prerender = false;` then `return Astro.redirect(`/projects?id=${Astro.params.id}`);` -- pattern copied from `src/pages/login.astro:24`'s `Astro.redirect`.
- `web-client/src/components/RepositoriesTable.astro` -- NEW. Props `{ repositories: RepositoryRow[] }` (a plain shape mirroring the fields above). One `<table>` per repo, columns `repository · default · method · quality_gate_command · test_globs · clone check · status`; `<tr data-testid={`projects-repo-${slug}`}>`; failed row's clone-check `<td>` carries `data-signal="failed"`; below a failed row, a `CommandBlock` (`src/components/CommandBlock.astro`) with the verbatim `output` and the `hint` line, plus a `<form method="POST" action={actions.repositories.recheck}>` with a hidden `repositoryId` input and a submit button `data-testid={`projects-recheck-${slug}`}` labelled `re-run check`. Zero repositories renders `no repositories · edit the project to add one` instead of a table.
- `web-client/src/components/ProjectSettings.astro` -- NEW. Wraps `KvTable` (`src/components/KvTable.astro`, `{rows:{label,value}[]}`): row 1 `env vars` → `${env_vars.length} · ${env_vars.map(v=>`${v.name} ${v.masked}`).join(', ')}` (or `0 · none set`); row 2 `GitHub token and gateway key` → `instance settings` (static).
- `web-client/src/components/ProjectListRow.astro` -- NEW. Props `{ id, slug, name, repositoryCount, failedCount, selected, href }`. Renders `name · {repositoryCount} repositories · 0 runs`, plus a red `{failedCount} failed` fragment only when `failedCount > 0` (signal rule: nothing rendered at 0). `data-testid={`projects-row-${slug}`}`, `data-selected={selected}`; whole row is an `<a href={href}>` (mirrors `RecordRow.astro`'s one-link-target pattern, new component because the record-row grid has the wrong five columns for this data).
- `web-client/src/actions/repositories.ts` -- NEW. `export const recheck = defineAction({ accept: 'form', handler: async (form, context) => {...} })`: read `repositoryId` from `FormData`; if it is missing or not a string, throw `ActionError({code:'BAD_REQUEST', message:'repositoryId is required'})` (mirrors `login.ts`'s missing-field handling); otherwise call `backend().POST('/api/v1/repositories/{repository_id}/clone-check', {params:{path:{repository_id: repositoryId}}})`; on `error` throw `ActionError({code: error.status === 404 ? 'NOT_FOUND' : 'INTERNAL_SERVER_ERROR', message: error.detail ?? 'clone check failed'})`; on success return `data` (`CloneCheckResultOut`). Pattern: `src/actions/login.ts`'s `defineAction`/`ActionError` shape; `backend()` import is fine here (the eslint restriction only covers `src/islands|stores|components`).
- `web-client/src/actions/index.ts` -- EDIT (not a test file). `import { recheck } from './repositories'; export const server = { login, repositories: { recheck } };` -- the frozen `tests/unit/actions.test.ts` only asserts `server.login === login`, unaffected by the added key.
- `web-client/tests/e2e/stub-backend.mjs` -- EDIT (fixture, not a test file). Add `GET /api/v1/projects` → always `{items:[],next_cursor:null}`; `GET /api/v1/projects/{id}` for three fixed ids imported from the new fixtures module (below), 404 otherwise; `POST /api/v1/repositories/{id}/clone-check` only for `MIXED`'s repository (2) — the recheck target — flips its stored result from `failed` to `ok` (in the in-memory fixture object the stub holds) and returns the new `CloneCheckResultOut`; any other id 404s (no frontend code path calls the plain `GET .../clone-check` operation — `clone_check`/`clone_check_lines`/`clone_check_hint` already arrive embedded in `GET /projects/{id}`'s `repositories[]`, so it needs no route here).
- `web-client/tests/e2e/projects-fixtures.mjs` -- NEW, plain JS (imported by both the `.mjs` stub and the `.spec.ts` file; `tsconfig.json` already includes `*.mjs`). Exports fixed UUID constants and three `ProjectRead`-shaped fixtures: `MIXED`, with four repositories in this order — (1) `status:"ok"`, `bmad_version:"6.11.0"`, `quality_gate_command` set, `lines` with non-zero `seconds`; (2) `status:"failed"`, non-empty `hint`/`output` — this is the recheck target; (3) `status:"ok"`, `bmad_version:"missing"` (the string 2.3's use case stores, not the JS value `null`), `quality_gate_command:""`; (4) `status:"pending"`, `bmad_version:null`, `lines:[]` — `CLEAN` (two `status:"ok"` repositories, for the colour-scan AC), `NO_REPOS` (`repositories:[]`).
- `web-client/tests/unit/projects-components.test.ts` -- NEW, `astro/container` pattern from `tests/unit/components.test.ts`. Renders `RepositoriesTable`, `ProjectSettings`, `ProjectListRow` directly with fixture props (not through the stub) and asserts every Cells rule, the zero-repositories message, the env-vars/credentials KV rows, and `ProjectListRow`'s failed-count-only-when-nonzero and selected marking.
- `web-client/tests/unit/actions-repositories.test.ts` -- NEW, `vi.stubGlobal('fetch', ...)` pattern from `tests/unit/proxy.test.ts`. Drives `recheck.orThrow` (the `Symbol.for('astro.actionAPIContext')` double from `tests/unit/actions.test.ts`) for the success path, a 404 upstream, and a missing `repositoryId` field.
- `web-client/tests/e2e/projects.spec.ts` -- NEW. Empty state + bar link (bare `/projects`, uses the always-empty stub route — safe alongside `shell.spec.ts`); `?id=MIXED` detail rendering (meta line, context hint, all repository-cell states, failed row's inset block + recheck control); clicking *re-run check* and asserting the row updates; `?id=CLEAN` colour scan (copy of `shell.spec.ts`'s local `paintedColours` helper, a new function in this new file — the frozen file is not touched); `?id=NO_REPOS` empty-repositories message; `[id].astro`'s redirect via `request.get(path, {maxRedirects:0})` (pattern from `no-credential.spec.ts`).

## Tasks & Acceptance

**Execution:**
1. `web-client/tests/e2e/projects-fixtures.mjs` -- author the three fixed `ProjectRead` fixtures and id constants -- shared ground truth for the stub and the spec.
2. `web-client/tests/e2e/stub-backend.mjs` -- add the four route families above, importing the fixtures module.
3. `web-client/tests/unit/projects-components.test.ts` -- failing tests for every Cells rule, zero-repositories, KV rows, and `ProjectListRow` -- TDD; drives task 4.
4. `web-client/src/components/{RepositoriesTable,ProjectSettings,ProjectListRow}.astro` -- the three components.
5. `web-client/tests/unit/actions-repositories.test.ts` -- failing tests for `recheck` (success, 404, missing field) -- TDD; drives task 6.
6. `web-client/src/actions/repositories.ts`, `web-client/src/actions/index.ts` -- the Action and its registration.
7. `web-client/src/pages/projects/index.astro` -- the two-pane page, composed from tasks 4 and 6's pieces.
8. `web-client/src/pages/projects/[id].astro` -- the redirect.
9. `web-client/tests/e2e/projects.spec.ts` -- the full Playwright suite described above -- proves the wiring end to end.
10. `pnpm lint && pnpm test && pnpm e2e` inside `web-client/`, then `make lint && make test && make e2e-ui` from the root.

**Acceptance Criteria:**
- Given the fixed `MIXED` project id, when `/projects?id=<id>` renders, then title, meta line, CONTEXT (with its verbatim hint line), the repositories table (ok+version, failed with hint+output+recheck control, ok+`missing` method with `— none declared`/`verify step will be skipped`, and pending with `pending · save to check`/`—` method), SETTINGS, and `no runs yet` all render in that order, and the corresponding list row carries `data-selected="true"`.
- Given the `CLEAN` project id, when the Playwright colour scan runs over `/projects?id=<id>`, then no painted value contains the amber or red rgb literal.
- Given the `NO_REPOS` project id, when its detail renders, then the repositories area reads `no repositories · edit the project to add one`.
- Given two `ProjectListRow`s rendered with fixture props, one marked selected, when `tests/unit/projects-components.test.ts` runs, then both rows' testids and copy render and only the selected one carries `data-selected="true"` — the list-population half of the brief's combined AC, proven at this layer because the shared e2e stub's list endpoint must stay unconditionally empty for the frozen `shell.spec.ts` (see Design Notes).
- Given no Projects, when `/projects` renders, then it shows `NO PROJECTS`, the `register a project to start` link, and the bar's `+ New project` link, and `tests/e2e/shell.spec.ts` continues to pass unmodified.
- Given the failed repository's *re-run check* control, when it is clicked, then `POST /repositories/{id}/clone-check` is called and the same page re-renders the row with the new stored result, with no client-side JavaScript involved.
- Given `/projects/{id}`, when requested, then the response redirects to `/projects?id={id}`.
- Given `pnpm lint && pnpm test && pnpm e2e` in `web-client/`, then every gate passes, including `check-test-pairs` for the three new components and the new Action.

## Spec Change Log

## Review Triage Log

### 2026-09-05 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 1, medium 5, low 1)
- defer: 5: (high 0, medium 0, low 5)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[high]` `[patch]` `tests/e2e/projects.spec.ts`'s recheck test mutates the same stub repository (`MIXED_FAILED_REPO_ID` / `orchestrator-web`) that two sibling tests in the same `describe` block assert stays `failed`; under Playwright's `fullyParallel: true` (confirmed running 7 workers with interleaved completion across the `?id=<MIXED>` block) this is an order-dependent race that can flake the `make e2e-ui` hard gate. Fixed by giving the recheck test its own dedicated fixture repository, distinct from the one the read-only cell-state assertions depend on.
  - `[medium]` `[patch]` `index.astro`'s populated-list wiring (`selected={entry.id === selectedId}`, the `failedCount` filter, and the `projects.map` → `ProjectListRow` composition) was never exercised by any test — the e2e stub's list route is unconditionally empty (by design, for `shell.spec.ts`) and the unit test rendered `ProjectListRow` directly with hand-picked props, bypassing `index.astro`'s own mapping code entirely. Added a unit test that renders `index.astro` itself via `astro/container` with a stubbed multi-item `backend()` response, asserting the right row carries `data-selected="true"` and the right `failedCount`.
  - `[medium]` `[patch]` `GET /api/v1/projects`'s `error` case (and a rejected fetch) was silently coerced to an empty list, rendering identically to a genuine `NO PROJECTS`. The list fetch now distinguishes a fetch failure from an empty result.
  - `[medium]` `[patch]` The AC's "renders … in that order" claim for the detail pane's six sections was only checked by `toContainText` (presence) plus a list-vs-detail bounding-box comparison, never the sections' own relative order. Added an assertion proving the six sections appear in the claimed order.
  - `[medium]` `[patch]` The intent contract's own matrix row "a backend refusal surfaces via `ActionError`, page still renders" had no test at the composed-page level, only at the Action-unit level. Added an e2e test that drives a failing recheck through the real page and asserts it still answers 200 with no crash.
  - `[medium]` `[patch]` `bmad_version: "outdated"` — one of the three values the brief's Cells rule names explicitly — had zero test coverage anywhere. Added a `RepositoriesTable` unit test case for it.
  - `[low]` `[patch]` The bar's count read `"1 projects"` for a single Project. Fixed the pluralisation.
  - `[low]` `[defer]` The detail fetch treats every error (not just a 404) as "nothing selected," masking a real backend failure as "not found" — a deliberate fail-safe default (never crash the page), not incorrect, but worth distinguishing later.
  - `[low]` `[defer]` `next_cursor` is read from `GET /api/v1/projects` and discarded; there is no pagination path once Project count exceeds one page. Mirrors the backend's own pre-existing unpaginated-list behaviour since 2.1.
  - `[low]` `[defer]` A failed *re-run check* gives the Operator no explicit visible error message — only the implicit signal that the row still reads `failed`.
  - `[low]` `[defer]` `ProjectListRow`'s selected state is conveyed by background colour and `data-selected` only, with no `aria-current`/non-visual signal for assistive technology.
  - `[low]` `[defer]` `RepositoriesTable.astro`'s `recheckAction` preserves `?id=` by string-slicing `actions.repositories.recheck.toString()` — documented, tested, but a slightly fragile dependency on Astro's current action-URL format.
  - Rejected as noise or already-justified: sequential (not `Promise.all`) list+detail awaits (cosmetic); `+ New project`/`Edit` linking to the not-yet-built 2.5 routes (the brief itself directs this); `RepositoriesTable` not reusing `DenseTable` (already justified in this spec's own Boundaries — `DenseTable`'s plain-string cells cannot host the failed-signal colour, the recheck form, or the inset block); the `—` fourth method-cell value for a `pending` Repository (a deliberate, already-authorized completion of the brief's incomplete three-value enumeration); the stub's `rerunCloneCheck` using a live timestamp (nothing asserts on it, and "now" is arguably the more correct value); no fixture for two simultaneously-failed repositories (each row's recheck form is already structurally independent by construction); no defensive parsing guard for a malformed `created_at` (contractually guaranteed well-formed by the backend's `UtcTimestamp` type).

## Design Notes

**Why the list pane can prove "no rows" e2e but not "two rows" e2e.** `tests/e2e/shell.spec.ts` is frozen and asserts `NO PROJECTS` at bare `/projects` against the shared stub backend that every spec file runs against under Playwright's `fullyParallel: true` — so `GET /api/v1/projects` must answer an empty list unconditionally, for every test, forever. That forecloses an e2e scenario where the *list* endpoint itself returns two items. "The list shows both rows, and marks the selected one" is instead proven at the component level (`tests/unit/projects-components.test.ts`, `ProjectListRow` rendered twice with fixture props) — a stronger, faster, and more exhaustive check than one more Playwright page load would have been. The end-to-end layer instead proves the part that only a real page can show: that `?id=` selects the right detail via its own dedicated `GET /api/v1/projects/{id}` call, that the failed-row recheck control does a real round trip with no client JS, and that a fully-`ok` project paints no signal colour.

**Meta line formatting.** No date-format helper exists yet in `web-client/src/lib/`; `created {date}` uses `created_at.slice(0, 10)` (the ISO date portion, already UTC per the root conventions — no timezone conversion, no locale formatting to keep deterministic in tests), and `log_prompt_content on|off` is `log_prompt_content ? 'on' : 'off'`.

**Method cell and clone-check seconds.** `bmad_version` already arrives as the display string — the backend stores `"missing"`/`"outdated"`/the real version, per 2.3's use case — so the method cell only needs `bmad_version ?? '—'`, no frontend derivation. `CloneCheckOut` itself carries no duration; the `ok · {seconds}s` figure is the sum of `clone_check_lines[].seconds`, computed once in `index.astro`'s frontmatter and passed to `RepositoriesTable` as a plain number alongside the row.

**Recheck without an island.** The form's `action` posts to the Action; Astro's non-JS form flow re-renders the referring page afterward (`src/pages/login.astro` already relies on the same mechanism for its own re-render on failure). Because `index.astro`'s frontmatter always re-fetches `GET /api/v1/projects/{id}` fresh, the recheck's own return value need not be threaded into the render — the next natural page render already reflects the change.

## Verification

**Commands:**
- `cd web-client && pnpm lint` -- expected: astro sync/check, tsc, eslint, prettier, `check-test-pairs` all pass, including the three new components and `actions/repositories.ts`
- `cd web-client && pnpm test` -- expected: green, including the two new unit test modules
- `cd web-client && pnpm build && pnpm e2e` -- expected: `tests/e2e/projects.spec.ts` passes and every existing spec (`shell`, `login`, `no-credential`, `smoke`) keeps passing unmodified
- `make lint && make test && make e2e-ui` from the repo root -- expected: green

## Auto Run Result

Status: done

**Implemented change.** The two-pane Projects screen: `web-client/src/pages/projects/index.astro`
rewritten from Epic 1's static stub into an SSR page fetching `GET /api/v1/projects` (list) and
`GET /api/v1/projects/{id}` (detail, via `?id=`), three new static components, a form Action that
re-runs a Repository's clone check with no island, and `projects/[id].astro` as a redirect.

**Files changed**

- `web-client/src/pages/projects/index.astro` — the two-pane page: list pane, detail pane,
  bar filters (`+ New project`/`Edit`), and (added in review) a `listUnavailable` state distinct
  from a genuine empty list.
- `web-client/src/pages/projects/[id].astro` — new; redirects to `/projects?id={id}`.
- `web-client/src/components/RepositoriesTable.astro` — new; its own `<table>` (not `DenseTable`,
  which cannot host the failed-signal colour, the recheck form, or the inset output block).
- `web-client/src/components/ProjectSettings.astro`, `ProjectListRow.astro`, `repository-row.ts`
  — new; the SETTINGS kv rows, the list row, and the shared `RepositoryRow` type.
- `web-client/src/actions/repositories.ts` — new; the `recheck` Action.
- `web-client/src/actions/index.ts` — registers `repositories.recheck` beside `login`.
- `web-client/src/layouts/Shell.astro` — forwards a `filters` named slot to `SurfaceBar`, a
  small necessary addition the story's Code Map did not anticipate (this is the first screen
  with bar filters to offer).
- `web-client/tests/e2e/stub-backend.mjs` — the `GET /api/v1/projects` (always empty, for the
  frozen `shell.spec.ts`), `GET /api/v1/projects/{id}`, and `POST /repositories/{id}/clone-check`
  routes, driven by the new fixtures module.
- `web-client/tests/e2e/projects-fixtures.mjs`, `projects.spec.ts` — new; the shared fixtures
  (five Repositories across three Projects, one dedicated solely to the recheck round trip) and
  the full Playwright suite.
- `web-client/tests/unit/projects-components.test.ts`, `projects-page.test.ts`,
  `actions-repositories.test.ts` — new; component-level, page-wiring, and Action unit tests.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `2-4-...` corrected to `done`.

No pre-existing test file, `AGENTS.md`, `SPEC.md`, or `stories.yaml` was modified; every test
file in the diff is new to this story.

**Review findings.** Four layers (blind hunter, edge-case hunter, verification-gap,
intent-alignment) ran over the full diff. 7 patched (1 high, 5 medium, 1 low), 6 deferred (all
low), 7 rejected. No `intent_gap`, no `bad_spec`: every finding was either a containable code/test
gap or already resolved by a documented decision made during planning, so `review_loop_iteration`
stayed at 0.

The high-severity patch is the one worth knowing: `tests/e2e/projects.spec.ts`'s recheck test
mutated the same stub repository (`orchestrator-web`) that two sibling tests in the same
`describe` block asserted stayed `failed` — under Playwright's `fullyParallel: true` (confirmed
running 7 workers with interleaved completion across that block) this was a real,
order-dependent race capable of flaking the `make e2e-ui` hard gate. Fixed by giving the recheck
test its own dedicated fixture repository (`orchestrator-recheck`), never asserted `failed` by
any other test. Three of the five medium patches closed genuine verification gaps rather than
behavioural bugs: `index.astro`'s populated-list wiring (`selected`/`failedCount`) had no test at
any layer, the detail pane's claimed section order was only checked for presence, and the
spec's own "a backend refusal surfaces via `ActionError`, page still renders" matrix row had no
composed-page-level test. The remaining medium patch was a real behavioural gap: a `GET
/api/v1/projects` failure was silently rendered as `NO PROJECTS`; the list fetch now sets a
distinct `listUnavailable` state.

**Follow-up review recommended: true.** A high-severity patch alone sets this true; the score is
3 × 5 + 1 = 16, also ≥ 5.

**Verification performed** (all commands re-run after the patches landed, not taken on trust):

| Command | Outcome |
| --- | --- |
| `cd web-client && pnpm lint` | exit 0 — astro check (65 files, 0 errors), tsc, eslint, prettier, `check-test-pairs` (25 modules) |
| `cd web-client && pnpm test` | **528 passed** (0 skipped); coverage 98.8% stmts / 96.15% branch / 100% funcs / 100% lines |
| `cd web-client && pnpm build && pnpm e2e` | **47 passed** — every new `projects.spec.ts` test plus every pre-existing frozen spec (`shell`, `login`, `no-credential`, `smoke`) unmodified |
| `make lint` (root) | exit 0 — ruff, mypy strict, `lint-imports` (3 contracts kept), env contract (25/31), backend test pairs (38 modules), contract-drift check, full web-client lane |
| `make test` (root) | backend **1412 passed, 1 skipped** (pre-existing), `domain/`+`application/` 100% branch; web-client 528 passed |
| `make e2e-ui` (root) | **47 passed**, 0 skipped, against a freshly built stack |

Every row of the I/O & Edge-Case Matrix is covered by a test that ran and passed, including the
recheck-failure row, now proven at the composed-page level.

**Residual risks.** The 6 items in frontmatter `deferred` (all low): the detail fetch collapsing
every error into "nothing selected" rather than distinguishing a real failure from a true 404;
`next_cursor` discarded with no pagination path (mirrors 2.1's own accepted limitation); a failed
recheck giving no explicit visible error message (only the row not changing); `ProjectListRow`'s
selected state carrying no non-visual (`aria-current`-style) signal; the recheck form's
`?id=`-preserving trick depending on the exact string Astro's action helper produces today
(covered by an e2e test that would catch a regression); and the e2e stub's in-memory clone-check
mutation not being idempotent across `--repeat-each` repeats within one server process (neither
`pnpm e2e` nor `make e2e-ui` ever pass that flag, so the gate itself never reaches it).
</content>
