---
title: 'Optional budget — tracked, no cap'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: '8ecebb7815868c13093c57677fb1b90eac666038'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      budgetRatio and moneyRatio are near-identical functions across two files
    evidence: |-
      Both budget.ts:budgetRatio and detail.ts:moneyRatio implement the same null guard
      and ratio format. Pre-existing split; story 3-2 added the same guard to both.
      Maintenance risk if one diverges.
    location: >-
      web-client/src/lib/run/budget.ts:44 and web-client/src/lib/run/detail.ts:158
    severity: low
  - summary: >-
      Alembic downgrade has no guard for existing null rows
    evidence: |-
      ALTER COLUMN budget_usd NOT NULL fails if null rows exist. Migration docstring
      acknowledges this: "only safe when no null rows exist." No preflight check or
      SET DEFAULT before the constraint is added back.
    location: >-
      backend-api/alembic/versions/0013_budget_usd_nullable.py:downgrade
    severity: low
  - summary: >-
      No null-budget tests for codex, opencode, and fake adapter null path
    evidence: |-
      test_claude_adapter_null_budget.py covers the null path for Claude only.
      Codex/opencode ignore budget_usd_remaining (documented in adapter docstrings);
      fake records it. Pre-existing pattern — only Claude is tested for budget behavior.
    location: >-
      backend-api/tests/unit/test_claude_adapter_null_budget.py (claude only)
    severity: low
  - summary: >-
      No e2e-api scenario for null-budget run creation
    evidence: |-
      Unit tests cover the null path at every layer. No make e2e-api scenario sends
      POST /runs without budget_usd and verifies the 201 + null budget in GET /runs/{id}.
      make e2e-api passes because existing scenarios are unaffected.
    severity: low
---

<intent-contract>

## Intent

**Problem:** Every Run requires `budget_usd`; operators wanting an uncapped run must set an arbitrary ceiling, and the budget halt fires unconditionally once spend crosses it.

**Approach:** Make `budget_usd` nullable end-to-end — DB column, domain entity, API schemas, harness port, and UI; when null the budget rule is a no-op, `--max-budget-usd` is omitted from Claude argv (existing guard at `adapter.py:321` already handles `None`), and cost surfaces render `"tracked, no cap"` verbatim (FR-17, AD-11). Spend tracking is untouched.

## Boundaries & Constraints

**Always:**
- `run.spend_usd` tracking unchanged and authoritative (FR-17, AD-11); only the ceiling changes
- `"tracked, no cap"` is verbatim display copy (NFR-8); used wherever `moneyRatio`/`budgetRatio` previously rendered `$X / $Y`
- The `--max-budget-usd` guard at `claude/adapter.py:321` already handles `None`; only the `Decimal` → `Decimal | None` widening is needed at the port and adapter signatures
- Generated contract only (AD-3): `make openapi` → `pnpm gen:api` after API schema changes; no hand edits to `schema.d.ts`
- Two-writer rule (AD-8) untouched; no new status token or park kind
- TDD: tests fail before implementation lands; `make lint` and `make test` always apply

**Block If:** Any code path reaches `budget.forced()` with `run.budget_usd is None` at runtime (cannot format the reason string) — add a defensive guard and report if invariant is broken.

