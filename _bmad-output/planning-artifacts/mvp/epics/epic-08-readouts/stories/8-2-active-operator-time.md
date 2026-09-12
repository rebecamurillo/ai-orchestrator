---
title: 'Active Operator time'
type: 'feature'
created: '2026-09-11'
status: 'done'
baseline_revision: '30a6072458e09a23a9944a7b23afb15a5745139b'
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      context frontmatter is empty despite two prior attempts with relevant commits
    evidence: |-
      Commits 985943f, c1890fd, and f8cf9d8 are prior attempts on this story; their
      outcomes explain why attempt 3 looks the way it does, but context: [] offers no
      traceability. Future readers cannot determine what was tried and abandoned.
    severity: low
  - summary: >-
      I/O matrix missing unknown-run_id scenario despite use case documenting NotFound
    evidence: |-
      Code Map notes "raises NotFound for unknown id" in activity.py but the matrix
      has no row for it. The 422 behavior on out-of-range inputs is covered; the 404
      on an unknown run is not.
    location: >-
      _bmad-output/planning-artifacts/mvp/epics/epic-08-readouts/stories/8-2-active-operator-time.md
    severity: low
  - summary: >-
      I/O matrix "6 idle minutes" row does not specify when the POST fires
    evidence: |-
      The row says "only 5 min counted before POST" but does not state whether the
      POST fires at the 5-minute mark or only at the next 60-second batch boundary
      after the idle timeout. A reader cannot determine the exact trigger.
    location: >-
      _bmad-output/planning-artifacts/mvp/epics/epic-08-readouts/stories/8-2-active-operator-time.md
    severity: low
---

<intent-contract>

## Intent

**Problem:** The Run detail has no way to record how long the Operator actually spent reading it; the cost block is missing a `your active time` figure, and `run.active_seconds` is never incremented from the client.

**Approach:** All layers are already implemented in prior attempts (commits `985943f` and `c1890fd`). The sole remaining task is fixing a latent bug in an existing test — `test_bearer_auth.py` line 276 always reads `["get"]` for every method, which crashes when a POST-only path is encountered. The operator has authorized fixing it (blocking condition answer). One character change: `["get"]` → `[_method]`.

## Boundaries & Constraints

**Always:**
- `active_seconds` is the only Run field written by this story's endpoint; status has exactly two writers (AD-8).
- `POST /runs/{id}/activity {focused_seconds: int (1..3600)}` → 200 `{active_seconds}` or 422.
- The activity endpoint is allowed for any Run status.
- The label in the cost block is exactly `your active time`.
- Client batches every 60 s and flushes on `pagehide`; idle gaps > 5 min excluded.
- `schema.d.ts` is not hand-edited (AD-3); `ActivityIn`/`ActivityOut` types flow from `make openapi && pnpm gen:api`.

**Block If:**
- `run.active_seconds` column is absent from the database (confirmed present; no migration needed — `active_seconds` exists from story 4.1).

**Never:**
- Per-day breakdown; any second writer of Run status.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|-----------------|----------------|
| Two sequential POSTs | `focused_seconds: 45` twice | `active_seconds: 90`; cost block reads `00:01:30` | — |
| Out-of-range: zero | `focused_seconds: 0` | 422 | Problem JSON |
| Out-of-range: over max | `focused_seconds: 5000` | 422 | Problem JSON |
| 60 s with activity | focused tab, fake timer advances 60 s | one POST `focused_seconds: 60`; store resets | — |
| 6 idle minutes | activity then 6 min idle | only 5 min counted before POST | — |
| Tab hidden | `document.visibilityState === 'hidden'` | no tick increments; remainder flushed on `pagehide` | — |

</intent-contract>

## Code Map

All files are already implemented and committed.

