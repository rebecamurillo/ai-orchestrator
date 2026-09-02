---
title: Reconciliation — prd.md against ARCHITECTURE-SPINE.md after the 2026-09-02 §I update
date: 2026-09-02
inputs:
  - ../../addendum.md §I "Feedback to the spine (2026-09-02 PRD update)" — 13 items
  - ../../prd.md (FR-1..FR-33, §4.6 Stop table, §8, NFR-1..9)
  - ../ARCHITECTURE-SPINE.md (updated 2026-09-02)
  - ../../reconcile-spine.md (prior pass: 1 high · 10 medium · 21 low)
  - cross-checked: ../deliverables/.env.example, ../deliverables/scripts/harness/_common.sh, ../../template-dsl-draft.md
---

# Reconciliation — PRD vs spine, post-§I update

The PRD is the load-bearing input; the spine was updated to absorb addendum §I. Severity: **high** = a builder would build the wrong thing against a MUST; **medium** = a builder must choose between two stated behaviours or invent a mechanism; **low** = wording, example, tier or scope drift.

**Result.** §I: **13 absorbed · 0 partial · 0 missing.** Remaining after the update: **0 high · 3 medium · 18 low** contradictions, plus 8 silent drops (all low) and 4 quiet-rule gaps (all low). Of the prior 32 findings: **14 closed · 3 partially closed · 15 remain** (one of them, S8, is now a medium contradiction).

## 1. §I absorption table

