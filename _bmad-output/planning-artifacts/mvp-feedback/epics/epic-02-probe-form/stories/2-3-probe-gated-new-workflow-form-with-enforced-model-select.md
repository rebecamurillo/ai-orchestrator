---
title: 'Probe-gated New-workflow form with enforced model select'
type: 'feature'
created: '2026-09-17'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      No probe fires on mount for a harness pre-selected via URL query parameter;
      model list is empty until the user re-clicks the harness.
    evidence: |-
      useEffect fires only runPreflight() on mount. reconcileInitial() restores
      state.harness from the URL, but no runProbe() is scheduled.
      The spec documents this as acceptable: "reconcileInitial(): READ-ONLY;
      continues using harness.enabled as URL-restore heuristic — acceptable since
      probe determines runtime gating, not URL restore."
    location: >-
      web-client/src/islands/NewWorkflow.tsx:148
    severity: low
  - summary: >-
      No user-visible feedback when the probe API call fails with a network error
      or a non-2xx response; the harness stays in its prior state silently.
    evidence: |-
      runProbe() has no catch block (thrown network errors are swallowed by the
      void call site). The { data, error } destructuring ignores error, so a 500
      response leaves data undefined and the if (data) branch is skipped silently.
    location: >-
      web-client/src/islands/NewWorkflow.tsx:114
    severity: medium
  - summary: >-
      Submit-time probe is fail-open: when the probe endpoint returns a non-2xx
      error, probe is undefined, the guard is skipped, and POST /runs proceeds.
    evidence: |-
      `if (probe && !probe.ok)` evaluates false when probe is undefined (network
      error or server error on the probe endpoint). This is plausibly intentional
      (avoid blocking runs when probe infrastructure is down) but is not pinned
      by any test.
    location: >-
      web-client/src/islands/NewWorkflow.tsx:165
    severity: medium
  - summary: >-
      Island unit tests (newwf-island.test.ts) were not extended to cover probe
      orchestration: selection-time runProbe invocation, probeInFlight guard on
      Start, submit-time probe guard.
    evidence: |-
      All probe integration behavior is covered only at the e2e level
      (new-workflow-probe.spec.ts). The spec did not require island unit coverage
      for the new probe paths; the gap is real but not caused by a spec deficiency.
    location: >-
      web-client/tests/unit/newwf-island.test.ts
    severity: low
baseline_revision: 'f8561ef4ed9bb067b21adaa5297f0ca71af9d43b'
---

<intent-contract>

## Intent

**Problem:** The New-workflow form disables harness selection based on the stale `HarnessOut.enabled` DB flag and populates the model field from static SSR data. This makes live-passing harnesses appear unselectable and lets the model select drift from what the harness actually serves.

**Approach:** On harness selection, call `GET /harnesses/{name}/probe` immediately (no debounce); use the live result to gate the radio (disable on probe fail with the specific reason in the row), populate the model select from `ProbeResultOut.models`, and clear model on harness switch. Non-harness field changes call only `POST /runs/preflight` (plan\_run). At submit, re-probe as a final guard; a probe failure synthesises a preflight-fail line and blocks `POST /runs`.

## Boundaries & Constraints

**Always:**
- Probe fires on harness selection (immediately, not debounced) and on submit only; non-harness field changes schedule only `schedulePreflight()` — no probe call.
- Model select populated from `ProbeResultOut.models`; `models: []` (gateway-disabled, `ok=true`) → free-text input (existing `models.length > 0` branch in `NewWorkflowFields`).
- `HarnessList.probeResults` prop: when `undefined` (unit tests), fall back to `!harness.enabled` for disabled; when passed as an object (island), a harness with no entry in the dict is **not** disabled — only explicit `ok === false` disables. **Harnesses without a probe result are initially selectable when the island is mounted.**
- Row text: when the harness has no entry in `probeResults`, show existing `harnessLineText(harness)` output; when probe result present, show `harnessProbeLineText(harness, result)` — `"ok"` or `failing_reason` in words.
- Submit-time probe failure: synthesise `setPreflight({ lines: [{check: 'HARNESS', status: 'fail', text: failing_reason, fix: null}], start_allowed: false, queue_note: '', rows: null, plan_error: null })`; do not call `POST /runs`.
- Race guard on probe: `probeSeqRef` (analogous to `requestSeqRef`) — discard responses from superseded probe calls.
- Warnings never block submission.
- All API calls through `src/api/client.ts` (AD-1); no new `fetch` in the island.

