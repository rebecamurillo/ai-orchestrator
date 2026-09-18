---
title: 'Probe-gated New-workflow form with enforced model select'
type: 'feature'
created: '2026-09-17'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The New-workflow form disables harness selection based on the stale `HarnessOut.enabled` DB flag and populates the model field from static SSR data. This makes live-passing harnesses appear unselectable and lets the model select drift from what the harness actually serves.

**Approach:** On harness selection, call `GET /harnesses/{name}/probe` immediately (no debounce); use the live result to gate the radio (disable on probe fail with the specific reason in the row), populate the model select from `ProbeResultOut.models`, and clear model on harness switch. Non-harness field changes call only `POST /runs/preflight` (plan\_run). At submit, re-probe as a final guard; a probe failure synthesises a preflight-fail line and blocks `POST /runs`.

## Boundaries & Constraints

**Always:**
- Probe fires on harness selection (immediately, not debounced) and on submit only; non-harness field changes schedule only `schedulePreflight()` — no probe call.
- Model select populated from `ProbeResultOut.models`; `models: []` (gateway-disabled, `ok=true`) → free-text input (existing `models.length > 0` branch in `NewWorkflowFields`).
- `HarnessList.probeResults` prop: when `undefined` (unit tests), fall back to `!harness.enabled` for disabled; when passed as an object (island), a harness with no entry in the dict is **not** disabled — only explicit `ok === false` disables. **This means harnesses without a probe result are initially selectable when the island is mounted.**
- Row text: when the harness has no entry in `probeResults`, show existing `harnessLineText(harness)` output; when probe result present, show `harnessProbeLineText(harness, result)` — `"ok"` or `failing_reason` in words.
- Submit-time probe failure: synthesise `setPreflight({ lines: [{check: 'HARNESS', status: 'fail', text: failing_reason, fix: null}], start_allowed: false, queue_note: '', rows: null, plan_error: null })`; do not call `POST /runs`.
- Race guard on probe: `probeSeqRef` (analogous to `requestSeqRef`) — discard responses from superseded probe calls.
- Warnings never block submission.
- All API calls through `src/api/client.ts` (AD-1); no new `fetch` in the island.

**Block If:**
- Two tests in `web-client/tests/e2e/new-workflow.spec.ts` pin `disabled` radio behavior driven by `HarnessOut.enabled` and cannot be implemented without Operator exception-4 authorisation:
  - Line 99 (`'a disabled harness reads its own line and is not selectable'`): asserts `input[type="radio"]` is disabled for a harness with `enabled: false`.
  - Line 393 (`'the re-run readiness link points at the endpoint…'`): asserts `input` is disabled for the same harness.
  - After story 2-3, harnesses without a probe result are **selectable** (the probe determines disability, not the stored flag). These tests must be revised under exception-4 (Operator decision to implement probe-based gating, as stated in SPEC.md and EXPERIENCE-v1 §2.1). The revised tests should assert: (a) the radio is initially enabled; (b) after a `page.route`-mocked failing probe fires on click, the radio becomes disabled and the row shows the `failing_reason`.
  - **Authorisation required before the implementation agent proceeds.**

