---
title: 'Process runner, workspace, and the plan.check, shell, checkpoint kinds'
type: 'feature'
created: '2026-09-06'
status: 'blocked'
review_loop_iteration: 0
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-7-process-runner-workspace-and-basic-kinds.md'
  - 'backend-api/AGENTS.md'
warnings: []
baseline_revision: '8195e5b'
---

## Auto Run Result

Status: **blocked**

**Blocking condition.** `make e2e` fails on one pre-existing anchor test —
`backend-api/tests/e2e/test_engine_walker.py::test_a_second_run_on_the_same_repository_does_not_run_while_the_first_holds_it`
— as a direct, deterministic, unavoidable consequence of this story doing exactly what it
was scoped to do. The story's implementation, unit tests (100% branch over `domain/` +
`application/`), and every other gate are complete and green; this one e2e assertion is the
sole open item, and hard rule 1 forbids fixing it myself. See **Design Notes** for the full
analysis and **what the operator needs to decide**.

**What was implemented.**

- `domain/ports/process.py` — `Handle`, `Outcome`, `ProcessRunner` Protocol (AD-14).
- `infrastructure/process/{runner,__init__}.py` — `RealProcessRunner`: `subprocess.Popen`
  in its own session/process group, `wait` enforcing `timeout_min` (`SIGTERM` → 10 s →
  `SIGKILL`), `kill_group` idempotent, environment built from the caller's map plus
  `PATH`/`HOME`/`LANG`/`TERM=dumb`/`GIT_TERMINAL_PROMPT=0` only.
- `domain/ports/workspace.py` + `infrastructure/workspace/{fs,__init__}.py` — `Workspace`
  Protocol and `FsWorkspace`: rooted at one worktree (or `None` before `git.worktree` has
  run), every path relative and traversal-checked (`..`, absolute → `WorkspaceError`).
- `tests/unit/fakes/{process,workspace}.py` — the shared fakes (AD-18).
- `application/steps/{plan_check,shell,checkpoint}.py` — the three executors, each
  registering itself on its own kind.
- `application/steps/context.py` — `StepPorts` grows additively: `process` and `workspace`
  (a factory, not an instance — see Design Notes), both defaulted to `None` so every
  existing `StepPorts(git=..., clock=..., work_dir=...)` call site keeps working; a new
  `log_path(ctx)` helper shared by any kind that starts a process.
- `application/templates/{reader,lists,plan}.py` — `PlanReader.record` gains an optional
  `branch` kwarg and a new `plan_branches` map; `plan_check_row` now carries its own copy of
  `base_dir`, `url`, `base_branch`, `plan_refs` and `list_branches`, so `plan.check` — which
  runs before any worktree exists — has everything it needs to ask `Git` again.
- `infrastructure/dbos/startup.py` — `walker_deps` wires `RealProcessRunner()` and
  `FsWorkspace` (the class, as the factory) into `StepPorts`; imports `checkpoint`,
  `plan_check` and `shell` to run their `register(...)` calls (see Design Notes on why here
  and not in `application/steps/__init__.py`).
- Ten new unit test modules, two new shared fakes.

**Files changed**

- New: `backend-api/src/orchestrator/domain/ports/{process,workspace}.py`
- New: `backend-api/src/orchestrator/infrastructure/process/{__init__,runner}.py`
- New: `backend-api/src/orchestrator/infrastructure/workspace/{__init__,fs}.py`
- New: `backend-api/src/orchestrator/application/steps/{plan_check,shell,checkpoint}.py`
- New: `backend-api/tests/unit/fakes/{process,workspace}.py`
- New: `backend-api/tests/unit/test_{process_runner,fs_workspace,plan_check_executor,shell_executor,checkpoint_executor,plan_check_row_with_resolved}.py`
- Changed: `.../application/steps/{context,__init__}.py`,
  `.../application/templates/{reader,lists,plan}.py`, `.../infrastructure/dbos/startup.py`

## Design Notes

**`run.plan_refs` already existed — the brief's `plan_files` migration was not needed.**
The brief assumed `[ASSUMPTION: plan_files is a small JSON list on the Run added by the
planner story's migration or here]`, but 4.2/4.4 already added `Run.plan_refs: dict[str,
str]` (`{path: sha}`), migrated in `0005_run` and populated by the planner. Adding a second,
differently-shaped field would have been the second copy this codebase's own voice warns
against. The gap the brief was actually pointing at — `plan.check` needs to know *which
branch* each recorded file came from, not just its commit — is real, and is what
`PlanReader.plan_branches` / `plan_check_row`'s `list_branches` key closes, additively, with
no new migration.