**Never:**
- Changing `run.spend_usd` logic or attempt cost tracking
- `budget_raise` signal on null-budget runs (box only renders when `park_kind == "budget"`, which never fires for null budget; out of scope)
- New status token or park kind

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Create run without budget | `POST /runs` body omits `budget_usd` | Run created; `run.budget_usd = null` | None |
| Create run with budget | `POST /runs` with `budget_usd: "5.00"` | Existing behavior unchanged | None |
| Null-budget run, spend any amount | `run.budget_usd = null`, `spend_usd = any` | `budget.check()` returns `None`; no park | — |
| Claude start, null budget | `run.budget_usd = null` → `budget_usd_remaining = None` | `--max-budget-usd` absent from argv | — |
| Cost display, null budget | `CostOut.budget_usd = null` | `moneyRatio()` / `budgetRatio()` return `"tracked, no cap"` | — |
| New-workflow form, no budget entered | `budgetUsd = ""` | `runBody()` returns body with `budget_usd: null`; form not blocked | — |
| Budget-set run | `run.budget_usd = "5.00"`, spend > 5 | Existing park behavior unchanged | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/entities/run.py:65` — `budget_usd: Decimal` → `Decimal | None`; no default (null is explicit)
- `backend-api/src/orchestrator/application/rules/budget.py:18-22` — `check()`: add `if run.budget_usd is None: return None` before comparison
- `backend-api/src/orchestrator/application/rules/budget.py:25-37` — `forced()`: guard reason string when `budget_usd` is None (defensive; Claude cannot self-cap when flag is absent)
- `backend-api/src/orchestrator/domain/ports/harness.py:224,248` — `run()` and `start()` signatures: `budget_usd_remaining: Decimal` → `Decimal | None`
- `backend-api/src/orchestrator/application/steps/agent.py:376` — `budget_usd_remaining=run.budget_usd - run.spend_usd` → `run.budget_usd - run.spend_usd if run.budget_usd is not None else None`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:98` — `CreateRunRequest.budget_usd: Decimal` → `Decimal | None`
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:219` — `Cost.budget_usd: Decimal` → `Decimal | None`
- `backend-api/src/orchestrator/api/schemas/runs.py:63` — `RunIn.budget_usd: BudgetUsd` → `BudgetUsd | None = None`; same file lines 97-116: `RunSummaryOut.budget_usd: MoneyStr` → `MoneyStr | None`
- `backend-api/src/orchestrator/api/schemas/run_views.py:275` — `CostOut.budget_usd: MoneyStr` → `MoneyStr | None`; `CostOut.of()` at line 284 unchanged (passes through None)
- `backend-api/src/orchestrator/infrastructure/db/models/run.py:85` — `Mapped[Decimal]` → `Mapped[Decimal | None]`; add `nullable=True` to `mapped_column`
- `backend-api/alembic/versions/0013_budget_usd_nullable.py` — new migration: `ALTER COLUMN budget_usd DROP NOT NULL`
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:213,241` — `budget_usd_remaining: Decimal` → `Decimal | None` on public `run()` and `start()`; `_argv()` at line 303 already typed `Decimal | None` — no change needed there
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py:157,185` — same widening on `run()` and `start()`
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:161,189` — same
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py:114,142` — same
- `web-client/src/lib/run/detail.ts:156-157` — `moneyRatio()`: when `cost.budget_usd == null` return `"tracked, no cap"` else existing ratio string
- `web-client/src/lib/run/budget.ts:41-42` — `budgetRatio()`: same null guard (TypeScript compliance; box never renders for null-budget runs)
- `web-client/src/components/NewWorkflowFields.tsx:173,177` — label becomes `BUDGET (USD) (optional)`; remove `required` attribute from input
- `web-client/src/lib/newwf/state.ts:175` — remove `!state.budgetUsd` from `runBody()` null guard; line 185: `budget_usd: state.budgetUsd || null`

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/entities/run.py` -- `budget_usd: Decimal | None`; no other field changes -- domain root; must precede all downstream changes
- `backend-api/src/orchestrator/application/rules/budget.py` -- `check()` returns `None` when `run.budget_usd is None`; `forced()` defensively guards the reason string -- budget rule no-op for null
- `backend-api/src/orchestrator/domain/ports/harness.py` -- `budget_usd_remaining: Decimal | None` on `run()` and `start()` -- port must widen before adapters
- `backend-api/src/orchestrator/application/steps/agent.py` -- compute `None` when `run.budget_usd is None` at line 376 -- prevents TypeError at dispatch
- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- `budget_usd: Decimal | None` on `CreateRunRequest` -- accepts missing budget
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` -- `Cost.budget_usd: Decimal | None` -- view type matches domain
- `backend-api/src/orchestrator/api/schemas/runs.py` -- `RunIn.budget_usd: BudgetUsd | None = None`; `RunSummaryOut.budget_usd: MoneyStr | None` -- API accepts and returns null
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- `CostOut.budget_usd: MoneyStr | None` -- cost response carries null
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- widen `run()` and `start()` signatures to `Decimal | None` -- mypy compliance; `_argv()` guard already present
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- same widening -- mypy compliance
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` -- same -- mypy compliance
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` -- same -- mypy compliance
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` -- `Mapped[Decimal | None]`, `nullable=True` -- ORM matches domain
- `backend-api/alembic/versions/0013_budget_usd_nullable.py` -- `op.alter_column("run", "budget_usd", nullable=True)` with downgrade reverting -- schema migration
- `backend-api/tests/unit/application/test_budget_rule.py` -- new test: `check(run_with_budget_usd_none)` returns `None` -- TDD gate for null path
- `backend-api/tests/unit/application/test_create_run_use_case.py` -- new test: `create_run` with `budget_usd=None` succeeds and stores null -- TDD gate for create path
- `backend-api/tests/unit/test_claude_adapter.py` -- new test: `budget_usd_remaining=None` → `--max-budget-usd` absent from argv -- TDD gate for adapter path
- `make openapi` -- regenerate `contracts/openapi.json` and run `pnpm gen:api` -- AD-3 contract sync; run after all backend schema changes
- `web-client/src/lib/run/detail.ts` -- `moneyRatio()` null guard: `cost.budget_usd == null ? "tracked, no cap" : ...` -- cost block and banner display
- `web-client/src/lib/run/budget.ts` -- `budgetRatio()` null guard: same pattern -- TypeScript compliance; box never renders for null budget
- `web-client/src/components/NewWorkflowFields.tsx` -- label `BUDGET (USD) (optional)`; remove `required` -- completes story 2-5's deferred item
- `web-client/src/lib/newwf/state.ts` -- remove `!state.budgetUsd` from `runBody()` guard; `budget_usd: state.budgetUsd || null` -- allows form submission without budget
- `web-client/tests/unit/run-cost-block.test.ts` -- new test: `moneyRatio({...cost, budget_usd: null})` returns `"tracked, no cap"` -- TDD gate
- `web-client/tests/unit/newwf-state.test.ts` -- new test: `runBody()` with empty `budgetUsd` returns body (not null); `budget_usd` is null in body -- TDD gate
- `web-client/tests/unit/newwf-fields.test.ts` -- new test: budget input lacks `required` attribute -- TDD gate