**Never:**
- Call probe on non-harness field changes.
- Call probe on page load for all harnesses speculatively.
- Modify `harnessLineText`, `withHarness`, `reconcileInitial`, or `modelsFor` in `state.ts` — all anchor-tested in `newwf-state.test.ts`.
- Modify `harness-list.test.ts` or `newwf-state.test.ts`.
- Read `HarnessOut.enabled` for the gating decision in post-probe state (after `probeResults[name]` is set).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Harness selected, probe ok | Click claude radio; probe returns `{ok:true, models:["m1"], version:"v1"}` | Radio stays checked; row: `"claude · ok · last readiness … · "` ; model select shows `["m1"]` | None |
| Harness selected, probe fail | Click claude radio; probe returns `{ok:false, failing_reason:"not logged in"}` | Radio becomes disabled; row: `"claude · not logged in · last readiness … · "`; state.harness cleared; model select empty | Start blocked |
| Non-harness field change | User edits base branch | Only `POST /runs/preflight` fires; probe endpoint NOT called | None |
| Submit with passing probe | Start run clicked; probe returns ok=true | Proceed to `POST /runs` | None |
| Submit with failing probe | Start run clicked; probe returns `{ok:false, failing_reason:"gateway unreachable"}` | `POST /runs` not called; pre-flight section shows `x · HARNESS · gateway unreachable`; Start disabled | Reason shown in-place |
| Gateway-disabled probe (ok=true, models=[]) | Click harness; probe `ok=true, models:[]` | Free-text model input shown (models.length === 0) | None |
| Probe in-flight | Probe call in progress after selection | `probeInFlight=true`; Start disabled; model select empty (no result yet) | None |
| Two harness selections in quick succession | Select A then immediately B | Only B's probe result applied; A's response discarded via probeSeqRef race guard | None |
| No harness set | `state.harness = ""` | Submit skips probe; `runBody` passes `harness: null` | None |

</intent-contract>

## Code Map

**Island:**
- `web-client/src/islands/NewWorkflow.tsx:65` — `NewWorkflow()`: all state declared here; add `probeResults: Record<string, ProbeResultOut>` and `probeInFlight: boolean` state; add `probeSeqRef = useRef(0)`
- `web-client/src/islands/NewWorkflow.tsx:77` — `runPreflight()`: pure plan\_run; never calls probe — unchanged
- `web-client/src/islands/NewWorkflow.tsx:104` — `schedulePreflight()`: debounce wrapper for plan\_run only — unchanged
- `web-client/src/islands/NewWorkflow.tsx:112` — `update()`: called for non-harness changes; continues to call `schedulePreflight()` — unchanged
- `web-client/src/islands/NewWorkflow.tsx:130` — `startRun()`: add probe guard before `api.POST('/runs', ...)` — see Design Notes
- `web-client/src/islands/NewWorkflow.tsx:159` — `startDisabled`: add `|| probeInFlight`
- `web-client/src/islands/NewWorkflow.tsx:173` — `models={modelsFor(harnesses, state.harness)}` → change to `models={probeResults[state.harness]?.models ?? []}`
- `web-client/src/islands/NewWorkflow.tsx:178-183` — `HarnessList onSelect`: change `update(withHarness(state, name, harnesses))` to `update({...state, harness: name, model: ''}); void runProbe(name);` (calls `update` for plan\_run scheduling, then immediately probes)
- `web-client/src/islands/NewWorkflow.tsx:178` — `HarnessList`: add `probeResults={probeResults}` prop

**Component:**
- `web-client/src/components/HarnessList.tsx:34` — Props interface: add `probeResults?: Record<string, ProbeResultOut>`
- `web-client/src/components/HarnessList.tsx:54` — `disabled={!harness.enabled}`: change to `disabled={probeResults !== undefined ? (probeResults[harness.name]?.ok === false) : !harness.enabled}`
- `web-client/src/components/HarnessList.tsx:58` — `{harnessLineText(harness)}`: change to `{probeResults !== undefined && probeResults[harness.name] ? harnessProbeLineText(harness, probeResults[harness.name]) : harnessLineText(harness)}`
- `web-client/src/components/HarnessList.tsx:22-28` — imports: add `harnessProbeLineText` and `ProbeResultOut` from state

