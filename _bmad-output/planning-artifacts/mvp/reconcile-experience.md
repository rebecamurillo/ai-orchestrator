---
title: Reconciliation — EXPERIENCE-v1.md against PRD (2026-09-02)
date: 2026-09-02
inputs:
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md (status final, 2026-08-26)
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/screens/*.dc.html (nine artboards + Flow)
  - ../ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md (visual system)
  - prd.md (updated 2026-09-02)
---

# Reconciliation: v1 Experience vs PRD 2026-09-02

Read-only review. Every item names the UX surface (section of `EXPERIENCE-v1.md` and the artboard) and the PRD requirement it now disagrees with or that it leaves unspecified. Severity: **high** — the screen cannot be built as specced; **medium** — buildable but with wrong data, copy or controls; **low** — copy, naming, or a detail the front-end stories can settle.

Totals: **5 high · 8 medium · 8 low** (UX surfaces: 5 high, 5 medium, 5 low; PRD statements: 3 medium, 3 low).

## 1. UX surfaces needing update

### High

#### H1 · §2.1 New workflow (`NewWorkflow.dc.html`; also *Operator workflow* step 3 and *Depth*) — FR-8, FR-30, FR-33
- **Inputs changed.** UX form: template, project, repository, base, working branch, *spec folder*, *epics file (optional)*, *stories file*, harness, model, budget, manual estimate. PRD FR-8: the folder Inputs the Template declares — **Initiative folder** for `initiative`, **Spec folder** for `epic` / `story` — no epics-file or stories-file fields (both are found inside the folders: `epics.yaml`, `stories.yaml`); new toggle ***re-review done Stories*** (`re_review_done`). The form is therefore template-dependent (folder label follows the chosen Template's Inputs). The *Depth* paragraph's "eight fields" is out of date (eleven for `initiative`).
- **Pre-flight lines changed.** UX: origin reachable, base exists, working branch exists/created, `stories.yaml` parses (count, ids prefix-free), checkpoints (warning), `SPEC.md` found, epics file found, *harness available and project key present*. PRD FR-8 adds/replaces: `epics.yaml` parses with its Spec folders in order; **every** `stories.yaml` parses; `SPEC.md` in **every** Spec folder; no branch the plan checks out is held by a Worktree of a non-terminal Run; **Harness enabled** (readiness run passed, FR-33) — "project key present" must go (there is no per-project key, AD-5/AD-11); **`_bmad/` present on the Working branch at the pinned `BMAD_VERSION`**, with the fix line `run Initialise repository` (FR-30); existing `stories/*.md` listed with their statuses; Repository Clone check not `failed`.
- **Harness list is a new control.** FR-33: per Harness `enabled` / `disabled: {check}` with the time of the last readiness run and a *re-run readiness* control on this screen. The UX has a plain `claude | codex | local` selector. The artboard's `litellm key` line under the harness must go.
- **"What will run" gains columns and rows.** FR-8: every planned row with **Path, kind, Gate strength**, loops expanded to parsed epic × Story counts, already-done Stories as `skipped · already done` unless *re-review* is on. UX specifies "step list with the loop expanded to the story count" only.
- **Start-run note.** FR-8: the response names the Run holding the lock (`queues behind {run}`); UX says "the button's note says which" — consistent in intent, copy needs the Run name.

#### H2 · §2.2 Run detail (`RunDetail.dc.html`; *Operator workflow* step 5; *State vocabulary*) — FR-10, FR-11, FR-16, FR-17, FR-19, FR-20, FR-23, FR-31
- **Steps table re-keyed.** UX `# · step · type · gate · status · time · harness · cost` (artboard header `#`). PRD FR-23: `path · kind · gate · status · time · harness · cost`, **one row per planned Step from the start** (`planned` rendered `QUE`), the words `skipped` / `unvalidated` in the gate/status cells, and **latest Attempt with a count** on rows that ran more than once. Gate values: `liveness / deterministic / human` (UX) — PRD adds `unvalidated`; the UX's `spec checkpoint` in amber in the gate column becomes a checkpoint *status* of the Story step (`CHK`), plus a separate planned `checkpoint` row for done checkpoints.
- **ERR state contradicts the PRD.** UX 2.2 `ERR` state: "banner red; the failing command and its last 40 lines; *Retry step* / *Cancel run*", and the vocabulary table defines Run `ERR` as "baseline red, infrastructure failure after retries, clone failure". PRD: every stop that can be retried (timeout, harness exit, push rejected, misconfigured, internal, verify failed 2/2, sync diverged, protected path, no/ambiguous story file) parks the Run in **`needs-you` → token `BLK`, amber banner**, with the Step row `ERR`; `failed` (`ERR`) is **terminal** — baseline non-zero only — and offers no Retry (FR-20 "failed Runs are terminal — the Operator starts a new Run"). The red-banner state therefore has no Retry, and the retry-able states are amber. The UX must split its ERR state into (a) `failed` — red banner, output, *Cancel* not applicable, "start a new Run" and (b) `needs-you · error` — amber banner, output, *Retry* / *Skip story* / *Cancel*.
- **New needs-you reasons, each with its own banner copy and body.** FR-10/16/17/31: `verify failed 2/2` (Verify Failure section of the Story file), `sync: branch diverged` (git output), `timeout {path} after {n} min`, `push rejected` (git output), `protected path modified: {file}` (+ diff names), `internal: {error}`, `harness misconfigured: {condition}` (**no Answer box**), `no story file` / `ambiguous story file` (file list), `unexpected status: {status}` / `harness exit {code}`, `budget {spent} / {budget}` (**Skip not offered**), `re-baseline failed after skip`. UX specifies only blocked, checkpoint, verify-failed and budget. The action set per reason is a table the UX does not have.
- **New actions.** FR-20 *Skip epic*; FR-17 *Raise budget* (a numeric control on the Run, resumes the Run); FR-19 *Reject with a reason* at a spec checkpoint (uses the Answer mechanism). UX offers *Resume with answer*, *Skip story*, *Cancel run*, *Continue*, *Retry step* only. The artboard shows one *Skip story* button.
- **Inline editing of Spec folder files (FR-19, SHOULD).** While `needs-you` and no terminal session is in progress, any file of the Spec folder is editable inline; each save commits `spec: operator edit (orchestrator)` and writes a gate-record line. UX Artifacts tree is a read-only tree with changed-since-last-opened chips; no editor component exists in the visual system outside the Templates YAML editor. Needs: editor placement (right column vs replacing the Question), save/commit affordance, disabled state while a terminal session is in progress, and the file kinds (Markdown, YAML).
- **Compare links replace "PR #".** FR-11: the Run records **one compare link per epic** (`{default}...{working}`) and never creates a PR; UX 2.2 `DON` state and workflow step 6 say "PR link" / `PR #`. The `DON` summary must also list skipped Stories and epics beside the links (FR-11, FR-20).
- **Meta line.** FR-23: "Initiative **or** Spec folder" in the header meta line (UX: spec folder).
- **Gate record vocabulary.** Glossary: events `blocked | checkpoint | verify_failed | budget | timeout | push_rejected | protected_path | misconfigured | internal`, Signals incl. `skip_epic | budget_raise | terminal_release | terminal_resume`, transitions `start | done | failed | cancelled`, each with time, Step path, actor, text. UX lists five event kinds.
- **Cost.** FR-28: harness-reported usage shown as *provisional* until the Gateway figure exists — a state the cost kv does not have.

#### H3 · §2.3 Run diagram (`RunDiagram.dc.html`) — FR-29, FR-7
- **Hierarchy.** UX: Root = the Run; Level 1 = the template's steps `checkout · baseline · stories · push`; `stories` fans into epic nodes **by story-id prefix**; column heads `RUN · STEPS · EPICS · STORIES`. PRD FR-29: Root = **the initiative** for an `initiative` Run; **Run → epics → Stories → their Steps**; grouping is **the plan's Path** (`epics[0].stories[3].build`), never id prefixes; `checkout`, `baseline`, `push`, and the compare link are **per epic** (inside the `epic` Template), not Run-level. The artboard's `epic 1..4` nodes derived from id prefixes and its `STEPS` column are wrong for the shipped Template.
- **Group token rule** (new): `ERR`/`BLK`/`CHK` if any child is, else `RUN` if any, else `DON` when all done or skipped, else `QUE`. UX has no group-token rule.
- **Story sub-steps.** UX shows three (`build done · verify — · commit —`); PRD: `sync · build · verify · commit-guard` plus an optional done-`checkpoint` row.
- **`template` calls as collapsed nodes** (FR-7) — unspecified in both diagrams.
- **Root and footer readout.** `n/m stories` in the root becomes `n/n epics · m/m stories · k` compare links; the footer `step 15 of 22 · story 4-1 build` must be Path-based. Node ids are Step Paths (click → Steps row by Path).
- **Orientation.** FR-29 "a Template with no Run renders identically minus tokens" and UX 2.3 "the two never differ in shape" — but UX §5 draws the Templates diagram **vertical** and 2.3 **left-to-right**. One orientation must be chosen (see M2).

#### H4 · §3 Projects (`Projects.dc.html`) — FR-2, FR-3, FR-4, FR-30, FR-32, AD-5
- **No GitHub token field, no per-project litellm key.** UX title meta "litellm key", Credentials kv "token set/scope, litellm key + budget" and the artboard's `github token` / `litellm key` lines contradict FR-2 ("No GitHub token and no Gateway key can be entered on a Project") and AD-11 (no per-Project key or budget at the Gateway). Replace with the statement FR-2 requires: credentials are instance environment variables. Keep monthly spend (FR-28, COULD) and env var count.
- **New control `log_prompt_content`** switch with its statement "enabling it sends source code to Langfuse" (FR-2).
- **Repositories table.** UX `repository · default · quality_gate_command · clone check · status`. PRD adds `test_globs`, `install_command`, a **method-version state** (`{version}` / `missing` / `outdated`, from the last Clone check) and the row action ***Initialise repository*** (FR-30, MUST) which starts a `repo-init` Run (subject to the repository lock) and shows the compare link on the row; a `failed` repository status from the daily re-check blocks new Runs (FR-4). Where the `repo-init` Run's progress and its compare link surface (row vs Board card vs Run detail) is unspecified.
- **New action *Export trajectories*** (FR-32): a JSON-lines download per Project — placement and copy unspecified.

#### H5 · §3.1 New project (`NewProject.dc.html`; *Operator workflow* step 2) — FR-2, FR-3, FR-30
- Remove the **GitHub token** field (artboard has it). Add `test_globs` (default `tests/**`, `**/*.test.*`, `**/*.spec.*` shown, additions accepted), `install_command`, and the `log_prompt_content` switch.
- **Clone check readout** gains the method-version finding (`{version}` / `missing` / `outdated`) per repository, with the *Initialise repository* pointer when missing/outdated (UJ-1 edge case); the token-failure fix line now reads "the instance's GitHub token has no access" (UJ-1).

### Medium

#### M1 · §2 Workflows board (`Main.dc.html`; *Operator workflow* steps 4 and 6) — FR-22, FR-11, FR-30
- Card progress `n/m stories` → **`n/n epics · m/m stories · k PRs`** (epic figure omitted for `story` / `epic` Runs); Done card copy `n/n stories · pushed · PR #` → `2/2 epics · 8/8 stories · 2 PRs` (see P1 on "PRs").
- Card step line is "the current or last Step **by Path**" (§4.7) — the UX line `story 3-2 · build · claude · 00h 42m` needs a rendering rule for Path (see P4).
- `cancelled` Runs appear under **Failed** with the word `cancelled` (FR-22) — the UX's `CAN` token is defined but not placed; its colour (grey) and the column follow from the hue table but should be stated.
- `repo-init` Runs (FR-30) appear on the Board; a card without Stories or epics has no defined content.
- LIST rows (`token · project · repository · branch · step · age`) need the epic/story/PR progress too.

#### M2 · §5 Templates (`Templates.dc.html`) — FR-5, FR-6, FR-7
- **DSL changed**: Steps are `uses: <kind>` + `with` or `run: <command>`; kinds `git.worktree | git.sync | shell | agent | git.commit | git.push | pr.link | checkpoint | template | bmad.install`; typed Inputs `project | repository | string | path | enum | number | item`; `for_each` with `pause_before_item_when` / `pause_after_item_when`. The editor's "step types accent" highlighting, the *Inputs bound at start* table and the diagram's node eyebrows (kind) must follow the DSL.
- **Four shipped Templates composed by call** (`initiative` → `epic` → `story`, plus `repo-init`): the versions list must show pin counts **and which Versions call each** (Callee Versions, FR-6); a `template` call renders as a **collapsed node** (FR-7).
- **Validation** returns template, version, line and reason per error (FR-5); invalid YAML leaves the last valid diagram with a stated error (FR-7). UX bar has validation timestamp only.
- Nodes without a Gate strength carry the word `unvalidated` (FR-5, NFR-2) — unspecified.
- **Orientation**: pick one for FR-7 and FR-29 (H3).

#### M3 · *State vocabulary* table — Glossary "Status", FR-9, FR-10, FR-16, FR-20
- Step status gains **`planned`** (rendered `QUE`) — "not yet started" should distinguish planned from queued.
- Run `BLK` covers every `needs-you` stop except Checkpoint: blocked, verify failed 2/2, budget, timeout, push rejected, protected path, misconfigured, internal, sync diverged, no/ambiguous story file. Run `ERR` is **`failed` only** (baseline non-zero); "infrastructure failure after retries" and "clone failure" are no longer Run statuses (clone failure blocks new Runs on the Repository, FR-4).
- `SKP` reasons are words: `skipped · already done`, `skipped · skipped by operator`, `skipped — no quality_gate_command`, `install_command` absent (FR-9, FR-10, FR-20).
- `CHK` applies to a Story step (spec checkpoint) **and** to a planned `checkpoint` row (done checkpoint).

#### M4 · *Operator workflow* (`Flow.dc.html`) — FR-2, FR-8, FR-11, FR-20
Steps 2 (GitHub token, no `test_globs`, no Initialise), 3 (spec folder / epics file / stories file; "project key present"), 5 (ERR with *Retry step*; no Skip epic / Raise budget / Reject) and 6 (`PR #`) restate the outdated surfaces above; the artboard's copy (`spec folder`, `stories file`) is stale.

#### M5 · §4 Runs (`Runs.dc.html`) — FR-25
- Queue reasons are a fixed set: `repository lock held by {run}`, `global concurrency`, `running`, `waiting for your answer` (UX: "waiting for your answer · not queued until then" — keep the second clause as hint, not reason).
- History rows are **Attempts**; the `step` cell is a Path; `type` is now `kind`; Harness, Session id and tokens are empty on non-agent rows. Pagination is SHOULD.

### Low

#### L1 · *Shell* and *Information architecture* — FR-24, FR-30
- A failed fetch renders a **full-surface readout with the failed request and a retry control** (FR-24) — unspecified in UX.
- No new route is needed; `repo-init` Runs reuse Run detail (M1).

#### L2 · §1 Login (`Login.dc.html`) — FR-1 (COULD)
The lockout state (`after 5 failures within 15 minutes the endpoint refuses for 15 minutes`) has no copy; `token rejected — n attempts left` matches.

#### L3 · §2.2 terminal resume (`RunDetail.dc.html`) — FR-21
- Command execs into **`backend-api`** (`docker compose exec backend-api …`); the artboard reads `docker compose exec -w /work/… orchestrator claude`.
- `local` shows no command; lifetime shown for `claude` only, omitted for `codex`.
- New machine behaviour: while a terminal session is in progress the server polls the Worktree and **auto-resumes at verify** when the Story file is `done` and the tree is clean — the "terminal session in progress" state needs a line saying so (`terminal_resume` in the gate record).

#### L4 · *Voice* — NFR-8
New strings to add to the additions list: `spec: operator edit (orchestrator)`, `skipped · already done`, `waiting: repository lock held by {run}`, `verify failed 2/2`, `protected path modified: {file}`, `run Initialise repository`, `enabled` / `disabled: {check}`, `provisional` (cost), `re-baseline failed after skip`.

#### L5 · *Test-ids*
New prefixes needed for the harness readiness list, the inline editor, *Initialise repository*, *Export trajectories*, *Skip epic*, *Raise budget*.

## 2. PRD statements contradicting UX rules

### Medium

#### P1 · FR-11, FR-22, UJ-3 — `k PRs` — contradicts *Voice* (facts, identifiers) and NFR-8
The orchestrator never creates a pull request (FR-11 `[NON-GOAL]`, §5); it records **compare links**. A card that says `2 PRs` states something that does not exist. Copy should be `2 compare links` / `2 pushed`, and the Done summary should link the compare URLs.

#### P2 · NFR-6 — "a screen with nothing needing the Operator has no amber or red pixel" — stricter than the UX honours
The PRD restates the UX attention rule, and two UX statements now violate it: §5 Templates "human gates **amber-bordered**" (decorative amber on a screen with no stop) and §2.2 "`spec checkpoint` in amber" in the gate column of a **future** row. Both must yield to NFR-6: a declared human gate is the word `human` in the gate column and a hairline in `{colors.line-strong}` on the node; amber appears only when the Run is parked there. (DESIGN.md: "no coloured stripes wider than a 2px rule" — a border is not a signal.)

#### P4 · §4.7, FR-22 — "current or last Step (by Path)" on the card — contradicts the card's fixed single-line order
A raw Path (`epics[0].stories[3].build`) on a card or in the diagram footer would be truncated (DESIGN: row cells ellipsis) and is not what UJ-2 itself shows (`epic 1 · story 1-1 · build · claude`). The PRD needs a **display rule**: raw Path in the Steps table, gate record and history (detail contexts never truncate); human form (`epic n · story id · kind`) on cards, the LIST row and the diagram footer. The UX then owns the human form.

### Low

#### P3 · NFR-6 "exactly one element carries a signal colour" vs FR-22 "a wait longer than 48 h renders its age in amber"
A `BLK` card older than 48 h carries an amber token **and** an amber age. UX *Deltas* 10 already tolerates this ("the token (and an aged age) is the only signal on a card"); NFR-6 should say so, or the aged age should be reserved for `QUE` / `CHK` cards.

#### P5 · FR-2 — "the Project screen states that enabling it sends source code to Langfuse"
A configuration statement, not a stop. It must be plain secondary text, not the "one warning line in a readout" (amber) the UX allows only for a check result; otherwise a Project with the switch on shows amber with nothing needing the Operator (NFR-6).

#### P7 · FR-29 group token rule — "`DON` when all are done or skipped"
An epic whose every Story was skipped reads `DON` (grey), which hides the skip the counter-metric SM-C3 wants visible and strains NFR-2 (skipped is always a word). Suggest `SKP` when every child is skipped, `DON` otherwise; the Story node keeps `skipped` as a word in either case.

## 3. Consistent

These UX statements still hold against the 2026-09-02 PRD and need no change:
- Attention model and hue table (green `RUN`, amber `BLK`/`CHK`, red `ERR`, greys for `QUE DON SKP`) — NFR-6; status always a word token (glossary tokens `QUE RUN BLK CHK ERR DON SKP CAN`), no traffic lights (FR-29 "never as a second coloured mark"), `skipped` / `unvalidated` never green (NFR-2, FR-16, FR-23).
- Information architecture: the same nine surfaces and routes; no Notifications surface; "Needs you" as column + rail count; the only modal is Cancel confirm (FR-20 "requires a confirmation"); Board → Run detail is the maximum depth; the Run detail is the only place decisions are made (§4.7).
- Shell: rail `n need you` in amber only when n > 0; footer running/queued counts and last update (FR-22); polling 5 s / 30 s with state-swap updates and no animation (FR-24).
- Board: five always-rendered columns `Queued · Running · Needs you · Done · Failed`, `—` for empty, count 0; `NOTHING RUNNING` / `NOTHING REGISTERED` states; cards not draggable, whole card opens the Run; queued card `waiting: repository lock held by …`; LIST toggle (COULD) (FR-22, FR-13).
- Login: centred panel, `token rejected — n attempts left`, 30-day cookie (FR-1).
- Run detail: header meta line never truncated or collapsed (FR-23, DESIGN detail header); alert banner only when `needs-you` or `failed`; Question = the whole `## Auto Run Result` section with agent/model/time attribution; Answer hint stating the archive-to-`stories/.answers/{id}-attempt-{n}.md` and re-plan mechanism, with the "edit `SPEC.md` on the branch" note (FR-18); Run leaves `needs-you` within one poll; spec checkpoint shows the planned Story file inline with *Continue* (FR-19); Stories strip; cost block `spent / budget`, tokens in/out, wall-clock, active Operator time with the 5-minute idle rule, Trace link (FR-23, FR-27); artifacts tree with changed-since-last-opened marks (COULD); whole detail is one server read.
- Terminal resume: copyable command, `COPIED` ~1.2 s, never soft-wraps, "terminal session in progress" disables Answer / Continue / Skip / Retry until *Release* (FR-21).
- Run diagram: reached by `DIAGRAM · DETAIL` toggle with `view=diagram` in the query string; read-only; token per node, current node `now` promoted, scheduled nodes `QUE`; clicking a node scrolls the detail to the Step row; same poll as the detail; same builder as the Template diagram (FR-29, FR-7).
- Projects: context text with the "injected into every prompt" hint (FR-15); repository without `quality_gate_command` shows `— none declared` / `verify step will be skipped` at configuration time (FR-3); env vars masked after save (FR-2); Runs on this project.
- New project: Clone check live on save (`ls-remote`, shallow clone with size/seconds, default branch), verbatim git output in an inset block with a one-line fix, one failure blocks save and the form keeps every value (FR-4).
- Runs: queue on top read from the engine, `pos · project · workflow · next step · waiting because · waiting`, section head `concurrency 2 · one active run per repository`, a `needs-you` Run at position `—` (FR-13, FR-25); history newest first, rows link to the Run detail.
- Templates: YAML editor with line numbers, read-only marker and pin count on pinned versions, *Validate*, *Save as vN+1* never mutating a pinned version (FR-6); diagram computed by the backend and never dragged or edited (FR-7); escalation edges not drawn.
- Pre-flight readout uses the words `ok / ! / x / —`, warnings never block, a failing line disables *Start run* and states the fix (FR-8).
- Voice: facts and identifiers, mechanism named on every file/branch change (NFR-8); "verify step will be skipped" at configuration and "skipped — no `quality_gate_command`" at run time (FR-3, FR-9).
- Dense tables as a separate component with the token as the only signal-coloured cell (Deltas 9) — matches NFR-6 "on any card or row exactly one element".
