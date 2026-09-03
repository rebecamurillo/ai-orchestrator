---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/mvp/prd.md
  - _bmad-output/planning-artifacts/mvp/addendum.md
  - _bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/mvp/architecture/deliverables/ (AGENTS.md ×3, scripts/harness/*.sh, .env.example)
  - _bmad-output/planning-artifacts/mvp/template-dsl-draft.md
  - _bmad-output/planning-artifacts/ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
  - _bmad-output/planning-artifacts/ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md
  - GUIDELINES.md
---

# ai-orchestrator - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ai-orchestrator (MVP dev loop), decomposing the requirements from the MVP PRD (`mvp/prd.md`, FR-1..FR-33, NFR-1..NFR-9), the architecture spine (`mvp/architecture/ARCHITECTURE-SPINE.md`, AD-1..AD-20), and the v1 UX experience spec plus the instrument-dark visual system into implementable stories.

Tier per requirement comes from PRD §6.1: **M** = MUST, **S** = SHOULD, **C** = COULD.

**Execution model (confirmed 2026-09-02).** Epic 1 (repository setup and quality gates) is executed directly by a high-capability agent in a supervised session; its stories may be denser and carry spec checkpoints. Every later epic is built by Sonnet-class agents through `bmad-build-auto` in unattended mode: each story brief must be self-contained (rules inlined, sources cited only for detail), and checkpoints are declared only where a decision cannot be made unattended. Output layout: `mvp/epics/epics.yaml` (initiative list, one shared branch `feat/mvp`), one folder per epic with `SPEC.md`, `stories.yaml`, `briefs/<id>-<slug>.md`, and an empty `stories/` reserved for the dev agent.

## Requirements Inventory

### Functional Requirements

FR-1 [M; lockout C]: Token login — the access token sets a 30-day HttpOnly session cookie and redirects to the Board; every `/api/*` call requires the session (401 otherwise, page loads redirect to `/login`); wrong token shows `token rejected — n attempts left`; 5 failures in 15 min lock for 15 min (COULD).
FR-2 [M]: Create and edit a Project — name, context text, context file paths, agent env vars (Fernet-encrypted at rest, masked to last four chars on read, exported only into that Project's Runs); no GitHub token or Gateway key on a Project (instance settings, stated on screen); per-Project `log_prompt_content` switch defaulting to `LOG_PROMPT_CONTENT_DEFAULT`, with the statement that it sends source code to Langfuse.
FR-3 [M]: Register a Repository — URL, default branch, package manager, `test_globs` (default `tests/**`, `**/*.test.*`, `**/*.spec.*`, shown and extendable), optional `install_command`, `quality_gate_command`, `unit_test_command`; a Repository without `quality_gate_command` saves and its row says `verify step will be skipped`.
FR-4 [M on save; daily re-check C]: Clone check — on Project save, per Repository: `git ls-remote`, shallow clone into `/work/{project}/{repo}/base`, default branch exists; each line `ok` + duration or verbatim output; a failure stores status `failed` with the output, does not block the save, blocks new Runs on that Repository until a check passes; re-run from the row; daily re-check (COULD); GitHub token supplied per git command, never stored or written to a Worktree.
FR-5 [M]: Template schema and validation — DSL v1 (inputs `project | repository | string | path | enum | number | item`; steps `uses: <kind>` + `with` xor `run:`; kinds `git.worktree | git.sync | shell | agent | git.commit | git.push | pr.link | checkpoint | template | bmad.install` (+ `plan.check` planned first); one `for_each` per file with `pause_before_item_when` / `pause_after_item_when`; `{{var}}` substitution only); validate returns every error with template, version, line, reason (the FR-5 error list); `agent` extras `expect`, `retry`, `escalate_when`, `pause_when`; any step `timeout_min`, `on_fail`; `template` call `with {name, version, inputs}` sees only declared inputs; a step without `gate` is reported `unvalidated`.
FR-6 [S]: Immutable Versions — saving creates version n+1; a version pinned by any Run (directly or as callee) cannot be modified or deleted; versions list shows pin counts and callers; a Run keeps resolving its pinned versions.
FR-7 [S]: Rendered template diagram — backend computes the graph (one node per step with kind, name, gate; `for_each` as group; `template` calls collapsed; agent steps and human gates distinguished) from the same validator; browser lays out and draws it read-only; updates on every successful validation; invalid YAML keeps the last valid diagram with a stated error.
FR-8 [M]: Start a Run with pre-flight — choose Template Version (`initiative`, `epic`, `repo-init`; never `story`), Project, Repository, base branch, template inputs, Harness, model, budget, *re-review done Stories*, manual estimate (immutable after start); pre-flight on every field change with the FR-8 check list (origin, base, branches exist/held, `epics.yaml` and every `stories.yaml` parse with prefix-free ids, checkpoints warning, `SPEC.md` present, harness enabled, `_bmad/` at `BMAD_VERSION`, existing story files with statuses, clone check not failed); failing check disables *Start run* with the fix; *What will run* is the full planned row list (first row `plan`, loops expanded, done Stories `skipped · already done`) from the same planner that persists; rows read at one `plan_ref` SHA; stale-plan check when the first Step starts parks `plan stale: {file}`; *Start run* persists rows, enqueues, and says whether it starts now or queues behind a named Run; plan-time errors name template, version, line, item.
FR-9 [M]: Checkout and baseline — Worktree at `/work/{project}/{repo}/wt/{branch}` (created from base when the branch is missing), recorded on the Run with created/pushed flags; `install_command` runs inside checkout when declared; baseline runs `quality_gate_command` before any Story of an epic; non-zero baseline → Run `failed`, $0 spend; no quality command → baseline `skipped`; existing clean Worktree reused, dirty one refuses to start; terminal Runs' Worktrees removed after 7 days.
FR-10 [M]: Story loop — per Story in `stories.yaml` order: sync, build (Story step), verify, commit-guard, optional done checkpoint; list read once at planning; already-done Stories planned `skipped · already done` unless re-review; sync fetch + ff-only (no-op without upstream; diverged → `sync: branch diverged` park); verify runs `quality_gate_command`, on failure appends `## Verify Failure` to the Story file, sets `in-progress`, redispatches once (`on_fail: {redispatch, max: 1}`), second failure parks `verify failed 2/2`; commit-guard commits leftovers `story {id}: {title} (orchestrator)` (spec folder staged first) or records `no changes`, and runs the protected-path check; per-Step `timeout_min` (defaults 90 agent / 30 shell / 5 git) enforced by the process runner, expiry → Step `error`, park `timeout {path} after {n} min`; every automatic re-execution is a recorded Attempt with counters; blocked/budget/timeout/protected/internal/config failures never auto-retry; Story step ≤ `(1+retry.max)×(1+redispatch.max)` Attempts; budget check after every Attempt.
FR-11 [M]: Push and finish — after the last Story of an epic push the Working branch (token per git command, never in an agent env), refuse when branch = default branch, rejected push parks `push rejected` with Retry, never force-push; record the GitHub compare URL `{default}...{branch}` per epic in the Run's links; Run `done` after the last epic; card reads `n/n epics · m/m stories · k links`; skipped Stories/epics listed beside the link.
FR-12 [M]: Durability and recovery — restart resumes at the interrupted Step without re-executing completed ones; interrupted Story step re-runs as a new Attempt with a new Session id; before every Story Attempt: WIP commit `wip: story {id} attempt {n} (interrupted)` when dirty, then orchestrator writes committed as `orchestrator: prepare story {id} attempt {n}`, `start_sha` after both; each Harness process in its own process group, pgid recorded, re-attempt kills the group and waits for `.git/index.lock`; checkout idempotent; `/work` and Harness session dirs are persistent volumes; a Run parked 30 days becomes `failed` (`parked 30 days`); image upgrades do not re-plan parked Runs.
FR-13 [M]: Concurrency and repository lock — at most one active Run per Repository and `MAX_ACTIVE_RUNS` (default 2) overall; further Runs queue with `waiting: repository lock held by {run}` / `waiting: global concurrency, held by {runs}`; a `needs-you` Run holds its lock and its slot; the lock is the queue's per-Repository partition, no lock table.
FR-14 [M for `claude`, `codex`; S for `local`]: Dispatch a Story to a Harness — launch the Harness headlessly in the Worktree with a prompt naming the skill, Spec folder, Story id, plus `invoke_dev_with`, plus "Halt after planning." when `spec_checkpoint`; approvals pre-granted; the Harness must expose subagent spawning, file read/write, shell (Claude: default discovery + `CLAUDE_ALLOWED_TOOLS`, never `--bare`); `bmad-build-auto` installed in the image for every Harness; Session id per Attempt; CLI invocation resolved from current docs and recorded in `addendum.md` §B; static config from setup scripts referencing env names only; Harness exit from its own budget cap routed as budget halt; process receives exactly the env contract (Gateway URL/key, Langfuse, identifiers, trace context, Project env vars, content-logging switch) and never `GITHUB_TOKEN`, the spend key, or the orchestrator env; Attempt records harness, model, session id, exit code, wall-clock, tokens, cost, log.
FR-15 [M]: Project context in the prompt — before every Story step write `{Spec folder}/project-context.md` (context text + existing context file paths; missing paths reported in the Step log), regenerated per dispatch, committed by the prepare commit / commit-guard, never inside the prompt.
FR-16 [M]: Agent contract evaluation — after exit, glob `{Spec folder}/stories/{id}-*.md`: exactly one parseable file is liveness; zero/several/unparseable → `error`, park `no story file` / `ambiguous story file` (Retry archives all but newest to `stories/.answers/`); `blocked` with a configuration condition (`no subagents`, `no stories.yaml found`, `story id not found in stories.yaml`, `version-control metadata not writable`) → park `harness misconfigured: {condition}` without Answer box; routing: `done` → done; `blocked` → blocked with the whole `## Auto Run Result` as Question; `ready-for-dev` + `spec_checkpoint` → checkpoint; anything else or exit ≠ 0 with `done` → `error` after the template `retry {max, prompt}` is exhausted (`unexpected status: {s}` / `harness exit {code}`); protected-path hit wins over every route; unexpected exception → `internal: {error}`; Story step gate recorded `liveness`, never rendered green on its own.
FR-17 [M]: Budget halt — after every Story Attempt (before verify) read Attempt spend from Gateway logs by Run + Attempt ids, Run spend = sum; spend > budget → park `budget {spent} / {budget}`, no further Harness process; Harness-reported usage used and marked provisional until the Gateway figure exists; Raise budget resumes at the Step's routed status (a `blocked`/`checkpoint` row returns to that stop without re-dispatch; `done` continues) or Cancel.
FR-18 [M]: Answer a blocked Story — Answer box states the mechanism; on submit move the Story file to `{Spec folder}/stories/.answers/{id}-attempt-{n}.md` with `## Human Answer` appended, re-dispatch on the same Harness with prompt suffix `Answer from the operator to the blocking condition "{condition}": {answer}`; Run leaves `needs-you` within one poll; Answer, actor, time in the gate record.
FR-19 [M; inline edit S]: Continue at a Checkpoint — spec checkpoint: Continue re-dispatches with the file at `ready-for-dev` (no re-planning); *Reject with a reason* = the Answer signal at a spec checkpoint; done checkpoint: a planned `checkpoint` row, Continue marks it done; while `needs-you` (and no terminal session) inline edit of any Spec folder file except `stories.yaml` / `epics.yaml` (read-only, `planned at {commit}`), each save committed `spec: operator edit (orchestrator)` and named in the gate record; both write a gate record entry.
FR-20 [M; skip epic S]: Skip a Story or epic, retry a Step, cancel a Run — Skip story marks the Story's remaining agent/checkpoint rows `skipped · skipped by operator`, runs its verify as re-baseline and commit-guard `story {id}: skipped by operator` (re-baseline failure parks `re-baseline failed after skip`); Skip epic does the same over the remaining Stories, still runs commit-guard, push, and compare link, then the next epic; Retry re-executes only the current `error` Step as a new Attempt (`failed` Runs are terminal; retrying a `done` file starts a review pass); Cancel (confirmed) kills Harness process groups, stops the Run, marks planned Steps `skipped`, removes the Run's Worktrees, deletes branches only if created by this Run and never pushed, status `cancelled`, late results ignored and logged.
FR-21 [S]: Terminal resume command — `claude` and `codex` Story steps show a copyable `docker compose exec backend-api …` resume command with Worktree path and Session id (remaining lifetime shown for `claude`, 30 days); `local` shows none; copy confirms `COPIED` ~1.2 s, never soft-wraps; copying marks the Run `terminal session in progress` (Answer/Continue/Skip/Retry disabled until *Release*); the server polls the Worktree every 30 s and after two consecutive clean `done` polls marks the Story step done (actor `terminal`) and resumes at verify.
FR-22 [M; LIST C]: Board — every Run as a card in its Status column (`Queued · Running · Needs you · Done · Failed`, always rendered, empty as `—` with count 0; `cancelled` under Failed with the word), filtered by Project; `NOTHING RUNNING` / `NOTHING REGISTERED` empty states; rail `n need you` amber only when n > 0; footer running/queued counts and last update; waits > 48 h amber age; cards not draggable, whole card opens Run detail; progress `n/n epics · m/m stories · k links` (epic figure omitted for `epic` Runs); LIST alternative (COULD).
FR-23 [M; artifacts tree + active time S; changed marks C]: Run detail — header (Status, branch, unabridged meta line: Project, Repository, base, Initiative or Spec folder, Template Version, Harness, start time, Worktree), alert banner on `needs-you`/`failed`, Question + Answer, resume command, Steps table (`path · kind · gate · status · time · harness · cost`, every planned row from the start, gate words, `skipped` / `unvalidated` never green, latest Attempt + count), Stories strip, Spec folder file tree with inline viewer/editor, cost block (`spent / budget` ratio, tokens, wall-clock, active Operator time via `POST /runs/{id}/activity` focused seconds excluding idle > 5 min, Trace link), compare links, gate record; one read from the server, no browser aggregation; changed-since-last-opened marks (COULD).
FR-24 [M]: Refresh model — Board and Run detail poll every 5 s while any Run is `running`, else 30 s; footer prints the last update; state swap without animation; a failed fetch renders a full-surface readout with the failed request and a retry control.
FR-25 [M queue; S history]: Queue and history — queue (position, Run, next Step, waiting reason from `repository lock held by {run}` / `global concurrency` / `running` / `waiting for your answer`, waiting time) read from the engine port, `needs-you` Runs at position `—`; paginated Step history (one row per Attempt: time, Project, Run, Step path, kind, Harness, Status, duration, cost, Trace link; Harness/session/tokens empty on non-agent rows) filtered by Project and Status, rows link to the Run detail.
FR-26 [M]: Gateway routing — every model call through LiteLLM with the instance model-call key and the attribution identifiers (`langfuse_session_id` = Run id, `langfuse_tags` and `x-litellm-tags` `run:`, `attempt:`, `story:`, `harness:`, `project:`, `x-litellm-end-user-id` = Run id, `x-litellm-session-id` = Attempt id); Gateway unreachable → Step `error`; spend logs filterable to one Run and one Attempt; no per-Project key/budget/alias; the spend-read key (`LITELLM_SPEND_KEY`) never reaches a Harness.
FR-27 [M]: One Trace per Run — trace created at `create_run` with id seeded from the Run id and Langfuse session = Run id; every Step has a span; every Attempt runs inside a child span whose `TRACEPARENT` is exported to the Harness (`claude`, `codex` parent natively; `local` found by Run id as user/session id); exactly one exporter per Harness; the Run detail Trace link opens a view with every Step span and every Gateway generation.
FR-28 [M; per-Project monthly C]: Cost per Attempt — tokens in/out and cost per Attempt from Gateway spend per model; Run cost = sum; cost per epic/Story = sum over Path prefix (card and Run detail); Gateway figure authoritative, harness usage shown `provisional`; per-Project monthly spend on the Project screen (COULD).
FR-29 [S]: Run diagram — Run detail diagram view: the planned Steps as a left-to-right tree Run → epics → Stories → Steps from the same backend graph builder (node id = Step path, group = path prefix), every node with its token, Stories in `stories.yaml` order grouped by path, sub-steps as words, group token rule (`ERR/BLK/CHK` if any child, else `RUN`, else `SKP` all skipped, else `DON`, else `QUE`), current node `now`, click → Steps row, read-only, same poll.
FR-30 [M]: Initialise a Repository — from the Repository row start a `repo-init` v1 Run on `chore/bmad-init` from the default branch: `bmad.install` at `BMAD_VERSION`, git-ignore lines for `.claude/skills/bmad-*` and `.agents/skills/bmad-*`, commit, push, compare link; skill/agent folders never committed; re-running updates `_bmad/` on the same branch; row states the method version found on the default branch, `missing`, or `outdated` (from `_bmad/_config/manifest.yaml`); subject to the repository lock.
FR-31 [M]: Protected paths — after every Story Attempt and at every commit-guard check that the agent modified none of `SPEC.md`, `stories.yaml`, `epics.yaml`, any `AGENTS.md` (creating one is a hit), or a pre-existing `test_globs` file frozen at the Story frame's first Attempt (agent-created tests stay editable); compare agent ranges only (`start_sha` → `end_sha` ∪ uncommitted) so Operator and orchestrator commits are never attributed to the agent; hit → Step `error`, park `protected path modified: {files}` with diff names, never auto-retried; Operator Accepts (files recorded in `accepted_paths`, gate record, Trajectory; routing resumes on the same tree), reverts and Retries, or Skips; the agent's own Story file is not protected.
FR-32 [M record; S export]: Trajectory — when a Story's build row is `done` and its verify row `done`/`skipped`, insert one append-only record (Run, Story, Harness, model, Attempts, gate results, cost, Story file as committed, start and end commits); *Export trajectories* on the Project screen downloads JSON-lines newest first; nothing updates or deletes rows.
FR-33 [M]: Harness readiness — a Harness is offered only after an `epic` v1 Run on the built-in fixture Repository (Project `readiness`, uneditable; branch `readiness/{harness}/{date}`, never pushed; an ordinary Run on the Board) reached `done` with: Story file `done`, Session id recorded, trace holds the Attempt's spans (`claude`, `codex`) or generations under the Run session (`local`), Gateway spend non-empty, verify exit 0; each check a line, first failure is `disabled: {line}`; harness list on New workflow shows `enabled` / `disabled: {check}` + last readiness time + re-run; a changed version pin disables until readiness passes again; parked Runs keep their Harness.

### NonFunctional Requirements

NFR-1 Durability: no completed Step is ever re-executed after a restart; a Run may park 30 days.
NFR-2 Honesty of status: `skipped` and `unvalidated` are words, never green; no Step without a Gate strength renders as passed (tested with a Template whose Step lacks `gate`).
NFR-3 Isolation: agent processes run as a non-root user in the backend container and receive exactly the declared environment contract; never `GITHUB_TOKEN`, a direct provider key, the spend key, or the orchestrator env; Project A's Run cannot read Project B's env vars; credentials read once from the instance env.
NFR-4 Egress: outbound network limited to git host, package registries, Gateway, Langfuse, host model server — documented as a host firewall rule in the MVP, not enforced by containers.
NFR-5 Observability: every Step has a span; every model call has a Gateway spend log with Run tags.
NFR-6 UI: desktop ≥ 1280 px, single dark theme, WCAG 2.2 AA contrast for primary and secondary text; status always a word token; exactly one signal-coloured element per card or row (green running, amber needs you, red failed); a screen with nothing needing the Operator has no amber or red pixel.
NFR-7 Build size: one Docker Compose file (web-client, backend-api, Postgres) with LiteLLM, Langfuse, and the model server on the host; `/work` and Harness config/session directories as named volumes; every setting an env var listed in one `.env.example`; first run from clone in under 30 minutes on the Mac mini.
NFR-8 Voice: copy states facts and identifiers, never congratulates or apologises, names the mechanism whenever an action changes a file or branch; `skipped`, `unvalidated`, `blocked`, `exit 1` are words, not icons.
NFR-9 Buildability: two components with one constitution each (`AGENTS.md`), strict layering enforced by a linter, formatter + linter per stack, unit tests on shared fakes, independent API and UI end-to-end suites from project setup; a step kind, a Harness, or the workflow engine is replaceable by adding one adapter.

### Additional Requirements

**Starter template:** none. Greenfield monorepo scaffolded to the spine's Structural Seed tree; the drafted deliverables under `mvp/architecture/deliverables/` (root + per-component `AGENTS.md`, `scripts/harness/{_common,claude,codex,opencode}.sh`, `.env.example`) are placed into the repository by the first story.

- AR-1 Repository layout (spine Structural Seed): root `AGENTS.md`, `Makefile` (`up down lint test e2e-api e2e-ui openapi`), `docker-compose.yml`, `.env.example`, `contracts/openapi.json`, `templates/{repo-init,story,epic,initiative}.yaml`, `scripts/harness/*.sh`, `scripts/readiness_fixture.sh`, `fixtures/readiness-repo/`, `host/{README.md,litellm.config.yaml,backups/}`, `backend-api/`, `web-client/`.
- AR-2 backend-api stack and layering (AD-2, Stack): Python 3.14, uv 0.12, FastAPI 0.141, Pydantic 2.13 + pydantic-settings, SQLAlchemy 2.0 + psycopg 3 + Alembic, dbos 2.31, langfuse 4.15, structlog, PyYAML, cryptography; packages `domain/ → application/ → {api/, infrastructure/} → main.py`; `domain/` and `application/` never import fastapi, sqlalchemy, dbos, subprocess, os, shutil, httpx, langfuse, git; enforced by import-linter; ruff + mypy strict on domain/application.
- AR-3 web-client stack (AD-1, Stack): Astro 7.2 SSR (`@astrojs/node` standalone) on Node 24, React 19 islands, nanostores, openapi-typescript + openapi-fetch, CodeMirror 6 (`lang-yaml`), `@dagrejs/dagre`, Vitest, Playwright, pnpm 11; only `src/api/server.ts` (server, `astro:env/server`) and `src/api/client.ts` (browser, base `/api/`) call `fetch`; eslint `no-restricted-globals` / `no-restricted-imports` on `src/islands/**`, `src/stores/**`, `src/components/**`; proxy route `src/pages/api/[...path].ts`; islands never hold a backend credential.
- AR-4 Contract generation (AD-3): Pydantic schemas in `api/schemas/` are the single source; `make openapi` exports `contracts/openapi.json`; `pnpm gen:api` generates `src/api/schema.d.ts`; CI regenerates both and fails on `git diff --exit-code`; no hand-written payload types.
- AR-5 Auth (AD-4): backend authenticates every `/api/v1/*` request by constant-time bearer comparison against `ORCHESTRATOR_TOKEN` in `api/deps.py`; web-client `POST /login` compares the same token and sets signed HttpOnly `orch_session` (30 days, `ORCHESTRATOR_SESSION_SECRET`); `src/middleware.ts` redirects unauthenticated page loads to `/login`; backend has no cookies, no CORS headers.
- AR-6 Configuration (AD-20): `infrastructure/settings.py` (pydantic-settings) and `astro:env` are the only readers of the environment; `.env.example` lists every variable with a comment (table in the spine: `ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SESSION_SECRET`, `ORCHESTRATOR_SECRET_KEY`, `BACKEND_API_URL`, `DATABASE_URL`, `DBOS_APPLICATION_VERSION`, `GITHUB_TOKEN`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LOCAL_MODELS`, `MAX_ACTIVE_RUNS`, `LANGFUSE_BASE_URL/PUBLIC_KEY/SECRET_KEY/ENVIRONMENT`, `BMAD_VERSION`, `CLAUDE_CODE_VERSION`, `CODEX_VERSION`, `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION`, `CLAUDE_ALLOWED_TOOLS`, `WORK_DIR`, `AGENT_HOME`, `LOG_PROMPT_CONTENT_DEFAULT`, `LOG_LEVEL`); `make lint` fails when a setting is added without updating `.env.example`.
- AR-7 Ports (AD-6, AD-10, AD-11, AD-14): `domain/ports/{engine,harness,git,workspace,process,gateway,tracer,clock,repositories}.py` with the exact method sets the spine states (`WorkflowEngine.enqueue/signal/cancel/list_queue/attempt_record/schedule`; `Harness.run/resume/resume_command` + capabilities; `Git` 13 methods; `Workspace.read/write/glob/exists/move/tree` rooted at the current worktree with traversal rejected; `ProcessRunner.start/wait/kill_group` with `timeout_min`; `Gateway.spend_for_attempt`; `Tracer` incl. `attempt_observed`; `Clock`); one in-memory fake per port in `tests/unit/fakes/`.
- AR-8 Data model (Structural Seed fields): `project` (env_vars_enc, log_prompt_content), `repository` (default_branch, package manager, install/quality_gate/unit_test commands, test_globs, clone_check{status, at, output, bmad_version}), `harness` (name, enabled, last_readiness_at, failing_check, version_pin), `template` + `template_version` (yaml, hash, calls[], frozen once pinned), `run` (engine_ref, plan_ref, accepted_paths[], worktree_path, worktrees[]{branch, path, created_branch, pushed}, compare_urls[], trace_id, budget_usd, spend_usd, manual_estimate_h, park_kind, park_path, terminal_session, re_review_done, active_seconds, last_opened_at, status), `step_run` (seq, path unique per Run, label, kind, gate, status, reason, with_resolved, retry_count, redispatch_count), `attempt` (n, started_at, ended_at, status, engine_ref, start_sha, end_sha, frozen_test_files, log_path, harness, model, session_id, pgid, exit_code, tokens_in/out, cost_usd), `gate_record` (run, at, path?, event, actor, text), `trajectory` (append-only); UUIDv7 ids, `timestamptz`, money `numeric(12,6)` as JSON strings; Alembic migrations run at container start before `DBOS.launch()`.
- AR-9 Engine adapter (AD-6, AD-12): `infrastructure/dbos/` implements the port with a walker that executes `step_run` rows in `seq` order, one queue with `partition_key = repository_id` (partition concurrency 1, global `MAX_ACTIVE_RUNS`), human waits as a single `recv` on `human:{run_id}` (30 days; expiry → Run `failed`, `parked 30 days`), `schedule(name, cron, job)`; replay-safe rules (side effects inside engine steps, engine retries off, list files read once, no wall-clock branching outside steps); `application_version` = `DBOS_APPLICATION_VERSION`; `engine_ref` JSON opaque to everything but the adapter.
- AR-10 Planner (AD-7): pure `plan_run(template_version, inputs, Git) -> Plan{plan_ref, rows[PlannedRow{seq, path, label, kind, gate, status, reason?, with_resolved}]}` reading list files and callees via `Git.read_file/list_files` at `origin/{branch}` or `origin/{base}`; `template` calls are path segments; `pause_*_when` become `checkpoint` rows at `…stories[n].before/after`; empty `shell` → `skipped · no command`; done Stories → `skipped · already done` unless `re_review_done`; first row `plan.check`; `create_run` persists rows in one transaction before `enqueue`; pre-flight renders the same output; plan-time error = 422 with template, version, line, item.
- AR-11 Status writers (AD-8): `start_attempt(run_id, seq)` and `apply_step_result(run_id, seq, StepResult)` own execution transitions (successor `planned → queued` in the same unit of work; park writes `run.status`, `park_kind`, `park_path`, gate_record; no-op when Run not `running`; escaped exceptions → `internal`); `signal_run(run_id, Signal)` owns Operator transitions (validate → 409, gate_record, transition, clear `park_*`, `engine.signal`); Run and Step state machines exactly as the spine's two diagrams; `AttemptRepository.mark_started` (start_sha, frozen_test_files, pgid) before `ProcessRunner.wait` and `mark_finished` (end_sha, exit_code, session_id, usage, log_path) right after.
- AR-12 Step kinds (AD-9, kinds table): `application/steps/<kind>.py` implementing `StepExecutor.execute(StepContext) -> StepResult` for `plan.check`, `git.worktree`, `git.sync`, `shell`, `agent`, `git.commit`, `git.push`, `pr.link`, `checkpoint`, `bmad.install`; registry in `application/steps/__init__.py` is the only enumeration read by validator, planner, graph builder, walker; default gates and timeouts per the table; `compose_prompt` in `steps/agent.py` is the only prompt builder; signal side effects (Answer archive, de-ambiguation archive, skip commit message) performed by the resumed executor reading `resume_signal`; `continue` after `protected_path` re-applies the agent tail without dispatch or new spend.
- AR-13 Rules (AD-9, AD-11, AD-17): `application/rules/{routing,budget,protected_paths}.py` — FR-16 routing table, budget rule (`spend_usd > budget_usd` → park `budget` while the row keeps its routed status), protected-path check over `diff_names(start_sha, end_sha) ∪ uncommitted` with the frozen test set and `accepted_paths` exclusion; 100 % branch coverage required.
- AR-14 Harness adapters (AD-10): `infrastructure/harness/{claude,codex,opencode}/adapter.py`; `env_for(attempt)` = `HARNESS_ENV_CONTRACT` (`ORCH_RUN_ID, ORCH_ATTEMPT_ID, ORCH_STORY_ID, ORCH_HARNESS, ORCH_PROJECT, ORCH_TAGS, ORCH_LANGFUSE_TAGS, TRACEPARENT, LITELLM_BASE_URL, LITELLM_API_KEY, LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, ORCH_LOG_CONTENT`) + the harness's `HARNESS_ENV_ALIASES` + Project env vars, with a unit test asserting the key set equals the two script lists; adapters read env names only, write nothing under `AGENT_HOME`, return `HarnessResult{session_id, exit_code, usage, log_path}` uninterpreted; Claude: default tool discovery + `CLAUDE_ALLOWED_TOOLS`, `dontAsk`, `--disallowedTools "mcp__*"`, `--max-budget-usd` = remaining budget; Codex: `codex exec`, `danger-full-access`, session id captured from output; OpenCode: `opencode run --format json --session <id>`, config-driven permissions; `scripts/harness/<name>.sh install|configure|doctor` generate static config from env names (`install` at image build, `configure` at container start).
- AR-15 Harness readiness (AD-10): `harness` table written only by `use_cases/harness_readiness` (`start(name)`, `evaluate(run_id)` called by the walker's final step for every Run of Project `readiness`, `sync_pins()` at container start); `fixtures/readiness-repo/` materialised by `scripts/readiness_fixture.sh` (git init + `bmad.install` at `BMAD_VERSION`, one trivial Story); built-in uneditable Project `readiness`; `enabled` read only by `create_run` and pre-flight; the readiness Run is exempt from the harness-enabled check; `GET /harnesses`, `POST /harnesses/{name}/readiness`.
- AR-16 Tracing (AD-11): `Tracer` port over the Langfuse SDK — `create_run` creates the trace (`trace_id = create_trace_id(seed=run_id)`, `session.id = run_id`, tags `run:`, `project:`), a span per Step, a child span per Attempt exporting W3C `TRACEPARENT`; `attempt_observed(run_id, attempt_id)`; `claude`/`codex` native OTLP (Claude behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`), `local` via `@langfuse/opencode-observability-plugin` with `LANGFUSE_USER_ID = run_id`; content logging switches (`OTEL_LOG_USER_PROMPTS`, Codex `log_user_prompt`, plugin equivalent) only when `project.log_prompt_content`.
- AR-17 Gateway spend (AD-5, AD-11): `infrastructure/gateway/` reads `GET /spend/logs/v2?end_user=<run_id>&session_id=<attempt_id>` with `LITELLM_SPEND_KEY` and sums into `AttemptSpend{usd, tokens_in, tokens_out, provisional}`; empty → `HarnessResult.usage` marked provisional; attribution headers set through each harness's env-name header mechanism (`langfuse_session_id`, `langfuse_tags`, `x-litellm-end-user-id`, `x-litellm-session-id`, `x-litellm-tags`).
- AR-18 Signals (AD-13): `POST /runs/{id}/signals {kind, payload}` for `answer`, `continue`, `retry`, `skip_story`, `skip_epic`, `budget_raise`, `cancel`, `terminal_start`, `terminal_release`, plus machine `terminal_resume`; validity, writes, resumed-step effects, and row transitions exactly per the AD-13 table; `PUT /runs/{id}/files` (spec folder only, `needs_you`, not during a terminal session, never list files) commits `spec: operator edit (orchestrator)`; `cancel` and file edits are the only worktree writes outside an engine step; `terminal_poll` every 30 s.
- AR-19 Git, workspace, process adapters and jobs (AD-14): base clones with detached `HEAD` at `/work/{project}/{repo}/base`, worktrees at `/work/{project}/{repo}/wt/{branch}`, logs at `/work/logs/{run_id}/` on volume `work`; `GIT_ASKPASS` for `GITHUB_TOKEN` per command; `git.worktree` reuse-when-clean / refuse-when-dirty, appends `run.worktrees[]`, runs `install_command`; `Git.sync` no-op without upstream; `ProcessRunner` starts each process in its own session/process group, enforces `timeout_min`; scheduled jobs `clone_check` (daily), `worktree_gc` (7 days), `terminal_poll` (30 s) through `engine.schedule`.
- AR-20 Templates (AD-15, AD-16): `application/templates/validate.py` is the single parser/validator implementing the DSL v1 key table; `application/templates/plan.py`; `application/graph.py` producing `{nodes, edges, groups, statuses?}` for `GET /templates/{name}/{v}/graph` (index-free node ids like `stories.story.build`, calls collapsed) and `GET /runs/{id}/graph` (node id = `step_run.path`, group = prefix, group status by the one rule; cancelled Run derives none); `POST /templates/{name}/validate`; saving creates version n+1, pinned versions frozen; shipped YAML for `repo-init@1`, `story@1`, `epic@1`, `initiative@1` per `template-dsl-draft.md` §3 (epic: worktree → baseline → for_each stories → push → link; story: sync → build → verify (`on_fail: {redispatch, max: 1}`) → commit-guard; initiative: for_each epics → `uses: template epic`; repo-init: worktree `chore/bmad-init` → `bmad.install` → commit → push → link).
- AR-21 BMAD in the image (AD-16): backend image pins `bmad-method` 6.11.0 and copies skill stubs to `~/.claude/skills` and `~/.agents/skills`; `bmad.install` runs `npx bmad-method@$BMAD_VERSION install --yes --directory <worktree>` + gitignore lines; pre-flight requires `_bmad/_config/manifest.yaml` version = `BMAD_VERSION` at `plan_ref` unless the plan contains a `bmad.install` row.
- AR-22 Tests and gates (AD-18): backend unit tests only on fakes; `tests/e2e/` httpx scenarios + Schemathesis from `/openapi.json` against the compose stack; web-client Vitest units (React Testing Library for islands) + Playwright in `tests/e2e/` against `astro preview` with stubbed routes or `E2E_BACKEND=real`; every `src` module has a test module; 100 % branch coverage on `domain/`/`application/` rules, status machines, `signal_run`, `apply_step_result`, `steps/agent.py`; changed lines ≥ 90 %; CI order lint → unit → e2e-api → e2e-ui.
- AR-23 Trajectory (AD-19): `use_cases/record_trajectory.py` inserts one `trajectory` row when build `done` and verify `done | skipped`; `GET /projects/{id}/trajectories.jsonl` exports newest first.
- AR-24 API conventions: routers `auth`, `projects`, `repositories`, `templates`, `runs`, `steps`, `queue`, `harnesses` under `/api/v1`; `/healthz`, `/openapi.json`; `POST /repositories/{id}/clone-check`, `POST /repositories/{id}/init`; read models per screen (`GET /runs?view=board`, `GET /runs/{id}` with steps, stories strip, cost, gate record, worktrees, compare URLs; `GET /queue`; `GET /steps`; `GET /runs/{id}/files?path=`); `POST /runs/{id}/activity {focused_seconds}` batched every 60 s; RFC 9457 `application/problem+json` (401, 409, 422 with `errors[]{template?, version?, line?, path?, reason}`); lists `{items, next_cursor}`; ISO 8601 UTC `Z`; structlog JSON with `run_id`, `path`, `attempt`; `Clock` port, no `datetime.now()` outside infrastructure.
- AR-25 Front-end structure: `src/pages/` (login, index board, runs/[id], runs, projects, templates), `src/actions/` form posts returning `ActionError` with the problem body (page re-renders with every submitted value, `detail` verbatim, `errors[]` beside the field named by `path`, no toast, no redirect on error), `src/islands/` (Board, RunDetail, RunDiagram, TemplateEditor, ProjectForm, NewWorkflow), `src/components/` static Astro, `src/stores/` (polling interval store, session, filters).
- AR-26 Containers and host (NFR-7, AD-20, Operations): backend Dockerfile `python:3.14-slim-trixie` + uv + Node 24 + git/gh + Claude Code 2.1.258, Codex 0.152.1, OpenCode 1.18.26 + bmad-method, non-root user `agent`; web-client Dockerfile `node:24-bookworm-slim` build → astro node standalone; compose with `postgres:18`, named volumes `work` and `agent-home`, `cap_drop ALL`, `no-new-privileges`, `host.docker.internal` for LiteLLM/Langfuse; `host/README.md` (LiteLLM `model_list`, `LITELLM_OTEL_V2=true` + `langfuse_otel`, local models `openai/<alias>` with `use_chat_completions_api: true`, two keys, oMLX, nightly `pg_dump` cron 14 days) and `host/litellm.config.yaml`.
- AR-27 Day-1 verifications (spine "Open at handoff", PRD §8): Codex honours `TRACEPARENT` (fallback: Langfuse Codex plugin, flat trace); `DBOS.step_id` = `operation_outputs.function_id`; `CLAUDE_ALLOWED_TOOLS` reaching `done` under `dontAsk`; image skill stubs resolve the worktree as project root and Codex/OpenCode subagents satisfy `bmad-build-auto` (fallback: `git.worktree` copies stubs into git-ignored worktree folders); `x-litellm-session-id` coexists with `langfuse_session_id` (fallback: sum by `request_tags`); two Gateway keys on the host (`key_type: llm_api` + admin) — each decided by the readiness run, fallbacks recorded in `addendum.md`.

### UX Design Requirements

- UX-DR1 Design tokens as CSS custom properties in one global stylesheet (instrument-dark): grounds `bg #0B0D0E`, `surface #111416`, `surface-raised #171B1D`, `surface-rail #0E1113`, `surface-inset #08090A`; hairlines `line #21272A`, `line-strong #2C3438`; text `#DDE3E5` / secondary `#8B979B` / tertiary `#5C686C`; signals `signal-blocked #E4B33C` (amber BLK/CHK), `signal-qa #4FB477` (green RUN), `signal-infra #E05252` (red ERR); `accent #7FD4C1` (interaction and identifier literals only); one monospace family, no weight above 400, the 14-role type ramp (detail-title 19, question 14/1.7, command 13/1.7, body 13/1.45, surface-title 13 uppercase 0.18em, row-title 12.5, row-body 12.5/1.55, meta 11.5, micro 11, status-token 11/0.10em, control 11 uppercase 0.12em, eyebrow 10.5 uppercase 0.16em, column-head 10 uppercase 0.18em, section-head 10 uppercase 0.22em); 2px spacing scale, `rail-width 172px`, `page-max 1180px`, `detail-max 940px`, `section-gap 34px`; radius 0 everywhere; no shadows (only the accent inset marker on the active nav item).
- UX-DR2 Signal rule (attention model): three hues only; on any card or row exactly one element carries a signal colour (chip + token); a declared human gate is the word `human` and a `line-strong` hairline, never amber; a screen with nothing needing the Operator has no amber or red pixel; the only tolerated pair is a `BLK`/`CHK` card older than 48 h (token and age both amber); tokens `QUE RUN BLK CHK ERR DON SKP CAN` always as words in a fixed leftmost column.
- UX-DR3 Shell: fixed 172px app rail on `surface-rail` with brand block, *Workflows* (count + `n need you` in amber when n > 0), *Runs*, group *Configure*: *Projects*, *Templates*; active item on `surface-raised` with the accent inset marker; surface bar (surface title, count, filters right); footer readout `n running · m queued / k need you / updated hh:mm:ss · refresh`; no notifications surface; depth Board → Run detail is the maximum.
- UX-DR4 Refresh and failure readout: polling every 5 s while any Run is `RUN`, else 30 s, through one nanostores interval store; updates are a state swap with no animation; a failed fetch replaces the surface with a full-surface readout showing method, path, status in a command block and a *Retry* control.
- UX-DR5 Reusable components (from `DESIGN.md`, all square, no fills): status chip (7px square) + three-letter token, record row (five-column grid `52px 128px 210px 1fr 74px`, whole row a link, hover to `surface-raised`), dense table (as many columns as the data has, same hairlines, token the only coloured cell), board column and board card, alert banner (`surface-raised` + 2px left signal rule), detail header (crumb, chip + token, title, unabridged meta line), section head, question block (`typography.question`, amber 2px rule, eyebrow attribution `Agent · model · timestamp`), command block (`surface-inset`, `line-strong` frame, Copy → `COPIED` ~1.2 s, never soft-wraps), outline buttons (primary accent, destructive red, uppercase control type), key/value table (ratios as literals, never bars), artifact tree (14px indent, changed files promoted with one accent chip), empty state (uppercase headline + readout of what is happening instead), focus ring (1px accent outline, never removed), filter group (segmented hairline box with token labels), gate record timeline (timestamp · glyph · text, current row `■` in the signal colour).
- UX-DR6 Login (`/login`): centred 400px panel — brand, `ACCESS TOKEN` input, *Enter*, one hint line (token origin, cookie lifetime); rejection replaces the hint with `token rejected — n attempts left` in red; after the fifth failure `too many attempts — try again in 15 min` with the input disabled (COULD).
- UX-DR7 Workflows board (`/`): bar with title, count readout (`7 runs · 2 need you · oldest wait 2d 04h`), project segmented filter in the query string, BOARD/LIST toggle, *+ New workflow*; five equal fluid columns `Queued · Running · Needs you · Done · Failed` that never collapse (Running header green, Needs-you header amber, others grey); card in fixed order: chip + token (+ harness name right, tertiary) · current branch · project · repository · current or last step **label** · progress `n/n epics · m/m stories · k links` (epic figure omitted for `epic` Runs; `repo-init` / `readiness` in place of progress) · template name and version · age; 2px left rule on blocked/failed cards; age > 48 h amber; cards not draggable; empty column `—` with count 0; empty board `NOTHING RUNNING` + queued list + link to New workflow; no Project `NOTHING REGISTERED` → Projects; `cancelled` under Failed with grey `CAN` and the word; LIST toggle renders record rows (token · project · repository · branch · step label · progress · age) (COULD).
- UX-DR8 New workflow (`/workflows/new`, a page, bookmarkable, survives reload): two columns — form left (190px labels: template with `initiative` latest pre-selected, `epic`, `repo-init`, never `story`; project; repository; base branch; then the inputs the template declares — `initiative`: initiative folder; `epic`: working branch + spec folder; harness as a list, one line per harness with `enabled` or `disabled: {check}` in words, last readiness time, *re-run readiness* link, disabled harnesses unselectable; model (harness default); budget; *re-review done stories* (off); manual estimate) — and right **Pre-flight** (lines `ok / ! / x / —` as words in the first column, never icons; a red line disables *Start run* and states the fix; warnings never block) + **What will run** (dense table `path · kind · gate`, first row `plan · plan.check`, loops expanded to parsed counts, already-done Stories `skipped · already done` unless re-review); decision bar *Start run* (primary), *Cancel*, one note naming the holding Run when queued.
- UX-DR9 Run detail (`/workflows/:runId`): header (crumb, chip + token + branch + age of the current state, unabridged meta line project · repository · base · initiative or spec folder · template version · harness · started · worktree path); alert banner only on `needs-you`/`failed` (token, the Stop's reason text verbatim, right-aligned progress + spend); left column in order: Stop body → **Or continue in the session** command block with copy and session lifetime (hidden for `local`) → **Steps** table (`path · kind · gate · status · time · harness · cost`, every planned row from the start, `planned` as `QUE`, current row promoted, `· n attempts`, gate words `liveness / deterministic / human / unvalidated`, status words `skipped · already done`, `skipped · skipped by operator`, `skipped — no quality_gate_command`; nothing in these columns ever green); right column: **Stories** strip (`n/m` per epic, one cell per story by id: done filled, current amber, future hollow, skipped struck) → **Artifacts** tree at spec-folder scope with changed-since-last-opened chips and, while parked and no terminal session, an inline Markdown/YAML editor with *Save* and the hint `saved as commit "spec: operator edit (orchestrator)" on {branch}`; `stories.yaml` / `epics.yaml` read-only with `planned at {sha} — start a new run to change the list` → **Cost & trace** kv (spent/budget ratio, tokens, wall-clock, your active time, Langfuse trace link, epic compare links, branch link; `provisional` where the Gateway figure is missing) → **Gate record** (append-only lines time · path · event · actor · text); other states: `RUN` no banner and the current row marked; `ERR` red banner with the failing command and last 40 lines and only a `start a new run` link; `DON` one-line summary with progress, one compare link per epic, skipped ids; `CAN` grey banner `cancelled by operator at …`; terminal-session line `terminal session in progress · Answer, Continue, Skip and Retry disabled until Release — the run resumes by itself when the story file is done and the tree is clean`.
- UX-DR10 Stop bodies and actions (one row per PRD §4.6 Stop kind): `blocked` → whole `## Auto Run Result` in a question block with agent eyebrow, Answer textarea with the mechanism hint, *Resume with answer* + Skip story · Skip epic · Cancel run; `spec checkpoint` / `done checkpoint` → planned story file inline (spec) or story summary (done), *Continue* + *Reject with a reason* (spec only, textarea) · Skip story · Skip epic · Cancel; `verify failed 2/2` / `re-baseline failed after skip` → failing command + last 40 lines, *Retry* + skips · Cancel; `budget {spent} / {budget}` → cost kv promoted + numeric *new budget*, *Raise budget* + Cancel; `timeout {path} after {n} min` → log tail, *Retry* + skips · Cancel; `push rejected` / `sync: branch diverged` → git output + `resolve on the remote, then Retry — Retry fetches first`, *Retry* + Skip epic · Cancel; `protected path modified: {files}` → file list with `+ − ~` and diff links, a line naming what Accept does, *Accept changes* + Retry · skips · Cancel; `misconfigured` family → condition, file list, log tail, **no Answer box**, *Retry* + skips · Cancel; `plan stale: {file}` → list-file diff between plan commit and head, *Continue on the recorded plan* + Cancel (and `start a new run` link); `internal: {error}` → exception line + log tail, *Retry* + skips · Cancel; *Cancel run* is the product's only modal (destructive confirm).
- UX-DR11 Run diagram (`?view=diagram`, `DIAGRAM · DETAIL` toggle, survives reload): same header and banner rules; left-to-right tree with orthogonal `line-strong` connectors, square nodes on `surface`, column heads `RUN · EPICS · STORIES · STEPS`; root = the run (initiative: branch, token, progress); `plan` row between root and first epic; epic nodes each with `checkout · baseline` before and `push · link` after their stories; story nodes in `stories.yaml` order grouped by path; step nodes; node = row-title label, meta kind or duration, chip + token right; story node adds a micro row of sub-steps as words (`sync done · build done · verify — · commit —`, `checkpoint` when declared); current node promoted with the word `now`; scheduled nodes `QUE` tertiary; group token by the one rule; cancelled Run root `CAN`, no derived group tokens; laid out with dagre, SVG, read-only; click → DETAIL scrolled to the row by path; footer readout `step 15 of 22 · epic 1 · story 4-1 · build · blocked 2d 04h · 5/8 stories`; queued Run → every node `QUE`, root `waiting: …`.
- UX-DR12 Projects (`/projects`, `/projects/:id`): two panes — list (name, repositories, runs, one amber/red count if any) and detail: title + meta (created, monthly spend, `log_prompt_content on/off`), **Context** (text + hint that it is written to `project-context.md` for every story), **Repositories** table (`repository · default · method · quality_gate_command · test_globs · clone check · status`; method cell = version found / `missing` / `outdated` with *Initialise repository* on missing/outdated rows linking to the `repo-init` Run card and then its compare link; `failed · new runs blocked` with *re-run check*; `— none declared` + `verify step will be skipped` for no quality command) with *+ Add repository*, **Settings** kv (env var count, masked values, the line `GitHub token and gateway key: instance settings`), **Runs on this project**; bar actions *Edit*, *Export trajectories* (downloads `trajectories.jsonl`, hint: one line per done story).
- UX-DR13 New project (`/projects/new`): form left — name, context, context file paths, env vars, `log_prompt_content` switch with its statement in secondary text, repositories (URL, default branch, package manager, `test_globs` pre-filled with the default, `install_command`, `quality_gate_command`, `unit_test_command`); no token field, secondary line `credentials are instance settings (.env)`; **Clone check** readout right, live on save, per repository: `ls-remote`, shallow clone (size, seconds), default branch, method version; failure prints the git output verbatim in an inset block plus a one-line fix (token without access: `the instance's GitHub token has no access to this repository`); the project saves anyway and the row reads `failed · new runs blocked`; `missing`/`outdated` method reads `run Initialise repository after save`; the form keeps every value on error.
- UX-DR14 Runs (`/runs`): bar with project filter + status filter (`ALL · QUE · RUN · BLK · ERR · DON`); **Queue** section (`pos · project · workflow · next step · waiting because · waiting`) with reasons from the fixed set, section head `concurrency {MAX_ACTIVE_RUNS} · one active run per repository · parked runs hold a slot`, parked Runs at `—` with hint `not queued until then`; **History** table (`time · project · workflow · path · kind · harness · status · time · cost · trace`), one row per attempt newest first, current rows promoted, harness/session/tokens empty on non-agent rows, rows link to the Run detail scrolled to that path; pagination (SHOULD).
- UX-DR15 Templates (`/templates/:name/:version`): three columns — versions list (name, version, pinned-by count, `called by {name@v}`, read-only marker, hint explaining frozen versions), CodeMirror YAML editor (line numbers, keys secondary, values primary, `uses:` kinds and `run:` in accent, selected step highlighted), diagram from the backend graph (left-to-right like the Run diagram; node per step with kind eyebrow and gate word; `for_each` as a dashed group; `template` calls collapsed with callee name and version; agent nodes accent-bordered; human gates as the word `human` + hairline; nodes without gate carry `unvalidated`; escalation edges not drawn) + **Inputs bound at start** table (type per input); bar with validation readout (`valid · {time}` or `{n} errors`), *Validate*, *Save as vN+1*; errors listed `line · reason` under the editor; invalid YAML keeps the last valid diagram with `diagram from last valid version`.
- UX-DR16 Naming rule: every planned step has a path (`epics[0].stories[3].build`) and a label (`epic 1 · story 4-1 · build`); the Steps table, gate record, and Runs history print the path; cards, LIST rows, the Stories strip, diagram footer, and banners print the label; never both on one screen for the same step.
- UX-DR17 Voice strings (NFR-8) used verbatim: `Blocked story file archived to stories/.answers/{id}-attempt-{n}.md with your answer; story {id} re-planned with the answer as context.`, `verify step will be skipped`, `skipped — no quality_gate_command`, `Starts immediately if the repository is free, otherwise queues behind {run}.`, `saved as commit "spec: operator edit (orchestrator)" on {branch}`, `skipped · already done`, `waiting: repository lock held by {run}`, `verify failed 2/2`, `protected path modified: {files}`, `run Initialise repository and merge its branch`, `enabled` / `disabled: {check}`, `provisional`, `re-baseline failed after skip`, `plan stale: {file}`, `k links` (never "PRs").
- UX-DR18 Test-ids: grammar `<surface>-<component>[-<instance>][-<field>]`; surface prefixes `login`, `nav`, `board`, `newwf` (incl. `newwf-harness-<name>`, `newwf-plan`), `wf` (`wf-stop-<kind>`, `wf-skip-epic`, `wf-budget-raise`, `wf-accept`, `wf-editor`), `projects` (`projects-init-<repo>`, `projects-export`), `project-form`, `repo-form`, `runs`, `templates`, `artifacts`; the full table is written with the front-end stories and is the Playwright contract.
- UX-DR19 Platform and accessibility (NFR-6): desktop ≥ 1280 px, single dark theme, WCAG 2.2 AA contrast for primary and secondary text, focus ring on every focusable element, status never conveyed by colour alone, no breakpoints (horizontal scroll below ~1024 px rather than reflow).

### FR Coverage Map

FR-1: Epic 1 - token login end to end (backend bearer, web-client cookie, login page); lockout in Epic 8
FR-2: Epic 2 - Project create/edit with encrypted env vars and `log_prompt_content`
FR-3: Epic 2 - Repository registration with commands and `test_globs`
FR-4: Epic 2 - Clone check on save and re-run from the row; daily re-check job in Epic 4
FR-5: Epic 3 - DSL v1 validator and error contract
FR-6: Epic 3 - save as version n+1, versions list; freeze-once-pinned enforced when Runs exist (Epic 4)
FR-7: Epic 3 - backend graph + Templates diagram
FR-8: Epic 4 - pre-flight, pure planner, What will run, plan_ref, stale-plan check
FR-9: Epic 4 - `git.worktree` (install) + baseline shell step
FR-10: Epic 5 - story loop (sync · build · verify with redispatch · commit-guard · done checkpoint) through `story@1` / `epic@1`; the non-agent kinds it composes are built in Epic 4
FR-11: Epic 4 - `git.push` + `pr.link`, compare links, Run `done`
FR-12: Epic 4 - durable walker, restart recovery, process groups; WIP/prepare commits for Story steps in Epic 5
FR-13: Epic 4 - queue partition lock, `MAX_ACTIVE_RUNS`, queue reasons
FR-14: Epic 5 - `claude` dispatch; Epic 7 - `codex` and `local`
FR-15: Epic 5 - `project-context.md` written before every Story step
FR-16: Epic 5 - agent contract evaluation and routing
FR-17: Epic 5 - budget halt after every Attempt; Raise budget signal in Epic 6
FR-18: Epic 6 - Answer a blocked Story (archive + re-dispatch)
FR-19: Epic 6 - Continue / Reject at checkpoints, inline spec editing
FR-20: Epic 4 - cancel, retry on error rows; Epic 6 - skip story, skip epic, re-baseline after skip
FR-21: Epic 6 - terminal resume command, terminal session, terminal poll
FR-22: Epic 4 - Board with columns, cards, empty states, rail count; LIST view in Epic 8
FR-23: Epic 4 - header, banner, Steps table, gate record, cost block skeleton; Epic 5 - Question, Stories strip, cost figures; Epic 6 - Artifacts tree + editor; Epic 8 - active time, changed marks
FR-24: Epic 4 - polling store, state swap, failed-fetch readout
FR-25: Epic 4 - queue section from the engine port; Epic 7 - history table
FR-26: Epic 5 - gateway routing and attribution headers via `env_for`
FR-27: Epic 5 - Run trace, Step spans, Attempt child span, `TRACEPARENT`; per-harness exporters in Epic 7
FR-28: Epic 5 - cost per Attempt from spend logs, sums per path; per-Project monthly figure in Epic 8
FR-29: Epic 8 - Run diagram view
FR-30: Epic 4 - `repo-init@1` Run from the Repository row (first end-to-end Run)
FR-31: Epic 5 - protected-path checks (agent and commit-guard); Accept signal in Epic 6
FR-32: Epic 5 - trajectory record; Epic 7 - export
FR-33: Epic 5 - readiness state, fixture repository, readiness Run for `claude`; Epic 7 - `codex`, `local`
NFR-1: Epic 4 (durability) · NFR-2: Epics 3, 4, 5 (gate words, never green) · NFR-3: Epics 1, 5 (non-root, env contract) · NFR-4: Epic 1 (host/README rule) · NFR-5: Epic 5 · NFR-6: Epics 1, 4 (tokens, signal rule) · NFR-7: Epic 1 · NFR-8: every UI story · NFR-9: Epic 1

## Epic List

### Epic 1: Repository foundation, quality gates, and Operator login
The repository exists as the spine describes it and every gate is runnable: two components with their constitutions, strict layering, lint/test/e2e harnesses, the generated contract pipeline, Docker Compose with hardening, `.env.example` as the configuration contract, the instrument-dark shell, and the Operator's token login. After this epic the Operator can bring the stack up from a clone, log in, and see an empty Board reading `NOTHING REGISTERED`; every later story is built unattended on top of these gates. Executed directly by a high-capability agent.
**FRs covered:** FR-1 (without lockout); NFR-3, NFR-4, NFR-6 (tokens), NFR-7, NFR-9; AR-1..AR-7, AR-22, AR-24 (conventions), AR-26; UX-DR1..UX-DR6, UX-DR19

### Epic 2: Projects and Repositories with the Clone check
The Operator can register a Project with context, encrypted environment variables, and Repositories with their commands, and learns at save time whether the instance token can reach each Repository and which method version it carries. Covers UJ-1 except repository initialisation.
**FRs covered:** FR-2, FR-3, FR-4 (on save and re-run); AR-8 (project, repository), AR-19 (base clone, `GIT_ASKPASS`); UX-DR12, UX-DR13

### Epic 3: Templates — validated DSL, versions, and the rendered diagram
The Operator can read, validate, edit, and save the four shipped Templates as immutable versions and see each version's graph drawn beside the YAML. Delivers the single validator and graph builder every later epic reads.
**FRs covered:** FR-5, FR-6 (save as n+1; freeze-on-pin enforced in Epic 4), FR-7; AR-20 (validate, graph, shipped YAML); UX-DR15

### Epic 4: Plan, start, and durably execute a Run — `repo-init` end to end
The Operator starts a Run from New workflow with pre-flight and the whole plan visible, watches it on the Board and in the Run detail, and gets a compare link: the durable engine behind its port, the pure planner, the two status writers, every non-agent step kind, the repository lock and queue, restart recovery, cancel and retry. The first Run to reach `done` is `repo-init@1` initialising a Repository (UJ-1 edge case); `epic@1` plans and executes up to its first Story step.
**FRs covered:** FR-8, FR-9, FR-11, FR-12, FR-13, FR-20 (cancel, retry), FR-22, FR-23 (header, banner, Steps table, gate record), FR-24, FR-25 (queue), FR-30; FR-4 daily re-check; AR-8..AR-12 (non-agent kinds), AR-18 (signal endpoint, cancel, continue, retry), AR-19, AR-24; UX-DR2..UX-DR5, UX-DR7, UX-DR8, UX-DR9 (core), UX-DR14 (queue), UX-DR16, UX-DR17

### Epic 5: The unattended dev loop through Claude Code
An epic's Stories run to verified commits without anyone watching: the `agent` step with its prepare commits and prompt, the Claude adapter and its setup script, contract evaluation, protected paths, budget halt, one trace and one cost per Run through the Gateway, the harness readiness Run on the fixture Repository, and the trajectory record. Covers UJ-2 and SM-1 for `claude`.
**FRs covered:** FR-10, FR-14 (`claude`), FR-15, FR-16, FR-17 (halt), FR-26, FR-27, FR-28, FR-31 (checks), FR-32 (record), FR-33 (`claude`); FR-23 (Question, Stories strip, cost figures); AR-13..AR-17, AR-21, AR-23, AR-27; UX-DR9 (question block, cost), UX-DR8 (harness list)

### Epic 6: Human gates — answer, continue, skip, retry, accept, terminal
When a Run stops, one screen shows what it needs and every admitted action resumes it exactly once: Answer with archive and re-dispatch, Continue and Reject at checkpoints, inline spec editing, Skip story and Skip epic with re-baseline, Raise budget, Accept a protected-path change, the terminal resume command with its poll. Covers UJ-3 and SM-2.
**FRs covered:** FR-18, FR-19, FR-20 (skip story, skip epic), FR-17 (raise), FR-31 (accept), FR-21; FR-23 (Artifacts tree and editor); AR-18 (remaining signals, `PUT /runs/{id}/files`, `terminal_poll`); UX-DR9 (artifacts, editor), UX-DR10

### Epic 7: Codex and local harnesses, cost and time per Story
The same Story runs on Codex or on a local model through OpenCode, each behind its readiness Run, with its trace joined to the Run and its spend attributed, so cost, time, and outcome per Story can be compared per Harness (SM-3): the two adapters and setup scripts, per-harness tracing, the Runs history, and the trajectory export.
**FRs covered:** FR-14 (`codex`, `local`), FR-33 (`codex`, `local`), FR-27 (per-harness exporters), FR-25 (history), FR-32 (export); AR-14, AR-16 (codex, opencode); UX-DR14 (history)

### Epic 8: Run diagram and readout completions
The Operator reads a whole Run as a tree and the remaining SHOULD/COULD readouts land: the Run diagram, active Operator time, changed-since-last-opened marks, the Board LIST view, login lockout, and per-Project monthly spend.
**FRs covered:** FR-29, FR-23 (active time, changed marks), FR-22 (LIST), FR-1 (lockout), FR-28 (monthly figure); UX-DR11, UX-DR7 (LIST), UX-DR6 (lockout)

## Epic 1: Repository foundation, quality gates, and Operator login

A mandate and an opportunity: every later epic is built unattended by coding agents, and an agent can only be trusted with a story when the gates that decide "done" already exist and are green. This epic turns an empty repository into the two-component monorepo the spine describes, with its constitutions, layering linter, contract pipeline, test harnesses, containers, the instrument-dark shell, and the Operator's token login. After it, the Operator brings the stack up from a clone in under 30 minutes, logs in, and sees an empty Board.

### Story 1.1: Repository constitution and backend-api skeleton with layering gates

As the Operator who will hand every later story to a coding agent,
I want the repository to carry its constitutions, its configuration contract, and a backend-api package whose lint, type, layering, and unit-test gates already run green,
So that an agent's work can be judged by `make lint` and `make test` from the first story onward.

Brief: `epic-01-foundation/briefs/1-1-repository-constitution-and-backend-skeleton.md`

**Acceptance Criteria:**

**Given** a fresh clone with `uv` installed
**When** I run `make lint` and `make test`
**Then** both exit 0, running ruff check + format check, mypy strict on `domain/` and `application/`, import-linter, the env-contract check, and pytest on `backend-api/tests/unit`.

**Given** a test module under `backend-api/tests/unit/` that imports `sqlalchemy` from a file placed in `src/orchestrator/application/`
**When** `uv run lint-imports` runs
**Then** it fails naming the forbidden contract (the test creates the file in a temp copy or asserts the contract config through import-linter's API; the real tree stays clean).

**Given** a new field added to `Settings` without a line in `.env.example`
**When** `make lint` runs
**Then** the env-contract check fails and names the variable.

**Given** the app started with `uv run python -m orchestrator.main`
**When** `GET /healthz` is called
**Then** it returns 200 with JSON `{"status": "ok", "version": "<package version>"}` and `GET /openapi.json` returns the OpenAPI document.

**Given** the `Settings` model
**When** it is instantiated from the variables in `.env.example`
**Then** every variable of the spine's variable table that belongs to backend-api parses into a typed field (`ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SECRET_KEY`, `DATABASE_URL`, `DBOS_APPLICATION_VERSION`, `GITHUB_TOKEN`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LOCAL_MODELS`, `MAX_ACTIVE_RUNS`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_ENVIRONMENT`, `BMAD_VERSION`, `CLAUDE_CODE_VERSION`, `CODEX_VERSION`, `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION`, `CLAUDE_ALLOWED_TOOLS`, `WORK_DIR`, `AGENT_HOME`, `LOG_PROMPT_CONTENT_DEFAULT`, `LOG_LEVEL`, `BACKEND_API_PORT`), secrets typed as `SecretStr`.

**Given** the root `Makefile`
**When** a target's tooling does not exist yet (`e2e-ui` before 1.3, `up` before 1.6)
**Then** the target exists and exits non-zero with the message `not available until story <id>`; no target silently succeeds.

### Story 1.2: Database, migrations, bearer auth, and API conventions

As the Operator,
I want backend-api to talk to Postgres through one datasource with migrations applied at startup, to refuse every unauthenticated API call, and to answer errors in one machine-readable shape,
So that every later endpoint inherits authentication, persistence, and error conventions instead of re-deciding them.

Brief: `epic-01-foundation/briefs/1-2-database-auth-and-api-conventions.md`

**Acceptance Criteria:**

**Given** the app running against Postgres
**When** it starts
**Then** `alembic upgrade head` has run (a `alembic_version` row exists) before the first request is served, and the log line `migrations applied` carries the head revision.

**Given** any route under `/api/v1/`
**When** called without `Authorization`, with a wrong token, or with a token differing by one byte
**Then** it returns 401 `application/problem+json` with `title: "unauthorized"` and no other detail, and the comparison is constant-time (`hmac.compare_digest`).

**Given** `GET /api/v1/ping` (a minimal authenticated route kept for tests)
**When** called with the correct bearer
**Then** it returns 200 `{"pong": true}`.

**Given** a request body failing Pydantic validation on any route
**When** handled
**Then** the response is 422 `application/problem+json` with `errors[]` of `{path, reason}` and `detail` naming the first error.

**Given** `make e2e-api` with the `postgres` service and the app running
**When** it executes
**Then** an httpx scenario covers healthz, 401, and ping, and Schemathesis runs every operation from `/openapi.json` with the bearer and reports no 5xx.

**Given** a unit test suite run
**When** `make test` executes
**Then** it completes without a database or network (a fake unit-of-work exists in `tests/unit/fakes/db.py`).

### Story 1.3: Generated contract and web-client skeleton

As the Operator,
I want the API contract exported from the backend and the web-client scaffolded around generated types, a server-side proxy, and its own lint, unit, and end-to-end gates,
So that no TypeScript payload type is ever written by hand and the browser never holds a backend credential.

Brief: `epic-01-foundation/briefs/1-3-contract-pipeline-and-web-client-skeleton.md`

**Acceptance Criteria:**

**Given** the backend from 1.2
**When** `make openapi` runs
**Then** `contracts/openapi.json` is written and `web-client/src/api/schema.d.ts` is regenerated from it; running it twice produces no diff.

**Given** a hand edit to `schema.d.ts` or a backend schema change without regeneration
**When** `make lint` runs
**Then** the drift check fails naming the file.

**Given** a file under `src/islands/` that calls `fetch` or imports `src/api/server`
**When** `pnpm lint` runs
**Then** eslint fails on that line (covered by a fixture test in `tests/unit/lint.test.ts` that runs eslint on a temp file).

**Given** a request to `/api/ping` on the Astro server
**When** the proxy handles it
**Then** it forwards to `${BACKEND_API_URL}/api/v1/ping` with the bearer, streams status, headers, and body back unchanged, and the token appears in no response header, HTML, or client bundle (unit test with a mocked upstream; a bundle grep test).

**Given** `make lint`, `make test`, `make e2e-ui`
**When** run from a fresh clone with Node 24 and pnpm
**Then** eslint, prettier check, `tsc --noEmit`, `astro check`, Vitest, and a Playwright smoke test on `/` (placeholder page) all pass.

### Story 1.4: Design tokens and the instrument-dark shell

As the Operator,
I want every screen to render inside one severe, monospace, dark shell built from a single set of tokens and a small set of base components,
So that later screens are assembled from proven parts and the signal rule (one coloured element per row, none when nothing needs me) holds by construction.

Brief: `epic-01-foundation/briefs/1-4-design-tokens-and-shell.md`

**Acceptance Criteria:**

**Given** `tokens.css`
**When** the Vitest token test parses it
**Then** every colour, type role, spacing, and layout token above exists with the exact value, and the stylesheet set contains no `border-radius` other than `0` and no `box-shadow` other than the accent inset.

**Given** the contrast test
**When** it computes WCAG contrast for `--color-text` and `--color-text-secondary` against `bg`, `surface`, `surface-raised`, `surface-rail`
**Then** every pair is ≥ 4.5:1 and `--color-text-tertiary` ≥ 3:1 against `bg` and `surface`.

**Given** any of `/`, `/runs`, `/projects`, `/templates`, `/workflows/new`
**When** rendered
**Then** it shows the rail with the active item marked, a surface bar with the surface title, an `EmptyState` readout in the body (`NOTHING REGISTERED` on `/`, `NO RUNS` on `/runs`, `NO PROJECTS` on `/projects`, `NO TEMPLATES` on `/templates`), the footer readout `0 running · 0 queued / 0 need you / updated —`, and a Playwright assertion finds no element whose computed colour equals the amber or red token.

**Given** the `StatusToken` component
**When** rendered with each of `QUE RUN BLK CHK DON ERR CAN SKP`
**Then** it outputs a 7px square chip and the three-letter token in the same colour, green for `RUN`, amber for `BLK`/`CHK`, red for `ERR`, tertiary grey otherwise, with `data-token` set.

**Given** keyboard navigation on any page
**When** an element receives focus
**Then** the accent focus ring is visible (Playwright `toHaveCSS('outline-color', …)`).

### Story 1.5: Operator token login

As the Operator,
I want to enter the access token once and stay logged in for 30 days, with every page and every API call refused until I do,
So that the single credential of the instance is the only thing standing between the internet and my runs.

Brief: `epic-01-foundation/briefs/1-5-operator-token-login.md`

**Acceptance Criteria:**

**Given** no cookie
**When** I open `/`, `/runs`, `/projects`, `/templates`, or `/workflows/new`
**Then** I am redirected to `/login` with status 302.

**Given** no cookie
**When** the browser calls `/api/ping`
**Then** the proxy answers 401 `application/problem+json` and the upstream is not called (unit test with a mocked upstream).

**Given** the login page
**When** I submit a wrong token
**Then** the page re-renders at `/login` with the line `token rejected` in the red signal colour, the input empty, and no cookie set.

**Given** the login page
**When** I submit the correct token
**Then** the response sets `orch_session` with `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=2592000`, and redirects to `/`, which renders `NOTHING REGISTERED`.

**Given** a cookie whose signature was altered or whose issued-at is older than 30 days
**When** any page is requested
**Then** the request is treated as unauthenticated.

**Given** a valid cookie
**When** the browser calls `/api/ping`
**Then** the proxy forwards with the bearer and returns the backend's `{"pong": true}`.

### Story 1.6: Container images and the Compose stack

As the Operator,
I want `make up` on the Mac mini to bring up the whole MVP from a clone with one `.env`, with the three harness CLIs and the BMAD skill stubs already inside the backend image,
So that the stack exists once, is configured only by the environment, and a harness readiness run can be attempted the moment its adapter lands.

Brief: `epic-01-foundation/briefs/1-6-containers-and-compose.md`

**Acceptance Criteria:**

**Given** a clean clone and a filled `.env`
**When** `make up` runs
**Then** within 30 minutes on the Mac mini all three services are healthy, `curl localhost:8000/healthz` returns 200, and `http://localhost:4321/login` accepts the token.

**Given** the running backend container
**When** `docker compose exec backend-api sh -c 'id -un; claude --version; codex --version; opencode --version'` runs
**Then** it prints `agent` and the three pinned versions.

**Given** the running backend container
**When** `docker compose exec backend-api sh -c 'ls ~/.claude/skills/bmad-build-auto/SKILL.md ~/.agents/skills/bmad-build-auto/SKILL.md'` runs
**Then** both files exist and `~/.claude/settings.json` references `LITELLM_BASE_URL`'s value and the Langfuse OTLP endpoint but contains no key value other than the Basic auth header derived from the Langfuse keys.

**Given** `docker compose config`
**When** inspected
**Then** `web-client` has exactly the four variables above, both app services carry `cap_drop: [ALL]` and `no-new-privileges`, and volumes `work`, `agent-home`, `pgdata` are declared.

**Given** `docker compose exec backend-api scripts/harness/claude.sh doctor`
**When** the host gateway is reachable
**Then** it exits 0 printing the version, skill discovery, and gateway lines; when unreachable it exits non-zero naming the gateway.

**Given** `make down`
**When** run and then `make up` again
**Then** the database and the `work` and `agent-home` volumes persist.

### Story 1.7: CI pipeline and coverage gates

As the Operator,
I want every push to run lint, unit, API end-to-end, and UI end-to-end gates in that order with contract drift and coverage thresholds enforced,
So that a story built unattended is judged by the same gates I would run, and nothing merges green by accident.

Brief: `epic-01-foundation/briefs/1-7-ci-pipeline-and-coverage-gates.md`

**Acceptance Criteria:**

**Given** a push to any branch
**When** the workflow runs
**Then** four jobs run in dependency order (`lint`, `unit`, `e2e-api` with the `postgres` service and the backend started from source, `e2e-ui` with the built web-client and a stubbed backend), and the epic's final commit is green.

**Given** a commit that adds a `src` module without a test module, or that lowers `domain/` branch coverage below 100 %, or that edits `schema.d.ts` by hand
**When** the workflow runs
**Then** it fails at `lint`, `unit`, or `lint` respectively with the offending file named (verified once by a deliberately failing commit on a throwaway branch, then reverted).

**Given** `make lint`, `make test`, `make e2e-api`, `make e2e-ui` run locally
**When** compared with the workflow logs
**Then** they run the same commands.

## Epic 2: Projects and Repositories with the Clone check

A pain to prevent: a wrong URL or a token without access must fail at configuration time, not hours into a Run. This epic gives the Operator the Project (context text, encrypted agent environment variables, the content-logging switch) and its Repositories (default branch, commands, protected test globs), and runs the Clone check on every save so the Repository row states `ok`, `failed` with the verbatim git output, and the method version it carries. It realises user journey UJ-1 except repository initialisation, which needs Runs (Epic 4).

### Story 2.1: Project entity, API, and encrypted environment variables

As the Operator,
I want to create and edit a Project holding the context every agent reads, its agent environment variables, and the content-logging switch,
So that a Run can scope what its agents receive, and no secret of mine ever sits in the database in clear.

Brief: `epic-02-projects/briefs/2-1-project-entity-api-and-encrypted-env-vars.md`

**Acceptance Criteria:**

**Given** a valid create payload with two env vars
**When** `POST /api/v1/projects` is called with the bearer
**Then** it returns 201, the row's `env_vars_enc` values are Fernet tokens (not the plaintext), and the response shows `masked` ending with each value's last four characters.

**Given** a payload whose env var name is `GITHUB_TOKEN` or fails the name pattern
**When** posted
**Then** 422 problem+json names the path `env_vars[i].name` and the reason.

**Given** a stored Project with vars `A` and `B`
**When** `PUT` sends `[{name: "A"}, {name: "C", value: "x"}]`
**Then** `A` keeps its ciphertext unchanged, `B` is deleted, `C` is added, and `updated_at` changes.

**Given** two create calls with the same name
**When** the second is made
**Then** it returns 409 problem+json.

**Given** `LOG_PROMPT_CONTENT_DEFAULT=false`
**When** a Project is created without `log_prompt_content`
**Then** it is stored `false`, and `true` when the setting is `true`.

**Given** the e2e-api suite against the stack
**When** it runs
**Then** create → get → list → update round-trips succeed and Schemathesis reports no 5xx on the new operations.

### Story 2.2: Repository registration with commands and test globs

As the Operator,
I want to add Repositories to a Project with their default branch, package manager, the commands the dev loop will run, and the globs naming the tests agents must not touch,
So that a Run knows how to install, verify, and protect a repository before any agent is dispatched.

Brief: `epic-02-projects/briefs/2-2-repository-registration.md`

**Acceptance Criteria:**

**Given** a Project
**When** `POST /projects/{id}/repositories` is called with only `url` and `default_branch`
**Then** it returns 201 with `test_globs` equal to the three defaults, `verify_skipped: true`, `clone_check.status: "pending"`, and `package_manager: "other"`.

**Given** a payload with `test_globs: ["e2e/**"]`
**When** posted
**Then** the stored globs are the three defaults plus `e2e/**`, in that order, without duplicates.

**Given** a payload with `quality_gate_command: "make lint test"`
**When** posted then read
**Then** `verify_skipped` is `false`.

**Given** a second repository with the same URL under the same Project
**When** posted
**Then** 409 problem+json; the same URL under another Project is accepted.

**Given** `PUT /repositories/{id}` with a changed `default_branch`
**When** applied
**Then** the field updates and `clone_check` is unchanged (`pending` or the last result).

**Given** `GET /projects/{id}`
**When** the Project has two repositories
**Then** both are embedded with every field and `verify_skipped`.

### Story 2.3: Git port, base clone layout, and the Clone check

As the Operator,
I want every Repository checked when I save the Project and on demand: can the instance token reach it, does the default branch exist, which method version does it carry,
So that credential and URL problems surface at configuration time instead of hours into a Run (SM-5).

Brief: `epic-02-projects/briefs/2-3-git-port-and-clone-check.md`

**Acceptance Criteria:**

**Given** a Project saved with two Repositories, one reachable and one whose URL does not exist
**When** the save completes
**Then** the first Repository reads `clone_check.status: ok` with four lines and `bmad_version` set, the second reads `failed` with line 1 failed, the verbatim git output, and a non-empty `hint`; the Project and both Repositories are stored.

**Given** a Repository whose default branch is missing on origin
**When** `POST /api/v1/repositories/{id}/clone-check` runs
**Then** lines 1 and 2 are `ok`, line 3 is `failed` with `hint: branch … does not exist on origin`, `status: failed`.

**Given** a repository with `_bmad/_config/manifest.yaml` at `installation.version: 6.11.0` and `BMAD_VERSION=6.11.0`
**When** checked
**Then** `bmad_version` is `6.11.0`; with `BMAD_VERSION=6.12.0` it is `outdated`; without the file it is `missing`; `status` is `ok` in all three cases.

**Given** any git command run by the adapter
**When** the process environment and the filesystem under `/work` are inspected during and after the check
**Then** `GITHUB_TOKEN` appears in no file, no git config, no URL, and no log line; a failing command's stored output has the token value replaced by `***` if it ever appears.

**Given** `base` already exists from a previous check
**When** the check runs again
**Then** it fetches instead of cloning and line 2 says `fetched` with the seconds.

**Given** the unit suite
**When** run
**Then** the use case is covered on the fake `Git` for every branch above (ok, each failing line, each `bmad_version` value, existing base) without a network.

**Given** the e2e suite
**When** run
**Then** it creates a local bare repository with a `_bmad/_config/manifest.yaml` on `main`, registers it by `file://` URL, and gets `ok` with the version; a second registration with a wrong URL gets `failed`.

### Story 2.4: Projects list and detail screens

As the Operator,
I want to open Projects and see, for each Project, its context, its repositories with their method version and clone-check state, and its settings,
So that I can tell at a glance which repository is ready for a Run and which needs my attention.

Brief: `epic-02-projects/briefs/2-4-projects-list-and-detail-screens.md`

**Acceptance Criteria:**

**Given** two Projects, one selected by `?id=`
**When** `/projects` renders
**Then** the list shows both rows, the selected row is marked, and the detail shows title, meta line, context, repositories table, settings kv, and the runs readout, in that order.

**Given** a Repository with `clone_check.status: failed`
**When** rendered
**Then** its clone-check cell reads `failed · new runs blocked` in the red token colour, the verbatim output and the hint are shown in an inset block, and *re-run check* is present; clicking it calls the API and re-renders the row with the new result.

**Given** a Repository without `quality_gate_command`
**When** rendered
**Then** the command cell reads `— none declared` and the status cell reads `verify step will be skipped`.

**Given** a Repository with `bmad_version: missing`
**When** rendered
**Then** the method cell reads `missing` (no action yet).

**Given** no Projects
**When** `/projects` renders
**Then** it shows `NO PROJECTS` with the link to `/projects/new`.

**Given** a page with every repository `ok`
**When** the Playwright colour scan runs
**Then** no element uses the amber or red token.

### Story 2.5: New project and edit form with the live Clone check readout

As the Operator,
I want one form for a Project and its Repositories that keeps every value when something is wrong and shows the Clone check result per repository the moment I save,
So that configuring a project and finding out the token is wrong happen in the same minute (UJ-1).

Brief: `epic-02-projects/briefs/2-5-project-form-and-clone-check-readout.md`

**Acceptance Criteria:**

**Given** `/projects/new`
**When** I add two repositories, one env var, and save
**Then** the Project is created with both repositories, the page shows the **CLONE CHECK** readout for each with its four lines, and the URL is `/projects/{id}/edit?saved=1`.

**Given** a submission with an empty default branch on the second repository
**When** saved
**Then** the page re-renders with every value kept and the reason beside `repo-form-1-default-branch`; nothing is created.

**Given** a repository the token cannot reach
**When** saved
**Then** its readout block shows `ls-remote failed`, the verbatim git output in an inset block, the hint line, and `failed · new runs blocked`; the Project is saved anyway.

**Given** the edit page of a Project with a stored env var
**When** I save without touching it
**Then** the stored value is unchanged (the Action sends the entry without `value`); after *replace* and a new value it is updated and its mask changes.

**Given** a repository without `quality_gate_command`
**When** saved
**Then** its readout block ends with `verify step will be skipped`.

**Given** the form
**When** inspected
**Then** it has no token or gateway key field and shows the line `credentials are instance settings (.env)`.

## Epic 3: Templates: validated DSL, versions, and the rendered diagram

An opportunity to make the dev loop legible and editable without a visual editor: a Template is YAML written like a CI workflow, validated by one function, stored as immutable versions, and drawn from a graph the backend computes. This epic delivers that single validator and graph builder, the four shipped Templates (`repo-init`, `story`, `epic`, `initiative`), the versions API, and the Templates screen with its editor and diagram. Every later epic reads the validator and the graph; nothing else ever parses a Template.

### Story 3.1: DSL v1 parser and validator

As the Operator,
I want every Template I write checked against one small, explicit language before it can be saved or run, with each problem named by line and reason,
So that a Run can never start from YAML that means something other than what it says.

Brief: `epic-03-templates/briefs/3-1-dsl-v1-parser-and-validator.md`

**Acceptance Criteria:**

**Given** a minimal valid template (one `shell` step with a gate)
**When** validated
**Then** `errors` is empty, `unvalidated` is empty, and `template` holds the parsed tree with resolved kind metadata.

**Given** each of these inputs in its own test: an unknown top-level key; `version: "1"`; `version: "{{v}}"`; a step with both `uses` and `run`; `uses: rocket`; a `{{missing}}` in `with`; `{{repository.secret}}`; `{{story.title | upper}}`; two `for_each` at top level; a `for_each` nested in another; `parallel: 2`; a `template` call with `timeout_min`; a `template` call to a callee that does not exist; a callee input named wrongly; a callee `path` input bound to a `number`; a chain `a → b → c → d` (depth 4); `a → b → a`; a duplicate step id; `on_fail: {redispatch: verify, max: 1}` where `verify` is not an agent step; `gate: green`
**When** validated
**Then** exactly the expected reason appears, with the line of the offending node.

**Given** a template whose second step has no `gate`
**When** validated
**Then** `errors` is empty and `unvalidated` contains that step's path.

**Given** a template with three independent errors on different lines
**When** validated
**Then** all three are returned, sorted by line.

**Given** `run: "make test"` on a step
**When** parsed
**Then** the step is `uses: shell` with `with.command = "make test"`.

**Given** the coverage report
**When** `make test` runs
**Then** `validate.py` and `model.py` show 100 % branch coverage.

### Story 3.2: Shipped Templates `repo-init`, `story`, `epic`, `initiative`

As the Operator,
I want the dev loop and repository initialisation to ship as four readable YAML Templates that compose by call,
So that what runs is visible, versioned, and editable, and the planner of the next epic has something real to expand.

Brief: `epic-03-templates/briefs/3-2-shipped-templates.md`

**Acceptance Criteria:**

**Given** the four files
**When** each is validated with a fake repository containing the other three
**Then** every result has no errors and an empty `unvalidated` list.

**Given** `initiative@1`
**When** its calls are resolved
**Then** the call chain is `initiative → epic → story` at depth 3, and every callee input is bound with a matching type (`story: {{story}}` to an `item`, `epic: {{epic}}` to an `item`).

**Given** `story@1`
**When** parsed
**Then** it has no `git.worktree` step, `verify.on_fail` is `{redispatch: build, max: 1}`, `build.expect.files` has one glob, and `build.timeout_min` is 90.

**Given** `epic@1`
**When** parsed
**Then** it has exactly one `for_each` with `pause_after_item_when: story.done_checkpoint`, no `install` step, and `baseline.on_fail` is `fail`.

**Given** `repo-init@1`
**When** parsed
**Then** its branch literal is `chore/bmad-init` on `checkout`, `push`, and `link`, and it contains one `bmad.install` step.

**Given** the four files
**When** loaded through the YAML loader
**Then** each `version` is the integer `1` and each `name` equals the file stem.

### Story 3.3: Template versions API and seeding

As the Operator,
I want Templates stored as immutable numbered versions I can list, read, validate, and extend with a new version, with the four shipped Templates present from the first start,
So that a Run can pin exactly what it executes and a later edit can never change it.

Brief: `epic-03-templates/briefs/3-3-template-versions-api-and-seeding.md`

**Acceptance Criteria:**

**Given** an empty database and the four shipped files
**When** the app starts
**Then** `GET /templates` lists `repo-init`, `story`, `epic`, `initiative` each with `versions: [1]`, and a second start inserts nothing.

**Given** `GET /templates/epic/1`
**When** read
**Then** `calls` is `[{name: story, version: 1}]`, `called_by` is `[{name: initiative, version: 1}]`, `pinned_by` is `0`, and `inputs` lists eight inputs with their types.

**Given** valid YAML for `epic` with `version: 2`
**When** posted to `/templates/epic/versions`
**Then** 201 returns version 2, `GET /templates/epic/1` still returns the original YAML byte for byte, and the list shows `versions: [1, 2]`.

**Given** YAML with `version: 5` when the next number is 2, or with `name: story` posted under `/templates/epic/versions`
**When** posted
**Then** 422 problem+json with the reason.

**Given** invalid YAML
**When** posted to `/validate`
**Then** 200 with the errors listed by line; when posted to `/versions` → 422 with the same errors in `errors[]` and no row written.

**Given** a shipped file edited on disk to a new hash
**When** the app restarts
**Then** it is inserted as the next version and the previous version is unchanged.

### Story 3.4: Graph builder and template graph endpoint

As the Operator,
I want the backend to compute the shape of a Template version from the same parse the validator did,
So that the browser only draws, never interprets, and the diagram and the validator can never disagree.

Brief: `epic-03-templates/briefs/3-4-graph-builder-and-endpoint.md`

**Acceptance Criteria:**

**Given** `epic@1`
**When** its graph is built
**Then** nodes are `checkout`, `baseline`, `stories.story` (`call: {story, 1}`), `stories.after` (`kind: checkpoint`, `human: true`), `push`, `link`; the group `stories` has members `[stories.story, stories.after]`; edges are `checkout→baseline`, `baseline→stories.story`, `stories.story→stories.after`, `stories.after→push`, `push→link`.

**Given** `initiative@1`
**When** built
**Then** nodes are `epics.epic` (`call: {epic, 1}`) and `epics.after`; one group `epics`.

**Given** `story@1`
**When** built
**Then** `build` has `agent: true`, `gate: liveness`; `verify` and `commit_guard` are `deterministic`; `sync` precedes `build`.

**Given** `repo-init@1`
**When** built
**Then** five nodes in order with no group and no call.

**Given** a template whose step lacks `gate`
**When** built
**Then** that node has `gate: "unvalidated"`.

**Given** `GET /templates/epic/1/graph` with the bearer
**When** called
**Then** it returns the graph above; `GET /templates/epic/9/graph` returns 404.

### Story 3.5: Templates screen with versions list, editor, validate, and save

As the Operator,
I want to open any Template version, read and edit its YAML in the browser, see every validation error by line, and save my edit as the next version,
So that the dev loop is something I can read and change without touching the repository, and never something I can corrupt in place.

Brief: `epic-03-templates/briefs/3-5-templates-screen.md`

**Acceptance Criteria:**

**Given** `/templates`
**When** opened
**Then** it redirects to the latest version of the first Template by name, the versions list shows every version of every Template with `pinned by 0 runs` and the callers of callees (`story v1 · called by epic@1`), and the editor shows the YAML with line numbers.

**Given** the editor content with `parallel: 2` added and a `gate` removed
**When** *Validate* is clicked
**Then** the bar reads `1 errors` in red, the list shows `line {n} · parallel is reserved` and `unvalidated · {path}`, and the text is untouched.

**Given** valid edited content
**When** *Save as v2* is clicked
**Then** the browser navigates to `/templates/{name}/2`, the versions list shows v1 and v2, and v1's YAML is unchanged.

**Given** the version page
**When** rendered
**Then** the inputs table lists every input with type, required, and default.

**Given** the editor
**When** the cursor is inside a step mapping
**Then** that step's lines are highlighted; `uses:` values render in the accent colour.

### Story 3.6: Template diagram rendered from the backend graph

As the Operator,
I want the Template's graph drawn beside the YAML, left to right, updating each time the editor validates and holding the last valid picture when it does not,
So that I read the structure of a workflow at a glance without trusting the browser to interpret it.

Brief: `epic-03-templates/briefs/3-6-template-diagram.md`

**Acceptance Criteria:**

**Given** `/templates/epic/1`
**When** rendered
**Then** the diagram shows nodes `checkout`, `baseline`, `stories.story` (title `story@1`), `stories.after` (word `human`), `push`, `link`, left to right, with the dashed group `stories` around the two loop nodes, and no amber or red pixel.

**Given** the editor content changed to something valid with a new step
**When** validation succeeds
**Then** the diagram redraws with the new node within the same poll cycle and no `templates-diagram-stale` line is shown.

**Given** the editor content changed to something invalid
**When** validation fails
**Then** the diagram is unchanged and the line `diagram from last valid version` is shown.

**Given** a graph with an `unvalidated` node
**When** drawn
**Then** the node's footer reads `unvalidated` in plain text.

**Given** `story@1`
**When** drawn
**Then** the `build` node has the accent border and the eyebrow `agent`.

**Given** the backend
**When** `POST /templates/story/graph` is called with valid YAML text
**Then** it returns the graph; with invalid YAML it returns 422 with the validator's errors.

## Epic 4: Plan, start, and durably execute a Run: `repo-init` end to end

The vision to realise: a Run is planned completely before it starts, executed by a durable engine one row at a time, parked for the Operator only where declared, and visible as one honest readout. This epic builds that machine without the agent step: the domain model and its two status writers, the pure planner, pre-flight, the DBOS engine behind its port, the process, workspace, and git adapters, every non-agent step kind, the repository lock and queue, the signals endpoint with cancel, retry, and continue, and the screens that show a Run (New workflow, Board, Run detail, Runs queue). The first Run to reach `done` is `repo-init@1`, initialising a Repository for the method and returning a compare link.

### Story 4.1: Run domain model and status machines

As the Operator,
I want the Run, its planned Steps, their Attempts, and the gate record to exist as one precise model with transitions that are checked, not assumed,
So that every later story writes state through rules that cannot be bent by a router, an executor, or a screen.

Brief: `epic-04-runs/briefs/4-1-run-domain-model-and-status-machines.md`

**Acceptance Criteria:**

**Given** each valid `(status, event)` pair in the two tables
**When** the transition function is called
**Then** it returns the listed target; **and** for every pair not listed it raises `InvalidTransition` naming both (parametrised tests over the full product of statuses × events).

**Given** a `Run` created by the fake repository
**When** `update` is called with a changed `spend_usd` and `manual_estimate_h`
**Then** the fake stores the change (immutability of the estimate is enforced by the use case in 4.4, not here).

**Given** the SQLAlchemy models
**When** `alembic upgrade head` runs on an empty database and a Run with two rows and one attempt is inserted through the repositories
**Then** reads return equal entities (e2e-api test through a test-only fixture or the unit test marked `db` run in CI's e2e job).

**Given** the enums
**When** serialised to the API later
**Then** `needs_you` is the stored spelling (the UI maps it to `BLK`/`CHK`).

### Story 4.2: Pure planner `plan_run`

As the Operator,
I want the whole Run planned into rows from my branch at one commit before anything starts,
So that *What will run* is exactly what runs, and no later edit of the branch or the repository can change it.

Brief: `epic-04-runs/briefs/4-2-pure-planner.md`

**Acceptance Criteria:**

**Given** `repo-init@1` with a repository snapshot and `base_branch: main`, and a fake `Git` where `chore/bmad-init` does not exist
**When** planned
**Then** `plan_ref` is the base SHA and the rows are `plan, checkout, install, commit, push, link` with `seq` 1–6, gates `deterministic ×5, liveness`, `checkout.with_resolved = {base: main, branch: chore/bmad-init}`, `push.with_resolved.branch = chore/bmad-init`.

**Given** `epic@1` with a `stories.yaml` of three stories where story `2` has `done_checkpoint: true` and story `3` has a `done` story file, and `re_review_done` false
**When** planned
**Then** rows are `plan, checkout, baseline, stories[0].sync, stories[0].build, stories[0].verify, stories[0].commit_guard, stories[1].sync … stories[1].commit_guard, stories[1].after, stories[2].sync … (all skipped · already done), push, link`; labels read `story 1 · build`, `story 2 · done checkpoint`; `story_id` and `frame` are set on every story row.

**Given** the same with `re_review_done: true`
**When** planned
**Then** story `3`'s rows are `planned`, not skipped.

**Given** a repository without `quality_gate_command`
**When** `epic@1` is planned
**Then** `baseline` and every `verify` row are `skipped · no quality_gate_command`.

**Given** `initiative@1` with two epics on the same branch and eight stories
**When** planned
**Then** paths follow `epics[i].stories[j].<step>`, labels `epic 1 · story 4-1 · build`, each epic frame ends with `epics[i].push`, `epics[i].link`, and `epics[i].after` only when the epic declares `done_checkpoint`; the second epic's list file is read once.

**Given** a `stories.yaml` with ids `4-1` and `4-1-a`, or a missing `SPEC.md`-independent required field
**When** planned
**Then** a `PlanError{template, version, line, item, reason}` is raised naming the entry.

**Given** a step without `gate` in a custom template
**When** planned
**Then** its row has `gate: unvalidated`.

### Story 4.3: Pre-flight checks and the harness table

As the Operator,
I want every reason a Run could fail at start reported as a line before I click *Start run*, with the fix stated,
So that I never enqueue a Run that will stop on a configuration problem.

Brief: `epic-04-runs/briefs/4-3-preflight.md`

**Acceptance Criteria:**

**Given** a `repo-init` request on a Repository with `clone_check.ok`, a reachable origin, and no `chore/bmad-init` branch
**When** pre-flight runs
**Then** lines 1–3, 9 (`skip`), 11, 12 are present, line 3 reads `branch chore/bmad-init · will create from main`, `start_allowed` is true, `rows` has six entries, and `queue_note` is `starts immediately if the repository is free`.

**Given** an `epic` request where `stories.yaml` has ids `4-1` and `4-1-a`
**When** pre-flight runs
**Then** line 5 is `fail` naming the ids, `start_allowed` is false, and `rows` is null with `plan_error` set.

**Given** an `epic` request with `harness: claude` while `harness.enabled` is false
**When** pre-flight runs
**Then** line 8 is `fail · disabled: no readiness run` with its fix.

**Given** a non-terminal Run holding `feat/x` on the Repository
**When** pre-flight for `feat/x` runs
**Then** line 3 is `fail · held by run epic · feat/x` and `queue_note` names it.

**Given** `_bmad/_config/manifest.yaml` at `plan_ref` with version `6.10.0` and `BMAD_VERSION=6.11.0`
**When** an `epic` request runs
**Then** line 9 is `fail · outdated: 6.10.0` with fix `run Initialise repository and merge its branch`.

**Given** a request missing `repository_id`
**When** posted
**Then** 200 with every line `skip` and `start_allowed: false`.

### Story 4.4: Create and enqueue a Run

As the Operator,
I want *Start run* to persist the whole plan and put the Run in the queue behind its Repository, telling me whether it starts now or waits,
So that what I saw in *What will run* is exactly what the engine will execute, and two Runs never share a Repository.

Brief: `epic-04-runs/briefs/4-4-create-and-enqueue-a-run.md`

**Acceptance Criteria:**

**Given** a passing pre-flight for `repo-init@1`
**When** `POST /runs` is called
**Then** 201; the Run row exists with six `step_run` rows (`seq` 1–6, `plan` first, all `planned`), `pinned_versions = [{repo-init, 1}]`, `engine.enqueue` was called once with the Repository id, and `starts_now` is true.

**Given** a passing pre-flight for `initiative@1`
**When** created
**Then** `pinned_versions` is `[{initiative,1},{epic,1},{story,1}]` and `GET /templates/story/1` reports `pinned_by: 1`, `GET /templates/epic/1` `pinned_by: 1`.

**Given** a non-terminal Run on the same Repository
**When** a second Run is created
**Then** 201 with `starts_now: false` and `waiting: queues behind {label}`; the Run is `queued`.

**Given** a failing pre-flight line
**When** posted
**Then** 409 problem+json with the line texts in `detail` and no Run row written.

**Given** a plan error
**When** posted
**Then** 422 problem+json with `errors[]` carrying template, version, line, item, reason.

**Given** the unit-of-work fake
**When** the step-row insert raises
**Then** no Run row remains and `enqueue` is not called.

### Story 4.5: Status writers `start_attempt`, `apply_step_result`, `signal_run`

As the Operator,
I want every change of a Run's or a Step's status to go through three small, fully tested use cases and to leave a line in the gate record,
So that no action is ever applied twice or half-way, and the record on screen is the record of what happened.

Brief: `epic-04-runs/briefs/4-5-status-writers.md`

**Acceptance Criteria:**

**Given** a Run with rows `plan, checkout` and row 1 `queued`
**When** `start_attempt(run, 1)` runs
**Then** row 1 is `running` with Attempt `n=1`, the Run is `running`, and the gate record has `start`.

**Given** row 1 `running`
**When** `apply_step_result` receives `done`
**Then** row 1 is `done`, row 2 is `queued`, and no Run status change occurs; **and** when row 2 is the last and ends `done`, the Run is `done` with the `done` record.

**Given** a result with `park {plan_stale, "plan stale: stories.yaml"}`
**When** applied
**Then** the row is `error`, the Run `needs_you` with `park_kind plan_stale`, `park_path` the row path, and the record event `plan_stale`.

**Given** a `verify` result with `redispatch {target=build, max 1}` and `redispatch_count 0`
**When** applied
**Then** the `build` row is `queued`, its `redispatch_count` is 1, the record says `verify failed, story re-dispatched 1/1`; applied again with count 1 → park `verify_failed`, reason `verify failed 2/2`.

**Given** each row of the signal table, valid and invalid cases
**When** `signal_run` is called
**Then** valid cases write exactly the listed changes and call `engine.signal` when stated; invalid cases raise `Conflict` and write nothing (parametrised tests covering every row and every listed exclusion).

**Given** a cancelled Run
**When** a late `apply_step_result` arrives
**Then** nothing changes and a log line `late result ignored` is emitted.

**Given** `make test` with coverage
**When** run
**Then** the three use cases and `statuses.py` report 100 % branch coverage.

### Story 4.6: DBOS engine adapter and walker

As the Operator,
I want a Run to survive a restart or a container replacement and resume at the row it was on, and two Runs never to run on the same Repository,
So that I can walk away from a Run for days and trust that what completed stays completed.

Brief: `epic-04-runs/briefs/4-6-dbos-engine-adapter-and-walker.md`

**Acceptance Criteria:**

**Given** a Run created with rows `plan, checkout`… whose executors are fakes returning `done`
**When** enqueued on the real engine in the e2e stack
**Then** the walker runs rows in `seq` order, each row has exactly one Attempt, and the Run ends `done` with the `start` and `done` records.

**Given** an executor that returns a `checkpoint` park
**When** the walker reaches it
**Then** the Run is `needs_you`, the workflow is waiting in `recv`, `list_queue()` shows the Run as `pending` with position `None`, and `signal(run_id, continue)` resumes it within 5 s.

**Given** two Runs on the same Repository
**When** both are enqueued
**Then** the second stays `enqueued` (position 1) until the first is terminal; **and** given `MAX_ACTIVE_RUNS=2` and two Runs parked in `needs_you` on two Repositories, a third Run on a third Repository stays `enqueued`.

**Given** the backend killed (`SIGKILL`) while a row's executor is sleeping
**When** the backend restarts
**Then** rows completed before the kill are not re-executed (their Attempt count stays 1), the interrupted row gets Attempt 2, and the Run completes.

**Given** `cancel(run_id)` while the walker waits in `recv`
**When** called
**Then** the workflow ends within 5 s and a later fake result for that Run is ignored.

**Given** a Run parked with a `recv` timeout shortened to 5 s in a test configuration
**When** the timeout elapses
**Then** the Run is `failed` with reason `parked 30 days` and record `expired`.

**Given** `import-linter`
**When** run
**Then** `dbos` is imported only under `infrastructure/dbos/`.

### Story 4.7: Process runner, workspace, and the `plan.check`, `shell`, `checkpoint` kinds

As the Operator,
I want every command a Run executes to run in its own process group with a hard time limit and a log I can read, and the three simplest step kinds to exist,
So that a hung command can never hang a Run, and a stale plan or a declared checkpoint parks the Run exactly as promised.

Brief: `epic-04-runs/briefs/4-7-process-runner-workspace-and-basic-kinds.md`

**Acceptance Criteria:**

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

### Story 4.8: Git step kinds `git.worktree`, `git.sync`, `git.commit`, `git.push`, `pr.link`, `bmad.install`

As the Operator,
I want the git half of the dev loop to exist as six small executors over one Git port,
So that `repo-init` runs end to end, and the epic loop's checkout, sync, commit-guard, push, and compare link are ready for the agent step.

Brief: `epic-04-runs/briefs/4-8-git-step-kinds.md`

**Acceptance Criteria:**

**Given** a local bare "origin" with `main` and a Repository registered on it (no `chore/bmad-init` branch)
**When** a `repo-init@1` Run executes on the real engine in the e2e stack
**Then** rows `plan, checkout, install, commit, push, link` end `done` in order; `run.worktrees` has one entry with `created_branch: true, pushed: true`; the origin has `chore/bmad-init` with a commit `chore: initialise BMAD method (orchestrator)` containing `_bmad/` and the two `.gitignore` lines and no `.claude/` or `.agents/` folders; `run.compare_urls` holds the compare URL when the URL is a GitHub one (asserted with a `github.com` URL on the fake adapter in unit tests).

**Given** an existing clean worktree for the branch
**When** `git.worktree` runs
**Then** it is reused and the log says `reused worktree`; **and** a dirty one parks `misconfigured` with `worktree dirty: {path}`.

**Given** a Repository with `install_command: "false"`
**When** `git.worktree` runs
**Then** the row parks `misconfigured` with `install failed: exit 1` and the output is in the row log.

**Given** a branch created by this Run and never pushed
**When** `git.sync` runs
**Then** it records `no upstream · no-op` and ends `done`.

**Given** a worktree with no changes
**When** `git.commit` runs
**Then** it ends `done` with reason `no changes`; **and** with an untracked file it commits with the resolved message and `spec_folder` staged first (unit test on the fake asserting call order).

**Given** `git.push` with `branch == default_branch`
**When** executed
**Then** it parks `push_rejected` with `push refused: main is the default branch` and no push command runs.

**Given** a push rejected by the remote (non-fast-forward)
**When** executed, then `retry` is signalled
**Then** the first attempt parks `push_rejected` with the git output; the retry attempt fetches and fast-forwards first, then pushes.

### Story 4.9: Signals endpoint with cancel, retry, and continue

As the Operator,
I want one endpoint for every action on a Run, refusing what the Run's state does not admit and applying the rest exactly once,
So that cancelling, retrying, and continuing are as safe as reading.

Brief: `epic-04-runs/briefs/4-9-signals-cancel-retry-continue.md`

**Acceptance Criteria:**

**Given** a Run parked `plan_stale`
**When** `POST /runs/{id}/signals {kind: continue}` is called
**Then** 200, the `plan` row is `done`, the next row `queued`, the Run `running`, the record has `continue`, and the engine received the signal.

**Given** a Run parked on a `checkpoint` row
**When** `continue` is signalled
**Then** the row is `done`, the successor `queued`, and the walker proceeds (e2e).

**Given** a Run parked `push_rejected`
**When** `retry` is signalled
**Then** the row is `queued`, a new Attempt runs, and the record has `retry`.

**Given** a `running` Run with a live process and a worktree on a branch it created and never pushed
**When** `cancel {confirm: true}` is signalled
**Then** the process group is killed, the workflow is cancelled, the worktree directory is gone, the branch is deleted, planned rows are `skipped`, the Run is `cancelled`, and the record text names the worktree and branch; **and** with `pushed: true` the branch survives.

**Given** a `done` Run
**When** any signal is posted
**Then** 409 problem+json.

**Given** `answer` posted on a `blocked` Run in this epic
**When** validated
**Then** 409 with `detail: answer not available yet` (validation passed, effect absent).

**Given** `GET /runs/{id}` for a Run parked `push_rejected`
**When** read
**Then** `admitted_signals` is `[retry, skip_epic, cancel]`.

### Story 4.10: Initialise a Repository from the Project screen

As the Operator,
I want to click *Initialise repository* on a Repository whose method is `missing` or `outdated` and get a branch with `_bmad/` pushed and a compare link,
So that a repository is ready for the dev loop without my touching a terminal (UJ-1 edge case).

Brief: `epic-04-runs/briefs/4-10-initialise-repository.md`

**Acceptance Criteria:**

**Given** a Repository with `bmad_version: missing` and a passing clone check
**When** *Initialise repository* is clicked
**Then** a `repo-init@1` Run is created and the row reads `initialising · QUE` or `RUN` linking to `/workflows/{id}` (the Board card itself is 4.14's concern).

**Given** the Run reaches `done` on the e2e local remote
**When** the Project detail reloads
**Then** the method cell reads the installed version, the row shows the compare link, and the runs list shows the Run as `DON`.

**Given** a Repository whose clone check is `failed`
**When** the endpoint is called
**Then** 409 problem+json and the control is not rendered on the row.

**Given** a non-terminal `repo-init` Run for the Repository
**When** the endpoint is called again
**Then** 409 `initialisation already running`.

### Story 4.11: Queue read model and scheduled jobs

As the Operator,
I want to see the queue as the engine sees it, with the reason each Run waits, and to have stale worktrees and clone checks handled without me,
So that "why is nothing happening" has an answer on screen and the disk does not fill up.

Brief: `epic-04-runs/briefs/4-11-queue-read-model-and-scheduled-jobs.md`

**Acceptance Criteria:**

**Given** two Runs on Repository A (one running, one enqueued) and one Run parked on Repository B
**When** `GET /queue` is read
**Then** three rows: A's first with `reason: running` and `position: null`; A's second with `position: 1`, `reason: repository lock held by {label}`; B's with `position: null`, `reason: waiting for your answer`.

**Given** `MAX_ACTIVE_RUNS=2`, two active Runs on two Repositories, and a third enqueued on a third Repository
**When** read
**Then** the third's reason is `global concurrency, held by {label1}, {label2}`.

**Given** the `worktree_gc` job on the fake ports with a Run terminal 8 days ago and one terminal yesterday
**When** run
**Then** only the older Run's worktrees and logs are removed and `worktrees_removed_at` is set on it.

**Given** the `clone_check` job
**When** run with one Repository whose origin is now unreachable
**Then** its `clone_check.status` becomes `failed` and no Run status changes.

**Given** the app started in the e2e stack
**When** DBOS lists scheduled workflows
**Then** both jobs are registered with the configured crons.

### Story 4.12: Run read models for the board, the detail, and the run graph

As the Operator,
I want each screen to read one endpoint shaped for it,
So that the browser aggregates nothing and the Board, the detail, and the diagram can never disagree.

Brief: `epic-04-runs/briefs/4-12-run-read-models.md`

**Acceptance Criteria:**

**Given** Runs in every status including one `cancelled`
**When** `GET /runs?view=board` is read
**Then** each appears once in its column, the cancelled one under `failed` with `CAN`, `counts` are right, and a `needs_you` Run parked on a `checkpoint` has `CHK`.

**Given** an `initiative` Run with two epics and eight stories, three stories done, one epic pushed
**When** the board card is read
**Then** `progress` is `{1, 2, 3, 8, 1}` and `current_step_label` names the running row.

**Given** a Run with a row that has three attempts
**When** `GET /runs/{id}` is read
**Then** its `StepRow.attempts` is 3 and `latest.n` is 3 with the last 40 log lines; `admitted_signals` matches the park.

**Given** a `done` Run with one skipped story
**When** read
**Then** `summary.skipped` lists its id and `summary.links` the compare URLs.

**Given** an `epic` Run with rows in mixed states
**When** `GET /runs/{id}/graph` is read
**Then** groups carry statuses by the one rule (tested for each branch of the rule) and `current` is the park row; **and** a cancelled Run has `null` group statuses and root token `CAN`.

**Given** the contract
**When** `make openapi` runs
**Then** the three read models are generated into `schema.d.ts`.

### Story 4.13: New workflow screen with pre-flight and *What will run*

As the Operator,
I want one page where I bind a Template's inputs, watch pre-flight re-run on every change, read the whole plan, and start,
So that starting a Run is a decision made with everything in view (UJ-2).

Brief: `epic-04-runs/briefs/4-13-new-workflow-screen.md`

**Acceptance Criteria:**

**Given** `/workflows/new` with stubbed templates, projects, and harnesses
**When** opened
**Then** `initiative` is pre-selected, the initiative-folder input is shown, and switching to `epic` swaps it for working branch and spec folder; `repo-init` hides the harness list.

**Given** the harness list with `claude` disabled
**When** rendered
**Then** its line reads `claude · disabled: no readiness run · last readiness — · re-run readiness` and it cannot be selected.

**Given** a pre-flight response with one `fail` line
**When** rendered
**Then** the line shows `x`, its text and fix, *Start run* is disabled, and only the `x` is coloured.

**Given** a pre-flight response with rows
**When** rendered
**Then** the plan table lists every row with `plan` first and `skipped · already done` rows as plain words.

**Given** every line `ok` or `warn`
**When** *Start run* is clicked and the stub answers 201
**Then** the browser navigates to `/workflows/{id}`; with a 409 the detail is shown and the form is kept.

**Given** a reload of the page with a filled form
**When** the page loads
**Then** the form is restored from the query string and pre-flight re-runs.

### Story 4.14: Board with polling and the failed-fetch readout

As the Operator,
I want the home screen to show every Run as a card in the column of its status, refreshed without anything moving under my cursor, and to tell me plainly when it cannot reach the server,
So that coming back cold I see in one glance where everything is and what needs me (UJ-2, UJ-3).

Brief: `epic-04-runs/briefs/4-14-board-and-polling.md`

**Acceptance Criteria:**

**Given** a stubbed board response with Runs in every column and one `cancelled`
**When** `/` renders
**Then** five columns show the right counts and cards in the fixed field order, the cancelled card sits under Failed with `CAN · cancelled`, and clicking a card navigates to its detail.

**Given** `counts.running > 0`
**When** the page is open for 12 s (fake timers)
**Then** the endpoint is polled at 5 s intervals; with `running = 0` at 30 s; each response replaces the state with no CSS transition on cards.

**Given** the stub returns 500 on a poll
**When** it happens
**Then** the surface is replaced by the failed-fetch readout showing `GET /api/runs?view=board → 500` and *Retry*; after a successful Retry the board returns and polling resumes.

**Given** a board with no `needs_you` and no `failed` Runs
**When** scanned
**Then** no element uses the amber or red token; **and** with one `BLK` card older than 48 h both its token and its age are amber and nothing else is.

**Given** no Runs at all
**When** rendered
**Then** the body reads `NOTHING RUNNING`; with no Projects `NOTHING REGISTERED` linking to Projects.

**Given** `?project=<id>`
**When** the page loads
**Then** the filter is active and the request carries `project_id`.

### Story 4.15: Run detail core

As the Operator,
I want one screen for a Run that shows every planned step from the start, what stopped it and why, the record of every decision, and the actions the Run admits,
So that the Run detail is the only place decisions are made and nothing on it can look checked when it was not.

Brief: `epic-04-runs/briefs/4-15-run-detail-core.md`

**Acceptance Criteria:**

**Given** a stubbed detail with 12 planned rows, row 5 running
**When** rendered
**Then** all 12 rows are listed by path with tokens, row 5 is promoted, gate words are plain, and no cell other than tokens carries colour.

**Given** a Run parked `plan_stale`
**When** rendered
**Then** the banner reads `plan stale: stories.yaml`, the body shows the diff, and the buttons are exactly *Continue on the recorded plan* and *Cancel run*; clicking Continue posts the signal and the banner disappears after the next poll.

**Given** a Run parked `push_rejected` with `admitted_signals [retry, cancel]`
**When** rendered
**Then** the body shows the log tail and the resolve line; *Retry* posts `{kind: retry}`.

**Given** *Cancel run* clicked
**When** the modal is confirmed
**Then** the signal is posted with `confirm: true`; when dismissed nothing is posted.

**Given** a `failed` Run
**When** rendered
**Then** the banner is red, the log tail is shown, and the only control is `start a new run`.

**Given** a `done` Run with one skipped story and two links
**When** rendered
**Then** the summary line replaces the banner and lists the links and the skipped id; no amber or red pixel is present.

**Given** a skipped row with reason `no quality_gate_command`
**When** rendered
**Then** its status cell reads `SKP · skipped — no quality_gate_command` in grey.

### Story 4.16: Runs screen queue section

As the Operator,
I want to see the queue exactly as the engine holds it, with why each Run waits and for how long,
So that "the second run is waiting for the repository lock" is a line on a screen, not a guess.

Brief: `epic-04-runs/briefs/4-16-runs-screen-queue.md`

**Acceptance Criteria:**

**Given** a stubbed queue with an active Run, one waiting on the lock, one on global concurrency, and one parked
**When** `/runs` renders
**Then** four rows with positions `—, 1, 2, —`, reasons `running`, `repository lock held by …`, `global concurrency, held by …`, `waiting for your answer` (with the hint), and the section head shows the concurrency figure.

**Given** an empty queue
**When** rendered
**Then** the section reads `nothing queued`.

**Given** the page open with the poll store ticking
**When** the stub changes
**Then** the table updates on the next tick without animation.

### Story 4.17: Durability proof: restart and orphan test

As the Operator,
I want a repeatable test that kills the orchestrator in the middle of a Run and proves it resumes at the same row with exactly one process,
So that "runs survive restart" is measured (SM-4), not promised.

Brief: `epic-04-runs/briefs/4-17-durability-proof.md`

**Acceptance Criteria:**

**Given** the compose stack
**When** `make durability` runs
**Then** both scenarios pass with the assertions above, and the output prints the attempt table of each Run.

**Given** the CI workflow
**When** it runs on the epic's final commit
**Then** the durability marker runs in the `e2e-api` job (or a dedicated job) and passes.

## Epic 5: The unattended dev loop through Claude Code

The vision itself: a story-sized unit of work runs to a verified commit without anyone watching. This epic adds the one step kind that dispatches a coding agent — through the Claude Code harness first — and everything that makes its result trustworthy: the prepare commits that give the agent a clean tree, the prompt that names the skill and nothing else, the evaluation of the story file the agent writes, the protected-path check, the budget halt, one trace and one attributable cost per Run through the Gateway, the readiness Run that proves a harness before it is offered, and the trajectory record written once per done story. It realises user journey UJ-2 and success metric SM-1 for `claude`.

### Story 5.1: Harness port, environment contract, and the Claude adapter

As the Operator,
I want the orchestrator to drive Claude Code headlessly with exactly the environment the scripts declare and nothing of mine beyond it,
So that a story can be dispatched, resumed, and attributed to its Run without a credential ever leaking into an agent process.

Brief: `epic-05-dev-loop/briefs/5-1-harness-port-and-claude-adapter.md`

**Acceptance Criteria:**

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

### Story 5.2: Tracer port and the Langfuse adapter

As the Operator,
I want one trace per Run in Langfuse that holds every Step span and every model call the agents made,
So that a Run is one place to read, and cost, time, and outcome per story can be compared later (SM-3).

Brief: `epic-05-dev-loop/briefs/5-2-tracer-port-and-langfuse-adapter.md`

**Acceptance Criteria:**

**Given** `create_run`
**When** a Run is created with the fake tracer
**Then** `create_run_trace` was called with the Run id and tags, and `run.trace_id` is stored.

**Given** the walker executing a row
**When** the executor runs
**Then** a step span named by the path wraps the execution, and for an `agent` row an attempt span is opened whose `traceparent` appears as `TRACEPARENT` in the env the fake harness received (`00-{trace_id}-…-01` with the run's trace id).

**Given** the real adapter against a Langfuse test endpoint (e2e, `E2E_LANGFUSE=1`) `[ASSUMPTION: optional e2e when a Langfuse is reachable]`
**When** a `repo-init` Run completes
**Then** a trace with `session_id == run_id` exists holding one span per row, and `trace_url` opens it.

**Given** a Project with `log_prompt_content` false
**When** an agent env is built
**Then** no `OTEL_LOG_*` key is present; true → both present.

**Given** `attempt_observed` on the fake
**When** scripted true/false
**Then** readiness (5.8) can consume it (interface test only here).

### Story 5.3: Gateway spend adapter and the budget rule

As the Operator,
I want every attempt's cost and tokens read from the Gateway's own spend logs by the identifiers the call carried, and one small rule that says when a Run has spent more than its budget,
So that cost per story is a fact, not a harness's estimate, and no Run ever runs away.

Brief: `epic-05-dev-loop/briefs/5-3-gateway-spend-and-budget-rule.md`

**Acceptance Criteria:**

**Given** a stubbed spend endpoint returning three rows for the attempt (two models)
**When** `spend_for_attempt` is called
**Then** the sum and the per-model breakdown are right and `provisional` is false; **and** with an empty list or a connection error, `provisional` is true with zeros and a log line.

**Given** a provisional Gateway answer and `harness_usage` present
**When** `record_attempt_spend` runs
**Then** the attempt carries the harness figures with `cost_provisional = true`; a later call with Gateway rows replaces them and clears the flag; `run.spend_usd` is the sum over attempts both times.

**Given** `spend_usd 41.20` and `budget_usd 40.00`
**When** `budget.check` runs
**Then** it returns the park with reason `budget $41.20 / $40.00`; with `40.00 / 40.00` → `None`.

**Given** a Run with two story frames of two attempts each
**When** `GET /runs/{id}` is read
**Then** each story's `cost_usd` is its attempts' sum, `cost.spent_usd` the total, and `cost.provisional` reflects any provisional attempt.

**Given** the adapter's HTTP client
**When** any request is made
**Then** the bearer is `LITELLM_SPEND_KEY`, never `LITELLM_API_KEY`.

### Story 5.4: Agent executor: prepare and dispatch

As the Operator,
I want every story dispatch to start from a clean, committed tree with the project context written, a prompt that names the skill and nothing else, and every fact of the attempt recorded before and after the harness runs,
So that the agent can never refuse to start on a dirty tree, and nothing the orchestrator wrote is ever attributed to it.

Brief: `epic-05-dev-loop/briefs/5-4-agent-executor-prepare-and-dispatch.md`

**Acceptance Criteria:**

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

### Story 5.5: Agent executor: contract evaluation and routing

As the Operator,
I want the story file the agent wrote to be the only thing that decides what happens next, by rules I can read,
So that a harness's exit code, its output, or its mood never counts as done.

Brief: `epic-05-dev-loop/briefs/5-5-agent-executor-routing.md`

**Acceptance Criteria:**

**Given** a story file with `status: done`
**When** the tail runs
**Then** the result is `done` with gate `liveness` and no park.

**Given** `status: blocked` with `Blocking condition: intent gap` and questions listed
**When** the tail runs
**Then** the result is `blocked` with park `blocked` whose reason is the exact `## Auto Run Result` section text.

**Given** `status: blocked` with `Blocking condition: no subagents`
**When** the tail runs
**Then** the park is `misconfigured` with `harness misconfigured: no subagents`.

**Given** `status: ready-for-dev` and `spec_checkpoint: true`
**When** the tail runs
**Then** the result is `checkpoint` with reason `spec checkpoint`; with `spec_checkpoint: false` and `retry_count 0 < max 2` → `error` carrying the retry prompt; with `retry_count 2` → park `misconfigured · unexpected status: ready-for-dev`.

**Given** exit code 1 with a `done` file
**When** the tail runs
**Then** the retry path applies with reason `harness exit 1`.

**Given** zero, two, or an unparseable story file
**When** the tail runs
**Then** the parks are `no story file`, `ambiguous story file: a.md, b.md`, `no story file: frontmatter unreadable in a.md`; **and** on `retry` after the ambiguous case the older file is archived to `stories/.answers/` before dispatch.

**Given** a redispatched attempt after a verify failure
**When** the prepare phase runs
**Then** the story file has `status: in-progress` and a `## Verify Failure` section with the command, exit code, and log tail, committed in the prepare commit.

**Given** the coverage report
**When** run
**Then** `rules/routing.py` and the tail are at 100 % branch coverage.

### Story 5.6: Protected paths

As the Operator,
I want the spec, the epics list, every constitution, and every pre-existing test to be read-only to agents, checked deterministically after every attempt and at every commit-guard,
So that an agent can never make a gate pass by editing what the gate reads.

Brief: `epic-05-dev-loop/briefs/5-6-protected-paths.md`

**Acceptance Criteria:**

**Given** an attempt whose range modifies `specs/x/SPEC.md`
**When** the tail runs
**Then** the result parks `protected_path` with `protected path modified: specs/x/SPEC.md` and routing is not reached.

**Given** an agent that adds `web-client/AGENTS.md`
**When** checked
**Then** it is a hit (`added`).

**Given** `frozen_test_files = ["tests/a.py"]`, the agent modifies `tests/a.py` and creates `tests/new.py`
**When** checked on attempt 1
**Then** one hit (`tests/a.py`); on attempt 2 of the same frame, a modification of `tests/new.py` is not a hit and a deletion of `tests/a.py` is.

**Given** an operator commit `spec: operator edit (orchestrator)` between attempts that changed `SPEC.md`
**When** attempt 2's range is checked
**Then** no hit (the change is outside `start_sha..end_sha`).

**Given** `run.accepted_paths = ["tests/a.py"]`
**When** the same frame's later attempt modifies `tests/a.py` again
**Then** no hit.

**Given** `git.commit` with an uncommitted change to `stories.yaml`
**When** it runs
**Then** it parks `protected_path` and commits nothing.

**Given** `continue` on a `protected_path` park
**When** the agent executor resumes
**Then** no harness call is made, the tail re-runs over the previous attempt's SHAs with the accepted paths excluded, and routing proceeds on the story file as it is.

### Story 5.7: Budget halt in the loop

As the Operator,
I want a Run to stop before the next model call once it has spent more than I allowed, and to tell me the exact figures,
So that a Run can never exceed its budget by more than one attempt.

Brief: `epic-05-dev-loop/briefs/5-7-budget-halt.md`

**Acceptance Criteria:**

**Given** a routed `done` attempt whose spend brings `run.spend_usd` to 41.20 against a 40.00 budget
**When** the tail finishes
**Then** the result is `done` with park `budget · budget $41.20 / $40.00`; `apply_step_result` writes one `budget` record, the Run is `needs_you` with `park_kind budget`, and the verify row stays `planned`.

**Given** a routed `blocked` attempt over budget
**When** applied
**Then** two records are written in order (`blocked` then `budget`), `park_kind` is `budget`, and the row is `blocked`.

**Given** an attempt exactly at budget (`40.00 / 40.00`)
**When** checked
**Then** no park.

**Given** a harness result whose raw result marks a budget-cap stop
**When** the tail runs
**Then** the park is `budget`, `retry_count` is unchanged, and no `retry_auto` record exists.

**Given** a retry-path `error` (unexpected status) that is also over budget
**When** applied
**Then** the Run parks with `park_kind budget` and the row is `error` with no automatic retry.

### Story 5.8: Harness readiness

As the Operator,
I want a harness offered to me only after it has actually run one story to `done` on a fixture repository with its trace and its spend attributable,
So that "enabled" means proven, and a broken adapter or a changed version can never quietly eat a real Run.

Brief: `epic-05-dev-loop/briefs/5-8-harness-readiness.md`

**Acceptance Criteria:**

**Given** startup on an empty database
**When** seeding runs
**Then** Project `readiness` exists with `builtin: true` and its Repository's clone check is `ok` with `bmad_version == BMAD_VERSION`; `PUT /projects/{readiness id}` returns 409.

**Given** `POST /harnesses/claude/readiness`
**When** called
**Then** an `epic@1` Run is created on branch `readiness/claude/{date}` with the fixture spec folder, `skip_harness_check` bypassed the disabled line, and the Board shows it with `readiness` in place of progress.

**Given** a finished readiness Run whose attempt has a session id, a non-provisional spend with calls, an observed trace, a `done` story file, and a `done` verify row
**When** `evaluate` runs on the fakes
**Then** `claude` is `enabled` with `failing_check None` and `last_readiness_at` set; **and** with `attempt_observed` false, `enabled` is false and `failing_check` is `trace observed: no spans for attempt …`; each other line is tested failing alone.

**Given** `CLAUDE_CODE_VERSION` changed since the last start
**When** `sync_pins` runs
**Then** `claude` is disabled with `version pin changed: 2.1.258 → 2.1.260`.

**Given** the New workflow harness list after a failed evaluation
**When** rendered
**Then** the line reads `claude · disabled: trace observed: … · last readiness {time} · re-run readiness`.

### Story 5.9: Trajectory record

As the Operator,
I want one append-only record per done story capturing what ran, how many attempts, what the gates said, what it cost, and the story file as committed,
So that unattended completion and cost per harness (SM-1, SM-3) are computed from facts, and a future fine-tuning set has its trajectories.

Brief: `epic-05-dev-loop/briefs/5-9-trajectory-record.md`

**Acceptance Criteria:**

**Given** a frame whose build ended `done` after two attempts and whose verify ended `done`
**When** the verify result is applied
**Then** one trajectory row exists with two attempts, `gate_results.verify == done`, the story file text, `start_sha` of attempt 1 and `end_sha` of the commit-guard, cost and tokens summed, and `human_actions` empty.

**Given** a frame with a `blocked` stop answered by the operator
**When** recorded
**Then** `human_actions` lists the `blocked` park and the `answer` signal with times.

**Given** the same result applied twice (replay)
**When** the trigger runs again
**Then** the row is unchanged and no second row exists.

**Given** a frame whose verify is `skipped · no quality_gate_command`
**When** recorded
**Then** `gate_results.verify == skipped`.

**Given** the repository port
**When** inspected
**Then** it exposes no update or delete method.

### Story 5.10: Run detail additions for story steps

As the Operator,
I want a blocked story's question shown whole and attributed, the cost figures marked provisional until the Gateway confirms them, and the trace one click away,
So that coming back cold I read what the agent needs and what the Run has cost, without guessing (SM-2).

Brief: `epic-05-dev-loop/briefs/5-10-run-detail-story-additions.md`

**Acceptance Criteria:**

**Given** a stubbed detail parked `blocked` with a three-paragraph `## Auto Run Result`
**When** rendered
**Then** the question block shows the whole section with the eyebrow `Agent · claude · claude-opus-4 · {time}`, and the buttons are exactly the admitted signals from the stub.

**Given** a detail parked `misconfigured` with `no story file`
**When** rendered
**Then** the body shows the condition and the log tail and contains no textarea.

**Given** a step row whose latest attempt is provisional
**When** rendered
**Then** its cost cell reads `$1.23 provisional` and the cost kv reads `$12.30 / $40.00 provisional`.

**Given** `cost.trace_url` set
**When** rendered
**Then** the kv shows the `open in Langfuse` link; when null, no trace row.

**Given** the stories strip with states done, current, future, skipped
**When** rendered
**Then** each cell has the matching class and only the current cell uses the amber token.

### Story 5.11: Claude readiness passes end to end

As the Operator,
I want the `claude` harness to reach `enabled` on the real host Gateway and Langfuse, with every open day-1 question answered by that run and recorded,
So that the first real epic is dispatched to a harness that has already proven the whole chain once.

Brief: `epic-05-dev-loop/briefs/5-11-claude-readiness-end-to-end.md`

**Acceptance Criteria:**

**Given** the stack against the host services
**When** the readiness Run for `claude` completes
**Then** `GET /harnesses` shows `claude · enabled`, `last_readiness_at` set, and every evaluation line `ok`; the Board card reads `DON · readiness`; the Run detail's trace link opens a Langfuse trace with the attempt's Claude Code spans under the Run session; the attempt's cost is non-provisional.

**Given** the cap probe Run with `--max-budget-usd 0.01`
**When** it stops
**Then** the Run parks `budget` (not `misconfigured`), and the field that marked it is recorded in the addendum and used by 5.7.

**Given** `addendum.md` §B and `host/README.md`
**When** read
**Then** they contain the verified Claude block and the key commands, dated.

**Given** any fix made to 5.1–5.8
**When** `make lint test` runs
**Then** it is covered by a unit test and green.

## Epic 6: Human gates: answer, continue, skip, retry, accept, terminal

A pain to solve: a Run that stops is worthless unless one screen shows what it needs and one action resumes it exactly once. Epic 5 made Runs park with the right reason; this epic gives the Operator every admitted action and its screen body: Answer with archive and re-dispatch, Continue and Reject at checkpoints, inline editing of the spec while parked, Skip story and Skip epic with the re-baseline, Raise budget, Accept a protected-path change, and the terminal resume path with its poll. It realises user journey UJ-3 and success metric SM-2, and adds a scripted test harness so the whole loop is provable end to end without a model.

### Story 6.1: Answer a blocked story, with a scripted test harness

As the Operator,
I want to answer a blocked story from the Run detail and see the Run resume within seconds, with the mechanism stated in words above the button,
So that the intent gap an agent found costs me one paragraph, not a session (UJ-3).

Brief: `epic-06-human-gates/briefs/6-1-answer-and-test-harness.md`

**Acceptance Criteria:**

**Given** a Run parked `blocked` on story `4-1` after attempt 1, whose file's blocking condition is `intent gap`
**When** `answer {text: "Post to the project's channel only"}` is signalled and the executor resumes on the fakes
**Then** the file is at `stories/.answers/4-1-attempt-1.md` ending with `## Human Answer`, the time, and the text; the prepare commit contains the move; no `stories/4-1-*.md` exists at dispatch; the harness prompt ends with ` Answer from the operator to the blocking condition "intent gap": Post to the project's channel only`; the gate record has `answer` with the text.

**Given** the Answer box
**When** rendered on a `blocked` detail
**Then** the hint reads the verbatim line with the right file name, the button is disabled until text is typed, and clicking posts the signal.

**Given** the fake harness in test mode
**When** dispatched with a scenario `story_file: {status: blocked, blocking condition intent gap}` then, after an Answer, `story_file: {status: done}, commit: true, echo_prompt: true`
**Then** the first attempt parks `blocked`, the second reaches `done`, and the archived file and the new story file (with the echoed Answer suffix) exist on the branch (e2e on the compose stack with `ORCH_TEST_MODE=1`).

**Given** `answer` posted on a Run parked `timeout`
**When** validated
**Then** 409.

### Story 6.2: Continue and Reject at checkpoints

As the Operator,
I want to read the planned story spec inline at a spec checkpoint and either let the agent implement it or send it back with a reason, and to acknowledge a done checkpoint with one click,
So that the pauses I declared in `stories.yaml` are cheap to clear.

Brief: `epic-06-human-gates/briefs/6-2-continue-and-reject-at-checkpoints.md`

**Acceptance Criteria:**

**Given** a Run parked at a spec checkpoint on story `4-2` after attempt 1
**When** `continue` is signalled and the executor resumes on the fakes
**Then** no archive happens, the prompt has no `Halt after planning.` suffix, attempt 2 dispatches with a new session, and the gate record has `continue`.

**Given** the same Run
**When** `answer {text: "split the endpoint in two"}` is signalled
**Then** the file is archived with the reason, the prompt suffix reads `Answer from the operator to the blocking condition "spec rejected": split the endpoint in two` followed by ` Halt after planning.`, and the record has `answer`.

**Given** the spec-checkpoint detail
**When** rendered with a stubbed file
**Then** the story file content is shown inline with the eyebrow, *Continue* is primary, *Reject with a reason* reveals the textarea and hint, and the buttons match `admitted_signals`.

**Given** a done-checkpoint detail
**When** rendered
**Then** the summary line and *Continue* are shown; clicking posts `continue` and the Run resumes at the next story (e2e on the gates fixture, story `3`).

**Given** `GET /runs/{id}/files?path=../x`
**When** called
**Then** 422; a path outside the spec folder → 403.

### Story 6.3: Inline spec editing while parked

As the Operator,
I want to fix `SPEC.md` or a story file from the Run detail while the Run waits for me, with every save committed and named in the record,
So that a gap in the spec is closed where I read it, and the next attempt starts from my edit without it ever counting as the agent's.

Brief: `epic-06-human-gates/briefs/6-3-inline-spec-editing.md`

**Acceptance Criteria:**

**Given** a parked Run
**When** `PUT /runs/{id}/files {path: "specs/x/SPEC.md", content}` is called
**Then** the worktree file is written, a commit `spec: operator edit (orchestrator)` with only that path exists on the branch, the gate record has `spec_edit · edited specs/x/SPEC.md`, and the response carries the new mtime.

**Given** `path: "specs/x/stories.yaml"`
**When** put
**Then** 409 with `planned at {sha} — start a new run to change the list` and no write.

**Given** a `running` Run, or a parked Run with `terminal_session`
**When** put
**Then** 409 and no write.

**Given** an operator edit followed by the next agent attempt
**When** the protected-path check runs on that attempt
**Then** the operator's change to `SPEC.md` is not a hit (unit test over the fakes with the SHAs).

**Given** the artifacts tree on a parked detail
**When** a Markdown file is opened and edited
**Then** *Save* posts the PUT, the hint shows the commit line, and the tree's mtime updates; `stories.yaml` opens read-only with the planned line.

### Story 6.4: Skip story with the re-baseline

As the Operator,
I want to give up on one story and have the Run leave the tree green and committed before the next one starts,
So that skipping is honest: the story is listed as skipped, nothing half-done leaks into the next story.

Brief: `epic-06-human-gates/briefs/6-4-skip-story.md`

**Acceptance Criteria:**

**Given** a Run parked `blocked` on `stories[1].build` with rows `sync done, build blocked, verify planned, commit_guard planned, after planned`
**When** `skip_story` is signalled
**Then** `build` and `after` are `skipped · skipped by operator`, `verify` is `queued`, `commit_guard.with_resolved.message` is `story 2: skipped by operator`, the Run is `running`, and the record has `skip_story`.

**Given** the re-baseline passes on the fakes
**When** the walker continues
**Then** `commit_guard` commits (or records `no changes`) and `stories[2].sync` becomes `queued`.

**Given** the re-baseline fails
**When** applied
**Then** the Run parks `verify_failed · re-baseline failed after skip`, and `admitted_signals` is `[retry, skip_epic, cancel]`.

**Given** a frame whose verify was `skipped · no quality_gate_command`
**When** skipped
**Then** the `git.commit` row is queued directly.

**Given** a Run that finishes with one skipped story
**When** read
**Then** `summary.skipped == ["2"]`, the card reads `8/8 stories`, and the detail's compare line names the skipped id.

**Given** the detail
**When** *Skip story* is clicked and confirmed
**Then** the signal is posted; *Keep* posts nothing.

### Story 6.5: Skip epic

As the Operator,
I want to abandon the rest of an epic while still pushing what was done and getting its compare link, then move on to the next epic,
So that a bad epic does not hold the initiative hostage and nothing done is lost.

Brief: `epic-06-human-gates/briefs/6-5-skip-epic.md`

**Acceptance Criteria:**

**Given** an initiative Run parked `blocked` on `epics[0].stories[1].build` with stories 2–4 remaining
**When** `skip_epic` is signalled
**Then** the current frame is handled as skip story, every row of `epics[0].stories[2..3]` is `skipped · skipped by operator`, `epics[0].push`, `epics[0].link` stay `planned`, and after the re-baseline and commit-guard the walker runs push and link, then `epics[1].checkout`.

**Given** a Run parked `push_rejected` on `epics[0].push`
**When** `skip_epic` is signalled
**Then** `epics[0].push` and `epics[0].link` are `skipped`, `epics[1].checkout` is `queued`, and `summary.skipped_epics == [1]` at the end.

**Given** a Run parked `re-baseline failed after skip` on `epics[0].stories[1].verify`
**When** `skip_epic` is signalled
**Then** that verify row is `skipped`, the frame's `git.commit` is `queued`, and the epic proceeds to push.

**Given** a Run parked `budget`
**When** `skip_epic` is signalled
**Then** 409.

**Given** the detail
**When** *Skip epic* is clicked and confirmed
**Then** the signal is posted with the right confirm text per park kind.

### Story 6.6: Raise budget and Accept a protected-path change

As the Operator,
I want to raise a Run's budget and have it continue exactly where it stopped, and to accept an agent's change to a protected file when I judge it right,
So that the two stops that need my judgement rather than my text are one field or one click.

Brief: `epic-06-human-gates/briefs/6-6-raise-budget-and-accept.md`

**Acceptance Criteria:**

**Given** a Run parked `budget` on a `blocked` row
**When** `budget_raise {budget_usd: 60}` is signalled
**Then** `budget_usd` is 60, `park_kind` is `blocked`, the Run stays `needs_you`, no engine signal was sent, and the next detail read shows the Question body.

**Given** a Run parked `budget` on a `done` row
**When** raised
**Then** the Run is `running` and the walker continues at the verify row (e2e on the fake harness with a scenario `usage.cost_usd` above the budget).

**Given** `budget_usd: 30` with `spend_usd: 41.20`
**When** raised
**Then** 409 with the reason.

**Given** a Run parked `protected_path` with hits `[tests/a.py ~, AGENTS.md +]`
**When** `continue {files: [tests/a.py, AGENTS.md]}` is signalled and the executor resumes on the fakes
**Then** `accepted_paths` holds both, no harness call is made, the tail routes on the existing story file, and the record has `continue` with the files; **and** with a `files` list that does not match the hits → 409.

**Given** the protected-path detail
**When** rendered
**Then** each file shows its `+ − ~` and a diff link that opens the unified diff, and *Accept changes* posts the files.

### Story 6.7: Terminal resume command, session flag, and poll

As the Operator,
I want the exact command to pick up a story's session in a terminal, with the screen's actions held while I do, and the Run resuming by itself when I leave the story done and the tree clean,
So that the terminal is a real second path to unblock a story, visible to the record.

Brief: `epic-06-human-gates/briefs/6-7-terminal-resume.md`

**Acceptance Criteria:**

**Given** a Run parked `blocked` on a `claude` attempt
**When** the detail is read
**Then** `terminal.command` contains the eight identifier `-e` flags, no secret value, `sh -c` with the alias exports by name and `cd {worktree} && claude --resume {session}`, and `session_lifetime_ends_at` is start + 30 days.

**Given** the command block
**When** Copy is clicked
**Then** the clipboard holds the command, the button reads `COPIED` for about 1.2 s, and `terminal_start` is posted; the line and *Release* appear and the other buttons are disabled.

**Given** `terminal_session` true
**When** `answer` is posted
**Then** 409; `terminal_release` → 200 and the buttons return.

**Given** the poll job on the fakes with the story file `done` and a clean tree
**When** run twice
**Then** the first run sets `terminal_clean_polls = 1`, the second sends `terminal_resume`: the row is `done` with actor `terminal`, the Run is `running`, the successor queued; **and** a dirty tree between them resets the counter.

**Given** a `local` attempt
**When** the detail is read
**Then** `terminal` is null and the section is hidden.

### Story 6.8: UJ-3 proven end to end

As the Operator,
I want the whole "come back cold and unblock" journey exercised by tests that drive the real stack with a scripted harness,
So that the gates are known to work together, not one by one.

Brief: `epic-06-human-gates/briefs/6-8-uj3-end-to-end.md`

**Acceptance Criteria:**

**Given** the compose stack in test mode
**When** `make e2e-api` runs the `uj3` marker
**Then** scenarios A–D pass with every assertion above and print each Run's gate record.

**Given** `E2E_BACKEND=real`
**When** `make e2e-ui` runs the journey
**Then** it passes on the same stack.

**Given** any fix made along the way
**When** `make lint test` runs
**Then** it is unit-covered and green.

## Epic 7: Codex and local harnesses, cost and time per Story

An opportunity: the three-harness design exists to compare cost, time, and outcome per story across Claude Code, Codex, and an open-weight model served locally (SM-3). This epic adds the two remaining adapters behind the same port and the same readiness gate, joins their traces and spend to the Run the way each harness allows, and completes the two readouts that make the comparison readable: the Runs history and the trajectory export.

### Story 7.1: Codex adapter and script

As the Operator,
I want the same story dispatched to Codex CLI exactly as it is to Claude Code, through the same port and the same environment contract,
So that a harness is a choice on one screen, not a second orchestrator.

Brief: `epic-07-harnesses/briefs/7-1-codex-adapter.md`

**Acceptance Criteria:**

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

### Story 7.2: Codex readiness passes end to end

As the Operator,
I want `codex` proven on the real host: one story to `done`, its spans under the Run, its spend attributed,
So that the harness comparison (SM-3) has its second data point on a proven path.

Brief: `epic-07-harnesses/briefs/7-2-codex-readiness-end-to-end.md`

**Acceptance Criteria:**

**Given** the stack against the host services
**When** the `codex` readiness Run completes
**Then** `GET /harnesses` shows `codex · enabled` with every line `ok`, the trace holds the attempt's Codex observations (parented or session-level, as recorded), and the attempt's cost is non-provisional.

**Given** `addendum.md` §B
**When** read
**Then** it contains the verified Codex block with the trace decision.

**Given** any fix made to 7.1 or the tracer
**When** `make lint test` runs
**Then** it is unit-covered and green.

### Story 7.3: OpenCode adapter and script for local models

As the Operator,
I want stories dispatched to an open-weight model served on the Mac mini through OpenCode, with its calls found under the Run in Langfuse and its tokens recorded at zero cost,
So that a local model is a cost lever I can measure, not a guess.

Brief: `epic-07-harnesses/briefs/7-3-opencode-adapter.md`

**Acceptance Criteria:**

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

### Story 7.4: OpenCode readiness passes end to end with host model serving

As the Operator,
I want the local harness proven against a model actually served on the Mac mini, or the fallback recorded honestly,
So that the MVP's definition of done for `local` is met or explicitly deferred (PRD §6.1).

Brief: `epic-07-harnesses/briefs/7-4-opencode-readiness-end-to-end.md`

**Acceptance Criteria:**

**Given** the host services and the model server
**When** the `local` readiness Run completes
**Then** either `GET /harnesses` shows `local · enabled` with every line `ok`, or it shows `disabled: {first failing line}` and the addendum records the fallback decision with the evidence.

**Given** `host/litellm.config.yaml`
**When** read
**Then** it lists every `LOCAL_MODELS` alias with the chat-completions flag.

**Given** any fix made to 7.3 or the tracer
**When** `make lint test` runs
**Then** it is unit-covered and green.

### Story 7.5: Runs history

As the Operator,
I want every execution of every step, newest first, in one table with its harness, tokens, cost, and trace,
So that comparing harnesses on the same work is a scroll, not a query.

Brief: `epic-07-harnesses/briefs/7-5-runs-history.md`

**Acceptance Criteria:**

**Given** three Runs with twelve attempts across agent and git rows
**When** `GET /steps?limit=5` is read twice with the cursor
**Then** ten distinct rows arrive newest first, agent rows carry harness, session, tokens, cost, and non-agent rows carry nulls; the third page is empty with `next_cursor null`.

**Given** `?status=BLK`
**When** read
**Then** only attempts whose row ended `blocked` or `error` appear; `?harness=codex` only Codex attempts.

**Given** the Runs screen with a stubbed history
**When** rendered
**Then** rows show the ten columns, clicking one navigates to the Run detail scrolled to that step, and *more* appends the next page.

**Given** the detail opened with `#step-7`
**When** rendered
**Then** row 7 is scrolled into view and promoted briefly.

### Story 7.6: Trajectory export

As the Operator,
I want to download every done story's trajectory for a Project as JSON lines,
So that unattended completion and cost per harness are computed from the record, and a fine-tuning set can be built from it later.

Brief: `epic-07-harnesses/briefs/7-6-trajectory-export.md`

**Acceptance Criteria:**

**Given** a Project with three trajectories
**When** the endpoint is read
**Then** three lines arrive newest first, each parses as JSON with the fields above, and the headers carry the ndjson type and the attachment filename.

**Given** a Project with none
**When** read
**Then** 200 with an empty body.

**Given** the Project detail
**When** rendered
**Then** *Export trajectories* links to the proxy path, the hint is shown, and the count reads `3 trajectories`.

**Given** the proxy
**When** the download is requested from the browser (Playwright)
**Then** the file arrives with the filename and content.

## Epic 8: Run diagram and readout completions

A vision to complete: the Operator should read a whole Run as one tree, and every readout the PRD tiers as SHOULD or COULD should exist rather than be forgotten. This epic adds the run diagram view (the SHOULD that rides on the template graph), active Operator time (the measurement behind SM-2), changed-since-last-opened marks on the artifacts, the Board's LIST view, the login lockout, and per-Project monthly spend. Nothing here changes how a Run executes.

### Story 8.1: Run diagram view

As the Operator,
I want to switch the Run detail to a tree that shows what ran, where it is, and what is scheduled,
So that a two-epic, eight-story Run reads from start to finish in one picture that cannot disagree with the table.

Brief: `epic-08-readouts/briefs/8-1-run-diagram-view.md`

**Acceptance Criteria:**

**Given** a stubbed initiative graph with two epics, eight stories, story `4-1` blocked
**When** `?view=diagram` renders
**Then** the four column heads appear, the root shows the branch and `BLK`, epic 1's group reads `DON`, epic 2's group `BLK`, story `4-1`'s node is amber with `now` and its sub-step words, the other stories read `QUE`, and the footer reads `step 15 of 22 · epic 2 · story 4-1 · build · blocked 2d 04h · 5/8 stories`.

**Given** the same graph
**When** the Playwright colour scan runs
**Then** exactly one element uses the amber token in the tree (the current node's chip + token) and none the red.

**Given** a node click
**When** it fires
**Then** the URL becomes `?view=detail#step-15` and the Steps row 15 is in view.

**Given** a cancelled Run
**When** rendered
**Then** groups carry no token and the root reads `CAN`.

**Given** a reload with `?view=diagram`
**When** the page loads
**Then** the diagram view is active.

### Story 8.2: Active Operator time

As the Operator,
I want the Run to keep how long I actually spent on its detail,
So that cold-reload time (SM-2) is measured from facts across reloads and devices.

Brief: `epic-08-readouts/briefs/8-2-active-operator-time.md`

**Acceptance Criteria:**

**Given** a focused detail with fake timers
**When** 60 s pass with activity
**Then** one POST with `focused_seconds: 60` is sent and the store resets; after 6 idle minutes only the first 5 count.

**Given** the tab hidden
**When** time passes
**Then** nothing is counted; on `pagehide` the remainder is posted.

**Given** `POST /runs/{id}/activity {focused_seconds: 45}` twice
**When** applied
**Then** `active_seconds` is 90 and the cost block reads `00:01:30`.

**Given** `focused_seconds: 0` or `5000`
**When** posted
**Then** 422.

### Story 8.3: Changed-since-last-opened marks

As the Operator,
I want the artifacts tree to show which files changed since I last opened this Run,
So that coming back after two days I go straight to what moved.

Brief: `epic-08-readouts/briefs/8-3-changed-since-last-opened.md`

**Acceptance Criteria:**

**Given** a Run last opened at T and two files modified after T
**When** the detail is opened (`?opened=1`) and the tree is read
**Then** those two entries have `changed: true`, the others `false`, `last_opened_at` is now, and the tree shows the accent chip and promotion on the two files.

**Given** subsequent polls during the same visit
**When** the tree is re-read
**Then** the marks are unchanged.

**Given** a second opening later with no new changes
**When** the tree is read
**Then** no entry is `changed`.

### Story 8.4: Board LIST view

As the Operator,
I want the Board's Runs as record rows when there are too many cards to scan,
So that twenty or more Runs still read top to bottom like a log.

Brief: `epic-08-readouts/briefs/8-4-board-list-view.md`

**Acceptance Criteria:**

**Given** a stubbed board with Runs in every column
**When** LIST is selected
**Then** the rows appear grouped with heads in the order above, each with the seven fields, and the URL carries `?view=list`; selecting BOARD restores the columns without a new request.

**Given** a reload with `?view=list`
**When** the page loads
**Then** the list view is active.

**Given** a `BLK` Run older than 48 h
**When** listed
**Then** its token and age are amber and nothing else in the row is.

### Story 8.5: Login lockout

As the Operator,
I want repeated wrong tokens to be counted and, after five in fifteen minutes, refused for fifteen minutes,
So that the one secret of the instance cannot be guessed at leisure.

Brief: `epic-08-readouts/briefs/8-5-login-lockout.md`

**Acceptance Criteria:**

**Given** four wrong tokens in a minute
**When** the fourth response renders
**Then** the line reads `token rejected — 1 attempts left`.

**Given** a fifth wrong token
**When** submitted
**Then** the line reads `too many attempts — try again in 15 min`, the input is disabled, and a correct token submitted within the window is refused with the same line.

**Given** the window elapsed (fake clock)
**When** the correct token is submitted
**Then** login succeeds and the counter is cleared.

**Given** a correct token after two failures
**When** submitted
**Then** login succeeds and the next failure reads `4 attempts left`.

### Story 8.6: Per-Project monthly spend

As the Operator,
I want each Project to show what its Runs have cost this month, and the Projects list to show at a glance which Project has something needing me,
So that spend is visible where it is decided, even though it is not capped there.

Brief: `epic-08-readouts/briefs/8-6-project-monthly-spend.md`

**Acceptance Criteria:**

**Given** a Project with attempts costing 12.30 this month and 40.00 last month
**When** `GET /projects/{id}` is read
**Then** `monthly_spend_usd == "12.30"` and the meta line reads `this month $12.30`.

**Given** one provisional attempt in the sum
**When** rendered
**Then** the figure carries the word `provisional`.

**Given** Projects with a parked Run, a recently failed Run, and neither
**When** the list renders
**Then** the rows show `1 need you` in amber, `1 failed` in red, and nothing, respectively; the colour scan finds nothing else.

## Final Validation (2026-09-03)

- **Coverage.** Every FR-1..FR-33, NFR-1..NFR-9, AR-1..AR-27, and UX-DR1..UX-DR19 is named in the `requirements:` frontmatter of at least one brief and addressed by that brief's acceptance criteria (script-checked). Tier split respected: MUST items land in Epics 1–6, SHOULD in Epics 6–8, COULD in Epic 8.
- **Starter template.** None specified; Story 1.1 scaffolds the monorepo to the spine's Structural Seed and places the drafted constitutions, harness scripts, and `.env.example`.
- **Entities created when needed.** 1.2 baseline (no tables) → 2.1 `project` → 2.2 `repository` → 3.3 `template`, `template_version` → 4.1 `run`, `step_run`, `attempt`, `gate_record` (needed together by 4.2–4.5) → 4.3 `harness` → 4.7 `plan_files` → 4.11 `worktrees_removed_at` → 5.9 `trajectory` → 6.7 `terminal_clean_polls` → 8.3 `last_opened_before`.
- **Forward dependencies.** A scan of every brief for references to later stories found only scope exclusions ("Out: …"), version numbers, and seams where a later story consumes what an earlier one produces; the one acceptance criterion that depended on a later story (4.10 on the Board of 4.14) was rewritten. Each story is completable on the previous ones alone.
- **Epic independence.** Epic 2 stands on Epic 1; Epic 3 on 1–2; Epic 4 delivers `repo-init` end to end without the agent step; Epic 5 delivers unattended completion with parks but without resumes; Epics 6–8 add actions and readouts only.
- **File churn, considered and accepted.** `RunDetail` (4.15, 5.10, 6.x, 8.x), `steps/agent.py` (5.4–5.7), `signal_run` (4.5, 6.x), and `graph.py` (3.4, 4.12) are touched by several epics. The split follows real risk boundaries (engine before agent before human gates) and keeps each story inside one unattended agent's context; consolidation into one 36-story epic was rejected because it would remove the per-epic compare link, done checkpoint, and retrospective.
- **Story sizing.** 66 stories; briefs of 50–110 lines with exact rules inlined; spec checkpoints only on the twelve architecture-deciding or host-dependent stories (2.3, 3.1, 4.2, 4.5, 4.6, 5.1, 5.4, 5.11, 6.1, 7.1–7.4); `done_checkpoint` at every epic's last story and in `epics.yaml`.
- **Layout.** `epics.yaml` (initiative list) + `epic-0N-<slug>/{SPEC.md, stories.yaml, briefs/, stories/}`; every `invoke_dev_with` names an existing brief by repository-relative path; every `stories.yaml` passes the schema rules (quoted, prefix-free ids; no `status` field).
