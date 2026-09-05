---
title: 'New project and edit form with the live Clone check readout'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: ['{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-02-projects/briefs/2-5-project-form-and-clone-check-readout.md']
warnings: ['oversized']
deferred:
  - summary: >-
      A save that fails partway through create or update does not carry forward which
      Project/Repository writes already succeeded, so retrying the same submission re-attempts
      those writes.
    evidence: |-
      `createFlow`/`updateFlow` throw the original, unmutated `draft` on any repository-level
      failure; a retry re-POSTs an already-created repository and, in create mode, re-POSTs the
      already-created Project. The backend's own uniqueness constraints (duplicate name,
      duplicate URL) convert this into a confusing 409 on retry rather than silent duplication,
      but the retry path itself is not clean.
    location: web-client/src/actions/projects.ts
    severity: medium
  - summary: >-
      Three I/O-matrix rows (reserved env var name, invalid glob, duplicate project name) are
      verified only at the Action-unit level, not exercised end-to-end through the real
      rendered form.
    evidence: |-
      `stub-backend.mjs`'s create/update handlers implement no reserved-name, glob, or
      duplicate-name validation, so `project-form.spec.ts` cannot currently drive these
      scenarios through the live DOM; `actions-projects.test.ts` covers the path-remapping
      logic directly against a stubbed 422/409 instead.
    location: web-client/tests/e2e/stub-backend.mjs
    severity: low
  - summary: >-
      The env-var name/value inputs have no associated `<label>`, `aria-describedby`, or
      `aria-invalid`, unlike every other field in the form.
    evidence: |-
      `ProjectForm.tsx`'s env-var row markup relies on `placeholder` text alone for both
      inputs, while every project- and repository-level field uses a proper `<label>`.
    location: web-client/src/islands/ProjectForm.tsx
    severity: low
  - summary: >-
      Editing a still-masked env var row's name without clicking *replace* submits a new name
      with no stored value to keep, which the backend refuses rather than the UI preventing or
      explaining it up front.
    evidence: |-
      The name input stays editable regardless of `masked`/`replacing` state; there is no
      client-side guard or hint for the rename-while-masked case, so the Operator only learns
      of the problem from the backend's "no stored value to keep" refusal.
    location: web-client/src/islands/ProjectForm.tsx
    severity: low
  - summary: >-
      Neither page disables the Save button or shows a pending state while the multi-request
      save sequence is in flight.
    evidence: |-
      `ProjectForm.tsx`'s submit button carries no `disabled`/pending state tied to submission,
      leaving no guard against a double submit on a slow connection.
    location: web-client/src/islands/ProjectForm.tsx
    severity: low
  - summary: >-
      No explicit guard exists for a 2xx backend response that carries neither a usable `data`
      body nor an `error`.
    evidence: |-
      `createFlow`/`updateFlow` already check `error || !project`/`!created`/`!updated` before
      calling `fail`, so this shape is not reachable through today's typed client, but
      `toFailure` itself assumes a `ProblemDetail`-shaped `error` was passed and has no fallback
      of its own if that assumption is ever violated by a future client change.
    location: web-client/src/actions/projects.ts
    severity: low
  - summary: >-
      A fire-and-forget clone-check failure (a thrown exception or an `{error}` response) is
      swallowed with nothing logged, so an infrastructure failure during the save-time check is
      indistinguishable from an ordinary stale/pending readout.
    evidence: |-
      `triggerCloneChecks` catches and discards both failure shapes with no server-side signal
      either way; this mirrors 2.3's own already-accepted "no time budget / no visibility"
      residual risk, now inherited by this Action's own explicit per-repository checks.
    location: web-client/src/actions/projects.ts
    severity: low
baseline_revision: 'ea65c9470d60d8b918ab575e8a1ed3b8caad824c'
---

<intent-contract>

## Intent

