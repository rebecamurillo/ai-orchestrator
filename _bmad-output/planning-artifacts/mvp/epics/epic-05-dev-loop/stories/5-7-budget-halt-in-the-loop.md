---
title: 'Budget halt in the loop'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Nothing reads an attempt's real spend or stops a Run once it is over budget —
`Gateway.spend_for_attempt` (5.3), `budget.check` (5.3) and the `agent_tail` seam (5.5/5.6)
all exist with no call site, so a Run can run past its `budget_usd` indefinitely.

**Approach:** Wire `record_attempt_spend` + `budget.check` into `agent_tail.tail`'s named
5.7 seam, after routing; add a `StepResult.budget_park` field and an `apply_step_result`
`after_route` hook (`budget_second_record`) for the double gate record a routed stop needs;
fold the Claude `--max-budget-usd` cap exit into the same check.

## Boundaries & Constraints

**Always:** the row keeps the status `route` gave it; the Run parks on top via
`park_kind=budget`; `run.spend_usd` is read after every agent attempt (including a
`re_check` replay) before the verify row can start; a routed stop that already parked gets
a second gate record, never a rewritten first one; the reason is always `budget
${spend:.2f} / ${budget:.2f}`.

**Block If:** the brief conflicts with the spine on how a park combines with an existing
one — it does not; both are already declared (`Park`, `budget_park`).

