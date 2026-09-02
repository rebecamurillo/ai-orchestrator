---
title: Reconciliation review — ARCHITECTURE-SPINE.md against architecture-v1.md and the 2026-09-02 research
status: review
created: 2026-09-02
reviewed:
  - ../ARCHITECTURE-SPINE.md (draft 2026-09-02)
  - ../../../v1-dev-loop-2026-08-26/architecture-v1.md (proposal 2026-08-26, incl. its Corrections banner)
  - ../research/tracing.md, ../research/backend.md, ../research/dbos.md (verified 2026-09-02)
cross-checked: ../../prd.md (FR-1..FR-29, NFR-1..NFR-8, §6.1 tiers), ../../addendum.md §D/§G, ../../template-dsl-draft.md, ../prd-deltas.md
---

# Reconciliation review — architecture-v1 → ARCHITECTURE-SPINE

**Verdict.** The spine supersedes architecture-v1 cleanly on structure (engine port, materialised plan, two deployables, instance-level credentials, BMAD in the image) and states no CLI flag that the research contradicts — `--bare`, `opencode --auto`, `wire_api`, `codex exec` invocation are all delegated to `scripts/harness/*.sh` and to the "Open at handoff" list, which is the right place. Two things it *does* state collide with the research (the gateway header set that the budget mechanism depends on, and image-level BMAD skill stubs), and five architecture-v1 mechanisms the MVP still needs are neither governed, seeded, nor deferred. Details below; the intentional changes listed in the task brief are excluded.

Severity key: **high** = a MUST-tier FR cannot be built consistently from the spine as written; **medium** = an epic will have to invent a cross-cutting decision the spine should own; **low** = a one-line addition or a note.

---

## (a) architecture-v1 mechanisms still needed, not governed / seeded / deferred

### A1 — Spend per Run from Gateway spend logs; the `Gateway` port has no contract — **high**
- **v1 source:** §3 "Spend per run = `GET /spend/logs?…` summed by tag, cached on `run.spend_usd` after each step; budget halt = `spend_usd > budget_usd` checked after every agent step → BLK"; addendum §D "Budget"; addendum §G "Budget check timing … the Gateway sum is the contract".
- **Needs it:** FR-17 budget halt (MUST), FR-26 "Gateway spend logs carry tags", FR-28 cost per Step (MUST), FR-23 cost block `spent / budget`, NFR-5.
- **Spine today:** `ports/gateway.py` appears in the seed tree and the capability map (FR-16, FR-17 row → `application/rules/budget.py`, `Gateway` port), but unlike `WorkflowEngine`, `Harness`, `Git`, `ProcessRunner` the port has no declared methods, and no AD says *where* the authoritative cost figure comes from (Gateway spend logs vs harness-reported usage; FR-28 says Gateway is authoritative, harness usage provisional). `run.spend_usd`/`run.budget_usd` are not in the ERD notes. See B1: the header set the spine mandates does not populate spend-log tags per the research, so the sum-by-tag query has nothing to sum.
- **Fix:** In AD-11 (or a new AD) declare `Gateway{spend(run_id, since?) -> {cost_usd, tokens_in, tokens_out} by story/model}` and the rule "budget is evaluated by `application/rules/budget.py` from `Gateway.spend` after every agent attempt, before verify; harness-reported usage is stored on the attempt and shown provisional". Add `run.budget_usd`, `run.spend_usd` to the ERD notes. Mention the Claude-only `--max-budget-usd = remaining` cap as an adapter detail owned by `scripts/harness/claude.sh` (addendum §G) or drop it explicitly.