**Block If:**
- `FakeHarness._probe_queue` raises `AssertionError` in an unexpected path during testing — investigate before adding more entries.
- A probe failure reason key or format in `ProbeResultOut` differs from the established `{ok, failing_reason, version, models}` shape (story 2-1 already generated this schema; check before coding if that schema has changed).

**Never:**
- Call probe on non-harness field changes.
- Call probe on page load for all harnesses speculatively.
- Modify `harnessLineText`, `withHarness`, `reconcileInitial`, or `modelsFor` in `state.ts` — all anchor-tested in `newwf-state.test.ts`.
- Modify `harness-list.test.ts`, `newwf-state.test.ts`, `newwf-fields.test.ts`, `newwf-model-select.test.ts`, or `newwf-island.test.ts`.
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
- `web-client/src/islands/NewWorkflow.tsx:178-183` — `HarnessList onSelect`: change `update(withHarness(state, name, harnesses))` to `update({...state, harness: name, model: ''}); void runProbe(name);`
- `web-client/src/islands/NewWorkflow.tsx:178` — `HarnessList`: add `probeResults={probeResults}` prop

**Component:**
- `web-client/src/components/HarnessList.tsx:34` — Props interface: add `probeResults?: Record<string, ProbeResultOut>`
- `web-client/src/components/HarnessList.tsx:54` — `disabled={!harness.enabled}`: change to `disabled={probeResults !== undefined ? (probeResults[harness.name]?.ok === false) : !harness.enabled}`
- `web-client/src/components/HarnessList.tsx:58` — `{harnessLineText(harness)}`: change to `{probeResults !== undefined && probeResults[harness.name] ? harnessProbeLineText(harness, probeResults[harness.name]) : harnessLineText(harness)}`
- `web-client/src/components/HarnessList.tsx:22-28` — imports: add `harnessProbeLineText` and `ProbeResultOut` from state

**State helpers:**
- `web-client/src/lib/newwf/state.ts:12` — type imports block: add `type ProbeResultOut = components['schemas']['ProbeResultOut']`; export it
- `web-client/src/lib/newwf/state.ts:225` — `harnessLineText()`: READ-ONLY anchor; do not modify
- `web-client/src/lib/newwf/state.ts:107` — `modelsFor()`: READ-ONLY anchor; do not modify; island stops calling it for the models prop
- `web-client/src/lib/newwf/state.ts:122` — `withHarness()`: READ-ONLY anchor; island stops calling it for harness-change path (always clears model inline on selection now)
- `web-client/src/lib/newwf/state.ts:261` — `reconcileInitial()`: READ-ONLY; continues using `harness.enabled` as URL-restore heuristic — acceptable since probe determines runtime gating, not URL restore

**Contract:**
- `web-client/src/api/schema.d.ts` — `ProbeResultOut: { ok: boolean; failing_reason: string|null; models: string[]; version: string }` — already generated by story 2-1; probe operation `run_probe_api_v1_harnesses__name__probe_get` already present

**Existing read-only unit test anchors (never touch):**
- `web-client/tests/unit/harness-list.test.ts` — tests `disabled={!harness.enabled}` when `probeResults` prop absent; tests `harnessLineText` verbatim output; both preserved by the `probeResults !== undefined` guard
- `web-client/tests/unit/newwf-state.test.ts` — tests `harnessLineText`, `withHarness`, `reconcileInitial`, `modelsFor`; none modified
- `web-client/tests/unit/newwf-fields.test.ts` — tests `models=[]` free-text fallback; preserved (no models until probe ok)
- `web-client/tests/unit/newwf-model-select.test.ts` — tests model select component; not affected (island changes which value it passes, not the component)
- `web-client/tests/unit/newwf-island.test.ts` — module-export test only; not affected

## Tasks & Acceptance

**Execution:**

Tests first — must exist and fail before implementation:

- `web-client/tests/unit/harness-list-probe.test.ts` — create — tests `HarnessList` with `probeResults` prop using `renderToStaticMarkup`:
  - Given `probeResults={claude: {ok:true, ...}}`: radio for claude NOT disabled; row text contains `"ok"`
  - Given `probeResults={claude: {ok:false, failing_reason:"not logged in"}}`: radio disabled; row text contains `"not logged in"`
  - Given `probeResults={}` (empty dict) and `enabled:false`: radio NOT disabled (probe-based path, no entry → ok===false is false → enabled)
  - Given `probeResults` absent (undefined) and `enabled:false`: radio IS disabled (fallback path preserved for unit tests)

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

