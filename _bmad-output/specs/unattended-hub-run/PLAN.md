# Unattended hub Run — plan (2026-10-09)

Source: client change requests from Run `01a103e3-…` (`initiative-hub@1`, 7 epics, 18 stories,
claude / claude-sonnet-5, 2026-10-03 → 10-06): 64.8 h wall clock, 12.9 h of agent work that
counted, 44.7 h parked across 34 parks, of which **one** was a decision a human had to make.

Goal: a Run that stops only on conditions a human has to decide. Rule for this plan: a fix
lands in the shipped templates or the install configuration wherever the DSL has a knob; code
changes only where it has none, each one its own TDD story. Nothing here is built yet;
**D-n** items need the Operator.

## 0. Diagnosis — what the code does today, request by request

Read before the proposals: in four of the nine requests the client's reading of the cause is
not what the code does, and the fix follows the code.

| # | Request | What actually happens (file:line) |
| --- | --- | --- |
| 1 | protected tests (16 parks, 22.9 h) | **Already shipped on main** — `3514460` (Operator decision 2026-10-06): `repository.test_globs` is exactly what is listed, empty freezes none. The client's install predates it, and an upgraded install keeps the three stored globs until the Repository form is cleared. The four anchors stay frozen. |
| 2 | sync parks (11, 10.4 h) | `git.sync` is `fetch origin <branch>` + `merge --ff-only FETCH_HEAD` on the Run's **own** branch (`infrastructure/git/worktrees.py:148-171`); it never looks at the base branch. It diverges because the Run pushes the hub only at `push-hub`, once per epic, while the initiative branch on origin moves (operator pushes, dispatch commits). Same cause for the four `push-hub` rejections. `git.push` runs a sync only on an Operator `retry` (`steps/git_push.py:91-95`). A `git.merge` kind exists: fetch, `merge-base --is-ancestor` → `done · already merged`, else `merge --no-ff`, conflict → `merge_conflict` (admits retry, cancel). |
| 3 | stall kills (4 parks, 8.5 h + 4.8 h killed) | The runner's liveness signal is "max mtime under `cwd` **or** growth of the attempt log" every 10 s (`infrastructure/process/runner.py:129-177`). The claude adapter runs `--output-format json` (`harness/claude/adapter.py:74`), which prints nothing until exit, so **the log never grows and only file writes count**. No shipped template sets `stall_min`; the kind default 30 applies to every agent row. `timeout_min` is the wall-clock ceiling (build 90, others 30). A stall or timeout returns a park before routing — never an automatic retry (`steps/agent_tail.py:117-142`). A killed attempt records `exit_code` and SHAs but no `log_path`, no usage and no gateway spend (`agent_tail.py:105-116`, `:179-205` runs only from `tail()`). **Resume never passes `--model`** (`adapter.py:261-290`), so every retry runs on the harness's own default — the Haiku downgrade already on record. |
| 4 | "killed for a protected path" | Nothing kills an agent for a hit; both checks run after exit (`agent_tail.py:88-176`, `steps/git_commit.py`). Exit 143 is the stall detector. What the client saw: the tail runs the protected check **before** the stall/timeout park and before routing (FR-31 anchor wins), so a stalled attempt that had touched a test parks `protected_path`, and a `blocked` story file is routed only after the Operator's `continue`. Two parks for one attempt is that ordering. |
| 5 | denied Bash commands | The allow list is instance-wide `CLAUDE_ALLOWED_TOOLS` (`settings.py:81-98`, `.env.example:106`); shipped default already allows `git, uv run, pnpm, npm, npx, yarn, make, rm`. The client's install had a narrower list (their answer "changed Claude config" fixed it). Not configurable per Project or template. Pre-flight probes version, auth and gateway models only (`scripts/harness/claude.sh:145-172`); `install`/`test` rows run through `ProcessRunner`, outside the harness. |
| 6 | api_error → "unexpected status: draft" | No classification of harness/infrastructure failures exists; `is_error` / `terminal_reason` are never read. Routing reads the story file, finds `draft`, retries under the template's `retry.max`, then parks `misconfigured · unexpected status: draft` (`rules/routing.py:108-110`, `:162-176`). AD-13 already reserves the reason `gateway unreachable`. |
| 7 | sandbox / wip titles | There is no sandbox; the container is. Claude Code in `dontAsk` mode refuses paths outside its cwd, and on a `workdir` row the cwd is the submodule (`steps/agent.py:320-322`); no `--add-dir` is passed. The hub-side story file stays uncommitted until `commit-retro` by design (`initiative-hub-story.yaml` note), so a retry's WIP sweep commits it as `wip: … (interrupted)` (`steps/agent_workdir.py:93`, `:203-217`). |
| 8 | retro has no logs | `compose_prompt` drops the attempt data (`steps/agent_prompt.py:108`); logs live at `/work/logs/{run_id}/`, outside the worktree, and no runtime token names them. |
| 9 | notify | `orchestrator-watch --notify` is off by default (`deploy/kit/bin/orchestrator-watch:40`); the backend has no outbound channel at all. |

