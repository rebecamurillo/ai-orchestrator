# Addendum — AI Orchestrator MVP

Depth that belongs downstream (architecture, solutioning, stories) or that earned a place but is not a requirement. The PRD states *what*; this file records *how* and *why not otherwise*. Full technical detail lives in `../v1-dev-loop-2026-08-26/architecture-v1.md`; full rationale and research citations in `../v1-dev-loop-2026-08-26/challenge-v1.md`. This addendum does not duplicate them; it indexes and adds what the PRD conversation surfaced.

## A. Technology decisions (pointers)
| Concern | Decision | Where |
|---|---|---|
| Durable engine | DBOS Transact (Python) on Postgres; one workflow interprets a pinned Template Version; human waits are `recv` on a per-Run topic; queue partitioned by Repository (`partition_concurrency=1`, `global_concurrency=2`) | architecture-v1 §2.3 |
| Backend | Python 3.12, FastAPI + DBOS in one process, SQLAlchemy, PyYAML | architecture-v1 §2 |
| Front-end | Vite + React + TypeScript, TanStack Router/Query, CodeMirror 6; no component library; polling | architecture-v1 §1 |
| Gateway | LiteLLM 1.98 with Postgres; virtual key per Project; `langfuse_otel` callback; local models as `openai/<alias>` with `use_chat_completions_api: true` so Codex's `/v1/responses` bridges | architecture-v1 §3 |
| Tracing | Langfuse OTLP `/api/public/otel` (HTTP/protobuf, traces only); Run trace id from the orchestrator; Claude Code spans via inbound `TRACEPARENT`; Codex/OpenCode via session id + tags | architecture-v1 §3 |
| Local models | oMLX on the host; Qwen3.8-27B 4-bit (coder, pinned), Qwen3.6-35B-A3B 4-bit (general, LRU); wired GPU limit raised to ~42 GB | challenge-v1 §6 |
| Container | non-root, `cap-drop ALL`, `no-new-privileges`, egress allowlist, tooling: git gh node uv claude codex opencode | architecture-v1 §4 |

## B. Harness matrix (from documentation, 2026-08-26)

> **Status: to be re-verified from each harness's own documentation when its adapter is built.** These CLIs change between releases — the 2026-08-26 pass already found `--full-auto` deprecated in Codex and `wire_api = "chat"` removed. Treat every flag below as a starting point, never as a contract; the contract is FR-14's capability list. **Codex and OpenCode technical details are deliberately deferred** (PRD §8).

**One item is confirmed by direct observation and is not provisional:** Claude Code 2.1.246 `-p --bare` exposes exactly `Bash, Edit, Read` — no subagent tool, no `Write`, no `Skill` — and neither `--add-dir` nor `--tools default` restores them, while default discovery exposes `Task`, `Write`, and `Skill`. `--bare` cannot run `bmad-build-auto`. Use default discovery with an explicit allowlist plus `--disallowedTools "mcp__*"` (a container has no personal MCP connectors, but the exclusion should be explicit).