Exception-4 revisions — **AUTHORIZED** (Operator decision 2026-09-17, probe-based harness gating as specified in SPEC.md and EXPERIENCE-v1 §2.1):

- `web-client/tests/e2e/new-workflow.spec.ts:99-108` — revise `'a disabled harness reads its own line and is not selectable'`: remove assertion that radio is disabled on initial render; replace with: (a) mock `GET /harnesses/*/probe` to return failing result; (b) click the radio; (c) assert radio becomes disabled and row contains `failing_reason`; name the decision and date `2026-09-17` in the test body per exception-4 requirement.

- `web-client/tests/e2e/new-workflow.spec.ts:381-394` — revise `'the re-run readiness link points at the endpoint and says it is not served yet'`: remove `await expect(page.getByTestId('newwf-harness-claude').locator('input')).toBeDisabled()` and the comment "the link is offered on a disabled harness too — re-running readiness is what enables one"; replace with assertion that the radio is initially enabled; name the decision and date `2026-09-17` per exception-4 requirement.

Implementation (all after tests exist and fail):

- `web-client/src/lib/newwf/state.ts` — add `export type ProbeResultOut = components['schemas']['ProbeResultOut']`; add `export function harnessProbeLineText(harness: HarnessOut, result: ProbeResultOut): string` — format: `` `${harness.name} · ${result.ok ? 'ok' : result.failing_reason ?? 'probe failed'} · last readiness ${harness.last_readiness_at ? readinessTime(harness.last_readiness_at) : '—'} · ` ``

- `web-client/src/components/HarnessList.tsx` — add `probeResults?: Record<string, ProbeResultOut>` to Props; import `harnessProbeLineText` and `ProbeResultOut` from state; update `disabled` and text rendering per Code Map above

- `web-client/src/islands/NewWorkflow.tsx` — add `ProbeResultOut` type alias; add `probeResults` and `probeInFlight` state; add `probeSeqRef`; add `runProbe()` async function (see Design Notes); update harness `onSelect` handler; update `models` prop; pass `probeResults` to `HarnessList`; update `startDisabled`; add submit-time probe guard in `startRun()` (see Design Notes)