## 1. Phase 1 — templates and configuration (no orchestrator code)

Ships on the next image boot: `seed_shipped` inserts a changed shipped file as the next
version by content hash; running Runs keep their pinned version. Step **ids stay the same**
(`sync`, `push-hub`, `commit-guard`), so nothing that names a row path moves.

### T-1 — `sync` becomes a merge (R2)

`initiative-hub-story.yaml`, row `sync`: `uses: git.sync` → `uses: git.merge`,
`with: { from: "{{branch}}" }`. Semantics: fetch `origin/{{branch}}`; already contained →
`done · already merged`; otherwise a merge commit; a conflict parks `merge_conflict`, the one
case a human has to resolve. This is the client's `sync: merge` with no new DSL. Trade: when
the local branch is strictly behind, history gets a merge commit where a fast-forward would
have done — acceptable on an integration branch. The row's comment is rewritten (it currently
explains why `--ff-only` tolerates a dirty tree; T-4 makes the tree clean instead).

### T-2 — merge before push (R2)

`initiative-hub-epic.yaml`: new row `merge-hub` (`uses: git.merge`, `from: "{{branch}}"`)
immediately before `push-hub`. A push after a merge is rejected only if someone pushes inside
that window; then the existing `retry` (sync-first) is the right stop. Gap kept: `git.merge`
has no `workdir` form, so `push-code` (the submodule) keeps today's behaviour; the client had
zero rejections there.

### T-3 — declared stall and wall-clock limits on every agent row (R3)

| row | `timeout_min` today → proposed | `stall_min` today → proposed |
| --- | --- | --- |
| `spec-gate` | 30 → 45 | 30 (default) → 45 |
| `build` | 90 → 180 | 30 → 90 |
| `gen-e2e` | 30 → 60 | 30 → 60 |
| `retro` | 30 → 60 | 30 → 60 |

Read-heavy phases (review, spec-gate, retro) write no files, so until O-1 lands the stall
detector is a second wall clock; these values make it one that fires after a healthy long
review, with `timeout_min` as the hard ceiling the client asked for. The four killed
attempts (3830 s, 3244 s, 4777 s, 1803 s) all fit under build 180/90. After O-1 the
`stall_min` values can come back down in a follow-up template edit, because the signal will
then mean "no model activity". `epic.yaml` / `story.yaml` (the hidden readiness fixtures)
stay as they are. Per-initiative values are O-7 (needs code).

### T-4 — one hub-side commit per story (R7, enables T-1)

`initiative-hub-story.yaml`: new row `commit-story` after `commit-guard`:
`uses: git.commit`, no `workdir`, `message: "story {{story.id}}: {{story.title}} — spec (orchestrator)"`.
The root `git.commit` stages the spec folder and the root tree, ignores gitlinks (AD-14), runs
the frame's protected check and ends `done · no changes` when nothing moved. Effects: the story
file reaches a commit with a truthful title on the story that wrote it; a later retry's WIP
sweep no longer finds finished work to label `interrupted`; the hub tree is clean at every
`sync`, which is what makes T-1 a plain merge. `commit-retro` keeps sweeping the retro output.

### C-1 — Bash policy shipped default (R5) — **D-1**

