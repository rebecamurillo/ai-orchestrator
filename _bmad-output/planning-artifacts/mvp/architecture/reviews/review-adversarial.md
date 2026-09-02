---
title: Adversarial review — ARCHITECTURE-SPINE (2026-09-02)
type: review
lens: adversarial
reviewed: ../ARCHITECTURE-SPINE.md
also-read: ../../template-dsl-draft.md
created: 2026-09-02
verdict: not yet build-safe — 15 pairs of AD-compliant epics that build incompatibly; 8 need a new or tightened AD sentence before epics are cut, 7 can be closed by a convention line
---

# Adversarial review — can two compliant epics still collide?

Method: for each pair of epics one level down (E1 scaffold/CI · E2 projects/repositories/clone check · E3 templates/validator/planner/graph · E4 run creation/pre-flight/walker/queue · E5 `git.*`/`shell`/`checkpoint`/`bmad.install` · E6 agent step/harness adapters/tracing/budget · E7 signals · E8 board/run detail/diagram · E9 runs screen/queue/history · E10 trajectories/protected paths) I took the spine's ADs as the *only* contract, wrote the two most natural implementations that each satisfy every AD sentence literally, and checked whether they agree on shared data shapes, entity ownership and status-mutation paths. Every disagreement below is a hole. Fixes are phrased as the sentence to add or replace; "AD-x" means the rule text of that AD, "Entity" means the field list under Structural Seed, "Conv" means the Consistency Conventions table.

Severity: **S1** = the two epics cannot be integrated without one of them being rewritten; **S2** = they integrate but produce wrong runtime behaviour (double writes, orphans, false parks); **S3** = they integrate, the UI or history lies.

---

## H1 — S1 — E4 walker vs E7 signals vs E6 agent step: three writers of `run.status = needs_you`, and cancel races an in-flight step

**AD text relied on:** AD-8 "execution transitions happen inside the engine step that performs the work; operator transitions in `signal_run`"; AD-13 "a use case never blocks; it returns `Park(...)` and the engine adapter waits"; AD-8 "every Run transition appends a `gate_record`".

**Reading A (E6):** the `agent` executor *is* the engine step that performs the work, so when it decides `blocked` it writes `step_run.status = blocked`, `run.status = needs_you`, `run.park_kind = blocked`, appends `gate_record{blocked}`, and *then* returns `StepResult{park}` so the adapter can `recv`. Every sentence of AD-8/AD-13 holds.

**Reading B (E4):** executors are pure over ports and return `StepResult`; the walker, still inside the engine step, calls `park_run(run_id, Park)` which writes the same three rows. Every sentence holds too.

Built together: two `gate_record{blocked}` rows per park, and `run.park_kind` written twice (harmless) — until E7's `retry` re-queues the row and E6's next attempt parks again while E4 also parks: the second `needs_you→needs_you` write is not in the state machine and `signal_run`'s 409 check now sees a gate_record count it did not expect. Built with only one of them (each assumes the other does it): the adapter waits on `recv` with `run.status = running` forever, the board shows a green card for a Run nobody can signal.

Same hole, second face: AD-13 puts `cancel` in the request path (`kill_group` → `engine.cancel` → `remove_worktree`) and AD-8 puts `→cancelled` in `signal_run`. The killed harness returns exit `-15` to the E6 executor, which is still inside its engine step, routes the story file (`no story file` → `error`) and writes `step_run.status = error` and — under Reading A — `run.status = needs_you` *after* E7 wrote `cancelled`. AD-8 forbids neither write. Under Reading B the walker writes `error` on the step of a cancelled Run and the run diagram shows a red node on a grey Run.

Third face: who turns `error → queued` on `retry`? AD-8's step diagram labels the edge "operator retry", so E7 does it in `signal_run`; but AD-8's prose says only "operator transitions (`needs_you→running`, `→cancelled`, `→skipped`)" — no `→queued` — so E4 does it when the walker wakes. Both defensible; done twice the row's `retry_count` is off by one.

