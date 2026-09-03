---
story: "4-7"
epic: 4
title: Process runner, workspace, and the plan.check, shell, checkpoint kinds
requirements: [FR-8 (stale plan), FR-9 (baseline), FR-10 (timeouts), FR-19 (done checkpoint), NFR-3, AR-12, AR-19]
binds: [AD-7, AD-9, AD-14]
---

# Story 4.7 — Process runner, workspace, and the `plan.check`, `shell`, `checkpoint` kinds

As the Operator,
I want every command a Run executes to run in its own process group with a hard time limit and a log I can read, and the three simplest step kinds to exist,
So that a hung command can never hang a Run, and a stale plan or a declared checkpoint parks the Run exactly as promised.

## Scope

**In:** `domain/ports/process.py` + `infrastructure/process/runner.py`, `domain/ports/workspace.py` + `infrastructure/workspace/fs.py`, fakes for both, `application/steps/{plan_check,shell,checkpoint}.py`, the `StepExecutor` protocol and `StepContext`, registry entries, tests.
**Out:** git kinds (4.8), `agent` (Epic 5).

## Binding rules (inlined)

- **ProcessRunner (AD-14).** `start(cmd: [str] | str, cwd, env, timeout_min, log_path) -> Handle{pid, pgid}` starts the process with `start_new_session=True` (its own session and process group), stdout+stderr appended to `log_path`; `wait(handle) -> Outcome{exit_code, timed_out: bool}` enforces `timeout_min`: on expiry send `SIGTERM` to the group, wait 10 s, `SIGKILL`, return `timed_out=True`; `kill_group(pgid)` same TERM→KILL sequence, idempotent when the group is gone. The runner never inherits the orchestrator's environment: `env` is exactly what the caller passes plus `PATH`, `HOME`, `LANG`, `TERM=dumb`, `GIT_TERMINAL_PROMPT=0`.
- **Logs.** `/work/logs/{run_id}/{seq:03d}-{attempt_n}.log`; the executor sets `attempt.log_path` through the context; the log's last 200 lines are `output_ref` material for the API.
- **Workspace (AD-14).** Rooted at `run.worktree_path`; `read(path)`, `write(path, text)`, `exists`, `glob(pattern)`, `move(src, dst)`, `tree(prefix) -> [entries]`; every path is relative and normalised; `..` or absolute paths raise `WorkspaceError`; unavailable (raises) before a `git.worktree` row has set `worktree_path`.
- **Executor protocol (AD-9).** `StepExecutor.execute(ctx: StepContext) -> StepResult`; `StepContext{run, row, with_resolved, cwd, frame_start_sha, previous_attempt, attempt, resume_signal, ports, settings: StepSettings{project_env: {}, bmad_version, work_dir, github_compare_base}}`. Registry `REGISTRY: dict[str, StepExecutor]` in `application/steps/__init__.py` beside `KIND_META`; `agent` registers a stub executor returning `Park{misconfigured, "agent step not available yet"}` until Epic 5.
- **`plan.check`.** Re-reads every list file recorded in the plan (`run.inputs` and the rows' loop sources; the planner stores the list of `(path, ref)` pairs in `run.plan_files`) at the branch head (`Git.ls_remote` → head SHA of the branch it was read from, then `Git.read_file`) and compares with the content at the recorded ref; identical → `done`; different → `StepResult(error, park Park{plan_stale, "plan stale: {path}"})`; `continue` (`resume_signal`) → `done` without re-reading (the recorded plan proceeds). `[ASSUMPTION: plan_files is a small JSON list on the Run added by the planner story's migration or here]`
- **`shell`.** Command = `with_resolved.command` (already skipped at plan time when empty); runs in `cwd` with `ctx.settings.project_env` (the Project's decrypted vars) via `ProcessRunner` under the row's `timeout_min`; exit 0 → `done` (gate `deterministic`, `output_ref` = log path); timed out → `error`, park `Park{timeout, "timeout {path} after {n} min"}`; non-zero exit: `on_fail` (`with_resolved.on_fail`) `fail` → `StepResult(error, reason "{path} exit {code}")` with no park (the writer turns it into Run `failed`); `continue` → `done` with `reason "exit {code} (continued)"`; `{redispatch}` → `StepResult(error, redispatch=Redispatch{target_seq, max}, reason "exit {code}")` — the `## Verify Failure` append is the agent executor's job on the redispatched attempt (Epic 5), so here the row only carries `output_ref`; `escalate` (default) → `error`, park `Park{verify_failed, "{path} exit {code}"}` `[ASSUMPTION: generic shell failures use the verify_failed park kind]`.
- **`checkpoint`.** First execution → `StepResult(checkpoint, gate human, park Park{checkpoint, "done checkpoint"})` (or `"spec checkpoint"` / `"before"` from `with_resolved.label`); when `resume_signal.kind == continue` the writer already moved the row to `done` (AD-13), so the executor is not called again; when `skip_story` skipped it, likewise.
- **Layering:** executors import `domain` and the ports only; `subprocess`, `os`, `signal`, `shutil` appear only in `infrastructure/process/` and `infrastructure/workspace/`.

## Acceptance criteria

**Given** the real `ProcessRunner`
**When** it starts `sleep 60` with `timeout_min = 1/60` (one second, test-only fractional allowed)
**Then** `wait` returns `timed_out=True` within 12 s, the process group is gone, and the log file exists.

**Given** a started process
**When** `kill_group(pgid)` is called twice
**Then** both calls return without error and no process of that group remains.

**Given** the runner
**When** a command prints its environment
**Then** it contains exactly the caller's variables plus `PATH`, `HOME`, `LANG`, `TERM`, `GIT_TERMINAL_PROMPT`, and never `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL`, or `ORCHESTRATOR_TOKEN`.

**Given** a `shell` row with `on_fail: escalate` and a command exiting 2
**When** executed on the fake runner
**Then** the result is `error` with park `verify_failed` and reason `{path} exit 2`; with `on_fail: fail` → `error` without park; with `on_fail: continue` → `done`; with `{redispatch: build, max: 1}` → `error` with `redispatch.target_seq` of the `build` row.

**Given** a `plan.check` row whose `stories.yaml` at the branch head differs from `plan_ref`
**When** executed
**Then** the result parks `plan_stale` with reason `plan stale: {spec_folder}/stories.yaml`; with `resume_signal continue` → `done`; with identical content → `done`.

**Given** a `checkpoint` row
**When** executed the first time
**Then** the result is `checkpoint` with park `checkpoint` and reason `done checkpoint`.

**Given** the `Workspace` rooted at a temp worktree
**When** `read("../secret")` or `read("/etc/passwd")` is called
**Then** it raises `WorkspaceError`.

## Implementation notes

- `infrastructure/process/runner.py` uses `subprocess.Popen(..., start_new_session=True)`, `os.killpg`; `wait` polls with `Popen.wait(timeout=…)`.
- `tests/unit/fakes/process.py` scripts outcomes per command; `tests/unit/fakes/workspace.py` is an in-memory tree.
- Add `run.plan_files: [{path, ref}]` (migration `0007_plan_files.py`) and have the planner (4.2) fill it — a small follow-up edit in `plan.py` is in scope here.

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-9 (executor protocol, `StepContext`, `StepResult`), AD-14 (ports, timeouts, process groups, logs), AD-7 (`plan.check`), Structural Seed "Shipped kinds". PRD FR-8 (stale plan), FR-10 (timeouts, bounds), FR-9 (baseline `on_fail: fail`), NFR-3.
