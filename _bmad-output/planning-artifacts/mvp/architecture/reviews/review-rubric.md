---
title: Rubric review — ARCHITECTURE-SPINE.md (ai-orchestrator-mvp)
reviewer: rubric walker
reviewed: 2026-09-02 (update pass)
subject: ../ARCHITECTURE-SPINE.md (status final, updated 2026-09-02, second pass)
driving-spec: ../../prd.md (updated 2026-09-02; FR-1..FR-33, NFR-1..NFR-9)
verdict: ready for handoff after three local edits — no critical finding; every critical/high finding of the first pass is resolved; three new high findings, each fixed by one to three lines in AD-10, AD-13 or AD-17
---

# Rubric review — 2026-09-02 update pass

Scope of this pass: the amended items (AD-5, AD-7, AD-8, AD-9, AD-10, AD-11, AD-12, AD-13, AD-14, AD-15, AD-17, conventions › routes and commits, structural seed › harness table / `clone_check.bmad_version` / `attempt.frozen_test_files` / kinds table / env table, capability map FR-30..FR-33, Deferred, Open at handoff 6) and their consistency with the untouched ADs (AD-1..AD-4, AD-6, AD-16, AD-18..AD-20). Named-technology freshness is not judged here (separate lens).

## Disposition of the first-pass findings

| First pass | Status now |
| --- | --- |
| C-1 signal side effects unowned | Resolved — AD-13 per-signal table (request-path writes / effects in the resumed step / row transition); `PUT /runs/{id}/files` and `cancel` named as the only non-engine worktree writes |
| H-1 `path` order | Resolved — `step_run.seq` dense integer, walker executes in `seq` order (AD-7, seed) |
| H-2 `Git` cannot list at a ref | Resolved — `Git.list_files(ref, prefix)` (AD-14), used by `plan_run` and AD-17 |
| H-3 DSL key set | Resolved — "Template DSL v1 keys" table in the seed, `validate.py` implements exactly it (AD-15) |
| H-4 per-attempt cost | Resolved — `attempt:` tag, `x-litellm-session-id = attempt_id`, `Gateway.spend_for_attempt`, provisional fallback (AD-11) |
| H-5 unexpected exception | Resolved — caught by the walker, row `error`, `park_kind = internal` (AD-8); `internal` in the `Park.kind` enum (AD-13) |
| H-6 `dev-loop` mapping | Resolved — last sentences of AD-7 |
| H-7 signal vocabulary / `checkpoint → done` | Resolved — one vocabulary in AD-8 text, both diagrams, AD-13 |
| M-1..M-8, L-1..L-8 | Resolved (Operations, Read models, activity endpoint, AD-1 fetch modules, Form errors, kinds table, transaction/timeout folded into AD-8/AD-14, pins, `/healthz`, environments, `PUT /files` vs terminal session, "other fields follow the PRD glossary") |

## Method — divergence scenarios for the amended items

