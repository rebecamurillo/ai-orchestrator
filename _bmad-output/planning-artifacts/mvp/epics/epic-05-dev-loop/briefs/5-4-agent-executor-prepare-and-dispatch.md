---
story: "5-4"
epic: 5
title: Agent executor — prepare and dispatch
requirements: [FR-10 (attempt bounds, timeout), FR-12 (WIP and prepare commits, pgid), FR-14, FR-15, AR-12, AR-13]
binds: [AD-8, AD-9, AD-10, AD-14, AD-17 (start_sha)]
---

# Story 5.4 — Agent executor: prepare and dispatch

As the Operator,
I want every story dispatch to start from a clean, committed tree with the project context written, a prompt that names the skill and nothing else, and every fact of the attempt recorded before and after the harness runs,
So that the agent can never refuse to start on a dirty tree, and nothing the orchestrator wrote is ever attributed to it.

## Scope

**In:** `application/steps/agent.py` first half — `execute` up to and including the harness call and `mark_finished`; `compose_prompt`; `project-context.md`; the WIP and prepare commits; `start_sha`/`end_sha`; the timeout park; the fake harness wiring; tests. The tail (routing, protected paths, spend, budget) is 5.5–5.7 and is called through a single `_tail(ctx, result)` seam that this story leaves as a stub returning `done`.
**Out:** routing (5.5), protected paths (5.6), budget (5.7).

## Binding rules (inlined)

- **Order (AD-9), each step through ports:**
  1. **Orphan control (FR-12):** if `ctx.previous_attempt` has a `pgid` and no `ended_at`, `ProcessRunner.kill_group(pgid)` and wait until `.git/index.lock` is absent (poll 1 s, 30 s max) — then close that attempt as `error · interrupted` through the attempt repository.
  2. **WIP commit:** `Git.status(cwd)` non-empty → `Git.commit(cwd, "wip: story {id} attempt {n} (interrupted)", all=True)`.
  3. **Orchestrator writes:** (a) `project-context.md` at `{spec_folder}/project-context.md` — the Project's `context_text`, then a `## Context files` list of `context_paths` that exist in the worktree (`Workspace.exists`), each missing path logged as `context path missing: {path}` and omitted; regenerated every attempt; (b) the Answer archive (Epic 6) and the `## Verify Failure` append (5.5) when `ctx.resume_signal` / `ctx.previous_attempt` say so — this story provides the hook `_prepare_writes(ctx) -> [paths written]`.
  4. **Prepare commit:** when anything was written → `Git.commit(cwd, "orchestrator: prepare story {id} attempt {n}", paths)`.
  5. **`start_sha = Git.head_sha(cwd)`**; `frozen_test_files` = on the frame's first attempt only, `Git.list_files(start_sha, "")` filtered by `repository.test_globs` (5.6 consumes; compute and store here); `AttemptRepository.mark_started(attempt, start_sha, frozen_test_files, pgid=None)` in its own unit of work **before** the harness starts.
  6. **Prompt:** `compose_prompt(with_resolved, resume_signal, previous_attempt) -> str` — exactly: `Run the skill bmad-build-auto in folder+id dispatch mode: spec folder {spec_folder}, story id {story_id}.` + (`invoke_dev_with` non-empty → ` ` + `prompt_extra` verbatim) + (`with_resolved.spec_checkpoint` and this is a first dispatch or a re-plan → ` Halt after planning.`) + (resume after `answer` → ` Answer from the operator to the blocking condition "{condition}": {answer}`) — nothing else, no greeting, no file list. Retry messages (5.5) use the template's `retry.prompt` verbatim.
  7. **Dispatch:** `tracer.attempt_span(...)` → `env = env_for(attempt, run, project_env, log_content)` with `TRACEPARENT` → `harness.run(cwd, prompt, env, model, session_id=uuid7(), budget_usd_remaining=budget - spend, timeout_min, log_path)`; the adapter's `ProcessRunner.start` returns `pgid`, which the executor records through `AttemptRepository.update(pgid)` immediately (a second tiny unit of work) before awaiting.
  8. **After exit:** `end_sha = Git.head_sha(cwd)`; `mark_finished(attempt, end_sha, exit_code, session_id, usage, log_path)` in its own unit of work; `timed_out` → `StepResult(error, park Park{timeout, "timeout {path} after {n} min"})` and stop; else call `_tail(ctx, harness_result)`.
