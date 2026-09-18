---
title: 'The queue partitions by (Repository, branch)'
type: 'feature'
created: '2026-09-18'
status: 'in-progress'
baseline_revision: '29cf53606cb0e704488dae344d2de6648a4d254b'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** `engine.enqueue` partitions only by `repository_id`, serialising all Runs on a Repository even when they target different branches; the pre-flight held-branch check compares the new plan's declared branch against `run.worktrees[*].branch` (the allocated fresh name), so those names never match and the guard is silently broken.

**Approach:** Widen `engine.enqueue`'s `partition_key` to `str`; set it to `"{repository_id}:{declared_branch}"` in `create_run`; persist the declared branch as `run.partition_branch` so pre-flight, queue-reason logic, and the git.worktree executor backstop can all compare branch partitions correctly.

## Boundaries & Constraints

**Always:** Two-writer rule (AD-8) — `apply_step_result` and `signal_run` are the only status writers; no new status tokens; queue reasons are exactly the two renamed strings; `MAX_ACTIVE_RUNS` and `needs_you` slot-holding behaviour are unchanged; TDD with shared fakes; `partition_branch` is set once at `create_run` time and never written again; the operator revision of 2026-09-15 authorises revising the two test-pinned queue-reason strings in `use_cases/queue.py` tests — the revised test must name the decision and date; no other assertion may be weakened; new settings land in `.env.example` + typed settings together (none needed here); `make lint` and `make test` green.

**Block If:** Any code path that sets a `partition_branch` from a source other than the plan's `branches` dict or the request's `base_branch` (for initiative plans); any attempt to add a third writer for the new `partition_branch` field.