- `backend-api/src/orchestrator/api/routers/run_activity.py` — POST `/runs/{run_id}/activity`; `ActivityIn` (ge=1, le=3600) → `record_activity` → `ActivityOut`
- `backend-api/src/orchestrator/application/use_cases/activity.py` — `record_activity`: gets run, increments `active_seconds`, commits, returns new total; raises `NotFound` for unknown id
- `backend-api/src/orchestrator/api/providers.py:347` — `activity_ports` provider
- `backend-api/src/orchestrator/main.py:66,309` — `run_activity.router` imported and mounted under `API_PREFIX` with `require_bearer`
- `web-client/src/stores/activity.ts` — focus tracker: counts seconds, 60 s batch via `api.POST`, `pagehide` via `sendBeacon` (or `keepalive` fallback); idle gate `IDLE_TIMEOUT_MS = 300_000`
- `web-client/src/islands/RunDetail.tsx:54,108-109` — imports and wires `startTracking(runId)` / `stopTracking()` via `useEffect`
- `web-client/src/lib/run/detail.ts:171-175` — `activeTimeText(cost)` → zero-padded `hh:mm:ss` from `cost.active_seconds`
- `web-client/src/components/run/CostBlock.tsx:58` — `<th scope="row">your active time</th>` row calling `activeTimeText`
- `backend-api/tests/unit/application/test_record_activity.py` — use case unit tests (existing)
- `backend-api/tests/unit/test_run_activity_router.py` — router unit tests (existing)
- `web-client/tests/unit/activity-store.test.ts` — store unit tests with fake timers (existing)
- `web-client/tests/unit/run-cost-block-active-time.test.ts` — `activeTimeText` unit tests (existing)
- `web-client/tests/e2e/run-activity.spec.ts` — Playwright e2e tests (existing)
- `backend-api/tests/unit/test_bearer_auth.py:276` — **FIXED**: `document["paths"][path]["get"]["responses"]` → `document["paths"][path][_method]["responses"]`; operator-authorized one-character fix
- `web-client/tests/e2e/run-activity.spec.ts:114,157` — **FIXED**: `page.clock.fastForward(65_000)` → `page.clock.runFor(65_000)`; `fastForward` fires only the last timer occurrence (resulting in `focused_seconds: 1`), while `runFor` fires all 65 intermediate ticks so the batch correctly accumulates 60 seconds; operator-authorized fix
- `web-client/playwright.config.ts` — **FIXED**: added `workers: 2`; stub backend is single-threaded Node.js and the default 7 workers (14 CPUs / 2) saturated it causing 30 s timeouts across all tests

## Tasks & Acceptance

**Execution (completed):**
- `backend-api/tests/unit/test_bearer_auth.py:276` — changed `["get"]` to `[_method]`; operator-authorized one-character fix ✓
- `web-client/tests/e2e/run-activity.spec.ts:114,157` — changed `page.clock.fastForward(65_000)` to `page.clock.runFor(65_000)`; `fastForward` fires only the last timer, `runFor` fires all 65 ticks; operator-authorized fix ✓
- `web-client/playwright.config.ts` — added `workers: 2` to prevent stub backend saturation (14 CPUs default = 7 workers, causing 30s timeouts) ✓

**Acceptance Criteria:**
- Given `POST /runs/{id}/activity {focused_seconds: 45}` twice, when applied, then `active_seconds` is 90 and the cost block reads `00:01:30`
- Given `focused_seconds: 0` or `5000`, when posted, then 422
- Given a focused detail with fake timers, when 60 s pass with activity, then one POST with `focused_seconds: 60` is sent and the store resets; after 6 idle minutes only the first 5 count
- Given the tab hidden, when time passes, then nothing is counted; on `pagehide` the remainder is posted
- Given any versioned route in the contract, when the bearer-auth contract test checks its 401, then it reads the correct method's responses (not always GET)

## Spec Change Log

### 2026-09-11 — bad_spec repair (review pass 1)

**Triggering finding:** The initial implementation of attempt 3 incorrectly removed `&& document.hasFocus()` from `_isActive()`, changing production behavior so time accumulates whenever the tab is visible even when another OS window is focused. This contradicts the spec's prior implementation (committed in 985943f) and the brief's "window focused" condition. The removal was unnecessary: `page.clock.runFor()` fires all 65 tick callbacks synchronously after a click gives the page focus, so `hasFocus()` returns `true` throughout without modification.

**What was amended:** Code Map and Tasks entries for `web-client/src/stores/activity.ts:42` removed (no `_isActive()` change is part of this story). Design Notes updated to reflect the actual three changes. `activity.ts` code reverted to `return document.visibilityState === 'visible' && document.hasFocus()` with the original docstring restored.

**Known-bad state avoided:** Do not remove `document.hasFocus()` from `_isActive()`. The fix for the e2e tests is `page.clock.runFor(65_000)` (not `fastForward`), which fires all intermediate timers synchronously. With `runFor`, `hasFocus()` returns `true` for all 65 callbacks because no async event loop turns occur between ticks; the click before `runFor` establishes focus and it persists through the synchronous batch.

