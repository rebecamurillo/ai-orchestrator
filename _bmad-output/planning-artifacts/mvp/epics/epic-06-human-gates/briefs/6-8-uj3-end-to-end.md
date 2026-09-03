---
story: "6-8"
epic: 6
title: UJ-3 proven end to end
requirements: [FR-18, FR-19, FR-20, SM-2, UJ-3]
binds: [AD-13, AD-18]
---

# Story 6.8 — UJ-3 proven end to end

As the Operator,
I want the whole "come back cold and unblock" journey exercised by tests that drive the real stack with a scripted harness,
So that the gates are known to work together, not one by one.

## Scope

**In:** e2e scenarios in `tests/e2e/test_uj3.py` (API-driven, `ORCH_TEST_MODE=1`, the gates fixture) and one Playwright journey in `tests/e2e/uj3.spec.ts` with `E2E_BACKEND=real`; small fixes they reveal.
**Out:** new features.

## Binding rules (inlined)

- **Scenario A — blocked → answer → done.** Start `epic@1` on the gates fixture with harness `fake`; story `1`'s scenario: attempt 1 `blocked · intent gap`, attempt 2 `done` + commit + echo prompt. Assert: park `blocked` with the Question text; `answer` → the Run is `running` within one poll (API read ≤ 5 s); the archived file with `## Human Answer`; the new story file echoes the Answer suffix; verify `done`; commit-guard `no changes`; trajectory row with the `answer` human action.
- **Scenario B — spec checkpoint → continue.** Story `2` (`spec_checkpoint: true`): attempt 1 writes `ready-for-dev`; assert park `checkpoint · spec checkpoint`, the file readable through `GET /runs/{id}/files`; `continue` → attempt 2 prompt has no halt suffix; scenario writes `done` + commit; verify done.
- **Scenario C — verify failed twice → skip story.** Story `3` (`done_checkpoint: true`): attempt 1 `done` + commit but the fixture's `GATE_OK` file is removed by the scenario (`files:` with a deletion marker `[add `delete: [paths]` to the fake scenario schema]`) so verify fails; the redispatch attempt (status `in-progress` with `## Verify Failure` present — assert it) fails verify again; park `verify_failed · verify failed 2/2`; `skip_story` → verify re-runs (scenario restores `GATE_OK` through an operator `PUT /runs/{id}/files` before the skip) and passes; commit-guard `story 3: skipped by operator`; the done checkpoint is skipped too (it belongs to the frame); push and link run; the Run ends `done` with `summary.skipped == ["3"]`.
- **Scenario D — cancel while parked.** A second Run parked `blocked`; `cancel {confirm: true}` → `cancelled`, the worktree removed, the branch (created, never pushed) deleted on the local origin.
- **Playwright journey (UX).** With the real stack: open the `BLK` card from the Board, read the Question, type the Answer, click *Resume with answer*, see the card back in Running on the next poll, then at the checkpoint click *Continue*, and at the end see `DON` with the compare link and the skipped id; assert the active-time figure is not required (Epic 8).
- **Timing:** each API scenario under 3 minutes; the journey under 5.

## Acceptance criteria

**Given** the compose stack in test mode
**When** `make e2e-api` runs the `uj3` marker
**Then** scenarios A–D pass with every assertion above and print each Run's gate record.

**Given** `E2E_BACKEND=real`
**When** `make e2e-ui` runs the journey
**Then** it passes on the same stack.

**Given** any fix made along the way
**When** `make lint test` runs
**Then** it is unit-covered and green.

## Implementation notes

- Extend the fake scenario schema with `delete: [paths]` (6.1's adapter) and document it in the adapter's docstring.
- Helpers `wait_for_status(run_id, status)`, `signal(run_id, kind, payload)`.

## Verification

```bash
ORCH_TEST_MODE=1 make up && make e2e-api && E2E_BACKEND=real make e2e-ui
```

## Sources for detail only

PRD UJ-3, FR-18..FR-20, SM-2. Spine AD-13, AD-18.
