# Adversarial review — PRD + addendum (2026-09-02 pass)

Pass of 2026-09-02 over `prd.md` and `addendum.md` as updated to match `architecture/ARCHITECTURE-SPINE.md`. Read-only; the spine's AD-7, AD-8, AD-9, AD-13, AD-16, AD-17 and the shipped skeletons in `template-dsl-draft.md` were used where the PRD defers to them. Facts about `bmad-build-auto` were checked against the installed skill (`~/.claude/skills/bmad-build-auto`, step-01/03/04, `customize.toml`), not assumed.

Severity: **critical** = a story written from this text would be wrong or unsafe; **high** = a builder must guess; **medium**; **low**. Anything already covered by a consequence bullet is omitted.

Counts: 5 critical · 8 high · 7 medium · 4 low.

---

## Critical

### C1 — Every orchestrator write made before a dispatch leaves the tree dirty, and `bmad-build-auto` halts on a dirty tree
**Scenario.** First Story of a Run. The agent executor (spine kind table: "WIP commit → protected-path check → `project-context.md` → compose_prompt → dispatch") writes `{Spec folder}/project-context.md` *after* the WIP commit. The file is untracked when the Harness starts. `bmad-build-auto` step-01 item 3: "require a clean working tree … HALT on a dirty tree." Every first dispatch in every Spec folder halts `blocked`. The same applies to the Answer archive (`git mv` to `.answers/` — a staged rename is dirty; and `git mv` fails outright on an untracked blocked file that the WIP commit has not yet tracked) and to the `## Verify Failure` append + `status: in-progress` edit before a redispatch if it happens after the WIP commit.
**PRD.** FR-15: "The file is regenerated at every dispatch and committed by the commit-guard" (i.e. after the agent). FR-12: "Before every Story step Attempt the orchestrator commits any uncommitted changes … because the agent refuses to start on a dirty tree." FR-18: archive then re-dispatch, no commit mentioned.
**Fix.** One sentence in FR-12: "Every orchestrator write to the Worktree that precedes a dispatch (`project-context.md`, the Answer archive, the `## Verify Failure` append) is made *before* the WIP commit, so the Harness always starts on a clean tree; the WIP commit is therefore never `no changes` on those attempts." Drop "committed by the commit-guard" from FR-15.

### C2 — The initiative composition has no defined branch model; epics on their own branches never see the spec
**Scenario.** `initiative@1` (DSL §3.3) has no `branch` input; each epic runs on `{{epic.branch}}` from `epics.yaml`. `epic@1`'s `git.worktree` creates a missing branch "from `origin/{base}`". Epic 2 declares `branch: feat/saved-views`, which does not exist; it is created from `main`, which does not contain `specs/notifications/…` (that lives on the Working branch). The first dispatch halts `no stories.yaml found` → FR-16 says that is `harness misconfigured`. Wrong diagnosis, no route out. Meanwhile the PRD's own model is single-branch: UJ-2 picks "the working branch", FR-8 lists "Working branch" as a Run input, FR-9 says "creates a Worktree on the Working branch", and the Glossary says `epics.yaml` "lists the Spec folders of its epics in order" — no `branch` field anywhere in the PRD. A builder writing the `initiative` Template story has two contradictory contracts.
**PRD.** Glossary *Initiative*; FR-8 inputs; FR-9 first sentence; DSL §3.3 `branch: "{{epic.branch}}"`.
**Fix.** Pick one and write it into the Glossary as the `epics.yaml` schema. Cheapest for the MVP: `epics.yaml` entries are `{id, title, spec_folder, done_checkpoint?}` only; every epic runs on the Run's Working branch (stacked); `initiative@1` gains `branch` as an input and passes it down. If per-epic branches are kept: every epic branch is created from the *Working branch*, not `base`, pre-flight lists every branch the plan checks out, and `plan_ref` is defined per branch.