| # | Unit A | Unit B | Divergence point | Settled? |
| --- | --- | --- | --- | --- |
| S1 | Harness readiness (FR-33) | Pre-flight / `create_run` (FR-8) | Can a readiness Run start while its harness is `disabled`? | **No** → H-1 |
| S2 | Agent step (FR-16, FR-31) | Commit-guard (FR-10, FR-31) | Are files the Operator accepted on `protected_path` re-reported by later checks in the same frame? | **No** → H-2 |
| S3 | Human gates (FR-20) | Push / compare link (FR-11) | Is `skip_epic` valid on a rejected push? | **No** — AD-13 "Valid when" contradicts its own effects column and PRD §4.6 → H-3 |
| S4 | Human gates (FR-17) | Walker (AD-8) | Who re-parks a `blocked` row after `budget_raise` when the resumed step does "none"? | Partly → M-1 |
| S5 | Human gates (FR-20) | Story loop (FR-10) | `skip_story` on `sync: branch diverged`; `skip_epic` over remaining frames' `sync`/`verify`/`git.commit` rows | Partly → M-2, M-3 |
| S6 | Repository init (FR-30) | Pre-flight (FR-8, AD-16) | Does the `_bmad/` version check apply to `repo-init@1`? | **No** → M-5 |
| S7 | Harness scripts (`_common.sh`) | Harness adapters / `env_for` | The literal `HARNESS_ENV_CONTRACT` vs the variables AD-5 and AD-11 require | Partly → M-6 |
| S8 | Claude adapter (AD-10) | Agent executor (AD-9, AD-11) | How a budget-cap exit is told apart from an expect miss when the adapter interprets nothing | Partly → M-7 |
| S9 | Terminal resume (FR-21) | Signals API | Which request sets `terminal_session = true` | **No** → M-4 |
| S10 | Planner (AD-7) | Walker (AD-7 stale check) | Which ref the stale check reads; `park_path` of a `plan_stale` park | Partly → L-3 |
| S11 | Executor order (AD-9) | Start-SHA rule (AD-17) | `attempt.start_sha` = HEAD after WIP + prepare commit | Yes — both say so; the kinds table repeats the same order |
| S12 | Signals (AD-13) | Run/Step diagrams (AD-8) | Names and transitions | Yes for names and all listed edges; three edges missing → L-6, L-7 |
| S13 | Spend (AD-11) | Settings (AD-5), env table, Open 6 | Two gateway keys | Yes — `LITELLM_API_KEY` / `LITELLM_SPEND_KEY` consistent in all four places |
| S14 | Trajectory (FR-32) | Steps (AD-9) | Trigger and writer | Yes — AD-19 |

## Checklist

| Item | Result | One-line reason |
| --- | --- | --- |
| 1 Fixes the real divergence points below (epics/stories) and misses none | adequate | All first-pass gaps closed; three new ones in the amended text (S1, S2, S3) — each a local edit |
| 2 Every AD's Rule is enforceable and prevents its stated divergence | adequate | AD-17 as written re-detects an accepted hit forever (H-2); AD-13 "Valid when" for `skip_epic` forbids what its effects column describes (H-3); AD-10 enables a harness only through a Run the same rule forbids starting (H-1); the rest enforceable |
| 3 Nothing under Deferred could let two units diverge | strong | Every bullet names its landing place and the MVP behaviour (`plan_stale`, `MAX_ACTIVE_RUNS`, tags, firewall doc); nothing undecided is parked there |
| 4 Named tech verified-current | skipped | Freshness lens |
| 5 Covers the PRD's capabilities (FR-1..FR-33, NFR-1..NFR-9) | strong | Every FR and NFR has a row in the capability map or a Deferred bullet; FR-30..FR-33 mapped to AD-16, AD-17, AD-19, AD-10; §4.6 kinds and reason texts match AD-13's enum; the FR-33 mechanics are thin (M-8) |
| 6 Every dimension the altitude owns is decided, deferred, or open | strong | Backups, environments, error handling, read models, activity time now decided; six open items each carry a day and a fallback |
| 7 AD-13 table vs AD-8 diagrams vs PRD §4.6 | thin | Kinds: 10/10 match. Admitted signals: 2 divergences (`skip_epic` on `push rejected` — H-3; `skip_story` on `sync: branch diverged` — M-2). Diagrams: `terminal_resume` from `checkpoint`/`error`, `error → queued` for the verify row on redispatch, and `answer` on `checkpoint` are unlabelled (L-6, L-7) |
| 8 AD-9 executor order vs AD-17 `start_sha` rule | adequate | They agree (HEAD after WIP + prepare); the pre-dispatch "check of the previous attempt" is not reconciled with an accepted hit (H-2) or with `diff_names` semantics (L-4) |

## Findings

### High

#### H-1 — The readiness Run cannot start: pre-flight requires the harness to be `enabled`, and only that Run enables it (AD-10, capability map FR-8; PRD FR-8, FR-33)

Spine: AD-10 — "a harness is `enabled` only after an `epic@1` Run on `fixtures/readiness-repo/` … reaches `done` … `POST /harnesses/{name}/readiness` starts the run"; capability map FR-8 lists "harness enabled" among the pre-flight checks that `create_run` shares with pre-flight, and PRD FR-8 says "Any failing check disables *Start run*". A readiness Run is "an ordinary Run on the Board", so the pre-flight epic will apply the check to it and every harness stays `disabled` forever. The readiness epic and the pre-flight epic are different units; neither text tells them who yields.

