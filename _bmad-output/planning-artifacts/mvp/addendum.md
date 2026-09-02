# Addendum — AI Orchestrator MVP

Depth that belongs downstream (architecture, solutioning, stories) or that earned a place but is not a requirement. The PRD states *what*; this file records *how* and *why not otherwise*. The binding technical contract is `architecture/ARCHITECTURE-SPINE.md` (2026-09-02, `AD-1..AD-20`), which supersedes `../v1-dev-loop-2026-08-26/architecture-v1.md`; full rationale and research citations are in `../v1-dev-loop-2026-08-26/challenge-v1.md` and `architecture/research/`. This addendum does not duplicate them; it indexes and adds what the PRD conversation surfaced. Updated 2026-09-02 to match the spine.

## A. Technology decisions (pointers)
| Concern | Decision | Where |
|---|---|---|
| Durable engine | DBOS (Python) on the same Postgres, behind a `WorkflowEngine` port with opaque engine references, so a different engine is a new adapter only; the walker executes pre-planned `step_run` rows in order; human waits are `recv` on a per-Run topic; queue partitioned by Repository (`partition_concurrency=1`, `global_concurrency=2`); scheduled jobs (daily clone check, worktree GC, terminal poll) through the same port | spine AD-6, AD-7, AD-12 |
| Backend | Python 3.14, FastAPI + DBOS in one process, SQLAlchemy, Alembic, Pydantic, PyYAML; strict clean architecture (domain ← application ← api, infrastructure ← main) enforced by import-linter | spine AD-2, Stack |
| Contract | Pydantic schemas are the single source; OpenAPI exported to `contracts/openapi.json`; TypeScript types generated, never hand-written | spine AD-3 |
| Front-end | Astro 7 SSR on Node 24 with React islands, nanostores polling, CodeMirror 6, dagre layout; the browser talks only to the Astro server, which proxies to the backend with the bearer token | spine AD-1, Stack |
| Gateway | LiteLLM on the host; one instance key; attribution by tags + Langfuse session (Run id) + Gateway end-user (Run id) and session (Attempt id); spend read from `/spend/logs/v2`; `langfuse_otel` callback with `LITELLM_OTEL_V2=true`; local models as `openai/<alias>` with `use_chat_completions_api: true` so Codex's `/v1/responses` bridges | spine AD-11, research/spend.md |
| Tracing | Langfuse OTLP `/api/public/otel` (HTTP/protobuf, traces only); Run trace id seeded from the Run id, session id = Run id; Claude Code and Codex spans via inbound `TRACEPARENT` (native OTLP); OpenCode via the Langfuse plugin, session/user id only | spine AD-11, research/tracing.md |
| Method | BMAD pinned in the image (skill stubs under the agent home for every harness); target repositories commit `_bmad/` only; `repo-init@1` initialises them | spine AD-16 |
| Local models | oMLX on the host; Qwen3.8-27B 4-bit (coder, pinned), Qwen3.6-35B-A3B 4-bit (general, LRU); wired GPU limit raised to ~42 GB | challenge-v1 §6 |
| Containers | two (`web-client`, `backend-api`) plus Postgres in one compose file; backend non-root, `cap-drop ALL`, `no-new-privileges`, tooling: git gh node uv claude codex opencode bmad; per-harness `install · configure · doctor` scripts; every setting from `.env` | spine AD-20, Structural Seed |

## B. Harness matrix (from documentation, 2026-08-26)

> **Status: to be re-verified from each harness's own documentation when its adapter is built.** These CLIs change between releases — the 2026-08-26 pass already found `--full-auto` deprecated in Codex and `wire_api = "chat"` removed. Treat every flag below as a starting point, never as a contract; the contract is FR-14's capability list. **Codex and OpenCode technical details are deliberately deferred** (PRD §8).

