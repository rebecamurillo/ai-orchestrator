---
story: "9-3"
epic: 9
title: Gateway off — unknown spend, never free
requirements: [FR-10 (budget), FR-24, NFR-7, NFR-8]
binds: [AD-2, AD-11]
---

# Story 9.3 — Gateway off: unknown spend, never free

As the Operator,
I want an instance with no LiteLLM to say that it does not know what an attempt cost,
So that a Run I paid for on my own subscription is never reported to me as free.

## Scope

**In:** `infrastructure/gateway/disabled.py` (`DisabledGateway`), `build_gateway(settings, http)` in `infrastructure/gateway/__init__.py`, and the walker's construction site in `infrastructure/dbos/startup.py` wired through it.
**Out:** the model route itself — with the Gateway off a harness reaches its provider by its own login, which is 9-4 (environment) and 9-5 (config files). No pricing table, no token-to-money computation, ever.

## Binding rules (inlined)

- **`Settings.gateway_enabled` (9-1) is the only condition.** `build_gateway` returns `LiteLLMSpend(settings, http)` when true and `DisabledGateway()` when false. `application/` keeps taking the `Gateway` port and branches on nothing (AD-2).
- **The answer is *unknown*, spelled the way this system already spells it:** `AttemptSpend(usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True)` — the identical shape `LiteLLMSpend` returns for an outage, and the shape `tests/unit/fakes/gateway.py::PROVISIONAL_ZERO` already gives. `provisional=True` is the whole point: `tests/unit/test_local_spend_zero_cost.py` pins the distinction that a **measured** zero (`provisional=False`, rows existed, tokens counted) is a different fact from an **unknown** zero, and an instance with no Gateway only ever produces the second.
- **No client, no I/O, no raising.** `DisabledGateway` holds no `httpx.Client` and makes no request; `build_gateway` does not construct one when the Gateway is off. One `info` line at construction — `gateway disabled, spend unknown` — and none per attempt, so a long Run does not log the same fact a hundred times.
- **`record_attempt_spend` is not modified, and this is the finding worth stating.** It already prefers a settled Gateway answer and falls back to the harness's own `HarnessUsage` when the answer is provisional, carrying `cost_provisional=True`; when there is no harness estimate either it writes nothing rather than inventing a zero. So with the Gateway off, an attempt's cost is whatever the harness reported (`claude` reports its own USD, `codex` its usage, `local` zero), always flagged provisional, and `run.spend_usd` is the sum of those. `application/rules/budget.py::check` therefore still parks a Run that exceeds its budget — on the harness's figures, and no better than they are. Assert this behaviour; do not change it.
- **`--max-budget-usd` still applies.** `application/steps/agent.py` passes `run.budget_usd - run.spend_usd` to the harness, and a harness that enforces its own cap keeps enforcing it. The budget park from a harness cap (`rules/budget.py::forced`) is unaffected.
- **The screen states it.** Nothing in this story changes a schema: `cost_provisional` already exists on the attempt and the read model already carries it. The words on screen are 9-6's.

## Acceptance criteria

**Given** `gateway_enabled` false
**When** `build_gateway(settings, http)` is called
**Then** it returns a `DisabledGateway`, the instance satisfies `isinstance(x, Gateway)`, and the shared `httpx.Client` is never used (assert by passing a client whose `request` raises).

**Given** the committed `.env.example` environment
**When** `build_gateway(settings, http)` is called
**Then** it returns a `LiteLLMSpend`.

**Given** a `DisabledGateway`
**When** `spend_for_attempt(run_id, attempt_id)` is called with any ids
**Then** it answers `usd=0`, `tokens_in=0`, `tokens_out=0`, `by_model=()`, `calls=0`, `provisional=True`, and raises nothing.

**Given** a `DisabledGateway` and an attempt whose harness reported `HarnessUsage(tokens_in=1200, tokens_out=300, cost_usd=Decimal("0.42"))`
**When** `record_attempt_spend` runs
**Then** the attempt carries `cost_usd == 0.42`, the harness's token counts, and `cost_provisional is True`, and `run.spend_usd` is the sum over the Run's attempts.

**Given** a `DisabledGateway` and an attempt whose harness reported nothing
**When** `record_attempt_spend` runs
**Then** the attempt's cost fields are left as they were — an unpriced attempt is not written down as a $0.00 one.

**Given** a Run whose `spend_usd` (harness figures) exceeds its `budget_usd`
**When** `application/rules/budget.py::check` runs
**Then** it parks with `kind="budget"`, unchanged by the mode.

## Implementation notes

- New test files: `backend-api/tests/unit/test_disabled_gateway.py` and, for the two `record_attempt_spend` cases, `test_spend_without_gateway.py`. Do not touch `test_litellm_spend_adapter.py` or `test_local_spend_zero_cost.py`.
- Use the shared fakes for the five repositories (`tests/unit/fakes/`) exactly as `test_local_spend_zero_cost.py` does; do not create a second double for a port that already has one (hard rule 6).
- `infrastructure/gateway/__init__.py` currently exports the adapter; add the factory beside it and keep the adapter's name exported so existing imports and tests resolve.

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-11 (spend per attempt, provisional). `infrastructure/gateway/litellm_spend.py` — the degraded-answer contract and `SPEND_QUERY_DEGRADED`. `application/use_cases/spend.py` — "settled beats provisional", and why inventing zeros misrepresents unknown as free. `tests/unit/test_local_spend_zero_cost.py` — the free/unknown distinction this story must not collapse. PRD §11 (local models cost zero), FR-24 (cost readout).
