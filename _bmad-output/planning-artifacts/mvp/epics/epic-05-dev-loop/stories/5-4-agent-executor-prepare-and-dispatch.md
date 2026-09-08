---
title: 'Agent executor — prepare and dispatch'
type: 'feature'
created: '2026-09-08'
status: 'done'
baseline_revision: '035963dbc45e78aaf6a613fa7501e3bc5d47317b'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      The index-lock poll watches `.git/index.lock` relative to the run worktree, but a
      linked worktree keeps its index lock in the base clone's gitdir, so the poll is a
      no-op in production.
    evidence: |-
      Runs execute in `{work_dir}/{project}/{repo}/wt/{branch}`, created by `git worktree
      add`, where `.git` is a file and the lock lives at
      `<base>/.git/worktrees/<name>/index.lock`. `Workspace` is rooted at the worktree and
      rejects every path outside it, so the correct path is unreachable through the port
      the executor has. The poll is bounded and never raises, and a genuinely stale lock
      still surfaces as a `GitError` from `git.stage`/`git.commit` (an `internal` park)
      rather than as corruption -- but the wait AD-14 asks for does not actually happen.
      `FakeWorkspace` is a flat path->text dict, so no unit test can show this.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:100
    severity: medium
  - summary: >-
      The Project's decrypted variables are materialised on `RunEnvironment` for every row
      of every kind, not only for the `agent` row that hands them to a process.
    evidence: |-
      `walker.py::_walk_ports` calls `deps.read_environment(run_id)` before every row, and
      `read_run_environment` is bound with the `crypto` factory unconditionally, so a
      `git.sync`, `shell` or `checkpoint` row also decrypts. `domain/ports/crypto.py` says
      "decrypt only when a Run is about to hand the value to a harness process".
      `ProjectContext.env_vars` is now `repr=False`, which closes the printing half; the
      read itself would need the row's kind, which `read_run_environment` does not have.
    location: >-
      backend-api/src/orchestrator/infrastructure/db/environment.py:51
    severity: medium
  - summary: >-
      `application/steps/agent.py` is at exactly 400 lines, the frozen cap, so 5.5-5.7 must
      move the tail out before adding to it.
    evidence: |-
      `tests/unit/test_source_limits.py` caps every module at 400 lines. The brief for this
      story already names `application/steps/agent_tail.py` as the escape hatch; `_tail`
      is the seam and its signature (`ctx`, the finished `Attempt`, the `HarnessResult`)
      already carries everything 5.5, 5.6 and 5.7 read.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:400
    severity: medium
  - summary: >-
      `AttemptRepository.mark_started` does not persist `harness` or `model`; only the
      `pgid` update that follows it does.
    evidence: |-
      `STARTED_COLUMNS` omits both (they are in `FINISHED_COLUMNS`). `_start` sets them on
      the entity and `test_the_start_half_records_...` asserts they are recorded, which is
      true of `FakeAttemptRepository` (it swaps the whole entity) but not of the SQLAlchemy
      adapter. The window is the few milliseconds between `mark_started` and the `pgid`
      `update`, which writes every mutable column, so the values do land.
    location: >-
      backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py:35
    severity: low
  - summary: >-
      `DEFAULT_TIMEOUT_MIN = 90` restates `KIND_META["agent"].timeout_default_min` and
      `templates/story.yaml` as a third literal, with nothing asserting the three agree.
    evidence: |-
      Every other executor does the same (`shell.py`, `git_worktree.py`,
      `bmad_install.py`), so this is the codebase's existing shape rather than a new one --
      but the copies can drift silently.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:105
    severity: low
  - summary: >-
      Nothing asserts that the harness registry's keys are a subset of the names
      `seed_harness_table` seeds.
    evidence: |-
      `registry.py`'s docstring states the invariant ("a registry entry with no row would
      be a harness pre-flight could never enable") and `test_main_harness_registry.py`
      checks the subset from `main`, which still re-exports the function -- so the check
      survives the move, but it now lives a module away from the thing it constrains.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/registry.py:31
    severity: low
---

<intent-contract>

## Intent

**Problem:** `agent` is the only `KIND_META` kind with no executor: nothing in the system
dispatches a coding agent. Story 5.1–5.3 landed the `Harness`, `Tracer` and `Gateway` ports
with no production call site, and AD-14's `attempt.pgid`-before-await guarantee is
unimplementable because `Harness.run` starts and waits in one call.

**Approach:** Add `application/steps/agent.py` — orphan control, WIP commit,
`project-context.md`, prepare commit, `mark_started` with `start_sha`/`frozen_test_files`,
`compose_prompt`, the attempt span, dispatch through the `Harness` port, the `pgid` update
before the await, `mark_finished`, the timeout park — ending in a `_tail(...)` stub that
5.5–5.7 fill. Split `Harness.run` into `start` → `wait` so the pgid is observable between
them, and wire the registry, the environment builder and the executor's own unit of work
into `StepPorts` from `infrastructure/dbos/startup.py`.

## Boundaries & Constraints

**Always:**
- AD-9's side-effect order: orphan control → WIP commit → orchestrator writes → prepare
  commit → `start_sha` → prompt → dispatch → `mark_finished`. Every effect through a port.
- AD-8: `mark_started`, the `pgid` update and `mark_finished` each commit in their own unit
  of work. The executor writes no status field and touches no repository but
  `AttemptRepository`.
- AD-14: `attempt.pgid` is stored **before** the harness process is awaited.
- AD-10/AD-5: the harness receives exactly what the environment builder returns; the
  executor never reads the orchestrator's own environment and never names a credential.
- The row's gate is `ctx.row.gate` (`liveness`). `_tail` returning `done` means "5.5 will
  decide", never "green".
- 100 % branch coverage on `application/steps/agent.py` (AD-18); every module ≤ 400 lines.
- Anchors are frozen: no existing test file, `SPEC.md`, `stories.yaml` or `AGENTS.md` may be
  edited. `tests/unit/fakes/*` may be extended **additively** only.