**One item is confirmed by direct observation and is not provisional:** Claude Code 2.1.246 `-p --bare` exposes exactly `Bash, Edit, Read` — no subagent tool, no `Write`, no `Skill` — and neither `--add-dir` nor `--tools default` restores them, while default discovery exposes `Task`, `Write`, and `Skill`. `--bare` cannot run `bmad-build-auto`. Use default discovery with an explicit allowlist plus `--disallowedTools "mcp__*"` (a container has no personal MCP connectors, but the exclusion should be explicit).

See challenge-v1 §5 for the full table with doc citations. Facts that changed since the 2026-08-24 PRD's addendum and matter for stories:
- Codex `wire_api` accepts only `responses`; `--full-auto` is deprecated; `codex exec` is always approval `never`; `[otel]` now has separate `trace_exporter`; skills are read from `.agents/skills`; session ids cannot be pre-assigned.
- Claude Code: the docs recommend `--bare` for scripted calls — **do not follow that here** (see above); `.agents/skills` is **not** read; OTLP traces are beta behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`.
- OpenCode reads both `.claude/skills` and `.agents/skills`; `opencode run --format json --session <id>` (no `--auto` flag: auto-approval is config-driven through `opencode.json` permissions); provider config supports `headers` with `{env:NAME}` references; tracing through `@langfuse/opencode-observability-plugin`.
- Per-harness setup scripts (`scripts/harness/{claude,codex,opencode}.sh`, drafted in `architecture/deliverables/`) are the place these facts land; each writes its harness's static config from environment variable names only.
- LiteLLM: `/v1/messages` translation to any provider, Anthropic-native `/v1/models` for Claude Code gateway model discovery, header-driven Langfuse metadata (`langfuse_*`, `x-litellm-tags`, `x-litellm-session-id`), tag budgets via `/tag/new`.

## C. Rejected alternatives (MVP)
| Rejected | Why |
|---|---|
| JSON-schema structured output as the agent contract | Only Claude Code and Codex support it; the Story file frontmatter is what `bmad-build-auto` already writes and is Harness-independent. |
| Terminal `--resume` as the primary reply path | Claude/Codex only; depends on harness-local session content; invisible to the gate record. Kept as secondary. |
| Pipeline-stage board columns (Spec → Plan → Build → Review → Merged) | One dev loop; stage lives on the card; status columns put attention where it belongs. |
| Global serialization (one Run at a time) | Existed only for a shared E2E database that is out of scope. Repository-partitioned queue instead. |
| Visual workflow editor | A product in itself; YAML + rendered diagram covers the need. |
| Codex or Claude Code pointed at LiteLLM for local models instead of a third Harness | Kept as fallbacks (in that order) if the OpenCode adapter slips; OpenCode's skill discovery and chat-completions provider make it the better default. |
| Notifications inbox screen | Redundant for one operator; "Needs you" column + rail count. |
| Gateway virtual key per Project (`/key/generate`, monthly budget) | Dropped 2026-09-02: one instance key and identifier-based attribution give the same per-Run and per-Attempt figures without key management; per-Project budgets are deferred (spine AD-5, AD-11). |
| Global BMAD install in the image | Impossible: the method's scripts need `_bmad/` in the target repository. Skill stubs live in the image, `_bmad/` in the repository, `repo-init@1` puts it there (spine AD-16). |
| One endpoint per Operator action | Replaced by one `signals` endpoint with an enumerated kind, so every action shares one validation, one gate-record write, and one resume path (spine AD-13). |
| Steps created as the Run progresses | Replaced by planning every row before enqueue: "What will run" and the Run diagram are the same data as execution (spine AD-7). |

## D. Mechanisms (for solutioning)
- **Story-file evaluation** after a Story step: glob `{spec_folder}/stories/{id}-*.md`; exactly one match; parse YAML frontmatter; route on `status`; the whole `## Auto Run Result` section is shown as the Question (PRD FR-16).
- **Answer (revised at PRD finalization):** `git mv stories/{id}-{slug}.md stories/.answers/{id}-attempt-{n}.md`, append `## Human Answer` with timestamp and text, commit-guard; then dispatch folder+id again — with no `stories/{id}-*.md` present this is a *first dispatch*, so step-02 plans fresh — with the prompt suffix `Answer from the operator to the blocking condition "{condition}": {answer}`. Rejected: appending `## Human Answers` and resetting to `draft` — step-02 preserves the old `<intent-contract>` verbatim on a draft resume and the template has no such section, so the Answer would be overwritten or ignored.
- **Spec checkpoint:** dispatch prompt ends with "Halt after planning."; agent stops at `ready-for-dev`; Continue re-dispatches without the phrase; `bmad-build-auto` routes `ready-for-dev` straight to implementation.
- **Repository lock:** the engine port's partition key (`enqueue(run_id, partition_key=repository_id)`), held for the Run's whole life including `needs-you` — a workflow parked in `recv` still occupies its partition, which is exactly the lock. No release-on-park; rejected because it would require ending and re-enqueueing the workflow and would let two Runs share one Repository's worktrees (spine AD-12).
- **Planned rows:** `plan_run(template_version, inputs)` is pure, reads list files and callee versions from the remote branch at one SHA (`plan_ref`), and returns rows `{seq, path, kind, gate, status, with_resolved}`; `create_run` persists them before enqueue; pre-flight renders the same output without persisting (spine AD-7).
- **Two status writers:** `apply_step_result` for every execution transition, `signal_run` for every Operator transition; executors return results and never touch status (spine AD-8).
- **Signals:** `POST /runs/{id}/signals {kind, payload}`; validity per current status, gate-record write, and the worktree effect of each kind are the table in spine AD-13. Inline spec edits: `PUT /runs/{id}/files` (spec folder only, `needs_you`, not during a terminal session) committing `spec: operator edit (orchestrator)`. Active time: `POST /runs/{id}/activity {focused_seconds}` batched every 60 s into `run.active_seconds`.
- **Budget:** `Gateway.spend_for_attempt(run_id, attempt_id)` reads `GET /spend/logs/v2?end_user=<run_id>&session_id=<attempt_id>` after each Story step Attempt; `run.spend_usd` is the sum over Attempts (spine AD-11).
- **Protected paths:** `rules/protected_paths.check` on `Git.diff_names(attempt.start_sha)` after the harness exits and in the commit-guard against the frame's start SHA; `start_sha` is HEAD after the WIP commit *and* the prepare commit (see §I); the frozen test-file set is taken at the Story frame's first Attempt (spine AD-17, amended per §I).
- **Cancel rollback:** `git worktree remove --force` for every entry of `run.worktrees[]`; `git branch -D` only when that entry's `created_branch && !pushed`.
- **Credentials:** `GITHUB_TOKEN` per git command via `GIT_ASKPASS`; harness processes get exactly `HARNESS_ENV_CONTRACT` plus the Project's Fernet-decrypted env vars (spine AD-5, AD-10).

