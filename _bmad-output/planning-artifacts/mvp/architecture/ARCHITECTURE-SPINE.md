---
name: ai-orchestrator-mvp
type: architecture-spine
purpose: build-substrate
altitude: feature
paradigm: 'clean architecture (ports & adapters) per component; durable interpreter over a materialised plan'
scope: 'ai-orchestrator MVP — web-client (Astro), backend-api (FastAPI + DBOS walker + harnesses), harness setup scripts, docker compose; governs the epics built from mvp/prd.md'
status: final
created: '2026-09-02'
updated: '2026-09-02'
binds: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27, FR-28, FR-29, NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-6, NFR-7, NFR-8]
sources:
  - ../prd.md
  - ../addendum.md
  - ../template-dsl-draft.md
  - ../../v1-dev-loop-2026-08-26/architecture-v1.md
  - ../../../../GUIDELINES.md
  - research/dbos.md
  - research/tracing.md
  - research/frontend.md
  - research/backend.md
  - research/spend.md
companions:
  - prd-deltas.md
  - deliverables/AGENTS.md, deliverables/web-client/AGENTS.md, deliverables/backend-api/AGENTS.md
  - deliverables/scripts/harness/{_common,claude,codex,opencode}.sh, deliverables/.env.example
  - deliverables/solution-design.html
---

# Architecture Spine — ai-orchestrator-mvp

`[ADOPTED]` marks a decision the PRD, the user, or verified reality had already settled; unmarked ADs bind equally.

## Design Paradigm

**Clean architecture (ports & adapters)** in each deployable, and **one durable interpreter over a materialised plan** as the runtime model: a Run is planned entirely at start into `step_run` rows, then walked by a durable engine that executes one row at a time and parks for humans.

| Layer | backend-api directory | May import |
| --- | --- | --- |
| domain | `src/orchestrator/domain/` — entities, value objects, status machines, port protocols | stdlib (no `os`, `shutil`, `subprocess`), pydantic |
| application | `src/orchestrator/application/` — use cases, step kinds, template validator/planner, routing and budget rules | domain |
| api | `src/orchestrator/api/` — FastAPI routers per feature, request/response schemas, bearer dependency | application, domain |
| infrastructure | `src/orchestrator/infrastructure/` — DBOS engine adapter + walker, SQLAlchemy repositories, git, workspace, process runner, harness adapters, gateway, tracing, crypto, settings | application, domain |
| composition root | `src/orchestrator/main.py` — wires adapters into ports, launches DBOS + uvicorn | everything |

web-client is an **Astro multi-page app with React islands** acting as the browser's only origin (backend-for-frontend): pages, Actions and a proxy route call backend-api server-side; islands never hold a backend credential.

## Invariants & Rules

```mermaid
graph LR
  main[main.py composition root] --> api
  main --> infra[infrastructure]
  api --> application
  infra --> application
  application --> domain
  web[web-client] -->|HTTP JSON, Bearer token| api
```

### AD-1 — Two deployables, one browser-facing origin [ADOPTED]

- **Binds:** all
- **Prevents:** islands calling backend-api directly, CORS, cookies on the API, two auth surfaces
- **Rule:** The deployables are `web-client` and `backend-api` (the orchestrator process and the harness CLIs share the backend-api container). The browser talks only to web-client. web-client's server side is the only caller of backend-api and always sends `Authorization: Bearer $ORCHESTRATOR_TOKEN`; `src/api/server.ts` (server-only, reads `astro:env/server`) and `src/api/client.ts` (browser, base `/api/`) are the only modules that call `fetch`; the proxy route `src/pages/api/[...path].ts` and Actions import `server.ts`. backend-api exposes `/api/v1/*` plus `/openapi.json` and `/healthz`, JSON only, no cookies, no CORS headers. Enforced by eslint `no-restricted-globals`/`no-restricted-imports` on `src/islands/**`, `src/stores/**`, `src/components/**`.

### AD-2 — Dependency direction inside backend-api

- **Binds:** backend-api, every epic
- **Prevents:** DBOS, SQLAlchemy, FastAPI, filesystem or subprocess idioms leaking into use cases; untestable rules
- **Rule:** Imports follow the diagram above and nothing else. `domain/` and `application/` import neither `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`, `langfuse` nor `git`; all I/O goes through the ports in AD-14. Enforced by `import-linter` layer + forbidden contracts in `pyproject.toml`; CI fails on violation.

### AD-3 — The contract is owned by backend-api and generated into web-client

- **Binds:** FR-1..FR-29 (every endpoint), web-client `src/api/`
- **Prevents:** hand-written TypeScript twins drifting from Pydantic
- **Rule:** Pydantic schemas in `api/schemas/` are the single source. `make openapi` exports `contracts/openapi.json`; web-client generates `src/api/schema.d.ts` with `openapi-typescript` and calls through `openapi-fetch`. CI regenerates both files and fails on `git diff --exit-code`; no TypeScript type for an API payload is written by hand.

### AD-4 — One secret token, two carriers [ADOPTED]

- **Binds:** FR-1, NFR-3
- **Prevents:** a second user model, roles, session tables
- **Rule:** `ORCHESTRATOR_TOKEN` (instance env) is the only credential. backend-api authenticates every `/api/v1/*` request by constant-time comparison of the bearer. web-client's `POST /login` compares the same token and sets a signed, HttpOnly session cookie `orch_session` (30 days, signing key `ORCHESTRATOR_SESSION_SECRET`); Astro middleware redirects unauthenticated page loads to `/login`.

### AD-5 — Credentials come from the instance env and stop at the process that needs them [ADOPTED]

- **Binds:** FR-2, FR-11, FR-14, FR-26, NFR-3, PRD §11 privacy
- **Prevents:** tokens in the DB, tokens in agent environments, per-repo credential code
- **Rule:** `GITHUB_TOKEN`, `LITELLM_API_KEY`, `LANGFUSE_PUBLIC_KEY/SECRET_KEY`, `ORCHESTRATOR_*` are read once by `infrastructure/settings.py` (pydantic-settings) and nowhere else. Git commands receive `GITHUB_TOKEN` per command via `GIT_ASKPASS`. A harness process receives exactly the `HARNESS_ENV_CONTRACT` (AD-10): gateway URL and `LITELLM_API_KEY`, Langfuse keys and trace env, the Run identifiers, the Project's env vars, and content-logging switches (`OTEL_LOG_USER_PROMPTS`, Codex `log_user_prompt`, plugin equivalents) only when `project.log_prompt_content` is true; never `GITHUB_TOKEN`, never the orchestrator's own env. Project env vars are stored Fernet-encrypted (`ORCHESTRATOR_SECRET_KEY`) and returned masked.