### A2 — Worktree file I/O has no port — **medium**
- **v1 source:** §2.4 (story-file liveness check, frontmatter parse), addendum §D Answer (`git mv` to `stories/.answers/…`, append `## Human Answer`), §G verify failure (append `## Verify Failure`, set `status: in-progress`), FR-15 `project-context.md`, §1 `GET /api/runs/:id/artifacts`, `…/artifacts/file?path=`.
- **Needs it:** FR-15 (MUST), FR-16 (MUST), FR-18 (MUST), FR-10 verify re-dispatch (MUST), FR-19 "the Operator may edit the Story file inline before Continue" (MUST — a *write* into the worktree from the API), FR-21 polling of the story file (SHOULD), FR-23 file tree + inline viewer (SHOULD).
- **Spine today:** AD-14 says *all* git and process side effects go through `Git` and `ProcessRunner`; the ports list is `{engine,harness,git,process,gateway,tracer,clock,repositories}`; the capability map's FR-15 row says "via `Git`/fs port" — an fs port that does not exist. AD-2 does not forbid `pathlib` in `application/`, so each epic will read/write the worktree directly and AD-18's "unit tests use only in-memory fakes" becomes untrue for the routing, answer, verify and context use cases. No route exists for reading/writing worktree files (routes: `auth projects repositories templates runs steps queue health`).
- **Fix:** AD-14 → three ports: add `Workspace{read, write, glob, move, tree, exists}` rooted at the Run's worktree; state that `application/` touches files only through it. Routes convention: `GET /runs/{id}/files?path=` and `PUT /runs/{id}/files` (story file edit before Continue), gated on `run.status == needs_you` and not while `terminal_session`.

### A3 — Prompt composition is not governed — **medium**
- **v1 source:** §2.4 "The prompt is the same for every harness: *Invoke the `bmad-build-auto` skill with spec folder … and story id …* + `invoke_dev_with` + [Halt after planning.]"; addendum §D Answer suffix `Answer from the operator to the blocking condition "{condition}": {answer}`; spec-checkpoint Continue "re-dispatches without the phrase"; template-dsl `retry.prompt` prepended for harnesses without `resume`.
- **Needs it:** FR-14 "a prompt that names the skill, Spec folder, and Story id, plus `invoke_dev_with`, plus 'Halt after planning.' … **and nothing else**" (MUST); FR-18, FR-19.
- **Spine today:** AD-10 fixes the *result* contract (Story file) and forbids adapters from interpreting output, but nothing says the prompt is built once, in `application/`, and passed verbatim — the one property that makes SM-3 (harness comparison) meaningful. `prompt_extra` in the DSL and the answer/retry suffixes have no stated owner.
- **Fix:** AD-10, one sentence: "`application/steps/agent.py::compose_prompt(skill, spec_folder, story_id, invoke_dev_with, halt_after_planning, answer?, retry_prompt?)` is the only prompt builder; adapters pass the string unchanged; the same Story on any harness receives byte-identical prompts."

### A4 — Cancel compensation and who runs it — **medium**
- **v1 source:** §2.3 "Cancel: `DBOS.cancel_workflow` + a compensating step that removes the worktree and, if the branch was created by this run and never pushed, deletes it"; addendum §D "Cancel rollback: `git worktree remove --force`; `git branch -D` only when `run.created_branch && !run.pushed`".
- **Needs it:** FR-20 cancel (MUST): "terminates any Harness process group of the Run, then stops the Run, removes the Worktree, and deletes the Working branch only if this Run created it and it was never pushed".
- **Spine today:** `engine.cancel(run_id)` exists (AD-6); `Git.remove_worktree`, `Git.delete_branch`, `ProcessRunner.kill_group` exist (AD-14); `run → cancelled` is in the state machine. But the compensation policy is unstated, `created_branch`/`pushed` are not in the ERD notes, and AD-8 ("status is written … from inside an engine step") cannot hold for a cancel of a `queued` or parked Run — a cancelled DBOS workflow does not get to run a compensating step; the `signal_run(cancel)` use case (or a separate cleanup workflow) must do it. Also FR-9's "worktrees of terminal Runs are removed 7 days later" has no owner (`engine.schedule` is only wired for the daily clone re-check).
- **Fix:** AD-13, add: "`Signal.cancel`: the use case kills `attempt.pgid`, calls `engine.cancel`, writes `cancelled` + `gate_record` directly (the one status write outside an engine step), then `Git.remove_worktree`; `Git.delete_branch` only when `run.created_branch and not run.pushed`." ERD notes: `run.created_branch`, `run.pushed`. Capability map FR-9 row: `engine.schedule('worktree_gc', daily)` alongside the clone re-check.

