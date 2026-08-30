---
title: AI Orchestrator — v1 general architecture
status: proposal
created: 2026-08-26
scope: front-end webapp, backend service, harness adapters, LiteLLM + Langfuse wiring, local model serving
verified-against: Claude Code 2.1.246, Codex CLI 0.149.1, LiteLLM 1.98.0, OpenCode docs, DBOS Transact Python docs (all fetched 2026-08-26)
---

# v1 architecture

> **Corrections (2026-08-26, PRD finalize).** Superseded details, authoritative in `../mvp/prd.md` and `../mvp/addendum.md` §H: the agent commits its own work, so the loop is build → verify → **commit-guard**; the Answer path archives the blocked story file to `stories/.answers/` and re-dispatches with the Answer as prompt context (no `## Human Answers` in place); verify failure appends `## Verify Failure` and sets `status: in-progress`; the repository lock is **held** while a run is `needs-you`; Step `timeout_min` with defaults 90/30/5; `pause_when` for the done checkpoint belongs to the `for_each` group; per-step process groups and a WIP commit before any re-attempt; `/work` and harness session dirs are named volumes; project context is delivered as `{spec_folder}/project-context.md`, not prompt text; PR = compare URL only; `install_command` runs at checkout; a daily clone re-check needs a scheduled workflow. **§2.5's adapter table is provisional:** `--bare` is confirmed unusable (Claude Code 2.1.246 exposes only `Bash, Edit, Read` under it — no subagent tool, no `Write`), so the Claude adapter uses default discovery with an explicit allowlist plus `--disallowedTools "mcp__*"`; the Codex and OpenCode rows are to be re-derived from those harnesses' own documentation when their adapters are built (PRD §8, deferred). The binding contract is PRD FR-14's capability list, not any flag string.

```
Mac Mini M4 Pro 48 GB (host)                       ┌──────────────────────── docker compose ─────────────────────────┐
┌──────────────────────────────┐                   │                                                                 │
│ oMLX  :8000  /v1/chat/…      │◄── host.docker ───│  litellm :4000 ──► anthropic / openai APIs                       │
│  qwen3.8-27b (pinned, coder) │    .internal      │     │  virtual key per project · tags per run · langfuse_otel    │
│  qwen3.6-35b-a3b (general)   │                   │     ▼                                                           │
└──────────────────────────────┘                   │  langfuse :3000  (OTLP /api/public/otel, traces only)           │
                                                   │     ▲                     ▲                                     │
   operator browser                                │     │ orchestrator spans  │ claude-code spans (OTLP)            │
        │ https, token cookie                      │  ┌──┴─────────────────────┴───────────────────────────────┐     │
        ▼                                          │  │ orchestrator container (non-root, egress allowlist)    │     │
   ┌──────────────┐   /api/*  JSON                 │  │  FastAPI + DBOS (same process)                          │     │
   │ web (static) │──────────────────────────────► │  │  interpreter · adapters · git ops · clone check          │     │
   │ Vite+React   │                                │  │  tooling: git gh node uv claude codex opencode          │     │
   └──────────────┘                                │  │  /work/<project>/<repo>/wt/<branch>   (worktrees)      │     │
                                                   │  └──────────────────────────┬─────────────────────────────┘     │
                                                   │                  postgres ◄─┘ (dbos schema + app schema + litellm) │
                                                   └─────────────────────────────────────────────────────────────────┘
```

## 1. Front-end webapp

- **Stack:** Vite + React + TypeScript, TanStack Router + Query, CodeMirror 6 (YAML) for Templates, hand-authored components on the instrument-dark tokens as CSS variables (no component library — the design system forbids one and the surface is small). Served as static files by the orchestrator container (same origin, no CORS).
- **Auth:** `POST /api/login {token}` → HttpOnly cookie (30 d). Every `/api/*` checks it. Single operator; no roles.
- **Data flow:** REST + polling (5 s while any run is `RUN`, else 30 s). No websockets in v1; the footer prints the last update time. SSE is the upgrade path, the API shape does not change.
- **Screens → endpoints:**
  - Board: `GET /api/runs?status=&project=` (grouped client-side by status)
  - New workflow: `GET /api/templates`, `GET /api/projects`, `POST /api/runs/preflight`, `POST /api/runs`
  - Run detail: `GET /api/runs/:id` (run, steps, stories, gate record, cost), `GET /api/runs/:id/artifacts`, `GET /api/runs/:id/artifacts/file?path=`, `POST /api/runs/:id/answer`, `POST /api/runs/:id/continue`, `POST /api/runs/:id/skip-story`, `POST /api/runs/:id/retry-step`, `POST /api/runs/:id/cancel`
  - Projects: `GET/POST /api/projects`, `POST /api/projects/:id/repositories` (runs the clone check synchronously, returns per-check results)
  - Runs: `GET /api/steps?status=&project=&page=`, `GET /api/queue`
  - Templates: `GET /api/templates/:name/versions`, `GET /api/templates/:name/:v`, `POST /api/templates/:name/validate`, `POST /api/templates/:name` (creates v+1)
