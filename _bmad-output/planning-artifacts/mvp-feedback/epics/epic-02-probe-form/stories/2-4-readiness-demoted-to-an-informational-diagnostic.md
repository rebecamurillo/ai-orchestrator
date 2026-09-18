---
title: 'Readiness demoted to an informational diagnostic'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: '5400b20a752e9127c5001630bb3ba835069b3616'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - 'runReadiness error handling for 5xx / network errors (spec chose 4-line handler; 201 and 409 are the only expected responses)'
  - 'In-flight guard for double-click on run readiness (409 from second click is handled gracefully by board navigation)'
  - 'VERSION_PIN_CHANGED constant not imported in test_sync_pins_badge_reset.py — uses string literal matching anchor pattern'
---

<intent-contract>

## Intent

**Problem:** The harness row's readiness section shows "not available yet" even though `POST /harnesses/{name}/readiness` is in the contract; `sync_pins()` does not reset `last_readiness_at` on a pin change, leaving stale last-run times on the badge; and the readiness run's role is to inform the operator, not gate anything.

**Approach:** Wire `onRunReadiness` in the island so clicking "run readiness" fires `POST /harnesses/{name}/readiness` and navigates to the board; show the badge (`last_readiness_at` + `failing_check`) in the span when the prop is present; update `sync_pins()` to clear `last_readiness_at` on pin change.

## Boundaries & Constraints

**Always:**
- Readiness is informational only — it never gates harness selection, pre-flight, or `create_run`; that is the probe's job (stories 2-2, 2-3).
- `HarnessList` fallback path (no `onRunReadiness` prop) must continue to show "not available yet" — preserved by the same guard as `probeResults` (anchor test `harness-list.test.ts` renders without the new prop and must keep passing unchanged).
- `HarnessOut` schema is not changed — badge fields (`last_readiness_at`, `failing_check`) are already in the response; probe result stays at `GET /harnesses/{name}/probe`.
- All API calls through `src/api/client.ts` (AD-1); no new `fetch` in the island.
- TDD: new test files created and failing before implementation; existing anchor test files never touched except the one exception-4 revision below.
- `make lint` import-linter must pass: no `fastapi`, `sqlalchemy`, `subprocess`, etc. in `domain/` or `application/`.

**Block If:**
- `POST /harnesses/{name}/readiness` is absent from `contracts/openapi.json` — must be present (story 2-1 regenerated it; verify before coding).
- `harness_readiness_seed.py::sync_pins` signature or return type has changed in a way that prevents the `last_readiness_at: None` addition.

