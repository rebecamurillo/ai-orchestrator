# Test Automation Summary — spec-step-handling

Generated: 2026-09-25  
Spec: `_bmad-output/specs/spec-step-handling/SPEC.md`  
Stories: 1–5 (all done)

---

## Generated Tests

### Backend API E2E Tests

- [x] `backend-api/tests/e2e/test_skip_step.py` — CAP-1 (story 1): skip_step signal end-to-end on the scripted harness; asserts the parked row is marked `skipped`, the Run returns to `running`, and the gate_record names the operator. Pattern mirrors `test_skip_story.py`; needs `ORCH_TEST_MODE=1`.

### Playwright (UI) E2E Tests

- [x] `web-client/tests/e2e/run-detail-skip-step.spec.ts` — CAP-1 (story 1): Skip step ConfirmAction in a real browser. Resolves the medium-severity deferred item from story 1's review triage: `onConfirm` wiring was unverifiable from `renderToStaticMarkup`. Covers: confirm line text, posting `skip_step` exactly once, Keep posting nothing.

- [x] `web-client/tests/e2e/run-detail-cancel-running.spec.ts` — CAP-5 (story 2): Cancel button on a running/queued Run. Asserts the cancel button renders without a stop body when the Run is not parked, and that confirming posts `{kind: cancel}`. Also pins the no-cancel path (empty `admitted_signals`).

- [x] `web-client/tests/e2e/run-detail-retry-box.spec.ts` — CAP-2 + CAP-3 (story 4): RetryBox in a real browser. Covers: box always renders when `retry` admitted, session radio defaults when `replyAvailable=true`, restart-only with reason messages for `no_session`/`no_capability`, text field posts with signal payload, empty text omitted from payload.

- [x] `web-client/tests/e2e/step-detail.spec.ts` — CAP-6 (story 5): Attempts table on `/workflows/{id}/steps/{path}`. Resolves the medium-severity deferred item from story 5's review triage: `onDrawer` routing was unverifiable from `renderToStaticMarkup`. Covers: header columns, newest-first row order, pre-selection, click selection, prompt/result + reach-agent button presence, signal-coloured token cell, drawer opening.

---

## Coverage

| Story | CAP | Backend unit | Backend e2e | Frontend unit | Frontend e2e |
|-------|-----|-------------|-------------|---------------|--------------|
| 1 — Skip one step | CAP-1 | ✅ existing | ✅ new | ✅ existing | ✅ new |
| 2 — Cancel while running | CAP-5 | n/a (client-only) | n/a | ✅ existing | ✅ new |
| 3 — Local harness resumes | CAP-4 | ✅ existing | n/a (no fake local) | n/a | n/a |
| 4 — Retry instruction + resume default | CAP-2/3 | ✅ existing | n/a | ✅ existing | ✅ new |
| 5 — Attempts table | CAP-6 | n/a (client-only) | n/a | ✅ existing | ✅ new |

---

## Deferred Items Addressed

- **Story 1 (medium)**: `onConfirm` wiring for skip_step ConfirmAction — covered by `run-detail-skip-step.spec.ts`.
- **Story 5 (medium)**: `onDrawer` content-type routing — covered by `step-detail.spec.ts` (the drawer-open test).

## Remaining Deferred Items (not addressed here)

- Story 1 (medium): workspace state after skip_step on `push_rejected`/`merge_conflict` parks — no test; backend integration concern.
- Story 5 (medium): keyboard accessibility (`tabIndex`/`onKeyDown`) on `<tr>` rows — CSS/accessibility gap, no automated test.
- Story 3 (low): `resume_command` unquoted `cwd` — paths under `/work/` have no spaces; latent risk.

## Next Steps

- Run `make e2e-ui` to execute all four Playwright specs against the built web-client.
- Run `make e2e` (or `make e2e-api`) to execute `test_skip_step.py` in the disposable `aio-e2e` stack.
- Address remaining deferred items in follow-up stories if operators report keyboard navigation issues.
