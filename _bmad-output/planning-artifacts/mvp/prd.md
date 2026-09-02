---
title: AI Orchestrator MVP — dev loop
status: final
created: 2026-08-26
updated: 2026-09-02
supersedes-for-mvp: ../prds/prd-ai-orchestrator-2026-08-24/prd.md (the long-term product PRD; not replaced)
inputs:
  - ../v1-dev-loop-2026-08-26/challenge-v1.md
  - architecture/ARCHITECTURE-SPINE.md (2026-09-02; supersedes ../v1-dev-loop-2026-08-26/architecture-v1.md)
  - template-dsl-draft.md
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/screens/ (nine artboards)
  - ../ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md (visual system, unchanged)
---

# PRD: AI Orchestrator MVP — dev loop

## 0. Document purpose

This PRD is the build contract for the **MVP** of `ai-orchestrator`: the version to be built in one build week (plan: `addendum.md` §F) and used from day 8. It is written for the operator who will also build it and for `bmad-create-epics-and-stories`. It builds on three inputs it does not restate: the v1 challenge (why this scope), the architecture spine (how — the binding invariants `AD-1..AD-20` and the stack live there and in `addendum.md`), and the v1 experience spec with its nine screens (what it looks like). Updated 2026-09-02 to match the spine; the spine's `AD` ids are cited where a requirement is bound by one. Vocabulary is anchored in §3; features are grouped in §4 with globally numbered FRs; inferences are tagged `[ASSUMPTION]` inline and indexed in §9.

The long-term product PRD of 2026-08-24 remains the description of where this goes (intake, executable specs, gates). This document narrows to what ships first and is deliberately silent on the rest.

## 1. Vision

A senior engineer writes the spec — `SPEC.md`, `stories.yaml` per epic, an `epics.yaml` listing them — on a working branch, points the orchestrator at it, and walks away. The orchestrator plans every step of the run up front, checks the branch out in a worktree, confirms the repository is green, then dispatches each story to a coding agent in unattended mode; the agent plans, implements, reviews, and commits; the orchestrator verifies the committed result with the repository's own quality gate and moves to the next story. It stops only where the spec author declared a checkpoint or where an agent could not proceed without a human. When it stops, one screen shows what it needs; when an epic finishes, its branch is pushed and a compare link is waiting.

The MVP is a **dispatcher and a readout**, not an autonomous engineer. Its value is that a story-sized unit of work runs to a verified commit without anyone watching, across any of three agent harnesses — Claude Code, Codex, or a local open-weight model — with every model call routed through one gateway and every run visible as one trace with one cost. It moves the engineer's time from typing implementations to writing stories and answering the occasional question.

It exists now because the pieces already exist: the BMAD `bmad-build-auto` skill implements a story unattended and reports its outcome in the story file; `stories.yaml` already carries the checkpoint fields a dispatcher needs; a durable workflow engine on Postgres gives restartable runs; and the three harnesses all run headless. The MVP wires them together and puts one honest screen in front.

## 2. Target user

### 2.1 Jobs to be done
- **Functional:** run every story of an epic to a verified commit while I do something else; stop me only when the spec author said so or when an agent is stuck; tell me in one glance where everything is and what needs me.
- **Functional:** compare harnesses and models on the same work — cost, time, and outcome per story — through one gateway and one tracing tool.
- **Emotional:** trust the green. A step that was not actually checked must never look checked.
- **Contextual:** come back cold after a day or two and reload the state of a run in under five minutes.

### 2.2 Non-users (MVP)
- Anyone who is not the single operator. No second account, no roles, no sharing.
- Teams whose repositories have no deterministic quality command — the MVP will run, but every verify step is `skipped` and stated as such.
- Anyone expecting the orchestrator to write the spec, open issues, or merge.

### 2.3 Key user journeys

- **UJ-1. Rebeca sets up a project and finds out the token is wrong before it matters.** Rebeca, the sole operator, logs in with the access token and creates project *Website*: context text, two repositories with their `quality_gate_command`, two agent environment variables. She saves. The clone check runs per repository; the second one reads `failed` with the verbatim `fatal: Authentication failed` and a one-line fix: the instance's GitHub token has no access to that repository. The Project is saved anyway, but no Run can start on that repository until the check passes; she grants the token access, re-runs the check from the row, both repositories read `ok`. **Edge case:** the second repository has never been initialised for the method — its row offers *Initialise repository*, which pushes a `chore/bmad-init` branch and shows the compare link (FR-30). **Edge case:** a repository with no quality command saves fine and is marked *verify step will be skipped* on its row.

- **UJ-2. Rebeca starts an epic and walks away.** Base branch `main` already holds `specs/notifications/epics.yaml` — two epics, each naming its branch (`feat/notifications-mm` for both, so the second stacks on the first) and its spec folder with `SPEC.md` and `stories.yaml`. From the board she opens *New workflow*, picks template `initiative` v1, project, repository, base `main`, the initiative folder, harness `claude`, a $40 budget, and types "6" into *manual estimate*. Pre-flight reads two epics and eight stories, lists the branch each epic will create or check out, warns that story 4-2 has a spec checkpoint, confirms `_bmad/` on the base branch matches the image, everything else `ok`; *What will run* lists every planned step. She clicks *Start run*. The card appears in **Running** with `checkout`, then `baseline`, then `epic 1 · story 1-1 · build · claude`. She closes the laptop. **Edge case:** the repository is already held by another run — the card appears in **Queued** with "waiting: repository lock held by feat/saved-views".

- **UJ-3. Two days later, one card is amber.** Rebeca opens the board: one card in **Needs you**, `BLK · story 4-1 · intent gap · 2d 04h`. She opens it. The question is at the top: SPEC.md CAP-3 says a Mattermost message is posted on block but not to which channel. Below it the *Answer* box. She types "Post to the project's channel only; no direct message in this story" and clicks *Resume with answer*. The blocked story file is archived with her answer, the story is re-dispatched with the answer as planning context; the card is back in **Running** within the next poll. Twenty minutes later story 4-1 is done; at story 4-2 the run pauses at the spec checkpoint, she reads the planned story spec inline, clicks *Continue*. By evening the card is in **Done** with `2/2 epics · 8/8 stories · 2 links`. **Edge case:** the verify step fails twice on story 4-3 — the card goes amber with the failing command's output; she chooses *Skip story* or *Cancel run*.

## 3. Glossary

