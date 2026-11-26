# Test Automation Summary — orchestrator-initiative-steps / epic-11-initiative-page

Generated: 2026-11-26. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-11-initiative-page/SPEC.md` (relative to the hub).
Stories: 1–6 (through commit `a12b476a`).
Previous summary (epic-10-initiatives-board): in git history.

Framework: Playwright (`web-client/tests/e2e`, the `make e2e-ui` gate). The epic is web-client
only, with no backend or contract change, so no API test is added. The stories already wrote
the smoke spec `initiative-page.spec.ts` (B14), with one or two tests per story. The new file
covers the flows the smoke leaves out. States the stub backend does not serve (a failed turn,
cancelled, done, a refused read) are made by rewriting the stub's detail answer in the browser
with `page.route()`. No existing test file and no stub route was touched, and no shipped
template is read (hard rule 6).

## Generated Tests

### E2E tests — `web-client/tests/e2e/initiative-page-flows.spec.ts` (11 tests)

- [x] CAP-1: the header crumb links to `/initiatives`, `h1` is the slug, the position line reads
  `workflow 1 of 2 · spec · step 3 of 6`, and `NOW` and `aria-pressed` are on the current workflow only.
- [x] CAP-1/CAP-2: selecting a past (`DON`) step removes the message box, and `aria-current="step"`
  stays on the current step.
- [x] CAP-1: `?workflow=2` selects the auto workflow, renders no steps strip, and *Open workflow*
  links to `/workflows/{run id}`.
- [x] CAP-4: *Start now* → confirm posts `POST /initiatives/{id}/start-next` with `{park_seq: 7}`.
- [x] CAP-4: Escape on the cancel modal closes it and sends no cancel request.
- [x] CAP-6: the reopen confirmation posts `{step: 'tech', reason}`, and the reason carries the
  build's stop as the API states it.
- [x] CAP-6: Escape on the reopen modal sends nothing.
- [x] CAP-5: a failed last turn shows the stop banner with its failure reason, and *Restart step*
  posts `POST /runs/{id}/session/retry`.
- [x] CAP-4: a cancelled initiative reads `cancelled at ux`, has no `NOW`, and renders no cancel,
  *Start now* or message box.
- [x] CAP-5: a done initiative reads `done · pull request merged 2026-11-25`, with no cancel and no banner.
- [x] A refused detail read (404) renders the failed-fetch block with its retry, not the page.

## Coverage (epic success criteria, e2e level)

| Capability | Smoke (stories) | This file | Left to unit tests |
| --- | --- | --- | --- |
| CAP-1 header, track, strip, selection, auto summary | track, strip, `aria-current` | crumb, position line, `NOW`, `?workflow=`, Open workflow | tags, meta line, not-started summary |
| CAP-2 conversation | queued line after Ctrl+Enter | read-only past step | attribution, answering line, closed and not-closed lines, `show all` |
| CAP-3 files, sessions | file opens read-only | — | groups, `draft`, changed chip, session rows |
| CAP-4 forced start, cancel | modal copy, Escape, cancel confirm | start-next body, cancel Escape, cancelled state | focus trap |
| CAP-5 stops | merge banner, budget stop | restart → retry, done state | defects block, reopen-on-failed-Run, waiting-for-merge line |
| CAP-6 reopen | reopen confirm | request body, Escape | visibility rules, `BLK` line, fresh-branch line |

UI flows covered end to end: 19 tests (8 smoke and 11 new) out of the 6 capabilities' main flows.
Every capability has at least one e2e flow. Copy variants stay with the vitest unit suites.

## Run

`pnpm build`, then `E2E_PREVIEW_PORT=4391 E2E_STUB_BACKEND_PORT=8798 pnpm exec playwright test
tests/e2e/initiative-page-flows.spec.ts tests/e2e/initiative-page.spec.ts`: 19 passed (3.3 s).
I used other ports so that port 4321 was not touched (hard rule 9). ESLint, Prettier and `tsc`
are clean on the new file. I did not run the full `make e2e-ui` suite or `make e2e`.

## Next Steps

- The lead runs `make e2e` in the disposable `aio-e2e` stack before the pull request (SPEC, Playwright B14).