### A5 — Host-side LiteLLM / model-serving configuration — **medium**
- **v1 source:** §3 `model_list` (Anthropic, OpenAI, local models as `openai/<alias>` with `api_base: http://host.docker.internal:8000/v1` and `use_chat_completions_api: true` so Codex's `/v1/responses` bridges), `litellm_settings.callbacks: ["langfuse_otel"]`; §5 oMLX aliases `local-coder` / `local-general`, memory guard, 2-turn tool-calling smoke test through LiteLLM before wiring OpenCode.
- **Needs it:** FR-26 (MUST — nothing works without a configured gateway), FR-14 `codex` (MUST) and the addendum §C fallback "Codex pointed at LiteLLM for local models" (which is the *stated* MVP fallback if `local` slips and requires the responses→chat bridge), NFR-7 "first run from clone in under 30 minutes".
- **Spine today:** LiteLLM and Langfuse moved out of compose to the host (NFR-7 delta); the seed shows `litellm --> omlx` and the `langfuse_otel` edge, but no file, script, or doc in the Structural Seed owns the host config, and the Deferred list does not mention it. The 30-minute first run has no path.
- **Fix:** Structural Seed: add `host/litellm.config.yaml` (model_list incl. `use_chat_completions_api: true` for local aliases; `callbacks: [langfuse_otel]`) and `host/README.md` (oMLX install, aliases, the tool-calling smoke test) — or a Deferred line stating the host setup is manual and pointing at challenge-v1 §6.

### A6 — Per-Project prompt-content switch reaches no harness — **low**
- **v1 source:** §3 "Content redaction stays on by default; `OTEL_LOG_USER_PROMPTS` is a per-project switch".
- **Needs it:** FR-2 `log_prompt_content` (MUST), PRD §11 privacy guardrail.
- **Spine today:** `LOG_PROMPT_CONTENT_DEFAULT` is in the env table and the deltas say "unchanged", but AD-5's harness env list (`LITELLM_API_KEY`, Langfuse keys, trace env, Project env vars) omits the switch, and the research names three different knobs (Claude `OTEL_LOG_USER_PROMPTS`/`OTEL_LOG_TOOL_CONTENT`, Codex `[otel] log_user_prompt`, OpenCode: plugin-level).
- **Fix:** AD-5 or AD-11: "`project.log_prompt_content` is translated by each adapter's `env_for(run)` into that harness's content-logging knob; default off."

### A7 — Container hardening and egress mechanism — **low**
- **v1 source:** §4 non-root, `--cap-drop ALL`, `no-new-privileges`, egress allowlist, no host credential mounts.
- **Needs it:** NFR-3, NFR-4 (bound by the spine).
- **Spine today:** capability map row "Dockerfile non-root, compose network, `ProcessRunner` env". `cap_drop`/`security_opt` are not in the seed; "compose network" is not an egress allowlist mechanism (compose has none; it needs an egress proxy, `iptables` in the container, or an explicit acceptance that NFR-4 is aspirational for the MVP).
- **Fix:** Seed `docker-compose.yml` comment: `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `read_only` where possible; NFR-4: either name the mechanism or move it to Deferred with a sentence.

### A8 — Harness-readiness items not carried into "Open at handoff" — **low**
- **v1 source:** §2.5 Codex "Enable `multi_agent` feature"; addendum §G "Codex `multi_agent`, OpenCode `task` (Open question 1)"; PRD §8 Q3/Q4.
- **Needs it:** FR-14 (`codex` MUST): "must expose to the skill a subagent-spawning tool".
- **Spine today:** Open at handoff lists Codex `TRACEPARENT`, `DBOS.step_id`, Claude allowlist — not whether Codex/OpenCode expose subagents to `bmad-build-auto`, which decides whether `codex` is usable at all.
- **Fix:** Open at handoff item 4: "Codex subagent support (`multi_agent`) and OpenCode `task` satisfy `bmad-build-auto`'s subagent requirement — readiness fixture (`story@1` on the fixture repo) on day 4; fallback per addendum §C."

### Confirmed superseded or already covered (no action)
- §2.1 `repo_lock`, `dbos_workflow_id`, `litellm_key_ref`, `github_token_ref` → AD-12, AD-6, AD-5 (intentional).
- §2.2 template schema → template-dsl-draft + AD-9/AD-15.
- §2.3 queue/recv/recovery → AD-12/AD-13/AD-6; `@DBOS.scheduled` → `engine.schedule` (research: `create_schedule`); dirty-tree WIP commit → Commits convention; process groups → AD-14 `attempt.pgid`.
- §2.6 clone check, worktree add from `origin/<base>`, `GIT_ASKPASS`, compare URL (no `gh pr create`) → AD-14, AD-5, `pr.link`.
- §3 one trace per Run, `create_trace_id(seed)`, session floor → AD-11 (matches tracing.md).
- §6 growth path → Deferred (all five items present).

---

## (b) Spine statements the 2026-09-02 research contradicts

### B1 — Gateway headers: `langfuse_*` feeds Langfuse, not spend logs — **high**
- **Spine (AD-11):** "Every gateway request carries `langfuse_session_id: <run_id>` and `langfuse_tags: [run:, story:, harness:, project:]` as static headers set by the adapter."
- **Research (tracing.md, LiteLLM section):** `langfuse_*` headers become Langfuse span attributes; "`x-litellm-tags`, `x-litellm-session-id`, `x-litellm-end-user-id` are for spend logs (mapping to Langfuse session UNVERIFIED)". Two distinct header families for two distinct sinks.
- **Consequence:** FR-26 ("Gateway spend logs carry tags `run:{id}`…") and FR-17 (sum spend logs by Run tag) are not satisfied by the spine's header set; A1's budget query would return nothing.
- **Fix:** AD-11: adapters set *both* families — `x-litellm-tags: run:{id},story:{id},harness:{h},project:{p}` + `x-litellm-session-id: {run_id}` (spend logs) and `langfuse_session_id` + `langfuse_tags` (traces). Codex via `env_http_headers`, Claude via `ANTHROPIC_CUSTOM_HEADERS` (newline-separated `Name: Value`), OpenCode via provider `options.headers` with `{env:…}` — so per-attempt values flow through the adapter's env, not through regenerated config files (keeps AD-20 true).

### B2 — Image-level BMAD skill stubs vs "BMAD is per-project only" — **high**
- **Spine (AD-16):** "The backend-api image pins one `bmad-method` version and copies the skill stubs into `~/.claude/skills` and `~/.agents/skills` … A target repository commits `_bmad/` … only; `.claude/skills/bmad-*` … are git-ignored there."
- **Research (backend.md):** "**Per-project only** — no global/user-level mode; every SKILL.md runs `uv run {project-root}/_bmad/scripts/render_skill.py`, which raises if the project root lacks `_bmad/`." Whether the installed stub embeds an absolute `{project-root}` (then a stub copied into `~/.claude/skills` points at the image's scratch project, not the worktree) or resolves from cwd is not established by the research.
- **Consequence:** FR-8 pre-flight and FR-14 dispatch (MUST) rest on an invariant the research explicitly marks as unsupported by the tool. It is also absent from "Open at handoff".
- **Fix:** Open at handoff item 5 (day 1, < 1 h): install into a scratch repo, inspect the stub's `uv run …render_skill.py` path, run it from a different cwd. Fallback that keeps AD-16's intent: `git.worktree` copies the image's stubs into `{worktree}/.claude/skills` and `.agents/skills` (already git-ignored per AD-16) instead of `~/`.

### B3 — OpenCode plugin environment and prerequisites — **low**
- **Spine (env table, AD-11):** harness env receives `LANGFUSE_BASE_URL`; `local` "uses the Langfuse plugin with `LANGFUSE_USER_ID = run_id`"; universal floor "session.id = run id … every harness".
- **Research (tracing.md, OpenCode):** plugin env is `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASEURL` (no underscore); the plugin needs `experimental.openTelemetry: true`, which "is dropped in OpenCode v2"; traces are "one per turn keyed by OpenCode sessionID" — i.e. the plugin's traces are found by `user.id = run_id`, not in the Run's Sessions view; only the gateway generations (via B1's header) land under `session.id = run_id`.
- **Fix:** Env table note "adapter maps `LANGFUSE_BASE_URL` → `LANGFUSE_BASEURL` for OpenCode"; AD-11 wording "for `local`, plugin traces are reachable by `user.id = run_id`; the Sessions view holds the gateway generations"; Deferred "OpenCode trace parenting" line: add the `experimental.openTelemetry` dependency and the v2 removal.

### B4 — OpenCode provider package — **low**
- **Spine:** silent on which `@ai-sdk/*` package the `litellm` provider uses (scripts own it).
- **Research (backend.md):** "custom `@ai-sdk/anthropic` + baseURL drops the key — open bug #21737"; `@ai-sdk/openai-compatible` works.
- **Fix:** One line in AD-10 or the companions list: `scripts/harness/opencode.sh` must declare `provider.litellm.npm = "@ai-sdk/openai-compatible"`.

### Checked and consistent
- No `--bare`, no `opencode --auto`, no `wire_api`, no `codex exec` flags appear in the spine (delegated). `langfuse_otel` (not legacy `langfuse`) in the seed diagram matches the research. `create_trace_id(seed=run_id)`, OTLP `/api/public/otel`, Basic auth `pk:sk` — match. DBOS `register_queue` + partition key, `recv` 30 d, `SQLAlchemyDatasource`, schema `dbos`, `create_schedule`, pinned `application_version` — match dbos.md. Skill-discovery directories in AD-16 match backend.md. Stack versions match all three research files. `TRACEPARENT` for `claude -p` documented, for `codex` source-only — correctly flagged as open item 1.

---

## (c) §2.1 fields an FR needs that the ERD notes omit

The ERD notes are explicitly "entity notes that are invariants", so this list is limited to fields whose *rule* is cross-cutting (immutability, blocking, privacy, money) rather than plain attributes an epic will obviously add.

| Field (v1 §2.1 / PRD) | FR | Rule the spine should state | Severity |
| --- | --- | --- | --- |
| `run.budget_usd`, `run.spend_usd` | FR-17, FR-23, FR-28 (MUST) | spend cached from `Gateway.spend` after every agent attempt; `budget_raise` signal edits `budget_usd` only | medium (with A1) |
| `run.manual_estimate_h` | FR-8 (MUST), §6.2 "cannot be retrofitted" | written at create, immutable after `queued → running` | medium |
| `repository.clone_check{status, at, output}` + `install_command`, `quality_gate_command`, `unit_test_command`, `package_manager` | FR-3, FR-4, FR-8, FR-9 (MUST) | `clone_check.status = failed` blocks *new* Runs on that Repository (pre-flight rule); commands are template variables `{{repository.*}}` | medium |
| `run.created_branch`, `run.pushed` | FR-20 (MUST) | cancel rollback guard | medium (with A4) |
| `project.log_prompt_content`, `context_text`, `context_paths[]` | FR-2, FR-15 (MUST) | privacy switch → harness env; context → `project-context.md` | low (with A6) |
| `gate_record{at, step_path?, event, actor, text}` with `event ∈ {start, blocked, checkpoint, timeout, budget, answer, continue, skip, retry, cancel, budget-raise, …}` | Glossary, addendum §G, FR-18/19/20/23 | the enum is rendered by the UI and consumed by the future notifier; pin it | low |
| `run.park_reason` (text) beside `run.park_kind` | FR-23 alert banner, FR-16/17/10 reason strings | reason strings are product copy (NFR-8); store verbatim | low |
| `run.compare_url` | FR-11 (`pr.link`) | written once by `pr.link`, shown on the card | low |
| `step_run.gate`, `attempt.{harness, model, tokens_in, tokens_out, cost_usd, exit_code, started_at, finished_at}` | NFR-2, FR-14, FR-28 | gate strength stored per row (never derived); attempt usage is "provisional" until Gateway figure lands | low |
| `template_version.hash` | FR-6 | immutability check on save | low |

Not needed / intentionally gone: `project.github_token_ref`, `project.litellm_key_ref`, `project.budget_month` (FR-28 per-Project monthly figure is COULD — a query over `attempt.cost_usd`, no column), `repo_lock`, `run.dbos_workflow_id`, `step_run.session_id` (→ `attempt.session_id`).

---

## Suggested edit order
1. AD-11: add `x-litellm-tags` / `x-litellm-session-id`; declare `Gateway.spend`; `log_prompt_content` mapping (B1, A1, A6).
2. Open at handoff: add BMAD stub path (B2) and Codex/OpenCode subagent readiness (A8).
3. AD-14: `Workspace` port; routes for worktree files (A2).
4. AD-10: `compose_prompt` ownership (A3); OpenCode provider package (B4).
5. AD-13: cancel clause; ERD notes: `budget_usd`, `spend_usd`, `manual_estimate_h`, `created_branch`, `pushed`, `clone_check` (A4, c).
6. Seed: host LiteLLM config + README, compose hardening, `worktree_gc` schedule (A5, A7, A4).
7. Env table / Deferred: OpenCode plugin env name and `experimental.openTelemetry` dependency (B3).