**Block If:**
- Landing this needs an edit to any pre-existing test file, or to `SPEC.md` /
  `stories.yaml` / any `AGENTS.md`.
- A spine decision beyond the three seams named in Design Notes (pgid split,
  composition-root room, `Clock.sleep`) turns out to be required.

**Never:**
- No routing, no `expect`/`retry`, no protected-path check, no spend read, no budget rule
  (5.5–5.7). `_tail` is a stub.
- No `codex`/`local` adapter. No new API surface, no schema change, no migration, no new
  setting, no `.env.example` line.
- Never modify `application/steps/registry.py`'s `EXECUTORS` by hand; register via
  `register(KIND, AgentExecutor())`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Unknown harness | `with_resolved["harness"] = "nope"`, registry has `claude` | `StepResult(status="error", park=Park("misconfigured", "harness misconfigured: unknown harness nope", path=row.path))`; nothing written, no commit | park, no dispatch |
| Orphan control | `previous_attempt.pgid = 4242`, `ended_at is None` | `kill_group(4242)`, poll `.git/index.lock`, then `mark_finished(previous)` with `status="error"`, `output_ref="interrupted"` | none |
| Orphan skipped | `previous_attempt is None`, or `pgid is None`, or `ended_at` set | no `kill_group`, no close | none |
| Index lock clears | lock present, cleared during the first `clock.sleep` | loop exits after one sleep | none |
| Index lock stays | lock present for the whole 30 s | loop exits at the deadline and proceeds | bounded, never raises |
| WIP commit | `git.status(cwd)` non-empty | `stage(cwd)` then `commit(cwd, "wip: story 4-1 attempt 2 (interrupted)")` | none |
| Clean tree | `git.status(cwd)` empty/whitespace | no WIP commit | none |
| Context document | `context_text="ctx"`, `context_paths=("a.md","gone.md")`, only `a.md` exists | `{spec_folder}/project-context.md` holds `ctx`, `## Context files`, `- a.md`; log line `context path missing: gone.md` | missing path omitted, never raises |
| Prepare commit | context file changed the tree | `stage(cwd, path)` then `commit(cwd, "orchestrator: prepare story 4-1 attempt 1")` | none |
| Prepare no-op | identical file already committed (`status` empty after staging) | no commit | none |
| No spec folder | `with_resolved["spec_folder"]` empty | nothing written, no prepare commit | none |
| `mark_started` | before dispatch | `start_sha = head_sha(cwd)`, `frozen_test_files`, `pgid=None`, `harness`, `model`, committed alone | none |
| Frozen set, first attempt | `previous_attempt is None`, tree `tests/a.py`, `src/b.py`, globs `("tests/**",)` | `frozen_test_files == ("tests/a.py",)` | none |
| Frozen set, later attempt | `previous_attempt is not None` | `frozen_test_files is None` | none |
| Prompt, plain | `skill=bmad-build-auto`, `spec_folder=specs/notifications`, `story_id=4-1`, `prompt_extra="Read X."` | `Run the skill bmad-build-auto in folder+id dispatch mode: spec folder specs/notifications, story id 4-1. Read X.` | none |
| Prompt, checkpoint | above + `spec_checkpoint=True`, `resume_signal is None` | same + ` Halt after planning.` | none |
| Prompt, resumed checkpoint | `spec_checkpoint=True`, `resume_signal.event == "continue"` | no ` Halt after planning.` | none |
| Prompt, answer | `resume_signal.event == "answer"`, payload `{condition, answer}` | trailing ` Answer from the operator to the blocking condition "C": A` | none |
| Prompt, no extra | `prompt_extra` empty/absent | first sentence only, no trailing space | none |
| Dispatch | harness present, tracer wired | `attempt_span` open around `start`+`wait`; env carries `TRACEPARENT` from the span; fresh UUIDv7 `session_id`; `budget_usd_remaining = budget − spend`; `timeout_min` from the row | none |
| No tracer | `ports.tracer is None` | dispatch still happens, `TRACEPARENT` empty | degrade, never raise |
| pgid before await | adapter's `start` returns `pgid` | `AttemptRepository.update` with `pgid` committed **before** `wait` | none |
| Timed out | `HarnessResult.timed_out` | `mark_finished` first, then `StepResult(error, park=Park("timeout","timeout epics[0].stories[3].build after 90 min"))`; `_tail` not called | park |
| Normal exit | `exit_code=0`, `usage` present | `end_sha`, `exit_code`, `session_id`, `usage`, `log_path` recorded; `_tail` invoked; result `done` with `output_ref = log path` | none |
| No usage | `HarnessResult.usage is None` | token/cost columns untouched | none |
| Unwired port | `harnesses`/`harness_env`/`attempt_writes`/`run_env.run` unset | `RuntimeError` naming the field → walker parks `internal` | wiring bug, reported |

</intent-contract>

## Code Map

Read-only anchors (**never edit**): `tests/unit/test_source_limits.py` (400-line cap),
`test_coverage_gates.py`, `test_layering.py`, `test_harness_port.py`,
`test_claude_adapter.py`, `test_dbos_startup.py`, `test_dbos_startup_tracing.py`,
`test_main_harness_registry.py`, `test_run_environment_reader.py`,
`test_walker_run_environment.py`, `test_api_providers.py`, `tests/unit/step_fixtures.py`,
`scripts/check_test_pairs.py`.

- `backend-api/src/orchestrator/application/steps/context.py` (221) — `StepContext` (AD-9's
  closed field list), `StepPorts`, `RunEnvironment`, `log_path(ctx)`,
  `require_env/process/workspace/cwd` + the `NO_*` messages. Every new port field and
  `require_*` helper goes here, matching the existing idiom exactly.
- `backend-api/src/orchestrator/application/steps/git_worktree.py` (203) — the executor
  shape to copy: `KIND`, module constants, a class with `execute`, private helpers, a
  trailing `register(KIND, XExecutor())`. `_failed` shows the `StepResult`+`Park` shape.