## E. FR lineage to the 2026-08-24 PRD
(ids below are the 2026-08-24 PRD's ids → this PRD's ids.) Kept in spirit: FR-1..5 (onboarding) → FR-2..4; FR-6..12 (templates, versioning, pinning) → FR-5..7; FR-13..18 (durable execution, park, resume, retry, cancel) → FR-12, FR-19, FR-20; FR-20..26 (agent tasks, session ids, per-task records) → FR-14, FR-16; FR-27/28 (gate strength, never green without oracle) → FR-16, NFR-2; FR-43..45 (trace, cost, budget) → FR-17, FR-26..28; FR-47/48 (serialization) replaced by FR-13. Dropped for MVP: FR-24a, FR-28b, FR-29, FR-12a/12f, FR-30/30a/31, FR-33..37, FR-38..42 (PR creation is a link), FR-46, FR-50..52 (only the manual-estimate capture survives), F9 entirely.

## F. The week (from challenge-v1 §7)
Day 1 infra + skeleton + the shipped Template YAML (`repo-init`, `story`, `epic`, `initiative`) · Day 2 Projects/Repositories/Clone check · Day 3 interpreter + Claude adapter + Board/New workflow · Day 4 Codex + OpenCode adapters + tracing + budget + queue + Run detail · Day 5 checkpoints, verify retry, cancel + Runs/Templates screens · Day 6 hardening + restart test + states · Day 7 dogfood on `fullstack-app`. Slips first: as PRD §6.1.

