---
story: "5-1"
epic: 5
title: Harness port, environment contract, and the Claude adapter
requirements: [FR-14 (claude), FR-21 (resume command), FR-26 (headers), NFR-3, AR-14]
binds: [AD-2, AD-5, AD-10, AD-11, AD-14]
---

# Story 5.1 — Harness port, environment contract, and the Claude adapter

As the Operator,
I want the orchestrator to drive Claude Code headlessly with exactly the environment the scripts declare and nothing of mine beyond it,
So that a story can be dispatched, resumed, and attributed to its Run without a credential ever leaking into an agent process.

## Scope

**In:** `domain/ports/harness.py`, `infrastructure/harness/env.py` (`env_for`), `infrastructure/harness/claude/adapter.py`, a script-parsing unit test, `tests/unit/fakes/harness.py`, registration in `main.py` (harness registry by name), settings for the pins and allowlist (already present).
**Out:** the agent executor (5.4), tracing (5.2), codex and opencode (Epic 7).

## Binding rules (inlined)

- **Port (AD-10).** `Harness{name: str, capabilities: {preassign_session: bool, resume: bool, native_tracing: bool}, run(cwd, prompt, env, model, session_id, budget_usd_remaining, timeout_min, log_path) -> HarnessResult, resume(cwd, session_id, message, env, timeout_min, log_path) -> HarnessResult, resume_command(cwd, session_id) -> str}`; `HarnessResult{session_id, exit_code, usage: {tokens_in, tokens_out, cost_usd} | None, log_path, timed_out: bool, pgid}`. The adapter uses `ProcessRunner` for the process (process group, timeout) and returns nothing interpreted from the model's output beyond `usage` and `session_id`.
- **`env_for(attempt, run, project_env, log_content) -> dict`** (`infrastructure/harness/env.py`, shared by every adapter): exactly `HARNESS_ENV_CONTRACT` — `ORCH_RUN_ID`, `ORCH_ATTEMPT_ID`, `ORCH_STORY_ID`, `ORCH_HARNESS`, `ORCH_PROJECT` (project slug), `ORCH_TAGS` = `run:{run_id},attempt:{attempt_id},story:{story_id},harness:{name},project:{slug}`, `ORCH_LANGFUSE_TAGS` (JSON array of the same), `TRACEPARENT` (from the attempt span, 5.2; empty string until then), `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_ENVIRONMENT`, `ORCH_LOG_CONTENT` (`1`/`0`) — plus the harness's `HARNESS_ENV_ALIASES` plus the Project's decrypted variables (a Project variable never overrides a contract name; 2.1 already refuses those names) plus `HOME=$AGENT_HOME`, `PATH`, `LANG`, `TERM=dumb`. Never `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL`, `ORCHESTRATOR_*`.
- **Claude aliases (from `scripts/harness/claude.sh`).** `ANTHROPIC_AUTH_TOKEN=$LITELLM_API_KEY`; `ANTHROPIC_CUSTOM_HEADERS` = the five header lines `langfuse_session_id: {run_id}`, `langfuse_tags: {json tags}`, `x-litellm-end-user-id: {run_id}`, `x-litellm-session-id: {attempt_id}`, `x-litellm-tags: {tags}` joined by `\n`; when `log_content`: `OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_TOOL_CONTENT=1`. Static settings (`ANTHROPIC_BASE_URL`, OTLP exporter, `DISABLE_AUTOUPDATER`) live in `~/.claude/settings.json` written by `claude.sh configure`; the adapter writes nothing under `AGENT_HOME`.
- **Contract test (AD-10).** A unit test parses the bash arrays `HARNESS_ENV_CONTRACT` in `scripts/harness/_common.sh` and `HARNESS_ENV_ALIASES` in `scripts/harness/claude.sh` and asserts `set(env_for(...).keys()) == contract ∪ alias names ∪ project vars ∪ {HOME, PATH, LANG, TERM}`; the same test shape is reused by Epic 7.
- **Invocation (FR-14, addendum §B; re-verify flags against Claude Code `CLAUDE_CODE_VERSION` docs at implementation and record changes in `addendum.md` §B).** `claude -p --session-id {uuid} --permission-mode dontAsk --allowedTools "{CLAUDE_ALLOWED_TOOLS}" --disallowedTools "mcp__*" --output-format json --max-budget-usd {remaining:.2f} "{prompt}"` in `cwd` (the worktree); never `--bare`; `--model {model}` when a model is given. `session_id` is pre-assigned (`capabilities.preassign_session = true`). `resume`: `claude -p --resume {session_id} --permission-mode dontAsk --allowedTools … --output-format json "{message}"` (`capabilities.resume = true`). `usage` parsed from the JSON result's cost and token fields when present (`total_cost_usd`, `usage.input_tokens`, `usage.output_tokens`) and marked provisional by the caller; a non-JSON output yields `usage = None`. `native_tracing = true`.
- **Budget cap exit.** The adapter reports `exit_code` and `log_path`; whether the exit was the harness's own budget cap is decided by the executor (5.7) from the JSON result field `[the exact field name is recorded in addendum §B after verification]`; the adapter exposes `HarnessResult.raw_result: dict | None` for that.
- **`resume_command(cwd, session_id)`** → `cd {cwd} && claude --resume {session_id}`; the read model (Epic 6) prefixes `docker compose exec backend-api env {contract vars}`.
- **Logs.** stdout and stderr to `log_path` (`/work/logs/{run_id}/{seq:03d}-{n}.log`); the prompt is written to `{log_path}.prompt` for the record `[ASSUMPTION]`.
- **Registry.** `main.py` builds `HARNESSES: dict[str, Harness]` with `claude` now; the executor looks harnesses up by the row's `with_resolved.harness`.
- **Layering:** the adapter imports `ProcessRunner`, settings, `json`; nothing from `application/`.