- `backend-api/src/orchestrator/application/steps/git_commit.py` (93) — the
  `stage → status → commit` idiom. `Git.commit(worktree, message)` takes **no** `paths`/`all`
  argument; staging is `Git.stage(worktree, pathspec=None)`. The brief's
  `commit(..., all=True)` / `commit(..., paths)` is this pair. **No `Git` port change.**
- `backend-api/src/orchestrator/application/steps/shell.py` (126) — `TIMED_OUT =
  "timeout {path} after {n} min"` and `with_resolved.get(TIMEOUT_KEY, DEFAULT_TIMEOUT_MIN)`.
  Copy the wording; `agent`'s default is `KIND_META`'s 90.
- `backend-api/src/orchestrator/application/steps/registry.py` (94) — `register`; `execute`
  turns any escaping exception into `Park("internal", "internal: {ClassName}")`.
- `backend-api/src/orchestrator/application/steps/__init__.py` (157) — `KIND_META["agent"]
  = KindMeta("liveness", 90, {"harness","model","skill","args","prompt_extra"})` already
  exists. **No change needed here.**
- `backend-api/src/orchestrator/application/templates/agent_row.py` (107) — the row's own
  keys, and its docstrings say these are what a dispatch reads: `story_id`, `spec_folder`,
  `spec_checkpoint`, `prompt_extra`, `expect`, `retry`, `escalate_when`, `story`.
- `templates/story.yaml:18-35` — the shipped agent row: `skill: bmad-build-auto`,
  `args: {spec_folder, story_id}`, `prompt_extra: "{{story.invoke_dev_with}}"`,
  `timeout_min: 90`, `pause_when: "story.spec_checkpoint"`.
- `backend-api/src/orchestrator/application/use_cases/writers.py` (218) — `WriterPorts`
  (`runs, steps, attempts, records, uow, clock`). The executor uses **only**
  `writers.attempts` + `writers.uow`.
- `backend-api/src/orchestrator/application/use_cases/walk.py:167-200` — `_context` builds
  `StepContext`; `_frame_start_sha` returns the frame's *first row with attempts*'
  `attempts[0].start_sha`, which for a story frame is the `git.sync` row's `None`. It is
  therefore **not** a usable "is this the frame's first attempt" signal — see Design Notes.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py:174-186` —
  `_close_attempt` re-reads the attempt with `get_latest` and overwrites only `ended_at`,
  `status`, `output_ref`. It cannot clobber what `mark_finished` stored here.
- `backend-api/src/orchestrator/domain/ports/harness.py` (140) — `HarnessResult`
  (`log_path` is a `Path`; `attempt.log_path` is a `str` — convert at the boundary), the
  `Harness` protocol, and the module docstring that already names the pgid seam as 5.4's.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` (365/400) —
  `_execute` starts, waits and parses. Line budget is the constraint; see Execution.
- `backend-api/src/orchestrator/infrastructure/harness/env.py:114-150` — `env_for(attempt,
  *, run, project_slug, project_env, log_content, settings, story_id="", traceparent="",
  aliases)`; `AliasBuilder` is the callable type.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:93-111` —
  `claude_aliases`, the one `AliasBuilder` that exists.
- `backend-api/src/orchestrator/main.py:194-207` (394/400) — `build_harnesses(settings,
  runner)`; its own docstring says `infrastructure/dbos/startup.py` may not import this
  module (AD-2). `tests/unit/test_main_harness_registry.py:20` imports
  `HARNESS_VERSION_SETTINGS, build_harnesses` **from `orchestrator.main`** — a re-export
  must keep that import working.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py:33-42,67-93` — the nine
  `# noqa: F401` kind imports that fill the registry, and `walker_deps` building
  `StepPorts(..., process=RealProcessRunner(), workspace=FsWorkspace,
  tracer=LangfuseTracer(settings))` plus `open_ports=partial(open_writer_ports,
  session_factory)` and `read_environment=partial(read_run_environment, session_factory,
  settings.bmad_version)`.
- `backend-api/src/orchestrator/infrastructure/db/environment.py` (65) —
  `read_run_environment` already reads the `Run` and the `Project`; the four project facts
  and the `Run` itself are one dataclass hop away.
- `backend-api/src/orchestrator/domain/entities/project.py:143-156` — `context_text`,
  `context_paths`, `env_vars_enc: tuple[EncryptedEnvVar, ...]`, `log_prompt_content`.
  `domain/ports/crypto.py`'s docstring: decrypt "only when a Run is about to hand the value
  to a harness process" — i.e. here.