## G. Corrections surfaced at PRD finalization (applied in the spine 2026-09-02)
Every item below was taken up by `bmad-architecture`; the note in brackets says where it landed.
- **The agent commits:** `bmad-build-auto` step-04 commits reviewed work and halts `done` only on a clean tree; step-01 halts `blocked` on a dirty tree. The loop is therefore build (agent commits) → verify (deterministic, on the committed tree) → commit-guard (orchestrator commits leftovers only). [`story@1` Template, spine AD-9]
- **Dirty-tree pre-dispatch rule:** Before any Story step attempt: `git add -A && git commit -m "wip: story {id} attempt {n} (interrupted)"` when the Worktree is dirty (FR-12). [`steps/agent.py`; `attempt.start_sha` is taken after this commit and the prepare commit of §I — spine AD-17]
- **Step timeouts:** `timeout_min` per Step in the Template schema (defaults 90 / 30 / 5); process kill → Step `error` → Run `needs-you` (FR-10). [The `ProcessRunner` port owns the timer; the engine never times a step — spine AD-14. Earlier wording "the DBOS step wrapper owns the timer" is withdrawn.]
- **Done checkpoint mechanism:** `pause_when` cannot hang off the `agent` Step alone. [`for_each` carries `pause_before_item_when` / `pause_after_item_when`; the planner turns them into `checkpoint` rows at `…stories[n].before` / `…stories[n].after`; the spec checkpoint stays a status of the `agent` row — spine AD-7, AD-9]
- **Budget check timing:** After each Story step attempt, before verify (FR-17). The Claude adapter additionally passes `--max-budget-usd = remaining budget` as a harness-local cap; Codex/OpenCode have no equivalent, so the Gateway sum is the contract. [spine AD-10, AD-11]
- **Daily Clone check:** a scheduled job. [`engine.schedule(name, cron, job)` on the engine port; DBOS `create_schedule` in the adapter — spine AD-6, AD-14]
- **Worktree retention, PR link:** as PRD FR-9 and FR-11. [`worktree_gc` job; `pr.link` kind appends compare URLs per epic — spine AD-14]
- **Verify failure re-dispatch:** append `## Verify Failure` (command, exit code, output tail) to the Story file, set `status: in-progress` → `bmad-build-auto` step-01 routes `in-progress` to step-03 (implement → verify → review). Rejected: re-dispatching a `done` file (routes to a review pass that never sees the failure) and a freeform fix prompt (its spec lands outside the Spec folder). [`on_fail: {redispatch, max: 1}` on the verify Step — spine AD-9]
- **Skip:** the frame's remaining agent/checkpoint rows are marked skipped, its verify row runs as the re-baseline, its commit-guard commits `story {id}: skipped by operator`; no reset to a pre-story SHA in the MVP (COULD later: `git reset --hard {story_start_sha}` option). [spine AD-13]
- **Orphan control:** `start_new_session=True` / `os.setsid`, PGID on the Attempt; re-attempt kills the group and waits for `.git/index.lock`. [`ProcessRunner.kill_group`, `attempt.pgid` — spine AD-14]
- **Harness readiness check:** a fixture Repository with a one-line Story; each adapter must reach `done` and its spend must be attributable before it is enabled. [PRD FR-33; `fixtures/readiness-repo/`, spine AD-10.] `claude` allowlist must include the subagent tool (`CLAUDE_ALLOWED_TOOLS`, PRD §8 item 1). Per-harness overrides of `implementation_handoff`/`review_layers` live in the *target Repository's* `_bmad/custom/bmad-build-auto.toml`, so the orchestrator would have to write them into the Worktree — avoid unless the readiness run fails.
- **Gate record:** a first-class entity (see Glossary): `gate_record(run_id, at, path?, event, actor, text)`, append-only, written on every Run transition. [spine AD-8]