## Acceptance criteria

**Given** an attempt on a Project with two variables and `log_prompt_content` false
**When** `env_for` is built for `claude`
**Then** its keys are exactly the contract ∪ `{ANTHROPIC_AUTH_TOKEN, ANTHROPIC_CUSTOM_HEADERS}` ∪ the two Project names ∪ `{HOME, PATH, LANG, TERM}`, `ANTHROPIC_AUTH_TOKEN` equals `LITELLM_API_KEY`, `ANTHROPIC_CUSTOM_HEADERS` contains the five header lines with the right ids, and `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `OTEL_LOG_USER_PROMPTS` are absent; with `log_prompt_content` true the two `OTEL_LOG_*` keys are present.

**Given** the script files
**When** the contract test runs
**Then** it passes; editing `_common.sh` to add a name makes it fail.

**Given** the fake `ProcessRunner`
**When** `run(...)` is called with a model and a remaining budget of 12.5
**Then** the command line is exactly the invocation above with `--max-budget-usd 12.50`, `--model`, and the prompt as the last argument, `cwd` is the worktree, and the returned `HarnessResult` carries the pre-assigned `session_id`, the exit code, the log path, and `usage` parsed from a sample JSON output.

**Given** a run whose process exceeds `timeout_min`
**When** awaited
**Then** `HarnessResult.timed_out` is true and the group was killed (fake runner records it).

**Given** `resume(...)`
**When** called
**Then** the command uses `--resume {session_id}` and the message as the prompt.

**Given** `resume_command`
**When** called
**Then** it returns `cd /work/p/r/wt/feat-x && claude --resume {id}`.

## Implementation notes

- `infrastructure/harness/claude/adapter.py::ClaudeHarness(runner, settings)`; `_argv(...)` pure and unit-tested; JSON parsing tolerant (last JSON object in the output).
- `tests/unit/fakes/harness.py::FakeHarness` scripted results per call, records prompts and envs.
- Record any deviation from the documented flags in `_bmad-output/planning-artifacts/mvp/addendum.md` §B under "Claude".

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-14, FR-21, FR-26, NFR-3, §8 Q1. Spine AD-10 (port, `env_for`, allowlist, `--max-budget-usd`), AD-11 (headers), AD-5. `scripts/harness/_common.sh`, `scripts/harness/claude.sh` (comments list the per-attempt env and the invocation shape). `addendum.md` §B.