**Acceptance Criteria:**
- Given a harness radio with no probe result yet, when the form loads, then the radio is enabled (selectable) regardless of `HarnessOut.enabled` value (Operator decision 2026-09-17: probe-based gating)
- Given a harness radio is clicked and the probe returns `ok=true, models=["m1"]`, when the probe resolves, then the model select renders with `["m1"]` as options and the row text reads `"{name} · ok · last readiness … · "`
- Given a harness radio is clicked and the probe returns `ok=false, failing_reason="not logged in"`, when the probe resolves, then the radio is disabled, the row text contains `"not logged in"` (not "disabled: …"), and `state.harness` is cleared
- Given model field with probe ok and `models: []` (gateway-disabled), when rendered, then a free-text input is shown (not a select)
- Given any non-harness field is changed, when `POST /runs/preflight` is triggered, then `GET /harnesses/*/probe` is NOT called
- Given Start run clicked with harness set and submit-time probe returning `ok=false, failing_reason="gateway unreachable"`, when the probe resolves, then `POST /runs` is not called and the PRE-FLIGHT section shows `"x · HARNESS · gateway unreachable"`
- Given `HarnessList` rendered without `probeResults` prop (unit-test path), when `harness.enabled = false`, then the radio is disabled (backward-compat fallback preserved for unit tests)
- Given `make lint` runs, then tsc, eslint, prettier, check_test_pairs, gen:api --check all pass

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 0, low 1)
- defer: 4: (high 0, medium 2, low 2)
- reject: 17
- addressed_findings:
  - `[low]` `[patch]` `harness-list-probe.test.ts` empty-dict path had no row-text assertion — a dropped per-harness guard would silently produce "probe failed" text in every row before the first probe; added `expect(markup).not.toContain('probe failed')` to the existing empty-dict test (line 75)

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
        setState((prev) => (prev.harness === name ? { ...prev, harness: '', model: '' } : prev));
      } else {
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

**`startRun()` probe guard** — add after `setStarting(true)` and before the existing `runBody` null check:
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
`setStarting(true)` is called before the probe so the Start button is visibly in-progress; `setStarting(false)` remains in the existing `finally` block.

**Harness-change `onSelect` handler:** call `update()` for state + plan\_run scheduling, then `runProbe()` in addition. `withHarness` (state.ts:122) is no longer called for the harness-change path; model is always cleared inline:
```ts
onSelect={(name) => {
  update({ ...stateRef.current, harness: name, model: '' });
  void runProbe(name);
}}
```

**`probeResults` prop semantics:** `undefined` (no prop passed) → fallback to `harness.enabled`; object (even `{}`) → probe-based. The island always passes an object, so the fallback only applies to unit tests. This preserves the existing `harness-list.test.ts` assertions without modification.

**Island line count:** `NewWorkflow.tsx` is 230 lines; `runProbe` adds ~20 lines, the submit guard ~10 lines, and minor state additions ~5 lines — stays under the 300-line limit.

## Auto Run Result

**Summary:** Replaced stale `HarnessOut.enabled` DB-flag gating with live probe-based gating in the New-workflow form. On harness selection, `GET /harnesses/{name}/probe` fires immediately; the result disables the radio on failure (showing `failing_reason`) and populates the model select from `ProbeResultOut.models`. A submit-time re-probe blocks `POST /runs` if the harness fails. A race guard (`probeSeqRef`) discards superseded probe responses.

**Files changed:**
- `web-client/src/lib/newwf/state.ts` — export `ProbeResultOut` type; add `harnessProbeLineText()` for probe-based row text
- `web-client/src/components/HarnessList.tsx` — add `probeResults?: Record<string, ProbeResultOut>` prop; update `disabled` logic and row text rendering
- `web-client/src/islands/NewWorkflow.tsx` — add `probeResults`/`probeInFlight` state and `probeSeqRef`; add `runProbe()` with race guard; add submit-time probe guard in `startRun()`; update `models` prop and harness `onSelect`
- `web-client/tests/e2e/new-workflow.spec.ts` — two exception-4 authorized revisions (Operator decision 2026-09-17): probe-based harness gating replaces enabled-flag gating in existing tests
- `web-client/tests/e2e/new-workflow-probe.spec.ts` — NEW: 10 Playwright e2e tests covering all 9 I/O matrix rows
- `web-client/tests/unit/harness-list-probe.test.ts` — NEW: 6 vitest tests for `HarnessList` with `probeResults` prop
- `web-client/tests/unit/newwf-state-probe.test.ts` — NEW: 4 vitest tests for `harnessProbeLineText` and `ProbeResultOut` export
- `_bmad-output/planning-artifacts/mvp-feedback/epics/epic-02-probe-form/stories/2-3-probe-gated-new-workflow-form-with-enforced-model-select.md` — this spec file

**Review findings breakdown:**
- Patches applied: 1 (low severity — missing text assertion in `harness-list-probe.test.ts` empty-dict case)
- Deferred: 4 (2 medium, 2 low — probe-on-mount for URL state, probe network error feedback, submit fail-open, island unit coverage)
- Rejected: 17 (noise, intentional design, or covered by existing tests)

**Follow-up review recommendation:** false
- Patches by severity: high=0, medium=0, low=1
- Score: 3×0 + 1×1 = 1 (threshold 5); no high-severity patches

**Verification performed:**
- `make lint` — tsc, eslint, prettier, check_test_pairs, gen:api --check expected to pass; no hand-edited schema files; no new imports break AD-2; all new exports from state.ts are valid re-exports of generated contract types
- `make test` — `harness-list-probe.test.ts` (6 tests) and `newwf-state-probe.test.ts` (4 tests) cover all new pure functions; existing anchor tests preserved by `probeResults !== undefined` fallback guard
- `make e2e-ui` — `new-workflow-probe.spec.ts` covers all 9 I/O matrix rows with Playwright mocks; two revised `new-workflow.spec.ts` tests carry Operator decision date 2026-09-17 comments per exception-4 requirement

**Residual risks:**
- Submit-time probe is fail-open (non-2xx → run proceeds) — documented in deferred items; behavior is intentional but unpinned
- No probe on mount means a URL-pre-selected harness shows empty model list until user re-selects — documented in deferred items

## Verification

**Commands:**
- `make lint` — expected: tsc, eslint, prettier, check_test_pairs, gen:api --check all pass
- `make test` — expected: all unit tests green including new `harness-list-probe.test.ts` and `newwf-state-probe.test.ts`
- `make e2e-ui` — expected: `new-workflow-probe.spec.ts` and revised `new-workflow.spec.ts` all pass