See challenge-v1 §5 for the full table with doc citations. Facts that changed since the 2026-08-24 PRD's addendum and matter for stories:
- Codex `wire_api` accepts only `responses`; `--full-auto` is deprecated; `codex exec` is always approval `never`; `[otel]` now has separate `trace_exporter`; skills are read from `.agents/skills`; session ids cannot be pre-assigned.
- Claude Code: the docs recommend `--bare` for scripted calls — **do not follow that here** (see above); `.agents/skills` is **not** read; OTLP traces are beta behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`.
- OpenCode reads both `.claude/skills` and `.agents/skills`; `opencode run --format json --auto --session <id>`; provider config supports `headers`; no OTEL of its own.
- LiteLLM: `/v1/messages` translation to any provider, Anthropic-native `/v1/models` for Claude Code gateway model discovery, header-driven Langfuse metadata (`langfuse_*`, `x-litellm-tags`, `x-litellm-session-id`), tag budgets via `/tag/new`.

## C. Rejected alternatives (MVP)
| Rejected | Why |
|---|---|
| JSON-schema structured output as the agent contract | Only Claude Code and Codex support it; the Story file frontmatter is what `bmad-build-auto` already writes and is Harness-independent. |
| Terminal `--resume` as the primary reply path | Claude/Codex only; depends on harness-local session content; invisible to the gate record. Kept as secondary. |
| Pipeline-stage board columns (Spec → Plan → Build → Review → Merged) | One Template; stage lives on the card; status columns put attention where it belongs. |
| Global serialization (one Run at a time) | Existed only for a shared E2E database that is out of scope. Repository-partitioned queue instead. |
| Visual workflow editor | A product in itself; YAML + rendered diagram covers the need. |
| Codex or Claude Code pointed at LiteLLM for local models instead of a third Harness | Kept as fallbacks (in that order) if the OpenCode adapter slips; OpenCode's skill discovery and chat-completions provider make it the better default. |
| Notifications inbox screen | Redundant for one operator; "Needs you" column + rail count. |

## D. Mechanisms (for solutioning)
- **Story-file evaluation** after a Story step: glob `{spec_folder}/stories/{id}-*.md`; exactly one match; parse YAML frontmatter; route on `status`; the whole `## Auto Run Result` section is shown as the Question (PRD FR-16).
- **Answer (revised at PRD finalization):** `git mv stories/{id}-{slug}.md stories/.answers/{id}-attempt-{n}.md`, append `## Human Answer` with timestamp and text, commit-guard; then dispatch folder+id again — with no `stories/{id}-*.md` present this is a *first dispatch*, so step-02 plans fresh — with the prompt suffix `Answer from the operator to the blocking condition "{condition}": {answer}`. Rejected: appending `## Human Answers` and resetting to `draft` — step-02 preserves the old `<intent-contract>` verbatim on a draft resume and the template has no such section, so the Answer would be overwritten or ignored.
- **Spec checkpoint:** dispatch prompt ends with "Halt after planning."; agent stops at `ready-for-dev`; Continue re-dispatches without the phrase; `bmad-build-auto` routes `ready-for-dev` straight to implementation.
- **Repository lock:** held for the Run's whole life including `needs-you` — a workflow parked in `recv` still occupies its queue partition (`partition_concurrency=1`), which is exactly the lock. No release-on-park; rejected because it would require ending and re-enqueueing the workflow and would let two Runs share one Repository's worktrees.
- **Budget:** `GET /spend/logs` summed by `run:{id}` tag after each Story step; cached on `run.spend_usd`.
- **Cancel rollback:** `git worktree remove --force`; `git branch -D` only when `run.created_branch && !run.pushed`.
- **Gateway key per Project:** `POST /key/generate {key_alias: project, max_budget, budget_duration: "1mo", tags: ["project:<name>"]}`; stored as a reference in the app DB, secret in `pgcrypto`.

## E. FR lineage to the 2026-08-24 PRD
(ids below are the 2026-08-24 PRD's ids → this PRD's ids.) Kept in spirit: FR-1..5 (onboarding) → FR-2..4; FR-6..12 (templates, versioning, pinning) → FR-5..7; FR-13..18 (durable execution, park, resume, retry, cancel) → FR-12, FR-19, FR-20; FR-20..26 (agent tasks, session ids, per-task records) → FR-14, FR-16; FR-27/28 (gate strength, never green without oracle) → FR-16, NFR-2; FR-43..45 (trace, cost, budget) → FR-17, FR-26..28; FR-47/48 (serialization) replaced by FR-13. Dropped for MVP: FR-24a, FR-28b, FR-29, FR-12a/12f, FR-30/30a/31, FR-33..37, FR-38..42 (PR creation is a link), FR-46, FR-50..52 (only the manual-estimate capture survives), F9 entirely.

