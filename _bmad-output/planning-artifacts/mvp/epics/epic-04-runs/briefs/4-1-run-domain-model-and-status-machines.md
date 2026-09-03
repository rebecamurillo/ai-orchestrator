---
story: "4-1"
epic: 4
title: Run domain model and status machines
requirements: [AR-8, AR-11 (machines), NFR-1, NFR-2]
binds: [AD-2, AD-7, AD-8, AD-13, AD-18]
---

# Story 4.1 — Run domain model and status machines

As the Operator,
I want the Run, its planned Steps, their Attempts, and the gate record to exist as one precise model with transitions that are checked, not assumed,
So that every later story writes state through rules that cannot be bent by a router, an executor, or a screen.

## Scope

**In:** `domain/entities/{run,step_run,attempt,gate_record}.py`, `domain/statuses.py` (enums + the two transition functions), `domain/values.py` (`Park`, `StepResult`, `Redispatch`, `Signal`, `PlannedRow`, `Worktree`), repository ports in `domain/ports/repositories.py` (`RunRepository`, `StepRunRepository`, `AttemptRepository`, `GateRecordRepository`) with in-memory fakes, SQLAlchemy models and a migration, unit tests.
**Out:** any use case (4.2 onward), the engine (4.6).

## Binding rules (inlined)

- **Run fields.** `id`, `project_id`, `repository_id`, `template_name`, `template_version`, `pinned_versions: [{name, version}]`, `inputs: {}` (the bound inputs incl. `base_branch`, `harness`, `model`, template inputs), `status`, `plan_ref` (SHA), `plan_refs: {path: sha}` (per list file when read elsewhere), `engine_ref: {}` (adapter-owned), `budget_usd: Decimal`, `spend_usd: Decimal = 0`, `manual_estimate_h: Decimal | None` (immutable after start), `re_review_done: bool`, `park_kind: ParkKind | None`, `park_path: str | None`, `park_reason: str | None`, `accepted_paths: [str]`, `worktree_path: str | None`, `worktrees: [{branch, path, created_branch, pushed}]`, `compare_urls: [str]`, `trace_id: str | None`, `terminal_session: bool = False`, `active_seconds: int = 0`, `last_opened_at`, `created_at`, `started_at`, `ended_at`.
- **StepRun fields.** `id`, `run_id`, `seq: int` (dense, unique per Run), `path: str` (unique per Run), `label: str`, `kind`, `gate: liveness | deterministic | human | unvalidated`, `status`, `reason: str | None`, `with_resolved: {}`, `retry_count: int = 0`, `redispatch_count: int = 0`, `frame: str | None` (the innermost `…stories[n]` / `epics[n]` prefix), `story_id: str | None`.
- **Attempt fields.** `id`, `run_id`, `step_run_id`, `n: int` (1-based per row), `status`, `started_at`, `ended_at`, `engine_ref: {}`, `start_sha`, `end_sha`, `frozen_test_files: [str] | None`, `log_path`, `exit_code`, `output_ref` (log path or short output), and for agent rows `harness`, `model`, `session_id`, `pgid`, `tokens_in`, `tokens_out`, `cost_usd`, `cost_provisional: bool`.
- **GateRecord fields.** `id`, `run_id`, `at`, `path: str | None`, `event: str` (a `ParkKind`, a `SignalKind`, or `start | done | failed | cancelled`), `actor: operator | machine | terminal`, `text: str`, `attempt_n: int | None`, `payload: {}` (e.g. accepted files).
- **Enums.** `RunStatus = queued running needs_you done failed cancelled`; `StepStatus = planned queued running done blocked checkpoint error skipped`; `ParkKind = blocked checkpoint verify_failed budget timeout push_rejected protected_path misconfigured plan_stale internal`; `SignalKind = answer continue retry skip_story skip_epic budget_raise cancel terminal_start terminal_release terminal_resume`; `Gate = liveness deterministic human unvalidated`.
- **Run transitions** (`domain/statuses.py::run_transition(status, event) -> RunStatus`, raises `InvalidTransition` otherwise): `queued →start→ running`; `running →park→ needs_you`; `needs_you →resume→ running` (events `answer continue retry skip_story skip_epic budget_raise terminal_resume`); `needs_you →expire→ failed`; `running →finish→ done`; `running →fail→ failed`; `queued|running|needs_you →cancel→ cancelled`. Terminal statuses accept nothing.
- **Step transitions** (`step_transition(status, event) -> StepStatus`): `planned →predecessor_done→ queued`; `planned →skip→ skipped`; `queued →start→ running`; `running →{done, blocked, checkpoint, error}`; `error →retry→ queued`; `error →continue_accept→ running`; `done →redispatch→ queued`; `blocked →answer→ queued`; `blocked →terminal_resume→ done`; `checkpoint →continue→ queued` (agent row) or `→ done` (checkpoint row, event `continue_checkpoint`); `blocked|checkpoint|error|queued →skip→ skipped`. Anything else raises.
- **Values.** `Park{kind, reason, path}`; `Redispatch{target_seq, max}`; `StepResult{status: StepStatus, gate: Gate, output_ref: str | None, park: Park | None, redispatch: Redispatch | None, reason: str | None}`; `Signal{kind, payload: {}}`; `PlannedRow{seq, path, label, kind, gate, status, reason, with_resolved, frame, story_id}`.
- **Ports.** `RunRepository{add, get, update, list(filter) , list_by_status, list_by_repository_non_terminal}`; `StepRunRepository{add_many, get_by_seq, list_for_run, update, first_queued}`; `AttemptRepository{add, get_latest, list_for_row, mark_started, mark_finished, update}`; `GateRecordRepository{add, list_for_run}`. Fakes in `tests/unit/fakes/runs.py`.
- **Persistence.** Tables `run`, `step_run` (unique `(run_id, seq)`, `(run_id, path)`), `attempt` (unique `(step_run_id, n)`), `gate_record`; JSONB for lists and maps; `numeric(12,6)` for money; migration `0005_run.py`.
- **Layering:** `domain/` has no I/O; pydantic models frozen where a value object.

## Acceptance criteria

**Given** each valid `(status, event)` pair in the two tables
**When** the transition function is called
**Then** it returns the listed target; **and** for every pair not listed it raises `InvalidTransition` naming both (parametrised tests over the full product of statuses × events).

**Given** a `Run` created by the fake repository
**When** `update` is called with a changed `spend_usd` and `manual_estimate_h`
**Then** the fake stores the change (immutability of the estimate is enforced by the use case in 4.4, not here).

**Given** the SQLAlchemy models
**When** `alembic upgrade head` runs on an empty database and a Run with two rows and one attempt is inserted through the repositories
**Then** reads return equal entities (e2e-api test through a test-only fixture or the unit test marked `db` run in CI's e2e job).

**Given** the enums
**When** serialised to the API later
**Then** `needs_you` is the stored spelling (the UI maps it to `BLK`/`CHK`).

## Implementation notes

- Keep `domain/statuses.py` as two dict-based tables plus the two functions; export `TERMINAL_RUN = {done, failed, cancelled}`.
- `frame` and `story_id` are filled by the planner (4.2) and used by skip signals (Epic 6); include them now to avoid a later migration.
- Fakes record every call for assertion (`calls` list).

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-7, AD-8 (two state diagrams), AD-13 (signal kinds), Structural Seed fields, conventions (Ids, Dates & money, Status tokens). PRD glossary (Run, Step, Attempt, Gate record, Status, Stop).