**Acceptance Criteria:**

- Given `POST /runs` with `budget_usd` absent, when the request is processed, then the run is created with `run.budget_usd = null` and the response includes `"budget_usd": null`.
- Given `run.budget_usd = null` and `run.spend_usd` at any value, when `budget.check(run)` is called, then it returns `None` (no park).
- Given `run.budget_usd = null`, when the agent executor calls `harness.start()`, then `budget_usd_remaining = None` is passed and `--max-budget-usd` is absent from the Claude argv.
- Given a run detail response with `cost.budget_usd = null`, when `moneyRatio(cost)` is called, then it returns `"tracked, no cap"`; both `CostBlock` and `Banner` display the phrase.
- Given the New-workflow form with the budget field empty, when the user fills all other required fields, then `runBody()` returns a valid body with `budget_usd: null` (form is not blocked).
- Given the New-workflow budget input, when rendered, then the label reads `BUDGET (USD) (optional)` and the input has no `required` attribute.
- Given `run.budget_usd = "5.00"` and spend exceeding it, when `budget.check(run)` is called, then existing park behavior is unchanged.
- Given `make lint` and `make test` after all changes, then both pass with no new violations.

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 4: (high 0, medium 0, low 4)
- reject: 8
- addressed_findings:
  - `[low]` `[patch]` `state.budgetUsd || null` coerces `"0"` to null — changed to explicit empty-string check `state.budgetUsd !== '' ? state.budgetUsd : null` in `runBody()`
  - `[low]` `[patch]` Alembic migration missing `existing_type` in `op.alter_column` — added to both upgrade and downgrade
  - `[low]` `[patch]` `budgetRatio` null guard untested — added null-budget test case in `run-budget-lib.test.ts`

## Design Notes

