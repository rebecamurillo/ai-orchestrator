---
title: Rubric review — ARCHITECTURE-SPINE.md (ai-orchestrator-mvp)
reviewer: rubric walker
reviewed: 2026-09-02
subject: ../ARCHITECTURE-SPINE.md (status draft, updated 2026-09-02)
driving-spec: ../../prd.md
verdict: not ready for handoff — one critical and seven high findings, all local edits; the skeleton (paradigm, layers, ports, status ownership, contract generation) is sound and no dimension except backups is wholly silent
---

# Rubric review

Judged only against the eight-point good-spine checklist. Findings are tiered; each names the AD or section and a concrete fix. Versions are not re-verified here.

## Method — divergence scenarios used for item 1

Seven "two epics built independently by coding agents" scenarios were constructed. Five are settled by the spine; the rest produced findings.

| # | Epic A | Epic B | Divergence point | Settled? |
| --- | --- | --- | --- | --- |
| S1 | Human gates (FR-18..20) | Story loop / agent step (FR-10, FR-16) | Who moves the blocked Story file to `stories/.answers/`, who runs commit-guard + re-baseline on Skip, who archives ambiguous files on Retry — request path (`signal_run`) or the resumed engine step | **No** — only `cancel` is placed (AD-13) → C-1 |
| S2 | Planner (AD-7) | Walker (AD-8/9) | Execution order of `step_run` rows keyed by `path` string | **No** — lexicographic order misorders `stories[10]` before `stories[3]` → H-1 |
| S3 | Pre-flight (FR-8) | Agent step (FR-16) | Listing `stories/{id}-*.md` at `plan_ref` on the remote branch | **No** — `Git` port has `read_file(ref, path)` but no way to list or glob a ref → H-2 |
| S4 | Template validator (AD-15) | Step kinds (AD-9) | The set of legal template keys ("rejects unknown keys") | **No** — key set is never enumerated; `expect`, `retry`, `gate`, `pause_*_when`, `escalate_when`, `inputs` types appear piecemeal → H-3 |
| S5 | Budget/cost (FR-17, FR-28) | Harness adapters (AD-10/11) | Source of `attempt.cost_usd` (per Step cost) | **No** — `Gateway.spend(run_id)` is per Run; no `attempt:` tag and no delta rule → H-4 |
| S6 | Board / Run detail (FR-22..24) | Runs API (FR-8, FR-25) | Whether the backend ships screen-shaped read models or the UI composes them; where "active Operator time" lives | Partly — AD-3 settles the mechanism, not ownership → M-2, M-3 |
| S7 | Templates epic (ships YAML) | Runs epic (FR-9..FR-11 "dev-loop") | PRD's one template `dev-loop` + `epics.md` vs spine's `initiative/epic/story` + `epics.yaml` | Not in the spine itself (delegated to prd-deltas) → H-6 |
| S8 | Contract / UI types | any API epic | TS twins drifting from Pydantic | Yes — AD-3 |
| S9 | Template diagram (FR-7) | Run diagram (FR-29) | Two renderers | Yes — AD-15 (backend graph + one dagre renderer) |
| S10 | Projects (FR-2) | Harness dispatch (FR-14) | What env a harness process receives | Yes — AD-5 |
| S11 | Queue (FR-13) | Runs screen (FR-25) | Lock table vs engine queue | Yes — AD-12 |
| S12 | Any router | Walker | Who writes status | Yes — AD-8 |

## Critical

### C-1 — Signal side effects are placed only for `cancel`; every other operator action is unowned (AD-13, AD-8, AD-9; FR-16, FR-18, FR-20)

AD-13 says `signal_run` "validates, appends the `gate_record`, applies the transition and then calls `engine.signal`" and places `cancel`'s side effects in the request path. Nothing places: (a) FR-18's move of the Story file to `.answers/{id}-attempt-{n}.md` with `## Human Answer`; (b) FR-20 Skip's commit-guard (`story {id}: skipped by operator`) and re-baseline (and its `re-baseline failed after skip` park); (c) FR-16's archive of all-but-newest files on Retry after `ambiguous story file`; (d) FR-19 Continue at a spec checkpoint re-dispatching the *same* row. AD-6 says every side effect lives inside an engine step, which forbids doing these in the request path — but AD-13 does exactly that for `cancel`, so a builder cannot infer the rule. The gates epic and the loop epic will each choose differently (or both do it).