**State helpers:**
- `web-client/src/lib/newwf/state.ts:19` — type imports block: add `type ProbeResultOut = components['schemas']['ProbeResultOut']`; export it
- `web-client/src/lib/newwf/state.ts:225` — `harnessLineText()`: READ-ONLY anchor; do not modify
- `web-client/src/lib/newwf/state.ts:107` — `modelsFor()`: READ-ONLY anchor; do not modify; island stops calling it
- `web-client/src/lib/newwf/state.ts:122` — `withHarness()`: READ-ONLY anchor; island stops calling it for harness-change path (always clears model on selection now)
- `web-client/src/lib/newwf/state.ts:261` — `reconcileInitial()`: READ-ONLY; continues using `harness.enabled` as URL-restore heuristic — acceptable since probe determines runtime gating, not URL restore

**Contract:**
- `web-client/src/api/schema.d.ts:1369` — `ProbeResultOut: { ok: boolean; failing_reason: string|null; models: string[]; version: string }` — already generated; probe operation at line 2220 (`run_probe_api_v1_harnesses__name__probe_get`)

**Read-only anchors (never touch):**
- `web-client/tests/unit/harness-list.test.ts` — tests `disabled={!harness.enabled}` when `probeResults` prop absent; tests `harnessLineText` verbatim output; both preserved by the `probeResults !== undefined` guard in HarnessList
- `web-client/tests/unit/newwf-state.test.ts` — tests `harnessLineText`, `withHarness`, `reconcileInitial`, `modelsFor`; none modified
- `web-client/tests/unit/newwf-fields.test.ts` — tests `models=[]` free-text fallback; preserved (no models until probe ok)
- `web-client/tests/e2e/new-workflow.spec.ts:99` and `:381` — **EXCEPTION-4 REQUIRED** (see Block If above)

## Tasks & Acceptance

**Execution:**

Tests first — must exist and fail before implementation:

- `web-client/tests/unit/harness-list-probe.test.ts` — create — tests `HarnessList` with `probeResults` prop using `renderToStaticMarkup`:
  - Given `probeResults={claude: {ok:true, ...}}`: radio for claude NOT disabled; row text contains `"ok"`
  - Given `probeResults={claude: {ok:false, failing_reason:"not logged in"}}`: radio disabled; row text contains `"not logged in"`
  - Given `probeResults={}` (empty dict) and `enabled:false`: radio NOT disabled (probe-based path, no entry → ok===false is false → enabled)
  - Given `probeResults` absent (undefined) and `enabled:false`: radio IS disabled (fallback path)

- `web-client/tests/unit/newwf-state-probe.test.ts` — create — tests `harnessProbeLineText(harness, result)`:
  - ok result → text is `"{name} · ok · last readiness {time} · "` (with the readiness time from harness SSR data)
  - failing result → text is `"{name} · {failing_reason} · last readiness — · "`
  - `ProbeResultOut` is exported from state.ts

- `web-client/tests/e2e/new-workflow-probe.spec.ts` — create — e2e probe-form flow; all API calls mocked with `page.route()`:
  - Given harness radio clicked and probe mocked ok → model select appears with probed models; radio stays checked
  - Given harness radio clicked and probe mocked fail → radio becomes disabled; row shows `failing_reason`; Start disabled
  - Given non-harness field change → probe endpoint never called (count via `page.route` call counter)
  - Given Start clicked and probe mocked ok → `POST /runs` called
  - Given Start clicked and probe mocked fail → `POST /runs` not called; pre-flight section shows fail line with `failing_reason`

Exception-4 revisions — **BLOCKED: require Operator authorization before implementation agent may execute**:

- `web-client/tests/e2e/new-workflow.spec.ts:99-108` — revise `'a disabled harness reads its own line and is not selectable'` (exception-4, Operator decision: probe-based harness gating as specified in SPEC.md and EXPERIENCE-v1 §2.1): remove assertion that radio is disabled on initial render; replace with: (a) mock `GET /harnesses/*/probe` to return failing result; (b) click the radio; (c) assert radio becomes disabled and row contains `failing_reason`; name the decision and date in the test body per exception-4 requirement.

