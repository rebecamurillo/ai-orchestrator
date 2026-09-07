---
title: 'Durability proof — restart and orphan test'
type: 'feature'
created: '2026-09-07'
status: 'done'
baseline_revision: 'a7bf0378a722c25f324e9b1d920992e163af1bc6'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      `tests/unit/test_dbos_facade.py`'s `CALLED` tuple no longer means what its comment says:
      it lists `create_schedule`, which the facade stopped calling in this story, and omits
      `apply_schedules`, which it now calls.
    evidence: |-
      The tuple is documented as "Every attribute of `DBOS` the facade calls". The test still
      passes, because it asserts `hasattr(DBOS, name)` and the library still exposes both
      symbols — so the drift is invisible rather than red. Nothing is left unpinned: the new
      `tests/unit/test_dbos_schedule_registration.py` pins `apply_schedules`, its signature and
      its three `ScheduleInput` keys. What remains is a frozen list a later reader would add a
      new facade call to, next to a name the facade abandoned. `test_dbos_facade.py` is an
      anchor and none of hard rule 1's three exceptions covers this, so it needs an operator
      decision, not a story's.
    location: >-
      backend-api/tests/unit/test_dbos_facade.py:42
    severity: low
  - summary: >-
      `status_of`, `wait_for`, a `/healthz` wait and a `docker compose` wrapper now exist in
      four e2e modules, each with its own copy of `HTTP_OK`, `POLL_INTERVAL_SECONDS` and a
      walk deadline.
    evidence: |-
      `test_engine_walker.py`, `test_repo_init.py`, `test_signals.py` and the new
      `test_durability.py` each hold their own. The `wait_until_walked` race this story was
      authorised to fix is what copied wait loops become over time, so the duplication is not
      hypothetical. Extracting them into `tests/e2e/conftest.py` would mean editing the three
      existing modules to use them, which hard rule 1 forbids; this story therefore followed
      the established convention rather than starting a fifth copy of the argument.
    location: >-
      backend-api/tests/e2e/conftest.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** SM-4 and FR-12 claim a Run survives a restart of the orchestrator, and nothing
measures it. Every durability rule in the walker is asserted over a fake engine; no gate has
ever killed the real backend mid-step and looked at what the database and the process table
say afterwards.

**Approach:** Two e2e scenarios in `backend-api/tests/e2e/test_durability.py`, carrying a new
`durability` pytest marker, that `docker compose kill` the backend container mid-Run and bring
it back: one killed while a row holds a real child process, one killed while the Run waits in
its `recv` on a `checkpoint` row. Both assert resumption at the same row, no repeated row, and
exactly one process group for the Run. A `make durability` target runs the marker in a stack of
its own, the way `make e2e` already runs `e2e-api` in one.

## Boundaries & Constraints

**Always:** the walker's step sequence stays at five (`test_dbos_walker.py` freezes it, and
`DBOS_APPLICATION_VERSION` pins it — AD-6); `signal_run` and `apply_step_result` stay the only
writers of status (AD-8); every process and filesystem effect goes through the `Git`,
`Workspace`, `ProcessRunner` ports (AD-14); the e2e suite stays twice-runnable against one
stack, so every Run this story creates ends terminal by the end of its own test; the durability
marker is deselected from `make e2e-api` (the target CI runs against a backend that is *not* a
container), so `make e2e`'s existing selection and its twice-runnable property are unchanged.

**Block If:** the proof cannot be made without changing the walker's five declared steps or
bumping `DBOS_APPLICATION_VERSION` (a spine-level decision — HALT, do not bump); the proof
cannot be made without editing an anchor other than the one `test_engine_walker.py` helper the
operator authorised on 2026-09-06.