| # | §I item | Status | Where the spine absorbs it (quoted) |
| --- | --- | --- | --- |
| 1 | Prepare commit (AD-9, AD-17) | **absorbed** | AD-9: "The `agent` executor commits everything it writes before dispatch: WIP commit (…, only when dirty) → `project-context.md`, Answer archive, `## Verify Failure` → commit `orchestrator: prepare story {id} attempt {n}` (only when something was written) → `attempt.start_sha = HEAD` → dispatch; the harness always starts on a clean tree". AD-17: "`attempt.start_sha` is HEAD *after* the WIP commit and the prepare commit (AD-9)". Kinds table `agent`: "WIP commit → `project-context.md` + signal writes → prepare commit → `start_sha` → `compose_prompt` → dispatch". Conventions → Commits list `orchestrator: prepare story {id} attempt {n}`. |
| 2 | Protected test set frozen at frame start (AD-17) | **absorbed** | AD-17: "every file matching `repository.test_globs` … that existed at the **story frame's first attempt** (`Git.list_files(frame_first_start_sha, …)`, recorded on the frame's first `attempt`); files the agent added inside the frame stay editable on its later attempts". Seed: `attempt.frozen_test_files (first attempt of a story frame only)`. |
| 3 | `story@1` callee-only; readiness runs `epic@1` (AD-10, AD-16, seed) | **absorbed** | AD-7: "`story@1` has no checkout and is a callee only: `create_run` accepts `initiative`, `epic`, `repo-init`." AD-10: "a harness is `enabled` only after an `epic@1` Run on `fixtures/readiness-repo/` (built-in Project `readiness`, uneditable; branch `readiness/{harness}/{date}`, never pushed; an ordinary Run on the Board)". Seed: "`fixtures/readiness-repo/` # one-story repository run through epic@1". (AD-16 itself is unchanged; the item lands in AD-7/AD-10/seed.) |
| 4 | Signals (AD-13): `answer` at checkpoint; `continue` at `protected_path`; `plan_stale` with `continue \| cancel`; `budget_raise` resumes at routed status; `skip_epic` keeps push/`pr.link`; `terminal_resume` marks agent row `done` | **absorbed** | AD-13 table: `answer` "Valid when `park_kind ∈ {blocked, checkpoint}` on an `agent` row (at a spec checkpoint = *Reject with a reason*)"; `continue` "`park_kind ∈ {checkpoint, protected_path, plan_stale}`"; `budget_raise` "the walker resumes at the row's routed status (`blocked`/`checkpoint` re-park immediately; `done` continues)"; `skip_epic` "the epic's `git.push` / `pr.link` stay planned (they are marked skipped only when the push itself is the stop)"; `terminal_resume` "the `agent` row `→ done` (actor `terminal`), gate_record \| verify runs \| `blocked → done`, verify `→ queued`". `cancel` "any non-terminal". |
| 5 | Park kinds (AD-13, AD-8): `push_rejected` ⊇ `sync: branch diverged`; `misconfigured` ⊇ five reasons; `failed` reason `parked 30 days` | **absorbed** | AD-13: "`push_rejected` also carries `sync: branch diverged`; `misconfigured` also carries `no story file`, `ambiguous story file`, `unexpected status: {s}`, `harness exit {code}`, `gateway unreachable`; the PRD §4.6 table is the reason-text and admitted-signal contract"; "`recv` on `human:{run_id}` (30 days; expiry is applied by the walker as Run `failed`, reason `parked 30 days`)". AD-8 diagram: `needs_you --> failed: parked 30 days (recv expiry)`. |
| 6 | Stale-plan check (AD-7); `PUT /runs/{id}/files` refuses list files | **absorbed** | AD-7: "Before the first row the walker re-reads every list file at the branch head and compares it with its content at `plan_ref`; a difference is applied as park `plan_stale: {file}` (AD-13) — a plan is never silently executed against a changed list." AD-13: "`PUT /runs/{id}/files` (spec folder only, … never `stories.yaml` or `epics.yaml` — the planned list files are read-only, `planned at {plan_ref}`)". Capability map FR-8: "stale-plan check at start … walker first step". |
| 7 | `git.sync` no-op without upstream; `retry` on `push_rejected` syncs first | **absorbed** | Kinds table `git.sync`: "fetch + `pull --ff-only`; recorded no-op when the branch has no upstream; non-fast-forward → park `push_rejected` (`sync: branch diverged`)". AD-14: "`Git.sync` is a recorded no-op when the branch has no upstream". AD-13 `retry`: "on `push_rejected` rows a `Git.sync` runs first". (See R-2: the PRD names a *different* retry that syncs first.) |
| 8 | Install inside `git.worktree`; no separate `install` step in `epic@1` | **absorbed** | Kinds table `git.worktree`: "runs `install_command` when declared (output in the row log; `epic@1` has no separate install row)". AD-14: "`git.worktree` runs `repository.install_command` in the new or reused worktree (output in the row log; no separate install row)". |
| 9 | Two Gateway keys (AD-5, AD-11, `.env.example`) | **absorbed** | AD-5: "`LITELLM_API_KEY`, `LITELLM_SPEND_KEY` … never `LITELLM_SPEND_KEY` (the spend-reading key, used only by `infrastructure/gateway/`)". AD-11: "reads `GET /spend/logs/v2?…` with `LITELLM_SPEND_KEY` (never the harness key)". Env table: `LITELLM_API_KEY` "can only call models"; `LITELLM_SPEND_KEY` "backend-api `infrastructure/gateway/` only". `_common.sh` `HARNESS_ENV_CONTRACT` carries `LITELLM_API_KEY` only; `.env.example` lines 29–30 declare both. Open at handoff 6 records PRD §8 item 5. |
| 10 | Harness readiness state + `POST /harnesses/{name}/readiness` | **absorbed** | AD-10: "Readiness is persisted state, table `harness{name, enabled, last_readiness_at, failing_check, version_pin}`, written only by `use_cases/harness_readiness` … each check is a line, the first failing one is `failing_check`. A changed `version_pin` disables the harness for new Runs; parked Runs keep it. `POST /harnesses/{name}/readiness` starts the run; `GET /harnesses` feeds New workflow." Routes convention adds `harnesses`; ER diagram `HARNESS ||--o{ RUN`; seed field list. |
| 11 | Clone check reads the method version (AD-14) | **absorbed** | AD-14: "`repository.clone_check{status, at, output, bmad_version}` … also reads `_bmad/_config/manifest.yaml` at the default branch (`bmad_version` = its version, `missing`, or `outdated` against `BMAD_VERSION`)". Capability map FR-2..4: "clone check (incl. `bmad_version`)". |
| 12 | `MAX_ACTIVE_RUNS` setting; reason `global concurrency, held by {runs}` (AD-12, `.env.example`) | **absorbed** | AD-12: "global concurrency `MAX_ACTIVE_RUNS` (instance setting, default 2) … `reason ∈ {repository lock held by {run}, global concurrency, held by {runs}, running, waiting for your answer}`". Env table `MAX_ACTIVE_RUNS` "global queue concurrency (AD-12), default 2"; `.env.example` line 22. |
| 13 | Graph (AD-15): `SKP` group token; label vs path | **absorbed** | AD-15: "else `skipped` when all are `skipped`; else `done` when all are `done \| skipped`"; "Every node carries `label` (human, e.g. `epic 1 · story 4-1 · build`) beside `path`; cards and strips show `label`, the Steps table and gate record show `path`". |