- `web-client/tests/e2e/new-workflow.spec.ts:381-394` — revise `'the re-run readiness link points at the endpoint and says it is not served yet'` (exception-4, same decision): remove `await expect(page.getByTestId('newwf-harness-claude').locator('input')).toBeDisabled()` and the comment "the link is offered on a disabled harness too — re-running readiness is what enables one"; replace with assertion that the radio is initially enabled; name the decision and date per exception-4 requirement.

Implementation (after exception-4 authorization received):

- `web-client/src/lib/newwf/state.ts` — add `export type ProbeResultOut = components['schemas']['ProbeResultOut']`; add `export function harnessProbeLineText(harness: HarnessOut, result: ProbeResultOut): string` — format: `` `${harness.name} · ${result.ok ? 'ok' : result.failing_reason ?? 'probe failed'} · last readiness ${harness.last_readiness_at ? readinessTime(harness.last_readiness_at) : '—'} · ` ``

- `web-client/src/components/HarnessList.tsx` — add `probeResults?: Record<string, ProbeResultOut>` to Props; import `harnessProbeLineText` and `ProbeResultOut` from state; update `disabled` and text rendering per Code Map above

- `web-client/src/islands/NewWorkflow.tsx` — add `ProbeResultOut` type alias; add `probeResults` and `probeInFlight` state; add `probeSeqRef`; add `runProbe()` async function (see Design Notes); update harness `onSelect` handler; update `models` prop; pass `probeResults` to `HarnessList`; update `startDisabled`; add submit-time probe guard in `startRun()`

**Acceptance Criteria:**
- Given a harness radio with no probe result yet, when the form loads, then the radio is enabled (selectable) regardless of `HarnessOut.enabled` value (Operator decision: probe-based gating)
- Given a harness radio is clicked and the probe returns `ok=true, models=["m1"]`, when the probe resolves, then the model select renders with `["m1"]` as options and the row text reads `"{name} · ok · last readiness … · "`
- Given a harness radio is clicked and the probe returns `ok=false, failing_reason="not logged in"`, when the probe resolves, then the radio is disabled, the row text contains `"not logged in"` (not "disabled: …"), and `state.harness` is cleared
- Given model field with probe ok and `models: []` (gateway-disabled), when rendered, then a free-text input is shown (not a select)
- Given any non-harness field is changed, when `POST /runs/preflight` is triggered, then `GET /harnesses/*/probe` is NOT called
- Given Start run clicked with harness set and submit-time probe returning `ok=false, failing_reason="gateway unreachable"`, when the probe resolves, then `POST /runs` is not called and the PRE-FLIGHT section shows `"x · HARNESS · gateway unreachable"`
- Given `HarnessList` rendered without `probeResults` prop (unit-test path), when `harness.enabled = false`, then the radio is disabled (backward-compat fallback preserved for unit tests)
- Given `make lint` runs, then ruff, mypy, import-linter, tsc, eslint, prettier, env-contract, check_test_pairs, gen:api --check all pass

## Spec Change Log

## Review Triage Log

## Design Notes

**`runProbe()` implementation:**
```ts
async function runProbe(name: string): Promise<void> {
  const seq = ++probeSeqRef.current;
  setProbeInFlight(true);
  try {
    const { data } = await api.GET('/harnesses/{name}/probe', { params: { path: { name } } });
    if (seq !== probeSeqRef.current) return;
    if (data) {
      setProbeResults((prev) => ({ ...prev, [name]: data }));
      if (!data.ok) {
        // probe failed — clear selection so the now-disabled radio doesn't stay checked
        setState((prev) => (prev.harness === name ? { ...prev, harness: '', model: '' } : prev));
      } else {
        // clear model if it isn't in the new probed list (non-empty list only)
        setState((prev) =>
          prev.harness === name && data.models.length > 0 && !data.models.includes(prev.model)
            ? { ...prev, model: '' }
            : prev,
        );
      }
    }
  } finally {
    if (seq === probeSeqRef.current) setProbeInFlight(false);
  }
}
```