**Fix:** add to AD-13 a per-signal table: `Signal.kind → {request-path effects, effects performed by the resumed engine step, resulting row transition}`. Recommended: request path = validate + `gate_record` + transition + `engine.signal` only (plus `cancel`'s kill/cleanup, stated as the sole exception because the workflow is being torn down); the resumed walker reads the latest `gate_record` for the row and performs archive / commit-guard / re-baseline / re-dispatch inside engine steps. State that the `PUT /runs/{id}/files` inline edit is the one non-engine write to the worktree and is allowed only while `needs_you` and `terminal_session` is false.

## High

### H-1 — `path` order is undefined for numeric indices (AD-7)

"The walker executes only existing rows in `path` order" — `path` is a string (`epics[0].epic.stories[3].story.build`); string order puts `stories[10]` before `stories[3]`. Planner and walker epics will diverge, or the loop will run out of order past nine stories.

**Fix:** add `step_run.seq` (integer, dense, assigned by `plan_run`, unique per Run) to the entity-field list; "walker executes rows in `seq` order; `path` is the human key only". Add `seq` to the Seed's invariant-carrying fields.

### H-2 — The `Git` port cannot list files at a ref, but AD-7 and FR-8 require it (AD-14, AD-7)

AD-7 marks a Story `skipped · already done` when its file is `done` at `plan_ref`; FR-8 lists existing `stories/*.md` with statuses; both happen before a worktree exists. The `Git` port offers `read_file(ref, path)` only — the file name is `{id}-*.md`, so a glob is needed. Pre-flight and step epics will each invent a workaround (shallow clone + glob, `git ls-tree` inline, or reading through `Workspace` on a not-yet-existing worktree).

**Fix:** add `Git.list_files(ref, prefix) -> [path]` (backed by `git ls-tree -r --name-only`) to AD-14 and state that `plan_run` resolves `{id}-*.md` through it; note that `Workspace` is unavailable before `git.worktree` sets `run.worktree_path`.

### H-3 — The template key set is nowhere enumerated, yet AD-15 rejects "unknown keys" (AD-15, AD-9, Conventions › Template variables)

Keys appear scattered: `uses`, `with`, `run`, `on_fail`, `timeout_min`, `gate`, `retry {max, prompt}`, an implied `expect` ("expect miss"), `for_each`, `inputs` (types `project | repository | string | path | enum | number | item`), `version`, `pause_before_item_when`, `pause_after_item_when`, `escalate_when`, `parallel` (rejected), `id`. `expect` is referenced only through "expect miss" and never defined. The validator epic and the steps epic will disagree on the legal set; the graph builder on a third.

**Fix:** either add a one-table "Template DSL v1 keys" block under AD-15 (key, level: template/step/for_each, type, required) and define `expect`, or make `../template-dsl-draft.md` a normative companion and name it as the single key authority in AD-15's Rule.

### H-4 — Per-attempt cost has no defined source (AD-11; FR-28 MUST, FR-17)

`Gateway.spend(run_id) -> Decimal` sums by the `run:` tag; the Seed lists `attempt.cost_usd` and AD-11 says "cost per path is a SQL sum of `attempt.cost_usd`". `x-litellm-tags` carries `run:, story:, harness:, project:` — no `attempt:` — and the headers are called "static" although `story:` changes per attempt. Two attempts of one story cannot be separated; the cost epic and the harness epic will pick different answers (delta of run spend vs a new tag).

**Fix:** add `attempt:{attempt_id}` to `x-litellm-tags`/`langfuse_tags` (set per attempt by `env_for(attempt)`, not statically), extend the port to `Gateway.spend(run_id) -> RunSpend{total, by_attempt}` or add `spend_for_attempt(attempt_id)`, and state `attempt.cost_usd` is written from it before verify. Replace "set statically by the adapter" with "set per attempt by `env_for`".

### H-5 — No rule for an unexpected exception inside an engine step (AD-6, AD-8)

The Run state diagram has `running → failed: baseline fail / on_fail fail` and `running → needs_you: park(reason)`. A bug or an adapter exception (git binary missing, DB timeout, harness binary crash) is neither. DBOS will mark the workflow `ERROR` or retry per its own step policy; the Run row stays `running`; the board shows a green card forever. The walker epic and the UI epic will diverge on what the Operator sees.

**Fix:** add to AD-8: "Any exception escaping a step executor is caught by the walker inside the same engine step: row → `error` (reason `internal: {exception class}`), Run → `needs_you` with `park_kind = misconfigured`, `gate_record.event = blocked`; Retry is offered; DBOS step retries are disabled (`retries_allowed=False`) so the engine never re-executes a side-effecting step on its own." Add `internal` to the `Park.kind` enum or map it to `misconfigured` explicitly.

### H-6 — The spine never names which shipped template is the PRD's `dev-loop`, nor reconciles `epics.md` with `epics.yaml` (Seed › templates, AD-17, Capability map FR-9..FR-11)

PRD §4.3/§4.4 says the MVP ships one template `dev-loop` with `checkout → baseline → for each Story {build → verify → commit-guard} → push`, spec folder holds optional `epics.md`. The spine ships `repo-init, story, epic, initiative` and protects `{initiative_folder}/epics.yaml`; row paths are `epics[0].epic.stories[3].story.build`. The Templates epic (authoring YAML) and the Runs epic (implementing FR-9..FR-11 against "dev-loop") can each be built to the PRD as written. The spine's binds say it governs FR-9..FR-11, so the mapping has to be in the spine, not only in prd-deltas.

**Fix:** one line in the Seed or AD-7: "PRD `dev-loop` = `initiative@1` → `epic@1` → `story@1`; the Run input `epics file` is `{initiative_folder}/epics.yaml` (list file of the outer `for_each`); `epics.md` is not read." Rename or alias consistently in AD-17 and the capability map.

### H-7 — Signal and gate-record vocabularies disagree across ADs (AD-8, AD-13)

AD-8 Run diagram: signals `answer/continue/retry/skip/skip_epic/budget_raise`; AD-13: `Signal.kind ∈ {answer, continue, skip_story, skip_epic, retry, cancel, budget_raise, terminal_release}`; `gate_record.event` uses `skip` and `skip_epic`. A tool checking the enum cannot tell which is canonical; the gates epic and the API epic will ship different enums and AD-3's generated types will freeze whichever lands first. Also the Step diagram lacks the transition that resolves a `checkpoint`-kind row after Continue (`checkpoint → done`, gate `human`) — it only shows `checkpoint → queued`, which is right for a `build` row at a spec checkpoint but wrong for a `…stories[n].before/after` row, so walker and UI can disagree on whether a continued pause row reads `QUE` or `DON`.

**Fix:** pick one name (`skip` or `skip_story`) and use it in AD-8 text, both diagrams, AD-13, and the routes convention; add `checkpoint → done: continue (row kind checkpoint)` to the Step diagram and state that `continue` on a `build` row at a spec checkpoint is a new attempt on the same row.

## Medium

### M-1 — Backups and data retention are silent (Operations dimension)

No statement on Postgres backup (app + `dbos` schema together, or restore is inconsistent), the `work` volume, `agent-home` (sessions), or harness log retention under `/work/logs/{run_id}/`. Worktree GC is 7 days; logs and DB have no policy. A single-operator MVP may legitimately decide "none", but it must be written.

**Fix:** add under Deferred or a new `Operations` convention row: "Backups: `pg_dump` of both schemas nightly to `host/backups/` via a host cron (or: none for the MVP, stated); harness logs deleted with the worktree by `worktree_gc`; `agent-home` is not backed up (PRD §5: sessions may be lost)."

### M-2 — Read-model ownership for screens is not decided (AD-3, Conventions › Routes; FR-22, FR-23, FR-25)

The Board needs per-card `current or last step`, `n/n stories`, `park_kind`, age, `waiting: lock held by {run}`; the rail needs `n need you`. AD-3 fixes the mechanism (Pydantic → generated TS) but not whether backend-api exposes screen-shaped read models or the UI joins `/runs` + `/steps` + `/queue` and derives them. The "UI renders the stored token, never derives one" convention implies backend-owned, but only for status.

**Fix:** convention row "Read models: every screen reads one backend endpoint shaped for it (`GET /runs?view=board`, `GET /runs/{id}` includes steps, stories strip, cost block, gate record); the UI performs no joins or aggregation across endpoints."

### M-3 — Active Operator time (FR-23) and changed-since-last-opened marks have no home

Neither the entity-field list nor Deferred mentions `run.active_seconds` / `run.last_opened_at`. The UI epic will keep them in `localStorage`; the API epic may add columns; SM-2 depends on the figure.

**Fix:** decide: `PUT /runs/{id}/activity {focused_seconds}` batched every 60 s into `run.active_seconds` and `run.last_opened_at` (backend-owned, survives browsers), or explicitly defer both with "client-side only, not a metric source" and drop SM-2's dependency.

### M-4 — AD-1's eslint rule and the proxy route contradict each other (AD-1)

"No `fetch` outside `src/api/`" — but the proxy at `src/pages/api/[...path].ts` and Actions must call backend-api. Either they import a helper from `src/api/` (then say so) or they are exempt (then the lint rule must list the exemption). As written, a compliant proxy is impossible.

**Fix:** "`src/api/client.ts` (browser-safe, relative base `/api/`) and `src/api/server.ts` (server-only, reads `astro:env/server`, sets the bearer) are the only modules that call `fetch`; the proxy route and Actions import `server.ts`."

### M-5 — Form and Action error handling in web-client is undecided (Conventions › Errors, Front-end data; FR-4 "form retains every value")

RFC 9457 is fixed for the backend; the polling readout is fixed for reads. Nothing says how a 422 from `POST /projects` (clone-check failure with verbatim git output) or a 409 signal conflict reaches an Astro Action form and how field values are retained.

**Fix:** convention row "Form errors: Actions return `ActionError` carrying the problem+json body; the page re-renders with every submitted value and prints `detail` verbatim plus `errors[]` beside the field named by `path`; no toast, no redirect on error."

### M-6 — AD-9 mixes the invariant with the `agent` kind's behaviour spec (seed vs invariant)

The invariant is: one module per kind behind `StepExecutor`; the registry is the only enumeration; automatic re-execution exists only as two bounded, recorded mechanisms. The rest (kind list, timeout defaults, "writes `project-context.md`", "WIP-commits", "suffix 'Halt after planning.'") is PRD behaviour the `steps/agent.py` code will own and a reviewer will read off it.

**Fix:** keep the three invariant sentences in the Rule; move the `agent`-kind walkthrough and timeout defaults to the Seed under a "Shipped kinds" table (kind, gate, default timeout, one-line behaviour). Same for AD-14's scheduled-job names and AD-16's fallback (which belongs in Open at handoff 4, where it already is).

### M-7 — Two conventions are really invariants a builder cannot read off compliant code

"Transactions: one repository unit-of-work per use case call; the DBOS adapter opens the SQLAlchemy session via `SQLAlchemyDatasource`" is the atomicity/replay rule that makes AD-6 and AD-8 hold; "Time & timeouts: `timeout_min` enforced by the `ProcessRunner`, never by the engine" decides who kills a process. Neither is visible in a single module.

**Fix:** fold the transaction sentence into AD-8's Rule (as the mechanism by which "status changes only through repositories in a use case" is atomic with the engine step) and the timeout sentence into AD-14's Rule.

### M-8 — Unpinned entries in the Stack table (item 4)

`pydantic-settings 2.x`, `pytest-cov latest`, `Node.js 24 LTS` (no minor/patch), `import-linter 2.14` (two-segment). The rubric asks for pinned versions; the freshness reviewer will verify values.

**Fix:** pin each to an exact release.

## Low

### L-1 — Rationale inside Rules (item 8)

- AD-16: "BMAD has no global install mode: every skill runs `{project-root}/_bmad/scripts/render_skill.py`, which needs `_bmad/` in the repository it works on. Therefore …" — keep the decision, move the why to the memlog.
- AD-4: "(a signing key rather than a second credential)".
- AD-10: "(maker ≠ checker)".
- Deferred bullets "revisit when a second operator or a hard per-project cap is needed", "deferred until one container saturates" — acceptable as deferral triggers, but trim.
- Conventions › Terminal resume: "(PRD FR-21 says `orchestrator`; the service is `backend-api`)" and Status tokens "(`planned` is added to the PRD glossary)" are PRD deltas — belong in `prd-deltas.md` only.

### L-2 — `[ADOPTED]` marker on AD-1, AD-4, AD-5, AD-12, AD-14 only

The remaining fifteen ADs carry no status. If the marker means "carried over from architecture-v1", say so once in the frontmatter or drop it; a builder reads unmarked ADs as weaker.

### L-3 — AD-1 says backend-api exposes `/api/v1/*` only, but AD-18 uses `/openapi.json`

State the two non-versioned paths (`/openapi.json`, `/api/v1/health` or `/healthz`) explicitly in AD-1 or the Routes convention.

### L-4 — AD-3's check flag

"`openapi-typescript --check`" — express the gate as an outcome a tool can verify regardless of CLI surface: "CI regenerates `schema.d.ts` and fails on `git diff --exit-code`".

### L-5 — Harness log retention and `/work/logs` are not on a volume in the compose diagram

`/work/logs/{run_id}/…` lives under `WORK_DIR` (volume `work`) by path, but the Seed's compose diagram lists only `work` and `agent-home`; say logs are under `work` and are removed by `worktree_gc` (ties to M-1).

### L-6 — Deployment environments

Only the Mac mini deployment is described. A one-line statement that "local development = the same compose file with `.env` pointing LiteLLM/Langfuse at `localhost`; there is no second environment" closes the environments sub-dimension.

### L-7 — `PUT /runs/{id}/files` vs terminal session

AD-13 disables "other signals" during a terminal session; the file write endpoint is not a signal. State whether it is also disabled (recommended, to avoid writing under a live agent).

### L-8 — Entity fields present in the PRD but absent from the Seed's field list

`project.context_text`, `project.context_file_paths`, `repository.package_manager`, `run.manual_estimate_h` is listed but `run.model`, `run.harness`, `run.spec_folder`, `run.stories_file`, `run.epics_file`, `run.base_branch` are not. They carry no invariant, so omission is defensible; a one-line "other fields are seed and follow the PRD glossary" removes the doubt.

## Checklist scorecard

| Item | Result |
| --- | --- |
| 1 Divergence points fixed | Fails on S1–S5, S7 (C-1, H-1..H-4, H-6); passes S8–S12 |
| 2 Rules enforceable and preventive | Mostly yes; AD-13 (C-1), AD-7 (H-1), AD-8 (H-5, H-7), AD-1 (M-4) need tightening |
| 3 Deferred cannot cause MVP divergence | Passes; but two undecided items are missing from Deferred (M-1, M-3) |
| 4 Versions pinned | Four entries unpinned (M-8) |
| 5 FR/NFR coverage | All 37 governed or deferred; FR-16/18/20 placement (C-1), FR-28 source (H-4), FR-23 active time (M-3) under-specified |
| 6 Dimensions | Backups silent (M-1); error handling half-decided (H-5, M-5); environments thin (L-6); all others decided |
| 7 Seed vs invariant | AD-9, AD-14, AD-16 carry seed (M-6); two conventions are invariants (M-7) |
| 8 Terseness | Rationale in five places, PRD deltas in conventions (L-1); no template placeholders found |