## 2. Remaining contradictions

Items tagged `(gap)` are PRD requirements without a spine mechanism; the rest are direct conflicts. R-numbers are new; the prior C-number is cited where the item survives from the earlier pass.

### Medium

| # | Sev | PRD — quoted | Spine — quoted | Finding |
| --- | --- | --- | --- | --- |
| R-1 | **medium** (was S8) | FR-31: "The check compares the tree against the Attempt's start commit (after the prepare commit of FR-12), so an Operator edit made while the Run was parked (FR-19) and every file the orchestrator wrote are never attributed to the agent." FR-19: inline edits are "committed at once on the branch as `spec: operator edit (orchestrator)` … so the next Attempt starts from it and the Protected-path check (FR-31) never attributes it to the agent." | AD-17: "before making those commits the `agent` executor checks `Git.diff_names(previous_attempt.start_sha)` and attributes a hit to the previous attempt"; and "in the `git.commit` executor against `ctx.frame_start_sha` (the frame's first `agent` attempt's `start_sha`, else HEAD)". | Both spine baselines predate operator commits. Sequence: Story parks `blocked`/`checkpoint` → Operator edits `SPEC.md` inline (committed `spec: operator edit`) → Answer/Continue → the `agent` executor's pre-WIP `diff_names(previous_attempt.start_sha)` lists `SPEC.md` → `protected_path` park blamed on the previous attempt. Likewise the commit-guard `diff_names(frame_start_sha)` lists the same edit made between attempt 1 and the commit-guard. A builder following the spine ships a false park on exactly the flow FR-19/FR-31 protect. Fix: diff only against the *latest* attempt's `start_sha` (drop the pre-WIP check or restrict it to the uncommitted tree), or exclude commits with the orchestrator's own messages. |
| R-2 | **medium** | FR-20: "After `re-baseline failed after skip` the Operator fixes the tree on the branch (inline edit, terminal session, or a push to the remote followed by Retry, **which syncs first**) and Retries the verify Step". FR-11: "Retry re-runs the push after the Operator resolves it." | AD-13 `retry`: "executor archives all-but-newest ambiguous files, then re-runs; **on `push_rejected` rows a `Git.sync` runs first**". No sync on a `verify_failed` retry; a sync before a push retry has no PRD counterpart. | The PRD attaches sync-first to the retry of a *verify* row after a skip re-baseline (so a fix pushed to the remote reaches the worktree); the spine attaches it to `push_rejected` rows only. Under the spine the operator's "push to the remote followed by Retry" re-runs verify on the stale tree and fails again. Decide: `retry` syncs first on `verify_failed` (PRD) and/or on `push_rejected` (spine); state both in AD-13 and FR-20/FR-11. |
| R-3 | **medium** | §4.6 table: `push_rejected` — reasons `push rejected`, `sync: branch diverged` — admits "Retry, Skip epic, Cancel" (no Skip story). Also "Skip story and Skip epic are not offered on `budget` or `plan_stale`." | AD-13 `skip_story`: "Valid when `park_kind ∉ {budget}` and `park_path` inside a story frame"; `skip_epic`: "as `skip_story`". AD-13 preamble: "the PRD §4.6 table is the reason-text and admitted-signal contract". | For `sync: branch diverged` the parked row is the story frame's `sync` row, so the spine's rule admits Skip story where the PRD refuses it (skipping leaves the next story to hit the same diverged sync). `plan_stale` is excluded only implicitly (its `park_path` is unstated). The spine both defers to the PRD table and carries its own "Valid when" column; `signal_run` will be coded from the column. Fix: make the column a literal of the PRD table (`skip_story` valid when `park_kind ∈ {blocked, checkpoint, verify_failed, timeout, protected_path, misconfigured, internal}`; `skip_epic` adds `push_rejected`). |