- **Harness lookup:** `ctx.ports.harnesses[with_resolved.harness]`; an unknown name → `Park{misconfigured, "harness misconfigured: unknown harness {name}"}`.
- **Project env:** `ctx.settings.project_env` (decrypted vars) is passed to `env_for`; the executor never sees the orchestrator's environment.
- **Gate:** the row's gate is `liveness`; the executor never returns green on its own — `done` here only means the routing (5.5) will decide.
- **Unit of work discipline (AD-8):** `mark_started`, the `pgid` update, and `mark_finished` are committed independently so a restart finds them; everything else is applied by `apply_step_result` from the returned `StepResult`.

## Acceptance criteria

**Given** a dirty worktree (fake `Git.status` non-empty) and a previous attempt without `ended_at` and with a `pgid`
**When** the executor runs
**Then** it kills the group, waits for the index lock, closes the previous attempt as `error · interrupted`, commits `wip: story 4-1 attempt 2 (interrupted)`, then proceeds.

**Given** a Project with context text and two context paths, one missing
**When** the executor prepares
**Then** `{spec_folder}/project-context.md` contains the text and only the existing path, the log has `context path missing: …`, and a commit `orchestrator: prepare story 4-1 attempt 1` was made with that file; **and** with no changes to write (an identical file already committed) no prepare commit is made.

**Given** `mark_started` recorded
**When** the fake harness is called
**Then** `start_sha` equals the HEAD after the prepare commit, the fake received the exact prompt `Run the skill bmad-build-auto in folder+id dispatch mode: spec folder specs/notifications, story id 4-1. {invoke_dev_with}` (plus ` Halt after planning.` when `spec_checkpoint`), the env from `env_for` with a `TRACEPARENT`, a fresh UUIDv7 session id, `budget_usd_remaining = budget − spend`, and the row's `timeout_min`.

**Given** the harness returns `timed_out`
**When** the executor finishes
**Then** `mark_finished` was called and the result parks `timeout` with `timeout epics[0].stories[3].build after 90 min`.

**Given** the harness exits normally
**When** finished
**Then** `end_sha`, `exit_code`, `session_id`, `usage`, `log_path` are recorded and `_tail` is invoked with the result.

**Given** `frozen_test_files`
**When** the frame's first attempt starts on a tree with `tests/a.py` and `src/b.py`
**Then** `frozen_test_files == ["tests/a.py"]`; on the frame's second attempt it is not recomputed (stays `None` on that attempt).

## Implementation notes

- `application/steps/agent.py` with small functions: `_orphan_control`, `_wip_commit`, `_prepare_writes`, `_prepare_commit`, `_start`, `compose_prompt`, `_dispatch`, `_finish`, `_tail` (stub). Keep the module ≤ 400 lines across 5.4–5.7 by moving the tail into `application/steps/agent_tail.py` if needed.
- `Git` port gains `head_sha(cwd)` and `commit(cwd, message, paths | all)` if not already present from 4.8.
- Tests: `tests/unit/application/steps/test_agent_prepare.py` on the fakes; `compose_prompt` has its own exhaustive test.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-12 (WIP/prepare, orphan control), FR-14 (prompt content, env), FR-15, FR-10 (timeout). Spine AD-9 (the executor order, `compose_prompt`), AD-8 (`mark_started`/`mark_finished`), AD-17 (`start_sha`, frozen set), AD-14. `addendum.md` §D, §G, §I (prepare commit).