- **Diagram:** a pure function `yaml → nodes/edges` in TypeScript mirroring the backend schema; rendered as absolutely-positioned divs + SVG lines. Read-only.

## 2. Backend service

**Python 3.12, FastAPI, DBOS Transact, SQLAlchemy, Pydantic, PyYAML, GitPython/subprocess.** One process: the API and the DBOS workflow executor. Recovery on restart is DBOS's.

### 2.1 Data model (app schema)
`project` (name, context_text, context_paths[], github_token_ref, env_vars, litellm_key_ref, budget_month) · `repository` (project_id, url, default_branch, package_manager, quality_gate_command?, unit_test_command?, clone_check{status, at, output}) · `template_version` (name, version, yaml, hash, created_at; immutable) · `run` (project_id, repository_id, template_version_id, inputs{}, status, dbos_workflow_id, worktree_path, branch, spend_usd, budget_usd, manual_estimate_h?, trace_id, started/finished_at) · `step_run` (run_id, step_id, story_id?, kind, gate, status, attempt, harness, model, session_id, started/finished_at, usage{in,out,cost}, exit_code, output_path) · `gate_record` (run_id, at, actor, event, payload) · `repo_lock` (repository_id → run_id).

DBOS's own tables (`dbos.workflow_status`, `operation_outputs`) hold the durable position; `run`/`step_run` are the query-friendly projection the UI reads, updated from inside steps.

### 2.2 Template schema (v1, deliberately small)
```yaml
name: dev-loop            # + version, description
inputs: { <name>: { type: project|repository|string|path|enum|number, default?, required?, values? } }
steps:                    # ordered; one construct beyond sequence: for_each
  - id: <slug>
    run: git.worktree | shell | agent | git.commit | git.push
    with: { ... "{{var}}" substitution only, no expressions }
    gate: liveness | deterministic | human      # what a green means
    on_fail: escalate | fail | continue         # default: escalate
    retry: { attempts: 1 }                      # infra failures only
  - id: stories
    for_each: "{{stories_file}}"                # a YAML list file; items bound as {{story.*}}
    as: story
    steps: [ ... ]
```
`run: agent` extras: `harness`, `model?`, `skill` (`bmad-build-auto`), `args` (`spec_folder`, `story_id`), `output` (glob of the artifact file), `escalate_when` (`output.status in [blocked]`), `pause_when` (`story.spec_checkpoint or story.done_checkpoint`). The validator rejects unknown keys, unbound variables, and non-prefix-free story ids. No user loops, no expressions, no string functions — FR-10 stands.

