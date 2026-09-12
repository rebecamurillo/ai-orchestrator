---
title: 'Active Operator time'
type: 'feature'
created: '2026-09-11'
status: 'in-progress'
baseline_revision: '9882dc04aea4ffe78b4d735a0f6dbb24d6d7c9e0'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Run detail's `your active time` row shows a static `—` and no endpoint receives focus-time reports; Operator attention is unmeasured (SM-2 cannot be satisfied).

**Approach:** Add `POST /runs/{id}/activity {focused_seconds}` that increments `run.active_seconds`; add a `src/stores/activity.ts` client store that counts focused seconds and batches them; render `cost.active_seconds` as `hh:mm:ss` in `CostBlock`.

## Boundaries & Constraints

**Always:**
- `active_seconds` increments only through the activity use case; it is never decremented
- Response is `{"active_seconds": N}` (updated total) with HTTP 200; 422 for `focused_seconds` outside `[1, 3600]`; allowed for any Run status
- The activity route lives in a new `run_activity.py` module — `run.py` has a frozen 3-route test and `run_detail.py` has a frozen 1-route test; neither can accept this route
- `schema.d.ts` is never hand-edited (AD-3); `CostOut.active_seconds: number` is already generated; run `make openapi` after the backend route is added so the new `ActivityOut` type is available before wiring the store's response type
- `run-cost-block.test.ts` line 80's `toContain('—')` is revised under the AGENTS.md placeholder exception: the fixture has `active_seconds: 30` (prepared for Epic 8) and `CostBlock.tsx:3–4` names Epic 8 as the replacer; the same commit adds `run-cost-block-active-time.test.ts` that strictly exceeds the revised assertion
- Both diagram and detail views count: wire `startTracking`/`stopTracking` in `RunDetail.tsx` and `RunDiagram.tsx`