**Never:**
- Gate on `harness.enabled`, `last_readiness_at`, or `failing_check` in `create_run`, pre-flight, or the new island handler.
- Modify `harnessLineText`, `harnessProbeLineText`, `withHarness`, `reconcileInitial`, `modelsFor`, `READINESS_LINK_LABEL`, `readinessHref`, or `READINESS_NOT_AVAILABLE` in `state.ts`.
- Modify `harness-list.test.ts`, `newwf-state.test.ts`, `newwf-state-probe.test.ts`, `harness-list-probe.test.ts`, `test_harness_readiness_seed.py`, or any other existing test file except the single exception-4 revision below.
- Call `probe()` from the "run readiness" handler.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Badge: no readiness run | `last_readiness_at=null`, `failing_check=null` | Note span text is `""` | No error |
| Badge: run passed | `last_readiness_at="2026-09-17T10:00:00Z"`, `failing_check=null` | Note span shows `"2026-09-17 10:00:00"` | No error |
| Badge: run failed | `last_readiness_at="2026-09-17T10:00:00Z"`, `failing_check="harness: not running"` | Note span shows `"2026-09-17 10:00:00 · harness: not running"` | No error |
| Badge: pin changed (no prior run) | `last_readiness_at=null`, `failing_check="version pin changed: 1.0 → 2.0"` | Note span shows `"version pin changed: 1.0 → 2.0"` | No error |
| Run readiness clicked, 201 | POST returns `{run:{id:...}}` | POST called; navigate to `/runs` | None |
| Run readiness clicked, 409 | POST returns conflict | Navigate to `/runs` so operator sees the in-progress run | None |
| sync_pins pin change | Harness with `last_readiness_at` set and different pin | `last_readiness_at` reset to `None`; `failing_check` set to pin-changed message (unchanged) | None |
| No `onRunReadiness` prop | Island absent (unit-test path) | Note span still shows "not available yet"; href still present | None |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/use_cases/harness_readiness_seed.py:47-69` — `sync_pins()`: add `"last_readiness_at": None` to the `model_copy(update={...})` dict; the `failing_check` pin-changed message stays; this line is the only change needed in this file
- `backend-api/src/orchestrator/domain/entities/harness.py:39-57` — `Harness` entity; `last_readiness_at: datetime | None = None`; confirm field is present before writing tests
- `backend-api/tests/unit/application/test_harness_readiness_seed.py` — READ-ONLY anchor; existing `test_disables_a_harness_whose_pin_changed_and_records_old_to_new` does not assert `last_readiness_at`, so the additive change does not break it; new behaviour goes in a new file
- `web-client/src/lib/newwf/state.ts:252-265` — add `export function readinessBadgeText(harness: HarnessOut): string` after `READINESS_NOT_AVAILABLE`; joins non-empty parts of `readinessTime(harness.last_readiness_at)` and `harness.failing_check` with ` · ` (returns `""` when both are null)
- `web-client/src/components/HarnessList.tsx:34-90` — Props interface: add `onRunReadiness?: (name: string) => void`; import `readinessBadgeText` from state; in the `<span>` (line 83): when `onRunReadiness !== undefined`, render `readinessBadgeText(harness)`; else keep `READINESS_NOT_AVAILABLE`; add `onClick` to the `<a>` when `onRunReadiness !== undefined`: `(e) => { e.preventDefault(); onRunReadiness(harness.name); }` — the `href` stays unchanged (anchor test pins it)
- `web-client/src/islands/NewWorkflow.tsx:65+` — add `runReadiness(name: string)`: calls `api.POST('/harnesses/{name}/readiness', { params: { path: { name } } })`; on any response (201 or 409) navigate to `/runs` via `window.location.href = '/runs'`; wire to `HarnessList` via `onRunReadiness={runReadiness}` prop
- `web-client/src/api/schema.d.ts` — `start_readiness_api_v1_harnesses__name__readiness_post` operation already generated (story 2-1); verify before coding
- `web-client/tests/unit/harness-list.test.ts` — READ-ONLY anchor; `onRunReadiness` absent path: "not available yet" preserved
- `web-client/tests/e2e/new-workflow.spec.ts:401-416` — exception-4 revision target: `toHaveText('not available yet')` → `toHaveText('')`

## Tasks & Acceptance

**Execution:**

Tests first — must exist and fail before implementation:

- `backend-api/tests/unit/application/test_sync_pins_badge_reset.py` — create — given a harness with `last_readiness_at` set and a changed pin, assert `sync_pins()` resets `last_readiness_at` to `None` and still sets `failing_check = "version pin changed: {old} → {new}"`; use a harness with `last_readiness_at=datetime(2026, 3, 4, tzinfo=UTC)` to distinguish from the default-None case

- `web-client/tests/unit/newwf-state-readiness.test.ts` — create — test `readinessBadgeText`: null/null → `""`, time/null → just time string, null/check → just check string, time/check → `"{time} · {check}"`; assert `readinessBadgeText` is exported from state

- `web-client/tests/unit/harness-list-readiness.test.ts` — create — uses `renderToStaticMarkup` (same pattern as anchor `harness-list.test.ts`); given `onRunReadiness` prop: note span shows `readinessBadgeText(harness)` output (empty string for null/null harness; time string for harness with `last_readiness_at`; failing_check concatenated when present); do NOT duplicate anchor test assertions for absent-prop path; click behavior covered by e2e only

- `web-client/tests/e2e/new-workflow-readiness.spec.ts` — create — mock `GET **/api/v1/harnesses` to return a harness with `last_readiness_at` set and `failing_check=null`; assert note span shows the formatted time (not "not available yet"); mock `POST **/api/v1/harnesses/*/readiness` to return 201; click "run readiness"; assert POST was called and navigation to `/runs` occurred; mock POST returning 409; click "run readiness"; assert navigation to `/runs` still occurred

Exception-4 revision — **AUTHORIZED** (Operator decision 2026-09-15, readiness demoted to informational diagnostic as specified in SPEC.md epic-02-probe-form):

- `web-client/tests/e2e/new-workflow.spec.ts:413` — revise `'the re-run readiness link points at the endpoint and says it is not served yet'`: change `await expect(page.getByTestId('newwf-readiness-claude-note')).toHaveText('not available yet')` to `await expect(page.getByTestId('newwf-readiness-claude-note')).toHaveText('')`; add comment naming the decision and date 2026-09-15/2026-09-17 per exception-4 requirement; no other change to this test

Implementation (all after tests exist and fail):

- `backend-api/src/orchestrator/application/use_cases/harness_readiness_seed.py` — add `"last_readiness_at": None` to the `model_copy(update={...})` dict in `sync_pins()`; no other change to this file

- `web-client/src/lib/newwf/state.ts` — add `export function readinessBadgeText(harness: HarnessOut): string` after the `READINESS_NOT_AVAILABLE` const; import `HarnessOut` type if not already imported at function scope

- `web-client/src/components/HarnessList.tsx` — add `onRunReadiness?: (name: string) => void` to Props; import `readinessBadgeText`; update span content and add conditional `onClick` to link per Code Map

- `web-client/src/islands/NewWorkflow.tsx` — add `runReadiness(name)` handler per Code Map; wire to `HarnessList` via `onRunReadiness={runReadiness}` prop; no additional state needed

**Acceptance Criteria:**
- Given `sync_pins()` is called with a changed pin and the harness has `last_readiness_at` set, then `last_readiness_at` is `None` after the update and `failing_check` is `"version pin changed: {old} → {new}"`
- Given `onRunReadiness` prop is passed to `HarnessList` and a harness has `last_readiness_at="2026-09-17T10:00:00Z"` and `failing_check=null`, when rendered, then the note span shows `"2026-09-17 10:00:00"` (not "not available yet")
- Given `onRunReadiness` prop is passed and a harness has both `last_readiness_at` and `failing_check` set, when rendered, then the note span shows `"{time} · {failing_check}"`
- Given `onRunReadiness` prop is absent (unit-test path), when rendered, then the note span still shows `"not available yet"` and the link href is `/api/harnesses/{name}/readiness` (backward-compat preserved)
- Given the form is running in the island and the operator clicks "run readiness", when `POST /harnesses/{name}/readiness` returns 201, then the browser navigates to `/runs`
- Given the form island and `POST /harnesses/{name}/readiness` returns 409 (run already in progress), then the browser navigates to `/runs` so the operator sees the in-progress run
- Given `make lint` runs, then ruff, mypy, import-linter, tsc, eslint, prettier, check_test_pairs, gen:api --check all pass

## Spec Change Log

## Review Triage Log

**Loop 0 — 2026-09-17**

Reviewers: Blind Hunter, Edge Case Hunter, Verification Gap Reviewer, Intent Alignment Auditor.

Patches applied (2):

1. **e2e test ordering** (`new-workflow-readiness.spec.ts:114-115`): `readinessPostCalled` synchronous assertion moved after `await expect(page).toHaveURL('/runs')` — route callback is guaranteed to have fired before the URL assertion resolves, so the ordering was a false-positive risk.

2. **Verification gap in `harness-list-readiness.test.ts` tests 3–5**: `toContain(...)` on full markup matched `failing_check` / `last_readiness_at` text appearing in both the note span AND the harness-line label (via `harnessLineText`). Added `noteText(markup, name)` helper that extracts the note span's content via regex; tests 3–5 now use `toBe(...)` on the span content only — a regression that drops `failing_check` from the badge would be detected.

Deferred (added to frontmatter):

- Error handling for 5xx / network errors in `runReadiness`: spec Design Notes explicitly chose a 4-line handler; 201 and 409 are the only expected responses and both navigate safely.
- In-flight guard for rapid double-click: spec says "No island state is needed for 409 feedback"; a 409 from the second click navigates to /runs where the in-progress run is visible.
- `VERSION_PIN_CHANGED` constant not imported in test; test uses string literal matching anchor pattern.

Rejected (false positives / out-of-scope):

- Empty badge for never-run harness: I/O matrix row 1 explicitly specifies `""`.
- `onRunReadiness` void vs Promise\<void\> type annotation: TypeScript permits async→void.
- Absent-prop path untested in new file: spec task spec says "do NOT duplicate anchor test assertions for absent-prop path".
- Exception-4 two-date format: spec tasks section specified `2026-09-15/2026-09-17` explicitly.
- `readinessTime` non-UTC offset: pre-existing behavior, unchanged in this story.
- Multi-harness iteration coverage: standard `Array.map`; low risk.
- Intent alignment auditor claim that tests omit story 2-4 coverage: false positive; auditor received truncated diff and did not see actual new file content.

## Design Notes

**`readinessBadgeText` format:** joins the non-null parts of `readinessTime(last_readiness_at)` and `failing_check` with ` · `, returning `""` when both are null. Uses the existing private `readinessTime()` helper (already in state.ts). The function is a pure state helper; do not add it to the island directly.

**`onRunReadiness` prop guard mirrors `probeResults`:** when `undefined` (unit tests / static SSR), show "not available yet"; when any function value (island), show badge. The island always passes a function, so the guard resolves at component boundaries, never inside the island logic.

**`runReadiness` navigation:** both 201 and 409 navigate to `/runs` via `window.location.href = '/runs'`; on 201 the operator sees the new run; on 409 they see the already-in-progress run. No island state is needed for 409 feedback — the board provides it. Do not use the Astro router or introduce a router dependency in the island. This keeps the handler to four lines.

## Auto Run Result

**Date:** 2026-09-17  
**Status:** done  
**Review loop iterations:** 1 (loop 0 — 2 patches applied; no re-review required)

**Changes delivered:**
- `backend-api/src/orchestrator/application/use_cases/harness_readiness_seed.py` — `sync_pins()` clears `last_readiness_at` on pin change
- `web-client/src/lib/newwf/state.ts` — `readinessBadgeText` exported
- `web-client/src/components/HarnessList.tsx` — `onRunReadiness` prop; badge span; conditional click handler
- `web-client/src/islands/NewWorkflow.tsx` — `runReadiness` handler wired to `HarnessList`
- `web-client/tests/e2e/new-workflow.spec.ts` — exception-4 revision (Operator decision 2026-09-15/2026-09-17)

**New test files:**
- `backend-api/tests/unit/application/test_sync_pins_badge_reset.py`
- `web-client/tests/unit/newwf-state-readiness.test.ts`
- `web-client/tests/unit/harness-list-readiness.test.ts`
- `web-client/tests/e2e/new-workflow-readiness.spec.ts`

## Verification

**Commands:**
- `make lint` — expected: ruff, mypy, import-linter, prettier, tsc, eslint, env-contract, check_test_pairs, gen:api --check all pass
- `make test` — expected: all unit tests green including new `test_sync_pins_badge_reset.py`, `newwf-state-readiness.test.ts`, `harness-list-readiness.test.ts`
- `make openapi` — expected: no drift (HarnessOut schema unchanged); run to confirm
- `make e2e-ui` — expected: `new-workflow-readiness.spec.ts` passes; revised `new-workflow.spec.ts` readiness test passes