**Never:** a new feature; a `time.sleep` standing in for a real wait; a test that skips when the
stack is missing (it fails, naming what is missing); a fix that papers over state a kill leaves
behind rather than reporting it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Kill mid-process | `git.worktree` row `running`, its `install_command` child process alive in one process group | container dies with the child; after restart the engine recovers the walk, the row gets Attempt 2, the Run reaches `done` | a Run that never resumes fails naming the row and its status |
| Rows finished before the kill | `plan` row `done` with one Attempt | replayed from the engine's recorded step output, never re-executed: still exactly one Attempt | a second Attempt on `plan` fails the test |
| Exactly one process | after restart, during Attempt 2 | exactly one process group in the container carries the Run's marker, at every sample | more than one is the orphan FR-12 forbids; zero means the row is not running |
| Kill inside `recv` | Run `needs_you` on a `checkpoint` row | after restart the walk waits again; `continue` resolves it and the Run reaches `done` with one Attempt per row | a Run still `needs_you` after `continue` fails naming its status |
| No compose backend | `docker compose ps -q backend-api` names nothing | the module fails naming what it needs | never skips |

</intent-contract>

## Code Map

- `backend-api/tests/e2e/test_engine_walker.py` -- the racing `wait_until_walked` helper
  (lines 158-170): returns the instant the Run leaves `queued`, so it can capture `running` on
  the way to `needs_you`, which story 4.7's strengthened `== NEEDS_YOU` (line 183) turns into an
  intermittent failure. **Operator-authorised edit, 2026-09-06, scoped to this helper alone.**
- `backend-api/tests/e2e/test_signals.py:109-120` -- `wait_for(client, run_id, targets)`, the
  non-racing shape the fix copies; `TWO_STEP_TEMPLATE` (65-83), the module-owned Template
  convention; `SWEEP_ROUNDS` (253) and the twice-runnable sweep this story must not break.
- `backend-api/tests/e2e/test_clone_check.py::Fixtures` (74-130) -- makes a bare `file://`
  origin under `WORK_DIR/e2e-fixtures` in either topology; `REPO_ROOT`, `MAKE_BARE_REPOSITORY`.
  Reused whole; no second helper.
- `backend-api/tests/e2e/test_run_creation.py` -- `RUNS`, `TEMPLATES`, `PROJECTS`,
  `REPOSITORIES`, `create_project`, `clone_check`, `run_payload`. `create_repository` takes no
  `install_command`, so this module posts the repository body itself.
- `backend-api/tests/e2e/test_repo_init.py:131-153` -- `read_back`'s two-route
  `subprocess` + `docker compose exec` shape; the convention for driving compose from a test.
- `backend-api/src/orchestrator/infrastructure/process/runner.py:52-74` -- `Popen(..., shell=True,
  start_new_session=True)`: a string command runs as `/bin/sh -c "<command>"` and `pgid == pid`,
  so the whole command string — marker included — is in the leader's `/proc/<pid>/cmdline`.
- `backend-api/src/orchestrator/application/steps/git_worktree.py:150-181` -- `_install` runs
  `RunEnvironment.install_command` through `ProcessRunner`; `DEFAULT_TIMEOUT_MIN = 5`.
- `backend-api/src/orchestrator/application/use_cases/start_attempt.py:93-104` -- `_open_the_row`:
  a row already `running` is the interrupted one; its open Attempt is closed `error` and the next
  is numbered after it. This is what the first scenario measures.
- `backend-api/src/orchestrator/infrastructure/dbos/{walker,adapter,facade,startup}.py` -- five
  declared steps (frozen by `tests/unit/test_dbos_walker.py`), `DBOS.launch()` recovers, the
  queue is declared after `start`, `application_version` is pinned (AD-6).
- `backend-api/tests/unit/test_ci_workflow.py:86-94` -- `assert tuple(jobs) == GATES` with
  `GATES = ("lint", "unit", "e2e-api", "e2e-ui", "images")`: a sixth CI job is an anchor edit.
  See Design Notes D5.
- `backend-api/tests/unit/test_makefile.py:33-99` -- `DECLARED_TARGETS`, `LINT_SUBGATES` and the
  `uv`-invocation count for `make -n lint`. A new target is fine; the lint recipe must not change.
- `Makefile:73-113` (`e2e`, `e2e-api`) -- `SUBMAKE` recursion, the `.env.e2e` stack, the
  `down -v` trap. `make durability` reuses it through one variable.