**Block If:**
- `run.active_seconds` is absent from `infrastructure/db/repositories/runs.py::MUTABLE_COLUMNS` (would mean the repository update doesn't persist it — check line 144 before writing the use case)
- `CostOut.active_seconds` is missing from `schema.d.ts` after `make openapi` runs

**Never:**
- Add `active_seconds` to `RunSummaryOut` or the Board
- Store per-day or per-session breakdown
- Accept `focused_seconds: 0` or `focused_seconds > 3600` (422 for both)
- Write `active_seconds` outside `application/use_cases/activity.py`
- Add a retry strategy to the store; fire-and-forget is sufficient

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|---|---|---|---|
| Happy path accumulation | `POST {focused_seconds: 45}` × 2 on run with `active_seconds=0` | Second call returns `{"active_seconds": 90}`; cost block shows `00:01:30` | — |
| Out of range low | `POST {focused_seconds: 0}` | 422 | — |
| Out of range high | `POST {focused_seconds: 5000}` | 422 | — |
| Any Run status | `POST {focused_seconds: 30}` on done/failed/cancelled Run | 200 `{"active_seconds": N}` | — |
| 60 s focus batch | Store: 60 s elapsed, activity events within 5 min | One POST with `focused_seconds: 60`; store resets to 0 | — |
| 6 min idle | Store: 6 min, no pointer/key events after min 5 | 300 s counted total; minute 6 excluded | — |
| Tab hidden | `visibilityState=hidden` | Counter pauses; no POST until pagehide | — |
| pagehide with ≥1 s | `accumulated_seconds ≥ 1` | POST fires immediately (sendBeacon / keepalive fetch) | — |
| pagehide with 0 s | `accumulated_seconds = 0` | No POST | — |

</intent-contract>

## Code Map

**Backend:**
- `backend-api/src/orchestrator/domain/entities/run.py:102` — `active_seconds: int = 0` already exists; no change
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py:144,164` — `MUTABLE_COLUMNS` includes `active_seconds`; `update(run)` persists it; no change
- `backend-api/src/orchestrator/api/schemas/run_views.py:267–273` — `CostOut.active_seconds: int` already in response schema; no change
- `backend-api/src/orchestrator/application/use_cases/activity.py` — NEW; `@dataclass(frozen=True) class ActivityPorts: runs: RunRepository; uow: UnitOfWork`; `record_activity(ports, run_id: UUID, focused_seconds: int) -> int` — fetches run (None → raises RunNotFound or equivalent), `model_copy(update={"active_seconds": run.active_seconds + focused_seconds})`, calls `ports.runs.update`, commits, returns new `active_seconds`; no `WriterPorts` — follow the `SpendPorts` pattern in `spend.py`
- `backend-api/src/orchestrator/api/routers/run_activity.py` — NEW; `POST /runs/{run_id}/activity`; Pydantic body `ActivityIn(focused_seconds: int = Field(ge=1, le=3600))`; calls `record_activity`; returns `{"active_seconds": N}`; 404 for unknown run — follow the 404 pattern from `run_detail.py::REFUSALS`
- `backend-api/src/orchestrator/api/providers.py` — add `activity_ports(request)` generator yielding `ActivityPorts(runs=SQLAlchemyRunRepository(uow.session), uow=uow)`; follow `run_files_ports` at line 317 as the pattern
- `backend-api/src/orchestrator/main.py:305–314` — add `run_activity` to the import block (line 53) and add `run_activity.router` to the for-loop registration block alongside the other run routers (after `run_detail`)
- `backend-api/tests/unit/fakes/runs.py` — `FakeRunRepository` already has a `get` method; use it in new tests
- `backend-api/tests/unit/test_run_activity_router.py` — NEW; 200 + body accumulation, 422 for `focused_seconds=0`, 422 for `focused_seconds=3601`, 404 for unknown `run_id`
- `backend-api/tests/unit/application/test_record_activity.py` — NEW; accumulation (`0+45=45`, `45+45=90`), returns new total, any Run status accepted

**Frontend:**
- `web-client/src/lib/run/detail.ts:155–169` — `moneyRatio`/`tokensText`/`wallClockText` pattern; add `activeTimeText(cost: CostOut): string` returning `hh:mm:ss` (zero-padded: `[h, m, s].map(n => String(n).padStart(2, '0')).join(':')`)
- `web-client/src/components/run/CostBlock.tsx:52–54` — replace `<td>—</td>` with `<td>{activeTimeText(cost)}</td>`; add `activeTimeText` to the import from `../../lib/run/detail`
- `web-client/tests/unit/run-cost-block.test.ts:73,80` — **placeholder exception** (fixture has `active_seconds: 30`; `CostBlock.tsx:3–4` names Epic 8 as replacer): revise test description from "em dash" to "hh:mm:ss" and assertion `'—'` → `'00:00:30'`; `run-cost-block-active-time.test.ts` below strictly exceeds it
- `web-client/tests/unit/run-cost-block-active-time.test.ts` — NEW; imports `activeTimeText` from `src/lib/run/detail`; four cases: `0→'00:00:00'`, `30→'00:00:30'`, `90→'00:01:30'`, `3661→'01:01:01'`
- `web-client/src/stores/activity.ts` — NEW singleton store; exports `startTracking(runId: string): void` and `stopTracking(): void`; state: `runId`, `accumulated`, `lastEventAt`, interval handle; tracking active when `document.visibilityState === 'visible'` and `document.hasFocus()`; idle exclusion: pointer and keydown events call `resetIdleTimer()` which sets `lastEventAt = Date.now()`; per-second tick: if `Date.now() - lastEventAt ≤ 300_000` and tab visible+focused, increment `accumulated`; every 60 s: if `accumulated ≥ 1`, POST and reset; `pagehide` listener (registered in `startTracking`, removed in `stopTracking`): if `accumulated ≥ 1`, post via `navigator.sendBeacon` or `fetch({keepalive: true})`
- `web-client/src/islands/RunDetail.tsx` — add `useEffect` that calls `startTracking(runId)` on mount and `stopTracking()` on cleanup; `runId` from `detail.run.id`
- `web-client/src/islands/RunDiagram.tsx` — same `startTracking(runId)` / `stopTracking()` wiring so both views count (brief CAP-2)
- `web-client/tests/unit/activity-store.test.ts` — NEW; vitest fake timers: 60 s with events → POST fires, accumulated resets; 6 idle min → only 300 s counted; `visibilityState=hidden` → nothing counted; pagehide → remainder posted when ≥1
- `web-client/tests/e2e/run-activity.spec.ts` — NEW; Playwright: intercept `POST /api/v1/runs/*/activity`; load Run detail page and assert at least one POST fires with a numeric `focused_seconds` body field; `page.clock.install()` / `page.clock.tick(65_000)` to advance time without waiting real seconds

## Tasks & Acceptance

**Execution:**

1. `backend-api/src/orchestrator/application/use_cases/activity.py` — NEW: `ActivityPorts`, `record_activity`
2. `backend-api/src/orchestrator/api/routers/run_activity.py` — NEW: `POST /runs/{run_id}/activity`, `ActivityIn` body, 422 range validation, 404 guard
3. `backend-api/src/orchestrator/api/providers.py` — add `activity_ports` provider
4. `backend-api/src/orchestrator/main.py` — import and register `run_activity.router`
5. `backend-api/tests/unit/test_run_activity_router.py` — NEW: router-level tests (200, 422×2, 404)
6. `backend-api/tests/unit/application/test_record_activity.py` — NEW: use-case unit tests (accumulation, return value, any status)
7. `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts` so the `ActivityOut` type is available before frontend work
8. `web-client/src/lib/run/detail.ts` — add `activeTimeText(cost: CostOut): string`
9. `web-client/src/components/run/CostBlock.tsx` — render `activeTimeText(cost)` in the active-time row
10. `web-client/tests/unit/run-cost-block.test.ts` — REVISE lines 73 + 80: description update + `'—'` → `'00:00:30'` (placeholder exception; exceeded by task 11)
11. `web-client/tests/unit/run-cost-block-active-time.test.ts` — NEW: four `activeTimeText` cases
12. `web-client/src/stores/activity.ts` — NEW: singleton tracker with idle exclusion, 60 s batch, pagehide flush
13. `web-client/src/islands/RunDetail.tsx` — mount/unmount `startTracking` / `stopTracking` in `useEffect`
14. `web-client/src/islands/RunDiagram.tsx` — same `startTracking` / `stopTracking` wiring
15. `web-client/tests/unit/activity-store.test.ts` — NEW: fake-timer unit tests
16. `web-client/tests/e2e/run-activity.spec.ts` — NEW: Playwright smoke for POST firing

**Acceptance Criteria:**
- Given a focused Run detail with fake timers, when 60 s pass with activity events, then one `POST /runs/{id}/activity` fires with `focused_seconds: 60` and the store resets to 0
- Given focused + 6 idle minutes (no pointer/key events in minute 6), when pagehide fires, then total seconds posted equal 300
- Given `visibilityState=hidden`, when time passes, then no seconds are counted; on pagehide the remainder (≥1 s) is posted
- Given `POST /runs/{id}/activity {focused_seconds: 45}` twice, when both apply, then `active_seconds` is 90 and the cost block reads `00:01:30`
- Given `focused_seconds: 0` or `focused_seconds: 5000`, when posted, then 422
- Given a done, failed, or cancelled Run, when `POST /activity` is called with valid `focused_seconds`, then 200

## Spec Change Log

## Review Triage Log

## Design Notes

**`run_activity.py` as a new module:** `test_run_router.py::test_the_router_declares_exactly_three_operations` pins `run.py` to exactly 3 routes; `test_run_detail_router.py::test_the_router_declares_exactly_one_operation` pins `run_detail.py` to exactly 1 route. The activity route goes in its own module — the same precedent 4.12 set when placing the detail route in `run_detail.py` (see `run_detail.py` docstring).

**`activeTimeText` zero case:** `active_seconds: 0` renders `00:00:00`, not `—`. The store never posts 0, so `00:00:00` only appears on Runs with no tracked activity.

**Idle-exclusion implementation:** Pointer and keydown events call `resetIdleTimer()` which sets `lastEventAt = Date.now()`. The per-second interval skips incrementing when `Date.now() - lastEventAt > 300_000`. This handles resumption implicitly: the next event resets the timer and the next tick counts again. No separate "paused" state flag is needed.

**pagehide POST:** Use `navigator.sendBeacon('/api/v1/runs/${runId}/activity', JSON.stringify({focused_seconds: accumulated}))` when available; fall back to `fetch({keepalive: true})`. Standard mechanism for unload-time POSTs.

**`make openapi` ordering:** Task 7 (`make openapi`) must run after task 4 (router registered) and before task 12 (store typed). Running it mid-implementation is intentional — the brief's own verification line lists `make openapi` as a required check.

## Verification

**Commands:**
- `make lint` — expected: zero ruff/mypy/import-linter/eslint/tsc errors
- `make test` — expected: all unit tests pass including `test_run_activity_router.py`, `test_record_activity.py`, `run-cost-block-active-time.test.ts`, `activity-store.test.ts`, and revised `run-cost-block.test.ts`
- `make openapi` — expected: `contracts/openapi.json` includes `POST /api/v1/runs/{run_id}/activity`; `schema.d.ts` regenerated
- `make e2e-ui` — expected: `run-activity.spec.ts` smoke test passes