### Low

| # | Sev | PRD — quoted | Spine — quoted | Finding |
| --- | --- | --- | --- | --- |
| R-4 (C12) | low | §3 Path: "e.g. `epics[0].stories[3].build`"; §4.7: "the raw Path (`epics[0].stories[3].build`)". | AD-7: "A `template` call is a path segment, not a row"; AD-15 template-graph example `stories.story.build`; DSL draft step ids `epics` → `epic` (call) → `stories` → `story` (call) → `build`. | The shipped ids make the run path `epics[0].epic.stories[3].story.build`. Either the PRD example gains the call segments or AD-7 states that call segments are elided from `path`. |
| R-5 (C14) | low | FR-9: "An existing Worktree … is reused when `git status --porcelain` is empty; otherwise the Run refuses to start with the reason." | AD-14 `git.worktree`: "reuse when clean, refuse when dirty"; pre-flight checks held branches only. | The refusal is a row-time `error`, not a *Start run* refusal, and no `Park.kind` is named for it (`misconfigured`? `internal`?). Add "worktree dirty" to pre-flight or reword FR-9 and name the kind. |
| R-6 (C15) | low | FR-1: "every `/api/*` call requires the resulting session". | AD-1: backend-api "`/api/v1/*` … no cookies"; AD-4: bearer on backend-api, cookie on web-client. | True only for web-client's `/api/` proxy; say so. |
| R-7 (C16/Q2) | low | FR-22: "A wait longer than 48 h renders its age in amber." | Conventions → UI signal: "exactly one element per card or row carries a signal colour … a screen with nothing needing the Operator has no amber or red pixel"; NFR-6 same. | A Queued/Running card older than 48 h carries a second amber element. Resolve as before. |
| R-8 (C17) | low | FR-14 / §8: "Confirmed against Claude Code 2.1.246". | Stack: Claude Code 2.1.258. | Not a conflict (FR-33 re-verifies on pin change); the PRD should say the observation predates the pinned build. |
| R-9 | low | FR-15: "The file is regenerated at every dispatch and **committed by the commit-guard**". FR-12 (same PRD): `project-context.md` is committed as `orchestrator: prepare story {id} attempt {n}`. | AD-9: `project-context.md` is in the prepare commit before dispatch. | FR-15 is stale against both FR-12 and the spine; replace "committed by the commit-guard" with "committed in the prepare commit (FR-12)". |
| R-10 | low | FR-26 `[ASSUMPTION: … the spine's single LITELLM_API_KEY is split accordingly]`. | AD-5/AD-11/env table already carry `LITELLM_API_KEY` + `LITELLM_SPEND_KEY`. | Assumption text is stale; the split is now a spine decision (§8 item 5 / Open at handoff 6 remain for the host side). |
| R-11 | low | FR-25: reasons are "`repository lock held by {run}`, `global concurrency`, `running`, `waiting for your answer`"; FR-13 / UJ-2 print "`waiting: repository lock held by …`", "`waiting: global concurrency, held by {runs}`". | AD-12: "`reason ∈ {repository lock held by {run}, global concurrency, held by {runs}, running, waiting for your answer}`". | FR-25 drops `, held by {runs}` and the `waiting:` prefix is PRD-only. Align FR-25 with FR-13; state whether `waiting:` is a UI prefix. |
| R-12 | low | FR-33: five readiness lines — "the Story file reaches `done` …; a Session id was recorded; the Run trace contains …; the Gateway returned a non-empty spend …; verify exited 0". | AD-10: three conjuncts — Run "reaches `done` **and** the Run trace holds the attempt's spans … **and** `Gateway.spend_for_attempt` returns a non-empty result"; "each check is a line". | Two PRD lines (session id recorded; verify exited 0) have no spine check; "Run done" subsumes verify only if the fixture declares `quality_gate_command`. State all five lines in AD-10 (and that the fixture repository declares a quality command). |
| R-13 `(gap)` | low | FR-33: readiness Run "on branch `readiness/{harness}/{date}`, **never pushed**"; FR-8: a Run targets a registered Repository (URL, Clone check). | AD-10: same words; seed `fixtures/readiness-repo/` is a path inside the orchestrator repo; `epic@1` ends with `git.push` and `pr.link` rows. | Neither document says how the `git.push`/`pr.link` rows of `epic@1` are prevented on the readiness Run (skipped rows? local bare remote? `repository.url` = a `file://` path inside the image?) nor what `compare_url` means for a local fixture. Shared gap; one sentence in AD-10. |
| R-14 | low | §4.6 table: `re-baseline failed after skip` is a `verify_failed` stop. | AD-9: "a redispatch whose target row is `skipped` is applied as `escalate` with reason `re-baseline failed after skip`" — `escalate` is an `on_fail` value, not a `Park.kind`. | Name the kind in AD-9 ("park `verify_failed`"). |
| R-15 | low | §4.6 table: `plan_stale` admits "Continue, Cancel". | AD-13 `retry`: valid when "`park_kind ∈ {…}` **or row `error`**"; AD-7 parks `plan_stale` "before the first row" — the parked row and its status are unstated (`park_path` = ?). | If the walker marks the first row `error`, `retry` becomes valid on `plan_stale`. State that `plan_stale` sets no row status (`park_path` null) and is excluded from `retry`/`skip_*`. |
| R-16 | low | FR-19: each inline save "is committed at once … and **named in the gate record**". | AD-13: `PUT /runs/{id}/files` "commits the edit immediately as `spec: operator edit (orchestrator)`"; AD-8: `gate_record.event` ∈ Park kinds ∪ Signal kinds ∪ `{start, done, failed, cancelled}` — no file-edit event. | The spine writes no gate record for an inline edit and has no event token for one. Add `file_edit` (path in text) to AD-8 or drop "named in the gate record" from FR-19. |
| R-17 `(gap)` | low | FR-26: "A Harness process with the Gateway unreachable fails its Step with `error`"; §4.6: `misconfigured` reason `gateway unreachable`. | AD-13 lists the reason; AD-10: adapters "never read model output" and return "nothing interpreted". | No mechanism distinguishes `gateway unreachable` from `harness exit {code}` without reading output. Either a pre-dispatch `GET {LITELLM_BASE_URL}/health` in the `agent` executor, or fold the reason into `harness exit {code}`. |
| R-18 `(gap)` | low | FR-28: "per-Project monthly spend shown on the Project" (COULD, §6.1). | No route or read model; AD-11: "Cost per path is a SQL sum of `attempt.cost_usd` over the path prefix". | COULD tier; add a `GET /projects/{id}` field or note it as deferred in the spine. |
| R-19 | low | FR-12: "The Attempt's start commit is **the second one**". | AD-9: WIP commit "only when dirty", prepare commit "only when something was written"; `start_sha = HEAD`. | Both commits are conditional; "the second one" is loose. Say "HEAD after both (possibly empty) commits". |
| R-20 (S5) | low | FR-12: "An orchestrator image upgrade while Runs are parked does not re-plan them; a parked Run resumes on the new image"; `[ASSUMPTION: image upgrades are drained of running Runs, not of parked ones]`. | AD-6: "`application_version` is the pinned `DBOS_APPLICATION_VERSION`, bumped deliberately when the walker's step sequence changes, **after draining active Runs**". | A DBOS workflow parked in `recv` under version A is not resumed by a version-B process; the PRD's guarantee holds only while `DBOS_APPLICATION_VERSION` is unchanged. State the condition in FR-12 (or keep the old version's executor running until parked Runs drain). |
| R-21 (C18) | low | Addendum §F week plan. | AD-10/AD-16/AD-19: `fixtures/readiness-repo/`, `repo-init@1`, `harness_readiness`, `trajectory`. | Template names fixed; the plan still has no slot for FR-30 (`repo-init`), FR-31, FR-32, FR-33 (fixture + readiness). |