Recommendation: `CLAUDE_ALLOWED_TOOLS_DEFAULT` allows `Bash` wholesale, with the deny list
(`mcp__*`, `Bash(git push*)`) unchanged. Rationale: the adapter's own docstring says the
container is the sandbox; every denied command is a `blocked` park an answer cannot clear
(`orchestrator-admin/references/runbooks.md:127-138`); `run_in_background` and `/tmp` are
Bash denials too. Alternative if the Operator wants a list: add `Bash(ls *) Bash(find *)
Bash(cat *) Bash(node *) Bash(python *) Bash(pytest *) Bash(mkdir *) Bash(cd *)` and keep
O-9. Same edit in `.env.example`, `deploy/.env.example`, `deploy/install.sh:611` handling.
Existing installs: a documented one-line `.env` change + `./install.sh start`.

### K-1 — watcher notifies by default (R9)

`deploy/kit/bin/orchestrator-watch`: `notify=1`, add `--no-notify`; `initiative-run` skill
and README say so. No backend change.

### Client upgrade note (R1)

With the image that carries `3514460`: open the hub Repository, clear `test_globs` (or list
only the files that must never move). Until cleared, the stored three globs still park.

## 2. Phase 2 — code changes the DSL cannot express (each its own TDD story)

| id | change | where | why it is strictly necessary |
| --- | --- | --- | --- |
| O-1 | claude adapter: `--output-format stream-json --verbose`; `result.py` already picks the last `"type":"result"` object, each stream line is one JSON object | `harness/claude/adapter.py`, `result.py`, adapter unit tests | Turns the runner's existing "log growth" signal into model-activity liveness with no runner change; also leaves a transcript for killed attempts (R3, R8) |
| O-2 | `Harness.resume` takes `model`; adapter passes `--model`; `_planned` forwards the row's model | `domain/ports/harness.py`, `claude/adapter.py:261-290`, `steps/agent.py:326-336`, fakes | Every retry today silently runs on the harness default (Haiku); the attempt row still records the declared model |
| O-3 | stall/timeout/orphan paths write `log_path` and run `record_attempt_spend` (gateway spend needs no result JSON) | `steps/agent_tail.py:105-144`, `steps/agent.py:218-232` | `GET …/log` answers `[]` and `spend_usd` under-counts for every killed attempt |
| O-4 | `--add-dir {worktree root}` on `workdir` rows | `claude/adapter.py:_argv`, dispatch call site | Claude Code refuses hub-side paths and `git -C <hub>` from a submodule cwd; story files then stay uncommitted (R7) |
| O-5 | harness failure classification: result `is_error` / `terminal_reason` with zero tokens → park `misconfigured · gateway unreachable: {message}` before routing | `steps/agent_tail.py` (new rule module `rules/harness_failure.py`) | The park today points at the story file; AD-13 already names the reason |
| O-6 | protected-path park reason carries the routed outcome beside the hits: `protected path modified: X · story blocked: {condition}` / `· stalled` | `agent_tail.py:214-241` | One park shows the whole state; ordering (anchor wins) unchanged (R4) |
| O-7 | `stall_min` / `timeout_min` accept an expression bound to a `number` input; empty → kind default; `initiative-hub` declares `stall_min`, `build_timeout_min` and passes them down | `templates/keys.py:374-382`, `rows.py:356-362`, three hub templates | The client's "flexible per initiative" timeout; depends on the planner applying declared defaults (staged-story-flow plan, O-1 there) so the form and the API agree |
| O-8 | `NOTIFY_WEBHOOK_URL` (settings + `.env.example`): POST the park payload on Run → `needs_you` and on terminal status | `settings.py` (split first, it is at 400 lines), new `infrastructure/notify/`, hook in `apply_step_result`'s transition writer | 31 of 44.7 h were overnight waits; the kit watcher only helps a terminal that is open |
| O-9 | pre-flight line "harness permissions": first token of every `install` / `test` / `quality_gate` in `epics.yaml` matched against the Bash allow patterns | `application/preflight/checks.py` | Only if D-1 keeps a list; deterministic, no model call |

## 3. Decisions for the Operator

- **D-1** Bash policy (C-1): allow-all with deny list (recommended) or a widened list + O-9.
- **D-2** Automatic retry on stall. AD-9 says timeout parks are never re-executed. Proposal:
  `retry: {…, on_stall: true}` — a stalled attempt counts as an expect miss, resumes the
  session with the retry prompt, within the same `max`. Stays inside hard rule 7 (template-
  declared, bounded). Needs an AD-9 sentence. Recommended **after** O-1, when a stall means a
  real hang.