- `README.md:166-224` (`## Contributing`) -- the gate list `tests/unit/test_ci_workflow.py::
  test_the_readme_names_the_gates_the_pipeline_runs` reads.
- `backend-api/pyproject.toml:142-145` -- `[tool.pytest.ini_options]`; the `durability` marker
  is registered here.
- `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` -- AD-8 line 106 and
  the field list at line 344: `pgid` is recorded by the **`agent`** executor, for **`agent`**
  rows. Epic 4 has no agent row. See Design Notes D1.

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/e2e/test_durability.py` -- new: both scenarios, the compose helpers
  (`kill_backend`, `restart_backend`, `started_at`), the `/proc`-based `process_groups(marker)`
  reader, `wait_for`, `wait_for_row`, and the attempt-table printout each scenario emits --
  the whole story; nothing else in `src/` changes.
- `backend-api/pyproject.toml` -- register the `durability` marker -- an unregistered mark is a
  warning, and `-m "not durability"` must select on a marker the suite declares.
- `Makefile` -- add `E2E_MARKER ?= not durability`, thread it into the `e2e-api` recipe, add the
  `durability` target (`$(SUBMAKE) e2e E2E_MARKER=durability`) and put it in `.PHONY` -- the
  marker needs a stack it may kill, which is `make e2e`'s stack, not `make e2e-api`'s.
- `README.md` -- a short paragraph in `## Contributing` naming `make durability`, what it proves
  and why it is not in `make e2e-api` -- the brief asks for it and the README is the gate list.
- `backend-api/tests/e2e/test_engine_walker.py` -- **authorised anchor edit**: make
  `wait_until_walked` wait for a *settled* status, distinguishing "never left `queued`" from
  "left `queued` but never settled". No assertion weakened; see Spec Change Log.

**Acceptance Criteria:**
- Given the compose stack, when `make durability` runs, then both scenarios pass and each prints
  its Run's attempt table (`path`, `n`, `status`, `started_at`, `ended_at`).
- Given a Run whose `git.worktree` row is executing a long `install_command`, when the backend
  container is SIGKILLed and brought back, then `plan` still has exactly one Attempt, the
  interrupted row has Attempt 1 `error` and Attempt 2 `done`, the Run reaches `done`,
  `run.worktrees` has exactly one entry, and the gate record holds `start` once and `done` once.
- Given that same Run after the restart, when the container's process table is sampled repeatedly
  while Attempt 2 runs, then exactly one process group carries the Run's marker at every sample.
- Given a Run parked `needs_you` on a `checkpoint` row, when the backend is SIGKILLed, brought
  back, and then signalled `continue`, then the Run reaches `done` with exactly one Attempt on
  every row and no row executed twice.
- Given `make e2e`, when it runs, then it selects the same tests it selected before this story
  (the `durability` marker is deselected) and the suite is still twice-runnable against one stack.
- Given `make lint`, `make test` and `make openapi`, when they run, then all three pass and the
  contract does not drift (this story publishes no route).

## Spec Change Log

- **`backend-api/tests/e2e/test_engine_walker.py` — operator-authorised, one-off, 2026-09-06.**
  `wait_until_walked` (lines 158-170) polled only until the Run left `queued`, so it could return
  `running` on the way to `needs_you`. Story 4.7 strengthened
  `test_the_engine_picks_the_run_up_and_walks_it` from `!= QUEUED` to `== NEEDS_YOU`, which turned
  that race into an intermittent gate failure — the test has already failed once this way and
  passed on re-run. The operator authorised, in scope and in writing, editing that helper alone so
  it waits until the Run reaches a **settled** status (`needs_you`, `done`, `failed`, `cancelled`)
  rather than merely leaving `queued`, and so its deadline failure distinguishes "never left
  `queued`" (the engine never picked it up) from "left `queued` but never settled" (the walk
  started and stalled) — two different bugs. **No assertion was weakened or deleted:**
  `assert second["starts_now"] is False`, `== NEEDS_YOU`, and the exact `park_kind` / `park_path`
  assertions all stand unchanged, and nothing else in the file changed. Coverage strictly exceeds
  what the file proved before: the race is now impossible rather than unlikely — the helper cannot
  return a non-settled status at all, so `== NEEDS_YOU` is proven for every scheduling order
  instead of for the orders that happened to poll late enough, and a hang is still diagnosed by a
  deadline message that names which of the two failures it was. No `time.sleep` stands in for the
  wait. **This authorisation is about this helper, this once — not a standing rule, and not a
  precedent any later story may cite on its own to edit an anchor.**