**Tightened rule — AD-8, replace the second sentence:**
> Exactly one use case, `apply_step_result(run_id, path, StepResult)`, applies every execution transition; it is called only by the walker, inside the engine step that ran the row, and step executors never touch `run`, `step_run`, `attempt` or `gate_record` status fields. A `StepResult.park` makes `apply_step_result` write `run.status = needs_you`, `run.park_kind`, `run.park_path = path` and one `gate_record` in the same unit of work. `apply_step_result` is a no-op (logged) when `run.status ∉ {running}` — a cancelled Run absorbs late results. `signal_run` owns every operator transition on the Run **and** the re-queue of the target row (`error|blocked|checkpoint → queued`, or `→ skipped`), so the walker on wake only reads.

---

## H2 — S1 — E5 `git.worktree` vs E4 create_run / E7 cancel: an initiative has N branches, the Run has one `worktree_path`, one `branch`, one `created_branch`, one `pushed`

**AD text relied on:** AD-14 "worktrees at `/work/{project}/{repo}/wt/{branch}`; `git.worktree` is idempotent and sets `run.worktree_path`"; AD-13 "`Git.delete_branch` only when `run.created_branch and not run.pushed`"; Entity `run.worktree_path, branch, created_branch, pushed`; DSL §4 "one Worktree per Run, branch per epic — `git.worktree` at the head of `epic` switches or creates the epic's branch".

**Reading A (E5, path-faithful):** each `git.worktree` row adds `wt/{branch}` for *its* branch and overwrites `run.worktree_path`. An initiative with `feat/a` then `feat/b` leaves two worktrees. E7's `cancel` removes `run.worktree_path` only → `wt/feat-a` is orphaned until `worktree_gc`, still holding `feat/a` checked out; `run.created_branch/pushed` describe whichever epic ran last, so `cancel` deletes `feat/b` (created, unpushed) but never `feat/a` (or the reverse). E4's pre-flight for a later Run on `feat/a` says "will reuse worktree" and is right by accident.

**Reading B (E5, DSL-faithful):** one worktree per Run, `git checkout -B feat/b` in place. `run.worktree_path` stays `wt/feat-a` while the tree is on `feat/b`. FR-9's "the Worktree path is `/work/…/wt/{working branch}`" — which E4's pre-flight and E8's header both print — is now false; the next Run on `feat/b` (different repository lock cycle) calls `worktree_add wt/feat-b` and git refuses because `feat/b` is checked out in `wt/feat-a`. E4's idempotence check ("reuse when clean") never sees it.

Both satisfy AD-14 literally. `StepContext.cwd = run.worktree_path` (AD-9) is read at row start, so under either reading rows in epic 2 run in the right place, which hides the bug until cancel or the second Run.

**Tightened rule — AD-14, add after "sets `run.worktree_path`":**
> One worktree per (Run, branch): `git.worktree` adds or reuses `wt/{branch}`, appends `{branch, path, created_branch, pushed: false}` to `run.worktrees[]` if absent, and sets `run.worktree_path` / `run.branch` to it; `git.push` sets `pushed` on the matching entry; `pr.link` appends to `run.compare_urls[]`. `cancel` and `worktree_gc` iterate `run.worktrees[]` (remove every worktree; delete each branch whose entry is `created_branch and not pushed`). Pre-flight lists every branch the plan will check out and refuses when any of them is checked out by a worktree of a non-terminal Run.
> Entity: replace `run.branch, created_branch, pushed` with `run.worktrees[]`; keep `run.worktree_path` as "current".

---

## H3 — S1 — E5 `checkpoint` kind vs E7 `continue`: the one edge `checkpoint → queued` means "re-execute" for `agent` and must mean "pass" for `checkpoint`

**AD text relied on:** AD-7 "`pause_*_item_when` become rows of kind `checkpoint` (gate `human`)"; AD-8 step diagram `running --> checkpoint: pause row / ready-for-dev + spec_checkpoint`, `checkpoint --> queued: continue`; AD-9 "`application/steps/<kind>.py` implements `execute(ctx) -> StepResult`".