**`StepContext` gained no new field; `plan.check`'s own data travels in `with_resolved`
instead.** AD-9's field list (`row, with_resolved, cwd, frame_start_sha, previous_attempt,
attempt, resume_signal, ports`) is spine-frozen and matches 4.6's landed code exactly; the
brief's `ctx.run` and `ctx.settings: StepSettings{...}` do not exist and are not what 4.6
built. `plan.check` runs *before* `git.worktree`, so it cannot read `run.worktree_path`
either way; everything it needs (`base_dir`, `url`, `base_branch`, `plan_refs`,
`list_branches`) is planner-computed, per-row data — exactly what `with_resolved` exists
for — so it travels there, the same channel every other kind's resolved `with` already
uses. Spine binds over the brief's imagined field list.

**Project environment variables are not wired into `shell` in this story.** AD-5 names them
as part of `HARNESS_ENV_CONTRACT`, built by `env_for(attempt)` for the `agent` kind (Epic 5)
— nothing in the landed codebase decrypts a Project's own vars for a `shell` row yet, and
`with_resolved` cannot carry them (it is a stored, API-read column; storing a decrypted
secret there is exactly what AD-5 forbids). `shell` passes `env={}`; `ProcessRunner` still
adds `PATH`/`HOME`/`LANG`/`TERM`/`GIT_TERMINAL_PROMPT` underneath it. Flagged as a gap for
whichever story wires `Crypto` + `ProjectRepository` into a process-running kind.

**`Workspace` ships fully built and tested, but unwired into `StepContext`/`StepPorts` as an
instance.** No kind in this story reads or writes the worktree (`plan.check` uses `Git`
directly on the base clone; `shell` only needs a `cwd`; `checkpoint` needs nothing). A
`Workspace` is rooted at `run.worktree_path`, which is per-Run, while `StepPorts` is built
once at the composition root — so `StepPorts.workspace` is a **factory**
(`Callable[[str | None], Workspace]`, `FsWorkspace` itself passed as the value), not an
instance, ready for 4.8's git kinds (the first to actually need one) to call with the row's
own `ctx.cwd`.

**`process` and `workspace` on `StepPorts` default to `None`.** Three existing, frozen test
files construct `StepPorts(git=..., clock=..., work_dir=...)` with exactly those three
keywords (`test_step_executor_registry.py`, `test_dbos_walker.py`,
`test_walk_use_case.py`). Growing `StepPorts` "additively" (4.6's own docstring) had to mean
optional fields with defaults, not a signature change those anchors would have had to be
edited to keep compiling — which hard rule 1 forbids regardless.

**Registration moved out of `application/steps/__init__.py` and into
`infrastructure/dbos/startup.py`.** The registry docstring's own plan — "each by calling
`register` beside its module" — collides with a real circular import: `checkpoint.py` and
`shell.py` need constants from `application/templates/` (`LABEL_SEPARATOR`, `ON_FAIL_KEY`,
`COMMAND_KEY`, …), and `application/templates/model.py` / `plan_model.py` import
`application/steps` right back for `KIND_META`. Importing `checkpoint`/`plan_check`/`shell`
from *inside* `application/steps/__init__.py` reaches back into a `templates` module that is
still mid-import whenever `templates` — not `steps` — is the first thing anything imports
(confirmed by running it: `ImportError: cannot import name 'ForEach' from partially
initialized module`). `infrastructure/dbos/startup.py` is a full AD-2 layer above
`application/`, so by the time its import runs, `application.steps` has always already
finished initialising, whoever asked for it first. Each kind's own module still calls
`register(...)` beside itself, exactly as planned — only the *trigger* that imports the
three modules moved.

**A BSD `kill()` quirk, handled rather than worked around.** On Darwin, signalling a process
group that has been sent `SIGTERM` but not yet reaped by `Popen.wait()` answers signal `0`
with `EPERM`, not `ESRCH` — only after reaping does it become `ESRCH`. `_signal_group`
treats any `OSError` (not just `ProcessLookupError`) as "nothing left to signal", which is
correct on every platform: a `PermissionError` here is never a real permission problem,
because this process is always its own child's parent.

**A second `except (A, B):` formatter bug, sidestepped rather than fought.** `ruff format`
0.16.5 rewrites `except (ProcessLookupError, PermissionError):` into the invalid
`except ProcessLookupError, PermissionError:` (reproduced in isolation, filed as a
observation here rather than upstream — out of this story's scope). Caught `OSError` once
instead: simpler, and it avoids the bug entirely.

**The blocking e2e conflict, in full.**
`tests/e2e/test_engine_walker.py` is a 4.6 anchor whose own docstring already states "no
kind can run yet, so today the walk stops on the first row; from 4.7 the same Run will get
further and from 4.8 it will finish" — anticipating that registering executors would change
how far the walk gets, but assuming full completion needed the git kinds (4.8) too. Its
fixture Template, `LEAF` (defined in the also-frozen `tests/e2e/test_run_creation.py`,
reused via import), is `plan.check` + one `shell` step and **nothing else** — no
`git.worktree`. With `plan.check` and `shell` both registered, exactly as this story
requires, that Run now reaches `done` inside 4.6's own walker test, one story earlier than
the anchor's author expected, because this particular fixture never needed a git kind to
begin with.

`test_a_second_run_on_the_same_repository_does_not_run_while_the_first_holds_it` asserts
the *first* Run still holds the Repository partition (AD-12) when a *second* Run on the same
Repository is created immediately after. Once the first Run is `done` rather than parked,
the partition and the global slot are both free, so `create_run`'s own pre-flight correctly
reports `starts_now: True` — and the test's `assert second["starts_now"] is False` fails,
every time, deterministically:

```
FAILED tests/e2e/test_engine_walker.py::test_a_second_run_on_the_same_repository_does_not_run_while_the_first_holds_it
    assert second["starts_now"] is False