## Review Triage Log

### 2026-09-07 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 20: (high 1, medium 8, low 11)
- defer: 2: (high 0, medium 0, low 2)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[high]` `[patch]` The durability marker ran in no CI job at all — worse than before the
    story, because `E2E_MARKER ?= not durability` made the pipeline's `e2e-api` job actively
    deselect it, so the one production defect this proof found was guarded by a command only a
    human types. D5 had deferred this to the operator on the grounds that a sixth job collides
    with `test_ci_workflow.py:87`. The review's own finding showed the third option: a *step*
    of an existing job breaks no frozen assertion, and `make durability` builds its own compose
    stack, so the `e2e-api` job's host-process backend is no obstacle. Added a `Durability
    proof` step running `make durability` to that job (after its own stack is stopped, so the
    two never share a port), raised its timeout to 40 minutes for the image build, and added
    `tests/unit/test_durability_gate.py::test_the_pipeline_runs_the_proof` so the wiring cannot
    be dropped silently. `test_ci_workflow.py` still passes unmodified. D5 is superseded and
    rewritten below.
  - `[medium]` `[patch]` The orphan assertion claimed more than a container kill can prove:
    `docker compose kill` tears down the PID namespace, so the previous child is gone before any
    code of ours could reap it, and the test would pass with `kill_group` deleted. Narrowed the
    module docstring, the test name and its docstring to the double-start net the count really
    is, and said plainly where the reaping half is actually proven. No assertion weakened — the
    claim was.
  - `[medium]` `[patch]` Neither scenario released its Run if it ended non-terminal, and the
    leftover-slot test checked only the parked Run and only the first page of `GET /runs` — so
    the module's own twice-runnable promise had a hole on exactly the failure path. Both
    fixtures are now `yield` fixtures whose `finally` cancels the Run, and the check covers both
    Runs across every page (`held_run_ids` follows `next_cursor`).
  - `[medium]` `[patch]` `attempt_table` omitted `ended_at`, which this story's own acceptance
    criterion names and which is the field that shows the interrupted Attempt being closed. Added
    it, with both timestamps `-`-safe (`Attempt.started_at` and `.ended_at` are both nullable),
    and the per-row Attempt list is now read once instead of twice.
  - `[medium]` `[patch]` `report(...)` was the last statement of each fixture, so the diagnostic
    table printed only when the scenario had already succeeded. Moved into the `finally`, reading
    the table itself and swallowing its own failure so a reporting error cannot replace the
    failure being reported.
  - `[medium]` `[patch]` `--strict-markers` was off, so `-m "not durabilty"` would have selected
    everything and let `make e2e-api` kill the stack it was running against while reporting
    success. Added to `addopts`; only `durability`, `parametrize` and `skipif` are in use, so
    nothing else moved.
  - `[medium]` `[patch]` Nothing pinned the marker plumbing: deleting `-m` from the `e2e-api`
    recipe, or the `durability` target, broke no test. Added
    `tests/unit/test_durability_gate.py` — the marker is declared, `--strict-markers` is on, the
    module carries the mark, `make -n e2e-api` selects `not durability`, `make -n durability`
    inverts it and recurses, the target is `.PHONY`, and the pipeline invokes it.
  - `[medium]` `[patch]` `restart_backend` discarded compose's output, so a genuinely failed
    `docker compose up` surfaced two minutes later as an unexplained `/healthz` timeout — hard
    rule 7. It now hands the output back and `wait_healthy` reports it with the timeout.
  - `[medium]` `[patch]` `attempt.started_at.isoformat()` would raise on a nullable column, in
    the reporter whose whole job is to explain a failure. Both timestamps go through `_at`.
  - `[low]` `[patch]` `run_of` can answer `None`, so the two "the Run ended badly" failure paths
    raised `AttributeError` instead of the diagnostic they exist to print. One `ended_badly`
    helper, guarded.
  - `[low]` `[patch]` A refused `continue` after the restart was reported as a two-minute walk
    stall; the fixture now fails on the refusal, naming it — a refused signal and a `recv` that
    never woke are different bugs.
  - `[low]` `[patch]` `container_id` picked the first of however many containers `compose ps`
    named; it now refuses more than one, since killing one and inspecting another proves nothing.
  - `[low]` `[patch]` No `docker` call had a deadline of its own: every wait bounded its polling,
    none bounded one call. `run(...)` carries `DOCKER_TIMEOUT_SECONDS`.
  - `[low]` `[patch]` The gate-record assertions read the Run-status constants `DONE`/`"start"`.
    Those are a different vocabulary that happens to share two spellings; they now have their own
    `RUN_STARTED` / `RUN_FINISHED`.
  - `[low]` `[patch]` Scenario 1 checked Attempt counts on `plan` and `checkout` but not on
    `after`; `test_no_other_row_of_the_interrupted_run_ran_twice` closes it for every other row.
  - `[low]` `[patch]` The `parked` fixture asserted "still `needs_you` after the restart" inside
    itself, so that failure reported as a fixture error against every test of the scenario. It is
    captured and asserted in the test that names it.
  - `[low]` `[patch]` `_AN_INSTANT` reached through the module under test for `datetime`/`UTC`
    and was defined after its only use. Imported directly and hoisted.
  - `[low]` `[patch]` `test_a_schedule_is_registered_by_create_or_replace_not_by_create` proved
    only the positive. `DBOS.create_schedule` is now patched to raise if the facade calls it, and
    the three `ScheduleInput` keys are pinned against the library (a `TypedDict` rename is a
    silent no-op otherwise).
  - `[low]` `[patch]` The README carried two gate lists and only one gained `make durability`,
    leaving the other's "every one of them runs" false; and "~4 minutes" was a guess. Both fixed
    — the measured figure is ~75 s of scenarios plus the stack build.
  - `[low]` `[patch]` The two guard tests differed only in whitespace. They now cover distinct
    refusals, and `test_the_module_skips_nowhere_at_all` asserts the never-skip property over the
    whole file rather than over one function.

## Design Notes

**D1 — `pgid` is not recorded in Epic 4, and the brief's precondition is corrected
(spine-first).** The brief says to wait until the row is `running` "with an Attempt and a
recorded `pgid`". Nothing calls `AttemptRepository.mark_started`, so `attempt.pgid` is `None`
for every Attempt this epic can produce — and the spine says that is correct: AD-8 (line 106)
gives the write to "the **`agent`** executor … before `ProcessRunner.wait`", and the field list
(line 344) lists `pgid` among the columns kept "for **`agent`** rows". Epic 4 ships no `agent`
step (SPEC non-goals). The precondition is therefore "the row is `running` with an open Attempt
**and its process is visible in the container**", which is the same fact read where it actually
exists, and it is what the brief's own assertion already reads (`ps`-equivalent, filtered).
Recorded so a later story does not read the brief alone and file this as a regression.

**D2 — the marker, not the worktree path, is what identifies the Run's process.** The brief
suggests filtering `ps -o pgid,cmd` on the worktree path; neither `/bin/sh -c "<install>"` nor
its `sleep` child carries that path in its command line, so the filter would match nothing. The
Repository is created with `install_command = ": <marker>; sleep <n>"` — a unique token per
scenario, and a two-command string so no shell can `exec`-optimise the marker away. Because
`RealProcessRunner` starts a string command with `shell=True, start_new_session=True`, the
`/bin/sh` leader is the process-group leader and its `/proc/<pid>/cmdline` holds the marker.
Counting *distinct process groups* whose command line contains the marker is exactly FR-12's
"exactly one Harness process for that Run".

**D3 — `/proc`, not `ps`.** The backend image installs no `procps`, so there is no `ps`. The
reader is a POSIX `sh` script over `/proc/[0-9]*/cmdline` and field 3 after the `)` in
`/proc/<pid>/stat` (the process group). It excludes its own process group — `docker compose exec`
gives the exec'd process a group of its own — so the checker never counts itself or the
short-lived subshells its own command substitutions fork.

**D4 — the scenarios use Templates of this module's own, not `repo-init@1` / `epic@1`.** The
brief names both. `repo-init@1`'s `install` row is `bmad.install`, which fetches a package from
the npm registry (`test_repo_init.py` gives it 900 s) — with the brief's own "whole test under
5 minutes" rule that is unaffordable, and the row proves nothing this story is about. `epic@1`
would need a Repository carrying a `stories.yaml` and an already-done story file to keep an
`agent` row from planning. Both scenarios instead use a Template the module owns, the way
`test_engine_walker.py` and `test_signals.py` both already do: scenario 1 is `git.worktree`
(carrying the long `install_command`) + `shell`, scenario 2 is `checkpoint` + `shell`. The
mechanism the brief asked for — a real child process held by a real row, and a real `recv` —
is unchanged; only the Template that reaches it is this module's.

**D5 — CI (brief AC2) runs the proof as a step, not as a sixth job.** The brief asks for the
marker to run "in the `e2e-api` job (or a dedicated job)". A *dedicated job* is out: it collides
with `tests/unit/test_ci_workflow.py:87` — `assert tuple(jobs) == GATES`, `GATES` being exactly
five — an existing test file no hard-rule-1 exception covers, and AD-18 fixes those five in that
order anyway. Running the marker *inside* the `e2e-api` job's own gate is also out: that job
starts backend-api from source on the runner (`uv run … -m orchestrator.main &`), so there is no
container to kill, which is why `E2E_MARKER`'s default deselects it there. What is left, and what
this story does, is a **step** of that job running `make durability` — which builds a compose
stack of its own, so the job's host-process backend is beside the point. It runs after that
backend's stack is stopped, so the two never share a port; it needs no credential, because
`scripts/generate-env.sh e2e` writes the whole environment itself; and the job's timeout goes to
40 minutes because the step builds the backend image before it can kill a container of it. No
frozen assertion in `test_ci_workflow.py` moves: the job list, the per-job `make` target, the
action pins and the credential sweeps are all unchanged, and
`test_every_make_target_the_pipeline_runs_exists` is satisfied because `durability` is in
`.PHONY`. `tests/unit/test_durability_gate.py` pins both halves of the selection so neither can be
dropped silently. **Unverified on this machine:** nothing in this repository can run GitHub
Actions (`test_ci_workflow.py`'s own docstring says so), so the step's runtime on a runner — image
build plus ~75 s of scenarios, inside 40 minutes — is a projection from the local timings, not a
measurement.

**D6 — the marker is deselected from `make e2e-api`, and `make e2e` is unchanged.** `make e2e-api`
attaches to whatever stack is configured — in CI that is a bare process. `E2E_MARKER ?= not
durability` on the `e2e-api` recipe keeps every existing selection exactly as it was (so the
144-test baseline and the twice-runnable property are untouched), and `make durability` recurses
through `make e2e` with `E2E_MARKER=durability`, getting the disposable stack, the `.env.e2e`
guard and the `down -v` trap for free rather than copying them.

**D7 — the restart is proven, not assumed.** `docker compose kill` sends `SIGKILL`, and
`restart: unless-stopped` means the container may come back on its own before
`docker compose up -d backend-api` runs — so the test asserts the container's
`State.StartedAt` changed rather than assuming its own command caused the restart, and then waits
on `/healthz` the way `tests/e2e/conftest.py::stack` does.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; 4 import-linter contracts kept.
- `make test` -- expected: exit 0; `domain/` + `application/` at 100 % branch.
- `make openapi` -- expected: exit 0, no drift (this story publishes no route).
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- expected: exit 0, the same selection as before.
- `PATH="$HOME/.docker/bin:$PATH" make durability` -- expected: exit 0; both scenarios pass and
  print their attempt tables, `ended_at` included.
- `make e2e-ui` -- expected: exit 0; nothing left listening on `127.0.0.1:4321`.
- `PATH="$HOME/.docker/bin:$PATH" uv run --locked --directory backend-api pytest tests/e2e -q -m
  "not durability"` run twice against one manually-held stack -- expected: the same pass count
  both times, and zero `needs_you`/`queued` rows after each. The marker is excluded deliberately:
  a bare `pytest tests/e2e` selects it and SIGKILLs the backend under every other module, which is
  what `make e2e-api`'s own `-m` default exists to prevent.

## Auto Run Result

Status: done

**What was implemented.** Epic 4's acceptance proof: two e2e scenarios that SIGKILL the
`backend-api` container in the middle of a Run and bring it back, a `durability` pytest marker
and a `make durability` target that runs them in a stack of its own, a CI step that runs that
target, and the one production fix the proof uncovered.

**The one real defect it found, and it is a serious one.** `RealEngine.schedule` called
`DBOS.create_schedule`, which refuses a `schedule_name` the *system database* already holds. The
schedule row outlives the process that wrote it, so from 4.11 onward the backend crashed during
start-up on **every boot after the first against any database it had already run against** — the
socket was never bound and the container never became healthy. Nothing before this story ever
started a second process against a live system database, so every gate stayed green: `make e2e`
and CI both create a database, run once, and `down -v`. Fixed at the one module that names the
library (AD-6): `DBOS.apply_schedules([entry])` creates or replaces, preserving `last_fired_at`
so a restart does not make a daily job fire twice, and removing no schedule absent from the list.
The first `make durability` run failed on exactly this, with the container's own traceback
(`UniqueViolation … workflow_schedules_schedule_name_key … Key (schedule_name)=(clone_check)`).

**Files changed**

- New: `backend-api/tests/e2e/test_durability.py` — both scenarios, the compose helpers, the
  `/proc`-based process-group reader, the waits, and the attempt table each scenario prints.
- New: `backend-api/tests/unit/test_dbos_schedule_registration.py` — which library call registers
  a recurring job, and why it must be the create-or-replace one.
- New: `backend-api/tests/unit/test_durability_guard.py` — the proof refuses a missing container
  and never skips; the whole module skips nowhere.
- New: `backend-api/tests/unit/test_durability_gate.py` — the marker is deselected from
  `make e2e-api` and selected by `make durability`, and the pipeline runs it.
- Changed: `backend-api/src/orchestrator/infrastructure/dbos/facade.py` — the restart fix above.
- Changed: `Makefile` — `E2E_MARKER ?= not durability` threaded into `e2e-api`, the `durability`
  target (recursing through `make e2e` so the stack is defined once), both in `.PHONY`.
- Changed: `backend-api/pyproject.toml` — the `durability` marker and `--strict-markers`.
- Changed: `.github/workflows/ci.yml` — a `Durability proof` step in the `e2e-api` job, timeout
  20 → 40 minutes. The five jobs, their order and their targets are untouched.
- Changed: `README.md` — `make durability` in both gate lists, what it proves, why it is not part
  of `make e2e-api`, and that CI runs it as its own step.
- Changed (**operator-authorised anchor edit**): `backend-api/tests/e2e/test_engine_walker.py` —
  `wait_until_walked` waits for a settled status. See **Spec Change Log**.

**Review findings.** 20 patched (1 high, 8 medium, 11 low), 2 deferred, 6 rejected. Follow-up
review recommended: **true** — one patched finding was `high` severity (the proof ran in no CI
job), which sets the flag on its own; the score from the rest is 3 × 8 + 1 × 11 = 35.

Rejected, with the reason, because each could otherwise be re-raised: an in-file note recording
the anchor authorisation (the operator's grant says *nothing else in that file changes*, and names
this spec's change log as the record); asserting the Attempt's `interrupted` *reason* (the entity
has no reason column — `error` plus a closed `ended_at` is all the interruption stores, and
`interrupted` is a log line in `start_attempt`); a sampling window that could observe zero
processes (`wait_for_process` returns only once a group is there, so the window starts after the
process exists and lasts 7.5 s against a 60 s command); `E2E_MARKER` being overridable from the
environment (that is the mechanism `make durability` uses); the process poll being tighter than
the process it waits on (each poll is a `compose exec`, already ~0.3 s); and creating an
`epic-4-handoff.md` (no such file convention exists — 4.9, 4.10 and 4.11 all recorded their
handoff notes in their own Auto Run Result, as this does).

**Verification, as run on this machine, all after the patches:**

- `make lint` — exit 0. ruff, `ruff format --check` (414 files), `mypy --strict` over `domain/` +
  `application/` (93 files), `lint-imports` **4 contracts kept / 0 broken**, env contract 30 ↔ 36,
  backend test pairs, `gen:api --check`, astro check 0 errors, eslint, prettier.
- `make test` — exit 0. Backend **4072 passed / 23 skipped**; the re-report over `domain/` +
  `application/` is **100 % branch** (`--fail-under=100`, 0 missed). Web-client 973 passed.
- `make openapi` — exit 0, no drift: this story publishes no route.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` — exit 0; **144 passed, 11 deselected**, 34 subtests.
  The 144 is the same selection as before this story: the marker is what the 11 are.