**Reading A (E5):** `steps/checkpoint.py` evaluates the item condition and returns `{status: checkpoint, park: Park(checkpoint)}`. On `continue` E7 moves the row `checkpoint → queued` (the only edge). The walker runs the row again; the executor evaluates the same item field, which is still true, and parks again. Infinite park. E5 "fixes" it by reading `gate_record` for a prior `continue` on this path inside the executor — a kind-specific status derivation AD-8 was written to prevent.

**Reading B (E7):** `continue` on a `checkpoint` row writes `done` directly and the walker advances. Correct for `checkpoint`, but the same code path on an `agent` row parked at `ready-for-dev + spec_checkpoint` must produce `queued` (FR-19: "Continue re-dispatches the Story"). E7 branches on `step_run.kind` inside `signal_run` — the kind-specific branch AD-9 bans from the walker/adapters/UI, now in a use case, with no AD saying it is allowed there.

Second face: `skip` on a `before` checkpoint row. AD-8 has `checkpoint --> skipped: skip`; E7 skips *the row* (the checkpoint) and the story runs anyway; E5/E8 expected "skip the story" (FR-20 says "skip the current Story"). Two Runs, same button, different outcomes.

**Tightened rule — AD-8 step machine, add edges and one sentence:**
> `checkpoint --> done: continue (kind checkpoint)`; `checkpoint --> queued: continue (kind agent)`. `signal_run(continue)` reads `step_run.kind` of `run.park_path` to pick the edge — the only kind test outside `application/steps/`. `skip_story` targets the *story frame* containing `run.park_path` (the innermost `…stories[n]` prefix), never the single row — see H4 for what it does to the frame.

---

## H4 — S1 — E7 `skip_story` vs E4 walker vs E5: the commit-guard and re-baseline that FR-20 requires are not rows in the plan

**AD text relied on:** AD-7 "the walker executes only existing rows in `path` order; nothing executes that is not in the plan"; AD-8 "`→skipped` in `signal_run`"; FR-20 "Skip first runs the commit-guard (`story {id}: skipped by operator`) … then re-runs `quality_gate_command` as a re-baseline"; Conv Commits "`story {id}: skipped by operator`".

**Reading A (E7, FR-faithful):** `signal_run(skip_story)` calls `Git.commit("story {id}: skipped by operator")` and `ProcessRunner.start(quality_gate_command)` in the request path, then marks the story rows `skipped`. It obeys AD-7 (no *row* executed) and AD-13 does not forbid it — but a 30-minute quality gate now runs inside an HTTP request, and the re-baseline result has no `step_run`/`attempt` to land on (FR-25 history never shows it).

**Reading B (E7, plan-faithful):** `skip_story` marks `build` `skipped` and leaves `verify` and `commit_guard` `planned`; the walker runs them. `verify` fails (the agent left a half-built tree) → E5's `shell` executor returns `redispatch: build` (`on_fail`), E4's walker re-queues a row that is `skipped` — AD-8 has no `skipped → queued` edge, so E4 either raises or silently runs the agent the operator just skipped. And `commit_guard`'s message was resolved at plan time to `story x: title (orchestrator)`, not `skipped by operator`.

**Tightened rule — AD-13, add:**
> `skip_story` marks every non-terminal `agent` and `checkpoint` row of the story frame `skipped` (reason `skipped by operator`) and leaves the frame's `shell` and `git.commit` rows planned; it also sets the frame's `git.commit` row's resolved `message` to `story {id}: skipped by operator`. The frame's `verify` row is the re-baseline; a `redispatch` whose target row is `skipped` is applied as `escalate` with reason `re-baseline failed after skip`. `skip_epic` is the same over the innermost `epics[i]` frame plus its `git.push`/`pr.link` rows, leaving the current story's `git.commit` row planned so the tree is committed before the next epic. (prd-delta: FR-20's "commit then re-baseline" becomes "verify then commit-guard" — same tree, same result.)

---