**`startRun()` probe guard:** add before the existing `runBody` null check:
```ts
if (state.harness) {
  const { data: probe } = await api.GET('/harnesses/{name}/probe',
    { params: { path: { name: state.harness } } });
  if (probe && !probe.ok) {
    setProbeResults((prev) => ({ ...prev, [state.harness]: probe }));
    setPreflight({
      lines: [{ check: 'HARNESS', status: 'fail',
                text: probe.failing_reason ?? 'probe failed', fix: null }],
      start_allowed: false, queue_note: '', rows: null, plan_error: null,
    });
    return;
  }
}
```
`setStarting(true)` should be called before the probe, `setStarting(false)` in the `finally` block (as currently structured), so the Start button is visibly in-progress during the guard.

**Harness-change `onSelect` handler:** call `update()` for the state + plan\_run scheduling, then call `runProbe()` in addition — `update()` already sets `pending=true` and schedules the debounce. `withHarness` (state.ts:122) is no longer called; the harness-change path always clears model inline (`{...state, harness: name, model: ''}`):
```ts
onSelect={(name) => {
  update({ ...stateRef.current, harness: name, model: '' });
  void runProbe(name);
}}
```

**Island line count:** `NewWorkflow.tsx` is 230 lines; `runProbe` adds ~20 lines, the submit guard ~10 lines, and minor state additions ~5 lines — stays under the 300-line limit.

**`probeResults` prop semantics:** `undefined` (no prop) → fallback to `harness.enabled`; object (even `{}`) → probe-based. The island always passes an object, so the fallback only applies to unit tests. This preserves the existing `harness-list.test.ts` assertions without modification.

## Verification

**Commands:**
- `make lint` — expected: ruff, mypy, import-linter, prettier, tsc, eslint, env-contract, check_test_pairs, gen:api --check all pass
- `make test` — expected: all unit tests green including new `harness-list-probe.test.ts` and `newwf-state-probe.test.ts`
- `make e2e-ui` — expected: `new-workflow-probe.spec.ts` and (after exception-4 revision) `new-workflow.spec.ts` all pass

## Auto Run Result

Status: blocked
Blocking condition: exception-4 authorization required for two tests in `web-client/tests/e2e/new-workflow.spec.ts` before the implementation agent may proceed.

**Tests that conflict with the probe model:**

1. `new-workflow.spec.ts:107` (`'a disabled harness reads its own line and is not selectable'`) — asserts `input[type="radio"]` is disabled based on `HarnessOut.enabled: false`. After story 2-3, harnesses without a probe result are initially selectable (probe determines gating). The assertion is wrong under the probe model.

2. `new-workflow.spec.ts:393` (`'the re-run readiness link points at the endpoint and says it is not served yet'`) — same assertion: `input` is disabled; comment says "re-running readiness is what enables one". Both the assertion and the comment pin the superseded enabled-flag behavior.

**Why exception-4:** the SPEC.md and EXPERIENCE-v1 §2.1 (the Operator's UX authority) explicitly specify that the probe result — not the stored enabled flag — determines harness selectability. This is the same product decision that drove exception-4 in story 2-2 for backend tests. The frontend tests that pinned the old behavior must be revised under exception-4 by an authorized agent.

**What the revised tests should assert:**

For test 1: the radio is initially enabled; a `page.route('**/api/harnesses/*/probe', ...)` mock returning a failing result is set up; the radio is clicked; after probe resolves the radio becomes disabled and the row contains the `failing_reason` text. The test body must name the decision and date per exception-4 requirement.

For test 2: remove the `toBeDisabled()` assertion and the "re-running readiness is what enables one" comment; add assertion that the radio is initially enabled; name the decision and date per exception-4 requirement.

**What does NOT need exception-4:** `harness-list.test.ts` and `newwf-state.test.ts` are preserved unchanged by the `probeResults !== undefined` fallback design in `HarnessList` (see Design Notes).