**Never:** `budget_raise` (Epic 6, out of scope); closing `Harness.resume`'s missing
`budget_usd_remaining` (out of this story's named scope — see Design Notes).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Routed `done`, over budget | spend 41.20 / budget 40.00 | `status=done`, `park=budget`, one gate record | n/a |
| Routed `blocked`, over budget | as above | `park=blocked` (own record) + `budget_park=budget` (second record via `after_route`) | n/a |
| Exactly at budget | 40.00 / 40.00 | no park | n/a |
| Claude cap exit | `raw_result.stop_reason == "max_budget"` | `park=budget`, no `retry`, whatever `route` would have said discarded | n/a |
| Retry-path `error`, over budget | unexpected status, retry available, over budget | `park=budget`, `retry=None` — no `retry_auto` record | n/a |
| No `spend_writes` wired | `ctx.ports.spend_writes is None` | budget check skipped entirely (degrades like `tracer`) | n/a |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/steps/agent_tail.py` — `tail`'s `# 5.7` seam
  (immediately after `route(...)`, before `output_ref`); `_spend_and_budget`/`_cap_exit`
  added. 350 → 400/400 (all the room this story had).
- `backend-api/src/orchestrator/application/use_cases/spend.py` — `record_attempt_spend`
  changed `-> None` to `-> Run`, returning the updated Run (`set_run`'s own shape) so the
  budget check needs no second repository round trip. No frozen test captures the old
  return value.
- `backend-api/src/orchestrator/application/rules/budget.py` — `check` now delegates to a
  new `forced(run) -> Park`, the unconditional park the Claude cap exit needs (the harness
  already stopped itself; the ordinary `<=` comparison would be beside the point).
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` — new
  `budget_second_record(ports, run, row, result)`: the `after_route` seam the module's own
  docstring already named ("Epic 5's seam ... nothing in Epic 4 passes it"). `set_run`, not
  `park_run`: `RUN_TRANSITIONS` has no `(needs_you, "park")` pair, and the Run is already
  parked by the first write.
- `backend-api/src/orchestrator/application/use_cases/walk.py` — `apply_result` always
  binds the hook via a new `_budget_hook(writers)`, unconditionally (this is Epic 5).
- `backend-api/src/orchestrator/application/steps/context.py` — new `StepPorts.spend_writes:
  SpendWrites | None`, a `SpendPorts` scope of its own: `attempt_writes`'s `WriterPorts`
  refuses `.runs`/`.steps` by the executor's own convention (AD-8), and the budget read
  needs both. Degrades like `tracer` (skip), not like `harnesses` (raise) — every fixture
  this story predates wires none.
- `backend-api/src/orchestrator/domain/values.py` — `StepResult.budget_park: Park | None`,
  the second park's own channel, distinct from `.park` (the routed stop's).
- `backend-api/src/orchestrator/infrastructure/db/writers.py` — `open_spend_ports`, the
  real `SpendPorts` scope, beside `open_writer_ports`.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — `walker_deps` builds one
  shared `httpx.Client` (`base_url=settings.litellm_base_url`,
  `timeout=SPEND_TIMEOUT_SECONDS=10.0`), `LiteLLMSpend(settings, client)`, and wires
  `spend_writes=partial(open_spend_ports, session_factory, gateway)`.

## Tasks & Acceptance

**Execution:**
- `agent_tail.py` -- add `_spend_and_budget`/`_cap_exit`, call from the named seam -- the
  brief's whole "In" scope.
- `spend.py` -- `record_attempt_spend` returns the updated `Run` -- the budget check's own
  input, without a second read.
- `budget.py` -- add `forced` -- the cap-exit path's unconditional park.
- `apply_step_result.py` -- add `budget_second_record` -- the double gate record.
- `walk.py` -- `apply_result` binds it -- the wiring the docstring already promised.
- `context.py`, `domain/values.py`, `infrastructure/db/writers.py`,
  `infrastructure/dbos/startup.py` -- the new port, field, real scope and its wiring.

**Acceptance Criteria:** the five given in the I/O matrix above, taken verbatim from the
brief's own AC list.

## Design Notes

**The resume `budget_usd_remaining` gap is left open.** `Harness.resume` takes neither
`model` nor a budget cap (`domain/ports/harness.py:202-214`, `adapter.py:217`
`budget_usd_remaining=None` on the resume path); AD-14 and CAP-7 both want a resumed
dispatch to carry the same discipline a fresh one does. Closing it means changing the
`Harness` protocol's `resume` signature — frozen by `test_harness_port.py`/
`test_claude_adapter.py` (anchors) — and every adapter/caller that implements or calls it,
none of which this brief's "In" list names (`record_attempt_spend`, `budget.check`, the
`budget` park, the double gate record, the Claude cap exit). That is a structural,
cross-story change the brief does not authorize; closing it here would be exactly the
"no structural decisions on your own" the dispatch forbids. Left for a story that names it.

**Why `budget_park` is a new field rather than overloading `.park`.** A routed stop
(`blocked`/`checkpoint`/`misconfigured`) already carries its own `Park` on `.park` before
5.7 runs; overwriting it would erase the routed stop's own gate record. The two-record
brief text ("the routed stop's record, then budget") is only satisfiable with a second
channel `apply_step_result`'s `after_route` can read after the first write has already
happened. `misconfigured` is treated the same as `blocked`/`checkpoint` here (any routed
stop that already carries a `.park`) even though the brief's own prose names only "blocked
or checkpoint" — no AC exercises `misconfigured` + over-budget, and dropping its own gate
record to make room for `budget` (the `done`/retry-path shape) would lose the reason a
misconfigured stop exists to report; the general reading is the one that loses nothing.

**Why `record_attempt_spend`/`budget.check` run from inside `agent_tail.tail`, not from
`apply_step_result`.** The brief's own implementation note says "extend `_tail`"; AD-9's
tail order also puts spend after routing and before the result is returned, i.e. before the
verify row can start — which only the executor itself can guarantee, since `apply_step_result`
runs later, after the walker has already decided to advance.

**Why `spend_writes` is its own `StepPorts` field, not folded into `attempt_writes`.**
`tests/unit/application/steps/agent_fixtures.py::_writes` (frozen, AD-18) builds
`WriterPorts` with `runs`/`steps`/`records` all `_refused` — any access raises — because the
agent kind's *attempt* writes never touch those repositories. The budget read genuinely
needs `runs.update` (to write `run.spend_usd`) and `steps.list_for_run` (to resum it), so it
needs a scope `attempt_writes` structurally cannot give it.

**The Claude cap-exit field is one constant, not yet confirmed.**
`agent_tail.CAP_EXIT_FIELD = "stop_reason"`, `CAP_EXIT_VALUE = "max_budget"` — the brief's
own literal guess (`raw_result.get("stop_reason") == "max_budget"`), held behind these two
names so 5.11 closes the loop by editing them alone once the real CLI is observed.

## Verification

**Commands:**
- `make lint` -- expected: exit 0.
- `make test` -- expected: exit 0; `domain/`+`application/` 100% branch.
- `make openapi` -- expected: exit 0, no drift (`StepResult` never crosses the wire).
- `make e2e-api` / `make e2e-ui` -- not run: no route, no schema field, no UI this story
  adds; same reasoning 5.6 used.

## Auto Run Result

Status: done

**What was implemented.** `agent_tail.tail`'s `# 5.7` seam now records this attempt's spend
through the Gateway (`record_attempt_spend`, changed to return the updated `Run`) and parks
`budget` on top of whatever `route` decided — a routed `done`/retry-path `error` gets the
budget `Park` directly (dropping any `retry`), a routed stop that already parked
(`blocked`/`checkpoint`/`misconfigured`) gets a second one via the new `StepResult.budget_park`
field, and a Claude `--max-budget-usd` cap exit (`raw_result.stop_reason == "max_budget"`,
one named constant pair, `[ASSUMPTION]`) short-circuits the whole decision to a `budget`
park regardless of what `route` would have said, with no `retry`. `apply_step_result` gained
`budget_second_record`, the `after_route` hook its own docstring had already named as
"Epic 5's seam" — it rewrites `park_kind`/`park_path`/`park_reason` and appends the second
gate record via `set_run`, not `park_run`, because the Run is already `needs_you` and
`RUN_TRANSITIONS` has no second `(needs_you, "park")` pair. `walk.apply_result` binds this
hook unconditionally. The budget read runs through a new `StepPorts.spend_writes` scope —
separate from `attempt_writes`, whose `WriterPorts` the agent kind's own frozen fixture
refuses `.runs`/`.steps` on — wired for real in `infrastructure/dbos/startup.py` over
`LiteLLMSpend` and one shared `httpx.Client` (`timeout=10.0s`, explicit, not httpx's 5s
default). `spend_writes` degrades like `tracer` (skip) rather than raising, so every
fixture predating this story keeps working unchanged.

**The resume `budget_usd_remaining` gap was left open, deliberately** — see Design Notes.
It requires changing the frozen `Harness.resume` signature, which is outside this brief's
named scope.

**Files changed (8 added, 9 modified):**
- `application/steps/agent_tail.py` — modified: `_spend_and_budget`, `_cap_exit`,
  `CAP_EXIT_FIELD`/`CAP_EXIT_VALUE`, the seam call. 350 → 400.
- `application/use_cases/spend.py` — modified: `record_attempt_spend` returns `Run`.
- `application/rules/budget.py` — modified: `forced`, `check` delegates to it.
- `application/use_cases/apply_step_result.py` — modified: `budget_second_record`.
- `application/use_cases/walk.py` — modified: `_budget_hook`, `apply_result` binds it;
  docstring trimmed for room. 399 → 400.
- `application/steps/context.py` — modified: `SpendWrites`, `StepPorts.spend_writes`;
  docstring trimmed for room. 400 → 400.
- `domain/values.py` — modified: `StepResult.budget_park`.
- `infrastructure/db/writers.py` — modified: `open_spend_ports`.
- `infrastructure/dbos/startup.py` — modified: `SPEND_TIMEOUT_SECONDS`, the `httpx.Client`
  and `LiteLLMSpend`, `spend_writes` wiring.
- Eight new test modules: `application/test_budget_rule_forced.py`,
  `application/test_record_attempt_spend_returns_run.py`,
  `application/test_apply_step_result_budget.py`, `application/test_walk_budget_hook.py`,
  `test_spend_writer_scope.py`, `test_dbos_startup_gateway.py`,
  `application/steps/agent_budget_fixtures.py` (fixtures, additive on top of the frozen
  `agent_fixtures`/`agent_tail_fixtures`), `application/steps/test_agent_tail_budget.py`
  (the five ACs plus the cap-exit-field-mismatch and unwired-degrade cases).

**Verification performed:**
- `make lint` — exit 0: ruff, ruff format --check, mypy `--strict` over `domain/` +
  `application/`, all four import-linter contracts KEPT, env contract unchanged (31
  settings fields / 37 `.env.example` variables — no new setting), `check_test_pairs`
  167/167 backend + 71/71 web-client paired, `gen:api --check` no drift, web-client
  astro-check/eslint/prettier/tsc all clean.
- `make test` — exit 0: 4775 backend unit tests passed (4752 before this story), 1
  skipped; `domain/` + `application/` at 100% branch under `--fail-under=100`; web-client
  973 passed.
- Branch coverage measured per module (`--cov-branch`): `rules/budget.py`,
  `steps/agent_tail.py`, `steps/context.py`, `use_cases/spend.py`,
  `use_cases/apply_step_result.py`, `use_cases/walk.py` — each **100%**.
- `make openapi` — exit 0, idempotent: no drift in `contracts/openapi.json` or
  `web-client/src/api/schema.d.ts` (this story exposes nothing new over the wire).
- `make e2e-api` / `make e2e-ui` — not run: no route, no schema field, no UI added.
- Anchor check (the literal command from the dispatch instructions) — flags only
  `tests/unit/fakes/{clock,git,workspace}.py`, all three from earlier stories on this
  branch, none touched here. No pre-existing test file, `SPEC.md`, `stories.yaml`, `epics.yaml`
  or `AGENTS.md` was edited.

**Follow-up review recommended:** false. Self-reviewed against the brief's five ACs (all
five pass as unit tests), the spine's AD-8/AD-9/AD-11, and the carried-forward gap; no
subagent review pass was run for this dispatch.