## H5 — S2 — E6 agent step vs E10 protected paths vs E5 `git.commit` vs E7 file edits: four opinions on what `attempt.start_sha` is

**AD text relied on:** AD-9 "WIP-commits a dirty tree before every attempt"; AD-17 "after every `agent` attempt and again in `git.commit`, `Git.diff_names(attempt.start_sha)` is checked"; Conv Routes "`PUT /runs/{id}/files` (spec folder only, allowed while `needs_you`)"; FR-18 "if the gap is in SPEC.md the Operator edits SPEC.md on the branch".

**Reading A (E6):** `start_sha = HEAD` *before* the WIP commit, so an interrupted attempt's edits are inside the diff and a protected hit is attributed to the agent. Then the operator edits `SPEC.md` through `PUT /files` while parked, presses Answer; the next attempt WIP-commits the operator's edit, runs, and `diff_names(start_sha)` reports `SPEC.md` → Run parks `protected path modified: SPEC.md`, "never re-executed automatically". The operator's sanctioned edit is a permanent false positive.

**Reading B (E6):** `start_sha = HEAD` *after* the WIP commit. Operator edits pass. But an agent interrupted by timeout mid-edit of `tests/foo.test.ts` gets its work WIP-committed on the re-attempt and is never checked — the guard AD-17 exists for is bypassed by every restart.

**Reading C (E5):** `git.commit` records *its own* attempt's `start_sha` (= HEAD when the commit row starts, the tree already WIP-committed or committed by the agent) → `diff_names` is empty by construction, the "again in `git.commit`" check is vacuous. **Reading D (E5):** it looks up the frame's `build` row's latest attempt — a cross-row read AD-9's `StepContext` does not carry.

**Where E10 runs it** is also open: inside the E6 executor before routing (row `error`, `park: protected_path`) or as an E4 walker post-hook after the row is `done`. Different step status for the same event; H1's single writer needs one answer.

**Tightened rule — AD-17, replace the second sentence:**
> `attempt.start_sha` is HEAD *after* the WIP commit. Before making the WIP commit the agent executor checks `diff_names(previous_attempt.start_sha)` against the protected set and attributes a hit to that previous attempt. `PUT /runs/{id}/files` commits the edit immediately as `spec: operator edit (orchestrator)`, so operator edits are never in an attempt's diff. `rules/protected_paths.check(ctx)` is called by the `agent` executor after the harness exits and before routing (a hit returns `status: error, park: protected_path`), and by the `git.commit` executor against `ctx.frame.last_agent_attempt.start_sha`, which `StepContext` carries as `frame_start_sha` (set by the walker from the frame's latest `agent` attempt, else HEAD).

---

## H6 — S2 — E1 `scripts/harness/*.sh configure` vs E6 `env_for(attempt)`: the per-Run gateway headers cannot be "static" for codex and opencode

**AD text relied on:** AD-10 "static config produced only by `scripts/harness/<name>.sh` … per-attempt environment only by the adapter's `env_for(attempt)`"; AD-11 "every gateway request carries two header families set statically by the adapter: `langfuse_session_id: <run_id>` … `x-litellm-tags: run:,story:,harness:,project:`"; AD-20 "harness config files … generated by `configure` at container start, never edited by hand".

**Reading A (E1):** `configure` writes `~/.codex/config.toml` `[model_providers.litellm] http_headers = {...}` and `opencode.json` `provider.litellm.options.headers` once, at container start, with values that exist at container start — there is no `run_id` yet, so the headers carry the harness name and nothing else. E6's `env_for` exports `TRACEPARENT`, `LANGFUSE_USER_ID`, `LITELLM_API_KEY`. Result: no spend log carries `run:` → `Gateway.spend(run_id)` sums to 0 → the budget halt (AD-11, FR-17) never fires for codex/local and `attempt.cost_usd` is null.

**Reading B (E6):** the adapter rewrites `~/.codex/config.toml` per attempt to inject `run:{id}`. Obeys "never edited by hand" (it is a program) but breaks AD-10's "static config produced *only* by the script", and with global concurrency 2 (AD-12) two Runs on different repositories race on the same file under the shared `agent-home` volume.