**Never:** Change `REASON_RUNNING` or `REASON_WAITING_ANSWER`; use the allocated (fresh) branch name as the partition key; add a new `park_kind` for the held-branch backstop (it reuses `"misconfigured"`); add `StepRunRepository` access to the pre-flight `Context`; add `RunRepository` access to any executor; store more than the two renamed queue-reason strings under new constant names (keep backward-compatible constant `REASON_REPOSITORY_LOCK` as an alias only if needed, otherwise remove it and update all call sites).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behaviour | Error Handling |
|----------|--------------|---------------------------|----------------|
| Same-branch second run | Non-terminal Run A on repo X branch `feat/s` exists; `create_run` for repo X branch `feat/s` | Pre-flight refuses with `held by run …`; Run B not created | 409 Conflict |
| Different-branch concurrent | Non-terminal Run A on repo X branch `feat/s1`; `create_run` for repo X branch `feat/s2` | Both Runs enqueued; partition keys differ; Run B created and starts without waiting behind A | No error |
| Initiative plan | Plan has empty `branches` dict | `partition_branch = req.base_branch`; partition key `"{repo_id}:{base_branch}"` | No error |
| Second enqueue (lost response) | `engine.enqueue(run_id, …)` called twice with same `run_id` | Second call is a no-op; same `engine_ref` returned | No error |
| Executor backstop race | Pre-flight passed; by execution time another run holds same `partition_branch` | `git.worktree` parks `kind="misconfigured"`, reason `"branch held by {run_label}"` | Park, operator sees blocking run |
| `needs_you` run | Run is parked (`needs_you`), same partition branch | Still holds partition and slot; a second run for the same branch stays queued behind it | Queue reason `"branch held by {run}"` |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/engine.py:59` — `WorkflowEngine.enqueue` signature (`partition_key: UUID` → `str`); update docstring
- `backend-api/src/orchestrator/domain/entities/run.py` — `Run` entity; add `partition_branch: str | None = None` field
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — `RunRow` ORM model; add `partition_branch` nullable column; update `_to_domain`/`_from_domain`
- `backend-api/alembic/versions/0013_run_partition_branch.py` — new Alembic migration; `ALTER TABLE run ADD COLUMN partition_branch VARCHAR`; `down_revision = "0012_run_spend_provisional"`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:147–180` — `plan` and `repository` available here; add `_partition_branch(plan, base_branch)` helper (`next(iter(plan.branches), base_branch)`); set `Run.partition_branch`; pass string partition_key to `engine.enqueue`; import `Plan` from `plan_model`
- `backend-api/src/orchestrator/infrastructure/dbos/adapter.py:92–97` — `DbosWorkflowEngine.enqueue`; change signature to `partition_key: str`; keep `str(partition_key)` defensively; add idempotency guard: if `self._engine.steps(str(run_id))` is non-empty, log and return early without re-enqueueing
- `backend-api/src/orchestrator/application/preflight/checks.py:197–204` — `_holding_run`; change comparison from `worktree.branch == branch` to `run.partition_branch == branch` (non-None only); update `run_label` to prefer `run.partition_branch` over `run.worktrees[0].branch` for the branch segment
- `backend-api/src/orchestrator/application/use_cases/queue.py:40–43,113–131` — rename `REASON_REPOSITORY_LOCK` → `REASON_BRANCH_HELD = "branch held by {run}"`; update `REASON_GLOBAL_CONCURRENCY` format param `{labels}` → `{runs}`; update `_reason` `.format()` calls; update `_holding_run` to compare `r.partition_branch == run.partition_branch` (skip when either is `None`)
- `backend-api/src/orchestrator/application/steps/context.py:126–165` — `RunEnvironment`; add `held_by_label: str | None = None` field (default `None` preserves every existing constructor call)
- `backend-api/src/orchestrator/infrastructure/db/environment.py:50–85` — `read_run_environment`; after reading `run` and `repository`, query `SQLAlchemyRunRepository(session).list_by_repository_non_terminal(run.repository_id)`, find the first run with `r.id != run_id` and `r.partition_branch == run.partition_branch` (non-None), format as `f"{r.template_name} · {r.partition_branch}"`, pass as `held_by_label`
- `backend-api/src/orchestrator/application/steps/git_worktree.py:84–97` — `GitWorktreeExecutor.execute`; after `require_env(ctx)`, check `env.held_by_label`; if set, return `StepResult(status="error", gate=ctx.row.gate, reason=HELD_BY.format(run=env.held_by_label), park=Park(kind="misconfigured", reason=..., path=ctx.row.path))`; add `HELD_BY = "branch held by {run}"` constant
- `backend-api/tests/unit/application/test_queue.py:104,136` — operator revision 2026-09-15; replace `REASON_REPOSITORY_LOCK.format(label=…)` with `REASON_BRANCH_HELD.format(run=…)`; replace `REASON_GLOBAL_CONCURRENCY.format(labels=…)` with `REASON_GLOBAL_CONCURRENCY.format(runs=…)`; add comment naming the operator decision and date
- `backend-api/tests/unit/test_queue_schema.py:49` — operator revision 2026-09-15; replace `"repository lock held by epic · main"` with `"branch held by epic · main"`; name the decision and date in the test

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/ports/engine.py` -- change `partition_key: UUID` to `partition_key: str` in `WorkflowEngine.enqueue`; update docstring to "(Repository, declared-branch) partition" -- port widens to str deliberately (AD-12)
- `backend-api/src/orchestrator/domain/entities/run.py` -- add `partition_branch: str | None = None` to the `Run` dataclass -- stores the declared branch for partition-key comparison without re-querying the plan
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` -- add `partition_branch: Mapped[str | None]` column to `RunRow`; update `_to_domain` and `_from_domain` to round-trip the new field -- persists `partition_branch` across sessions
- `backend-api/alembic/versions/0013_run_partition_branch.py` -- new Alembic migration adding nullable `partition_branch VARCHAR` column to `run` table; `down_revision = "0012_run_spend_provisional"` -- schema change required for new Run field
- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- add `_partition_branch(plan: Plan, base_branch: str) -> str` (returns `next(iter(plan.branches), base_branch)`); set `partition_branch=_partition_branch(plan, req.base_branch)` on the `Run(...)` constructor; change `engine.enqueue(run.id, partition_key=f"{repository.id}:{_partition_branch(plan, req.base_branch)}")` -- initiative plans (empty `plan.branches`) fall back to `base_branch`; declared branch used, never the allocated fresh name
- `backend-api/src/orchestrator/infrastructure/dbos/adapter.py` -- update `enqueue` signature to `partition_key: str`; keep `str(partition_key)` in the DBOS call; add guard: if `self._engine.steps(str(run_id))` is non-empty, log `"enqueue_no_op"` and return `{WORKFLOW_ID: str(run_id)}` without re-enqueueing -- idempotency on run_id: repeated call after lost response finds existing workflow (AD-12)
- `backend-api/src/orchestrator/application/preflight/checks.py` -- update `_holding_run`: replace `any(worktree.branch == branch for worktree in run.worktrees)` with `run.partition_branch is not None and run.partition_branch == branch`; update `run_label` to use `run.partition_branch` first, falling back to `run.worktrees[0].branch` then `run.inputs` -- covers branches declared by git.worktree rows of non-terminal Runs; shows declared (not fresh) branch in labels
- `backend-api/src/orchestrator/application/use_cases/queue.py` -- rename `REASON_REPOSITORY_LOCK` to `REASON_BRANCH_HELD = "branch held by {run}"`; update `REASON_GLOBAL_CONCURRENCY` value to `"global concurrency, held by {runs}"`; in `_reason`, use `.format(run=run_label(holder))` and `.format(runs=…)`; update `_holding_run` to filter on `r.partition_branch == run.partition_branch` (skip if either is `None`) -- operator revision 2026-09-15 authorises the string change; branch partition key makes same-repository / different-branch runs non-competing
- `backend-api/src/orchestrator/application/steps/context.py` -- add `held_by_label: str | None = None` to `RunEnvironment` -- pre-computed holding-run label so executor never touches a repository (AD-8)
- `backend-api/src/orchestrator/infrastructure/db/environment.py` -- in `read_run_environment`, after loading `run` and `repository`, query `list_by_repository_non_terminal(run.repository_id)` for another run with matching non-None `partition_branch`; set `held_by_label = f"{holder.template_name} · {holder.partition_branch}"` -- provides the backstop label before the executor starts
- `backend-api/src/orchestrator/application/steps/git_worktree.py` -- add `HELD_BY = "branch held by {run}"` constant; at the top of `GitWorktreeExecutor.execute`, after `env = require_env(ctx)`, check `env.held_by_label`; if set, return `StepResult(status="error", gate=ctx.row.gate, reason=HELD_BY.format(run=env.held_by_label), park=Park(kind="misconfigured", reason=…, path=ctx.row.path))` -- AD-14 backstop for race condition between pre-flight pass and worktree creation
- `backend-api/tests/unit/application/test_queue.py` -- operator revision 2026-09-15: replace `REASON_REPOSITORY_LOCK` with `REASON_BRANCH_HELD`, update `format` params from `label=` to `run=`, update global-concurrency format param from `labels=` to `runs=`; add inline comment `# operator revision 2026-09-15: partition by (repository, branch)` beside each revised assertion -- anchor exception 4, same commit adds tests asserting new strings
- `backend-api/tests/unit/test_queue_schema.py` -- operator revision 2026-09-15: replace `"repository lock held by …"` with `"branch held by …"`; add inline comment naming the decision and date -- anchor exception 4
- `backend-api/tests/unit/application/test_create_run_partition.py` -- NEW: test `_partition_branch` helper (story plan → first branch key; initiative empty branches → base_branch); test `create_run` sets `run.partition_branch` to the declared branch; test `engine.enqueue` receives `f"{repository_id}:{declared_branch}"` format string -- TDD coverage for new partition behaviour
- `backend-api/tests/unit/application/test_preflight_partition_branch.py` -- NEW: test `_holding_run` returns a run when `r.partition_branch == declared` (existing `worktree.branch` is ignored); test returns `None` when `r.partition_branch` differs; test returns `None` when `r.partition_branch` is `None` (old run) -- TDD coverage for fixed pre-flight check
- `backend-api/tests/unit/test_dbos_adapter_idempotency.py` -- NEW: construct `DbosWorkflowEngine` with `FakeDurableEngine(steps=[StepRecord(…)])` for `RUN_A`; call `engine.enqueue(RUN_A, partition_key="…")`; assert `fake.enqueued == []` (no duplicate) -- TDD coverage for idempotent enqueue (AD-12 comment, adapter.py line 8)
- `backend-api/tests/unit/application/test_git_worktree_held.py` -- NEW: test `GitWorktreeExecutor.execute` returns `StepResult(status="error", park.kind="misconfigured")` with `reason="branch held by epic · feat/s"` when `env.held_by_label = "epic · feat/s"` is set; test normal execution path when `held_by_label` is `None` -- TDD coverage for executor backstop

