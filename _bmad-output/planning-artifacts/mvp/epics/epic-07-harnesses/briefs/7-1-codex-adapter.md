---
story: "7-1"
epic: 7
title: Codex adapter and script
requirements: [FR-14 (codex), FR-21, FR-26, NFR-3, AR-14]
binds: [AD-5, AD-10, AD-11]
---

# Story 7.1 — Codex adapter and script

As the Operator,
I want the same story dispatched to Codex CLI exactly as it is to Claude Code, through the same port and the same environment contract,
So that a harness is a choice on one screen, not a second orchestrator.

## Scope

**In:** `infrastructure/harness/codex/adapter.py`, the `codex.sh` script placed and re-verified, registration as `codex`, the contract test for `codex`, `resume_command`, tests with the fake runner and sample JSON event streams.
**Out:** running it for real (7.2).

## Binding rules (inlined)

- **Script (AD-10, `scripts/harness/codex.sh`).** Already placed by Epic 1; re-verify every flag against Codex CLI `CODEX_VERSION` documentation at implementation and record changes in `addendum.md` §B. `HARNESS_ENV_ALIASES=()` — Codex reads the contract names directly (`env_key = "LITELLM_API_KEY"`, `env_http_headers` mapping the five headers to `ORCH_*` names); `CODEX_HOME=$AGENT_HOME/.codex`; `configure` writes `config.toml` with `model_provider = "litellm"`, `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`, `wire_api = "responses"`, the `[otel]` block exporting OTLP traces to Langfuse with `log_user_prompt = false`.
- **`env_for`** for `codex`: the contract + Project vars + `HOME`, `PATH`, `LANG`, `TERM`, `CODEX_HOME`; when `log_prompt_content`: the Codex content switch (`-c otel.log_user_prompt=true` on the command line, since the config file is static `[verify]`).
- **Invocation (provisional, addendum §B).** `codex exec --json -C {worktree} -m {model or default} -o {log_path}.last.md "{prompt}"` `[verify: whether `--skip-git-repo-check` or a sandbox flag is needed under cap_drop ALL]`; `capabilities = {preassign_session: false, resume: true, native_tracing: true}`. The session id is captured from the `thread.started` event in the JSON stream (`thread_id`) `[verify the event and field names]`; absent → `session_id = None` and the readiness line `session id recorded` fails. `resume`: `codex exec resume {session_id} --json "{message}"` `[verify]`. `usage` from the final `turn.completed` usage fields when present. `resume_command(cwd, sid)` → `cd {cwd} && codex resume {sid}`.
- **Never `--full-auto`** (deprecated); approvals are `never` in the config.
- **Skills.** Codex reads `$HOME/.agents/skills` (installed at image build) and `$CWD/.agents/skills`; the worktree's `_bmad/` is the method root.
- **Result.** `HarnessResult{session_id, exit_code, usage, log_path, timed_out, pgid, raw_result}`; the adapter interprets nothing else.

## Acceptance criteria

**Given** the contract test for `codex`
**When** run
**Then** `env_for` keys equal `HARNESS_ENV_CONTRACT` ∪ `{}` ∪ Project vars ∪ `{HOME, PATH, LANG, TERM, CODEX_HOME}`, and no secret beyond `LITELLM_API_KEY` and the Langfuse keys is present.

**Given** the fake runner and a sample `codex exec --json` stream containing a `thread.started` event with an id and a `turn.completed` with usage
**When** `run` is called
**Then** the argv matches the invocation with `-C {worktree}` and the prompt last, `session_id` equals the event's id, `usage` is parsed, and `exit_code`/`log_path` are set; **and** a stream without the event yields `session_id None`.

**Given** `resume`
**When** called
**Then** the argv uses the resume form with the session id and message.

**Given** `resume_command`
**When** called
**Then** it returns `cd {cwd} && codex resume {sid}` and the read model (6.7) wraps it without secrets.

**Given** `log_prompt_content` true
**When** the argv is built
**Then** the content switch is present; false → absent.

## Implementation notes

- Mirror `ClaudeHarness`'s structure; share the JSON-stream parser helpers in `infrastructure/harness/jsonl.py`.
- Sample streams as fixtures under `tests/unit/infrastructure/harness/fixtures/codex/`.
- `main.py` registers `codex` in `HARNESSES`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-14, §8 item 6. Spine AD-10. `scripts/harness/codex.sh` (comments: invocation shape, session capture). `addendum.md` §B (Codex facts). `research/tracing.md` §Codex.