**Tightened rule — AD-10, add:**
> `configure` writes config files that reference environment variable *names* only (Codex `env_http_headers`, OpenCode `{env:NAME}`, Claude `ANTHROPIC_CUSTOM_HEADERS`) and never a value that varies per Run; `scripts/harness/_common.sh` declares the list `HARNESS_ENV_CONTRACT` (`ORCH_RUN_ID`, `ORCH_STORY_ID`, `ORCH_HARNESS`, `ORCH_PROJECT`, `TRACEPARENT`, `LANGFUSE_*`, `LITELLM_*`) and `env_for(attempt)` populates exactly that list; the readiness run (AD-10) fails unless the gateway spend log for the fixture attempt carries `run:{run_id}`. Nothing under `AGENT_HOME` is written by an adapter.

---

## H7 — S2 — E3 planner vs E4 create_run/walker: `plan_run`'s boundary, row order and variable resolution are three private decisions

**AD text relied on:** AD-7 "`plan_run(template_version, inputs)` … records the resolved SHA as `run.plan_ref` … expands into `step_run` rows … in one transaction, before `engine.enqueue`"; "the walker executes only existing rows in `path` order"; "pre-flight renders the same `plan_run` output without persisting"; AD-9 "`StepContext` carries … resolved variables".

**Reading A (E3):** `plan_run` is a pure function returning `Plan{plan_ref, rows: [PlannedRow]}`; E4's `create_run` persists it. **Reading B (E3):** `plan_run` *is* the use case that records `run.plan_ref` and writes rows ("records", "in one transaction") and pre-flight calls a sibling `dry_plan`. E4 written against A double-persists under B; written against B has nothing to persist under A. Both readings of the sentence are literal.

Order: E3 emits rows in traversal order and assumes E4 keeps insertion order; E4 sorts by `path` as AD-7 says — `stories[10].story.build` < `stories[2].story.build` lexicographically, and the eleventh story runs second.

Resolution: E3 resolves `{{repository.install_command}}` at plan time and stores it (a `shell` with an empty command is `skipped` *in the plan*, visible in "What will run"); E5 resolves at execution against the live repository entity ("`skipped` when the bound command is empty" happens *at run time*). Pre-flight shows `install: planned`, the Run shows `install: skipped` — or the operator edits the repository mid-Run and the second epic installs differently from the first.

**Tightened rule — AD-7, add:**
> `plan_run` is pure: `(template_version, inputs, Git) -> Plan{plan_ref, rows: [PlannedRow{seq, path, kind, gate, status, reason?, with_resolved}]}`; `create_run` persists `rows` as `step_run` with `seq` (dense integer, plan order) and the walker orders by `seq` — `path` is the human key only. Every `{{…}}` is resolved at plan time from the entity snapshot and stored in `step_run.with_resolved`; a `shell` whose resolved command is empty is planned `skipped` with reason `no command`. Pre-flight and `create_run` call the same `plan_run`.

---

## H8 — S3 — E8 RunDiagram vs E3 graph builder: node identity and aggregate status

**AD text relied on:** AD-15 "the diagram graph (`nodes`, `edges`, `groups`, optional statuses; callee calls collapsed) is produced by backend-api at … `GET /runs/{id}/graph`"; AD-8 "the UI renders the stored token, never derives one"; FR-29 "initiative → epics → stories → story sub-steps".