## F. The week (from challenge-v1 §7)
Day 1 infra + skeleton + `dev-loop` YAML · Day 2 Projects/Repositories/Clone check · Day 3 interpreter + Claude adapter + Board/New workflow · Day 4 Codex + OpenCode adapters + tracing + budget + queue + Run detail · Day 5 checkpoints, verify retry, cancel + Runs/Templates screens · Day 6 hardening + restart test + states · Day 7 dogfood on `fullstack-app`. Slips first: as PRD §6.1.

## G. Corrections surfaced at PRD finalization (for bmad-architecture)
- **The agent commits:** `bmad-build-auto` step-04 commits reviewed work and halts `done` only on a clean tree; step-01 halts `blocked` on a dirty tree. The loop is therefore build (agent commits) → verify (deterministic, on the committed tree) → commit-guard (orchestrator commits leftovers only). architecture-v1 §2.2/§2.3 `commit` Step must be renamed/re-scoped accordingly.
- **Dirty-tree pre-dispatch rule:** Before any Story step attempt: `git add -A && git commit -m "wip: story {id} attempt {n} (interrupted)"` when the Worktree is dirty (FR-12).
- **Step timeouts:** `timeout_min` per Step in the Template schema (defaults 90 / 30 / 5); process kill → Step `error` → Run `needs-you` (FR-10). The DBOS step wrapper owns the timer.
- **Done checkpoint mechanism:** `pause_when` cannot hang off the `agent` Step alone: the done checkpoint is evaluated by the interpreter after the commit-guard Step from `stories.yaml`. Move `pause_when` to the `for_each` group (`pause_after_item_when: story.done_checkpoint`, `pause_before_implement_when: story.spec_checkpoint`).
- **Budget check timing:** After each Story step attempt, before verify (FR-17). The Claude adapter additionally passes `--max-budget-usd = remaining budget` as a harness-local cap; Codex/OpenCode have no equivalent, so the Gateway sum is the contract.
- **Daily Clone check:** Needs a scheduled DBOS workflow (`@DBOS.scheduled("0 6 * * *")`); not in architecture-v1.
- **Open questions 1 and 2:** (Codex `multi_agent`, OpenCode session id) are stated as settled in architecture-v1 §2.5; they are not — treat those rows as the day-1 verification targets.
- **Worktree retention, PR link:** as PRD FR-9 and FR-11; no change to architecture-v1 beyond removing `gh pr create`.
- **Verify failure re-dispatch:** append `## Verify Failure` (command, exit code, output tail) to the Story file, set `status: in-progress` → `bmad-build-auto` step-01 routes `in-progress` to step-03 (implement → verify → review). Rejected: re-dispatching a `done` file (routes to a review pass that never sees the failure) and a freeform fix prompt (its spec lands outside the Spec folder).
- **Skip:** commit-guard, then re-baseline; no reset to a pre-story SHA in the MVP (COULD later: `git reset --hard {story_start_sha}` option).
- **Orphan control:** `start_new_session=True` / `os.setsid`, PGID on `step_run`; re-attempt kills the group and waits for `.git/index.lock`.
- **Harness readiness check:** a fixture Repository with a one-line Story; each adapter must reach `done` before it is enabled. `claude` allowlist must include `Agent`; verify `--bare` keeps it (Open question 5). Codex `multi_agent`, OpenCode `task` (Open question 1). Per-harness overrides of `implementation_handoff`/`review_layers` live in the *target Repository's* `_bmad/custom/bmad-build-auto.toml`, so the orchestrator would have to write them into the Worktree — avoid unless OQ1 fails.
- **Gate record:** a first-class entity (see Glossary): `gate_record(run_id, at, step_id?, event, actor, text)`, append-only.

## H. Day-1 verification queue
Same as PRD §8 items 1–6; each under an hour; each decides a day-4 or day-5 story.