- **D-3** Backoff on `gateway unreachable` (R6): `retry.backoff_min: [5, 15, 30]`. A durable
  sleep in the walker is a step-sequence change → `DBOS_APPLICATION_VERSION` bump. Recommend
  O-5 first (the reason), backoff as a follow-up.
- **D-4** WIP title from the previous attempt's terminal status instead of `(interrupted)`.
  The text is fixed in AD-9; T-4 removes most occurrences. Recommend: not now.
- **D-5** `{run_logs}` runtime token so `retro` can be told where the attempt logs are (R8);
  the skill change lives in `bmad-retrospective`, not here. Recommend: after O-1/O-3, which
  make the logs exist for killed attempts.
- **D-6** Lighter review for small stories ($207, 371 M tokens): this is the staged-story-flow
  plan's D-3 (size-scaled review); no separate work here.

## 4. Declined, with the reason

- **Per-story `allowed_paths`** (R1): the repository-level opt-in gives the same result with
  no new DSL, and the anchors stay frozen regardless. The "test or assertion count went down"
  heuristic is not deterministic across frameworks and would re-open AD-17's "checked
  deterministically".
- **Pre-flight running the epic's test string through the harness** (R5): a model call per
  pre-flight, paid, and it proves only that one command passes; O-9 checks the whole list
  deterministically, and D-1 (allow-all) makes the question moot.
- **Moving the protected check out of the agent tail** (R4): the tail check is what catches a
  revision laundered by the next attempt's WIP commit (`agent_tail.py:98-104`); with opt-in
  globs the tail's hits reduce to anchors. O-6 fixes the reporting instead.
- **`sync: ignore`** (R2): a Run that never reads the branch it pushes to produces exactly
  the push rejections of request 2.

## 5. Spine touches owed (Operator paste, after the matching story lands)

- O-2: AD-10 port signature — `resume(session_id, prompt, model)`.
- O-5: AD-13 — `gateway unreachable: {message}` written by the agent tail before routing.
- O-6: AD-17 — "reason lists the files **and the routed outcome**".
- O-7: DSL table — `stall_min`, `timeout_min`: "int, or an expression bound to a `number`
  input; empty → kind default".
- D-2 if taken: AD-9 — `retry` may declare `on_stall`.
- Phase 1 needs no spine change: every kind used already exists and the templates are
  exemplars.

## 6. Work order

| # | item | owner | gate |
| --- | --- | --- | --- |
| 0 | Operator validates this plan; decides D-1 (the rest can wait) | Operator | — |
| 1 | T-1 … T-4, C-1, K-1, client upgrade note in `deploy/README.md` | me | `make lint test`, `make e2e` (hub fixture), one dev-stack Run on the hub fixture to see `sync` merge, `commit-story`, `merge-hub` |
| 2 | O-1 + O-3 (one story: stream output, persist on kill) | Sonnet subagent | `make lint test`; dev-stack Run killed on purpose: log present, spend recorded |
| 3 | O-2 resume keeps the model | Sonnet subagent | `make lint test`; a retry's `modelUsage` names the declared model |
| 4 | O-4 `--add-dir`, O-5 classification, O-6 reason | Sonnet subagent, one story each | `make lint test` |
| 5 | O-8 webhook | Sonnet subagent | `make lint test`, `.env.example` contract check |
| 6 | O-7 per-initiative limits (after staged-story-flow O-1) | me | `make lint test`, template smoke |
| 7 | D-2/D-3/D-5 if ratified | — | — |

Branch `feat/unattended-hub-run` off main; one commit per green item; PR at the end of
phase 1, a second for phase 2.

## 7. Expected effect on the client's Run

Against the 34 parks: 16 protected-test parks → 0 with cleared globs (R1, shipped); 11
sync/push parks → 0 unless a true conflict (T-1, T-2); 4 stall parks → 0 under T-3's limits
and the kills' cost becomes visible (O-3); 1 misconfigured park keeps its stop but names the
network (O-5); 2 `blocked` parks stay — one was the real decision, the other was a denied
command (C-1). Remaining expected stops: declared checkpoints, real conflicts, real blocks.