**Reading A (E3):** one node per *template step* (`checkout`, `stories`, `story` collapsed), so a Run with 12 stories has one `story` node whose `status` is… something E3 invents (last row? worst row?). **Reading B (E8):** one node per `step_run.path` so a click opens the row's attempts and the tree reads initiative → epics → stories. E8 keys its nanostore selection by `node.id === step_run.path`; E3's ids are `stories.story.build`. Nothing joins. And group status (an epic's colour) is a derived token — AD-8 forbids the UI to derive, no AD says who does.

**Tightened rule — AD-15, add:**
> Template graph node id = template-relative path with indices omitted (`stories.story.build`); Run graph node id = `step_run.path`, group id = path prefix (`epics[0]`, `epics[0].epic.stories[3]`). Group status is computed only in `application/graph.py` by one rule — `error|blocked|checkpoint` if any row is; else `running` if any; else `done` when all are `done|skipped`; else `queued|planned` — and is the only derived status token in the system.

---

## H9 — S3 — E4 engine adapter vs E9 runs screen: `QueueEntry` cannot carry what FR-25 shows

**AD text relied on:** AD-6 "`list_queue() -> [QueueEntry]`"; AD-12 "the Runs screen's queue is `engine.list_queue()`, never a table"; FR-25 "position, Run, next Step, waiting reason, waiting time; a `needs-you` Run appears with position `—` and reason `waiting for your answer`".

**Reading A (E4):** DBOS `list_queued_workflows` gives `{workflow_id, status ∈ {ENQUEUED, PENDING}, created_at}`; `QueueEntry{run_id, position, enqueued_at}`. A `needs_you` Run is PENDING (inside `recv`) — indistinguishable from `running` at the engine. **Reading B (E9):** expects `QueueEntry{run_id, position, next_path, reason, waiting_since}` fully populated because "never a table" reads as "do not join tables". E9 built against B renders empty columns; E4 built against B has the adapter reading `run`/`step_run` (allowed by AD-2, but the reason strings then live in `infrastructure/`).

**Tightened rule — AD-6 + AD-12:**
> `QueueEntry{run_id, engine_state ∈ {enqueued, pending}, position: int | None, enqueued_at}` is all the engine knows. `use_cases/queue.list_queue()` joins it with `run` (status, park_kind, park_path) and returns the FR-25 row with `reason ∈ {repository lock held by {run}, global concurrency, running, waiting for your answer}`; "never a table" means no queue *state* table — reading `run` is fine.

---

## H10 — S2 — E2 clone check vs E4 create_run: two writers of `repository.clone_check` and no consumer

**AD text relied on:** Entity "`clone_check{status, at, output}` — `failed` blocks new Runs (FR-4)"; AD-14 "the daily clone re-check is the scheduled job `clone_check`"; FR-8 pre-flight "origin reachable".

**Reading A (E2):** only `run_clone_check` (save + scheduled job) writes `clone_check`; nobody blocks — E2 assumes E4 reads it. **Reading B (E4):** pre-flight runs its own `ls_remote`; success is proof enough, and to be helpful it writes `clone_check.status = ok` (E2's entity, mutated from E4) — or it never reads `clone_check` at all and a `failed` repository starts a Run because origin happens to answer tonight. Both satisfy every sentence; the FR-4 consequence is implemented by nobody or by two.

**Tightened rule — Entity + AD-14:**
> `repository.clone_check` is written only by `use_cases/projects.run_clone_check` (called by project save, `POST /repositories/{id}/clone-check`, and the scheduled job). `create_run` returns 409 `clone check failed at {at}` while status is `failed`; pre-flight surfaces it as a failing check whose fix is the re-check endpoint. Pre-flight's `origin reachable` uses `Git.ls_remote` and writes nothing.

---

## H11 — S3 — E5/E6 vs E9/E10: does a `git.sync` or `checkpoint` row have an `attempt`?

**AD text relied on:** AD-7 "re-execution is a new `attempt` on the same row"; Entity `attempt.n, engine_ref, harness, model, session_id, pgid, start_sha, exit_code, tokens, cost_usd, log_path` (every field agent-shaped); FR-25 history "every Step … duration, cost".

**Reading A (E5):** every row execution inserts an `attempt` with nulls in harness fields (so history has `started/ended`). **Reading B (E6):** attempts are for `agent` rows only; E9 renders history from `step_run` — which has no timestamps in the entity list; E10's trajectory `attempts` count means agent attempts. Cost per path (AD-11) works either way, duration and `retry` of a `git.push` (FR-11 "Retry re-runs the push") do not: retrying a push under B has no attempt to record `pgid`/`log_path` on.

**Tightened rule — Entity:**
> Every execution of any row creates one `attempt{n, started_at, ended_at, status, start_sha, log_path, engine_ref}`; harness fields are null for non-`agent` kinds. `step_run.retry_count` counts attempts beyond the first that were not redispatches.

---

## H12 — S2 — E7 `answer` vs E6 agent step: who archives the story file to `.answers/`

**AD text relied on:** AD-13 "routers call `signal_run(run_id, Signal)` … `cancel` runs in the request path" (only cancel is named as doing side effects); AD-9 "Answer and retry suffixes" in `compose_prompt`; FR-18 "on submit the Story file is moved to `.answers/`"; FR-16 "Retry after `ambiguous story file` first archives every matching file except the newest".

**Reading A (E7):** `signal_run(answer)` moves the file through `Workspace` in the request path (FR-18 says "on submit"), appends `## Human Answer`, then signals. **Reading B (E6):** the agent executor, seeing `ctx.resume_signal.kind == answer` on the next attempt, archives inside the engine step so it is durable and replay-safe (AD-6). Built together: the second move finds no file, the attempt starts with the archive *already done*, then routing reports `no story file` — because E6 also expected to read the blocking condition from the file it just could not find. Built with neither: the old `blocked` file stays, the re-dispatch is not a "first dispatch" and `bmad-build-auto` resumes from `blocked`.

**Tightened rule — AD-13, add:**
> `signal_run` writes only the database (gate_record with payload) and calls `engine.signal`; every worktree side effect of a signal (`answer` archive + `## Human Answer`, `retry` de-ambiguation archive, skip commit message) is performed inside the engine step that resumes the row, by the row's executor, reading `StepContext.resume_signal` (the gate_record the walker passes). `cancel` (kill, remove worktree) and `PUT /files` are the only worktree side effects in the request path.

---

## H13 — S2 — E6 budget check vs E7 `budget_raise`: is raising the budget the resume, and which row resumes?

**AD text relied on:** AD-8 Run diagram "`needs_you --> running`: signal answer/continue/retry/skip/skip_epic/budget_raise"; AD-13 signal list has both `budget_raise` and `continue`; FR-17 "raise the budget on the Run and Continue"; AD-9 agent step "checks budget … before returning".

**Reading A (E7):** `budget_raise{budget_usd}` sets the budget and resumes (one click). **Reading B (E7):** `budget_raise` only updates `run.budget_usd` (valid in any status) and the operator then presses Continue — but `continue` is validated "against the current status" and the parked row is `done` (the story file said `done`; only the budget tripped), so `continue` on a `done` row is a 409 under E7's own table. And E6 must choose the row status when the file is `done` but budget is exceeded: `done` with `park: budget` (AD-9 reads that way) or `error` — E8 colours differ.

**Tightened rule — AD-13:**
> `budget_raise{budget_usd}` is valid only while `park_kind = budget`, requires `budget_usd > spend_usd`, and is itself the resume. A budget park leaves the agent row in its routed status; `run.park_kind = budget` overrides the row's own park; on resume the walker continues at the first row not `done|skipped`.

---

## H14 — S3 — E7 vs E8: "the current step" is derived twice

**AD text relied on:** AD-8 "the UI renders the stored token"; FR-20 "Retry is offered on a `needs-you` Run whose current Step is `error`"; Entity has `run.park_kind` but no `run.park_path`.

**Reading A (E8):** current step = first row in path order that is not `done|skipped`. **Reading B (E7):** current step = the row of the latest `gate_record`. After `skip_epic` (planned rows become `skipped` out of order) or a redispatch (an earlier `build` row is `queued` while `verify` is `error`), A and B name different rows; E8 offers Retry on a row E7 refuses with 409.

**Tightened rule — Entity + AD-8:** `run.park_path` is written with `run.park_kind` by `apply_step_result` (H1) and cleared by `signal_run`; both the Run detail and `signal_run` validation use it — nobody scans rows.

---

## H15 — S3 — E4 walker vs E7 terminal resume: "the walker polls every 30 s" while the walker is blocked in `recv`

**AD text relied on:** AD-13 "the engine adapter waits (`recv` on `human:{run_id}`, 30 days)" and "the walker polls the worktree every 30 s through `Workspace`/`Git`".

**Reading A (E4):** the adapter's wait is `recv(timeout=30 s)` in a loop and the poll is an engine step between receives — replay-safe but 86 400 DBOS steps per 30-day park, and `application_version` bumps for the loop shape. **Reading B (E7):** a scheduled job `terminal_poll` (AD-6 `schedule`) polls every Run with `terminal_session = true` and sends the `terminal_release`-equivalent signal. Both compliant; A's step count is a real cost, B's signal is not in the AD-13 enumeration.

**Tightened rule — AD-13:** the poll is the scheduled job `terminal_poll` (every 30 s over Runs with `terminal_session and status = needs_you`); two consecutive clean `done` polls send `Signal{kind: terminal_resume}` (added to the enumeration), applied by `signal_run` like `continue` on the frame's `verify` row. The adapter's `recv` stays a single call.

---

## Summary table

| # | Sev | Pair | Hole | Fix location |
| --- | --- | --- | --- | --- |
| H1 | S1 | E4 / E7 / E6 | three writers of `needs_you`; cancel races an in-flight step; who re-queues on retry | AD-8 (`apply_step_result`, precondition, `signal_run` owns re-queue) |
| H2 | S1 | E5 / E4 / E7 | N branches per Run vs singular `worktree_path/branch/created_branch/pushed` | AD-14 + Entity (`run.worktrees[]`) |
| H3 | S1 | E5 / E7 | `checkpoint → queued: continue` re-parks a `checkpoint` row; skip on a checkpoint row | AD-8 step machine (kind-split edges) |
| H4 | S1 | E7 / E4 / E5 | skip's commit-guard + re-baseline are not plan rows; redispatch into a skipped row | AD-13 (`skip_story` / `skip_epic` frame semantics) |
| H5 | S2 | E6 / E10 / E5 / E7 | `attempt.start_sha` before/after WIP; operator edits false-park; `git.commit` check vacuous | AD-17 (start_sha after WIP, PUT /files commits, `frame_start_sha`) |
| H6 | S2 | E1 / E6 | static config cannot carry `run:` tags → spend = 0, budget never halts for codex/local | AD-10 (`HARNESS_ENV_CONTRACT`, env-name-only config) |
| H7 | S2 | E3 / E4 / E5 | `plan_run` pure vs persisting; `path` string order; plan-time vs run-time variable resolution | AD-7 (pure `Plan`, `seq`, `with_resolved`) |
| H8 | S3 | E8 / E3 | graph node id ≠ `step_run.path`; who derives group status | AD-15 (node/group ids, one aggregate rule) |
| H9 | S3 | E4 / E9 | `QueueEntry` shape vs FR-25 columns | AD-6 + AD-12 |
| H10 | S2 | E2 / E4 | `clone_check` two writers, zero enforcers | Entity + AD-14 |
| H11 | S3 | E5 / E6 / E9 / E10 | attempts for non-agent rows | Entity |
| H12 | S2 | E7 / E6 | `.answers/` archive done twice or never | AD-13 (signals write DB only) |
| H13 | S2 | E6 / E7 | `budget_raise` resume semantics, row status under budget park | AD-13 |
| H14 | S3 | E7 / E8 | "current step" derived two ways | Entity `run.park_path` |
| H15 | S3 | E4 / E7 | terminal poll vs blocked `recv` | AD-13 (`terminal_poll` job, `terminal_resume` signal) |

Not holes (checked and closed by the spine as written): `Harness.resume` only within one row (AD-10 maker ≠ checker); `git.push` on default branch (AD-14); template pinning transitivity (AD-15); who enumerates kinds (AD-9 registry); credentials never reaching the harness env (AD-5); `application_version` bump discipline (AD-6).