**KEEP instructions:** `fastForward` → `runFor` change in `run-activity.spec.ts` (both sites). `workers: 2` in `playwright.config.ts`. `test_bearer_auth.py:276` one-character fix.

## Review Triage Log

### 2026-09-11 — Review pass
- intent_gap: 0
- bad_spec: 1: (high 0, medium 1, low 0)
- patch: 2: (high 0, medium 0, low 2)
- defer: 3: (high 0, medium 0, low 3)
- reject: 8
- addressed_findings:
  - `[medium]` `[bad_spec]` `_isActive()` removed `document.hasFocus()` unnecessarily — time accumulated while visible-but-unfocused contradicts the spec's prior implementation and brief's "window focused" condition; reverted to `return document.visibilityState === 'visible' && document.hasFocus()` and confirmed `page.clock.runFor()` alone is sufficient (tests pass)
  - `[low]` `[patch]` Design Notes said "only remaining change is test_bearer_auth.py:276" — updated to describe all three actual changes
  - `[low]` `[patch]` "Block If" guard retained forward-looking language after execution — updated to confirm column is present

## Design Notes

**Three fixes after fully-landed implementation:** All feature code landed in attempts 1 and 2. This attempt applies three remaining fixes: (1) `test_bearer_auth.py:276` — a one-character correction (`"get"` → `_method`) for a latent bug exposed by the POST-only activity route; (2) `run-activity.spec.ts` — `fastForward` → `runFor` so the fake clock fires all 65 tick callbacks instead of only the last one (operator-authorized); (3) `playwright.config.ts` — `workers: 2` cap so the single-threaded stub backend is not saturated by the default 7 parallel workers.

## Verification

**Commands:**
- `make lint` — expected: zero ruff/mypy/import-linter/eslint/tsc errors
- `make test` — expected: all unit tests pass, including `test_bearer_auth.py::test_the_contract_declares_the_401_and_its_media_type`
- `make openapi` — expected: no contract drift
- `make e2e-ui` — expected: `run-activity.spec.ts` passes

## Auto Run Result

**Summary:** Fixed three issues that blocked `make e2e-ui` for story 8-2: (1) `test_bearer_auth.py:276` hardcoded `["get"]` responses lookup that crashed on the POST-only activity endpoint; (2) `run-activity.spec.ts` used `page.clock.fastForward()` which fires only the last timer occurrence — changed to `page.clock.runFor()` which fires all 65 intermediate ticks allowing the batch to accumulate 60 seconds correctly; (3) `playwright.config.ts` gained `workers: 2` to prevent the single-threaded stub backend from timing out under 7 default parallel workers.

**Files changed:**
- `backend-api/tests/unit/test_bearer_auth.py` — `["get"]` → `[_method]` so 401 contract sweep reads each method's own responses
- `web-client/tests/e2e/run-activity.spec.ts` — `fastForward(65_000)` → `runFor(65_000)` in both test cases
- `web-client/playwright.config.ts` — added `workers: 2` global cap
- `_bmad-output/planning-artifacts/mvp/epics/epic-08-readouts/stories/8-2-active-operator-time.md` — spec file (this document)

**Review findings breakdown:**
- bad_spec repaired: 1 medium (unnecessary `hasFocus()` removal reverted)
- patch applied: 2 low (Design Notes text, Block If language)
- deferred: 3 low (context field empty, unknown-run_id matrix row missing, 6-idle-min trigger timing)
- rejected: 8

**Follow-up review score:** 0 high patches + 0 medium patches + 2 low patches → score = 3×0 + 3×0 + 1×2 = 2 < 5. `followup_review_recommended: false`.

**Verification performed:**
- `make lint` — ✓ zero errors
- `make test` — ✓ 6016 backend + 1321 frontend; `test_bearer_auth.py::test_the_contract_declares_the_401_and_its_media_type` passes
- `make openapi` — ✓ no contract drift
- `make e2e-ui` — ✓ 194 passed, 1 skipped (uj3 end-to-end integration, pre-existing skip)

**Residual risks:** The 5-minute idle timeout provides substantial protection for the "visible but unfocused" case: an operator who switches to another OS window within a 5-minute window does not accrue time because pointer/keyboard events reset the idle timer only on the orchestrator tab. The risk is a user who has the tab visible but never interacts for ≤5 minutes while in another window — this would accrue active seconds incorrectly. This is the intended behavior from the spec ("window focused") which is preserved by retaining `document.hasFocus()`.
