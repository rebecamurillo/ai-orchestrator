---
story: "7-4"
epic: 7
title: OpenCode readiness passes end to end with host model serving
requirements: [FR-14 (local), FR-33, NFR-7, PRD §8 items 7–8, AR-26 (host), AR-27]
binds: [AD-10, AD-11, AD-20]
---

# Story 7.4 — OpenCode readiness passes end to end with host model serving

As the Operator,
I want the local harness proven against a model actually served on the Mac mini, or the fallback recorded honestly,
So that the MVP's definition of done for `local` is met or explicitly deferred (PRD §6.1).

## Operator and agent split

*Added 2026-09-09, when the Operator decided this epic would be run by the orchestrator itself.*

**A coding agent cannot complete this story**, and it is the most operator-heavy in the MVP: it needs a
model server actually running on the Mac mini, the host LiteLLM reconfigured and restarted, and a
judgement about whether a local model can finish the fixture story at all.

**The agent does, in one dispatch:**

1. The proposed `host/litellm.config.yaml` entries for each `LOCAL_MODELS` alias (`openai/<served model>`,
   `api_base` the local server, `use_chat_completions_api: true`), the `langfuse_otel` callback line, and
   the `host/README.md` model section including the restart command — **written, not applied.** The host
   is the Operator's machine; changing what it serves is their action, not an agent's.
2. Any code the fallbacks require, unit-covered over the fakes.
3. A runbook, committed to this story's spec.
4. Then it **halts `blocked`**, naming what the Operator must start, restart, and run.

**The Operator then runs it** and answers with: whether the model server is serving each alias, the six
evaluation lines, observed throughput, and — the real decision — whether the fixture story reached `done`
within the readiness budget.

**The agent, resumed with that Answer**, records the "OpenCode — verified" block in `addendum.md` §B, or,
if the story could not pass, records the PRD §6.1 fallback as the decision with the Operator's stated
reason and leaves `local` reading `disabled: {line}` on New workflow — **which is the honest state, and a
perfectly acceptable outcome for this story.** It writes nothing into §B that the Operator did not observe.

## Scope

**In:** `host/README.md` and `host/litellm.config.yaml` entries for the local model server (oMLX) and the `LOCAL_MODELS` aliases as `openai/<alias>` with `use_chat_completions_api: true`; running `POST /harnesses/local/readiness`; recording results in `addendum.md` §B; if the run cannot pass, recording the PRD's fallback (Codex CLI pointed at the Gateway for local models, addendum §C) as the decision, with the reason.
**Out:** model selection or tuning beyond what makes the fixture story pass.

## Binding rules (inlined)

- **Preconditions.** Host LiteLLM, Langfuse, and the model server reachable; halt `blocked` naming the missing one otherwise.
- **Host config (AD-20).** `host/litellm.config.yaml` `model_list` entries for each `LOCAL_MODELS` alias pointing at the local server (`openai/<served model>`, `api_base` the server, `use_chat_completions_api: true`); documented restart command; the `langfuse_otel` callback with `LITELLM_OTEL_V2=true`.
- **Checks.** The readiness lines of 5.8 for `local`: story file done, session id recorded, trace observed (by user id, time window), spend attributable (rows with `spend 0`), verify exit 0, run done.
- **Fallback (PRD §6.1, addendum §C).** If the fixture story cannot reach `done` on the local model within a reasonable number of attempts (the readiness budget), record in `addendum.md` §B: what failed, and the decision to ship `local` later or to use the fallback; the `local` harness stays `disabled: {line}` on New workflow, which is the honest state.
- **Record.** `addendum.md` §B "OpenCode — verified" block (argv, session capture, plugin behaviour, observed throughput) and `host/README.md` model section.

## Acceptance criteria

**Given** the host services and the model server
**When** the `local` readiness Run completes
**Then** either `GET /harnesses` shows `local · enabled` with every line `ok`, or it shows `disabled: {first failing line}` and the addendum records the fallback decision with the evidence.

**Given** `host/litellm.config.yaml`
**When** read
**Then** it lists every `LOCAL_MODELS` alias with the chat-completions flag.

**Given** any fix made to 7.3 or the tracer
**When** `make lint test` runs
**Then** it is unit-covered and green.

## Verification

```bash
make up && curl -s -X POST -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" localhost:8000/api/v1/harnesses/local/readiness
```

## Sources for detail only

PRD §6.1 (definition of done, `local` fallback), §8 items 7–8, FR-33. Spine AD-20 (host), AD-11. `addendum.md` §A Local models, §B, §C. `host/README.md`.
