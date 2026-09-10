---
story: "9-4"
epic: 9
title: Harness environment and registry in off-mode
requirements: [FR-8 (pre-flight harness line), FR-14, NFR-7]
binds: [AD-5, AD-10, AD-11]
---

# Story 9.4 — The harness environment when a service is off

As the Operator,
I want a harness to be handed the credentials that exist and none that do not, and to be told plainly when a harness cannot run at all,
So that turning the Gateway off produces a refusal I can read instead of an attempt that fails on an empty Authorization header.

## Scope

**In:** `infrastructure/harness/registry.py::alias_table`'s off-mode branches; a `claude_native_aliases` builder in `infrastructure/harness/claude/adapter.py`; `local_aliases` gated on tracing; `build_harnesses` without `local` when the Gateway is off; the `local` harness row written disabled with a stated reason at start-up.
**Out:** the config files each CLI reads (9-5), the words on screen (9-6). No provider credential is added to `Settings` in this story or any other in this epic.

## Binding rules (inlined)

- **The contract does not change (AD-10).** `HARNESS_ENV_CONTRACT` keeps its fifteen names in its order, and `env_for` keeps exporting all of them; with a service off, its names simply carry the blank values `Settings` holds. This is what keeps the exported key set equal to the contract plus `HOME`, `PATH`, `LANG`, `TERM`, which `tests/unit/test_harness_env.py` asserts and which `tests/unit/test_harness_env_contract.py` compares against the bash array. **Do not add a name, do not drop a name, do not add a "mode" variable.**
- **A blank credential is never exported as an alias.** Aliases are the harness-native names, and an empty one is worse than an absent one — Claude Code with `ANTHROPIC_AUTH_TOKEN=""` sends an empty `Authorization` and fails on the first call, while with the name absent it uses the login in `~/.claude`. So:
  - **Gateway off, `claude`:** `claude_native_aliases` — no `ANTHROPIC_AUTH_TOKEN`. `ANTHROPIC_CUSTOM_HEADERS` keeps only the lines that still mean something: the two `langfuse_*` lines when tracing is on, none of the three `x-litellm-*` lines (there is no LiteLLM to read them). With tracing also off the name is absent entirely rather than set to an empty string. The content-logging pair keeps its existing rule (`ORCH_LOG_CONTENT == "1"`).
  - **Gateway off, `codex`:** unchanged — it has no aliases; it reads contract names from its config file, which 9-5 stops writing.
  - **Tracing off, `local`:** `local_aliases` returns neither `LANGFUSE_BASEURL` nor `LANGFUSE_USER_ID`. A plugin pointed at a blank base URL is a misconfiguration; a plugin the config file does not load (9-5) needs neither name.
- **`alias_table(settings)` stays the one join.** It already merges the subscription table per harness; add the off-mode selection there, in the same shape, so `env.py` stays harness-agnostic and every builder keeps the `AliasBuilder` signature (contract in, native names out) that lets the contract test call it.
- **Subscription mode and gateway-off mode are different modes and must not be conflated.** `CLAUDE_SUBSCRIPTION_AUTH=true` with the Gateway **on** still routes through LiteLLM and still moves the virtual key to `x-litellm-api-key`; with the Gateway **off** there is no virtual key at all, and `claude_native_aliases` is what applies regardless of that flag. State this in the module docstring.
- **`local` is unavailable without the Gateway.** OpenCode's route to a host model server in this system *is* the Gateway (`-m litellm/{model}`, `LOCAL_MODELS` are LiteLLM aliases). With the Gateway off: `build_harnesses` does not register it, exactly the way `fake` is registered only under `ORCH_TEST_MODE`; and the start-up seed writes its `harness` row `enabled = false` with `failing_check = "gateway disabled (LITELLM_BASE_URL blank)"`, mirroring `seed_test_harness`, which is already the one use case allowed to write that column outside readiness. Pre-flight's harness line then reads that reason (`application/preflight/checks.py::_failing_check`) and `create_run` refuses — the same path an Operator already experiences for a harness readiness has not passed.
- **A Project may still supply its own key.** `env_for` merges the Project's decrypted variables first and the contract over them, so a Project variable named `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` reaches the harness in off-mode and is overridden by nothing — AD-5's forbidden list (`GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL`, `ORCHESTRATOR_*`, `OTEL_LOG_*`) is unchanged. Document it in the docstring as the supported way to authenticate a harness that is not logged in; add no `Settings` field for it.

## Acceptance criteria

**Given** `gateway_enabled` false and `tracing_enabled` true, and the `claude` harness
**When** `env_for` builds an attempt's environment
**Then** the key set still equals `HARNESS_ENV_CONTRACT` ∪ Project vars ∪ `{HOME, PATH, LANG, TERM}` ∪ `{ANTHROPIC_CUSTOM_HEADERS}`; `ANTHROPIC_AUTH_TOKEN` is absent; `LITELLM_BASE_URL` and `LITELLM_API_KEY` are present and blank; and `ANTHROPIC_CUSTOM_HEADERS` holds exactly the two `langfuse_*` lines, in the contract's order.

**Given** both services off, and the `claude` harness
**When** `env_for` builds an attempt's environment
**Then** `ANTHROPIC_CUSTOM_HEADERS` is absent as well, and the key set equals the contract plus the base names plus the Project's variables.

**Given** both services on
**When** `env_for` builds an attempt's environment for each of `claude`, `codex`, `local`
**Then** every existing expectation holds byte for byte — this mode is the shipped default and nothing about it moves.

**Given** `tracing_enabled` false and the `local` harness
**When** `local_aliases` is applied
**Then** neither `LANGFUSE_BASEURL` nor `LANGFUSE_USER_ID` is exported.

**Given** `gateway_enabled` false
**When** `build_harnesses(settings, runner)` is called
**Then** its keys are `{claude, codex}` (plus `fake` under `ORCH_TEST_MODE`), and `local` is absent.

**Given** `gateway_enabled` false
**When** the start-up seed runs
**Then** the `local` row exists, `enabled` is false, and `failing_check` names the Gateway; **and** pre-flight's harness line for a Template naming `local` fails with that reason, and `create_run` refuses.

**Given** `gateway_enabled` true
**When** the start-up seed runs
**Then** `local`'s `enabled` and `failing_check` are left to readiness exactly as today — this story never enables a harness.

## Implementation notes

- New test files: `backend-api/tests/unit/test_harness_env_off_mode.py`, `test_harness_registry_off_mode.py`. Do not edit `test_harness_env.py`, `test_harness_env_contract.py`, `test_harness_env_subscription.py`, `test_alias_table_merge.py` or `test_harness_registry.py`; all five must stay green under the default environment.
- The new use case belongs beside `seed_test_harness` in `application/use_cases/harnesses.py` and takes ports, not a session (AD-2). `infrastructure/db/seed.py::seed_harness_table` calls it in the same place the test-mode branch sits.
- Keep `claude_aliases` and `claude_subscription_aliases` as they are and add the third builder beside them; three small builders read better than one that branches, and each stays callable by the contract test.

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-5 (one credential; what a harness never receives), AD-10 (the contract is the script's list), AD-11 (identity headers). `infrastructure/harness/env.py` — the merge order and the forbidden names. `infrastructure/harness/registry.py` — `alias_table`'s docstring on why merging per harness beats swapping tables. `infrastructure/db/seed.py` and `application/use_cases/harnesses.py` — the `fake` precedent for a conditional row. `application/preflight/checks.py` — the harness line and `_failing_check`.
