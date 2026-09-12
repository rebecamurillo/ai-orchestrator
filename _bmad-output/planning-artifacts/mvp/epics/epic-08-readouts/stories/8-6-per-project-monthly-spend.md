---
title: 'Per-Project monthly spend'
type: 'feature'
created: '2026-09-12'
status: 'in-review'
baseline_revision: '5dfb18e632fae48a01f6b1f5840f0a9a3b00db24'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Project read model exposes no cost visibility — the Operator cannot see what this month's Runs have cost per Project, and the Projects list carries no signal for parked or recently failed Runs.

**Approach:** Add `spend_provisional: bool` to the `Run` entity (set alongside `spend_usd` by `record_attempt_spend`); add a new `project_spend` use case that reads `runs.list(project_id=...)` once and computes monthly total, provisional flag, `needs_you` count, and 7-day-failed count; expose four new nullable fields on `ProjectRead`; update the web-client meta line and list row.

## Boundaries & Constraints

**Always:**
- `spend_provisional` on `Run` is the only new Run field written outside the two status writers (AD-8 exception: `record_attempt_spend` is its own explicit use case with its own port, same exception as `active_seconds`).
- `monthly_spend_usd` is formatted `f"{total:.2f}"` (2 decimal places), e.g. `"12.30"`.
- `monthly_spend_provisional` is `True` when any attempt in the month-filtered sum has `cost_provisional=True`, tracked via the new `run.spend_provisional` field.
- `needs_you_count` counts ALL Runs for the project with `status == "needs_you"` (no time window).
- `failed_recent_count` counts Runs with `status == "failed"` and `(r.ended_at or r.created_at) >= now − 7 days`.
- Projects list row shows **at most one** coloured count: `{n} need you` amber when `needs_you_count > 0`; else `{n} failed` red when `failed_recent_count > 0`; else nothing (NFR-6 signal rule).
- All four new `ProjectRead` fields are `| None = None` for frozen fixture compatibility; `of()` always resolves real values — same pattern as `trajectory_count` and `builtin`.
- Schema generated, never hand-written (AD-3); run `make openapi` after backend field additions.
- New migration slot: `0012_run_spend_provisional.py`, chains from revision `0011_last_opened_before`.

**Block If:**
- Column `spend_provisional` already exists on the `run` table in the DB (check `alembic/versions/` before writing migration).

**Never:**
- Per-Project budget caps (deferred by the spine).
- Compute the monthly sum in the browser.
- A second writer of Run `status` (AD-8).
- Modify any existing test file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|----------------|----------------|
| Settled monthly spend | Project runs totalling 12.30 started this month, 40.00 last month | `monthly_spend_usd="12.30"`, `monthly_spend_provisional=false` | — |
| Provisional attempt | One monthly run has `spend_provisional=true` | `monthly_spend_provisional=true`; sum correct | — |
| No runs this month | All runs started last month | `monthly_spend_usd="0.00"`, `monthly_spend_provisional=false` | — |
| `started_at` is None | Run queued, never started | excluded from monthly sum | — |
| `needs_you_count > 0` | Project has 2 parked Runs | row shows `2 need you` amber; red count not shown | — |
| `failed_recent > 0`, no needs_you | 1 run failed 3 days ago | row shows `1 failed` red | — |
| Both counts > 0 | needs_you and recent-failed runs both present | row shows `{n} need you` amber only (priority rule) | — |
| Neither count | All done/cancelled | row shows no coloured element | — |
| Provisional meta line | `monthly_spend_usd="5.40"`, `monthly_spend_provisional=true` | meta line reads `... · this month $5.40 provisional` | — |

</intent-contract>

## Code Map