**Smallest fix:** add to AD-10's Rule: "The `harness enabled` pre-flight check is skipped for Runs whose Project is `readiness`; no other check is."

#### H-2 — An accepted `protected_path` hit is re-detected by the next check in the same frame (AD-17, AD-9; PRD FR-31)

Spine: AD-17 — "before making those commits the `agent` executor checks `Git.diff_names(previous_attempt.start_sha)` and attributes a hit to the previous attempt … in the `git.commit` executor against `ctx.frame_start_sha` … `continue` on `protected_path` accepts it (file list in `gate_record` and `trajectory`) and routing resumes on the same tree." Nothing removes accepted files from later checks. Sequence: attempt n modifies `tests/x.test.ts` → park → Operator accepts → routing resumes → row `done` → `git.commit` checks `diff_names(frame_start_sha)` → the same file → park again; or the row routes `blocked` → Answer → attempt n+1 → the pre-dispatch check against `attempt_n.start_sha` → the same file → park again. PRD FR-31 says "Accepting is the only way an agent-made test change ships"; as written it cannot ship.

**Smallest fix:** in AD-17: "`rules/protected_paths.check(from_sha, accepted)` excludes `accepted` = the union of file lists in this frame's `gate_record`s with `event = continue` on `park_kind = protected_path`; both call sites pass it." Optionally: the pre-dispatch check runs only when the previous attempt ended without its post-exit check (interrupted).

#### H-3 — `skip_epic`'s "Valid when" forbids the case its own effects and PRD §4.6 describe (AD-13; PRD §4.6, FR-20)

Spine: AD-13 `skip_epic` row — "Valid when: as `skip_story`" i.e. "`park_kind ∉ {budget}` and `park_path` inside a story frame"; same row, effects — "the epic's `git.push` / `pr.link` … are marked skipped only when the push itself is the stop". PRD §4.6: `push_rejected` admits Skip epic; "Skip epic on a rejected push marks the push and the compare link skipped and continues with the next epic". A rejected push parks on `…epics[i].push`, which is not inside a story frame, so `signal_run` built from the table returns 409 and the PRD case is unreachable. The gates epic and the push epic will ship different answers.

**Smallest fix:** `skip_epic` Valid when: "`park_kind ∉ {budget, plan_stale}` and `park_path` inside an `…epics[i]` frame"; and add in effects: "on `push_rejected` at `…epics[i].push`: the `push` and `pr.link` rows `→ skipped`, next epic".

### Medium

#### M-1 — `budget_raise` promises an immediate re-park that no writer performs, and the walker's wake rule is unstated (AD-13, AD-11, AD-8)

Spine: AD-13 `budget_raise` — "Effects in the resumed engine step: none … the walker resumes at the row's routed status (`blocked`/`checkpoint` re-park immediately; `done` continues)"; AD-8 — "Exactly one use case, `apply_step_result`, applies every execution transition … the walker on wake only reads"; `signal_run` "clears `park_*`". Once `park_path` is cleared, how the walker picks the row to resume, and who writes the second `needs_you` (a `StepResult.park` needs an executor call, but "none" runs), is left to the walker epic; the gates epic assumes it happens.

**Smallest fix:** add to AD-8: "On wake the walker resumes at the first row in `seq` order whose status is not `done | skipped`; a row found in `blocked` or `checkpoint` is re-applied through `apply_step_result(StepResult{status: same, park: Park(kind = same)})` without invoking its executor." Change the `budget_raise` effects cell to name that re-application.

#### M-2 — `skip_story` is admitted on `sync: branch diverged`, which PRD §4.6 refuses (AD-13; PRD §4.6)

Spine: AD-13 `skip_story` — "Valid when `park_kind ∉ {budget}` and `park_path` inside a story frame". `…stories[n].sync` is inside the frame and its park is `push_rejected`; PRD §4.6 `push_rejected` admits "Retry, Skip epic, Cancel" only. Skipping the story leaves the branch diverged, so the next `sync` parks again — the PRD's exclusion is the right one.