E   assert True is False
1 failed, 123 passed, 27 subtests passed in 21.98s
```

This is the same mechanism the operator's own hazard note named for
`test_run_creation.py::test_get_reads_back_the_created_run` ("Runs reach a terminal status,
which frees the slots") — it did **not** fail this run — surfacing a second time, in a place
the note did not name. I looked for a fix touching only new code: there is none. The Run
reaching `done` is `shell`'s and `plan.check`'s correct, required behaviour; there is no
alternative implementation of this story's own scope that keeps that Run parked. Hard rule 1
gives no exception that fits (not a pending-gate registry, not a placeholder assertion, not
a nondeterministic third-party output), so the anchor was not touched.

**What the operator needs to decide.** Whether to accept this as a known, tracked residual
of landing 4.7 correctly (the same category the hazard note already accepted for the named
test) and authorise a narrow fix to `test_engine_walker.py` under a hard-rule-1 exception, or
to give `LEAF` (in `test_run_creation.py`) a `git.worktree` step so the fixture keeps parking
until 4.8 as originally assumed, or some other resolution. Both files are anchors; either
fix is outside what I may do unilaterally.

## Verification

```bash
make lint   # exit 0 — ruff, ruff format --check, mypy --strict (domain/+application/),
            #   lint-imports (4/4 contracts kept), env contract 27↔33, test pairs 120/120
            #   backend + 42/42 web-client, astro check 0/0/0, eslint, prettier
make test   # exit 0 — backend 3621 passed / 23 skipped; domain/+application/ 100% branch
            #   (--fail-under=100, 0 missed); web-client 722 passed
make openapi   # exit 0 — no drift (this story publishes no route)
PATH="$HOME/.docker/bin:$PATH" make e2e
            # exit 1 — 123 passed, 27 subtests passed, 1 failed:
            #   test_engine_walker.py::test_a_second_run_on_the_same_repository_does_not_run_while_the_first_holds_it
            #   (see Design Notes: an anchor-test conflict, not a code defect)
make e2e-ui    # not run: no hand-written web-client file changed in this story, and
               # 127.0.0.1:4321 is held by the operator's own dev stack (recorded, not
               # skipped silently — same call 4.6 made)
```

**`tests/e2e/test_run_creation.py::test_get_reads_back_the_created_run`** — the hazard the
operator flagged before this story ran — passed. It was not among the run's failures.