- `PATH="$HOME/.docker/bin:$PATH" make durability` — exit 0; **11 passed, 144 deselected in 73 s**,
  both attempt tables printed with `ended_at`. The interrupted row reads Attempt 1 `error` closed
  at the kill and Attempt 2 `done` exactly 60 s later; `plan` holds one Attempt throughout.
- `make e2e-ui` — exit 0; **118 passed**. `127.0.0.1:4321` was free before and is free after.
- **Twice-runnable, re-verified against one manually-held stack**: the default selection ran
  three times (144 passed each time) with the durability marker run *in between*, and
  `select status, count(*) from run group by status` showed **zero `queued` and zero `needs_you`
  rows after every pass**. The kill and restart do not break the property, and both of this
  module's Runs end terminal — released in a `finally` even when a scenario fails.
- Not verifiable here: the CI step itself. Nothing in this repository can run GitHub Actions.

**For the Epic 4 handoff**

- **The restart fix is the epic's most consequential finding.** Until this commit the orchestrator
  could not be restarted against a database it had already run against. Any future start-up
  registration that is not idempotent reintroduces the same class of bug, and `make durability` is
  now the only gate that would catch it — because it is the only thing that starts a second
  process against a live system database.
- **`pgid` is unrecorded for the whole of Epic 4, by the spine's own design.** AD-8 gives the write
  to the `agent` executor and the field list keeps `pgid` "for `agent` rows". The consequence is
  live today: `signal_effects._cancel` collects `attempt.pgid` and always finds `None`, so
  `cancel` kills no process group. Nothing in Epic 4 leaves a process running at a stop, so it
  costs nothing here — Epic 5's `agent` kind is the first row that would, and it must land the
  `mark_started` write with it.
- **The orphan clause of FR-12 is proven only half-way.** Killing the container destroys its PID
  namespace, so the child is gone by the topology rather than by `kill_group`. The reaping half
  needs a kill that leaves the process table standing, which is Epic 5's `agent` row with a
  recorded `pgid`.
- **`tests/unit/test_dbos_facade.py::CALLED` is stale** (deferred item 1) and needs an operator
  decision, since it is an anchor.
- **The brief's `repo-init@1` / `epic@1` scenarios were not used** (D4): `bmad.install` fetches
  from npm and cannot fit the brief's own five-minute budget. Neither shipped Template is exercised
  by this proof; `tests/e2e/test_repo_init.py` still covers `repo-init@1` end to end.

**Residual risks**

- The CI step is unverified on a runner: if the image build plus the scenarios exceed 40 minutes,
  the `e2e-api` job times out. The fix is a larger timeout or moving the step to `images`, and the
  first CI run on this branch will say which.
- `make durability` costs ~75 s of scenarios plus a stack build; it is not part of `make e2e`, so
  the ordinary loop does not pay for it and does not get its coverage either.
- The two scenarios use Templates of this module's own. A change to how the planner expands a
  shipped Template would not be caught here.