## 3. Silent drops — operator-visible spine decisions with no PRD counterpart

| # | Sev | Spine | Operator-visible effect | PRD place |
| --- | --- | --- | --- | --- |
| D-1 (S1) | low | AD-7 / DSL: `pause_before_item_when` → `checkpoint` row at `…stories[n].before`. | FR-5 now lists the key, but no `stories.yaml` field feeds it and the glossary knows only spec and done checkpoints. | §3 Checkpoint, FR-10 (or state `epic@1` does not use it). |
| D-2 (S2) | low | AD-13 `budget_raise` valid only when "`budget_usd > spend_usd`" (else 409). | Raising to a figure at or below current spend is refused. | FR-17. |
| D-3 (S4) | low | AD-14 `worktree_gc` "removes worktrees **and logs** of terminal Runs after 7 days". | The process log FR-14 records and FR-25 links to disappears after 7 days; FR-9/FR-12 mention worktrees only. | FR-9 / FR-25. |
| D-4 (S6) | low | Conventions → Operations: nightly `pg_dump` (`public` + `dbos`), 14 days, `host/backups/`; `agent-home` not backed up. | Recovery point one night; sessions lost on restore. | NFR-7 or §12. |
| D-5 (S7) | low | AD-15 entity-input whitelist: `project.name`, `repository.url \| default_branch \| install_command \| quality_gate_command \| unit_test_command`. | A Template author cannot reference `repository.test_globs`, `package_manager`, or Project context; validator rejects as unbound. | FR-5. |
| D-6 | low | AD-13 `retry`: "on `push_rejected` rows a `Git.sync` runs first". | A Retry on a rejected push first fast-forwards the worktree from origin (and can itself park `sync: branch diverged`); FR-11 says only "Retry re-runs the push". | FR-11 (see R-2). |
| D-7 | low | AD-13 `answer`: valid "on an `agent` row" only. | *Reject with a reason* is refused (409) at a done checkpoint even though the button set is shared; PRD says "(spec only)" in the table, so this is consistent — record it as the mechanism. | §4.6 note (no change needed beyond wording). |
| D-8 | low | AD-8: any executor exception → reason "`internal: {exception class}`". | The screen shows a Python class name where FR-16 says `internal: {error}`. | FR-16 (state the reason carries the class name, not the message). |