**Problem:** There is no way to create or edit a Project: `new.astro`/`[id]/edit.astro` do not exist, so
the Operator cannot register repositories, set env vars, or ever see the Clone check that already runs on
save (2.1-2.3).

**Approach:** Add `ProjectForm`, the repo's first React island (dynamic env-var and repository rows, no
`fetch`, native form post), a `saveProject` Action that orchestrates the per-resource API calls and maps
`ProblemDetail` back onto kept form values, and a `CloneCheckReadout.astro` that renders the stored result
per repository after save.

## Boundaries & Constraints

**Always:**
- Exact fields, copy, test-ids, save flow and readout content as specified in the brief's "Binding rules"
  section (form fields, errors, save flow, readout, signal rule, island rules, test-ids) — reproduced
  there verbatim and not restated here.
- `EnvVarIn.value` omitted means "keep the stored value" (schema-native, no extra flag needed);
  `RepositoryUpdate`/`RepositoryCreate` require only `url` and `default_branch`.
- Every backend `errors[].path` the Action receives is rewritten onto the exact `name` the offending field
  was submitted under (`env_vars[0].name`, `repositories[1].default_branch`) before it reaches the page,
  so one lookup renders every error beside its field with no per-field special-casing (Design Notes).
- The Action explicitly runs `POST /repositories/{id}/clone-check` for every repository it creates or
  updates in this save, in both flows, after that repository's own write and before the final
  `GET /projects/{id}` (Design Notes) — this is what makes the readout show fresh lines rather than
  `pending`/stale ones.