### AD-6 — The durable engine is a port; identifiers are opaque

- **Binds:** FR-12, FR-13, FR-25, NFR-1
- **Prevents:** DBOS tables, ids, or decorators appearing outside `infrastructure/dbos/`; an engine swap touching use cases
- **Rule:** `domain/ports/engine.py` declares `WorkflowEngine` with exactly: `enqueue(run_id, partition_key)`, `signal(run_id, Signal)`, `cancel(run_id)`, `list_queue() -> [QueueEntry{run_id, engine_state ∈ {enqueued, pending}, position: int | None, enqueued_at}]`, `attempt_record(engine_ref) -> EngineRecord | None`, `schedule(name, cron, job)`. `run.engine_ref` and `attempt.engine_ref` are JSON written and read only by the adapter. The adapter is replay-safe: every side effect inside an engine step, side-effecting steps declared with engine retries off (the engine never re-executes on its own), list files read once per Run, no wall-clock branching outside steps; `application_version` is the pinned `DBOS_APPLICATION_VERSION`, bumped deliberately when the walker's step sequence changes, after draining active Runs.

### AD-7 — A Run is planned completely, purely, from the remote branch, before it is enqueued

- **Binds:** FR-8, FR-9, FR-10, FR-23, FR-25, FR-29
- **Prevents:** steps appearing mid-run, two views of "what will run", plans that change on recovery or with a later repository edit, misordered rows
- **Rule:** `plan_run(template_version, inputs, Git) -> Plan{plan_ref, rows: [PlannedRow{seq, path, kind, gate, status, reason?, with_resolved}]}` is pure. It reads every `for_each` list file and callee version through `Git.read_file(ref, path)` / `Git.list_files(ref, prefix)` at `origin/{branch}` when the branch exists, else `origin/{base}`, records that SHA as `plan_ref`, resolves every `{{…}}` from the entity snapshot into `with_resolved`, and expands the pinned tree into rows in traversal order with a dense integer `seq`. A `template` call is a path segment, not a row; `pause_before_item_when` / `pause_after_item_when` become rows of kind `checkpoint` (gate `human`) at `…stories[n].before` / `…stories[n].after`; a `shell` whose resolved command is empty is planned `skipped · no command`; a Story whose file is already `done` at `plan_ref` has its frame planned `skipped · already done` unless the Run input `re_review_done` is true. `create_run` persists the rows as `step_run` in one transaction before `engine.enqueue`; pre-flight renders the same `plan_run` output without persisting; a plan-time error is a 422 naming template, version, line and item index. The walker executes only existing rows in `seq` order; `path` is the human key. Re-execution is a new `attempt` on the same row, never a new row. PRD `dev-loop` is `initiative@1 → epic@1 → story@1`; the Run input "epics file" is `{initiative_folder}/epics.yaml` (the outer list file); `epics.md` is not read.

### AD-8 — One writer per transition: `apply_step_result` for execution, `signal_run` for the operator

- **Binds:** FR-10, FR-16..FR-20, NFR-2
- **Prevents:** routers, executors, the walker, adapters or the UI mutating status; double writes on park; a second status machine in the UI
- **Rule:** `run`, `step_run`, `attempt`, `gate_record` change only through repository ports, in one unit of work per use case, opened by the engine adapter for the step (`SQLAlchemyDatasource`) or by the router for a request. Exactly one use case, `apply_step_result(run_id, seq, StepResult)`, applies every execution transition; the walker calls it inside the engine step that ran the row; step executors return results and never touch status fields. A `StepResult.park` makes it write `run.status = needs_you`, `run.park_kind`, `run.park_path` and one `gate_record` together; it is a logged no-op when `run.status ≠ running` (a cancelled Run absorbs late results). Any exception escaping an executor is caught by the walker inside the same step and applied as row `error` (reason `internal: {exception class}`) with `park_kind = internal`. `signal_run(run_id, Signal)` owns every operator transition on the Run and the re-queue of the target row (`run.park_path`): it validates the signal against the current status (409 otherwise), appends the `gate_record`, applies the transition, clears `park_*`, then calls `engine.signal`; the walker on wake only reads. `continue` on a `checkpoint`-kind row moves it to `done`, on an `agent` row to `queued` — the only kind test outside `application/steps/`. Every Run transition appends a `gate_record`; `gate_record.event` is the `Park.kind` for machine stops, the `Signal.kind` for operator actions, plus `start`, `done`, `failed`, `cancelled`. The UI renders stored tokens; the only derived token is the group status of AD-15.

```mermaid
stateDiagram-v2
  direction LR
  [*] --> queued: create_run
  queued --> running: walker starts
  running --> needs_you: park
  needs_you --> running: answer / continue / retry / skip_story / skip_epic / budget_raise / terminal_resume
  running --> done: last row done or skipped
  running --> failed: baseline fail / on_fail fail
  needs_you --> cancelled: cancel
  running --> cancelled: cancel
  queued --> cancelled: cancel
```

```mermaid
stateDiagram-v2
  direction LR
  [*] --> planned: plan_run
  [*] --> skipped: no command / already done
  planned --> queued: predecessor done or skipped
  planned --> skipped: skip_story / skip_epic / cancel
  queued --> running: attempt starts
  running --> done
  running --> blocked: agent status blocked
  running --> checkpoint: checkpoint row / ready-for-dev + spec_checkpoint
  running --> error: expect miss / exit≠0 / timeout / protected path / internal
  error --> queued: template retry (bounded) / retry signal
  done --> queued: on_fail redispatch (bounded)
  blocked --> queued: answer
  checkpoint --> queued: continue (agent row)
  checkpoint --> done: continue (checkpoint row)
  blocked --> skipped: skip_story
  checkpoint --> skipped: skip_story
  error --> skipped: skip_story
```

### AD-9 — Every step kind is one module behind one protocol; executors are pure over ports; re-execution is bounded by the pinned template