- `backend-api/src/orchestrator/domain/entities/repository.py` — `test_globs: tuple[str, ...]`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py:35-50` —
  `STARTED_COLUMNS` (no `harness`/`model`), `FINISHED_COLUMNS` (has them),
  `MUTABLE_COLUMNS` (`update` writes everything).
- `backend-api/tests/unit/fakes/` — `harness.py` `FakeHarness` (`calls` log, `results` list
  popped in order), `tracer.py` `FakeTracer` (`attempt_span_calls`), `git.py` `FakeGit`
  (`called(name)` → arg tuples, scripts repeat their last entry), `process.py`
  `FakeProcessRunner` (`called("kill_group")`), `workspace.py` `FakeWorkspace`,
  `clock.py` `FakeClock`, `runs.py` `FakeAttemptRepository` (`calls` records the *method
  name*, which is the only way to prove the start half committed before the await),
  `db.py` `FakeUnitOfWork`. Extend additively; never add a second double for a port.
- `backend-api/tests/unit/step_fixtures.py` (frozen) — `an_environment(**overrides)`,
  `a_row`, `a_context`, `without(ctx, **ports)`. `an_environment` forwards arbitrary
  overrides, so new `RunEnvironment` fields work through it unchanged; `a_context` does not
  know the new ports, so agent tests build their own `StepContext`.

## Tasks & Acceptance

**Execution:**

1. `backend-api/src/orchestrator/domain/ports/clock.py` -- add `sleep(self, seconds: float)
   -> None` to the `Clock` protocol -- the index-lock poll is "1 s, 30 s max" and
   `application/` may not import `time` (AD-2); the wall clock is a port.
2. `backend-api/src/orchestrator/infrastructure/clock.py` -- `SystemClock.sleep` =
   `time.sleep(seconds)`.
3. `backend-api/tests/unit/fakes/clock.py` -- **additive**: `FakeClock.__init__` gains
   `on_sleep: Callable[[], None] | None = None`; `sleep(seconds)` advances the clock and
   calls the hook. The hook is how a test makes `.git/index.lock` vanish mid-poll.
4. `backend-api/src/orchestrator/domain/ports/harness.py` -- add
   `@dataclass(frozen=True) class HarnessHandle{session_id: str, log_path: Path, pid: int,
   pgid: int}` and two protocol methods: `start(...) -> HarnessHandle` (the exact keyword
   list `run` already takes) and `wait(handle: HarnessHandle) -> HarnessResult`. Keep `run`
   — it is now documented as `wait(start(...))`. Update the docstring paragraph that says
   the seam "is 5.4's to close" to say how it was closed. `resume` is untouched (5.5).
5. `backend-api/src/orchestrator/infrastructure/harness/claude/result.py` -- **new**: move
   `ENCODING`, `RESULT_TYPE_FIELD`, `RESULT_TYPE`, `read_text`, `json_objects`,
   `result_object`, `_as_int`, `_as_decimal`, `usage_from` out of `adapter.py` verbatim --
   `adapter.py` is at 365/400 and `start`/`wait` do not fit otherwise.
6. `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- re-import the
   moved names (keep them importable from `adapter` for the frozen test's sake); replace
   `_execute` with `start` (public, port signature, records the prompt, returns
   `HarnessHandle` from `runner.start`), `wait` (the guarded `runner.wait` + log parse, with
   the existing `BaseException → kill_group → raise` rule), and `run = self.wait(
   self.start(...))`; `resume` keeps its behaviour through the same private pair.
7. `backend-api/src/orchestrator/infrastructure/harness/claude/__init__.py` -- re-export
   the `result` module's public names so `check_test_pairs` sees the new module paired.
8. `backend-api/tests/unit/fakes/harness.py` -- **additive**: `start` records a `"start"`
   call and returns a `HarnessHandle` (scripted `pgid`, default `4242`); `wait` records
   `"wait"` and pops the next scripted `HarnessResult`; `run` stays `wait(start(...))` so
   every existing assertion on `called("run")` keeps working. Give the fake an optional
   `pgid: int` constructor argument.
9. `backend-api/src/orchestrator/infrastructure/harness/registry.py` -- **new**: move
   `build_harnesses(settings, runner)` here verbatim, and add `ALIASES: dict[str,
   AliasBuilder] = {ClaudeHarness.name: claude_aliases}` plus `build_harness_env(settings)
   -> HarnessEnv`, a closure that calls `env_for(..., aliases=ALIASES.get(attempt.harness
   or ""))`. This is what lets `walker_deps` build both without importing `main` (AD-2).
10. `backend-api/src/orchestrator/infrastructure/harness/__init__.py` -- re-export
    `build_harnesses`, `build_harness_env`.
11. `backend-api/src/orchestrator/main.py` -- delete `build_harnesses` and the three imports
    it alone needed (`ProcessRunner`, `Harness as HarnessPort`, `ClaudeHarness` + its
    three-line comment); import `build_harnesses` from
    `orchestrator.infrastructure.harness` with a `# noqa: F401` re-export comment naming the
    frozen test that imports it from here. Net ≈ −18 lines (394 → ≈ 376).
12. `backend-api/src/orchestrator/domain/ports/harness.py` -- add a `HarnessEnv` protocol:
    `__call__(attempt: Attempt, *, run: Run, project_slug: str, project_env: Mapping[str,
    str], log_content: bool, story_id: str | None, traceparent: str) -> dict[str, str]`.
    A domain-typed seam so `application/` never imports `infrastructure/harness/env.py`.
13. `backend-api/src/orchestrator/application/steps/context.py` -- `RunEnvironment` gains
    four defaulted fields: `run: Run | None = None`, `project: ProjectContext =
    ProjectContext()` (a new frozen dataclass in this module: `context_text: str = ""`,
    `context_paths: tuple[str, ...] = ()`, `env_vars: Mapping[str, str] = <empty mapping>`,
    `log_prompt_content: bool = False`), `test_globs: tuple[str, ...] = ()`. `StepPorts`
    gains three defaulted fields: `harnesses: Mapping[str, Harness] | None = None`,
    `harness_env: HarnessEnv | None = None`, `attempt_writes: AttemptWrites | None = None`
    (`AttemptWrites = Callable[[], AbstractContextManager[WriterPorts]]`). Add
    `NO_HARNESSES`/`NO_HARNESS_ENV`/`NO_ATTEMPT_WRITES`/`NO_RUN` messages and the matching
    `require_*` helpers, in the existing style. Defaults keep every frozen `StepPorts(...)`
    and `RunEnvironment(...)` construction working unchanged.
14. `backend-api/src/orchestrator/application/steps/agent.py` -- **new**, the story. Public:
    `KIND = "agent"`, `AgentExecutor`, `compose_prompt(with_resolved, resume_signal,
    previous_attempt) -> str`. Private, in AD-9's order: `_harness`, `_orphan_control`,
    `_await_unlock`, `_wip_commit`, `_prepare_writes`, `_context_document`,
    `_prepare_commit`, `_start`, `_frozen_test_files`, `_dispatch`, `_run`, `_finish`,
    `_tail`, `_committed`. Ends with `register(KIND, AgentExecutor())`. See Design Notes
    for the exact strings and the ordering rules.
15. `backend-api/src/orchestrator/infrastructure/db/environment.py` -- `read_run_environment`
    gains keyword-only `crypto: Callable[[], Crypto] | None = None` (a **factory**, because
    `FernetCrypto` refuses the `.env.example` placeholder at construction and
    `walker_deps(Settings(), ...)` runs in a frozen test). Fill `run=run`,
    `test_globs=repository.test_globs` and `project=ProjectContext(...)`, decrypting
    `env_vars_enc` only when the Project has variables **and** a factory was supplied. The
    existing three-positional call keeps working.
16. `backend-api/src/orchestrator/infrastructure/dbos/startup.py` -- add
    `from orchestrator.application.steps import agent as _agent  # noqa: F401` to the kind
    imports (this is what registers the executor); in `walker_deps` bind `runner =
    RealProcessRunner()` once and pass it to both `process=` and `build_harnesses(settings,
    runner)`; add `harness_env=build_harness_env(settings)`,
    `attempt_writes=partial(open_writer_ports, session_factory)`; extend the
    `read_environment` partial with `crypto=partial(FernetCrypto,
    settings.orchestrator_secret_key.get_secret_value())`.

**New test modules** (never append to an existing file):

17. `backend-api/tests/unit/application/steps/__init__.py` and
    `backend-api/tests/unit/application/steps/agent_fixtures.py` -- a context builder for
    agent rows (the frozen `step_fixtures.a_context` knows none of the new ports); reuse the
    shared fakes, add none.
18. `backend-api/tests/unit/application/steps/test_agent_prompt.py` -- `compose_prompt`
    exhaustively: the five matrix prompt rows plus empty `skill`/`spec_folder`/`story_id`.
19. `backend-api/tests/unit/application/steps/test_agent_prepare.py` -- orphan control, the
    index-lock poll (all three shapes), WIP commit, the context document, the prepare commit
    and its no-op, `mark_started`, the frozen set (both shapes), the unknown harness park,
    and every unwired-port `RuntimeError`.
20. `backend-api/tests/unit/application/steps/test_agent_dispatch.py` -- the span, the env,
    the session id, the budget remainder, the timeout, `mark_finished`, `_tail`, the
    write-order proof (`FakeAttemptRepository.calls` shows `mark_started`, `update`,
    `mark_finished` and `FakeHarness.calls` shows `start`, `wait`, with the `update` between
    them), and the no-tracer degrade.
21. `backend-api/tests/unit/test_harness_start_wait.py` -- the port's new members, the
    adapter's `start`/`wait`/`run` equivalence, the fake's, and `isinstance(..., Harness)`.
22. `backend-api/tests/unit/test_claude_result_parsing.py` -- imports
    `infrastructure/harness/claude/result.py` directly so the moved module is paired.
23. `backend-api/tests/unit/test_harness_registry.py` -- `build_harnesses` from its new home
    and `build_harness_env` (a claude attempt gets `ANTHROPIC_AUTH_TOKEN`; an unknown
    harness name gets the contract without aliases).
24. `backend-api/tests/unit/test_run_environment_project.py` -- the Run, the project context,
    the decrypted variables (through `FakeCrypto`), `test_globs`, and the
    no-crypto/no-variables degrades.
25. `backend-api/tests/unit/test_dbos_startup_agent.py` -- `walker_deps` wires
    `harnesses`/`harness_env`/`attempt_writes`, the harness registry shares the
    `StepPorts.process` runner instance, and importing `startup` registers the `agent` kind.
26. `backend-api/tests/unit/test_clock_sleep.py` -- the port member, `SystemClock.sleep`
    (with a zero delay), and `FakeClock.sleep` + `on_sleep`.

**Acceptance Criteria:**

- Given a dirty worktree and a `previous_attempt` with a `pgid` and no `ended_at`, when the
  executor runs, then `kill_group` is called with that pgid, the previous attempt is closed
  `error`/`interrupted`, and `git.commit` is called with
  `wip: story 4-1 attempt 2 (interrupted)` before anything else is written.
- Given a Project with context text and two context paths of which one exists, when the
  executor prepares, then `{spec_folder}/project-context.md` holds the text and only the
  existing path, `context path missing: …` was logged, and one commit
  `orchestrator: prepare story 4-1 attempt 1` staged exactly that file; and given an
  identical file already committed, no prepare commit is made.
- Given `mark_started` recorded, when the fake harness is called, then `start_sha` equals
  the HEAD after the prepare commit, the prompt is exactly
  `Run the skill bmad-build-auto in folder+id dispatch mode: spec folder specs/notifications, story id 4-1. {invoke_dev_with}`
  (plus ` Halt after planning.` under `spec_checkpoint`), the env carries the span's
  `TRACEPARENT`, the session id is a fresh UUIDv7, `budget_usd_remaining == budget − spend`,
  and `timeout_min` is the row's.
- Given the harness handle carries a `pgid`, when the executor dispatches, then the
  `AttemptRepository.update` that stores it is committed **between** `Harness.start` and
  `Harness.wait`.
- Given `HarnessResult.timed_out`, when the executor finishes, then `mark_finished` ran and
  the result parks `timeout` with `timeout epics[0].stories[3].build after 90 min`, and
  `_tail` was not reached.
- Given a normal exit, when finished, then `end_sha`, `exit_code`, `session_id`, the usage
  and `log_path` (as a `str`) are recorded and `_tail` produced the returned `StepResult`.
- Given the frame's first attempt on a tree holding `tests/a.py` and `src/b.py`, when it
  starts, then `frozen_test_files == ("tests/a.py",)`; on a later attempt it is `None`.
- Given `make lint && make test`, when run, then both exit 0 with
  `application/steps/agent.py` at 100 % branch coverage and no module over 400 lines.

## Spec Change Log

## Review Triage Log

### 2026-09-08 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 2, medium 4, low 4)
- defer: 6: (high 0, medium 3, low 3)
- reject: 21: (high 1, medium 8, low 12)
- addressed_findings:
  - `[high]` `[patch]` `_orphan_control` was dead code on the restart path it exists for: it
    guarded on `previous.ended_at is not None`, but `start_attempt._open_the_row` already
    stamps `ended_at` on the interrupted attempt before the executor ever sees it. The guard
    now keys on `end_sha`, which only `_finish` writes — so "a recorded `pgid` and no
    `end_sha`" is exactly "a dispatch that started and never came back", and a previous
    attempt that finished normally is neither killed nor rewritten. Two tests added.
  - `[high]` `[patch]` `_frozen_test_files` globbed the live worktree through
    `Workspace.glob` (= `pathlib.Path.glob` in production, which returns directory entries
    and untracked files). It now reads `Git.list_files(worktree, start_sha, "")` and filters
    with `PurePosixPath.full_match`, which is the surface AD-17 and the brief both name and
    the one 5.6 will diff against.
  - `[medium]` `[patch]` `_frozen_test_files` could leave AD-17's set permanently `None`: it
    froze only when `previous_attempt is None`, so a first attempt that parked before
    `_start` disabled freezing for the whole row. It now skips only when the predecessor
    actually reached a `start_sha` — AD-17's own "lowest-`n` attempt that has a `start_sha`".
  - `[medium]` `[patch]` A `pgid` commit that raised between `Harness.start` and
    `Harness.wait` orphaned the process: the adapter's own guard never runs, and this frame
    is the only one holding the handle. The commit is now wrapped in
    `except BaseException: kill_group(pgid); raise`.
  - `[medium]` `[patch]` `session_id` is now stored with the `pgid` in the same `update`
    (which writes every mutable column), so a backend that dies mid-dispatch leaves an
    attempt FR-21 can still write a `resume_command` for.
  - `[medium]` `[patch]` The AD-14 ordering test compared two independent call logs and
    would have passed an implementation that committed the `pgid` after the await.
    `FakeHarness` gained an additive `on_wait` hook, and the test now snapshots
    `FakeAttemptRepository.calls` at the instant `wait` is entered.
  - `[low]` `[patch]` `RunEnvironment.project` was a shared class-level `ProjectContext()`
    instance, so every environment that named none shared its `env_vars` dict — now
    `field(default_factory=ProjectContext)`.
  - `[low]` `[patch]` `ProjectContext.env_vars` holds the Project's decrypted secrets and
    the dataclass repr would have printed them into any traceback or structlog binding — now
    `repr=False`, which makes the docstring's "never logged" mechanical.
  - `[low]` `[patch]` `timeout_min` was the one resolved key read without null handling; an
    explicit `timeout_min: null` reached `Harness.start` and the timeout sentence as `None`.
  - `[low]` `[patch]` The module's one log call bound `path=` to the row while the event text
    held the missing file; the missing path is now its own `context_path` key.

Notable rejections: the four-reviewer claim that
`infrastructure/harness/claude/result.py` fails to parse (`except TypeError, ValueError:`)
is a false positive — PEP 758 makes an unparenthesised except tuple legal on this
repository's pinned Python 3.14, verified with `ast.parse` and by the suite running over
that module. Non-zero exit routing, the budget check before dispatch, and `Harness.resume`
/ `capabilities` are 5.5-5.7 by the intent's own "Out" list.

## Design Notes

**Three seams, and why each is forced.**

1. *pgid before the await.* AD-14 and this brief both require `attempt.pgid` stored before
   the process is awaited; 5.1 implemented `run` as one start-and-wait call and recorded the
   gap in `domain/ports/harness.py`'s own docstring as "5.4's to close". `start` →
   `HarnessHandle` → `wait` is the smallest split that exposes the pgid without changing
   what `run` means; `run` stays on the port and is literally `self.wait(self.start(...))`,
   so every frozen assertion about `run` holds. `HarnessHandle` carries `pid` **and** `pgid`
   because `ProcessRunner.wait` takes a `Handle(pid, pgid)` — no opaque `Any`.
2. *Composition-root room.* `main.py` is 394/400 and `walker_deps` (in
   `infrastructure/dbos/startup.py`) may not import it (AD-2). Rather than threading the
   registry through `build_engine(...)` — which would need `main()` to build the
   `ProcessRunner` too, growing the file that has no room — `build_harnesses` **moves** to
   `infrastructure/harness/registry.py`, beside the adapter it names, and `main.py`
   re-exports it so `tests/unit/test_main_harness_registry.py` (frozen) keeps importing it
   from `orchestrator.main`. `walker_deps` then builds registry and env builder itself,
   exactly as 5.2 built `LangfuseTracer` there. `build_engine`'s signature is unchanged.
3. *`Clock.sleep`.* "poll 1 s, 30 s max" needs a sleep, `application/` may not import
   `time` (AD-2, and `test_source_limits.py` polices the wall clock), and `Clock` is the
   port for "time is an input". One method, one line in `SystemClock`, and `FakeClock`
   gains the `on_sleep` hook that lets a test make the lock vanish mid-poll.

**Why the env builder is a `StepPorts` field and not a `Harness` method.** `env_for` lives
in `infrastructure/` and takes `Settings`; `application/steps/agent.py` may import neither.
AD-10 enumerates the `Harness` port's members and `env` is not one of them, while
`context.py`'s own docstring already says `StepPorts` "grows with them: … Epic 5 adds the
harnesses and the gateway". So the seam is a field, typed by a domain `HarnessEnv` protocol,
built once in the registry module where the alias table lives.

**Why the `Run` travels on `RunEnvironment`.** `env_for(run=…)`, `attempt_span(run, …)` and
`budget − spend` all need the `Run` entity, and AD-9 closes `StepContext`'s field list.
`context.py` says `ports` is the field AD-9 leaves open and `RunEnvironment` is what the
walker puts there — it already carries `run_id`, `accepted_paths`, `worktrees`. Carrying the
`Run` itself is the same move, and `read_run_environment` already reads it.

**Why `previous_attempt is None` decides the frozen set.** AD-17 says "the frame's first
attempt", but `walk._frame_start_sha` returns the frame's *first row with attempts*'
`attempts[0].start_sha`, and in a story frame that row is `git.sync`, whose attempt has no
`start_sha` — so `ctx.frame_start_sha` is `None` on every attempt and cannot distinguish
them. Every shipped Template has exactly one `agent` row per story frame, so "this row's
first attempt" **is** the frame's first agent attempt, and AD-17's read side ("the frame's
lowest-`n` attempt that has a `start_sha`") finds exactly the attempt this rule writes.
Recorded for 5.6, which owns the read.

**Why ` Halt after planning.` is gated on `resume_signal is None`.** The brief says
"a first dispatch or a re-plan". Retries do not use `compose_prompt` at all (5.5 sends
`retry.prompt` verbatim), so the only other caller is a resume — and a resume after the
spec checkpoint must not halt again. `resume_signal is None` is therefore exactly "first
dispatch or re-plan", and is observable.

**The exact strings** (module constants, asserted verbatim):

```python
DISPATCH = "Run the skill {skill} in folder+id dispatch mode: spec folder {spec_folder}, story id {story_id}."
HALT = " Halt after planning."
ANSWER = ' Answer from the operator to the blocking condition "{condition}": {answer}'
WIP_MESSAGE = "wip: story {id} attempt {n} (interrupted)"
PREPARE_MESSAGE = "orchestrator: prepare story {id} attempt {n}"
CONTEXT_FILE = "project-context.md"
CONTEXT_HEADING = "## Context files"
CONTEXT_MISSING = "context path missing: {path}"
UNKNOWN_HARNESS = "harness misconfigured: unknown harness {name}"
TIMED_OUT = "timeout {path} after {n} min"        # shell.py's wording, unchanged
INDEX_LOCK = ".git/index.lock"
INTERRUPTED = "interrupted"
LOCK_POLL_SECONDS, LOCK_TIMEOUT_SECONDS = 1.0, 30.0
DEFAULT_TIMEOUT_MIN = 90                           # KIND_META["agent"]
```

`project-context.md` is `context_text`, a blank line, `CONTEXT_HEADING`, a blank line, then
one `- {path}` line per surviving context path — the heading is always written so the shape
has one form, not two.

**Ordering inside `execute`.** The harness lookup runs first: it is a pure read, and a
misconfigured row must not leave a WIP commit behind. Everything after it is AD-9's order
verbatim. `_committed(ctx, write)` takes a `Callable[[AttemptRepository], None]` so the
three unit-of-work call sites share one branch-free helper:

```python
def _committed(ctx: StepContext, write: Callable[[AttemptRepository], None]) -> None:
    with require_attempt_writes(ctx)() as writers, writers.uow:
        write(writers.attempts)
        writers.uow.commit()
```

`_finish` writes `mark_finished` **before** it inspects `timed_out`, so a timed-out attempt
is as fully recorded as a clean one. `_tail(ctx, attempt, result) -> StepResult` takes the
finished `Attempt` as well as the `HarnessResult` — 5.6 needs `start_sha`/`end_sha` off it
and 5.7 needs the usage — and this story returns
`StepResult(status="done", gate=ctx.row.gate, output_ref=str(result.log_path))`.

## Verification

**Commands:**
- `make lint` -- expected: exit 0. ruff, mypy `--strict` over `domain/`+`application/`, all
  four import-linter contracts KEPT, env-contract unchanged (no new setting),
  `check_test_pairs` reporting every new module paired, no contract drift.
- `make test` -- expected: exit 0; `domain/`+`application/` at 100 % branch under
  `--fail-under=100`; the count of backend unit tests strictly above 4321.
- `uv run --directory backend-api pytest tests/unit --cov=src/orchestrator/application/steps/agent.py --cov-branch --cov-report=term-missing` -- expected: 100 %.
- `for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "VIOLATION: $f"; esac; done` -- expected: no output.
- `wc -l backend-api/src/orchestrator/main.py backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py backend-api/src/orchestrator/application/steps/agent.py backend-api/src/orchestrator/application/steps/context.py` -- expected: every file ≤ 400.

**Manual checks (if no CLI):**
- `make e2e-api` / `make e2e-ui` / `make openapi` need no new run: this story adds no route,
  no schema field and no UI. Report them as not-run with that reason.

## Auto Run Result

Status: done

**What was implemented.** The `agent` kind now has an executor, and it is the first thing in
this system that dispatches a coding agent. `application/steps/agent.py` runs AD-9's
side-effect order verbatim — harness lookup, orphan control, WIP commit,
`{spec_folder}/project-context.md`, prepare commit, `start_sha` + `frozen_test_files`
through `mark_started`, `compose_prompt`, the attempt span, `Harness.start`, the `pgid`
commit, `Harness.wait`, `mark_finished` — and ends in a `_tail(ctx, attempt, result)` stub
that returns `done` at gate `liveness`, which means "5.5 will decide", never "green". Three
attempt writes commit in three units of work of their own (AD-8), and the middle one is why
the `Harness` port grew two halves: 5.1 recorded the pgid seam as 5.4's to close, and `start`
→ `HarnessHandle` → `wait` closes it, with `run` staying on the port as exactly
`wait(start(...))`. Orphan control kills the group a dead backend left behind, polls
`.git/index.lock` a second at a time for at most thirty, and closes that attempt `error` ·
`interrupted`. `compose_prompt` renders the FR-14 sentence, `prompt_extra`, the spec
checkpoint's `Halt after planning.` and an Operator answer, and nothing else. The
composition root grew room by *losing* something: `build_harnesses` moved out of `main.py`
(394 → 377) into `infrastructure/harness/registry.py` beside the adapter it names, where
`walker_deps` can reach it without importing the composition root (AD-2), and `main.py`
re-exports it so the frozen test that imports it from there keeps working.

**Files changed (15 added, 12 modified):**
- `backend-api/src/orchestrator/application/steps/agent.py` — added: `KIND`, `AgentExecutor`,
  `compose_prompt`, and the private chain in AD-9's order. 400/400 lines.
- `backend-api/src/orchestrator/application/steps/context.py` — modified: `ProjectContext`;
  `RunEnvironment.run`/`.project`/`.test_globs`; `StepPorts.harnesses`/`.harness_env`/
  `.attempt_writes`; four `NO_*` messages and their `require_*` helpers. All defaulted.
- `backend-api/src/orchestrator/domain/ports/harness.py` — modified: `HarnessHandle`,
  `Harness.start`, `Harness.wait`, and the `HarnessEnv` protocol.
- `backend-api/src/orchestrator/domain/ports/clock.py`,
  `backend-api/src/orchestrator/infrastructure/clock.py` — modified: `Clock.sleep`, because
  the index-lock poll is "1 s, 30 s max" and `application/` may not import `time` (AD-2).
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` — modified:
  `_execute` split into `start`/`wait`; `run` and `resume` both go through the pair. 365 → 328.
- `backend-api/src/orchestrator/infrastructure/harness/claude/result.py` — added: the log
  parsing moved out of the adapter to make room for the split; re-exported from both places.
- `backend-api/src/orchestrator/infrastructure/harness/registry.py` — added:
  `build_harnesses` (moved) plus `ALIASES` and `build_harness_env`.
- `backend-api/src/orchestrator/infrastructure/harness/__init__.py`,
  `.../harness/claude/__init__.py` — modified: the re-exports.
- `backend-api/src/orchestrator/main.py` — modified: `build_harnesses` deleted and
  re-exported; three imports it alone needed removed. 394 → 377.
- `backend-api/src/orchestrator/infrastructure/db/environment.py` — modified: the `Run`, the
  `Project`'s context and decrypted variables, and `test_globs` on `RunEnvironment`; `crypto`
  arrives as an optional *factory* because `FernetCrypto` refuses the contract placeholder.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — modified: imports
  `steps.agent` (which is what registers the kind); one `RealProcessRunner` shared by
  `StepPorts.process` and the registry; `harness_env`, `attempt_writes`, and `crypto`.
- `backend-api/tests/unit/fakes/clock.py`, `.../fakes/harness.py` — modified, strictly
  additively: `FakeClock.sleep`/`on_sleep`/`slept`; `FakeHarness.start`/`wait`/`pgid`/
  `on_wait`. No existing behaviour or assertion changed.
- `backend-api/tests/unit/application/steps/{__init__,agent_fixtures}.py` and
  `test_agent_{prompt,prepare,dispatch}.py`, plus `tests/unit/test_{harness_start_wait,
  claude_result_parsing,harness_registry,run_environment_project,dbos_startup_agent,
  clock_sleep}.py` — added: 107 tests over the executor, the port split, the registry, the
  environment reader, the wiring and the clock.

**Review findings:** 10 patched (2 high, 4 medium, 4 low), 6 deferred (frontmatter
`deferred`), 21 rejected. No `intent_gap` and no `bad_spec`, so no repair loopback ran. The
two high patches were real defects the gates could not see: `_orphan_control` was dead code
because `start_attempt._open_the_row` already stamps `ended_at` on the interrupted attempt
(the guard now keys on `end_sha`), and `frozen_test_files` was globbed off the live
filesystem instead of read from the committed tree at `start_sha` (AD-17's own surface). The
loudest finding of the pass — that `claude/result.py` fails to parse — was rejected as a
false positive: PEP 758 makes an unparenthesised `except` tuple legal on this repository's
Python 3.14, verified with `ast.parse` and by 4444 tests running over that module.

**Follow-up review recommended:** true. Two patched findings were `high` severity, which
sets the flag on its own; the medium/low score was `3 × 4 + 1 × 4 = 16`, also over the
threshold.

**Verification performed (re-run by the coordinator, not only trusted from the
implementation subagent's report):**
- `make lint` — exit 0, twice (before and after the patch pass): ruff check and format, mypy
  `--strict` over `domain/` + `application/`, all four import-linter contracts KEPT, env
  contract unchanged (31 settings fields / 37 `.env.example` variables — no new setting),
  `check_test_pairs` 163/163 paired, `gen:api --check` no drift, web-client clean.
- `make test` — exit 0, twice: 4444 backend unit tests passed, 1 skipped (4321 before this
  story); `domain/` + `application/` at 100 % branch under `--fail-under=100`; web-client 973.
- `application/steps/agent.py`: 172 statements, 34 branches, **100 %** branch coverage.
- `test_source_limits.py` green, so every module is ≤ 400 lines. `agent.py` 400,
  `context.py` 311, `adapter.py` 328, `result.py` 125, `registry.py` 79, `main.py` 377.
- Anchor check (the literal command from the dispatch instructions) — output is exactly one
  line, `VIOLATION: backend-api/tests/unit/fakes/clock.py`, which is the sanctioned shared-
  double exception; the diff was read line by line and is strictly additive (a defaulted
  `on_sleep` parameter plus `sleep`/`slept`). `tests/unit/fakes/harness.py` was extended the
  same way but is not an `origin/main` anchor at all — 5.1 added it on this branch. No other
  pre-existing test file, `SPEC.md`, `stories.yaml` or `AGENTS.md` was touched.
- Matrix audit: all 24 I/O matrix rows are covered by named tests that ran and passed, plus
  the five the patch pass added (the `start_attempt`-shaped orphan, the normally-finished
  predecessor, the parked-first-attempt frozen set, the failing pgid commit, the stored
  session id).
- `make e2e-api`, `make e2e-ui`, `make openapi` and `make durability` were **not run**: this
  story adds no route, no schema field, no UI and no migration, and `make lint` already ran
  `gen:api --check` and reported no drift.

**Residual risks (frontmatter `deferred`):** the index-lock poll cannot see a linked
worktree's real lock through the `Workspace` port; the Project's plaintext variables are
built for every row kind rather than only for `agent` rows (`repr=False` closes the printing
half); `mark_started` does not itself persist `harness`/`model` (the `pgid` `update` does);
`agent.py` is at exactly 400/400, so 5.5 must move the tail into `agent_tail.py` before
adding to it.