**Acceptance Criteria:**

- Given a plan with one `git.worktree` row declaring `"feat/s"` (allocated to `"feat/s-1"`), when `create_run` succeeds, then `run.partition_branch == "feat/s"` and the DBOS adapter is called with `partition_key` matching `"{repository_id}:feat/s"`.
- Given an initiative plan (empty `plan.branches`), when `create_run` succeeds, then `run.partition_branch == req.base_branch` and `partition_key` is `"{repository_id}:{base_branch}"`.
- Given a non-terminal Run A with `partition_branch = "feat/s"` on repository X, when pre-flight runs for a new Run on repository X with declared branch `"feat/s"`, then the branch line is `"fail"` with text `"held by run {run_label(A)}"`.
- Given Run A on repository X branch `"feat/s1"` and Run B on repository X branch `"feat/s2"`, when both are enqueued, then each has a distinct partition key and neither appears in the other's `REASON_BRANCH_HELD` reason.
- Given a Run in `needs_you` status with `partition_branch = "feat/s"`, when a second Run for the same repository and branch tries to enqueue, then the queue reason is `"branch held by {run_label}"` (not `"running"`).
- Given `engine.enqueue(run_id, …)` is called twice with the same `run_id` (DBOS steps non-empty), then the second call does not append a second entry to the DBOS queue and returns the same `engine_ref`.
- Given `env.held_by_label = "epic · feat/s"` in `RunEnvironment`, when `GitWorktreeExecutor.execute` runs, then the result is `StepResult(status="error", park=Park(kind="misconfigured", reason="branch held by epic · feat/s", …))` and no git operation is attempted.
- Given an enqueued Run on repo X branch `"feat/s"` with engine_state `"enqueued"` and a holding run with `partition_branch = "feat/s"`, when `list_queue` runs, then that Run's reason is `"branch held by {run_label(holder)}"` (not `"repository lock held by …"`).
- Given two Runs on different repositories both at global concurrency ceiling, when `list_queue` runs, then the waiting Run's reason matches `"global concurrency, held by {runs}"` with the active run labels joined by `", "`.
- Given `make lint` and `make test` after all changes, then both pass green.