### 2.3 Interpreter (one DBOS workflow)
```python
@DBOS.workflow()
def run_workflow(run_id: str) -> None:
    ctx = load_run(run_id)                       # template_version pinned, inputs bound
    for step in ctx.template.steps:
        execute(step, ctx)                       # sequence; for_each expands here

def execute(step, ctx, story=None):
    if step.for_each:  # bound list from stories.yaml, read once at start (a @DBOS.step, so it never changes on recovery)
        for story in ctx.stories: 
            for s in step.steps: execute(s, ctx, story)
        return
    result = run_step(step, ctx, story)          # @DBOS.step — the only side-effecting call
    if result.pause:   wait_for_human(ctx, step, story, reason="checkpoint")
    if result.escalate: wait_for_human(ctx, step, story, reason=result.reason)   # then re-execute or skip per the answer
```
- Every side effect is a `@DBOS.step` with `retries_allowed` only for `git.*` network failures; agent steps are never auto-retried (a retry is a new attempt with a new session id, decided by the human or by the verify rule).
- **Human wait:** `DBOS.recv(topic=f"human:{run_id}", timeout_seconds=30*24*3600)`; the API's answer/continue/skip/cancel endpoints call `DBOS.send(run.dbos_workflow_id, payload, topic)`. Zero compute while parked; survives restart.
- **Queueing:** a DBOS queue `runs` with `global_concurrency=2`, partitioned by repository (`queue_partition_key=repository_id`, `partition_concurrency=1`) → *one active run per repository, two overall*. That is the repository lock, for free; the Runs screen reads `DBOS.list_queued_workflows()`.
- **Cancel:** `DBOS.cancel_workflow` + a compensating step that removes the worktree and, if the branch was created by this run and never pushed, deletes it.
- **Recovery:** on process start DBOS resumes every `PENDING` workflow at its last completed step. An agent step interrupted mid-flight re-runs as a new attempt (the story file's status tells build-auto where to resume — `draft` → plan, `in-progress` → implement, `in-review` → review).

### 2.4 The agent contract (harness-independent)
Input: worktree path, prompt, env. Output: **the story spec file** `{spec_folder}/stories/{story_id}-*.md`, frontmatter `status` ∈ {draft, ready-for-dev, in-progress, in-review, blocked, done} and `## Auto Run Result` (status, blocking condition). The orchestrator:
1. checks liveness (exactly one file matches, frontmatter parses);
2. maps `blocked` → BLK with the blocking condition as the question; `ready-for-dev` + `spec_checkpoint` → CHK; `done` → next step; anything else → BLK "unexpected status";
3. records harness, model, session id, usage, cost, exit code on `step_run`.

The prompt is the same for every harness: *"Invoke the `bmad-build-auto` skill with spec folder `<spec_folder>` and story id `<id>`. <invoke_dev_with> [Halt after planning.]"* plus project context (text + context files) prepended, plus for a re-dispatch after an answer: *"The story file now contains `## Human Answers`; treat it as resolved intent."* Harnesses that cannot invoke skills by name get the rendered `workflow.md` path instead (the orchestrator can run `_bmad/scripts/render_skill.py` itself).

### 2.5 Harness adapters
```python
class Harness(Protocol):
    name: str
    capabilities: {preassign_session: bool, resume: bool, native_tracing: bool}
    def run(self, cwd, prompt, env, model, session_id=None) -> HarnessResult  # session_id, exit, usage, cost, log_path
    def resume(self, cwd, session_id, message, env) -> HarnessResult
    def resume_command(self, cwd, session_id) -> str | None
```
| Adapter | Command | Session | Env / config |
|---|---|---|---|
| `claude` | `claude -p --bare --session-id $SID --permission-mode dontAsk --allowedTools "Bash(uv run *)" "Bash(git *)" "Bash(pnpm *)" … --add-dir <repo> --output-format json --max-budget-usd $B "<prompt>"` | pre-assigned UUID | `ANTHROPIC_BASE_URL=http://litellm:4000 ANTHROPIC_AUTH_TOKEN=<project key> ANTHROPIC_CUSTOM_HEADERS="x-litellm-tags: run:<id>,project:<p>" CLAUDE_CODE_ENABLE_TELEMETRY=1 CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 OTEL_TRACES_EXPORTER=otlp OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse:3000/api/public/otel OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic …" CLAUDE_CODE_PROPAGATE_TRACEPARENT=1 TRACEPARENT=<run trace>` (+ `OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` — Langfuse takes traces only). `--bare` skips `.claude/skills` auto-discovery except under `--add-dir`, so pass the repo as `--add-dir`. |
| `codex` | `codex exec --json --sandbox workspace-write -C <wt> -m <model> -o <last.md> "<prompt>"` | captured from `thread.started` | `~/.codex/config.toml`: `model_provider="litellm"`, `[model_providers.litellm] base_url="http://litellm:4000/v1" env_key="LITELLM_API_KEY" wire_api="responses" http_headers={ "x-litellm-tags"="…" }`, `[otel] trace_exporter="otlp-http"` → Langfuse; per-run headers via `env_http_headers`. Skills read from `.agents/skills`. Enable `multi_agent` feature. |
| `opencode` (local) | `opencode run --format json --auto --dir <wt> -m litellm/<model> "<prompt>"` | captured from JSON events (fallback: `opencode session list --format json`) | `opencode.json` in the worktree: `provider.litellm = { npm: "@ai-sdk/openai-compatible", options: { baseURL: "http://litellm:4000/v1", apiKey: "{env:LITELLM_API_KEY}", headers: { "x-litellm-tags": "…" } }, models: { "local-coder": {...}, "local-general": {...} } }`, `permission: { edit: "allow", bash: "allow", webfetch: "deny" }`. Skills read from `.claude/skills` and `.agents/skills`. No OTEL — traces come from LiteLLM. |

Adapters never receive the GitHub token; git operations run in the orchestrator with the token injected per command. Model traffic only ever goes to LiteLLM.

### 2.6 Git operations
Clone check on repository save: `git ls-remote`, then `git clone --depth 1` into `/work/<project>/<repo>/base` (kept as the shared base clone). Run start: `git fetch`, `git worktree add /work/<project>/<repo>/wt/<branch> <branch>` (creating from `origin/<base>` when absent). `commit` adds the spec folder and everything build-auto changed (it finalises with a clean tree, so this is usually a no-op guard). `push` uses a per-command `GIT_ASKPASS` helper reading the project token; PR link = `gh pr create --fill --draft` when `gh` is authenticated, else a compare URL.

## 3. LiteLLM and Langfuse wiring

- **LiteLLM** (Postgres-backed for keys): `model_list` = Anthropic models (`anthropic/…`), OpenAI models (`openai/gpt-5.x-codex`), local models as `openai/<alias>` with `api_base: http://host.docker.internal:8000/v1` and `use_chat_completions_api: true` (so Codex's `/v1/responses` bridges to chat). `litellm_settings.callbacks: ["langfuse_otel"]`, `LANGFUSE_HOST=http://langfuse:3000`. One **virtual key per project** (`/key/generate` with `max_budget`, `budget_duration: monthly`, `tags: [project:<p>]`); the orchestrator stores the key ref, never the key in the DB in clear. Per-run attribution rides on `x-litellm-tags: run:<id>,story:<sid>,harness:<h>` and `x-litellm-session-id: <run id>` headers from every adapter. Spend per run = `GET /spend/logs?…` summed by tag, cached on `run.spend_usd` after each step; **budget halt** = `spend_usd > budget_usd` checked after every agent step → BLK.
- **Langfuse**: one trace per run, id = the run's W3C trace id, created by the orchestrator (`langfuse` Python SDK / OTel exporter to `/api/public/otel`). Orchestrator spans per step; Claude Code's own spans join via inbound `TRACEPARENT`; LiteLLM's generations join via the `traceparent` header the Claude path forwards and, for Codex/OpenCode, via `langfuse.session.id = run id` so at minimum the **session view** shows everything for a run even where span parenting is lost. Content redaction stays on by default; `OTEL_LOG_USER_PROMPTS` is a per-project switch.

## 4. Container and security (unchanged from the addendum, applied)
Non-root user; `--cap-drop ALL`, `no-new-privileges`; egress allowlist = GitHub, npm/PyPI, LiteLLM, Langfuse, host model server; no host credential mounts; project secrets injected per step from the orchestrator's secret store (Postgres, `pgcrypto`, key from env); agents never merge or push to a default branch (the push step refuses `working_branch == default_branch`).

## 5. Local model serving (host)
`brew install jundot/omlx/omlx`; `sudo sysctl iogpu.wired_limit_mb=43008`; serve `mlx-community/Qwen3.8-27B-4bit` (pinned, alias `local-coder`, `reasoning_effort: medium`) and `Qwen3.6-35B-A3B` 4-bit (alias `local-general`, LRU) with `--memory-guard-gb 40`. Verify tool calling through LiteLLM with a 2-turn agent smoke test before wiring OpenCode. Expect ~100–140 tok/s prefill and 25–40 tok/s decode on the coder; keep prompts small and rely on prefix caching.

## 6. What changes when v1 grows
- Concurrency: raise the DBOS queue's `global_concurrency`; nothing else.
- Second container: same image, same Postgres, DBOS handles distribution; worktrees move to a shared volume.
- Live updates: SSE on the same endpoints.
- Notifications: a `gate_record` consumer posting to Mattermost.
- Intake/spec generation (PRD M2): a second template `new-feature` that ends by writing the spec folder this template starts from.