**Smallest fix:** `skip_story` Valid when: "`park_kind ∉ {budget, plan_stale, push_rejected}` and `park_path` inside a story frame".

#### M-3 — `skip_epic` does not say what happens to the remaining frames' `sync` / `verify` / `git.commit` rows, and `skip_story` at a done checkpoint re-runs a finished verify and commit (AD-13; PRD §4.6, FR-20)

Spine: `skip_story` — "every non-terminal `agent`/`checkpoint` row of the innermost `…stories[n]` frame `→ skipped` … the frame's `verify` row runs as the re-baseline, then `git.commit`"; `skip_epic` — "same over the remaining story frames". Read literally, each remaining frame keeps a live `sync`, `verify` and `git.commit` row (one re-baseline per skipped story), while PRD FR-20 marks "their remaining Steps `skipped`". And at a done checkpoint (`…stories[n].after`) the frame's `verify` and `git.commit` are already `done`; PRD §4.6 says "marks the checkpoint skipped and continues", not "re-baseline".

**Smallest fix:** `skip_story`: "the frame's `verify` and `git.commit` rows run only when not already `done`"; `skip_epic`: "every row of the remaining frames `→ skipped`; only the current frame re-baselines and commits".

#### M-4 — No request sets `terminal_session = true` (AD-13, conventions › routes; PRD FR-21)

Spine: AD-13 has `terminal_release` ("`terminal_session = false`") and `terminal_resume`; the routes convention has only `POST /runs/{id}/signals`. PRD FR-21: "Copying the command marks the Run `terminal session in progress`". The UI epic will invent a field on `PUT /runs/{id}` or a client-side flag; `terminal_poll` (server side) will never see it.

**Smallest fix:** add a row `terminal_claim` — Valid when `needs_you and not terminal_session` on an `agent` row with a `session_id`; writes `terminal_session = true`, gate_record; effects none — and add it to the PRD Signal list in `prd-deltas.md`.

#### M-5 — The `_bmad/` version check blocks `repo-init@1`, the Run that installs `_bmad/` (AD-16, AD-7, capability map FR-8; PRD FR-30)

Spine: AD-16 — "Pre-flight requires `_bmad/` at `plan_ref` with `_bmad/_config/manifest.yaml` version equal to `BMAD_VERSION`"; AD-7 — "`create_run` accepts `initiative`, `epic`, `repo-init`"; capability map FR-8 — pre-flight checks include "harness enabled, `_bmad/` version". On a repository whose `bmad_version` is `missing`, a `create_run` that enforces the shared checks refuses the init Run.

**Smallest fix:** add to AD-16: "The `_bmad/` check and the `harness enabled` check apply only to plans that contain an `agent` row." (Also closes the harness-input question for `repo-init`.)

#### M-6 — `HARNESS_ENV_CONTRACT` is declared "exactly that list", but AD-5 and AD-11 require variables outside it (AD-10, AD-5, AD-11)

Spine: AD-10 — "`HARNESS_ENV_CONTRACT` = `{ORCH_RUN_ID, ORCH_ATTEMPT_ID, ORCH_STORY_ID, ORCH_HARNESS, ORCH_PROJECT, TRACEPARENT, LITELLM_BASE_URL, LITELLM_API_KEY, LANGFUSE_*, ORCH_LOG_CONTENT}` and `env_for(attempt)` populates exactly that list plus the Project's env vars"; AD-5 — the harness receives "content-logging switches (`OTEL_LOG_USER_PROMPTS`, …) only when `project.log_prompt_content` is true"; AD-11 — every request carries composite headers (`x-litellm-tags: run:,attempt:,…`, `langfuse_tags`) "from `env_for(attempt)` through the harness's env-name header mechanism", and Claude's mechanism is `ANTHROPIC_CUSTOM_HEADERS` "from env", plus the OTLP exporter variables native tracing needs. None of these is in the literal list. The scripts epic will ship the list; the adapter epic will need more.