### Quiet rules the spine carries and the PRD still omits (unchanged from the prior pass)

| # | Sev | Spine | PRD state | Fix |
| --- | --- | --- | --- | --- |
| Q-1 | low | Conventions: "`skipped`, `unvalidated`, `liveness` are words; only `deterministic` or `human` gates may render green." | NFR-2 lists `skipped`/`unvalidated` only; NFR-8's word list omits `liveness`; `pr.link` (liveness) uncovered. | NFR-2. |
| Q-3 | low | Form errors: "page re-renders with every submitted value … no toast, no redirect on error". | NFR-8 silent; nothing forbids toasts. | NFR-8. |
| Q-4 | low | AD-8: "The UI renders stored tokens; the only derived token is the group status of AD-15." | FR-29 states the group rule; no NFR says the UI derives nothing else. | NFR-2. |
| Q-5 (reverse) | low | Kinds table `git.push`: "refuses default branch; rejected push → park `push_rejected`". | PRD FR-11/§5/§11 "never force-pushes"; the kind row does not say `--force` is never passed. | Kinds table `git.push`. |

(Q-2 is R-7.)

## 4. Prior findings status (reconcile-spine.md, 32 items)

| Prior | Was | Now | Evidence |
| --- | --- | --- | --- |
| C1 answer at spec checkpoint | high | **closed** | AD-13 `answer` valid at `park_kind ∈ {blocked, checkpoint}` on an `agent` row "(at a spec checkpoint = *Reject with a reason*)". |
| C2 `needs-you` vs `needs_you` | medium | **closed** | PRD §3: "`needs-you` is stored as `needs_you`". |
| C3 clone check blocks save | medium | **closed** | PRD FR-4: "A failing check does not block the save"; AD-14 unchanged. |
| C4 install row vs `git.worktree` | medium | **closed** | PRD FR-9 "records its output in the checkout Step"; kinds table "no separate install row". |
| C5 unmapped stop reasons | medium | **closed** (residual R-14, R-15) | AD-13 maps every §4.6 reason to a kind; `plan_stale` added. |
| C6 template vs run graph "identical" | medium | **closed** | PRD FR-29: "loops unexpanded and calls collapsed; the Run graph expands them". |
| C7 dirty tree at dispatch | medium | **closed** | AD-9 prepare commit; PRD FR-12. |
| C8 harness readiness surface | medium | **closed** (residual R-12, R-13) | AD-10 `harness` table, `GET/POST /harnesses`, built-in Project `readiness`. |
| C9 method version on the row | medium | **closed** | AD-14 `clone_check.bmad_version`. |
| C10 `git.sync` without upstream | medium | **closed** | AD-14 / kinds table "recorded no-op when the branch has no upstream". |
| C11 `terminal_resume` row status | medium | **closed** | AD-13 `terminal_resume` "`blocked → done`". |
| C12 Path example | low | **remains** → R-4 | |
| C13 `pause_when`/`escalate_when` in FR-5 | low | **closed** | PRD FR-5 lists both (the "no conditionals" sentence beside them is loose wording only). |
| C14 dirty-worktree refusal timing | low | **remains** → R-5 | |
| C15 FR-1 `/api/*` | low | **remains** → R-6 | |
| C16 48 h amber | low | **remains** → R-7 | |
| C17 2.1.246 vs 2.1.258 | low | **remains** → R-8 | |
| C18 addendum §F | low | **partially closed** → R-21 | Template names fixed; no slot for FR-30..33. |
| C19 `binds` NFR-9 | low | **closed** | Spine front matter `binds: […, NFR-9]`. |
| S1 before-item checkpoint | low | **partially closed** → D-1 | FR-5 lists the key; no behaviour. |
| S2 `budget_raise > spend` | low | **remains** → D-2 | |
| S3 `--max-budget-usd` surface | low | **closed** | PRD FR-14: cap exit "routed as a budget halt (FR-17), never as a retry"; AD-10 same. |
| S4 logs GC'd at 7 days | low | **remains** → D-3 | |
| S5 walker version drain | low | **partially closed** → R-20 | PRD assumption added but contradicts AD-6 for parked Runs. |
| S6 backups | low | **remains** → D-4 | |
| S7 entity-input whitelist | low | **remains** → D-5 | |
| S8 pre-WIP protected check | low | **remains, upgraded** → R-1 (medium) | Now a contradiction with FR-19/FR-31 on operator edits. |
| Q1 `liveness` never green | low | **remains** → Q-1 | |
| Q2 amber pixel | low | **remains** (= R-7) | |
| Q3 no toast | low | **remains** → Q-3 | |
| Q4 UI derives nothing | low | **remains** → Q-4 | |
| Q5 never `--force` | low | **remains** → Q-5 | |