## H. Day-1 verification queue
PRD §8 items 1–4, run through the readiness run (FR-33) on the fixture repository; each under an hour; each decides a day-3 or day-4 story. The spine's "Open at handoff" adds one architecture-internal check (the engine adapter's step-id assumption) that has no PRD counterpart.

## I. Feedback to the spine (2026-09-02 PRD update)
Status: **absorbed** — applied to the spine by `bmad-architecture` (update) on 2026-09-02 (`architecture/reviews/reconcile-prd-update.md`: 13/13). Kept as the record of what the PRD gate fed back; the spine is again the binding contract.
- **Prepare commit (AD-9, AD-17):** the `agent` executor order becomes WIP commit → orchestrator writes (`project-context.md`, Answer archive, `## Verify Failure`) → commit `orchestrator: prepare story {id} attempt {n}` → `start_sha` → dispatch. Without it `bmad-build-auto` step-01 halts on the dirty tree at every first dispatch.
- **Protected test set at frame start (AD-17):** freeze `test_globs` matches at the Story frame's first Attempt, not each Attempt, or the verify redispatch parks on the agent's own new tests.
- **`story@1` is callee-only; readiness runs `epic@1` (AD-10, AD-16, Structural Seed):** `story@1` has no `git.worktree`; `fixtures/readiness-repo/` runs through `epic@1` under a built-in Project `readiness`; New workflow offers `initiative`, `epic`, `repo-init`.
- **Signals (AD-13):** `answer` also valid when `park_kind = checkpoint` (Reject with a reason); `continue` valid when `park_kind = protected_path` (accept); new `Park.kind = plan_stale` with `continue | cancel`; `budget_raise` resumes at the row's routed status (a `blocked` row goes straight back to `blocked`); `skip_epic` keeps the epic's `git.push` / `pr.link` planned unless the push is the stop; `terminal_resume` marks the `agent` row `done` (actor `terminal`) before verify.
- **Park kinds (AD-13, AD-8):** `push_rejected` also covers `sync: branch diverged`; `misconfigured` also covers `no story file`, `ambiguous story file`, `unexpected status`, `harness exit`, `gateway unreachable`; `failed` reason `parked 30 days` on `recv` expiry.
- **Stale-plan check (AD-7):** the walker's first step compares the list files at the branch head with `plan_ref` and parks `plan_stale` on difference; `PUT /runs/{id}/files` refuses `stories.yaml` / `epics.yaml`.
- **`git.sync` (kinds table):** no-op when the branch has no upstream; `retry` on `push_rejected` rows syncs first.
- **Install (kinds table vs `epic@1`):** `install_command` runs inside `git.worktree`; drop the separate `install` shell step from `epic@1`.
- **Two Gateway keys (AD-5, AD-11, `.env.example`):** `LITELLM_API_KEY` (model calls, harness env) and `LITELLM_SPEND_KEY` (orchestrator only, `/spend/logs/v2`); `HARNESS_ENV_CONTRACT` carries the first only. PRD §8 item 5.
- **Harness readiness state (new field or entity):** `harness{name, enabled, last_readiness_at, failing_check, version_pin}` and `POST /harnesses/{name}/readiness`; no counterpart exists in the spine today.
- **Clone check reads the method version (AD-14):** `clone_check{status, at, output, bmad_version}` from `_bmad/_config/manifest.yaml` at the default branch.
- **Global concurrency as a setting (AD-12, `.env.example`):** `MAX_ACTIVE_RUNS` (default 2); queue reason `global concurrency, held by {runs}`.
- **Graph (AD-15):** group token adds `SKP` when all children are skipped; cards show the human label of a path, the Steps table the raw path.