- **Operator** — the single authenticated human. Owns every decision the system asks for.
- **Project** — a named unit of context: context text, context file paths, agent environment variables, and one or more Repositories. Scopes the environment variables agents receive; holds no credential (AD-5).
- **Repository** — a git remote registered under a Project with a default branch, package manager, `test_globs`, and optional `install_command` / `quality_gate_command` / `unit_test_command`. Subject of the **Clone check** and of **Repository initialisation** (FR-30).
- **Clone check** — the validation run when a Repository is saved: `git ls-remote`, shallow clone, default branch exists. Result is `ok` or a failure with verbatim git output.
- **Template** — an authored YAML workflow definition with typed **Inputs** and ordered **Steps**, written like a CI workflow: each Step is `uses: <kind>` with `with`, or `run: <command>`. A Template may call another Template (`uses: template`). Has a name and an integer **Version**; a Version is immutable once any Run pins it, directly or as a **Callee Version**.
- **Callee Version** — a Template Version reached through `uses: template` from a pinned Version; frozen with its caller (FR-6).
- **Initiative** — the unit the shipped `initiative` Template runs: an **Initiative folder** holding `epics.yaml`, which lists the epics in order — each entry `id`, `title`, `branch`, `spec_folder` (relative to the Initiative folder), optional `done_checkpoint`. Consecutive epics may name the same branch (stacked) or different branches (one compare link each). One Initiative, one Repository, one Run.
- **Run** — an instance of one Template Version bound to Inputs (Project, Repository, base branch, the folders and branch the Template declares — Initiative folder for `initiative`; **Working branch** and **Spec folder** for `epic` — **Harness**, model, budget, `re_review_done`). Has exactly one **Status**. One Run targets exactly one Repository. Its Steps are **planned** as rows before it starts (FR-8, AD-7), from the branch contents at one commit, the **plan commit**.
- **Step** — one planned row of a Run, produced from a Template node: `uses: <kind>` (kinds in FR-5) or `run: <command>`. Has a **Path**, a **Gate strength**, and a **Step status**. An `agent` Step inside the Story loop is a **Story step**. Every execution of a Step is an **Attempt**.
- **Path** — the human key of a Step: the Template-relative route to it with loop indices, e.g. `epics[0].stories[3].build`. Names the row in the Steps table, the diagram, and the gate record.
- **Gate strength** — what a green Step status means: `liveness` (an artifact exists and parses), `deterministic` (a command exited 0), `human` (the Operator decided). A Step with no oracle is `unvalidated`, never green.
- **Spec folder** — the path, relative to the Repository root on the Working branch, that holds `SPEC.md`, `stories.yaml`, and `stories/` for one epic. It is the **Artifact destination**: agents write there and the Run commits it. `epics.md`, if present, is context for the human only and is never read.
- **Story** — one entry of `stories.yaml`: `id`, `title`, `description`, optional `spec_checkpoint`, `done_checkpoint`, `invoke_dev_with`. Executed in list order.
- **Story file** — `{Spec folder}/stories/{id}-*.md`, written by the agent; its frontmatter `status` (`draft | ready-for-dev | in-progress | in-review | blocked | done`) and `## Auto Run Result` section are the **Agent contract**.
- **Harness** — a coding-agent CLI the orchestrator drives headlessly: `claude` (Claude Code), `codex` (Codex CLI), `local` (OpenCode over a local model). Each has a **Session id** per Attempt. A Harness is offered only after its **readiness run** passed (FR-33).
- **Gateway** — the LiteLLM proxy every model call passes through, reached with one instance key; attributes spend per Run and per Attempt from the identifiers every call carries (FR-26).
- **Trace** — the Langfuse trace for a Run; orchestrator spans and Harness/Gateway generations share the Run's id as Langfuse session.
- **Checkpoint** — a human pause declared in a Story: *spec checkpoint* (after planning, before implementation; a status of the Story step) or *done checkpoint* (after the Story's commit-guard Step; planned as its own `checkpoint` row).
- **Signal** — one Operator action on a Run: `answer | continue | retry | skip_story | skip_epic | budget_raise | cancel | terminal_release`, plus the machine-sent `terminal_resume`. Every Signal is validated against the Run's current Status and written to the gate record (AD-13).
- **Protected path** — a file an agent must not modify during a Run: the spec files, every `AGENTS.md`, and pre-existing test files; the exact set and the check are FR-31.
- **Trajectory** — the append-only record written once per done Story: harness, model, attempts, gate results, cost, story-file snapshot, start and end commit (FR-32).
- **Needs you** — the Run Status column and rail count grouping every Run whose next action is the Operator's (the stops listed in §4.6).
- **Question** — the text shown to the Operator for a `blocked` Story: the whole `## Auto Run Result` section of the Story file (status, blocking condition, and any listed questions and evidence), attributed to Harness, model, and time.
- **Attempt** — one execution of a Step of any kind; a Step may have several Attempts (template retry, re-dispatch after an Answer or a verify failure, re-run after interruption); the Steps table shows the latest and counts the rest. Harness fields are empty on Attempts of non-agent Steps.
- **Answer** — Operator text resolving a `blocked` Story; the mechanism (archive the blocked Story file, re-dispatch with the Answer as planning context) is FR-18.
- **Gate record** — append-only list per Run of Operator decisions and machine stops: time, Step path, event, actor, text. Events are the Stop kinds (§4.6 table), the Signals (see **Signal**), and the Run transitions (`start | done | failed | cancelled`).
- **Status** — Run: `queued | running | needs-you | done | failed | cancelled` (`needs-you` is stored as `needs_you`). Step: `planned | queued | running | done | blocked | checkpoint | error | skipped`; `planned` means the row exists and its predecessor is not yet done. Tokens: Run `QUE RUN DON ERR CAN`, with `needs-you` rendered as `BLK` or `CHK` per the Stop kind (§4.6 table); Step `QUE RUN DON BLK CHK ERR SKP`, with `planned` rendered `QUE`. `CAN` is Run-only.
- **Board** — the home screen: Runs as cards in five Status columns.
- **Worktree** — a git worktree at `/work/{project}/{repo}/wt/{branch}` where a Run executes; one per (Run, branch), so an initiative whose epics name two branches holds two. A Run records every Worktree it created.
- **Stop** — a machine-detected condition that parks the Run in `needs-you`; every Stop has a **kind** (§4.6 table), a reason text, and the Signals it admits.

## 4. Features

### 4.1 Access
**Description:** one Operator, one secret. The login screen takes the access token from the server environment; a session cookie lasts 30 days. Nothing else is on that screen. Realises UJ-1.

#### FR-1: Token login
The Operator can authenticate by entering the access token; every `/api/*` call requires the resulting session.
**Consequences (testable):**
- A correct token sets an HttpOnly cookie valid 30 days and redirects to the Board.
- A wrong token returns the login screen with the line `token rejected — n attempts left`; after 5 failures within 15 minutes the endpoint refuses for 15 minutes. `[ASSUMPTION: lockout numbers]`
- An unauthenticated `/api/*` request returns 401; an unauthenticated page load redirects to `/login`.

### 4.2 Projects and Repositories
**Description:** a Project carries the context every agent reads before a Story, its agent environment variables, and its Repositories. Credentials are not per Project: the GitHub token and the Gateway key are instance environment variables (AD-5). Saving a Repository runs the Clone check so a bad URL or a token without access fails at configuration time, not hours into a Run. Realises UJ-1.

#### FR-2: Create and edit a Project
The Operator can create a Project with name, context text, optional context file paths, and agent environment variables.
**Consequences (testable):**
- Context text and context file paths are stored and delivered to every Story step as `project-context.md` (FR-15).
- Environment variables are stored encrypted at rest, returned by API responses after save masked to their last four characters only, exported into every Step of that Project's Runs, and into no other Project's Runs.
- No GitHub token and no Gateway key can be entered on a Project; both come from the instance environment and the Project screen says so.
- A per-Project switch `log_prompt_content` controls whether prompt and tool content reach Langfuse; its default is the instance setting `LOG_PROMPT_CONTENT_DEFAULT` (off unless set); the Project screen states that enabling it sends source code to Langfuse.

#### FR-3: Register a Repository with commands
The Operator can add a Repository to a Project with URL, default branch, package manager, `test_globs`, and optional `install_command`, `quality_gate_command`, and `unit_test_command`.
**Consequences (testable):**
- A Repository without `quality_gate_command` saves successfully and its row states `verify step will be skipped`.
- The default branch is checked on the remote by the Clone check (FR-4); a missing branch is a failed check, reported on the row.
- `test_globs` defaults to `tests/**`, `**/*.test.*`, `**/*.spec.*` and names the test files protected during a Run (FR-31); the form shows the default and accepts additions.

#### FR-4: Clone check on save
The system runs the Clone check for every Repository when the Project is saved and reports the result of each check.
**Consequences (testable):**
- Checks: `git ls-remote` succeeds; shallow clone into `/work/{project}/{repo}/base` succeeds; default branch exists. Each reports `ok` with duration, or the verbatim command output.
- A failing check does not block the save: the Repository is stored with status `failed` and the verbatim output on its row, and no Run can start on it until a check passes; the Operator can re-run the check from the row.
- The check re-runs daily; a failure sets the Repository's status to `failed` and blocks **new** Runs on that Repository only. `[ASSUMPTION: daily re-check cadence]`
- Clone and every later git command receive the instance GitHub token per command; the token is never stored and never written to a Worktree.

#### FR-30: Initialise a Repository for the method
The Operator can initialise a registered Repository for BMAD from its row: the system runs the shipped `repo-init` Template, which installs the pinned method files on a new branch, pushes it, and shows the compare link.
**Consequences (testable):**
- The action creates a Run of `repo-init` v1 on branch `chore/bmad-init` from the default branch; it adds `_bmad/` (config, scripts, `custom/`) and git-ignore lines for the skill folders (`.claude/skills/bmad-*`, `.agents/skills/bmad-*`), commits, pushes, and records the compare link. Skill and agent folders are never committed to the target Repository (AD-16).
- The installed version equals the instance's pinned `BMAD_VERSION`; running the action on an already-initialised Repository updates `_bmad/` to that version on the same branch name.
- The Repository row states the method version found on the default branch, `missing`, or `outdated`, read by the Clone check from `_bmad/_config/manifest.yaml`.
- The action is subject to the repository lock (FR-13) like any Run.
### 4.3 Templates
**Description:** a Template is versioned YAML with typed Inputs and Steps, written like a CI workflow (`uses:` a shipped kind with `with`, or `run:` a shell command). The Operator edits the YAML in the browser; the system validates it, computes its graph, and the browser draws it beside the editor; saving creates the next Version. The MVP ships four Templates: `repo-init`, `story`, `epic`, and `initiative`, composed by call (`initiative` → `epic` → `story`); `initiative` is the PRD's dev loop, `epic` is its unit for one branch, `story` is a callee only (it has no checkout of its own and is not offered in New workflow). Realises UJ-2.

#### FR-5: Template schema and validation
The system accepts Templates conforming to the DSL v1 (Inputs of type `project | repository | string | path | enum | number | item`; a Step is `uses: <kind>` with `with`, or `run: <command>`; kinds `git.worktree | git.sync | shell | agent | git.commit | git.push | pr.link | checkpoint | template | bmad.install`; one `for_each` construct over a YAML list file; `{{variable}}` substitution only) and rejects anything else. The full key table is the spine's "Template DSL v1 keys".
**Consequences (testable):**
- *Validate* returns every error with template, version, line, and reason: unknown key, unbound variable, unknown kind, `uses` and `run` on the same Step, nested or second `for_each`, expression syntax, non-literal version, call cycle, call depth over 3, callee input name or type mismatch, `parallel`, and `timeout_min` or `on_fail` on a `template` call.
- No loop other than `for_each`, no conditionals, no string functions are accepted. `for_each` accepts `pause_before_item_when` and `pause_after_item_when` (one item field each); `parallel` is reserved and rejected.
- An `agent` Step may declare `expect {files, status_in}`, `retry {max, prompt, resume_session}`, `escalate_when`, and `pause_when`; any Step may declare `timeout_min` and `on_fail` (`escalate | fail | continue | {redispatch, max}`).
- A `template` call declares `with {name, version, inputs}`; the callee sees only its declared Inputs, never the caller's scope.
- Every Step declares a Gate strength or the validator reports it as `unvalidated`.

#### FR-6: Immutable Versions
The Operator can save an edited Template, which creates Version n+1; a Version pinned by any Run, directly or as a Callee Version, cannot be modified or deleted.
**Consequences (testable):**
- Saving never changes the YAML of an existing Version; the versions list shows how many Runs pin each and which Versions call it.
- A Run started under Version n still resolves Version n, and every Callee Version it pinned, after later Versions exist.

#### FR-7: Rendered diagram
The system computes a read-only graph of a Template Version — one node per Step (kind, name, Gate strength), `for_each` as a group, `template` calls as collapsed nodes, agent Steps and human gates distinguished — and the browser lays it out and draws it.
**Consequences (testable):**
- The graph is produced by the backend from the same validator the editor uses (AD-15); the browser never parses YAML.
- The diagram updates on every successful validation of the editor content; invalid YAML leaves the last valid diagram with a stated error.
- No node can be dragged, added, or edited in the diagram.

### 4.4 Runs and the dev loop
**Description:** a Run binds Inputs to a Template Version, is planned completely into Step rows before it is enqueued (AD-7), and executes durably. The shipped dev loop is `initiative` → for each epic {`epic` → checkout (the epic's branch) → baseline → for each Story {`story` → sync → build → verify → commit-guard [→ done checkpoint]} → push → compare link}. Every file the orchestrator writes before a dispatch is committed before the agent starts, because the agent requires a clean tree; the agent commits its own work before it exits (`bmad-build-auto` finalises with a clean tree); the orchestrator verifies the committed tree and only commits what the agent left behind. Runs survive process restarts and resume at the last completed Step. `[ASSUMPTION: every Spec folder listed in epics.yaml contains SPEC.md and stories.yaml as produced by bmad-spec]` `[ASSUMPTION: one Repository per Run; an initiative spanning repositories is split by the Operator into one Run per Repository]` Realises UJ-2, UJ-3.

#### FR-8: Start a Run with pre-flight
The Operator can create a Run by choosing a Template Version (`initiative`, `epic`, or `repo-init`; `story` is not offered), Project, Repository, base branch, the Inputs the Template declares (for `initiative`: the Initiative folder — each epic's branch comes from `epics.yaml`; for `epic`: the Working branch and the Spec folder), Harness, optional model, budget, *re-review done Stories*, and optional manual estimate; pre-flight runs on every field change.
**Consequences (testable):**
- Pre-flight reports:
  - origin reachable; base branch exists;
  - every branch the plan checks out exists (will check out) or not (will create from base); none is held by a Worktree of a non-terminal Run;
  - `epics.yaml` parses with its epics, branches, and Spec folders in order (for `initiative`); the Initiative folder is present on the base branch or on every epic branch that already exists;
  - every `stories.yaml` parses with N Stories and ids such that no id equals another id followed by `-` (`4-1` and `4-10` are fine; `4-1` and `4-1-a` are not), so `{id}-*` globs are unambiguous;
  - declared Checkpoints (warning);
  - `SPEC.md` found in every Spec folder;
  - Harness enabled (its readiness run passed, FR-33);
  - `_bmad/` present at the plan commit with a method version equal to the instance's pinned `BMAD_VERSION` (else: `run Initialise repository and merge its branch`, FR-30);
  - existing `stories/*.md` files listed with their statuses;
  - Repository Clone check not `failed`.
- Any failing check disables *Start run* and states the fix; warnings never block.
- The manual estimate, if given, is stored on the Run before any Step executes and cannot be edited afterwards.
- The screen shows *What will run*: the complete planned Step list — every row with its Path, kind, and Gate strength, starting with the `plan` row that performs the stale-plan check below, loops expanded to the parsed epic and Story counts, already-done Stories shown as `skipped · already done` unless *re-review done Stories* is on — produced by the same planner that will persist the rows, so what the Operator sees is exactly what runs.
- Every planned row is read from the remote branch at one commit (the plan commit), recorded on the Run; a later edit of the branch or of the Repository does not change the plan.
- When a Run leaves the queue and its first Step starts, the list files (`epics.yaml`, every `stories.yaml`) at the branch head are compared with the plan commit; a difference parks the Run before any Step with reason `plan stale: {file}` — the Operator Cancels and starts a new Run, or Continues on the recorded plan. A Run never silently executes a plan that no longer matches its branch. `[ASSUMPTION: list-file changes after planning are rare; a full re-plan of a queued Run is deferred]`
- *Start run* persists the planned rows and enqueues the Run; the response states whether it starts now or queues behind a named Run. A plan-time error names the Template, Version, line, and item.

#### FR-9: Checkout and baseline
The Run creates a Worktree on the Working branch (from the base branch when the Working branch does not exist) and runs the Repository's `quality_gate_command` before any Story of an epic.
**Consequences (testable):**
- The Worktree path is `/work/{project}/{repo}/wt/{working branch}` and appears in the Run header; the Run records every Worktree it created or reused, and whether it created the branch and pushed it.
- When the Repository declares `install_command`, checkout runs it in the Worktree before baseline and records its output in the checkout Step; when absent nothing runs and the Step log says so.
- A non-zero baseline exit sets the Run to `failed` with the command output attached and no Story step started; spend is $0.
- A Repository without `quality_gate_command` records the baseline Step as `skipped`.
- An existing Worktree for the Working branch is reused when `git status --porcelain` is empty; otherwise the Run refuses to start with the reason. Worktrees of Runs in a terminal Status are removed 7 days later; base clones are kept. `[ASSUMPTION: 7-day worktree retention]`

#### FR-10: Story loop
The Run executes Stories in `stories.yaml` list order; for each: a sync Step, a Story step (FR-14), a verify Step, a commit-guard Step, and a done-checkpoint Step when the Story declares one.
**Consequences (testable):**
- The Story list is read once, at planning, and never re-read during the Run; the rows exist before the first Step starts.
- A Story whose file already reads `done` at planning has its rows planned `skipped · already done` and is not dispatched, unless the Operator enabled *re-review done Stories* at start.
- sync fetches origin and fast-forwards the branch; a branch with no upstream yet (created by this Run, not pushed) makes sync a recorded no-op. A non-fast-forward sets the Step to `error` and the Run to `needs-you` with reason `sync: branch diverged` and the git output; the Operator resolves it on the remote (merging into the branch), never in the Worktree, then Retries; the Retry fetches again and fast-forwards.
- verify runs `quality_gate_command` in the Worktree on the tree the agent committed. On exit ≠ 0 the Template's `on_fail: {redispatch, max: 1}` applies: the orchestrator appends a `## Verify Failure` section (command, exit code, last 200 lines) to the Story file, sets its status to `in-progress` (which routes the agent straight to implementation), and re-dispatches the Story step as a new Attempt. A second failure sets the Run to `needs-you` with reason `verify failed 2/2`. `[ASSUMPTION: the implementation step reads the appended Verify Failure section as part of the spec]`
- commit-guard adds anything the agent left uncommitted (the Spec folder staged before the rest of the tree) with message `story {id}: {title} (orchestrator)`; a clean tree commits nothing and records `no changes` — the normal case. It also runs the protected-path check (FR-31).
- Every Step has a maximum wall-clock time, declarable in the Template (`timeout_min`), defaulting to 90 for Story steps, 30 for `shell`, 5 for `git.*`; on expiry the process group is killed, the Step is `error`, and the Run is `needs-you` with reason `timeout {path} after {n} min`. The timer belongs to the process runner, never to the workflow engine (AD-14).
- Every automatic re-execution — template `retry` (FR-16) or verify redispatch — is a recorded Attempt with a gate-record entry and a counter on the Step; when the counter reaches `max` the Run parks. `blocked`, budget, timeout, protected-path, internal, and configuration failures are never re-executed automatically (AD-9).
- Bounds are per Attempt for time and per Step for counts: a Story step runs at most `(1 + retry.max) × (1 + redispatch.max)` Attempts (six for the shipped `story` Template), each under its own `timeout_min`; the budget check (FR-17) runs after every Attempt, retries included, so a Run can never exceed its budget by more than one Attempt.

#### FR-11: Push and finish
After the last Story of an epic the Run pushes the Working branch to origin and records a compare link; after the last epic the Run is done.
**Consequences (testable):**
- Push supplies the instance GitHub token to each git command individually; the token never appears in the environment of any agent process.
- The push Step refuses when Working branch equals the Repository default branch.
- A rejected push (remote diverged, permission) sets the Run to `needs-you` with reason `push rejected` and the git output; Retry re-runs the push after the Operator resolves it. The orchestrator never force-pushes.
- The compare link is the GitHub compare URL for `{default branch}...{Working branch}`, appended to the Run's list of links, one per epic; the Operator opens the pull request. `[NON-GOAL for MVP: creating the pull request]` When a Story or epic was skipped, the Run summary lists it beside the link.
- Run Status becomes `done`; the card shows `n/n epics · m/m stories · k links` — links, because no pull request is ever created.

#### FR-12: Durability and recovery
Runs survive orchestrator restart and container replacement without repeating completed Steps.
**Consequences (testable):**
- Killing the process during any Step and restarting resumes the Run at that Step; completed Steps are not re-executed.
- An interrupted Story step re-runs as a new Attempt with a new Session id; the agent resumes from the Story file's own status.
- Before every Story step Attempt the orchestrator commits any uncommitted changes in the Worktree as `wip: story {id} attempt {n} (interrupted)`, then writes what the dispatch needs (`project-context.md`, the archived Story file and Answer, the `## Verify Failure` section) and commits that as `orchestrator: prepare story {id} attempt {n}`, because the agent refuses to start on a dirty tree. The Attempt's start commit is the second one; nothing the orchestrator wrote is ever attributed to the agent.
- Every Harness process runs in its own process group whose id is recorded on the Attempt; a re-attempt first terminates the recorded group (TERM, then KILL) and waits for `.git/index.lock` to disappear. Test: kill the orchestrator mid-Story, restart — exactly one Harness process for that Run exists afterwards.
- The checkout Step is idempotent: a Worktree that exists on the right branch is reused; a missing one is recreated; `/work` and the Harness session directories are persistent volumes.
- A Run parked in `needs-you` for 30 days resumes correctly on Answer or Continue; at 30 days without a Signal the Run becomes `failed` with reason `parked 30 days` and its Worktrees follow the 7-day retention.
- An orchestrator image upgrade while Runs are parked does not re-plan them; a parked Run resumes on the new image, and pre-flight's method-version check applies to new Runs only. `[ASSUMPTION: image upgrades are drained of running Runs, not of parked ones]`

#### FR-13: Concurrency and repository lock
The system runs at most one active Run per Repository and at most two active Runs overall; further Runs queue in order.
**Consequences (testable):**
- Two Runs on the same Repository: the second shows `queued` with `waiting: repository lock held by {run}` until the first reaches a terminal Status. A `needs-you` Run **holds** its lock — the pre-flight and the queue row say so — because two Runs must never share a Repository's worktrees (mechanism: addendum §D).
- Runs on different Repositories execute concurrently up to the instance's active-Run limit (default 2). A `needs-you` Run also **holds one of these slots**: two parked Runs stop every other Repository until one is answered, skipped, or cancelled. The queue row says `waiting: global concurrency, held by {runs}`, and the Board's rail count makes the parked Runs the first thing on screen. This is the accepted trade-off of one worktree per Run and no release-on-park; the limit is an instance setting, not a per-Run one.
- The Runs screen shows queue position and the waiting reason.
- The lock is the queue's per-Repository partition (AD-12); there is no separate lock table.

### 4.5 Story steps and Harnesses
**Description:** a Story step invokes `bmad-build-auto` in folder+id dispatch through the chosen Harness, in the Worktree, with the Project context prepended and `invoke_dev_with` appended. The Harness is irrelevant to the outcome contract: the Story file is the result. Realises UJ-2, UJ-3.

#### FR-14: Dispatch a Story to a Harness
The system runs a Story step by launching the Harness headlessly in the Worktree with a prompt that names the skill, Spec folder, and Story id, plus `invoke_dev_with`, plus "Halt after planning." when `spec_checkpoint` is true — and nothing else, so the skill's intent detection is not disturbed.
**Consequences (testable):**
- The Harness runs non-interactively in the Worktree with approvals pre-granted, and must expose to the skill **a subagent-spawning tool, file read and write, and shell**. `bmad-build-auto` HALTs `blocked · no subagents` without the first, so a Harness mode that hides it is unusable. *(Confirmed against Claude Code 2.1.246: `--bare` exposes only `Bash, Edit, Read` — no subagent tool, no `Write` — and neither `--add-dir` nor `--tools default` restores them. The Claude adapter therefore uses default discovery with an explicit allowlist, not `--bare`.)*
- The `bmad-build-auto` skill is installed in the orchestrator image for every Harness (`~/.claude/skills` for `claude`, `~/.agents/skills` for `codex` and `local`) and resolves the Worktree, which carries `_bmad/`, as its project root; a Harness that cannot run the skill from a Worktree fails its readiness run (FR-33), not a Run.
- A Session id is recorded for every Attempt: pre-assigned where the Harness supports it, otherwise captured from the Harness's own output or session store.
- **The exact CLI invocation per Harness is not fixed here.** It is resolved from each Harness's current documentation at implementation time and recorded in `addendum.md` §B, because these CLIs change between releases. Each Harness's static configuration is generated by its own setup script from instance environment variables and references variable names only; per-Run values travel in the process environment (AD-10).
- A Harness is offered in New workflow only after its readiness run passed (FR-33). A Harness exit caused by the Harness's own budget cap (the `claude` adapter passes the remaining budget as its cap) is routed as a budget halt (FR-17), never as a retry.
- A Harness process receives no credential other than the instance Gateway key: never the GitHub token, never a direct provider key, never the orchestrator's own environment. It receives the Gateway base URL and key, the Langfuse endpoint and keys, the Run, Attempt, Story, Harness and Project identifiers, the trace context, the Project's environment variables, and the content-logging switch (FR-2).
- The Attempt records Harness, model, Session id, exit code, wall-clock time, tokens in/out, cost, and the process log.

#### FR-15: Project context in the prompt
Before every Story step the system writes the Project's context text and the list of its context file paths to `{Spec folder}/project-context.md`, which `bmad-build-auto` loads as a persistent fact for the whole run.
**Consequences (testable):**
- The file is regenerated at every dispatch and committed by the commit-guard; it is never part of the prompt.
- A context file path that does not exist in the Worktree is reported in the Step log and omitted from the file, never silently ignored.

#### FR-16: Agent contract evaluation
After the Harness exits, the system reads `{Spec folder}/stories/{id}-*.md` and routes on its frontmatter `status`.
**Consequences (testable):**
- Exactly one matching file with parseable frontmatter satisfies liveness; the Step is `done` only when its status routes forward (next bullet). Zero or several files, or unparseable frontmatter, is Step `error`, Run `needs-you` with reason `no story file` / `ambiguous story file` listing the files; Retry after `ambiguous story file` first archives every matching file except the newest to `stories/.answers/`, so the ambiguity cannot compound.
- A `blocked` file whose blocking condition is `no subagents`, `no stories.yaml found`, `story id not found in stories.yaml`, or `version-control metadata not writable` is a configuration failure, not a Question: Step `error`, Run `needs-you` with reason `harness misconfigured: {condition}` and no Answer box.
- Routing on the frontmatter status:
  - `done` → Step `done`, verify Step next;
  - `blocked` → Step `blocked`, Run `needs-you`, the whole `## Auto Run Result` section (status, blocking condition, and any listed questions and evidence) shown as the Question;
  - `ready-for-dev` with `spec_checkpoint` → Step `checkpoint`, Run `needs-you`;
  - any other status, or a Harness exit code ≠ 0 with a `done` file → Step `error`; before parking, the Template's `expect` + `retry {max, prompt}` on the Step applies: while the retry count is below `max` the Step re-runs as a new Attempt with the prompt, resuming the same session where the Harness allows it, else in a new session with the prompt prepended; when exhausted, Run `needs-you` with reason `unexpected status: {status}` / `harness exit {code}`.
- A modified Protected path (FR-31) is checked before routing and wins over every route above: Step `error`, Run `needs-you` with reason `protected path modified: {file}`.
- An unexpected exception inside any Step → Step `error`, Run `needs-you` with reason `internal: {error}`; Retry re-runs the Step.
- Every stop above maps to one Stop kind of the §4.6 table.
- The Step's Gate strength is recorded as `liveness`; the UI never renders a Story step green on its own — only the following verify Step (deterministic) or its `skipped` word.

#### FR-17: Budget halt
The system halts a Run whose spend exceeds its budget.
**Consequences (testable):**
- After every Story step Attempt (when the Harness process exits, before the verify Step), the Attempt's spend is read from Gateway spend logs by the Run and Attempt identifiers every call carried (FR-26) and the Run's spend is the sum over its Attempts; if spend > budget the Run becomes `needs-you` with reason `budget {spent} / {budget}` and no further Harness process is started. The Step keeps the status its file routed to.
- When the Gateway figure for the Attempt is not yet available, the Harness-reported usage is used for the halt check and marked provisional; the Gateway figure replaces it on the next check.
- The Operator can raise the budget on the Run, or Cancel. Raising the budget resumes the Run at the Step's routed status: a Step that routed to `blocked` or `checkpoint` returns the Run to that stop with its Question, and is not re-dispatched; a Step that routed to `done` continues.

#### FR-31: Protected paths
After every Story step Attempt and at every commit-guard, the system checks that the agent modified no Protected path; a hit parks the Run.
**Consequences (testable):**
- Protected paths per Run: `SPEC.md` and `stories.yaml` of the Spec folder, `epics.yaml` of the Initiative folder, every `AGENTS.md`, and every file matching the Repository's `test_globs`, as they existed when the **Story's first Attempt** started. Test files the agent created during the Story stay editable on its later Attempts (verify redispatch, retry); modifying or deleting a pre-existing one is not allowed. An `AGENTS.md` created by the agent is a hit.
- The check compares the tree against the Attempt's start commit (after the prepare commit of FR-12), so an Operator edit made while the Run was parked (FR-19) and every file the orchestrator wrote are never attributed to the agent.
- A hit sets the Step to `error` and the Run to `needs-you` with reason `protected path modified: {files}` and the diff names; it is never retried automatically. The Operator *Accepts* the change (Continue on this stop: the files are named in the gate record and the Trajectory, and the Step resumes routing on the same tree), reverts on the branch and Retries, or Skips the Story. Accepting is the only way an agent-made test change ships.
- The Story file the agent writes under `stories/` is not a Protected path.

#### FR-33: Harness readiness
A Harness is offered in New workflow only after its readiness run — the shipped `epic` Template on the built-in fixture Repository with one trivial Story — reached `done` and its spend was attributable.
**Consequences (testable):**
- The fixture Repository lives under the built-in Project `readiness`, which the Operator cannot edit or delete; readiness runs are ordinary Runs on the Board and the Runs screen, on branch `readiness/{harness}/{date}`, never pushed.
- The readiness run passes when all of these hold, each reported as its own line: the Story file reaches `done` (proves subagent tool, file read and write, shell, and skill discovery from a Worktree); a Session id was recorded; the Run trace contains the Attempt's Harness spans (`claude`, `codex`) or its generations under the Run's session (`local`); the Gateway returned a non-empty spend for the Attempt; verify exited 0. Any failing line keeps the Harness `disabled: {line}`.
- The Harness list on New workflow reads `enabled` / `disabled: {check}` per Harness, with the time of the last readiness run; the Operator can re-run readiness from the same screen.
- A Harness whose version pin changed is disabled until its readiness run passes again; Runs already parked on that Harness keep it and resume on it.

### 4.6 Human gates
**Description:** the Run stops for the Operator only for the Stops in the table below, and every Stop offers a subset of the same small set of actions on the Run detail (Answer, Continue, Skip story, Skip epic, Retry, Raise budget, Cancel; FR-18..FR-20). Every action is one Signal: validated against the Run's current Status, refused with the reason when invalid, written to the gate record, and applied by the Run itself when it resumes — so no action is ever applied twice or half-way (AD-13). This table is the only list of Stops; FR-16, FR-17, FR-31 and the glossary refer to it. Realises UJ-3.

| Stop kind | Reason text (verbatim on screen) | Token | Signals admitted |
| --- | --- | --- | --- |
| `blocked` | the Story's `## Auto Run Result` | BLK | Answer, Skip story, Skip epic, Cancel |
| `checkpoint` | `spec checkpoint` / `done checkpoint` | CHK | Continue, Reject with a reason (spec only), Skip story, Skip epic, Cancel |
| `verify_failed` | `verify failed 2/2`, `re-baseline failed after skip` | BLK | Retry, Skip story, Skip epic, Cancel |
| `budget` | `budget {spent} / {budget}` | BLK | Raise budget, Cancel |
| `timeout` | `timeout {path} after {n} min` | BLK | Retry, Skip story, Skip epic, Cancel |
| `push_rejected` | `push rejected`, `sync: branch diverged` | BLK | Retry, Skip epic, Cancel |
| `protected_path` | `protected path modified: {files}` | BLK | Continue (accept), Retry, Skip story, Skip epic, Cancel |
| `misconfigured` | `harness misconfigured: {condition}`, `no story file`, `ambiguous story file`, `unexpected status: {status}`, `harness exit {code}`, `gateway unreachable` | BLK | Retry, Skip story, Skip epic, Cancel |
| `plan_stale` | `plan stale: {file}` | BLK | Continue, Cancel |
| `internal` | `internal: {error}` | BLK | Retry, Skip story, Skip epic, Cancel |

Skip story at a done checkpoint marks the checkpoint skipped and continues; Skip story on the last Story of an epic proceeds to the epic's push; Skip epic on a rejected push marks the push and the compare link skipped and continues with the next epic; Skip story and Skip epic are not offered on `budget` or `plan_stale`.

#### FR-18: Answer a blocked Story
The Operator can answer a `blocked` Story from the Run detail; the blocked Story file is archived with the Answer and the Story is re-dispatched with the Answer as planning context.
**Consequences (testable):**
- The Answer box states, in words above the button, exactly what will happen: which file is archived where, and that the Story is re-planned with the Answer.
- On submit: the Story file is moved to `{Spec folder}/stories/.answers/{id}-attempt-{n}.md` with the Answer appended under `## Human Answer` (so no `stories/{id}-*.md` remains and the re-dispatch is a first dispatch). The re-dispatch prompt carries `Answer from the operator to the blocking condition "{condition}": {answer}` as planning context. The Story step re-runs on the same Harness. `[ASSUMPTION: the Answer as planning context resolves the intent gap on re-planning; if the gap is in SPEC.md the Operator edits SPEC.md on the branch instead, and the Answer box says so]`
- The Run leaves `needs-you` within one poll interval of the Answer.
- The Answer, actor, and time are written to the gate record.

#### FR-19: Continue at a Checkpoint
The Operator can Continue a Run paused at a spec checkpoint (after reading the planned Story file inline) or a done checkpoint.
**Consequences (testable):**
- spec checkpoint: Continue re-dispatches the Story with its file at `ready-for-dev`, which the agent implements without re-planning. *Reject with a reason* is the Answer Signal accepted at a spec checkpoint (FR-18): the planned file is archived and the Story re-planned with the reason.
- While a Run is `needs-you` (and no terminal session is in progress, FR-21) the Operator may edit any file of the Spec folder inline from the Run detail except the planned list files (`stories.yaml`, `epics.yaml`), which the editor shows read-only with the reason `planned at {commit}`; each save is committed at once on the branch as `spec: operator edit (orchestrator)` and named in the gate record, so the next Attempt starts from it and the Protected-path check (FR-31) never attributes it to the agent.
- done checkpoint: a `checkpoint` Step planned after the Story's commit-guard from `stories.yaml`; the Run parks on it and Continue marks it `done` and starts the next Story.
- Both write a gate record entry.

#### FR-20: Skip a Story or an epic, retry a Step, cancel a Run
The Operator can skip the current Story or the current epic (marking their remaining Steps `skipped` and proceeding), retry the current failed Step, or cancel the Run.
**Consequences (testable):**
- Skip story marks every not-yet-done agent and checkpoint Step of the current Story `skipped · skipped by operator`; the Story's verify Step then runs as the re-baseline and its commit-guard commits any leftovers as `story {id}: skipped by operator`, so the next Story starts on a clean, green tree. If the re-baseline exits non-zero the Run stays `needs-you` with reason `re-baseline failed after skip`. Any commits the agent already made stay on the branch; the Run summary and compare link list the skipped Story.
- Skip epic does the same over the remaining Stories of the current epic; the current Story's commit-guard still runs, then the epic's push and compare link run so that every done commit reaches the remote (they are marked skipped only when the push itself is the stop), and the Run continues with the next epic. The compare link lists the skipped Stories.
- After `re-baseline failed after skip` the Operator fixes the tree on the branch (inline edit, terminal session, or a push to the remote followed by Retry, which syncs first) and Retries the verify Step, or Skips the epic; a next epic whose baseline then fails ends the Run `failed` as FR-9 states.
- Retry is offered on a `needs-you` Run whose current Step is `error` (timeout, harness exit, push rejected, misconfigured, internal, verify failed); it re-executes only that Step as a new Attempt. `failed` Runs are terminal — the Operator starts a new Run. Retrying a Story step whose file is already `done` starts the agent's review pass, not a re-implementation.
- Cancel requires a confirmation; it terminates any Harness process group of the Run, then stops the Run, marks every planned Step `skipped`, removes every Worktree the Run holds, and deletes each branch only if this Run created it and it was never pushed. Status `cancelled`. A result arriving from a Step after cancel is ignored and logged.

#### FR-21: Terminal resume command
For Harnesses that support it, the Run detail shows the exact command to resume the Story's session in a terminal, with the remaining session lifetime.
**Consequences (testable):**
- `claude` and `codex` Story steps show a copyable command that execs into the backend container (`docker compose exec backend-api …`) with Worktree path and Session id, because sessions live in the container; `local` shows none. Remaining session lifetime is shown for `claude` (30 days from the Attempt start, per its documented retention) and omitted for `codex`.
- Copy confirms in place (`COPIED`, ~1.2 s); the string never soft-wraps.
- Copying the command marks the Run `terminal session in progress`; Answer, Continue, Skip, and Retry are disabled until the Operator clicks *Release* or the Story completes as below.
- While a terminal session is in progress and the Run is `needs-you`, the server polls the Worktree every 30 s. When two consecutive polls find the Story file `done` and the Worktree clean (`git status --porcelain` empty, no `.git/index.lock`), the Story step is marked `done` with actor `terminal` in the gate record and the Run resumes at verify without an Answer. `[ASSUMPTION: resume-by-terminal detection by polling the Worktree]`

### 4.7 Board and Run detail
**Description:** the Board is home; five Status columns; a card states the Run's current branch, Project · Repository, current or last Step, epic and Story progress, Template Version, and age. A Step is named by its human label (`epic 1 · story 4-1 · build`) on cards and in the Stories strip; the raw Path (`epics[0].stories[3].build`) is the key in the Steps table and the gate record. The Run detail is the only place decisions are made. Colour rules: NFR-6; visual rules in `EXPERIENCE-v1.md` and `DESIGN.md`. Realises UJ-2, UJ-3.

#### FR-22: Board
The Operator can see every Run as a card in the column of its Status, filtered by Project, with a LIST alternative.
**Consequences (testable):**
- Columns `Queued · Running · Needs you · Done · Failed` always render, empty ones with `—` and count 0. `cancelled` Runs appear under Failed with the word `cancelled`. `[ASSUMPTION: cancelled Runs share the Failed column]`
- With no Runs at all the Board reads `NOTHING RUNNING` and lists what is queued; with no Project registered it reads `NOTHING REGISTERED` and links to Projects.
- The rail shows `n need you` in amber only when n > 0; the footer shows running/queued counts and the last update time.
- A wait longer than 48 h renders its age in amber.
- Cards are not draggable; the whole card opens the Run detail.
- Progress reads `n/n epics · m/m stories · k links` (the epic figure is omitted for an `epic` Run).

#### FR-23: Run detail
The Operator can open a Run and see, in a detail view or a diagram view (FR-29): header (Status, branch, meta line with Project, Repository, base, Initiative or Spec folder, Template Version, Harness, start time, Worktree), an alert banner when the Run is `needs-you` or `failed`, the Question and Answer (FR-18), the resume command (FR-21), the Steps table (`path · kind · gate · status · time · harness · cost`, one row per planned Step including `planned` ones), the Stories strip, the Spec folder file tree with an inline file viewer and editor (FR-19), cost and Trace link, the compare links, and the gate record.
**Consequences (testable):**
- The meta line is never truncated or collapsed.
- The Steps table lists every planned row from the start, keyed by Path, prints Gate strength per row and the words `skipped` / `unvalidated` where applicable, never a green token for them; a row with several Attempts shows the latest and the count.
- The whole detail is one read from the server; the browser aggregates nothing across requests.
- The file tree marks files changed since the Operator last opened this Run.
- The cost block prints `spent / budget` as a ratio, tokens in/out, wall-clock time, active Operator time in this Run, and a link to the Trace. Active time is the sum of intervals during which the Run detail tab is focused, excluding idle gaps longer than 5 minutes; the browser reports focused seconds to the server, which keeps the total on the Run, so the figure survives reloads and devices.

#### FR-24: Refresh model
The Board and Run detail poll: every 5 s while any Run is `running`, else every 30 s; the footer prints the last update.
**Consequences (testable):**
- No content moves under the cursor: updates apply as a state swap without animation.
- A failed fetch renders a full-surface readout with the failed request and a retry control.

#### FR-29: Run diagram
The Operator can switch the Run detail to a diagram view: the Run's planned Steps rendered as a left-to-right tree — Run (the initiative, when the Run is `initiative`) → epics → Stories → their Steps — with every node carrying its Step status token, so the whole Run reads from start to finish: what ran, where it is, what is scheduled.
**Consequences (testable):**
- The graph is produced by the same backend builder as the Template graph (FR-7), fed with the Run's planned rows and their statuses; node ids are Step Paths, groups are Path prefixes. The Template graph shows the same shape with loops unexpanded and calls collapsed; the Run graph expands them to the planned rows.
- Stories appear in `stories.yaml` order under the epic node their Path places them in — grouping comes from the plan, never from story-id prefixes.
- Each node shows its token (`QUE RUN BLK CHK ERR DON SKP`); a Story node also shows its sub-steps (sync · build · verify · commit-guard) as words, never as a second coloured mark. A group's token is derived by one rule: `ERR`/`BLK`/`CHK` if any child is, else `RUN` if any, else `SKP` when all are skipped, else `DON` when all are done or skipped, else `QUE`. The current node is promoted to primary text and labelled `now`; scheduled nodes read `QUE`. No node carries more than one signal colour.
- Clicking a node scrolls the detail view to that Step's row; the diagram and the Steps table are two views of the same data and never disagree.
- The diagram is read-only and refreshes on the same poll as the Run detail (FR-24).

### 4.8 Runs screen
**Description:** every Step of every Run, newest first, plus the queue as the engine sees it. Realises UJ-2 (edge case).

#### FR-25: Queue and history
The Operator can see the queue (position, Run, next Step, waiting reason, waiting time) and paginated Step history (time, Project, Run, Step, type, Harness, Status, duration, cost, Trace link), filtered by Project and Status.
**Consequences (testable):**
- The queue is read from the workflow engine's queued workflows through its port, not from a separate table; reasons are `repository lock held by {run}`, `global concurrency`, `running`, `waiting for your answer`.
- A `needs-you` Run appears in the queue section with position `—` and reason `waiting for your answer`.
- Every execution of any Step is a history row (an Attempt); Harness, Session id, and tokens are empty on non-agent Steps.
- History rows link to the Run detail.

### 4.9 Observability and cost
**Description:** one Trace per Run; every model call through the Gateway; cost attributable to Run, Story, Harness, and Project.

#### FR-26: Gateway routing
Every model call from every Harness passes through the Gateway with the instance key and the identifiers that attribute it: tags `run:`, `attempt:`, `story:`, `harness:`, `project:`, the Run id as Langfuse session, and the Run and Attempt ids as the Gateway's end-user and session fields.
**Consequences (testable):**
- A Harness process with the Gateway unreachable fails its Step with `error` (credential rule: FR-14, NFR-3).
- Gateway spend logs for any call can be filtered to exactly one Run and one Attempt; Langfuse shows every call of a Run under one session.
- No per-Project key, budget, or alias exists at the Gateway; attribution is by identifiers only (AD-11).
- The key a Harness receives can only call models; the key the orchestrator uses to read spend logs is a separate instance variable that never reaches a Harness. `[ASSUMPTION: two instance keys, model-call and spend-read; the spine's single LITELLM_API_KEY is split accordingly]`

#### FR-27: One Trace per Run
The system creates a Trace per Run, seeded from the Run id and carrying the Run id as Langfuse session, and attaches orchestrator Step spans; Harness and Gateway generations join by the Run's trace context or session id.
**Consequences (testable):**
- The Run detail's Trace link opens a Langfuse view containing, at minimum, every Step span and every Gateway generation for the Run.
- Every Attempt runs inside a child span of the Run trace and receives its trace context; for `claude` and `codex`, harness spans are children of that span; for `local`, generations carry the Run id as Langfuse session and user id and are found by session. `[ASSUMPTION: span parenting differs per Harness; local has no inbound trace context]`
- Each Harness reports through exactly one exporter (native telemetry for `claude` and `codex`, the Langfuse plugin for `local`).

#### FR-28: Cost per Attempt
Every Story step Attempt records tokens in/out and cost from Gateway spend, per model.
**Consequences (testable):**
- Run cost = sum of Attempt costs; cost per epic or Story is the sum over the Path prefix; shown on the card summary and Run detail; per-Project monthly spend shown on the Project.
- Gateway spend logs are the authoritative figure; harness-reported usage is shown as provisional until the Gateway figure for the Attempt is available.

#### FR-32: Trajectory export
The system records one Trajectory per done Story and lets the Operator export a Project's Trajectories.
**Consequences (testable):**
- When a Story's build Step is `done` and its verify Step is `done` or `skipped`, one append-only record is written: Run, Story, Harness, model, Attempts, gate results, cost, the Story file as committed, and the start and end commits. Nothing updates or deletes it.
- The Project screen offers *Export trajectories*, a JSON-lines download of every record of the Project, newest first.
- The record carries what SM-1 and SM-3 need per Story; no separate metric table exists.

## 5. Non-goals (explicit)
- The orchestrator does not write specs, epics, or stories, and does not ingest issues. The human authors the Spec folder.
- It does not generate or run end-to-end tests, provision test environments, or judge acceptance criteria. The only oracle is the Repository's own commands.
- It never merges, never pushes to a default branch, never force-pushes.
- It is not a visual workflow editor; the diagram is read-only.
- It is not multi-user, has no roles, and no notification channel outside the UI.
- It is not a harness: it does not implement code itself, only dispatches to Claude Code, Codex, or OpenCode.
- It does not resume or replay harness sessions across containers; session content is harness-local and may be lost.
- It never commits a Harness's skill or agent folders to a target Repository; a Repository commits `_bmad/` and its spec folders only.

## 6. MVP scope

### 6.1 In scope
Token login · Projects with context, environment variables, Repositories, Clone check, and Repository initialisation · four shipped Templates (`repo-init`, `story`, `epic`, `initiative`) with editable versioned YAML, Template calls, and rendered diagram · Runs planned up front, with pre-flight, durable execution, repository lock, checkpoints, blocked-answer, template retry, skip story/epic, retry, cancel, budget halt, Step timeouts, Protected paths · three Harnesses (`claude`, `codex`, `local`) through LiteLLM, each behind a readiness run · one Langfuse Trace per Run with per-Attempt cost · Trajectory records · Board, Run detail (+ diagram view), Runs, Projects, Templates screens in the instrument-dark visual system (`DESIGN.md`).

**Definition of done for the MVP.** `claude` is required. `codex` is required, because SM-3 exists to compare Harnesses. `local` ships if the deferred OpenCode and Mac mini questions (§8) resolve in time; otherwise the fallback in `addendum.md` §C (Codex CLI pointed at the Gateway for local models) satisfies the MVP.

**Tiers.**
- **MUST:** FR-1 (without lockout), FR-2, FR-3, FR-4 (on save), FR-5 (including the `template` call), FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14 (`claude`, `codex`), FR-15..FR-20, FR-22 (board), FR-23 (header, alert, Question/Answer, Steps, Stories, cost), FR-24, FR-25 (queue), FR-26..FR-28, FR-30, FR-31, FR-32 (the record; SM-1 and SM-3 read it), FR-33; Templates `repo-init`, `story`, `epic`.
- **SHOULD:** Template `initiative` (and, with it, the initiative root node of FR-29), FR-6 (save as new Version), FR-7 (diagram), FR-14 `local`, FR-19 inline edit, FR-20 skip epic, FR-21, FR-23 artifacts tree and active time, FR-25 history, FR-29 (Run diagram — shares FR-7's graph, so it rides on FR-7), FR-32 export.
- **COULD:** FR-1 lockout, FR-4 daily re-check, FR-22 LIST view, FR-23 changed-since-last-opened marks, FR-28 per-Project monthly figure.
- **Out of scope:** `parallel` epics.

**Slips first, in order:** the `local` adapter, in-browser Template editing, the `initiative` Template (an epic Run per epic instead), Runs history pagination, cancel rollback of the branch.

### 6.2 Out of scope for MVP
- Intake and spec generation (long-term PRD M2). Deferred.
- Executable-spec oracle (Playwright from criteria, test-id contract, G2/G3 gates). Deferred to the long-term PRD.
- Multi-repository Runs — one Run, one Repository. `[NOTE FOR PM]` This is the first thing an initiative spanning front-end and back-end will hit; the workaround is two Runs, one per Repository.
- Parallel epics (`parallel` is reserved in the DSL and rejected by the validator); per-Repository GitHub tokens; per-Project Gateway keys or budgets. Each has a named landing place in the spine's Deferred list.
- Mattermost or any notification outside the Board. Deferred.
- Second container / multi-machine execution. The architecture does not change shape; deferred until one container is saturated.
- Session-store based resume across containers. Deferred; the Answer path does not need it.
- The verdict metric dashboard (manual estimate ÷ actual). The manual estimate field is captured now because it cannot be retrofitted; the dashboard is deferred.
- `unit_test_command` and `package manager` as consumed fields (`install_command` is consumed by checkout). Both stored for later Templates, unused by the shipped Templates. `[NOTE FOR PM]` Cheap to add as a `run:` Step once the loop is proven.

## 7. Success metrics

**Primary**
- **SM-1: Unattended completion rate** — share of Runs that reach `done` without any human action other than declared Checkpoints, reported per Harness. Target ≥ 50% over the first 10 `claude` Runs; `codex` and `local` are reported without a target — local models are a cost lever, not a peer. Validates FR-10, FR-14, FR-16.
- **SM-2: Cold-reload time** — Operator time from opening a `needs-you` Run to submitting an Answer or Continue, measured as active time on the Run detail. Target ≤ 5 minutes median. Validates FR-18, FR-23.
- **SM-3: Cost and time per done Story, per Harness** — recorded for every Story step; no target; this is the comparison the three-harness design exists to produce. Validates FR-26, FR-28.

**Secondary**
- **SM-4: Recovery correctness** — Runs interrupted by restart that resume at the correct Step. Target 100% in the day-6 test and thereafter. Validates FR-12.
- **SM-5: Configuration-time failures** — share of credential/URL problems caught by the Clone check rather than by a Run. Target ≥ 90%. Validates FR-4.

**Counter-metrics (do not optimise)**
- **SM-C1: Verify steps `skipped`** — a rising share means Repositories are being onboarded without a quality command; SM-1 would look better while meaning less. Counterbalances SM-1.
- **SM-C2: Answers per Run** — a falling count driven by agents assuming instead of blocking is worse than a higher count; watch alongside post-merge defects. Counterbalances SM-1, SM-2.
- **SM-C3: Skipped Stories** — skipping raises completion; every skip is listed on the Run.

## 8. Open questions

**Resolved 2026-08-26.**
- ~~Does `claude -p --bare` keep the subagent tool, and does `--add-dir` load the Repository's skills under it?~~ **No to both.** `--bare` exposes `Bash, Edit, Read` only; neither `--add-dir` nor `--tools default` restores the subagent tool or `Write`. The Claude adapter uses default discovery with an explicit allowlist (FR-14).

**Open, blocking the build.**
1. What is the Claude tool allowlist (`CLAUDE_ALLOWED_TOOLS`) that lets `bmad-build-auto` reach `done` on a real Repository under `dontAsk`? The base set is `Task, Bash, Edit, Read, Write, Skill, ToolSearch`; the Bash patterns are repository-specific (uv, git, package manager, test runners). Day 3.
2. Trace continuity, per Harness, checked end to end on day 1 by the readiness run (FR-33): `claude` honours an inbound trace context (documented); `codex` honours it in source but not in its documentation — if it does not, the fallback is the Langfuse Codex plugin with a seeded, flat trace under the Run's session; `local` is session-only by design.
3. Do the skill stubs installed in the image resolve the Worktree (which carries `_bmad/`) as project root for each Harness, and do Codex and OpenCode subagents satisfy `bmad-build-auto`? The readiness run decides; fallback: the checkout Step copies the stubs into the Worktree's git-ignored skill folders.
4. Do the Gateway's spend identifiers (Attempt id) and Langfuse's session identifier (Run id) coexist on one call? The readiness run asserts both; fallback: drop the Gateway session field and sum spend by the `attempt:` tag.
5. Can a model-call-only Gateway key be issued on the host LiteLLM so that the key agents receive cannot read spend logs (FR-26)? Day 1, host configuration; fallback: keep one key and accept the exposure until the Gateway is reconfigured.

**Deferred — resolved from harness documentation at implementation time, not by local testing.** None blocks the architecture; each is confined to one adapter behind the FR-14 capability contract.
6. Codex: its exact `exec` / session-capture invocation and headless configuration. `codex` is a MUST for SM-3 but its technical detail is deliberately out of scope until the adapter is built.
7. OpenCode: its headless invocation, permission configuration, and how a Session id is obtained. Retained as the harness for open-weight models.
8. Local model serving on the Mac mini (a separate machine): model choice, runtime, and throughput. Decides whether `local` runs whole Stories or small ones. Out of scope for this PRD; `local` is already tiered SHOULD in §6.1.

## 9. Assumptions index
- §4.1 FR-1 — lockout: 5 failures / 15 minutes.
- §4.2 FR-4 — Clone check re-runs daily.
- §4.4 — every Spec folder listed in `epics.yaml` contains `SPEC.md` and `stories.yaml` produced by `bmad-spec`; `epics.md` is never read.
- §4.4 — one Repository per Run; multi-repository initiatives are split by the Operator.
- §4.4 FR-8 — list-file changes after planning are rare; a full re-plan of a queued Run is deferred.
- §4.4 FR-9 — Worktrees of terminal Runs are kept 7 days.
- §4.4 FR-10 — the implementation step reads the appended `## Verify Failure` section as part of the spec when re-entering at `in-progress`.
- §4.4 FR-12 — image upgrades drain running Runs, not parked ones.
- §4.6 FR-18 — the Answer as planning context resolves the intent gap on re-planning; SPEC.md gaps are fixed by editing SPEC.md.
- §4.6 FR-21 — resume-by-terminal detection is by polling the Worktree (Story file and `git status`).
- §4.7 FR-22 — `cancelled` Runs share the Failed column.
- §4.9 FR-26 — two instance Gateway keys: model-call (Harnesses) and spend-read (orchestrator).
- §4.9 FR-27 — span parenting differs per Harness; `local` has no inbound trace context.

## 10. Cross-cutting NFRs
- **NFR-1 Durability:** no completed Step is ever re-executed after a restart; a Run may park 30 days.
- **NFR-2 Honesty of status:** `skipped` and `unvalidated` are words, never green; no Step without a Gate strength renders as passed. Tested by a Template with a Step lacking `gate`.
- **NFR-3 Isolation:** agent processes run as a non-root user in the backend container; they receive exactly the declared environment contract (FR-14) — never `GITHUB_TOKEN`, never a direct provider key, never the orchestrator's own environment; a Run for Project A cannot read Project B's environment variables. Credentials are read once from the instance environment and stop at the process that needs them (AD-5).
- **NFR-4 Egress:** the container's outbound network is limited to the git host, package registries, the Gateway, Langfuse, and the host model server. In the MVP the allowlist is a documented host firewall rule, not enforced by the containers.
- **NFR-5 Observability:** every Step has a span; every model call has a Gateway spend log with Run tags.
- **NFR-6 UI:** desktop, ≥ 1280 px wide, single theme (dark), WCAG 2.2 AA contrast for primary and secondary text; status is always a word token, never colour alone; on any card or row exactly one element carries a signal colour (green running, amber needs you, red failed), and a screen with nothing needing the Operator has no amber or red pixel.
- **NFR-7 Build size:** the whole MVP is one Docker Compose file (web-client, backend-api, Postgres) with LiteLLM, Langfuse, and the model server already running on the host; `/work` and the Harness config/session directories are named volumes; every setting is an environment variable listed in one `.env.example` (AD-20); first run from clone in under 30 minutes on the Mac mini.
- **NFR-8 Voice:** product copy states facts and identifiers, never congratulates or apologises, and names the mechanism wherever an action changes a file or a branch ("archived to stories/.answers/…, story re-dispatched"). `skipped`, `unvalidated`, `blocked`, `exit 1` are words on the screen, not icons.
- **NFR-9 Buildability:** the repository is two components with one constitution each (`AGENTS.md`), strict layering enforced by a linter, a formatter and linter per stack, unit tests on shared fakes, and independent API and UI end-to-end suites, all from project setup (AD-2, AD-18); a step kind, a Harness, or the workflow engine can be replaced by adding one adapter without touching use cases (AD-6, AD-9, AD-10).

## 11. Constraints and guardrails
- **Safety:** agents never merge, never push to a default branch (FR-11); cancel deletes only branches the Run created and never pushed (FR-20).
- **Privacy:** prompt and tool content are redacted in Langfuse by default; enabling content logging is a per-Project switch (`log_prompt_content`, FR-2) that puts source code in Langfuse.
- **Cost:** per-Run budget with halt (FR-17) is the only enforcement in the MVP; per-Project spend is displayed (FR-28), not capped. Local model spend is recorded as $0 with tokens. The budget is a soft cap: an agent that calls the Gateway directly, without the attribution headers its Harness configuration sets, spends outside the halt; the container is the sandbox and the Gateway's own limits are the hard cap.
- **Anchors:** the spec, the epics file, every `AGENTS.md`, and existing tests are read-only to agents during a Run (FR-31); the Operator changes them on the branch, never the agent.

## 12. Platform
Web, desktop-first, single dark theme, one operator. Two containers on the Mac mini — the web client, and the backend with every Harness and the method pre-installed — plus Postgres; the Gateway, Langfuse, and the model server on the host (Docker on macOS has no GPU). Technology choices, the binding invariants, and the week plan: `addendum.md` and `architecture/ARCHITECTURE-SPINE.md`.
