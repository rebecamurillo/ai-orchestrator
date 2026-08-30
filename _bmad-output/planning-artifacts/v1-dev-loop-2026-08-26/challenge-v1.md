---
title: AI Orchestrator — v1 challenge (one week, dev loop)
status: proposal
created: 2026-08-26
inputs:
  - _bmad-output/forge/agent-workflow-os/forged-idea.md
  - _bmad-output/planning-artifacts/prds/prd-ai-orchestrator-2026-08-24/prd.md
  - _bmad-output/planning-artifacts/prds/prd-ai-orchestrator-2026-08-24/addendum.md
  - _bmad-output/planning-artifacts/ux-designs/ux-ai-orchestrator-2026-08-25/EXPERIENCE.md
  - .claude/skills/bmad-build-auto/* and bmad-spec/assets/stories-schema.md
---

# The challenge

The repository's design (forge → PRD → UX spine) is a well-argued **8–12 month** product. The brief is now **a running orchestrator in one week, for the development steps only, with the human supplying the working branch and the spec folder**. Those two facts are incompatible unless most of what the PRD calls M1 is removed — not deferred, removed — and the remaining core is simplified to the point where three harnesses fit in the same week.

This document says what to keep, what to cut, what the repo's design got wrong for this brief, and what v1 actually is.

## 1. What the repo's design gets right (keep)

| Keep | Why it still holds |
|---|---|
| **DBOS as the durable engine, Postgres only** | One container + Postgres is the same architecture as N containers + Postgres. Human waits are `recv`, queues are built in. Nothing to install beyond Postgres. |
| **YAML is a minimal internal schema, not the CNCF/Open Workflow DSL** | Still no Python runtime for the DSL. A five-step-type schema is a day of work; an interpreter for someone else's spec is not. |
| **Workflow structure is authored, instances are bound variables** | This is exactly the "human provides branch + spec folder, orchestrator binds and runs" model the brief describes. |
| **Version and pin every template; runs never change mid-flight** (C-1) | Cheap to build on day one, impossible to retrofit. |
| **Orchestrator owns session identity** | Claude Code: `--session-id <uuid>` pre-assigned. Codex and OpenCode: captured from the first JSON event. Stored in Postgres per step. |
| **Gate strength is labelled** (liveness / deterministic / human) and **nothing without an oracle is ever green** | The single most important honesty rule. The v1 UI prints `skipped` and `unvalidated` as words. |
| **Escalate on structured status, not on prose** | Kept, but the structure is now the **story spec file's frontmatter**, not a JSON schema — see §3. |
| **Instrument-dark design system** | Already specified to the pixel; "colour is signal only" is the "epurated, attention-driven" UI the brief asks for. |
| **Single login, per-project secret scoping, non-root container, LiteLLM virtual keys, Langfuse OTLP** | All cheap at the start, all expensive later. |

## 2. What must be cut for one week (and why it is safe)

| Cut from M1 | Why it can go |
|---|---|
| **AC → Playwright spec generation, test-id contract, G2 gate, unmatched-criterion blocking** (FR-24a, FR-28b, FR-12a, F9 provisioning, FR-47/48/49) | The brief moves spec authorship to the human. The oracle for v1 is the repository's own `quality_gate_command` after every story — a deterministic check that already exists in the target repos. The Playwright-from-criteria machinery was the bulk of M1's cost and its largest untested assumption. |
| **Serialized execution** (FR-47) | It existed only because a shared E2E database was in scope. Without E2E provisioning, the lock is **one active run per repository** (worktree per run), several repositories in parallel. |
| **Notifications surface / review inbox** as a first-class screen | The brief's home is the **board**. "Needs you" is a board column plus the rail count. A separate inbox is redundant for one operator with a handful of runs. |
| **Epic-level re-spec on G3 rejection, session-resuming review loops, rework caps as a mechanism** | v1 has no G3. The run ends when the branch is pushed; the human reviews the branch in GitHub. A rejected story is a new story in `stories.yaml` and a new run. |
| **Manual-estimate ÷ actual-minutes verdict metric as infrastructure** | Kept as **one optional field** on New workflow (it is a one-way door per the PRD), but no derived metric or counter-metric dashboard in v1. |
| **Guacamole, Mattermost, GitHub issue ingest, multi-container** | Already M3. |

What is *not* cut, despite the pressure: template versioning, gate labelling, session identity in Postgres, per-project secrets, Langfuse trace per run, budgets. Each is a day-one seam that costs hours now and weeks later.

## 3. Where the repo's design is wrong for this brief

### 3.1 The agent contract is the artifact file, not a JSON schema
The PRD requires every agent task to return `--json-schema`-validated structured output (`status`, `open_questions`, `assumptions`). Only Claude Code supports that flag; Codex has `--output-schema`; a third harness may have nothing. But **`bmad-build-auto` already writes its result into the story spec's frontmatter** (`status: draft | ready-for-dev | in-progress | in-review | blocked | done`) plus a `## Auto Run Result` section with the blocking condition. That file lives in the spec folder the brief designates as the artifact destination.

**Decision:** the harness-independent contract is *the story spec file*. The orchestrator validates a `build` step by reading `{spec_folder}/stories/{story_id}-*.md` frontmatter. Liveness = file exists and parses; status drives routing; `blocked` escalates with the blocking condition as the question. No schema flags on any harness, so all three harnesses have the same adapter surface: **run a prompt in a directory, capture a session id, exit**.

### 3.2 `stories.yaml` was designed for this dispatcher
The BMAD `stories.yaml` schema carries three **caller-only** fields: `spec_checkpoint` (human reviews the story spec between planning and implementation), `done_checkpoint` (pause after the story), `invoke_dev_with` (text appended to the dispatch prompt). And `bmad-build-auto` honours the phrase **"Halt after planning."** by stopping at `ready-for-dev`. The orchestrator *is* the "dispatching caller" the schema anticipates. v1 implements exactly those three fields and nothing more — the human gates in v1 are the ones the spec author already declared.

### 3.3 The human's reply goes into the file, not the session
The PRD's blocked-story path is "print the `--resume` command; the operator answers in a terminal". That is Claude-specific, depends on harness-local session content (C-4), and is invisible to the gate record. **Decision:** the primary path is an **Answer box** on the run detail: the answer is appended to the story spec under `## Human Answers`, status reset to `draft`, the story re-dispatched to the same harness with the file as context. It works for all three harnesses, survives container replacement, and is recorded. The resume command stays as the secondary affordance for Claude and Codex.

### 3.4 The board encodes status, not pipeline stage
The UX memlog chose stage columns (Spec → Plan/G2 → Build → Review/G3 → Merged) to make a serialized engine look honest. v1 has one template (the dev loop) and real concurrency across repositories, so the stage is a line on the card ("story 3-2 · build") and the columns are **Queued · Running · Needs you · Done · Failed**. The amber column is where attention goes; nothing else on the page is amber.

### 3.5 A read-only diagram is not a visual editor
The PRD rejected a Kestra-style editor as a product in itself. Correct — and the brief does not need it: **editable YAML on the left, a diagram rendered from the parsed YAML on the right**. The diagram is a pure function of the same schema the backend validates. No drag-and-drop, no graph persistence. One day of front-end work.

### 3.6 Three harnesses in week one is the biggest risk — and it is manageable only because of 3.1
The PRD keeps one harness until the loop works. The brief wants Claude Code, Codex and a local-model harness from day one. With the file contract, an adapter is ~80 lines: build the command, set the env (LiteLLM base URL, virtual key, `TRACEPARENT`/headers), run in the worktree, capture the session id, return exit status and token usage. Claude and Codex are documented and verified (see §5). The third is best-effort in week one: it must run, trace, and write the file; resume can wait.

### 3.7 Subagents are a hard requirement of `bmad-build-auto`
The skill HALTs `blocked · no subagents` if it cannot spawn them (plan, implement and four review layers run as subagents). Claude Code has them. Codex CLI has the `multi_agent` feature flag and `SubagentStart/Stop` hooks (verify on day 1). OpenCode has subagents via its `task` tool and `mode: subagent` agents. If a harness cannot, the skill's `implementation_handoff` and `review_layers` are overridable per harness in `_bmad/custom/bmad-build-auto.toml` — that is the documented escape hatch, not a fork of the skill.

## 4. What v1 is

**One workflow template (`dev-loop`)** that, given a project, one repository, a base branch, a working branch and a spec folder containing `SPEC.md` + `stories.yaml` (+ optional `epics.md`):

1. `checkout` — worktree on the working branch (created from base if missing)
2. `baseline` — `quality_gate_command`; red before any story → `ERR`, nothing spent
3. **for each story** in list order:
   - `build` — `bmad-build-auto` folder+id dispatch via the chosen harness, `invoke_dev_with` appended, "Halt after planning." if `spec_checkpoint`
   - read the story file → `blocked` → **BLK** (Needs you); `ready-for-dev` with checkpoint → **CHK**; `done` → continue
   - `verify` — `quality_gate_command`; fail → one re-dispatch with the failure as context, then **BLK**
   - `commit` — spec folder + code; `done_checkpoint` → **CHK**
4. `push` — working branch to origin; PR link if `gh` is available

Five screens (Login, Workflows board + New workflow + Run detail, Projects + New project, Runs, Templates), one container, LiteLLM in front of every model, one Langfuse trace per run.

**Not in v1:** intake, spec generation, E2E provisioning, PR creation by the machine (a link is enough), notifications outside the UI, budgets beyond per-run halt, multi-repo runs.

## 5. Harnesses — verified 2026-08-26

| | Claude Code 2.1.246 | Codex CLI 0.149 | OpenCode (local models) |
|---|---|---|---|
| Headless | `claude -p --bare --permission-mode dontAsk --allowedTools … --output-format json` | `codex exec --json --sandbox workspace-write -C <wt>` (`--full-auto` deprecated; exec is always approval `never`) | `opencode run --format json --auto --dir <wt> -m litellm/<model>` |
| Session id | **pre-assigned** `--session-id <uuid>` | captured from `thread.started` event; cannot be pre-assigned | captured from JSON events / `opencode session list` |
| Resume with a message | `claude -p --resume <id> "…"` | `codex exec resume <id> "…"` | `opencode run --session <id> "…"` |
| Gateway | `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` → LiteLLM `/v1/messages` | `[model_providers.litellm] base_url=http://litellm:4000/v1 wire_api="responses"` (**only `responses` is supported now**; LiteLLM bridges to chat for local models with `use_chat_completions_api: true`) | `provider.litellm` with `@ai-sdk/openai-compatible`, `baseURL`, `headers` |
| Trace correlation | `CLAUDE_CODE_ENABLE_TELEMETRY=1 CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 OTEL_TRACES_EXPORTER=otlp` to Langfuse OTLP; reads inbound `TRACEPARENT`; `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` through the gateway | `[otel] trace_exporter="otlp-http"` (traces separate from logs now); plus `http_headers` on the provider carrying `x-litellm-tags` / `langfuse_*` | no OTEL; LiteLLM `langfuse_otel` callback + per-request headers (`x-litellm-tags`, `x-litellm-session-id`) carry the run id |
| Skills | `.claude/skills` (`.agents/skills` **not** read) | `.agents/skills` (+ repo root, `~/.agents/skills`) | `.claude/skills` **and** `.agents/skills` |
| Subagents | yes | `multi_agent` feature flag — verify day 1 | yes (`task` tool) |
| Permissions for unattended | `dontAsk` + allowlist; `--bare` needs an explicit key | sandbox `workspace-write`; hooks; `--dangerously-bypass-approvals-and-sandbox` only inside the container | `permission` block `allow`/`deny`; `--auto` |

**Why OpenCode for the local harness:** it discovers the same skill directories BMAD already installs (`.claude/skills`, `.agents/skills`), speaks OpenAI-compatible chat completions (which is what every Apple-silicon server exposes), has a documented headless mode with JSON events and session resume, supports subagents, and a `headers` option on the provider for trace tagging. Fallbacks, in order: (1) **Codex CLI pointed at LiteLLM** for local models — one fewer adapter, but only `/v1/responses` and its prompts are tuned for GPT models; (2) Claude Code with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` and LiteLLM's `/v1/messages` translation — documented by LiteLLM, explicitly unsupported by Anthropic, and Claude Code's tool surface is heavy for a 27B model.

## 6. Local models on the Mac Mini M4 Pro (48 GB, 20-core GPU, ~273 GB/s)

Research date 2026-08-26; numbers are ±30% until measured on the box.

| Role | Recommendation | Why | Footprint |
|---|---|---|---|
| **Coding** | **Qwen3.8-27B** (dense, Apache-2.0, released 2026-08-14) | Best open coder that fits: Terminal-Bench 2.1 73.0, SWE-bench Pro 61.7, LiveCodeBench 90.3. 262K context, KV cache is tiny (64 KB/token). Use `reasoning_effort: medium` for agent loops. | 4-bit 17–19 GB + 2 GB KV @32K. ~12–17 tok/s raw decode; 25–40 tok/s with oMLX MTP speculative decoding. |
| **Coding runner-up** | **Qwen3.6-35B-A3B** (MoE, 3B active) | Two to three times faster (35–60 tok/s), SWE-bench Verified 73.4, better characterised, safer parsers. Pick this if latency matters more than peak quality. | 4-bit 20–22 GB, KV ~1 GB @64K. |
| **General** | **Qwen3.6-35B-A3B** | MMLU-Pro 85.2, vision input, reliable tool calls, fast. Same weights can serve both roles if memory is tight. | as above |
| **General runner-up** | **gpt-oss-20b** | 13 GB, ~60 tok/s, cleanest structured tool calls, 128K; weaker on long agentic terminal work. | 13 GB + 3 GB KV @128K |

**Runtime:** **oMLX** (MLX-native, continuous batching, prefix + SSD-tiered KV cache, LRU multi-model with `--memory-guard-gb`, tool-parser auto-detect, `/v1/chat/completions` and `/v1/models`). Alternatives: LM Studio headless (`llmster`, MLX engine) if a GUI is wanted; Ollama's MLX backend is the simplest but ~1.5× slower on MoE decode and one model per runner.

**Memory plan:** both 4-bit models resident is ~39–43 GB — borderline. Robust setup: raise the GPU wired limit (`sudo sysctl iogpu.wired_limit_mb=43008`), pin the coder, let the general model LRU-swap (~5–7 s reload), or pair Qwen3.8-27B with gpt-oss-20b (~35 GB total).

**Two facts that shape the architecture:** Docker on macOS has no GPU access, so **the model server runs on the host**, and the orchestrator container reaches it at `host.docker.internal`. And **prefill is the bottleneck** — a cold 32K prompt is 1.5–2 min on the MoE and 4–5 min on the dense 27B — so prefix caching in the server is mandatory and the local harness should be given the smallest prompt that still carries the story.

**Expectation setting:** these models sit one to two tiers below Claude/GPT-5 on multi-hour agentic runs, and harness choice moves outcomes as much as model choice. v1 treats the local harness as a cost lever for routine stories, not as a peer.

## 7. The week

| Day | Backend | Front-end | Exit criterion |
|---|---|---|---|
| 1 | Compose: Postgres, LiteLLM (+ Postgres for keys), Langfuse, orchestrator image (git, gh, node, uv, claude, codex, opencode, non-root). FastAPI + DBOS skeleton, token auth, template schema + validator, `dev-loop` v1 YAML. | Vite + React shell, rail, tokens as CSS variables, Login. | `claude -p` from inside the container through LiteLLM appears in Langfuse. |
| 2 | Projects/repos CRUD, clone check, worktree ops, per-project LiteLLM virtual key, secret scoping. | Projects, New project with live clone check. | A bad token fails on save with the verbatim git error. |
| 3 | Interpreter: `git.worktree`, `shell`, `git.commit`, `git.push`, `for_each`, gates, escalate → `recv`. Story-file contract parser. Claude adapter. | Workflows board, New workflow with pre-flight. | One story runs end to end on a real repo with Claude, blocks on purpose, resumes from the Answer box. |
| 4 | Codex adapter, OpenCode adapter, Langfuse trace id through every path, budget halt, repository lock queue. | Run detail (question, answer, steps, artifacts, cost, resume command). | Same story runs on all three harnesses; three traces, one id each. |
| 5 | Checkpoints (`spec_checkpoint`, `done_checkpoint`, `invoke_dev_with`), retry on verify failure, cancel + rollback. | Runs (queue + history), Templates (YAML editor + rendered diagram + versions). | A 3-story `stories.yaml` completes unattended with one checkpoint. |
| 6 | Hardening: restart mid-run (DBOS recovery), non-root + allowlist, egress list, secrets never in agent env for other projects. | Empty/loading/error states, polling with "updated hh:mm:ss". | Kill the container mid-story; the run resumes at the right step. |
| 7 | Dogfood: run a real epic of `fullstack-app`. Fix what breaks. | — | First real branch pushed by the orchestrator. |

**What slips first if the week runs short:** OpenCode adapter (fall back to Codex→LiteLLM for local models), Templates editing (view-only), Runs history pagination, cancel-with-rollback (cancel without rollback).

## 8. Open items to confirm on day 1 (cheap, decisive)

1. Codex `multi_agent` feature flag gives `bmad-build-auto` the subagents it demands; otherwise override `implementation_handoff` / `review_layers` for Codex in `_bmad/custom/bmad-build-auto.toml`.
2. OpenCode emits the session id in `--format json` events (else read `opencode session list --format json` after the run).
3. `TRACEPARENT` from the orchestrator survives Claude Code → LiteLLM → Langfuse as one trace; for Codex/OpenCode, that the `x-litellm-session-id` / `langfuse_*` headers land as Langfuse session/trace attributes through the `langfuse_otel` callback.
4. oMLX prefill/decode on the actual Mac Mini for Qwen3.8-27B 4-bit at 32K context.
5. `bmad-build-auto` under Claude `dontAsk` + allowlist runs to `done` on a trivial story (allowlist must cover `uv run`, git, the repo's package manager).
