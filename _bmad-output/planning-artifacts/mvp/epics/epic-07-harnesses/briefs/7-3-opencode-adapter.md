---
story: "7-3"
epic: 7
title: OpenCode adapter and script for local models
requirements: [FR-14 (local), FR-27 (local), FR-28 (cost 0), NFR-3, AR-14, AR-16]
binds: [AD-5, AD-10, AD-11]
---

# Story 7.3 — OpenCode adapter and script for local models

As the Operator,
I want stories dispatched to an open-weight model served on the Mac mini through OpenCode, with its calls found under the Run in Langfuse and its tokens recorded at zero cost,
So that a local model is a cost lever I can measure, not a guess.

## Scope

**In:** `infrastructure/harness/opencode/adapter.py` registered as `local`, `opencode.sh` re-verified, `env_for` aliases (`LANGFUSE_BASEURL`, `LANGFUSE_USER_ID`), the contract test, `attempt_observed` for `local` by user id, `LOCAL_MODELS` exposure in New workflow's model field, cost `0` with tokens, tests.
**Out:** host model serving and the real run (7.4).

## Binding rules (inlined)

- **Script (`scripts/harness/opencode.sh`).** `HARNESS_ENV_ALIASES=(LANGFUSE_BASEURL=LANGFUSE_BASE_URL LANGFUSE_USER_ID=ORCH_RUN_ID)`; `configure` writes `~/.config/opencode/opencode.json` with the Langfuse plugin at `LANGFUSE_OPENCODE_PLUGIN_VERSION`, provider `litellm` (`@ai-sdk/openai-compatible`, `baseURL`, `apiKey: {env:LITELLM_API_KEY}`, the five headers by `{env:…}` name), one model entry per `LOCAL_MODELS` alias, `permission: {edit: allow, bash: allow, webfetch: deny}`. Re-verify against OpenCode `OPENCODE_VERSION` docs; record changes in `addendum.md` §B.
- **`env_for`** for `local`: contract + the two aliases + Project vars + `HOME`, `PATH`, `LANG`, `TERM`; content logging: the plugin's switch if it has one `[verify; else record "no content switch"]`.
- **Invocation (provisional).** `opencode run --format json --dir {worktree} -m litellm/{model} "{prompt}"` with `model` defaulting to the first `LOCAL_MODELS` alias; `capabilities = {preassign_session: false, resume: false, native_tracing: false}`; session id from the JSON events, fallback: the newest session in `~/.local/share/opencode/opencode.db` whose `directory` equals the worktree `[verify]`; `usage` from the events when present. `resume` unsupported → retries use a new session with the prompt prepended (5.5). `resume_command` → `None` (the read model hides the block, 6.7).
- **Tracing (AD-11).** No inbound `TRACEPARENT`; the plugin sends generations with `userId = run_id` and session `run_id`; `Tracer.attempt_observed(run_id, attempt_id)` for `local` returns true when at least one observation with `userId == run_id` was created between the attempt's `started_at` and `ended_at` `[ASSUMPTION: time-window attribution, since the plugin carries no attempt id]`.
- **Cost (PRD §11).** The Gateway's spend rows for local models carry `spend 0`; `record_attempt_spend` keeps tokens and cost `0`, not provisional when rows exist.
- **New workflow.** The model field, when `local` is selected, becomes a select over `LOCAL_MODELS` (`GET /harnesses` returns `models: [...]` per harness; empty for others).

## Acceptance criteria

**Given** the contract test for `opencode`
**When** run
**Then** `env_for` keys equal the contract ∪ `{LANGFUSE_BASEURL, LANGFUSE_USER_ID}` ∪ Project vars ∪ `{HOME, PATH, LANG, TERM}`, with `LANGFUSE_USER_ID == run_id`.

**Given** the fake runner and a sample JSON event stream with a session id and usage
**When** `run` is called
**Then** the argv matches the invocation with `-m litellm/local-coder` by default, the session id and usage are parsed, and `resume_command` is `None`.

**Given** a stream without a session id and a fake session store containing a session for the worktree
**When** `run` finishes
**Then** the session id comes from the store.

**Given** `attempt_observed` for `local` on a fake Langfuse client returning one observation with `userId == run_id` inside the attempt window
**When** called
**Then** it returns true; outside the window or with another user id → false.

**Given** Gateway rows with `spend 0` and tokens
**When** `record_attempt_spend` runs
**Then** `cost_usd == 0`, tokens set, `cost_provisional false`.

**Given** `GET /harnesses`
**When** read
**Then** `local.models` lists the `LOCAL_MODELS` aliases and the New workflow model field becomes a select for `local`.

## Implementation notes

- Adapter under `infrastructure/harness/opencode/`; register as `local` in `HARNESSES` (the harness table row is `local`).
- Extend `LangfuseTracer.attempt_observed` with the `local` branch; `Harness.name` vs table name mapping in one place.
- Sample streams under `tests/unit/infrastructure/harness/fixtures/opencode/`.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-14, FR-27 (`local`), §8 item 7, §11 Cost. Spine AD-10, AD-11 (`local` by user id), Deferred (OpenCode trace parenting). `scripts/harness/opencode.sh`. `research/tracing.md` §OpenCode. `addendum.md` §B.
