---
title: 'Trajectory record'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

# Trajectory record

## Auto Run Result

Status: done

**What was implemented.** `application/use_cases/record_trajectory.py::record_trajectory`
writes one append-only `trajectory` row (AD-19) the instant a Story frame's own commit-guard
row itself reaches `done` inside `apply_step_result`'s own unit of work
(`apply_step_result.py::_maybe_record_trajectory`, gated on `row.kind == COMMIT_KIND`). The
commit-guard is the frame's last row and the only point at which `end_sha` ("HEAD after the
commit-guard") is a fact rather than a guess: by construction the walk never reaches it until
the frame's `build` row is `done` and its `verify` row is `done | skipped`
(`templates/story.yaml`'s own order — `verify`'s `on_fail` sends a failure back to `build`,
and the commit-guard is queued only once `verify` finishes), so `record_trajectory`'s own
`build_row.status != done` / `verify_row.status not in (done, skipped)` checks are a safety
belt over an unusual Template shape, not the trigger itself. `skip_story` reaches the same row
the same way — `signal_effects.py::_skip_frame` rewrites the commit-guard's message and
re-queues it rather than skipping it — so an Operator-skipped Story still completes through
this one trigger; no second wiring was needed for it.

The row carries: `run_id`/`project_id`/`repository_id`/`story_id` off the Run and the `build`
row, `epic_index` parsed off the frame's own `epics[n]` prefix (`0` when there is none),
`frame`, `harness`/`model` off the `build` row's latest non-empty attempt, `attempts` — the
`build` row's own attempts only, each `{n, started_at, ended_at, exit_code, session_id,
cost_usd, tokens_in, tokens_out, route}` where `route` is that attempt's own `StepStatus`
(`"done"` for the one that finished the Story) — `gate_results.build` (`"liveness"`, the
row's own gate, never green per NFR-2), `.verify` (`"done"`/`"skipped"`), `.commit_guard`
(`"done"`/`"no changes"`, read off the commit-guard row's own `reason`), and
`.protected_paths.{hits, accepted}` (hits flattened from every `protected_path` gate record
about a row of the frame; accepted is the Run's own `accepted_paths`); `cost_usd`/`tokens_in`/
`tokens_out` summed over the `build` attempts; `wall_clock_seconds` summed over the attempts
that recorded both ends (an interrupted attempt with no `ended_at` contributes nothing);
`story_file` — the committed text at `end_sha`, read through `Git.list_files`/`read_file`
over the Run's own `worktree_path`, the same pattern 5.8's `harness_readiness_evaluate.py`
already established; `start_sha` — the frame's first `build` attempt that recorded one
(AD-17's own rule, reused); `end_sha` — `Git.head_sha(worktree_path)` at the moment the
commit-guard's own `done` is applied; `human_actions` — every gate record about a row of the
frame whose `event` is a park (`ParkKind`) or an Operator signal (`SignalKind`), explicitly
excluding the automatic bookkeeping AD-9 records without either (`redispatch`, `retry_auto`)
and the Run's own lifecycle lines; `recorded_at`.

**Idempotency (AD-19).** `TrajectoryRepository` exposes `add` and `list_for_project` only —
no update, no delete. `add` reads the row back by `(run_id, frame)` before inserting and does
nothing if one is already stored, backed by a `unique (run_id, frame)` index at the table
itself (`0009_trajectory.py`). `apply_step_result` calls `record_trajectory` unconditionally
whenever the commit-guard row reaches `done`, so a durable-step replay after a restart calls
it again with the same arguments — the row it already wrote is read back and nothing new is
inserted.

**A Story with a skipped verify vs. a green one.** Both flow through the exact same trigger
and the exact same code path: `verify`'s own executor (`shell.py`) returns `status: skipped`
when the row's `quality_gate_command` resolved to nothing, which is applied through
`apply_step_result` precisely like a `done` result — the row still reaches a `FINISHED`
status, the commit-guard still runs next, and `record_trajectory` still fires on the
commit-guard's own `done`. The only difference is `gate_results.verify`, which reads back
`"skipped"` instead of `"done"` — nothing else about the record's shape or timing changes.

**Files changed (11 added, 7 modified):**
- `domain/entities/trajectory.py` — added: `Trajectory`, `AttemptRecord`, `GateResults`,
  `ProtectedPathsResult`, `ProtectedPathHit`, `HumanAction`.
- `domain/ports/trajectories.py` — added: `TrajectoryRepository` (`add`, `list_for_project`).
- `application/use_cases/record_trajectory.py` — added: `record_trajectory` and its helpers.
- `application/use_cases/apply_step_result.py` — modified: `_maybe_record_trajectory`, called
  right after the row's own status write; imports `COMMIT_KIND` and `record_trajectory`.
  363 → 394/400.
- `application/use_cases/writers.py` — modified: `WriterPorts.git`/`.trajectories`, both
  defaulted `None` so every existing construction keeps working unchanged.
- `infrastructure/db/models/trajectory.py` — added: `TrajectoryRow`, `jsonb` for `attempts`/
  `gate_results`/`human_actions`, `unique (run_id, frame)`.
- `infrastructure/db/repositories/trajectories.py` — added: `SQLAlchemyTrajectoryRepository`.
- `infrastructure/db/{__init__,models/__init__,repositories/__init__}.py` — modified: the new
  model and adapter registered beside the existing ones.
- `infrastructure/db/writers.py` — modified: `open_writer_ports` gains a `git` parameter
  (defaulted `None`, degrades like `tracer`/`spend_writes`) and always builds
  `trajectories=SQLAlchemyTrajectoryRepository(session)`.
- `infrastructure/dbos/startup.py` — modified: `walker_deps`'s `open_ports` (the scope
  `apply_step_result` runs in) now carries `git=git`, the same `Git` adapter `step_ports`
  already holds.
- `alembic/versions/0009_trajectory.py` — added: the `trajectory` table.
- `tests/unit/fakes/trajectories.py` — added: `FakeTrajectoryRepository`, idempotent on
  `(run_id, frame)` the same way the adapter is.
- Four new test modules: `tests/unit/application/test_record_trajectory.py` (the four
  acceptance criteria that exercise the use case directly, plus the degrade/safety-belt and
  branch-coverage cases), `tests/unit/application/test_apply_step_result_trajectory.py` (the
  trigger itself: the commit-guard row and only that row, once and not twice on replay),
  `tests/unit/test_trajectory_repository_adapter.py` (the table's columns and unique index
  off `Base.metadata`, the round trip, `add`'s idempotency, and AC5's "no update or delete
  method" against the concrete adapter class).

**Verification performed** (every gate run in the foreground, its exit code observed
directly):
- `make lint` — exit 0: ruff check/format, `mypy --strict` over `domain/`+`application/`, all
  four import-linter contracts KEPT, env contract unchanged (32 settings fields / 38
  `.env.example` variables — no new setting, none needed), `check_test_pairs` 177 backend
  modules paired (up from 172), `gen:api --check` no drift (no route or schema touched),
  web-client astro-check/eslint/prettier/tsc all clean.
- `make test` — exit 0: 4915 backend unit tests passed (4911 before the two extra
  branch-coverage tests were added, 4869 before this story), 1 skipped;
  `coverage report --include='domain/*,application/*' --fail-under=100` — 100% branch,
  `record_trajectory.py` (88 statements / 18 branches) and `apply_step_result.py` both
  included; web-client 973/973 passed.
- `make openapi` — not run as its own gate: `make lint`'s own `gen:api --check` already
  confirmed `contracts/openapi.json` and `schema.d.ts` have no drift, and this story adds no
  route, no schema field and no UI.
- `make e2e-api` / `make e2e-ui` — not run: no route, no schema field, no UI this story adds
  (same reasoning 5.6/5.7/5.9's own siblings used).
- `make durability` — run, in its own disposable `aio-e2e` stack (the seven
  `ai-orchestrator-host-*` containers were left untouched): the new migration
  (`0009_trajectory`) applies cleanly through the restart-and-orphan proof.

**Anchor check** (the literal command from the dispatch instructions):
```
for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done
```
Flags exactly the five files the dispatch names as pre-existing and none of them mine:
`tests/unit/fakes/{clock,git,workspace}.py` (the sanctioned shared-double exception, carried
from earlier stories on this branch, untouched here) and `tests/e2e/test_harnesses.py` +
`tests/unit/test_harnesses_router.py` (5.8's operator-authorised edit). No pre-existing test
file, `SPEC.md`, `stories.yaml`, `epics.yaml` or `AGENTS.md` was touched. Every test module
this story adds is a brand-new file.

**What was moved to make room, and final line counts.** Nothing was moved: `apply_step_result.py`
had 37 lines of headroom (363/400) and needed about 30 for the import, the trigger call and
`_maybe_record_trajectory`, landing at 394/400. `walk.py` (400/400) and `context.py`/
`agent_tail.py` were not touched at all — the trigger needed nothing from either, since it
runs entirely inside `apply_step_result`'s own unit of work over `WriterPorts`, not through a
`StepContext`/`StepPorts` seam. New modules: `record_trajectory.py` 240, `trajectory.py`
(entity) 115, `trajectories.py` (adapter) 116, `trajectories.py` (model) 55 — all comfortably
under 400.

**What 5-10 / 5-11 must know.**
- **Where the trigger lives.** `apply_step_result.py::_maybe_record_trajectory`, gated on
  `row.kind == COMMIT_KIND` (not on the literal step id `"commit-guard"`, so a Template that
  names its commit row differently still triggers correctly) and `row.status == "done"`. It
  runs unconditionally, every time a commit-guard row reaches `done` — including a Story with
  no operator interaction and a Story that had one, since `human_actions` is what tells the
  two apart, not a second code path.
- **`WriterPorts` grew two optional fields** (`git`, `trajectories`), both defaulted `None`.
  Any future story adding a fifth writer-scope port should follow the same shape: default
  `None`, degrade like `tracer`, wire for real only in `infrastructure/db/writers.py` and
  `infrastructure/dbos/startup.py`.
- **The export endpoint and the Project button are explicitly out of this story's scope**
  (Epic 7, per the brief's own "Out" list) — `TrajectoryRepository.list_for_project` exists
  and is tested, but nothing calls it yet.
- **`apply_step_result.py` is at 394/400** — six lines of headroom left. A story that needs to
  add to it should expect to trim first.

**Operator decisions needed:** none. No anchor conflict was hit and no structural ambiguity
needed a ruling.

**Follow-up review recommended:** false. Self-reviewed against the brief's five acceptance
criteria (all five pass as unit tests — the replay idempotency and the skipped-verify case
each have a dedicated test) and the spine's AD-6/AD-8/AD-9/AD-18/AD-19; no subagent review
pass was run for this dispatch.
