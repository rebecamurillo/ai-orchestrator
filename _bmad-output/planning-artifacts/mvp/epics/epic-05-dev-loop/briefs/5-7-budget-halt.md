---
story: "5-7"
epic: 5
title: Budget halt in the loop
requirements: [FR-10 (budget after every attempt), FR-14 (cap exit), FR-17, AR-13]
binds: [AD-8, AD-9, AD-10, AD-11]
---

# Story 5.7 — Budget halt in the loop

As the Operator,
I want a Run to stop before the next model call once it has spent more than I allowed, and to tell me the exact figures,
So that a Run can never exceed its budget by more than one attempt.

## Scope

**In:** the last part of the agent tail — `record_attempt_spend` after every agent attempt (retries included), `budget.check`, the `budget` park that keeps the row's routed status, the double gate record, the Claude cap exit mapped to the budget park, tests.
**Out:** `budget_raise` (Epic 6).

## Binding rules (inlined)

- **When.** After the harness exits and after routing, before the result is returned (so before the verify row can start): `record_attempt_spend(run, attempt, harness_result.usage)` (5.3) → `park = budget.check(run)`.
- **How the park combines with routing (AD-8, AD-11).** The row keeps the status routing gave it (`done`, `blocked`, `checkpoint`, or `error` with retry) and the result carries `park = Park{budget, "budget ${spend} / ${budget}"}`; `apply_step_result` writes two gate records when the routed status was itself a stop (`blocked` or `checkpoint`): first the routed stop's record, then `budget`, and sets `run.park_kind = budget` with `park_path` the row. A routed `done` with a budget park parks the Run before verify; a `budget_raise` (Epic 6) then continues at the verify row. A retry-path `error` with a budget park is parked (no automatic retry) with `park_kind = budget`.
- **Claude cap exit (AD-10, FR-14).** The adapter passes `--max-budget-usd = remaining`; when `HarnessResult.raw_result` shows the harness stopped for its own budget cap (`[field per addendum §B after verification, e.g. a stop reason]`), the tail treats it as `Park{budget, …}` computed from the recorded spend, never as an expect miss and never as a retry.
- **No further process.** While `park_kind == budget` no harness process is started (the walker is parked); the readout shows `budget $41.20 / $40.00`.
- **Provisional spend counts.** The check uses `run.spend_usd` whether or not the latest attempt is provisional (FR-17); the figure is marked `provisional` in the read model.

## Acceptance criteria

**Given** a routed `done` attempt whose spend brings `run.spend_usd` to 41.20 against a 40.00 budget
**When** the tail finishes
**Then** the result is `done` with park `budget · budget $41.20 / $40.00`; `apply_step_result` writes one `budget` record, the Run is `needs_you` with `park_kind budget`, and the verify row stays `planned`.

**Given** a routed `blocked` attempt over budget
**When** applied
**Then** two records are written in order (`blocked` then `budget`), `park_kind` is `budget`, and the row is `blocked`.

**Given** an attempt exactly at budget (`40.00 / 40.00`)
**When** checked
**Then** no park.

**Given** a harness result whose raw result marks a budget-cap stop
**When** the tail runs
**Then** the park is `budget`, `retry_count` is unchanged, and no `retry_auto` record exists.

**Given** a retry-path `error` (unexpected status) that is also over budget
**When** applied
**Then** the Run parks with `park_kind budget` and the row is `error` with no automatic retry.

## Implementation notes

- Extend `_tail` (5.5) with `_spend_and_budget(ctx, result)`; extend `apply_step_result` for the double record (covered).
- Record the cap-exit field name in `addendum.md` §B once 5.11 verifies it; until then read `raw_result.get("stop_reason") == "max_budget"` behind a single constant `[ASSUMPTION]`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-17, FR-10 (bounds), FR-14 (cap). Spine AD-11 (budget rule and routed status), AD-8 (double record), AD-10 (`--max-budget-usd`). `addendum.md` §G Budget check timing.
