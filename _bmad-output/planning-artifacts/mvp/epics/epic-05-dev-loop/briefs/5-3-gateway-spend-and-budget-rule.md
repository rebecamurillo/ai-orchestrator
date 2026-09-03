---
story: "5-3"
epic: 5
title: Gateway spend adapter and the budget rule
requirements: [FR-17 (rule), FR-26, FR-28, NFR-5, AR-13 (budget), AR-17]
binds: [AD-2, AD-5, AD-11]
---

# Story 5.3 — Gateway spend adapter and the budget rule

As the Operator,
I want every attempt's cost and tokens read from the Gateway's own spend logs by the identifiers the call carried, and one small rule that says when a Run has spent more than its budget,
So that cost per story is a fact, not a harness's estimate, and no Run ever runs away.

## Scope

**In:** `domain/ports/gateway.py`, `infrastructure/gateway/litellm_spend.py`, `tests/unit/fakes/gateway.py`, `application/rules/budget.py`, attempt cost fields written by a use case `record_attempt_spend(run, attempt)`, `run.spend_usd`, per-path sums in the read models, tests.
**Out:** the call site in the agent tail (5.7); raising the budget (Epic 6).

## Binding rules (inlined)

- **Port.** `Gateway{spend_for_attempt(run_id, attempt_id) -> AttemptSpend{usd: Decimal, tokens_in: int, tokens_out: int, by_model: {model: {usd, tokens_in, tokens_out}}, provisional: bool, calls: int}}`; `provisional=true` with zeros when the Gateway has no rows yet or is unreachable (the adapter never raises to the caller; it logs and returns provisional).
- **Adapter (AD-11, research/spend.md).** `GET {LITELLM_BASE_URL}/spend/logs/v2?end_user={run_id}&session_id={attempt_id}` with `Authorization: Bearer {LITELLM_SPEND_KEY}`; sums `spend`, `prompt_tokens`, `completion_tokens` over the returned rows, grouped by `model`; paginates if the response is paged `[verify the response shape against LiteLLM 1.99 in research/spend.md]`; 5 s timeout. `LITELLM_SPEND_KEY` is read only here.
- **`record_attempt_spend(run, attempt, harness_usage)`** (application): calls the port; if `provisional`, uses `harness_usage` (from `HarnessResult.usage`) when present, marks `attempt.cost_provisional = true`; else writes the Gateway figures with `cost_provisional = false`. Writes `attempt.cost_usd`, `tokens_in`, `tokens_out`, `model` (the dominant model by spend when the attempt's model was unset); recomputes `run.spend_usd = Σ attempt.cost_usd` over the Run's attempts. Local models cost `0` with tokens (the Gateway returns 0 spend; keep it).
- **Re-check.** A provisional attempt is re-read on the next call for the same Run (the tail of the next attempt, or a `GET /runs/{id}` read `[ASSUMPTION: the detail read triggers a cheap refresh of provisional attempts at most once per minute]`), and replaced when the Gateway has rows.
- **Budget rule.** `rules/budget.py::check(run) -> Park | None`: returns `Park{budget, "budget ${spend:.2f} / ${budget:.2f}"}` when `run.spend_usd > run.budget_usd`, else `None`. Pure, 100 % covered.
- **Read models.** `StepRow.latest.cost_usd`, `StepRow.cost_usd` (sum over the row's attempts), per-frame sums for epic and story (`stories[].cost_usd`), `cost.spent_usd = run.spend_usd`, `cost.provisional = any attempt provisional`, `cost.tokens_in/out` sums. Cost per path prefix is a SQL sum over `attempt.cost_usd` joined by `step_run.path LIKE prefix%`.
- **Layering:** `httpx` only under `infrastructure/gateway/`.

## Acceptance criteria

**Given** a stubbed spend endpoint returning three rows for the attempt (two models)
**When** `spend_for_attempt` is called
**Then** the sum and the per-model breakdown are right and `provisional` is false; **and** with an empty list or a connection error, `provisional` is true with zeros and a log line.

**Given** a provisional Gateway answer and `harness_usage` present
**When** `record_attempt_spend` runs
**Then** the attempt carries the harness figures with `cost_provisional = true`; a later call with Gateway rows replaces them and clears the flag; `run.spend_usd` is the sum over attempts both times.

**Given** `spend_usd 41.20` and `budget_usd 40.00`
**When** `budget.check` runs
**Then** it returns the park with reason `budget $41.20 / $40.00`; with `40.00 / 40.00` → `None`.

**Given** a Run with two story frames of two attempts each
**When** `GET /runs/{id}` is read
**Then** each story's `cost_usd` is its attempts' sum, `cost.spent_usd` the total, and `cost.provisional` reflects any provisional attempt.

**Given** the adapter's HTTP client
**When** any request is made
**Then** the bearer is `LITELLM_SPEND_KEY`, never `LITELLM_API_KEY`.

## Implementation notes

- `infrastructure/gateway/litellm_spend.py::LiteLLMSpend(settings, http)`; `research/spend.md` has the endpoint notes; read it before planning.
- `application/use_cases/spend.py::record_attempt_spend`; migration only if new columns are needed (`attempt.cost_provisional` exists from 4.1).
- Fallback if `x-litellm-session-id` proves unusable at 5.11: filter by `request_tags` containing `attempt:{id}` — leave a single function `_query(run_id, attempt_id)` to swap.

## Verification

```bash
make lint && make test && make openapi
```

## Sources for detail only

PRD FR-17, FR-26, FR-28, §11 Cost. Spine AD-11 (spend, provisional, sums), AD-5 (two keys). `research/spend.md`. `addendum.md` §D Budget.