Totals: closed 14 (C1–C11, C13, C19, S3) · partially closed 3 (C18, S1, S5) · remain 15 (C12, C14–C17, S2, S4, S6–S8, Q1–Q5).

## 5. Verified consistent after the update (brief)

Signal set and glossary (§3 Signal ↔ AD-13); Stop kinds and tokens (§4.6 ↔ AD-13, conventions); prepare commit and `start_sha` (FR-12, FR-31 ↔ AD-9, AD-17); frozen test set per frame (FR-31 ↔ AD-17, seed); `story@1` callee-only and New workflow set (FR-8, §4.3 ↔ AD-7); readiness state, pin invalidation, built-in Project, branch name (FR-33 ↔ AD-10, seed, conventions); stale-plan park and read-only list files (FR-8, FR-19 ↔ AD-7, AD-13); `budget_raise` resume rule (FR-17 ↔ AD-11, AD-13); `skip_epic` keeps push/link (FR-20 ↔ AD-13); `terminal_resume` (FR-21 ↔ AD-13); two keys and the harness env contract (FR-14, FR-26, NFR-3 ↔ AD-5, AD-10, AD-11, `_common.sh`, `.env.example`); `bmad_version` on the row (FR-30 ↔ AD-14); `MAX_ACTIVE_RUNS` and queue reasons (FR-13 ↔ AD-12); `SKP` group rule and label/path split (FR-29, §4.7 ↔ AD-15); install inside checkout (FR-9, §6.2 ↔ kinds table); story attempt bound `(1 + 2) × (1 + 1) = 6` (FR-10 ↔ `story@1` `retry.max: 2`, `on_fail.max: 1`); §8 open items 1–5 ↔ Open at handoff 3, 1, 4, 5, 6 (item 2 architecture-internal).