The `_argv()` method in `claude/adapter.py` at line 303 already types `budget_usd_remaining: Decimal | None` and guards the flag at line 321 — this is the only adapter method with real budget logic. The `run()` and `start()` public methods (lines 213, 241) declare `Decimal` today; widening them to `Decimal | None` is the entire adapter change. Codex, opencode, and fake adapter methods accept the parameter per protocol but pass it through or ignore it; the same signature widening applies.

The DB migration alters the `run.budget_usd` column to `nullable=True`. Existing rows all have non-null values, so the migration applies cleanly. Downgrade reverts with `NOT NULL` — only possible when no null rows exist.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff/mypy/import-linter/eslint/tsc violations
- `make test` -- expected: all unit tests green, including new null-budget tests

## Auto Run Result

Status: done

**Summary:** Made `run.budget_usd` nullable end-to-end. When null: `budget.check()` is a no-op, `--max-budget-usd` is omitted from Claude argv, and cost surfaces render `"tracked, no cap"` verbatim. The New-workflow budget field is now optional (`(optional)` label, no `required` attribute). Spend tracking is untouched.

**Files changed:**
- `domain/entities/run.py` — `budget_usd: Decimal | None`
- `application/rules/budget.py` — `check()` returns `None` on null; `forced()` defensive guard
- `domain/ports/harness.py` — `budget_usd_remaining: Decimal | None` on `run()` and `start()`
- `application/steps/agent.py` — computes `None` when `run.budget_usd is None`
- `application/use_cases/create_run.py` — `CreateRunRequest.budget_usd: Decimal | None`
- `application/use_cases/run_view_types.py` — `Cost.budget_usd: Decimal | None`
- `api/schemas/runs.py` — `RunIn.budget_usd: BudgetUsd | None = None`; `RunSummaryOut.budget_usd: MoneyStr | None`
- `api/schemas/run_views.py` — `CostOut.budget_usd: MoneyStr | None`
- `infrastructure/db/models/run.py` — `Mapped[Decimal | None]`, `nullable=True`
- `alembic/versions/0013_budget_usd_nullable.py` — `ALTER COLUMN budget_usd DROP NOT NULL`; `existing_type=MONEY` on both calls
- Four adapters (claude, codex, opencode, fake) — `budget_usd_remaining: Decimal | None` on `run()` and `start()`
- `lib/run/detail.ts` — `moneyRatio()` returns `"tracked, no cap"` when `budget_usd == null`
- `lib/run/budget.ts` — same null guard in `budgetRatio()`
- `lib/newwf/state.ts` — `runBody()` guard removes `budgetUsd`; `budget_usd: state.budgetUsd !== '' ? state.budgetUsd : null`
- `components/NewWorkflowFields.tsx` — label `BUDGET (USD) (optional)`, `required` removed
- `contracts/openapi.json` and `web-client/src/api/schema.d.ts` — regenerated
- New tests: `test_budget_rule_null.py`, `test_create_run_null_budget.py`, `test_claude_adapter_null_budget.py`, `run-cost-block-null-budget.test.ts`, `newwf-state-null-budget.test.ts`
- Revised tests (anchor exception 4, Operator decision 2026-09-17): `test_run_repository_adapter.py`, `test_run_router.py`, `newwf-fields.test.ts`
- `run-budget-lib.test.ts` — added null-budget test case for `budgetRatio`

**Review findings breakdown:**
- Patches applied: 3 (high: 0, medium: 0, low: 3)
- Items deferred: 4 (all low)
- Items rejected: 8

**Follow-up review recommendation:** false
- Score: 0×3 (medium) + 3×1 (low) = 3 < 5; no high patch → false

**Verification performed:**
- `make lint` → 0 errors, 0 warnings (ruff, mypy, import-linter, eslint, prettier, tsc)
- `make test` → 6322 backend passed, 23 skipped, 0 failed; 1352 frontend passed, 0 failed
- All 6 I/O matrix rows covered by passing tests

**Residual risks:**
- Alembic `downgrade()` reverts to NOT NULL; will fail if null-budget rows exist (documented in migration, deferred)
- `moneyRatio`/`budgetRatio` bodies near-identical across two files (pre-existing, deferred)