**Smallest fix:** make the list normative by location, not by content: "`_common.sh` is the only declaration of `HARNESS_ENV_CONTRACT`; `env_for(attempt)` populates exactly what it declares and `scripts/harness/<name>.sh doctor` fails on any name referenced by static config that is not in it. It includes the identifiers, the gateway pair, `TRACEPARENT`, the Langfuse and OTLP exporter variables, the composite header/tag variables, and the content switches (set only when `log_prompt_content`)."

#### M-7 — A budget-cap exit must be recognised, but adapters "return nothing interpreted", and the budget rule runs after routing/retry (AD-10, AD-9, AD-11, kinds table)

Spine: AD-10 — "The Claude adapter additionally passes `--max-budget-usd` = remaining budget; a harness exit caused by that cap is applied as park `budget`, never as an expect miss" and "Adapters return `HarnessResult{session_id, exit_code, usage, log_path}` and nothing interpreted"; kinds table `agent` — "… dispatch → protected-path check → FR-16 routing → `Gateway.spend` → budget rule"; AD-9 — `retry {max, prompt}` on expect miss. A cap exit leaves the Story file `in-progress` → routing sees an expect miss → the template retry dispatches again before the budget rule runs, with a remaining budget of about zero.

**Smallest fix:** add `stop_reason ∈ {exit, budget_cap, killed}` to `HarnessResult` (read from the CLI's structured result, not from model output), and reorder the kinds-table cell: "… protected-path check → `Gateway.spend` → budget rule (park wins over retry) → FR-16 routing".

#### M-8 — Readiness-run mechanics are under-specified: "never pushed" has no mechanism, the evaluator has no trigger, and two PRD lines are absent (AD-10; PRD FR-33)

Spine: AD-10 — "`epic@1` Run on `fixtures/readiness-repo/` … branch `readiness/{harness}/{date}`, never pushed … each check is a line, the first failing one is `failing_check`". `epic@1` plans `git.push` and `pr.link` rows; nothing skips them. `use_cases/harness_readiness` is "the only writer" of the `harness` table but nothing says what invokes it when the Run reaches a terminal status. PRD FR-33 lists "a Session id was recorded" and "verify exited 0" as lines; a fixture without `quality_gate_command` would pass with verify `skipped`.

**Smallest fix:** "The fixture's origin is a local bare clone under `/work/readiness/` made at container start, so `git.push` is real and harmless (drop "never pushed"); `apply_step_result` calls `harness_readiness.evaluate(run_id)` when a Run of Project `readiness` reaches a terminal status; lines = Story file `done`, `session_id` recorded, verify row `done` (not `skipped`), trace spans/generations present, spend non-empty."

### Low

#### L-1 — `retry` on `protected_path` is admitted only through the catch-all "or row `error`" (AD-13; PRD §4.6)

PRD lists Retry for `protected_path`; AD-13's `retry` set omits it and relies on "or row `error`", which also makes the enumerated set redundant. **Fix:** add `protected_path` to the set and drop "or row `error`" (or keep it and say the set is illustrative).

#### L-2 — AD-12's reason set is mispunctuated

"`reason ∈ {repository lock held by {run}, global concurrency, held by {runs}, running, waiting for your answer}`" reads as five reasons; PRD FR-13 has "`waiting: global concurrency, held by {runs}`" as one. **Fix:** quote each reason.

#### L-3 — `plan_stale`: the ref of the stale check and the park's `park_path` are unstated (AD-7, AD-13)

"re-reads every list file at the branch head" — for an initiative whose epic branches do not all exist, say "at the same ref rule as planning (`origin/{branch}` else `origin/{base}`)"; state `park_path = null` for `plan_stale` (it is what makes `skip_*` invalid there).

#### L-4 — `Git.diff_names(from_sha)` semantics (AD-14, AD-17)

The pre-dispatch check runs before the WIP commit, so it must see uncommitted and untracked files; the post-exit check runs on a tree the agent committed. **Fix:** "`diff_names(from_sha)` = names changed between `from_sha` and the working tree, untracked included".

#### L-5 — A provisional spend on the last attempt of a Run is never replaced (AD-11; PRD FR-28)

"replaced on the next check" — there is no next check after the final attempt. **Fix:** re-check provisional attempts when the Run reaches a terminal status (or from `clone_check`'s daily job).

#### L-6 — Step diagram edges missing for `terminal_resume` from `checkpoint`/`error` rows and for `answer` on `checkpoint` (AD-8, AD-13; PRD FR-21)

FR-21 applies to any `needs_you` Run with a terminal session; the diagram has only `blocked → done: terminal_resume`. **Fix:** label `checkpoint → done` and `error → done` with `terminal_resume`, and `checkpoint → queued` with `answer / continue (agent row)`.

#### L-7 — The verify row's `error → queued` on redispatch is not in the diagram; `redispatch_count` row unstated (AD-8, AD-9)

After `done → queued: on_fail redispatch` on the build row, the verify row (in `error`) must be re-queued when the build row completes again. **Fix:** add `error → queued: predecessor re-done (redispatch)`; state that `redispatch_count` lives on the row that declares `on_fail`.

#### L-8 — "the only kind test outside `application/steps/`" is no longer true (AD-8, AD-13)

`signal_run` tests kinds for `answer` ("on an `agent` row") and `skip_story` ("`agent`/`checkpoint` rows"). **Fix:** "the kind tests outside `steps/` are those in AD-13's table".

#### L-9 — Operator `retry` after template-retry exhaustion: counter semantics (AD-9, AD-13)

Whether `retry_count` resets, and whether the re-run parks after one expect miss, is unstated. **Fix:** "an operator `retry` grants one more attempt; counters are not reset".

#### L-10 — AD-3 binds "FR-1..FR-29 (every endpoint)"; FR-30..FR-33 add endpoints

**Fix:** "FR-1..FR-33".

#### L-11 — Template-graph node id example contradicts "callee calls collapsed" (AD-15)

`stories.story.build` is inside the collapsed `story` call; the example for `epic@1`'s own graph would be `stories.story`. **Fix:** pick an id from the caller's own steps.

#### L-12 — `cancel` removes worktrees while a deterministic step may still be running in them (AD-13)

`kill_group` covers harness processes only; a `shell`/`git.*` step in flight races `Git.remove_worktree`. **Fix:** "`engine.cancel` first, then wait for the in-flight step to return (absorbed), then remove worktrees" — or accept and say so.

#### L-13 — The readiness fixture must carry `_bmad/` at `BMAD_VERSION` (AD-16, AD-10)

Pre-flight requires it at `plan_ref`; the fixture is static in the image. **Fix:** "the image build runs `bmad.install` into `fixtures/readiness-repo/`".

#### L-14 — `git.worktree` "refuse when dirty" has no park kind (AD-14; PRD FR-9)

PRD refuses at start (pre-flight); at execution the refusal needs a kind. **Fix:** pre-flight checks `Git.status` of an existing `wt/{branch}`; at execution a dirty reuse is park `misconfigured` with reason `worktree dirty: {path}`.

## Consistency of the amended items with the untouched ADs

- AD-2 / AD-9 / AD-17: `rules/protected_paths.check` and the executors stay in `application/` over ports — consistent.
- AD-3: generated contract now covers FR-30..FR-33 endpoints in practice; binds line stale (L-10).
- AD-6: `signal(run_id, Signal)` / `cancel` match AD-13's use; "list files read once per Run" coexists with AD-7's stale re-read (a read inside the first step, not a re-plan) — consistent, worth one clause.
- AD-16: repo-init flow matches the `bmad.install` kind row and the `chore/bmad-init` commit convention; the `_bmad/` check needs the exemption (M-5).
- AD-18: `signal_run` and `apply_step_result` under 100 % branch coverage — consistent with AD-8/AD-13 as the two writers.
- AD-19: trigger ("build `done` and verify `done | skipped`") matches PRD FR-32 and the skip path (verify re-baseline) — consistent.
- AD-20: `LITELLM_SPEND_KEY`, `MAX_ACTIVE_RUNS`, `CLAUDE_ALLOWED_TOOLS` present in the env table — consistent.

## Summary

Gate: ready for handoff after H-1, H-2, H-3 (three local edits in AD-10, AD-17, AD-13). Counts: critical 0 · high 3 · medium 8 · low 14.