## Design Notes

**Why `partition_branch` on `Run` rather than re-reading from `step_run` rows:** The pre-flight context has `RunRepository` but not `StepRunRepository`. Storing `partition_branch` on `Run` avoids adding a new port dependency to pre-flight, keeps the comparison O(1) per run, and survives the case where the `git.worktree` step has not yet executed (worktrees list is empty at queue time). Old runs with `partition_branch = None` are treated as non-competing — they had the old broken behaviour and cannot be retroactively fixed without replanning.

**Idempotency guard in the adapter:** The comment at adapter.py line 8 already states DBOS handles re-enqueue by workflow id; the explicit `steps()` check makes this testable with `FakeDurableEngine` (which does not implement DBOS's own idempotency).

**run_label update:** `run_label` in `checks.py` currently falls back to `run.worktrees[0].branch` (allocated name). Preferring `partition_branch` means labels show `"feat/s"` rather than `"feat/s-1"`, which is the name the Operator wrote. No existing test changes are needed because tests use `a_run(inputs={"branch": …})` with no `partition_branch`; the function's `inputs` fallback keeps those labels unchanged.

**Operator revision scope (2026-09-15):** Only the two verbatim queue-reason strings in `use_cases/queue.py` tests and `test_queue_schema.py` are revised; `REASON_RUNNING` and `REASON_WAITING_ANSWER` are untouched; the pre-flight `"held by run …"` text in `test_preflight_use_case.py` is NOT covered by this revision (it uses a different string format that does not match either renamed constant).

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract all pass
- `make test` -- expected: 100 % branch coverage on `domain/` and `application/`; all new and existing tests green