**Run entity and persistence:**
- `backend-api/src/orchestrator/domain/entities/run.py:66` — `spend_usd: Decimal = Decimal("0")`; add `spend_provisional: bool = False` on the next line
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — `RunRow`; add `spend_provisional: Mapped[bool] = mapped_column(Boolean(), server_default=text("FALSE"))` after the `spend_usd` column (line ~86); update `to_entity()` to read it; update `row_values()` to write it
- `backend-api/alembic/versions/0012_run_spend_provisional.py` — NEW migration; `revision="0012_run_spend_provisional"`, `down_revision="0011_last_opened_before"`; `op.add_column("run", sa.Column("spend_provisional", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))` in `upgrade()`; `op.drop_column("run", "spend_provisional")` in `downgrade()`
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` — `SQLAlchemyRunRepository.update(run)` persists `spend_provisional` automatically once `row_values()` includes it; no new methods needed

**Spend use case (record_attempt_spend):**
- `backend-api/src/orchestrator/application/use_cases/spend.py:116-123` — `_run_spend(ports, run) -> Decimal` iterates steps/attempts; replace with `_run_spend_and_provisional(ports, run) -> tuple[Decimal, bool]` that returns both total and `any(attempt.cost_provisional)` in one pass; update line 69 `model_copy(update={"spend_usd": ...})` to also set `"spend_provisional": provisional`

**New project metrics use case:**
- `backend-api/src/orchestrator/application/use_cases/project_spend.py` — NEW; frozen `ProjectMetrics` dataclass (`monthly_spend_usd: str`, `monthly_spend_provisional: bool`, `needs_you_count: int`, `failed_recent_count: int`); public `project_metrics(runs: RunRepository | None, project_id: UUID, now: datetime) -> ProjectMetrics`; calls `runs.list(project_id=project_id)` once; filters to `started_at >= datetime(now.year, now.month, 1, tzinfo=UTC)` for spend; uses `timedelta(days=7)` cutoff on `r.ended_at or r.created_at` for `failed_recent_count`; returns zero-valued `ProjectMetrics` when `runs is None`

**Schema and router:**
- `backend-api/src/orchestrator/api/schemas/projects.py:263` — after `trajectory_count: int | None = None` add four nullable fields: `monthly_spend_usd: str | None = None`, `monthly_spend_provisional: bool | None = None`, `needs_you_count: int | None = None`, `failed_recent_count: int | None = None` (same nullable-for-frozen-fixtures pattern; docstring mirrors `trajectory_count`'s own); update `of()` to accept `monthly_spend_usd: str = "0.00"`, `monthly_spend_provisional: bool = False`, `needs_you_count: int = 0`, `failed_recent_count: int = 0` and include them in `model_validate` dict
- `backend-api/src/orchestrator/api/routers/projects.py:96` — `_read()`; add `from orchestrator.application.use_cases import project_spend`; call `m = project_spend.project_metrics(ports.runs, view.id, ports.clock.now())`; pass `monthly_spend_usd=m.monthly_spend_usd`, `monthly_spend_provisional=m.monthly_spend_provisional`, `needs_you_count=m.needs_you_count`, `failed_recent_count=m.failed_recent_count` to `ProjectRead.of()`

**Web-client (after `make openapi`):**
- `web-client/src/api/schema.d.ts` — DO NOT EDIT; regenerated by `make openapi`
- `web-client/src/components/ProjectListRow.astro:11` — `Props` interface: add `needsYouCount: number` (with default 0 via destructuring); update rendering: replace `{failedCount > 0 && <span class="failed"> · {failedCount} failed</span>}` with priority conditional: when `needsYouCount > 0` → `<span class="needs-you"> · {needsYouCount} need you</span>` (amber); else when `failedCount > 0` → `<span class="failed"> · {failedCount} failed</span>` (red); else nothing; add `.needs-you { color: var(--color-signal-needs-you); }` scoped CSS rule
- `web-client/src/pages/projects/index.astro:132` — rename `failedCount()` to `runFailedCount()` returning `entry.failed_recent_count ?? 0`; add `runNeedsYouCount(entry)` returning `entry.needs_you_count ?? 0`; update `<ProjectListRow>` call to pass `failedCount={runFailedCount(entry)}` and `needsYouCount={runNeedsYouCount(entry)}`
- `web-client/src/pages/projects/index.astro:205` — meta line `<p class="meta">`; after `log_prompt_content {on/off}` append `{project.monthly_spend_usd != null && ` · this month $${project.monthly_spend_usd}${project.monthly_spend_provisional ? ' provisional' : ''}`}`

**Tests (all new files):**
- `backend-api/tests/unit/application/test_project_spend.py` — NEW; unit tests for `project_metrics()` using `FakeRunRepository` (from `tests/unit/fakes/runs.py`); covers: month boundary exclusion (runs starting last month excluded from sum), provisional propagation via `spend_provisional` field, needs_you count, failed_recent 7-day window with `ended_at` and `created_at` fallback, `started_at=None` exclusion, `runs=None` returns zeros
- `backend-api/tests/unit/test_project_schemas_monthly_spend.py` — NEW; parallel to `test_project_schemas_trajectory_count.py`; tests `of()` defaults (`"0.00"`, `False`, `0`, `0`); values pass through; `ProjectRead` constructed without the four fields validates (fields nullable)
- `backend-api/tests/unit/test_projects_router_monthly_spend.py` — NEW; parallel to `test_projects_router_trajectory_count.py`; `Harness._ports()` wires `runs=self.runs` (a `FakeRunRepository`); adds `Run` objects with known `spend_usd`, `spend_provisional`, `status`, `started_at`, `ended_at`, `project_id`; asserts per-project spend and counts in list response; asserts count isolation (one project's metrics do not bleed into another)
- `web-client/tests/unit/project-list-row-counts.test.ts` — NEW; renders `ProjectListRow` with `needsYouCount=2` → asserts `2 need you` present and `data-testid` amber; with `needsYouCount=0, failedCount=1` → asserts `1 failed` red; with both > 0 → asserts only amber shown; with both 0 → asserts no colour element
- `web-client/tests/e2e/projects-spend.spec.ts` — NEW; mocks `GET /api/v1/projects` with a project having `monthly_spend_usd="3.50"`, `monthly_spend_provisional=false`, `needs_you_count=1`, `failed_recent_count=0`; asserts meta line (detail pane activated via `?id=`) shows `this month $3.50`; asserts list row shows `1 need you`; second scenario: `monthly_spend_provisional=true` asserts `provisional` word in meta; third: `needs_you_count=0, failed_recent_count=2` asserts `2 failed` red

## Tasks & Acceptance

**Execution:**

1. `backend-api/src/orchestrator/domain/entities/run.py` — add `spend_provisional: bool = False` after `spend_usd` at line 66

2. `backend-api/src/orchestrator/infrastructure/db/models/run.py` — add `spend_provisional` column, update `to_entity()` and `row_values()`

3. `backend-api/alembic/versions/0012_run_spend_provisional.py` — NEW migration chaining from `0011_last_opened_before`

4. `backend-api/src/orchestrator/application/use_cases/spend.py` — replace `_run_spend()` with `_run_spend_and_provisional()` returning `tuple[Decimal, bool]`; update `record_attempt_spend` to also set `spend_provisional`

5. `backend-api/tests/unit/application/test_project_spend.py` — NEW (TDD: write first, all fail until task 6)

6. `backend-api/src/orchestrator/application/use_cases/project_spend.py` — NEW use case; makes task 5 pass

7. `backend-api/src/orchestrator/api/schemas/projects.py` — add four new nullable fields to `ProjectRead`; update `of()`

8. `backend-api/tests/unit/test_project_schemas_monthly_spend.py` — NEW schema unit tests

9. `backend-api/src/orchestrator/api/routers/projects.py` — update `_read()` to call `project_spend.project_metrics()` and pass results to `ProjectRead.of()`

10. `backend-api/tests/unit/test_projects_router_monthly_spend.py` — NEW router tests with wired `FakeRunRepository`

11. `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`

12. `web-client/src/components/ProjectListRow.astro` — add `needsYouCount` prop with default 0; update rendering to priority logic; add `.needs-you` CSS rule

13. `web-client/tests/unit/project-list-row-counts.test.ts` — NEW unit tests for the updated component

14. `web-client/src/pages/projects/index.astro` — update `failedCount()` to `runFailedCount()` using `entry.failed_recent_count`; add `runNeedsYouCount()`; pass both to `<ProjectListRow>`; append spend to meta line

15. `web-client/tests/e2e/projects-spend.spec.ts` — NEW e2e tests covering AC 1–3

**Acceptance Criteria:**
- Given a Project with attempts costing 12.30 this month and 40.00 last month, when `GET /projects/{id}` is read, then `monthly_spend_usd == "12.30"` and the detail pane meta line reads `... · this month $12.30`
- Given one provisional attempt in the monthly sum, when rendered, then `monthly_spend_provisional == true` and the meta line reads `... · this month $X.XX provisional`
- Given Projects with a parked Run, a recently-failed Run, and a done Run, when the Projects list renders, then the rows show `1 need you` in amber, `1 failed` in red, and nothing respectively; no other amber or red pixel appears on those rows

## Design Notes

**`spend_provisional` on `Run` entity:** `record_attempt_spend` already iterates every step and attempt to recompute `spend_usd`; tracking `spend_provisional` in the same pass adds one boolean accumulator with no extra I/O. The field defaults to `False`, so all pre-migration rows read correctly without a backfill. No new port method is added to `RunRepository`, avoiding changes to the frozen `FakeRunRepository`.

**One `runs.list()` call per project per request:** `project_spend.project_metrics()` calls `runs.list(project_id=...)` once and computes all four metrics. `embedded_runs()` calls it again limited to `EMBED_LIMIT=20`. Two calls per project per `_read()` is acceptable at MVP; a future story can coalesce them.

**`failedCount` prop semantics:** The frozen `projects-components.test.ts` passes `failedCount={2}` and asserts `2 failed`. This keeps working: `needsYouCount` defaults to 0, the priority falls through to show `failedCount`. The prop's semantics at the call site change (now driven by `failed_recent_count` from the API rather than repository clone-check count), but the component rendering contract is unchanged.

## Verification

**Commands:**
- `make lint` — expected: zero ruff/mypy/import-linter/eslint/tsc errors
- `make test` — expected: all unit tests pass, including `test_project_spend.py`, `test_project_schemas_monthly_spend.py`, `test_projects_router_monthly_spend.py`, `project-list-row-counts.test.ts`
- `make openapi` — expected: `contracts/openapi.json` updated with four new `ProjectRead` fields; no drift after `pnpm gen:api`
- `make e2e-ui` — expected: `projects-spend.spec.ts` passes; `projects.spec.ts` unaffected