- `client:load`, ≤ 5 props (`initial`, `errors`, `mode`), no `fetch`/`api/server`/`astro:env` import inside
  `src/islands/ProjectForm.tsx` or `src/components/projects/CloneCheckReadout.astro`
  (`web-client/eslint.config.js:18-38`'s `BROWSER_SIDE` rule enforces this).
- Every new `src/**` module is named by some file under `tests/unit/` (`check-test-pairs.mjs`); route
  pages (`new.astro`, `[id]/edit.astro`) are exempt, covered by Playwright instead.
- No pre-existing test file is edited; `tests/e2e/stub-backend.mjs` and `projects-fixtures.mjs` are
  fixtures, not test files (established precedent, story 2.4), and may be extended.

**Block If:** the architecture spine, this brief, and `contracts/openapi.json`/`schema.d.ts` disagree on a
field or route shape (none found during planning).

**Never:** no *Initialise repository* (Epic 4); no removal of an already-added repository or env-var row
— add-only, matching the epic's "no deletion of Projects or Repositories in the MVP UI" non-goal and the
brief naming only `*-add` test-ids, never a remove one; no token/gateway key field; no edit of any frozen
`tests/e2e/{shell,login,no-credential,smoke}.spec.ts` or `tests/unit/{actions,components,component-props}.test.ts`;
no new `zod` dependency (Design Notes).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reserved env var name | a row named `GITHUB_TOKEN` | 422; every value kept, reason beside `env_vars[0].name` | backend reason `instance setting, not a project variable` |
| Invalid glob in a repository row | `test_globs` containing `../x` | 422; every value kept, reason beside that repository's glob field | backend reason: no leading `/`, no `..` segment |
| Duplicate repository URL in one submission | two repository rows share a `url` | 409; `detail` printed verbatim above the form; nothing created | `Conflict` carries no `errors[]` — no field-level path |
| Duplicate project name | edit renames to another stored Project's name | 409; `detail` printed verbatim above the form; nothing changed | as above |
| New repository the token cannot reach | added during create; the Action's explicit `POST .../clone-check` reports `failed` | Project and repository both saved; readout shows the failed lines, verbatim output, hint | mirrors 2.3's "a failing check never fails the save" |
| Env var kept untouched on update | stored `A`; submitted row has `name:"A"` and no `value` field | `PUT` sends `{name:"A"}`; stored ciphertext and mask unchanged | matches 2.1's keep semantics |

</intent-contract>

## Code Map

- `web-client/src/actions/login.ts` (37 lines) -- `defineAction({accept:'form', handler})`, manual `FormData`
  extraction, `ActionError`; no `zod`. `web-client/src/actions/repositories.ts` (40 lines) -- same style,
  calls `backend().POST(...)`, maps `{data,error}` (`error.status`/`error.detail`) to `ActionError` --
  both are the pattern `src/actions/projects.ts::save` must follow (no new dependency; resolves the
  brief's own bracketed `[ASSUMPTION: zod]`).
- `web-client/src/actions/index.ts` (9 lines) -- `export const server = {login, repositories:{recheck}}`;
  add `projects:{save}`.
- `web-client/src/pages/login.astro` (148 lines) -- `Astro.getActionResult(actions.login)`; redirects on
  success (`if (result && !result.error) return Astro.redirect(...)`), else re-renders on the same page
  with `Astro.response.status = 200` and no redirect -- the exact structure `new.astro`/`edit.astro`
  replicate, redirecting to `/projects/{id}/edit?saved=1` on success using the id the Action returns.
- `web-client/src/api/server.ts` (136 lines) -- `backend(): Client<paths>`; every call returns
  `{data, error}`, `error` typed as `ProblemDetail`.
- `web-client/src/api/schema.d.ts` (180-527) -- `ProjectCreate{name, context_text, context_paths?,
  env_vars?: EnvVarCreate[], log_prompt_content?}`; `ProjectUpdate` identical but `env_vars?: EnvVarIn[]`
  (`value` optional = keep); neither carries `repositories`. `RepositoryCreate`/`RepositoryUpdate{url,
  default_branch, package_manager?("uv"|"pnpm"|"npm"|"yarn"|"pip"|"cargo"|"go"|"other"), test_globs?,
  install_command?, quality_gate_command?, unit_test_command?}` -- only `url`/`default_branch` required.
  `RepositoryOut` carries `clone_check{status,at,output,bmad_version}`, `clone_check_lines[{name,status,
  seconds,output}]`, `clone_check_hint`, `verify_skipped`. `ProblemDetail{status,title,detail?,errors?:
  ProblemError[]}`, `ProblemError{path?,reason,...}`.
- `web-client/src/components/CommandBlock.astro` (51 lines) -- `{label, command, testId?}`, reused for the
  readout's verbatim output + hint inset (already used this way by `RepositoriesTable.astro`).
- `web-client/src/components/repository-row.ts` (25 lines) -- precedent for a plain `.ts` module holding a
  shared row shape so a `.ts`/`.tsx` test can import it (`.astro` files expose only a default export).
- `web-client/vitest.config.ts` -- `test.environment: 'node'` (not jsdom/happy-dom): no DOM-mounting
  library is configured, so the island's row-management, hidden-input-name generation, and error-path
  lookup must be exported as plain functions from a sibling `.ts` module and tested directly, not mounted.
- `web-client/eslint.config.js:18-38` -- `BROWSER_SIDE = ['src/islands/**','src/stores/**',
  'src/components/**']`; blocks the `fetch` global and imports matching `astro:env`/`api/server` on those
  globs.
- `web-client/scripts/check-test-pairs.mjs` -- every new `src/**` module needs a `tests/unit/` reference;
  `src/pages/**/*.astro` is exempt.
- `web-client/src/pages/projects/index.astro` (2.4, ~185 lines) -- its `+ New project`/`Edit` links already
  target `/projects/new` and `/projects/{id}/edit`; no change needed. `.../[id].astro` (11 lines) is an
  unrelated sibling redirect; the new `[id]/edit.astro` nested route coexists without conflict.
- `web-client/tests/e2e/stub-backend.mjs` (115 lines) and `projects-fixtures.mjs` (229 lines, 2.4) --
  fixtures, not test files (explicit precedent, story 2.4's own file list); extend with `POST /projects`,
  `PUT /projects/{id}`, `POST /projects/{id}/repositories`, `PUT /repositories/{id}`, and
  `POST /repositories/{id}/clone-check` route handling, mutating the stub's in-memory store; keep
  `GET /api/v1/projects`'s unconditional empty list for the frozen `shell.spec.ts`.
- `web-client/playwright.config.ts:51` -- `fullyParallel: true`; new e2e tests needing mutable stub state
  must use dedicated fixture ids, mirroring 2.4's `RECHECK_REPOSITORY_ID` isolation fix.
- `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md:245` -- the frozen "Form errors"
  convention this story implements verbatim.
- 2.1's `application/use_cases/projects.py` keep/replace/delete `PUT` semantics and 2.2's duplicate-URL
  `Conflict` and glob validation are the exact backend behaviors the matrix rows above exercise; 2.3's
  `run_clone_checks_for_project` fires only from `POST`/`PUT /api/v1/projects/{id}`, never from a
  repository-level `POST`/`PUT` -- the fact Design Notes' clone-check-triggering decision rests on.

## Tasks & Acceptance

**Execution:**
1. `web-client/tests/unit/actions-projects.test.ts` -- failing tests for `save`: create (project, then each
   repo, then an explicit clone-check per repo, then the final read, returning an id), update (existing
   rows `PUT`, new rows `POST`, same clone-check-then-read tail), a 422 on the project payload, a 422 on
   one repository row with its path remapped to `repositories[n].field`, a 409 with no field path -- TDD;
   drives task 2.
2. `web-client/src/actions/projects.ts` -- the `save` Action: manual `FormData` parsing (no `zod`), the
   exact call sequence per mode, path remapping, and a single `ActionError` whose `message` JSON-encodes
   `{draft, detail, errors}` on failure, or the saved project's `id`/`slug` on success.
3. `web-client/src/actions/index.ts` -- register `projects:{save}`.
4. `web-client/tests/unit/project-form-logic.test.ts` -- failing tests for the island's extracted pure
   functions (row add, mask/replace toggle, hidden-input name generation, error lookup by path) -- TDD;
   drives task 5.
5. `web-client/src/islands/project-form-logic.ts` -- those pure functions, importable without a DOM.
6. `web-client/src/islands/ProjectForm.tsx` -- the island: `client:load`, props `{initial, errors, mode}`,
   add-only dynamic env-var/repository rows, mask/`replace` affordance, `log_prompt_content` switch and its
   secondary line, the no-token secondary line, the brief's exact test-ids, hidden inputs so submission is
   a native post to `actions.projects.save`.
7. `web-client/src/components/projects/CloneCheckReadout.astro` -- the per-repository block from
   `RepositoryOut`'s embedded fields, the `missing`/`outdated` extra line, `verify step will be skipped`,
   and the pre-save `save to run the clone check` state; reuses `CommandBlock`.
8. `web-client/src/pages/projects/new.astro` -- `mode="create"`, redirect-on-success /
   re-render-on-failure per the `login.astro` pattern, pre-save readout.
9. `web-client/src/pages/projects/[id]/edit.astro` -- `mode="edit"`, `GET /api/v1/projects/{id}` for
   `initial`, same result handling, live readout from the fetched repositories.
10. `web-client/tests/e2e/projects-fixtures.mjs` -- add any fixtures this story's spec needs (an
    unreachable-URL repository, a repository with no quality command).
11. `web-client/tests/e2e/stub-backend.mjs` -- add the five route families listed in the Code Map.
12. `web-client/tests/e2e/project-form.spec.ts` -- the six acceptance criteria end to end.
13. `pnpm lint && pnpm test && pnpm e2e` inside `web-client/`, then `make lint && make test && make e2e-ui`
    from the root.

**Acceptance Criteria:**
- Given `/projects/new`, when two repositories and one env var are added and saved, then the Project is
  created with both repositories, the page shows the CLONE CHECK readout for each with its four lines, and
  the URL is `/projects/{id}/edit?saved=1`.
- Given a submission with an empty default branch on the second repository, when saved, then the page
  re-renders with every value kept and the reason beside `repo-form-1-default-branch`; nothing is created.
- Given a repository the token cannot reach, when saved, then its readout block shows `ls-remote failed`,
  the verbatim git output, the hint line, and `failed · new runs blocked`; the Project is saved anyway.
- Given the edit page of a Project with a stored env var, when saved without touching it, then the stored
  value is unchanged; after *replace* and a new value it is updated and its mask changes.
- Given a repository without `quality_gate_command`, when saved, then its readout block ends with
  `verify step will be skipped`.
- Given the form, when inspected, then it has no token/gateway key field and shows
  `credentials are instance settings (.env)`.

## Spec Change Log

## Review Triage Log

### 2026-09-05 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 1, medium 5, low 0)
- defer: 7: (high 0, medium 1, low 6)
- reject: 11: (high 0, medium 0, low 11)
- addressed_findings:
  - `[high]` `[patch]` `ProjectForm.tsx` rendered an `errors[]` entry beside only four fields
    (`name`, env-var `name`, repository `url`, `default_branch`); the story's own binding rule
    ("each `errors[]` entry printed beside the field named by its `path`") is unconditional.
    Added the same `reasonFor(...)` lookup and error paragraph beside repository
    `test_globs`, `install_command`, `quality_gate_command`, `unit_test_command`,
    `package_manager`, and env-var `value` — the "Invalid glob" matrix row's backend refusal
    was previously computed correctly but never shown to the Operator.
  - `[medium]` `[patch]` `CloneCheckReadout.astro`'s `clone` line dropped the byte count the
    brief's binding rule names (`` clone (`{bytes} · {seconds}s`) ``); `CloneCheckLineOut` has
    no discrete bytes field, but `line.output` already carries the human-readable count
    (`"cloned N bytes"`/`"fetched"`) per 2.3. The clone line now renders
    `` `(${line.output} · ${line.seconds}s)` `` for both outcomes, not just inside the
    failed-detail block.
  - `[medium]` `[patch]` the readout treated any non-`failed` `clone_check.status` as `ok`,
    including `pending` (reachable for a Repository added outside this story's own explicit
    per-save check, e.g. directly through the API). Added an explicit `pending` branch reading
    `pending · save to check`, reusing the exact copy already shipped by
    `RepositoriesTable.astro` (2.4) for the same state.
  - `[medium]` `[patch]` `triggerCloneChecks` and the final `readProject` call in
    `actions/projects.ts` only tolerated an `{error}`-shaped response, not a thrown exception —
    a network-level failure during either call crashed the whole Action even though the
    Project and Repositories were already saved, violating this file's own stated "a failing
    check never fails the save" invariant. Both call sites now catch a thrown exception the
    same way they already tolerate an `{error}` response.
  - `[medium]` `[patch]` `web-client/tests/e2e/stub-backend.mjs` had two map-key expressions
    built from a literal raw NUL byte (`` `${id}\x00${name}` ``) instead of a safe delimiter,
    which made git treat the whole file as binary — `git diff` on it reported "Binary files
    ... differ" with zero line-level content, hiding every future change to this fixture from
    normal review. Both occurrences now use a plain `::` separator; confirmed independently
    (`grep -naP '\x00'` clean, `git diff --stat` now reports ordinary text-diff line counts).
  - `[medium]` `[patch]` the `log_prompt_content` switch and its Langfuse/source-code
    disclosure line had no test coverage anywhere — neither the checkbox interaction, the
    secondary line's visibility, nor the submitted value reaching the backend payload. Added a
    unit case in `actions-projects.test.ts` asserting the outgoing body carries
    `log_prompt_content: true` when checked, and an e2e step in `project-form.spec.ts`
    asserting the disclosure line appears/disappears with the checkbox and the checked state
    survives a save.

## Design Notes

**Why the Action must trigger its own clone check per repository.** 2.3's `run_clone_checks_for_project`
fires only from `POST`/`PUT /api/v1/projects/{id}`, re-checking whatever is stored *at that moment*. In
create, the Project write commits before any repository exists, so that trigger is a guaranteed no-op —
without an explicit `POST /repositories/{id}/clone-check` after each `POST .../repositories`, every new
repository would read `pending`, failing AC1. In update, an edited repository field is only re-checked by
this story's explicit call regardless of where `PUT /projects/{id}` falls in the sequence; a stray extra
check on an untouched existing repository is harmless (matches 2.3's already-accepted no-time-budget risk).

**Path normalization.** The Action rewrites every backend `errors[].path` onto the exact `name` its field
was submitted under, so one lookup (`errors.find(e => e.path === fieldName)`) renders every error, whether
it came from the single project payload (`env_vars[0].name`) or a synthesized per-row path
(`repositories[1].default_branch`) built from the row index the Action already tracks per call.

**Kept values on error.** Astro's `ActionError` carries no original `FormData`. On any failure the Action
JSON-encodes `{draft, detail, errors}` into `ActionError.message`; the page parses it back out of
`Astro.getActionResult(actions.projects.save)` and passes it as the island's `initial`/`errors` props —
the only way "every value kept" survives the native form's server round trip.

## Verification

**Commands:**
- `cd web-client && pnpm lint && pnpm test && pnpm e2e` -- expected: green, including the two new unit
  suites and `check-test-pairs` for every new module
- `make lint && make test && make e2e-ui` from the repo root -- expected: green, every pre-existing
  Playwright spec unmodified

## Auto Run Result

Status: done

**Implemented change.** The Project create/edit form: `ProjectForm`, the repo's first React
island, with add-only dynamic env-var and repository rows, a mask/*replace* affordance for
stored env vars, and no token field; `src/actions/projects.ts::save`, orchestrating the
per-resource create/update call sequence (including an explicit `POST .../clone-check` per
repository this save touches, since 2.3's own project-level trigger cannot see repositories
that do not exist yet at creation time); `CloneCheckReadout.astro`, rendering the stored
result per repository from `RepositoryOut`; and the two new routes, `projects/new.astro` and
`projects/[id]/edit.astro`, following `login.astro`'s redirect-on-success /
re-render-on-failure pattern.

**Files changed**

- `web-client/src/actions/projects.ts` — new; the `save` Action: manual `FormData` parsing (no
  `zod`), the create/update call sequences, backend `errors[].path` normalization onto each
  field's exact submitted name, and `ActionError.message` JSON-encoding `{draft, detail,
  errors}` so a failed save keeps every value.
- `web-client/src/islands/ProjectForm.tsx` — new; the island, `client:load`, 3 props, every
  field's error rendered beside it (widened in review — see Review Triage Log).
- `web-client/src/islands/project-form-logic.ts` — new; the pure row-management, naming, and
  error-lookup functions behind the island, tested with no DOM per `vitest.config.ts`'s `node`
  environment.
- `web-client/src/components/projects/CloneCheckReadout.astro` — new; the four fixed lines
  read straight off `RepositoryOut`, an explicit `pending` state, and the clone line's byte
  count restored from `line.output` (both fixed in review).
- `web-client/src/pages/projects/new.astro`, `web-client/src/pages/projects/[id]/edit.astro` —
  new; the two routes.
- `web-client/src/styles/project-form.css` — new; token-based styling.
- `web-client/src/actions/index.ts` — registers `projects: { save }` beside `login` and
  `repositories.recheck`.
- `web-client/tests/e2e/projects-fixtures.mjs`, `web-client/tests/e2e/stub-backend.mjs` —
  extended (fixtures, not test files, per story 2.4's own precedent): the five route families
  a real save needs, while leaving the pre-existing `RECHECK_REPOSITORY_ID`-only behavior
  `projects.spec.ts` (2.4) depends on untouched. A literal raw NUL byte the implementation had
  pasted into two of `stub-backend.mjs`'s map-key expressions — which had silently made git
  treat the whole file as binary — was found in review and replaced with a plain `::`
  separator; confirmed independently after the fix (`grep -naP '\x00'` clean,
  `git diff --stat` reports the file as ordinary text again).
- `web-client/tests/unit/{actions-projects,clone-check-readout,project-form-island,
  project-form-logic}.test.ts`, `web-client/tests/e2e/project-form.spec.ts` — new; the TDD
  suites and the six-acceptance-criteria Playwright spec.
- No pre-existing test file, `AGENTS.md`, `SPEC.md`, `stories.yaml`, or `epics.yaml` was
  modified or deleted.

**Review findings.** Four layers (blind hunter, edge-case hunter, verification-gap,
intent-alignment) ran over the full diff, plus a direct byte-level inspection that found the
NUL-byte issue no text-based reviewer could reliably see. 6 patched (1 high, 5 medium), 7
deferred (1 medium, 6 low), 11 rejected. No `intent_gap`, no `bad_spec`: every finding was
either a containable code/test gap or consistent with an already-accepted risk elsewhere in
the codebase, so `review_loop_iteration` stayed at 0.

The high-severity patch is the one worth knowing: `ProjectForm.tsx` rendered a field-level
error beside only 4 of the roughly 10 fields that can receive one — the "Invalid glob" I/O
matrix row's backend refusal was already computed and path-remapped correctly, but the
Operator never saw it, silently violating the story's own "each `errors[]` entry printed
beside the field named by its `path`" rule. Two other patches were correctness bugs the
intent-alignment layer traced to the generated contract lacking a field the brief's prose
assumed existed (`CloneCheckLineOut` has no `bytes` field; the byte count was recovered from
the line's existing `output` text instead) and to a `pending` Repository status silently
reading `ok`. The remaining two patches closed a crash-on-otherwise-successful-save gap
(an uncaught exception, not just an `{error}` response, during the save's own clone-check
calls) and a real, if fixture-only, source-file defect (the NUL bytes).

**Follow-up review recommended: true.** A high-severity patch alone sets this true; the score
is 3 × 5 + 0 = 15, also ≥ 5.

**Verification performed** (all commands re-run after the patches landed, not taken on trust):

| Command | Outcome |
| --- | --- |
| `make lint` (root) | exit 0 — ruff, mypy strict, `lint-imports` (3 contracts kept), env contract (25/31), backend test pairs (38 modules), contract-drift check, full web-client lane (astro check 76 files, eslint, prettier, `check-test-pairs` 29 modules) |
| `make test` (root) | backend **1412 passed, 1 skipped** (pre-existing skip), `domain/`+`application/` 100% branch; web-client **583 passed** |
| `make e2e-ui` (root) | **54 passed**, 0 skipped, against a freshly built stack — every new `project-form.spec.ts` test (7, including the added `log_prompt_content` case) plus every pre-existing spec (`login`, `no-credential`, `projects`, `shell`, `smoke`) unmodified |

Every row of the I/O & Edge-Case Matrix and all six acceptance criteria are covered by a test
that ran and passed; the NUL-byte fix was independently confirmed byte-for-byte
(`python3 -c "...data.count(b'\x00')..."` reports 0) rather than taken on the implementation's
report alone.

**Residual risks.** The 7 items in frontmatter `deferred` (1 medium: a save that fails
partway through create/update does not carry forward which writes already succeeded, so a
retry re-attempts them — caught by the backend's own uniqueness constraints as a confusing
409 rather than silent duplication; 6 low: e2e depth for three validation-error matrix rows,
missing accessible labels on env-var fields, an unguarded rename-while-masked env-var edge
case, no pending/disabled state on Save, a theoretical malformed-2xx-response gap, and no
observability for a swallowed clone-check failure).