- **Binds:** FR-5, FR-9, FR-10, FR-11, FR-14, FR-15, FR-16, FR-17; GUIDELINES §8
- **Prevents:** kind-specific branches scattered through the walker, adapters or UI; silent re-enqueue
- **Rule:** `application/steps/<kind>.py` implements `StepExecutor.execute(ctx: StepContext) -> StepResult` for exactly one kind. `StepContext` = `{row, with_resolved, cwd = run.worktree_path, frame_start_sha, resume_signal: GateRecord | None, ports}`; `StepResult` = `{status, gate, output_ref, park: Park | None, redispatch: Redispatch | None}`. The registry in `application/steps/__init__.py` is the only enumeration of kinds; the validator, planner, graph builder and walker read it. Every worktree side effect of a signal (Answer archive + `## Human Answer`, Retry de-ambiguation archive, skip commit message) is performed by the resumed row's executor reading `resume_signal`, inside the engine step. Bounded automatic re-execution exists only as `retry {max, prompt}` (expect miss, same row) and `on_fail.redispatch {max}` (verify failure → append `## Verify Failure`, set `in-progress`, new attempt on the target row); each is a recorded `attempt` + `gate_record`, counted on `step_run.retry_count` / `redispatch_count`; exhaustion parks the Run; a redispatch whose target row is `skipped` is applied as `escalate` with reason `re-baseline failed after skip`. `blocked`, budget, timeout, protected-path, internal and configuration failures are never re-executed automatically. `compose_prompt` in `steps/agent.py` is the only prompt builder; adapters pass it verbatim.

### AD-10 — Harness adapters implement one port, read only environment names from config, never read model output, and are enabled only after a readiness run

- **Binds:** FR-14, FR-16, FR-17, FR-21; GUIDELINES §1.6
- **Prevents:** per-harness result parsing; harness flags in application code; per-Run values in shared config files; an unproven harness offered in New workflow
- **Rule:** `domain/ports/harness.py`: `Harness{name, capabilities{preassign_session, resume, native_tracing}, run(cwd, prompt, env, model, session_id?) -> HarnessResult, resume(cwd, session_id, message, env), resume_command(cwd, session_id)}`. One adapter per harness in `infrastructure/harness/<name>/adapter.py`. Static config under `AGENT_HOME` is written only by `scripts/harness/<name>.sh` (`install` at image build, `configure` at container start) and references environment variable *names* only (Codex `env_http_headers`, OpenCode `{env:NAME}`, Claude `ANTHROPIC_CUSTOM_HEADERS` from env); adapters write nothing under `AGENT_HOME`. `scripts/harness/_common.sh` declares `HARNESS_ENV_CONTRACT` = `{ORCH_RUN_ID, ORCH_ATTEMPT_ID, ORCH_STORY_ID, ORCH_HARNESS, ORCH_PROJECT, TRACEPARENT, LITELLM_BASE_URL, LITELLM_API_KEY, LANGFUSE_*, ORCH_LOG_CONTENT}` and `env_for(attempt)` populates exactly that list plus the Project's env vars. The container is the sandbox: Codex runs `danger-full-access`, Claude `dontAsk` with `CLAUDE_ALLOWED_TOOLS`, OpenCode config-driven permissions. Adapters return `HarnessResult{session_id, exit_code, usage, log_path}` and nothing interpreted. `resume` is used only by `retry` on the same row; no row ever resumes another row's session. A harness is `enabled` only after `story@1` reaches `done` on `fixtures/readiness-repo/` **and** `Gateway.spend_for_attempt` returns a non-empty result for that attempt; the Claude adapter additionally passes `--max-budget-usd` = remaining budget.

### AD-11 — One Run, one Langfuse session; parented where the harness allows; every model call attributable to its attempt

- **Binds:** FR-17, FR-26, FR-27, FR-28, NFR-5
- **Prevents:** runs split across unlinked traces; two exporters per harness; spend that cannot be summed per Run or per attempt
- **Rule:** `create_run` creates the Run trace via the `Tracer` port (Langfuse SDK, `trace_id = create_trace_id(seed=run_id)`, `session.id = run_id`, tags `run:`, `project:`) and stores `run.trace_id`. Each attempt runs inside a child span whose W3C `TRACEPARENT` is exported into the harness env. `claude` and `codex` export native OTLP to Langfuse and parent under it; `local` (OpenCode) uses the Langfuse plugin (`LANGFUSE_BASEURL`, `LANGFUSE_USER_ID = run_id`) and is found by user id. Every gateway request carries, from `env_for(attempt)` through the harness's env-name header mechanism, `langfuse_session_id: <run_id>` + `langfuse_tags: [run:, attempt:, story:, harness:, project:]` (traces) and `x-litellm-end-user-id: <run_id>` + `x-litellm-session-id: <attempt_id>` + `x-litellm-tags: run:,attempt:,story:,harness:,project:` (spend logs; all recorded by the open-source proxy). `Gateway.spend_for_attempt(run_id, attempt_id) -> AttemptSpend{usd, tokens_in, tokens_out}` reads `GET /spend/logs/v2?end_user=<run_id>&session_id=<attempt_id>` and sums; it is called after every `agent` attempt, before verify, writes `attempt.cost_usd`/tokens, and `run.spend_usd` is the sum over attempts; `spend_usd > budget_usd` parks the Run with `park_kind = budget` while the row keeps its routed status. A harness has exactly one exporter. Cost per path is a SQL sum of `attempt.cost_usd` over the path prefix.

### AD-12 — Repository lock is the queue partition [ADOPTED]

- **Binds:** FR-13, FR-25
- **Prevents:** a separate lock table, lock release on park
- **Rule:** `engine.enqueue(run_id, partition_key=repository_id)` on one queue with global concurrency 2 and partition concurrency 1. The lock is held for the Run's whole life, including `needs_you`. `use_cases/queue.list_queue()` joins `engine.list_queue()` with `run` and returns the FR-25 row with `reason ∈ {repository lock held by {run}, global concurrency, running, waiting for your answer}`; there is no queue state table. Pre-flight names the holding Run.

### AD-13 — Signals are an enumerated contract that writes the database; worktree effects happen in the resumed step, except cancel

- **Binds:** FR-16..FR-21
- **Prevents:** endpoints that talk to the engine directly; side effects done twice or never; ad-hoc resume paths; orphaned worktrees and processes
- **Rule:** A use case never blocks; it returns `Park(reason, kind ∈ {blocked, checkpoint, verify_failed, budget, timeout, push_rejected, protected_path, misconfigured, internal})` and the engine adapter waits with a single `recv` on `human:{run_id}` (30 days). Routers call `signal_run(run_id, Signal)`:

| `Signal.kind` | Valid when | `signal_run` writes | Effects in the resumed engine step | Row transition |
| --- | --- | --- | --- | --- |
| `answer {text}` | `park_kind = blocked` | gate_record with text | executor archives the Story file to `stories/.answers/{id}-attempt-{n}.md` with `## Human Answer`, then first-dispatches with the Answer suffix | `blocked → queued` |
| `continue` | `park_kind = checkpoint` | gate_record | `agent` row: re-dispatch without the halt suffix; `checkpoint` row: none | `checkpoint → queued` / `→ done` |
| `retry` | `park_kind ∈ {timeout, push_rejected, misconfigured, internal, verify_failed}` or row `error` | gate_record | executor archives all-but-newest ambiguous files, then re-runs | `error → queued` |
| `skip_story` | `park_kind ∉ {budget}` and `park_path` inside a story frame | gate_record; every non-terminal `agent`/`checkpoint` row of the innermost `…stories[n]` frame `→ skipped (skipped by operator)`; the frame's `git.commit` message re-resolved to `story {id}: skipped by operator` | the frame's `verify` row runs as the re-baseline, then `git.commit` | as stated |
| `skip_epic` | as `skip_story` | same over the innermost `epics[i]` frame including its `git.push` / `pr.link`; the current story's `git.commit` row stays planned | commit-guard runs, then the next epic | as stated |
| `budget_raise {budget_usd}` | `park_kind = budget` and `budget_usd > spend_usd` | `run.budget_usd`, gate_record | none | none; the walker continues at the first row not `done \| skipped` |
| `cancel` | any non-terminal | gate_record; `ProcessRunner.kill_group(attempt.pgid)`; `engine.cancel`; for each `run.worktrees[]`: `Git.remove_worktree`, `Git.delete_branch` when `created_branch and not pushed` | none (the walker's late result is absorbed) | `planned/queued → skipped`, Run `→ cancelled` |
| `terminal_release` | `terminal_session` | `terminal_session = false`, gate_record | none | none |
| `terminal_resume` | sent by the scheduled job `terminal_poll` after two consecutive clean `done` polls | as `continue` on the frame's `verify` row | verify runs | `→ queued` |

`PUT /runs/{id}/files` (spec folder only, `needs_you` and not `terminal_session`) commits the edit immediately as `spec: operator edit (orchestrator)`; it and `cancel` are the only worktree writes outside an engine step. `terminal_poll` runs every 30 s over Runs with `terminal_session and status = needs_you`.

### AD-14 — All filesystem, git and process side effects go through three ports; one worktree per (Run, branch) [ADOPTED]

- **Binds:** FR-4, FR-9, FR-11, FR-12, FR-15, FR-16, FR-18..FR-20, FR-23, NFR-3
- **Prevents:** shell strings or file I/O in use cases; a harness inheriting the orchestrator's environment; orphaned worktrees when an initiative spans branches
- **Rule:** `Git` port (`ls_remote`, `read_file(ref, path)`, `list_files(ref, prefix)`, `branch_exists`, `clone_base`, `worktree_add`, `sync`, `status`, `diff_names(from_sha)`, `commit`, `push`, `remove_worktree`, `delete_branch`), `Workspace` port (`read`, `write`, `glob`, `exists`, `move`, `tree` — rooted at the Run's current worktree, unavailable before the first `git.worktree` row, path traversal rejected) and `ProcessRunner` port (`start(cmd, cwd, env, timeout_min) -> {pid, pgid}`, `wait`, `kill_group(pgid)`); the `ProcessRunner` enforces `timeout_min` (kill group → row `error`, reason `timeout {path} after {n} min`), the engine never times a step. Base clones live at `/work/{project}/{repo}/base`, worktrees at `/work/{project}/{repo}/wt/{branch}`, logs at `/work/logs/{run_id}/`, all on the named volume `work`. `git.worktree` adds or reuses `wt/{branch}` (reuse when clean, refuse when dirty), appends `{branch, path, created_branch, pushed: false}` to `run.worktrees[]` if absent, and sets `run.worktree_path` to it; `git.push` sets `pushed` on the matching entry and refuses `branch == repository.default_branch`; `pr.link` appends to `run.compare_urls[]`; pre-flight refuses when any branch the plan checks out is held by a worktree of a non-terminal Run. `repository.clone_check` is written only by `use_cases/projects.run_clone_check` (project save, `POST /repositories/{id}/clone-check`, scheduled job `clone_check`); `create_run` returns 409 while it is `failed`; pre-flight's `origin reachable` reads `Git.ls_remote` and writes nothing. Every harness process starts in its own session/process group with the AD-10 env; `attempt.pgid` is recorded before the process is awaited; a re-attempt first kills the recorded group and waits for `.git/index.lock` to vanish. Scheduled jobs: `clone_check` (daily), `worktree_gc` (removes worktrees and logs of terminal Runs after 7 days, iterating `run.worktrees[]`), `terminal_poll` (30 s).

### AD-15 — Templates are immutable versions validated by one function; variables do not inherit; the graph is computed once

- **Binds:** FR-5, FR-6, FR-7, FR-29
- **Prevents:** a second parser in TypeScript; a Run resolving a changed callee; a callee reading its caller's scope; graph nodes that do not join to rows
- **Rule:** `application/templates/validate.py` is the single parser/validator and implements exactly the "Template DSL v1 keys" table in the Structural Seed: unknown keys, unbound variables, unknown kinds, nested or multiple `for_each` per file, expressions beyond the grammar, cycles, depth > 3, callee input name/type mismatches, non-literal `version`, `parallel`, `timeout_min`/`on_fail` on `template` are rejected; a missing `gate` is reported as `unvalidated`. Errors carry `{template, version, line, reason}`. A callee sees only its declared `inputs`; item bindings are inputs of type `item`; entity inputs expose a fixed field whitelist (`project.name`, `repository.url | default_branch | install_command | quality_gate_command | unit_test_command`). `POST /templates/{name}/validate`, `plan_run` and `application/graph.py` call it. Saving creates version n+1; a version pinned by any Run, directly or as a callee, is frozen. `graph.py` produces `{nodes, edges, groups, statuses?}` for `GET /templates/{name}/{v}/graph` (node id = template-relative path without indices, e.g. `stories.story.build`; callee calls collapsed) and `GET /runs/{id}/graph` (node id = `step_run.path`, group id = path prefix); group status is computed only there by one rule — `error | blocked | checkpoint` if any row is; else `running` if any; else `done` when all are `done | skipped`; else `queued | planned`. web-client lays out with `@dagrejs/dagre` and renders SVG, read-only.

### AD-16 — BMAD lives in the image and in `_bmad/`; skill folders are never committed

- **Binds:** FR-8, FR-14, FR-15
- **Prevents:** per-run installs; skill folders in target repositories; version skew between skills and scripts
- **Rule:** The backend-api image pins one `bmad-method` version and copies the skill stubs into `~/.claude/skills` and `~/.agents/skills` (read by claude / codex+opencode); a target repository commits `_bmad/` (config, scripts, `custom/`) and its spec folders only, and git-ignores `.claude/skills/bmad-*` and `.agents/skills/bmad-*`. Pre-flight requires `_bmad/` at `plan_ref` with `_bmad/_config/manifest.yaml` version equal to `BMAD_VERSION`. The shipped template `repo-init@1` initialises or updates a repository (worktree `chore/bmad-init` → `bmad.install` → gitignore → commit → push → compare link).

### AD-17 — Frozen anchors are checked deterministically after every agent attempt, against a SHA taken after the WIP commit

- **Binds:** FR-10, FR-16, NFR-2; GUIDELINES §2.5.2, §2.5.4
- **Prevents:** an agent editing the spec, the constitution or existing tests to make a gate pass; operator edits false-parking; a vacuous commit-guard check
- **Rule:** Protected paths per Run: `{spec_folder}/SPEC.md`, `{spec_folder}/stories.yaml`, `{initiative_folder}/epics.yaml`, every `AGENTS.md`, and every *existing* file matching `repository.test_globs` (default `tests/**`, `**/*.test.*`, `**/*.spec.*`; additions allowed, modifications and deletions not). `attempt.start_sha` is HEAD *after* the WIP commit; before making that commit the `agent` executor checks `Git.diff_names(previous_attempt.start_sha)` and attributes a hit to the previous attempt. `rules/protected_paths.check` runs in the `agent` executor after the harness exits and before routing (hit → `status: error, park: protected_path`), and in the `git.commit` executor against `ctx.frame_start_sha` (the frame's latest `agent` attempt's `start_sha`, else HEAD). A hit is never re-executed automatically.

### AD-18 — Tests are layered, fakes are shared, and the gates are checkable

- **Binds:** all epics; GUIDELINES §1.6, §1.7, §5
- **Prevents:** unit tests needing Postgres or a harness; each epic inventing its own doubles; E2E suites coupled to each other; a "TDD" rule nobody can check
- **Rule:** Backend unit tests use only in-memory implementations of the ports, one fake per port in `tests/unit/fakes/`, and drive use cases directly. `tests/e2e/` hits a running compose stack over HTTP (httpx scenarios + Schemathesis from `/openapi.json`). web-client: Vitest for units, Playwright in `tests/e2e/` against `astro preview` with backend-api stubbed by route handlers or the real stack (`E2E_BACKEND=real`). Checkable gates: every `src` module has a test module; `domain/` and `application/` rules (`rules/`, `steps/agent.py`, status machines, `signal_run`, `apply_step_result`) have 100 % branch coverage; changed lines ≥ 90 % covered; CI order lint → unit → e2e-api → e2e-ui. "Tests first" is the working convention of `bmad-build-auto`, stated in AGENTS.md and reviewed, not machine-enforced.

### AD-19 — Trajectory capture is a table, written once per done Story

- **Binds:** FR-16, FR-28; GUIDELINES §10
- **Prevents:** a filesystem write path; records edited later
- **Rule:** When a Story's `build` row is `done` and its `verify` row is `done` or `skipped`, `record_trajectory` inserts one append-only `trajectory` row (run, story, harness, model, agent attempts, gate results, cost, story-file snapshot, start SHA → end SHA). `GET /projects/{id}/trajectories.jsonl` exports; nothing updates or deletes rows.

### AD-20 — Configuration is the environment; `.env.example` is its contract

- **Binds:** NFR-4, NFR-7; every deploy
- **Prevents:** config files with divergent keys per component; secrets in compose files
- **Rule:** Both components read configuration only from environment variables through one typed settings module (`pydantic-settings` / `astro:env`). `.env.example` at the repo root lists every variable with a comment; adding a variable without updating it fails `make lint`. Harness config files under `AGENT_HOME` are generated by `scripts/harness/<name>.sh configure` from the same variables at container start, never edited by hand. Host-side LiteLLM (`model_list`, `LITELLM_OTEL_V2=true` + `langfuse_otel` callback, local models as `openai/<alias>` with `use_chat_completions_api: true`) and oMLX are documented in `host/README.md` + `host/litellm.config.yaml`, outside compose.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Routes | `/api/v1/<feature>` per feature router: `auth`, `projects`, `repositories`, `templates`, `runs`, `steps`, `queue`; `/healthz`, `/openapi.json` unversioned. Actions on a Run: `POST /runs/{id}/signals {kind, payload}` (AD-13). Worktree files: `GET /runs/{id}/files?path=`, `PUT /runs/{id}/files`. Activity: `POST /runs/{id}/activity {focused_seconds}` batched every 60 s into `run.active_seconds`, `run.last_opened_at`. |
| Read models | Every screen reads one endpoint shaped for it (`GET /runs?view=board`, `GET /runs/{id}` with steps, stories strip, cost block, gate record, worktrees, compare URLs; `GET /queue`; `GET /steps`); the UI performs no joins or aggregation across endpoints. |
| Ids & keys | UUIDv7 (`uuid.uuid7()`) for every entity; `step_run.seq` orders, `step_run.path` names; engine ids only inside `engine_ref`. |
| Dates & money | ISO 8601 UTC with `Z`; DB `timestamptz`. Money `numeric(12,6)` USD, JSON as string; tokens as integers; local models cost `0` with tokens. |
| Errors | RFC 9457 `application/problem+json` `{type, title, status, detail, instance, errors?}`; validation errors list `{template?, version?, line?, path?, reason}`; 401 bad token, 409 signal invalid for the current status or clone check failed, 422 validation and plan-time errors. |
| Form errors (web-client) | Actions return `ActionError` carrying the problem body; the page re-renders with every submitted value and prints `detail` verbatim plus `errors[]` beside the field named by `path`; no toast, no redirect on error. |
| Lists | `{items: [...], next_cursor: str \| null}`; filters as query params; no envelopes elsewhere. |
| Status tokens | Run `queued running needs_you done failed cancelled`; Step `planned queued running done blocked checkpoint error skipped`; UI tokens `QUE RUN BLK CHK DON ERR CAN SKP`; `needs_you` renders `BLK` or `CHK` from `run.park_kind`. `skipped`, `unvalidated`, `liveness` are words; only `deterministic` or `human` gates may render green. |
| Template variables | `{{name}}` / `{{name.field}}` substitution only; `inputs` are the whole scope of a template; conditions (`pause_*_when`, `escalate_when`) are a single item field or `output.status == <token>`. |
| Naming | Python `snake_case`, modules singular by concept; TypeScript `camelCase`, components `PascalCase.tsx` in `src/islands/` (interactive) and `src/components/` (Astro, static); stores in `src/stores/`; step kinds dotted lowercase. |
| Logging | `structlog` JSON to stdout; every line inside a Run carries `run_id`, `path`, `attempt`; harness stdout/stderr to `attempt.log_path`. |
| Time | `Clock` port in domain; no `datetime.now()` outside infrastructure. |
| Front-end data | Islands poll through the Astro proxy on a single `nanostores` interval store (5 s while any Run is running, else 30 s); state swap without animation; a failed fetch renders the full-surface readout with the failed request and a retry control (FR-24). |
| UI signal & voice | NFR-6/NFR-8 as written, plus: exactly one element per card or row carries a signal colour (green running, amber needs you, red failed); a screen with nothing needing the Operator has no amber or red pixel; copy names the mechanism whenever an action changes a file or branch. Visual tokens: `DESIGN.md`; surfaces: `EXPERIENCE-v1.md`. |
| Front-end auth | Cookie `orch_session`, signed with `ORCHESTRATOR_SESSION_SECRET`; middleware `src/middleware.ts` guards every page except `/login`. |
| Commits & branches | Conventional commits; orchestrator commits `story {id}: {title} (orchestrator)`, `story {id}: skipped by operator`, `wip: story {id} attempt {n} (interrupted)`, `spec: operator edit (orchestrator)`; repo-init branch `chore/bmad-init`. |
| Terminal resume | `docker compose exec backend-api <harness resume …>`. |
| Environments | One environment: the Mac mini compose stack. Local development is the same compose file with `.env` pointing LiteLLM and Langfuse at `localhost`. |
| Operations | Nightly `pg_dump` of the whole database (schemas `public` + `dbos` together) by a host cron to `host/backups/`, 14 days kept; `work` logs and worktrees removed by `worktree_gc`; `agent-home` is not backed up (sessions may be lost, PRD §5). Migrations run at container start (`alembic upgrade head`) before `DBOS.launch()`. |
| Code quality | Python: ruff (lint+format), mypy strict on `domain/` and `application/`, import-linter; TypeScript: eslint (+ the AD-1 restrictions) + prettier + `tsc --noEmit` + `astro check`; both in `make lint`. |

## Stack

| Name | Version |
| --- | --- |
| Python | 3.14 |
| uv | 0.12.9 |
| FastAPI | 0.141.1 |
| Pydantic / pydantic-settings | 2.13.5 / 2.15.0 |
| SQLAlchemy / psycopg / Alembic | 2.0.52 / 3.3.5 / 1.19.1 |
| dbos | 2.31.0 |
| langfuse (Python SDK) | 4.15.1 |
| structlog / PyYAML / cryptography | 26.1.0 / 6.0.3 / 50.0.1 |
| pytest / pytest-asyncio / pytest-cov / httpx / schemathesis | 9.1.1 / 1.4.0 / 7.1.0 / 0.28.1 / 4.25.2 |
| ruff / mypy / import-linter | 0.16.5 / 2.3.1 / 2.14 |
| Node.js / pnpm | 24 (LTS line, image `node:24-bookworm-slim`) / 11.25.0 |
| Astro / @astrojs/node / @astrojs/react / @astrojs/check | 7.2.10 / 11.1.5 / 6.0.5 / 0.9.10 |
| React / nanostores / @nanostores/react | 19.2.8 / 1.5.2 / 1.1.0 |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 |
| @codemirror/state / view / lang-yaml | 6.7.2 / 6.43.10 / 6.1.3 |
| @dagrejs/dagre | 3.1.1 |
| Vitest / @playwright/test | 4.1.11 / 1.62.1 |
| PostgreSQL | 18 (image `postgres:18`) |
| LiteLLM (host) / Langfuse (host) | 1.99.0 / v4.27.0 |
| @langfuse/opencode-observability-plugin | 0.3.0 |
| bmad-method | 6.11.0 |
| Claude Code / Codex CLI / OpenCode | 2.1.258 / 0.152.1 / 1.18.26 |
| Docker base images | python:3.14-slim-trixie, node:24-bookworm-slim |

## Structural Seed

```mermaid
graph LR
  browser[Operator browser] -->|orch_session cookie| web[web-client<br/>Astro 7 on Node 24]
  web -->|Bearer ORCHESTRATOR_TOKEN<br/>/api/v1| api[backend-api<br/>FastAPI + DBOS walker + harnesses]
  api --> pg[(PostgreSQL 18<br/>public + dbos schemas)]
  api -->|subprocess, HARNESS_ENV_CONTRACT| h[claude · codex · opencode]
  h -->|langfuse_* and x-litellm-* headers| litellm[LiteLLM · host]
  litellm --> prov[Anthropic · OpenAI · oMLX]
  h -->|OTLP or plugin| lf[Langfuse · host]
  api -->|OTLP spans| lf
  litellm -->|langfuse_otel| lf
  api -->|https, GITHUB_TOKEN per command| gh[GitHub]
```

```mermaid
graph TB
  subgraph host [Mac mini host]
    litellm[litellm :4000]
    langfuse[langfuse :3000]
    omlx[oMLX :8000]
    backups[(host/backups nightly pg_dump)]
    subgraph compose [docker compose — non-root, cap_drop ALL, no-new-privileges]
      web[web-client :4321]
      api[backend-api :8000]
      pg[(postgres :5432)]
      work[(volume work: base, wt, logs)]
      home[(volume agent-home)]
    end
  end
  web --> api
  api --> pg
  pg --> backups
  api --- work
  api --- home
  api -->|host.docker.internal| litellm
  api -->|host.docker.internal| langfuse
  litellm --> omlx
```

```mermaid
erDiagram
  PROJECT ||--o{ REPOSITORY : has
  PROJECT ||--o{ RUN : scopes
  REPOSITORY ||--o{ RUN : targets
  TEMPLATE_VERSION ||--o{ RUN : pins
  TEMPLATE_VERSION }o--o{ TEMPLATE_VERSION : calls
  RUN ||--o{ STEP_RUN : plans
  STEP_RUN ||--o{ ATTEMPT : executes
  RUN ||--o{ GATE_RECORD : records
  RUN ||--o{ TRAJECTORY : yields
```

Fields that carry an invariant (other fields follow the PRD glossary): `project.env_vars_enc`, `log_prompt_content` (AD-5); `repository.default_branch`, `install_command`, `quality_gate_command`, `unit_test_command` (stored, unused), `test_globs`, `clone_check{status, at, output}` (AD-14, AD-17); `template_version.yaml`, `hash`, `calls[]`, frozen once pinned (AD-15); `run.engine_ref`, `plan_ref`, `worktree_path` (current), `worktrees[]{branch, path, created_branch, pushed}`, `compare_urls[]`, `trace_id`, `budget_usd`, `spend_usd`, `manual_estimate_h` (immutable after start), `park_kind`, `park_path`, `terminal_session`, `re_review_done`, `active_seconds`, `last_opened_at` (AD-6, AD-7, AD-11, AD-13, AD-14); `step_run.seq` (dense, orders), `path` (unique per Run), `kind`, `gate`, `status`, `reason`, `with_resolved`, `retry_count`, `redispatch_count` (AD-7..AD-9); `attempt` — one per execution of any row — `n`, `started_at`, `ended_at`, `status`, `engine_ref`, `start_sha`, `log_path`, and for `agent` rows `harness`, `model`, `session_id`, `pgid`, `exit_code`, `tokens_in/out`, `cost_usd` (AD-10, AD-11, AD-14, AD-17); `gate_record.event` (AD-8); `trajectory` append-only (AD-19).

**Template DSL v1 keys** (the set `validate.py` accepts):

| Level | Key | Type | Notes |
| --- | --- | --- | --- |
| template | `name`, `version`, `description`, `inputs`, `steps` | string, int literal, string, map, list | `inputs.<name>: {type: project \| repository \| string \| path \| enum \| number \| item, required?, default?, values?}` |
| step | `id`, `uses` xor `run`, `with`, `gate`, `timeout_min`, `on_fail` | slug, kind / command string, map, `liveness \| deterministic \| human`, int, `escalate \| fail \| continue \| {redispatch, max}` | `gate` missing → `unvalidated`; `timeout_min`, `on_fail` rejected on `template` |
| step `uses: agent` | `expect {files: [glob], status_in: [token]}`, `retry {max, prompt, resume_session?}`, `escalate_when`, `pause_when` | | each `files` glob must match exactly one file; `resume_session` defaults true and falls back to a new session when the harness lacks `resume` |
| step `uses: template` | `with {name, version, inputs}` | | callee inputs checked by name and type |
| for_each | `for_each`, `as`, `steps`, `pause_before_item_when`, `pause_after_item_when`, `parallel` | list-file path, name, list, item field, item field, rejected | one per file, no nesting |

**Shipped kinds** (`application/steps/`):

| Kind | Gate | Default `timeout_min` | Behaviour |
| --- | --- | --- | --- |
| `git.worktree` | deterministic | 5 | AD-14; runs `install_command` when declared |
| `git.sync` | deterministic | 5 | fetch + `pull --ff-only` |
| `shell` (`run:`) | deterministic | 30 | command in the worktree with the Project env; empty → planned `skipped` |
| `agent` | liveness | 90 | WIP commit → protected-path check of the previous attempt → `project-context.md` → `compose_prompt` → dispatch → protected-path check → FR-16 routing → `Gateway.spend` → budget rule |
| `git.commit` | deterministic | 5 | commit-guard (spec folder staged first), `frame_start_sha` protected-path check |
| `git.push` | deterministic | 5 | refuses default branch; rejected push → park `push_rejected` |
| `pr.link` | liveness | 5 | compare URL appended to `run.compare_urls[]` |
| `checkpoint` | human | — | parks `checkpoint`; `continue` → `done` |
| `template` | — | — | path segment; not a row |
| `bmad.install` | deterministic | 30 | `npx bmad-method@$BMAD_VERSION install --yes --directory <worktree>` + gitignore lines |

```text
ai-orchestrator/
  AGENTS.md                      # constitution for agents working on this repo
  Makefile                       # test · e2e-api · e2e-ui · lint · openapi · up · down
  docker-compose.yml             # web-client, backend-api, postgres; volumes work, agent-home; hardening flags
  .env.example                   # every variable of both components (AD-20)
  contracts/openapi.json         # exported by backend-api, consumed by web-client (AD-3)
  templates/                     # shipped Template YAML: repo-init.yaml, story.yaml, epic.yaml, initiative.yaml
  scripts/harness/{_common,claude,codex,opencode}.sh   # install · configure · doctor per harness (AD-10, AD-20)
  fixtures/readiness-repo/       # one-story repository used by the harness readiness run (AD-10)
  host/                          # README.md, litellm.config.yaml, backups/ (AD-20, Operations)
  backend-api/
    AGENTS.md
    Dockerfile                   # python:3.14-slim + uv + node 24 + git/gh + claude/codex/opencode + bmad-method; non-root `agent`
    pyproject.toml               # deps, ruff, mypy, import-linter contracts
    alembic/
    src/orchestrator/
      domain/                    # entities, statuses, ports/{engine,harness,git,workspace,process,gateway,tracer,clock,repositories}.py
      application/               # use_cases/{create_run,plan_run,apply_step_result,signal_run,preflight,projects,templates,queue,record_trajectory}.py
                                 # steps/<kind>.py, templates/{validate,plan}.py, graph.py, rules/{routing,budget,protected_paths}.py
      api/                       # routers/<feature>.py, schemas/, deps.py (bearer auth)
      infrastructure/            # dbos/, db/, git/, workspace/, process/, harness/<name>/, gateway/, tracing/, crypto/, settings.py
      main.py
    tests/unit/{fakes,domain,application,api}/
    tests/e2e/
  web-client/
    AGENTS.md
    Dockerfile                   # node:24 build → astro node standalone
    astro.config.mjs             # output: 'server', adapter node standalone, react()
    src/pages/                   # login, index (board), runs/[id], runs, projects, templates
    src/pages/api/[...path].ts   # proxy → backend-api with bearer (AD-1)
    src/middleware.ts            # cookie guard
    src/actions/                 # form posts
    src/islands/                 # Board, RunDetail, RunDiagram, TemplateEditor, ProjectForm, NewWorkflow (React)
    src/components/              # static Astro components (instrument-dark tokens)
    src/stores/                  # nanostores: polling, session, filters
    src/api/{schema.d.ts,client.ts,server.ts}
    tests/unit/  tests/e2e/
```

| Variable | Used by | Meaning |
| --- | --- | --- |
| `ORCHESTRATOR_TOKEN` | both | the one credential (AD-4) |
| `ORCHESTRATOR_SESSION_SECRET` | web-client | cookie signing key |
| `ORCHESTRATOR_SECRET_KEY` | backend-api | Fernet key for Project env vars |
| `BACKEND_API_URL` | web-client (server) | `http://backend-api:8000` |
| `DATABASE_URL` | backend-api | `postgresql+psycopg://…` (app + DBOS system DB) |
| `DBOS_APPLICATION_VERSION` | backend-api | pinned walker version (AD-6) |
| `GITHUB_TOKEN` | backend-api git only | push/clone (AD-5) |
| `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LOCAL_MODELS` | harness env, gateway adapter | gateway |
| `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_ENVIRONMENT` | backend-api, harness env (OpenCode plugin spells it `LANGFUSE_BASEURL`) | tracing (AD-11) |
| `BMAD_VERSION`, `CLAUDE_CODE_VERSION`, `CODEX_VERSION`, `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION` | image, pre-flight | pins (AD-16) |
| `CLAUDE_ALLOWED_TOOLS` | claude adapter | PRD §8 Q1 |
| `WORK_DIR` (`/work`), `AGENT_HOME` | backend-api | volumes |
| `LOG_PROMPT_CONTENT_DEFAULT`, `LOG_LEVEL` | backend-api | FR-2 default, logging |
| `LITELLM_OTEL_V2=true`, `LANGFUSE_*` | host LiteLLM | `langfuse_otel` callback (host/README.md) |

## Capability → Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| FR-1 token login | web-client `pages/login`, `middleware.ts`; backend `api/deps.py` | AD-1, AD-4 |
| FR-2..FR-4 projects, repositories, clone check, daily re-check | `use_cases/projects.py`, `infrastructure/git`, scheduled job `clone_check` | AD-5, AD-6, AD-14 |
| FR-5..FR-7 templates, versions, diagram | `templates/{validate,plan}.py`, `graph.py`; island `TemplateEditor` | AD-15, AD-9 |
| FR-8 pre-flight (origin, base, branch, held branches, stories parse + prefix-free ids, checkpoints, SPEC.md/epics, harness enabled, `_bmad/` version, existing story files, clone check), What will run, manual estimate immutable, queue position | `use_cases/preflight.py` (pure `plan_run`), `create_run` | AD-7, AD-10, AD-12, AD-14, AD-16 |
| FR-9..FR-11 checkout, install, baseline, loop, verify, commit-guard, push, compare link | `steps/*`, shipped templates | AD-7, AD-9, AD-14, AD-17 |
| FR-12 durability, WIP commit, orphan kill, internal errors | `infrastructure/dbos/walker.py`, `apply_step_result`, `steps/agent.py`, `ProcessRunner` | AD-6, AD-7, AD-8, AD-14 |
| FR-13 lock / queue | `engine.enqueue` partition, `use_cases/queue.py` | AD-12 |
| FR-14, FR-21 harness dispatch, readiness, resume command, terminal poll | `infrastructure/harness/<name>/`, `scripts/harness/`, `fixtures/readiness-repo/`, job `terminal_poll` | AD-10, AD-11, AD-13, AD-5 |
| FR-15 project context file | `steps/agent.py` via `Workspace` | AD-9, AD-14 |
| FR-16, FR-17 contract evaluation, ambiguous-file archive, budget halt | `steps/agent.py`, `rules/{routing,budget}.py`, `Gateway.spend_for_attempt` | AD-8, AD-9, AD-11 |
| FR-18..FR-20 answer, continue (incl. inline story edit), skip story/epic, retry, cancel | `use_cases/signal_run.py`; `POST /runs/{id}/signals`; `PUT /runs/{id}/files` | AD-13, AD-8, AD-9, AD-14 |
| FR-22..FR-24, FR-29 board, run detail, refresh, run diagram, active time | islands `Board`, `RunDetail`, `RunDiagram`; `GET /runs?view=board`, `GET /runs/{id}`, `GET /runs/{id}/graph`, `POST /runs/{id}/activity` | AD-1, AD-3, AD-15, conventions |
| FR-25 queue and history | `use_cases/queue.py`, `GET /steps` | AD-6, AD-12 |
| FR-26..FR-28 gateway, trace, cost per attempt | `infrastructure/{gateway,tracing}`, `env_for(attempt)` | AD-10, AD-11 |
| NFR-3, NFR-4 isolation, egress | Dockerfile non-root, compose hardening flags, `HARNESS_ENV_CONTRACT`; egress allowlist deferred | AD-5, AD-10, AD-14 |
| NFR-6, NFR-8 UI signal and voice | web-client components, copy | conventions |
| NFR-7 build size | compose + two Dockerfiles + `host/` | AD-20 |
| GUIDELINES anchors, trajectories, TDD | AGENTS.md ×3, `rules/protected_paths.py`, `trajectory` | AD-17, AD-18, AD-19 |

## Deferred

- **Per-repository GitHub tokens** — the Fernet column (AD-5) is where they land.
- **LiteLLM virtual keys / per-Project budgets** — tags carry attribution.
- **OpenCode trace parenting** — no inbound traceparent exists; user/session id only. The OpenCode v2 upgrade replaces the plugin path (`experimental.openTelemetry` is removed there).
- **Egress allowlist (NFR-4)** — compose hardening flags ship; the allowlist is a host firewall rule documented in `host/README.md`, not enforced by the MVP.
- **Parallel epics** — `parallel` rejected by the validator; needs a per-branch lock.
- **Per-step DBOS child workflows** — the port (AD-6) allows the adapter to switch without touching use cases.
- **Second backend container / shared `work` volume** — allowed by the adapter and volumes.
- **SSE instead of polling** — same endpoints; the `nanostores` interval store is the only place to change.
- **Notifications (Mattermost)** — a `gate_record` consumer.
- **Trajectory outcome rows** (merged / reverted signal of GUIDELINES §10) — needs a GitHub webhook or manual entry; the `trajectory` row already carries the SHAs to join on.
- **FR-1 lockout** — COULD; web-client middleware counter.
- **Astro Container API component tests** — experimental; unit-test islands with Vitest + React Testing Library instead.
- **Secret rotation** (`MultiFernet`) — single key now.
- **Visual template editor, multi-user, roles** — out of scope per PRD §5.

### Open at handoff

1. **Codex `TRACEPARENT`** is honoured in source, not documented. Day-1 check; fallback is the Langfuse Codex plugin with a seeded trace (flat), under AD-11's session floor.
2. **`DBOS.step_id` equals `operation_outputs.function_id`** is implied by the docs, not stated. Day-1 check; only the adapter depends on it.
3. **Claude tool allowlist** for `bmad-build-auto` under `dontAsk` (PRD §8 Q1) — `CLAUDE_ALLOWED_TOOLS`, resolved on day 3.
4. **Global skill stubs resolve the worktree as `{project-root}`** for each harness, and Codex `multi_agent` / OpenCode subagents satisfy `bmad-build-auto`'s subagent requirement — the readiness run (AD-10) decides; fallback: `git.worktree` copies the stubs into the worktree's git-ignored skill folders.
5. **Spend headers coexist with Langfuse headers.** `x-litellm-session-id` (attempt id, spend logs) and `langfuse_session_id` (run id, traces) are set together; the readiness run asserts the Langfuse session shows the Run id and `/spend/logs/v2` returns the attempt's rows. Fallback if they collide: drop `x-litellm-session-id` and sum by `request_tags @> '["attempt:<id>"]'` through `GET /global/spend/tags`.