### C3 — A standalone `story` Run (and therefore the readiness run) has no checkout row and no Worktree
**Scenario.** `story@1` = sync · build · verify · commit_guard. `Workspace` is "unavailable before the first `git.worktree` row" (AD-14). FR-33 runs "the shipped `story` Template on a fixture Repository"; DSL §4 says `story` "remain[s] startable directly from New workflow". The first row (`git.sync`) has no worktree to sync. A story written for FR-33 or for "start a `story` Run" cannot be implemented as specified.
**PRD.** FR-33 first sentence; FR-8 "for `epic` or `story`: the Spec folder"; FR-9 is written as if every Run has a checkout.
**Fix.** Either the readiness run and direct starts use `epic@1` with a one-Story `stories.yaml` (and FR-8/FR-33 say so), or `story@1` gets a `git.worktree` row when run top-level. State which.

### C4 — "Test files that existed when the Attempt started" freezes the agent's own new tests on the verify redispatch
**Scenario.** Attempt 1 writes `tests/foo.test.ts` (new — allowed) and commits `done`. verify fails because that test is wrong. Redispatch → Attempt 2; `tests/foo.test.ts` now "existed when the Attempt started" → protected. The agent fixes its own test → `protected path modified` → park, never retried. The redispatch path (FR-10's one bounded self-repair) is defeated in the single most common verify failure. Same for Retry after a timeout: the interrupted attempt's WIP-committed tests become frozen for the re-attempt. Renaming a test = delete + add = hit.
**PRD.** FR-31: "every file matching the Repository's `test_globs` that existed when the Attempt started. New test files are allowed."
**Fix.** "…that existed at the Story frame's *first* Attempt start SHA (`frame_start_sha` taken before the first dispatch of that Story), for every Attempt of that Story." Note the spine's AD-17 currently defines `frame_start_sha` as the *latest* attempt's SHA — same bug; both need the same sentence.

### C5 — The key handed to every agent process is the key the orchestrator uses to read `/spend/logs/v2`
**Scenario.** `LITELLM_API_KEY` is listed once (spine env table) as used by "harness env, gateway adapter". `GET /spend/logs/v2` is an admin route on LiteLLM; a key that can read it can read every spend log (including other Projects' request metadata), and if it is the proxy master key it can generate keys, change models and read `/global/spend`. That key sits in the environment of an unattended agent with `Bash` and `curl` in a container whose egress includes the Gateway. A prompt-injected agent can also spend with no `attempt:` tag — FR-17 sums by identifiers, so untagged spend is invisible to the budget halt. Before 2026-09-02 the agent got a per-Project virtual key with a budget; the PRD does not say what replaced that limit.
**PRD.** FR-14: "A Harness process receives no credential other than the instance Gateway key". FR-26 / AD-11: spend read via `/spend/logs/v2`. Addendum §C: virtual keys dropped.
**Fix.** Two variables: `LITELLM_HARNESS_KEY` (a non-admin virtual key, chat routes only, optionally with a hard monthly `max_budget`) and `LITELLM_ADMIN_KEY` (orchestrator only, never exported). Add to NFR-3. Add to FR-17 a consequence: "spend on the harness key that carries no `attempt:` tag is shown on the instance as *unattributed spend*" — or accept and state that the budget halt is advisory against a hostile agent.

---

## High

### H1 — The plan is frozen at `plan_ref` but nothing detects the branch moving away from it
**Scenarios.** (a) Run B queues behind Run A (parked for two days, lock held). A pushes `done` Story files. B starts with the plan it made on day 0: every Story planned "dispatch"; the agent finds `done` files → a review pass per Story (FR-20's own words) — paid, pointless, and `re_review_done` was off. (b) Mid-run the operator pushes a new Story into `stories.yaml`; `git.sync` pulls it; it is never dispatched; the Run ends `done · 8/8` on a branch whose spec has nine Stories. (c) The operator removes/renames a Story id; the agent halts `story id not found in stories.yaml` → FR-16 calls that `harness misconfigured`. (d) FR-19 lets the operator edit *any* file of the Spec folder inline while parked — including `stories.yaml`, the file the plan was frozen from; setting `spec_checkpoint: true` on a later Story or changing `invoke_dev_with` has no effect and no warning. (e) Pre-flight plans at SHA X; the operator pushes; *Start run* — is the persisted plan the one shown, or a re-plan? FR-8 says "produced by the same planner", not "the same output".
**PRD.** FR-8: "a later edit of the branch or of the Repository does not change the plan." FR-10: "never re-read during the Run." FR-19: "may edit any file of the Spec folder inline."
**Fix.** (1) At Run start (dequeue) and at every `git.sync`, compare the blob hashes of every list file (`epics.yaml`, each `stories.yaml`) at HEAD with those at `plan_ref`; on difference park with reason `plan stale: {file} changed since plan` (Cancel; start a new Run) — one sentence in FR-10. (2) FR-19: exclude `stories.yaml` and `epics.yaml` from inline edit, or state that edits to them do not alter this Run. (3) FR-8: *Start run* persists the rows produced by the pre-flight shown, refusing with `branch moved since pre-flight` if `origin/{branch}` ≠ `plan_ref`.

### H2 — "After the Operator resolves it" has no in-product path for a diverged branch, a rejected push, or a fix pushed while parked
**Scenarios.** (a) `git.sync` non-ff: the Worktree holds the agent's local commits; origin has the operator's. Resolution is a rebase *in the Worktree*. The operator cannot reach the Worktree from the UI (FR-19 edits Spec-folder files only), and a manual `docker compose exec … git rebase` has no `GITHUB_TOKEN` (AD-5: token only via `GIT_ASKPASS` per orchestrator command). (b) verify failed 2/2 → operator pushes a fix to origin → Retry "re-executes only that Step" = verify, without sync; the fix is never pulled; verify fails again; Retry again is valid and does the same. (c) Operator pushes during an epic → epic push rejected → Retry re-runs the push → rejected forever. (d) Skip story on a `sync` park runs verify on the stale tree; the next Story's sync parks identically — each skip burns a Story and resolves nothing.
**PRD.** FR-10: "Retry re-runs it after the Operator resolves it." FR-11: "Retry re-runs the push after the Operator resolves it." FR-20: "re-executes only that Step."
**Fix.** State the mechanism: "Retry on a `verify`, `git.push` or `git.sync` row first runs `git.sync`; a `git.sync` row that cannot fast-forward offers the Signal `rebase` (the orchestrator runs `git rebase origin/{branch}`; on conflict it parks `sync: rebase conflict` and the only exits are Cancel or a documented terminal procedure that supplies the token)." Skip is not offered on a `sync` park.

### H3 — Skip epic skips the push, stranding committed Stories in a Worktree that is garbage-collected
**Scenario.** Initiative with epics on two branches. Epic 1: Stories 1–3 done and committed; Story 4 blocked; *Skip epic* → "including its push and compare link". Epic 2 checks out its own branch; Run ends `done`. Epic 1's three commits exist only in `wt/feat/notifications`; `worktree_gc` removes it after 7 days. Nothing on the screen says the work was never pushed; FR-11 promises the summary lists skipped epics "beside the link" — there is no link.
**PRD.** FR-20: "Skip epic does the same over the rest of the current epic, including its push and compare link." FR-9: "Worktrees of Runs in a terminal Status are removed 7 days later."
**Fix.** Skip epic skips the remaining *Stories* only; the epic's `git.push` and `pr.link` still run (the branch is already an unmerged feature branch; pushing partial work is the safe default). If not: the Run summary must print `epic {id}: n commits not pushed at {worktree}` and GC must exclude such Worktrees.

### H4 — A `protected path` park has no exit for the legitimate case and Skip re-parks on the same hit
**Scenarios.** (a) Story changes an API; an existing test asserts the old contract; the agent edits it → park. The right answer is "yes, that edit is intended". Options offered: revert (then verify fails, redispatch, agent edits it again, park — a human loop), or Skip. (b) Skip: agent rows → `skipped`; verify; commit-guard "also runs the protected-path check" against `frame_start_sha` → the same modified file is still in the diff (committed by the agent or uncommitted) → park again on the `git.commit` row; Retry (row `error`) re-hits; Skip story again has nothing left to skip. Dead end unless the operator edits the file back — possible inline only for `SPEC.md`/`stories.yaml` (Spec folder), not for `AGENTS.md` or tests.
**PRD.** FR-31: "The Operator reverts on the branch and Retries, or Skips the Story." FR-10: commit-guard "also runs the protected-path check."
**Fix.** Add a Signal `accept_protected {files}` valid on `park_kind = protected_path` (human gate, gate-record entry, the listed files are excluded from the check for the rest of this Story). Define Skip on a protected-path park as: restore the protected files to `frame_start_sha` before the re-baseline verify. Optionally a per-Story `allow_paths` list in `stories.yaml`.

### H5 — `re-baseline failed after skip` is a dead end
**Scenario.** Skip story after a half-done implementation; verify (re-baseline) fails. Run parks. Valid Signals: Retry (re-runs verify on the same tree → fails), Skip story (nothing left; re-runs verify → fails), Skip epic (skips the push; the next epic on the same branch runs its baseline on the red tree → `failed`, terminal), Cancel. The operator cannot touch source in-product. The PRD does not name the `park_kind` for this park, so Retry validity is itself a guess.
**PRD.** FR-20: "If the re-baseline exits non-zero the Run stays `needs-you` with reason `re-baseline failed after skip`."
**Fix.** Give it `park_kind = verify_failed` and add the missing exit: the Skip signal accepts `reset: true` = `git reset --hard {frame_start_sha}` before the re-baseline (addendum §G lists this as a COULD; it is the only clean exit and is one git command). State it.

### H6 — The story-id prefix rule refuses any epic with ten or more Stories
**Scenario.** ids `4-1` … `4-10`. `4-1` is a prefix of `4-10` → pre-flight refuses. The glob `4-1-*` does not match `4-10-foo.md`, so the refusal is spurious; the skill itself says "id-prefix match".
**PRD.** FR-8: "ids of which none is a prefix of another (so `{id}-*` globs are unambiguous)".
**Fix.** "no `{id}-` is a prefix of another `{id}-`".

### H7 — Budget halt on a row that routed `blocked` or `checkpoint` re-executes that row on `budget_raise`
**Scenario.** Attempt ends `blocked`; spend > budget → `park_kind = budget`, "the Step keeps the status its file routed to". Answer is invalid (`park_kind ≠ blocked`). Operator raises the budget → "the walker continues at the first row not `done | skipped`" = the `blocked` agent row → re-dispatched with no Answer. `bmad-build-auto` step-01 on an existing `blocked` file: "HALT with blocking condition `story already blocked`" — a new paid Attempt, a new Question whose text is not the original, and `story already blocked` is not in FR-16's misconfigured list. Also: Claude's `--max-budget-usd = remaining` makes the Harness exit early with a non-terminal file → FR-16 routes that to `error` → template `retry {max: 2}` resumes the session twice into the same cap before parking as `expect failed`, not `budget`.
**PRD.** FR-17: "The Step keeps the status its file routed to." FR-16 retry bullet.
**Fix.** FR-17: "On `budget_raise`, if the halted row's routed status is `blocked` or `checkpoint`, the Run re-parks immediately with that kind (no execution)." FR-16: a Harness exit caused by its own budget cap is classified `budget`, never retried.

### H8 — Retry, redispatch, timeout and budget bounds are per-Step in the text and per-Attempt in the mechanism; the worst case is unstated
**Scenario.** One Story: dispatch + 2 retries = 3 Attempts; verify fails → redispatch: another 3 Attempts. `timeout_min: 90` is enforced by the `ProcessRunner` per process, so the cap is 6 × 90 min = 9 h of Harness time for one Story before any human sees it. FR-17 checks spend "after every Story step Attempt" — but the retry loop lives inside the agent executor (same row), and the spine's kind table puts `Gateway.spend → budget rule` *after* routing, i.e. after the retries. So the budget can be exceeded after Attempt 1 and the executor still starts Attempts 2 and 3. The timeout is also expressed as a Step limit ("Every Step has a maximum wall-clock time") which a builder may implement as a per-row budget.
**PRD.** FR-10 timeout bullet; FR-17 first bullet; FR-16 retry bullet.
**Fix.** "`timeout_min` bounds each Attempt. The budget rule runs after *every* Attempt, including template retries, before the next Attempt is started. Worst case per Story is `(retry.max + 1) × (redispatch.max + 1)` Attempts." Consider `retry.max: 1` in the shipped `story@1`.

---

## Medium

### M1 — Compare links per epic on one branch are the same URL; the PR count is fiction; merging the first PR mid-run breaks the second epic
Two epics on `feat/x` → two `pr.link` rows, both `main...feat/x`; card says `2 PRs`. If the operator merges PR 1 with squash + delete branch (GitHub's default), epic 2's `git.sync` fails (remote branch gone) or the epic-2 push is rejected. FR-11: "one per epic". **Fix.** Dedupe by branch; `k PRs` = distinct pushed branches; add to FR-11: "the Working branch must not be deleted or squash-merged until the Run is terminal; a missing remote branch parks `push rejected`."

### M2 — Skip semantics at three positions are undefined
(a) Done checkpoint row (`stories[n].after`): Skip marks it `skipped`, then "the Story's verify Step then runs as the re-baseline" — verify and commit-guard are already `done`; are they re-executed (new Attempts on done rows) or not? Is the Story counted done or skipped in `m/m`? A Trajectory was already written. (b) Last Story of the last epic: after re-baseline + commit-guard, push and `pr.link` run and the Run is `done` — but with `park_kind` possibly `verify_failed` the summary must say which Stories carry `skipped by operator` commits. (c) `skip_epic` is valid only when `park_path` is "inside a story frame" (AD-13 "as `skip_story`"); on `push rejected` the park is on the epic's push row, so the operator cannot skip the epic to move on, contradicting FR-20 "skip … the current epic". **Fix.** FR-20: "Rows already `done` are never re-executed by Skip; a Story whose build and verify are done counts as done. `skip_epic` is valid on any park inside the epic frame, including its push."

### M3 — Method version skew and image upgrades against parked Runs
Pre-flight checks `_bmad/` == `BMAD_VERSION` once. A Run parked 30 days survives an image rebuild with a new `BMAD_VERSION` and resumes with new skill stubs against old `_bmad/` scripts (exactly the skew AD-16 says it prevents). `repo-init` cannot run meanwhile (lock held). AD-6 says `DBOS_APPLICATION_VERSION` is bumped "after draining active Runs" — a 30-day park makes draining impossible; nothing tells the operator to cancel parked Runs before upgrading. Also: the Repository row's `outdated/missing` reads the *default* branch, pre-flight reads the *Working* branch; when `main` is initialised but the Working branch predates it, the stated fix "run Initialise repository" does nothing — the fix is "merge `main` into the branch". **Fix.** Add to FR-12: "On resume after a container restart the Run re-checks `_bmad/` against `BMAD_VERSION` and parks `misconfigured: method version` if different." Add the operational rule to NFR-7. Fix the pre-flight message.

### M4 — The readiness run is a Run with no stated Project, Repository, board presence, or lock partition; a Harness disabled while a Run using it is parked has undefined resume behaviour
FR-33 runs on "a fixture Repository": under which Project? Does it appear on the Board and the Runs screen? It takes one of two global slots and a Repository partition. FR-33 gates only *New workflow*; a Run parked on `codex` whose version pin changed resumes on a disabled Harness — proceed, or park `harness disabled`? **Fix.** "The readiness run is a Run of `epic@1` under the built-in Project `_readiness` on `fixtures/readiness-repo/`, visible on the Runs screen, filtered from the Board. A parked Run resumes on its Harness regardless of readiness state; readiness gates starts only."

### M5 — Protected-path edge cases unspecified
(a) `AGENTS.md` created by the agent: for tests, creation is allowed; for `AGENTS.md` "every `AGENTS.md`" is silent on creation. (b) `epics.yaml` is protected only through `{initiative_folder}`; an `epic` Run has none, so the agent may edit it. (c) `Git.diff_names(start_sha)` must include uncommitted and untracked changes, or a hit that the agent left uncommitted passes the post-exit check and is committed by the commit-guard. (d) `persistent_facts` loads `{project-root}/**/project-context.md` — every Spec folder's copy, including stale ones from other epics/Runs. **Fix.** One sentence each: creation of `AGENTS.md` is a hit; `epics.yaml` is protected wherever it exists under the Spec folder's parent; the diff covers the working tree; the orchestrator removes stale `project-context.md` copies outside the current Spec folder or writes one at the repository root.

### M6 — The 30-day park has an end and the PRD does not say what happens there
AD-13: `recv` on `human:{run_id}` for 30 days. Day 31: the walker wakes with nothing. FR-12 says only that a Run parked 30 days "resumes correctly". **Fix.** "A park older than 30 days is re-armed (the Run stays `needs-you`); the age renders in amber (FR-22)." Or: it fails, and say so.

### M7 — The `bmad-build-auto` prompt grammar is a contract the PRD leans on in five places and pins nowhere
FR-14 says "and nothing else, so the skill's intent detection is not disturbed", then appends `invoke_dev_with`, "Halt after planning.", the Answer suffix, the retry message, and relies on step-03 reading an appended `## Verify Failure` section. The installed skill does accept "Halt after planning." and treats extra prompt text as planning context, and does re-enter step-03 on `in-progress` — but the exact prompt strings are recorded nowhere, unlike the Harness flags in addendum §B. **Fix.** Addendum §B gains a "skill invocation grammar" block with the five literal strings and the skill version they were checked against.

---

## Low

### L1 — `install_command` runs twice
Spine kind table: `git.worktree` "runs `install_command` when declared"; `epic@1` also has an `install` shell row; FR-9 says "recorded as its own `shell` Step". Pick one.

### L2 — Skill blocking conditions missing from FR-16's configuration list
`story already blocked`, `blocked spec supplied`, `unrecognized status in existing story file`, `no epic spec found` are skill-side configuration/orchestration failures that FR-16 will show as Questions with an Answer box. Add them to the misconfigured list.

### L3 — `status_in` and routing disagree on `ready-for-dev` without `spec_checkpoint`
`expect.status_in: [done, blocked, ready-for-dev]` (expect hit) vs FR-16 "`ready-for-dev` with `spec_checkpoint` → checkpoint; any other status → error → retry". Both end in a retry, but the reason string and counter differ. State that `ready-for-dev` without a checkpoint is an expect miss.

### L4 — The redispatch counter never resets across an Answer; the reason lies
verify fails (redispatch 1/1) → agent blocks → Answer → fresh plan → verify fails → parks at once with `verify failed 2/2` although this plan was verified once. Reset `redispatch_count` on Answer, or word the reason as `verify failed; redispatch exhausted`.

---

## §8 open questions that are actually blockers for stories

| # | Item | Status |
| --- | --- | --- |
| — | `epics.yaml` schema and the branch model of `initiative` (C2) | Not in §8; blocks the `initiative` and `epic` Template stories and FR-9. |
| — | Worktree for a top-level `story` Run / the readiness run (C3) | Not in §8; blocks FR-33 and the `story` Template story. |
| — | Operator procedure for `sync: branch diverged` and `push rejected` (H2) | Not in §8; blocks the acceptance criteria of FR-10 and FR-11 ("after the Operator resolves it" is untestable). |
| — | Readiness run's Project/Repository identity (M4) | Not in §8; blocks FR-33. |
| 1 | Claude allowlist | Not a blocker: an env variable; the story ships the base set. |
| 2 | Codex `TRACEPARENT` | Not a blocker: fallback is defined. |
| 3 | Stub resolution of the Worktree as project root | Not a blocker: fallback is defined; note the fallback copies stubs into the Worktree, which is fine only because FR-30's gitignore lines exist — `git.worktree`'s dirty-tree refusal must ignore ignored files (say so). |
| 4 | Spend + Langfuse identifiers on one call | Not a blocker: fallback is defined. |
| 5–7 | Codex / OpenCode / Mac mini | Deferred by design; not blockers. |
