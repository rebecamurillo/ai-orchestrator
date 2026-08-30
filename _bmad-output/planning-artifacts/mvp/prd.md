---
title: AI Orchestrator MVP — dev loop
status: final
created: 2026-08-26
updated: 2026-08-28
supersedes-for-mvp: ../prds/prd-ai-orchestrator-2026-08-24/prd.md (the long-term product PRD; not replaced)
inputs:
  - ../v1-dev-loop-2026-08-26/challenge-v1.md
  - ../v1-dev-loop-2026-08-26/architecture-v1.md
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/screens/ (nine artboards)
  - ../ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md (visual system, unchanged)
---

# PRD: AI Orchestrator MVP — dev loop

## 0. Document purpose

This PRD is the build contract for the **MVP** of `ai-orchestrator`: the version to be built in the week of 2026-08-27 → 2026-09-02 and used from day 8. It is written for the operator who will also build it, for `bmad-architecture` (solutioning), and for `bmad-create-epics-and-stories`. It builds on three inputs it does not restate: the v1 challenge (why this scope), the v1 architecture (how — technology choices live there and in `addendum.md`), and the v1 experience spec with its nine screens (what it looks like). Vocabulary is anchored in §3; features are grouped in §4 with globally numbered FRs; inferences are tagged `[ASSUMPTION]` inline and indexed in §9.

The long-term product PRD of 2026-08-24 remains the description of where this goes (intake, executable specs, gates). This document narrows to what ships first and is deliberately silent on the rest.

## 1. Vision

A senior engineer writes the spec — `SPEC.md`, `stories.yaml`, an epics file — on a working branch, points the orchestrator at it, and walks away. The orchestrator checks the branch out in a worktree, confirms the repository is green, then dispatches each story to a coding agent in unattended mode; the agent plans, implements, reviews, and commits; the orchestrator verifies the committed result with the repository's own quality gate and moves to the next story. It stops only where the spec author declared a checkpoint or where an agent could not proceed without a human. When it stops, one screen shows what it needs; when it finishes, the branch is pushed and a link to the pull request is waiting.

The MVP is a **dispatcher and a readout**, not an autonomous engineer. Its value is that a story-sized unit of work runs to a verified commit without anyone watching, across any of three agent harnesses — Claude Code, Codex, or a local open-weight model — with every model call routed through one gateway and every run visible as one trace with one cost. It moves the engineer's time from typing implementations to writing stories and answering the occasional question.

It exists now because the pieces already exist: the BMAD `bmad-build-auto` skill implements a story unattended and reports its outcome in the story file; `stories.yaml` already carries the checkpoint fields a dispatcher needs; DBOS gives durable, restartable workflows on Postgres alone; and the three harnesses all run headless. The MVP wires them together and puts one honest screen in front.

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

- **UJ-1. Rebeca sets up a project and finds out the token is wrong before it matters.** Rebeca, the sole operator, logs in with the access token and creates project *Website*: context text, two repositories with their `quality_gate_command`, a GitHub token. She saves. The clone check runs per repository; the second one fails with the verbatim `fatal: Authentication failed` and a one-line fix. The form keeps every value; she fixes the token's repository access, saves again, both repositories read `ok`. **Edge case:** a repository with no quality command saves fine and is marked *verify step will be skipped* on its row.

- **UJ-2. Rebeca starts an epic and walks away.** Working branch `feat/notifications-mm` already holds `specs/notifications/{SPEC.md, stories.yaml, epics.md}`. From the board she opens *New workflow*, picks template `dev-loop` v3, project, repository, base `main`, the working branch, the spec folder, the stories file, harness `claude`, a $40 budget, and types "6" into *manual estimate*. Pre-flight reads eight stories, warns that story 4-2 has a spec checkpoint, everything else `ok`. She clicks *Start run*. The card appears in **Running** with `checkout`, then `baseline`, then `story 1-1 · build · claude`. She closes the laptop. **Edge case:** the repository is already held by another run — the card appears in **Queued** with "waiting: repository lock held by feat/saved-views".

- **UJ-3. Two days later, one card is amber.** Rebeca opens the board: one card in **Needs you**, `BLK · story 4-1 · intent gap · 2d 04h`. She opens it. The question is at the top: SPEC.md CAP-3 says a Mattermost message is posted on block but not to which channel. Below it the *Answer* box. She types "Post to the project's channel only; no direct message in this story" and clicks *Resume with answer*. The blocked story file is archived with her answer, the story is re-dispatched with the answer as planning context; the card is back in **Running** within the next poll. Twenty minutes later story 4-1 is done; at story 4-2 the run pauses at the spec checkpoint, she reads the planned story spec inline, clicks *Continue*. By evening the card is in **Done** with `8/8 stories · pushed · PR #52`. **Edge case:** the verify step fails twice on story 4-3 — the card goes amber with the failing command's output; she chooses *Skip story* or *Cancel run*.

## 3. Glossary

- **Operator** — the single authenticated human. Owns every decision the system asks for.
- **Project** — a named unit of context: context text, context file paths, credentials, and one or more Repositories. Scopes secrets and the Gateway key.
- **Repository** — a git remote registered under a Project with a default branch, package manager, and optional `quality_gate_command` / `unit_test_command`. Subject of the **Clone check**.
- **Clone check** — the validation run when a Repository is saved: `git ls-remote`, shallow clone, default branch exists. Result is `ok` or a failure with verbatim git output.
- **Template** — an authored YAML workflow definition with typed **Inputs** and ordered **Steps**. Has a name and an integer **Version**; a Version is immutable once any Run pins it.
- **Run** — an instance of one Template Version bound to Inputs (Project, Repository, base branch, **Working branch**, **Spec folder**, stories file, epics file, **Harness**, model, budget). Has exactly one **Status**. One Run targets exactly one Repository.
- **Step** — one node of a Template, executed within a Run; typed `git.worktree | shell | agent | git.commit | git.push`. Has a **Gate strength** and a **Step status**. An `agent` Step inside the Story loop is a **Story step**.
- **Gate strength** — what a green Step status means: `liveness` (an artifact exists and parses), `deterministic` (a command exited 0), `human` (the Operator decided). A Step with no oracle is `unvalidated`, never green.
- **Spec folder** — the path, relative to the Repository root on the Working branch, that holds `SPEC.md`, `stories.yaml`, optional `epics.md`, and `stories/`. It is the **Artifact destination**: agents write there and the Run commits it.
- **Story** — one entry of `stories.yaml`: `id`, `title`, `description`, optional `spec_checkpoint`, `done_checkpoint`, `invoke_dev_with`. Executed in list order.
- **Story file** — `{Spec folder}/stories/{id}-*.md`, written by the agent; its frontmatter `status` (`draft | ready-for-dev | in-progress | in-review | blocked | done`) and `## Auto Run Result` section are the **Agent contract**.
- **Harness** — a coding-agent CLI the orchestrator drives headlessly: `claude` (Claude Code), `codex` (Codex CLI), `local` (OpenCode over a local model). Each has a **Session id** per Story step.
- **Gateway** — the LiteLLM proxy every model call passes through; issues one virtual key per Project and attributes spend per Run.
- **Trace** — the Langfuse trace for a Run; orchestrator spans and Harness/Gateway generations share the Run's id.
- **Checkpoint** — a human pause declared in a Story: *spec checkpoint* (after planning, before implementation) or *done checkpoint* (after the Story's commit-guard Step).
- **Needs you** — the Run Status column and rail count grouping every Run whose next action is the Operator's (the stops listed in §4.6).
- **Question** — the text shown to the Operator for a `blocked` Story: the whole `## Auto Run Result` section of the Story file (status, blocking condition, and any listed questions and evidence), attributed to Harness, model, and time.
- **Attempt** — one execution of a Step; a Step may have several Attempts (retry, re-dispatch after an Answer, re-run after interruption); the Steps table shows the latest and counts the rest.
- **Answer** — Operator text resolving a `blocked` Story; the mechanism (archive the blocked Story file, re-dispatch with the Answer as planning context) is FR-18.
- **Gate record** — append-only list per Run of Operator decisions and machine stops: time, Step, event (`start | blocked | checkpoint | timeout | budget | answer | continue | skip | retry | cancel | budget-raise`), text.
- **Status** — Run: `queued | running | needs-you | done | failed | cancelled`. Step: `queued | running | done | blocked | checkpoint | error | skipped`. Tokens: Run `QUE RUN DON ERR CAN`, with `needs-you` rendered as `BLK` (blocked, verify failed, budget, timeout) or `CHK` (Checkpoint); Step `QUE RUN DON BLK CHK ERR SKP`. `CAN` is Run-only.
- **Board** — the home screen: Runs as cards in five Status columns.
- **Worktree** — the git worktree at `/work/{project}/{repo}/wt/{working branch}` where a Run executes.

## 4. Features

### 4.1 Access
**Description:** one Operator, one secret. The login screen takes the access token from the server environment; a session cookie lasts 30 days. Nothing else is on that screen. Realizes UJ-1.

#### FR-1: Token login
The Operator can authenticate by entering the access token; every `/api/*` call requires the resulting session.
**Consequences (testable):**
- A correct token sets an HttpOnly cookie valid 30 days and redirects to the Board.
- A wrong token returns the login screen with the line `token rejected — n attempts left`; after 5 failures within 15 minutes the endpoint refuses for 15 minutes. `[ASSUMPTION: lockout numbers]`
- An unauthenticated `/api/*` request returns 401; an unauthenticated page load redirects to `/login`.

### 4.2 Projects and Repositories
**Description:** a Project carries the context every agent reads before a Story, its credentials, and its Repositories. Saving a Repository runs the Clone check so a bad token or URL fails at configuration time, not hours into a Run. Realizes UJ-1.

#### FR-2: Create and edit a Project
The Operator can create a Project with name, context text, optional context file paths, a GitHub token, and agent environment variables.
**Consequences (testable):**
- Context text and context file paths are stored and delivered to every Story step as `project-context.md` (FR-15).
- The GitHub token is stored encrypted at rest and is returned by API responses after save only masked to its last four characters.
- Environment variables are exported into every Step of that Project's Runs and into no other Project's Runs.
- A per-Project switch `log_prompt_content` (default off) controls whether prompt and tool content reach Langfuse; the Project screen states that enabling it sends source code to Langfuse.

#### FR-3: Register a Repository with commands
The Operator can add a Repository to a Project with URL, default branch, package manager, and optional `install_command`, `quality_gate_command`, and `unit_test_command`.
**Consequences (testable):**
- A Repository without `quality_gate_command` saves successfully and its row states `verify step will be skipped`.
- The default branch must exist on the remote (checked by FR-4) or the save is refused with the reason.

#### FR-4: Clone check on save
The system runs the Clone check for every Repository when the Project is saved and reports the result of each check.
**Consequences (testable):**
- Checks: `git ls-remote` succeeds; shallow clone into `/work/{project}/{repo}/base` succeeds; default branch exists. Each reports `ok` with duration, or the verbatim command output.
- One failing Repository blocks the save; the form retains every entered value.
- The check re-runs daily; a failure sets the Repository's status to `failed` and blocks **new** Runs on that Repository only. `[ASSUMPTION: daily re-check cadence]`

### 4.3 Templates
**Description:** a Template is versioned YAML with typed Inputs and Steps. The Operator edits the YAML in the browser; a diagram is rendered from the parsed YAML beside it; saving creates the next Version. The MVP ships one Template, `dev-loop`. Realizes UJ-2.

#### FR-5: Template schema and validation
The system accepts Templates conforming to the MVP schema (Inputs of type `project | repository | string | path | enum | number`; Steps of type `git.worktree | shell | agent | git.commit | git.push`; one `for_each` construct over a YAML list file; `{{variable}}` substitution only) and rejects anything else.
**Consequences (testable):**
- *Validate* returns every error with line and reason: unknown key, unbound variable, unknown Step type, nested `for_each`, expression syntax.
- No loop other than `for_each`, no conditionals, no string functions are accepted.
- Every Step declares a Gate strength or the validator reports it as `unvalidated`.

#### FR-6: Immutable Versions
The Operator can save an edited Template, which creates Version n+1; a Version pinned by any Run cannot be modified or deleted.
**Consequences (testable):**
- Saving never changes the YAML of an existing Version; the versions list shows how many Runs pin each.
- A Run started under Version n still resolves Version n after Version n+1 exists.

#### FR-7: Rendered diagram
The system renders a read-only diagram from the parsed YAML: one node per Step (type, name, Gate strength), `for_each` as a group, agent Steps and human gates visually distinguished.
**Consequences (testable):**
- The diagram updates on every successful validation of the editor content; invalid YAML leaves the last valid diagram with a stated error.
- No node can be dragged, added, or edited in the diagram.

### 4.4 Runs and the dev loop
**Description:** a Run binds Inputs to a Template Version and executes durably. The `dev-loop` Template: checkout → baseline → for each Story {build → verify → commit-guard} → push. The agent commits its own work before it exits (`bmad-build-auto` finalises with a clean tree); the orchestrator verifies the committed tree and only commits what the agent left behind. Runs survive process restarts and resume at the last completed Step. `[ASSUMPTION: the Spec folder always contains SPEC.md and stories.yaml as produced by bmad-spec; epics.md is optional context]` `[ASSUMPTION: one Repository per Run; an epic spanning repositories is split by the Operator into one Run per Repository]` Realizes UJ-2, UJ-3.

#### FR-8: Start a Run with pre-flight
The Operator can create a Run by choosing a Template Version, Project, Repository, base branch, Working branch, Spec folder, stories file, optional epics file, Harness, optional model, budget, and optional manual estimate; pre-flight runs on every field change.
**Consequences (testable):**
- Pre-flight reports:
  - origin reachable;
  - base branch exists;
  - Working branch exists (will check out) or not (will create);
  - `stories.yaml` parses with N Stories and ids of which none is a prefix of another (so `{id}-*` globs are unambiguous);
  - declared Checkpoints (warning);
  - `SPEC.md` found; epics file found if given;
  - Harness available with a Gateway key for the Project;
  - `_bmad/scripts/render_skill.py` and the `bmad-build-auto` skill directory the chosen Harness reads (`.claude/skills` for `claude`, `.agents/skills` for `codex` and `local`) present on the Working branch;
  - existing `stories/*.md` files listed with their statuses.
- Any failing check disables *Start run* and states the fix; warnings never block.
- The manual estimate, if given, is stored on the Run before any Step executes and cannot be edited afterwards.
- The screen shows *What will run*: the Template's Steps with the Story loop expanded to the parsed Story count, before the Operator starts anything.
- *Start run* enqueues the Run; the response states whether it starts now or queues behind a named Run.

#### FR-9: Checkout and baseline
The Run creates a Worktree on the Working branch (from the base branch when the Working branch does not exist) and runs the Repository's `quality_gate_command` before any Story.
**Consequences (testable):**
- The Worktree path is `/work/{project}/{repo}/wt/{working branch}` and appears in the Run header.
- When the Repository declares `install_command`, checkout runs it in the Worktree before baseline (recorded as its own `shell` Step); when absent the Step is `skipped`.
- A non-zero baseline exit sets the Run to `failed` with the command output attached and no Story step started; spend is $0.
- A Repository without `quality_gate_command` records the baseline Step as `skipped`.
- An existing Worktree for the Working branch is reused when `git status --porcelain` is empty; otherwise the Run refuses to start with the reason. Worktrees of Runs in a terminal Status are removed 7 days later; base clones are kept. `[ASSUMPTION: 7-day worktree retention]`

#### FR-10: Story loop
The Run executes Stories in `stories.yaml` list order; for each: a Story step (FR-14), a verify Step, a commit-guard Step.
**Consequences (testable):**
- The Story list is read once at Run start and never re-read during the Run.
- A Story whose file already reads `done` at Run start is recorded `already done` and not dispatched, unless the Operator enabled *re-review done Stories* at start.
- verify runs `quality_gate_command` in the Worktree on the tree the agent committed. On exit ≠ 0 the orchestrator appends a `## Verify Failure` section (command, exit code, last 200 lines) to the Story file, sets its status to `in-progress` (which routes the agent straight to implementation), and re-dispatches once. A second failure sets the Run to `needs-you` with reason `verify failed 2/2`. `[ASSUMPTION: the implementation step reads the appended Verify Failure section as part of the spec]`
- commit-guard adds anything the agent left uncommitted (the Spec folder staged before the rest of the tree) with message `story {id}: {title} (orchestrator)`; a clean tree commits nothing and records `no changes` — the normal case.
- Every Step has a maximum wall-clock time, declarable in the Template (`timeout_min`), defaulting to 90 for Story steps, 30 for `shell`, 5 for `git.*`; on expiry the process is killed, the Step is `error`, and the Run is `needs-you` with reason `timeout {step} after {n} min`.

#### FR-11: Push and finish
After the last Story the Run pushes the Working branch to origin and records a pull-request link.
**Consequences (testable):**
- Push supplies the Project's GitHub token to each git command individually; the token never appears in the environment of any agent process.
- The push Step refuses when Working branch equals the Repository default branch.
- A rejected push (remote diverged, permission) sets the Run to `needs-you` with reason `push rejected` and the git output; Retry re-runs the push after the Operator resolves it. The orchestrator never force-pushes.
- The PR link is the GitHub compare URL for `{default branch}...{Working branch}`; the Operator opens the pull request. `[NON-GOAL for MVP: creating the pull request]` When a Story was skipped, the Run summary lists it beside the link.
- Run Status becomes `done`; the card shows `n/n stories · pushed · PR`.

#### FR-12: Durability and recovery
Runs survive orchestrator restart and container replacement without repeating completed Steps.
**Consequences (testable):**
- Killing the process during any Step and restarting resumes the Run at that Step; completed Steps are not re-executed.
- An interrupted Story step re-runs as a new Attempt with a new Session id; the agent resumes from the Story file's own status.
- Before every Story step Attempt the orchestrator commits any uncommitted changes in the Worktree as `wip: story {id} attempt {n} (interrupted)`, because the agent refuses to start on a dirty tree.
- Every Harness process runs in its own process group whose id is recorded on the Attempt; a re-attempt first terminates the recorded group (TERM, then KILL) and waits for `.git/index.lock` to disappear. Test: kill the orchestrator mid-Story, restart — exactly one Harness process for that Run exists afterwards.
- The checkout Step is idempotent: a Worktree that exists on the right branch is reused; a missing one is recreated; `/work` and the Harness session directories are persistent volumes.
- A Run parked in `needs-you` for 30 days resumes correctly on Answer or Continue.

#### FR-13: Concurrency and repository lock
The system runs at most one active Run per Repository and at most two active Runs overall; further Runs queue in order.
**Consequences (testable):**
- Two Runs on the same Repository: the second shows `queued` with `waiting: repository lock held by {run}` until the first reaches a terminal Status. A `needs-you` Run **holds** its lock — the pre-flight and the queue row say so — because two Runs must never share a Repository's worktrees (mechanism: addendum §D).
- Runs on different Repositories execute concurrently up to two.
- The Runs screen shows queue position and the waiting reason.

### 4.5 Story steps and Harnesses
**Description:** a Story step invokes `bmad-build-auto` in folder+id dispatch through the chosen Harness, in the Worktree, with the Project context prepended and `invoke_dev_with` appended. The Harness is irrelevant to the outcome contract: the Story file is the result. Realizes UJ-2, UJ-3.

#### FR-14: Dispatch a Story to a Harness
The system runs a Story step by launching the Harness headlessly in the Worktree with a prompt that names the skill, Spec folder, and Story id, plus `invoke_dev_with`, plus "Halt after planning." when `spec_checkpoint` is true — and nothing else, so the skill's intent detection is not disturbed.
**Consequences (testable):**
- The Harness runs non-interactively in the Worktree with approvals pre-granted, and must expose to the skill **a subagent-spawning tool, file read and write, and shell**. `bmad-build-auto` HALTs `blocked · no subagents` without the first, so a Harness mode that hides it is unusable. *(Confirmed against Claude Code 2.1.246: `--bare` exposes only `Bash, Edit, Read` — no subagent tool, no `Write` — and neither `--add-dir` nor `--tools default` restores them. The Claude adapter therefore uses default discovery with an explicit allowlist, not `--bare`.)*
- The Repository's `bmad-build-auto` skill directory is discoverable by the Harness from the Worktree; a Harness that cannot see it fails pre-flight (FR-8), not the Run.
- A Session id is recorded for every Attempt: pre-assigned where the Harness supports it, otherwise captured from the Harness's own output or session store.
- **The exact CLI invocation per Harness is not fixed here.** It is resolved from each Harness's current documentation at implementation time and recorded in `addendum.md` §B, because these CLIs change between releases.
- Every shipped Harness completes one trivial Story to `done` on a test Repository before it is offered in New workflow; this exercises `bmad-build-auto`'s mandatory subagents.
- A Harness process receives no credential other than the Project's Gateway virtual key: never the GitHub token, never a direct provider key. It receives the Gateway base URL, the Project's environment variables, trace headers, and the Harness's own configuration.
- The Step records Harness, model, Session id, exit code, wall-clock time, tokens in/out, cost.

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
  - any other status, or a Harness exit code ≠ 0 with a `done` file → Step `error`, Run `needs-you` with reason `unexpected status: {status}` / `harness exit {code}`.
- The Step's Gate strength is recorded as `liveness`; the UI never renders a Story step green on its own — only the following verify Step (deterministic) or its `skipped` word.

#### FR-17: Budget halt
The system halts a Run whose spend exceeds its budget.
**Consequences (testable):**
- After every Story step Attempt (when the Harness process exits, before the verify Step), spend for the Run is summed from Gateway spend logs by Run tag; if spend > budget the Run becomes `needs-you` with reason `budget {spent} / {budget}` and no further Harness process is started.
- The Operator can raise the budget on the Run and Continue, or Cancel.

### 4.6 Human gates
**Description:** the Run stops for the Operator only for: agent `blocked`, Checkpoint, verify failed twice, budget halt, Step timeout, push rejected, and the configuration failures listed in FR-16 — and every stop offers the same small set of actions on the Run detail (Answer, Continue, Skip, Retry, Cancel; FR-18..FR-20). Realizes UJ-3.

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
- spec checkpoint: Continue re-dispatches the Story with its file at `ready-for-dev`, which the agent implements without re-planning; the Operator may edit the Story file inline before Continue. *Reject with a reason* uses the Answer mechanism (FR-18): the planned file is archived and the Story re-planned with the reason.
- done checkpoint: the pause is applied by the orchestrator after the commit-guard Step, from `stories.yaml`, not from the Story file; Continue starts the next Story.
- Both write a gate record entry.

#### FR-20: Skip a Story, retry a Step, cancel a Run
The Operator can skip the current Story (marking it `skipped` and proceeding), retry the current failed Step, or cancel the Run.
**Consequences (testable):**
- Skip first runs the commit-guard (`story {id}: skipped by operator`) so the next Story starts on a clean tree, then re-runs `quality_gate_command` as a re-baseline; if that exits non-zero the Run stays `needs-you` with reason `re-baseline failed after skip`. Any commits the agent already made stay on the branch; the Run summary and PR link list the skipped Story.
- Retry is offered on a `needs-you` Run whose current Step is `error` (timeout, harness exit, push rejected); it re-executes only that Step as a new Attempt. `failed` Runs are terminal — the Operator starts a new Run. Retrying a Story step whose file is already `done` starts the agent's review pass, not a re-implementation.
- Cancel requires a confirmation; it terminates any Harness process group of the Run, then stops the Run, removes the Worktree, and deletes the Working branch only if this Run created it and it was never pushed. Status `cancelled`.

#### FR-21: Terminal resume command
For Harnesses that support it, the Run detail shows the exact command to resume the Story's session in a terminal, with the remaining session lifetime.
**Consequences (testable):**
- `claude` and `codex` Story steps show a copyable command that execs into the orchestrator container (`docker compose exec orchestrator …`) with Worktree path and Session id, because sessions live in the container; `local` shows none. Remaining session lifetime is shown for `claude` (30 days from the Attempt start, per its documented retention) and omitted for `codex`.
- Copy confirms in place (`COPIED`, ~1.2 s); the string never soft-wraps.
- Copying the command marks the Run `terminal session in progress`; Answer, Continue, Skip, and Retry are disabled until the Operator clicks *Release* or the Story completes as below.
- While a terminal session is in progress and the Run is `needs-you`, the server polls the Worktree every 30 s. When two consecutive polls find the Story file `done` and the Worktree clean (`git status --porcelain` empty, no `.git/index.lock`), the Run resumes at verify without an Answer. `[ASSUMPTION: resume-by-terminal detection by polling the Worktree]`

### 4.7 Board and Run detail
**Description:** the Board is home; five Status columns; a card states the Run's Working branch, Project · Repository, current or last Step, Story progress, Template Version, and age. The Run detail is the only place decisions are made. Colour rules: NFR-6; visual rules in `EXPERIENCE-v1.md` and `DESIGN.md`. Realizes UJ-2, UJ-3.

#### FR-22: Board
The Operator can see every Run as a card in the column of its Status, filtered by Project, with a LIST alternative.
**Consequences (testable):**
- Columns `Queued · Running · Needs you · Done · Failed` always render, empty ones with `—` and count 0. `cancelled` Runs appear under Failed with the word `cancelled`. `[ASSUMPTION: cancelled Runs share the Failed column]`
- With no Runs at all the Board reads `NOTHING RUNNING` and lists what is queued; with no Project registered it reads `NOTHING REGISTERED` and links to Projects.
- The rail shows `n need you` in amber only when n > 0; the footer shows running/queued counts and the last update time.
- A wait longer than 48 h renders its age in amber.
- Cards are not draggable; the whole card opens the Run detail.

#### FR-23: Run detail
The Operator can open a Run and see, in a detail view or a diagram view (FR-29): header (Status, branch, meta line with Project, Repository, base, Spec folder, Template Version, Harness, start time, Worktree), an alert banner when the Run is `needs-you` or `failed`, the Question and Answer (FR-18), the resume command (FR-21), the Steps table (`# · step · type · gate · status · time · harness · cost`), the Stories strip, the Spec folder file tree with an inline file viewer, cost and Trace link, and the gate record.
**Consequences (testable):**
- The meta line is never truncated or collapsed.
- The Steps table prints Gate strength per row and the words `skipped` / `unvalidated` where applicable, never a green token for them.
- The file tree marks files changed since the Operator last opened this Run.
- The cost block prints `spent / budget` as a ratio, tokens in/out, wall-clock time, active Operator time in this Run, and a link to the Trace. Active time is the sum of intervals during which the Run detail tab is focused, excluding idle gaps longer than 5 minutes.

#### FR-24: Refresh model
The Board and Run detail poll: every 5 s while any Run is `running`, else every 30 s; the footer prints the last update.
**Consequences (testable):**
- No content moves under the cursor: updates apply as a state swap without animation.
- A failed fetch renders a full-surface readout with the failed request and a retry control.

#### FR-29: Run diagram
The Operator can switch the Run detail to a diagram view: the Run's Template rendered as a left-to-right tree — Run → Steps → the story loop expanded to one node per Story, grouped by epic — with every node carrying its Step status token, so the whole Run reads from start to finish: what ran, where it is, what is scheduled.
**Consequences (testable):**
- The diagram is produced by the same renderer as the Template diagram (FR-7), fed with the Run's pinned Template Version and its Step statuses; a Template with no Run renders identically minus tokens.
- The story loop expands to one node per Story in `stories.yaml` order; Stories are grouped under an epic node by the story-id prefix (`3-2` → epic 3); ids without a prefix form a single group.
- Each node shows its token (`QUE RUN BLK CHK ERR DON SKP`); a Story node also shows its three sub-steps (build · verify · commit-guard) as words, never as a second coloured mark. The current node is promoted to primary text and labelled `now`; scheduled nodes read `QUE`. No node carries more than one signal colour.
- Clicking a node scrolls the detail view to that Step's row; the diagram and the Steps table are two views of the same data and never disagree.
- The diagram is read-only and refreshes on the same poll as the Run detail (FR-24).

### 4.8 Runs screen
**Description:** every Step of every Run, newest first, plus the queue as the engine sees it. Realizes UJ-2 (edge case).

#### FR-25: Queue and history
The Operator can see the queue (position, Run, next Step, waiting reason, waiting time) and paginated Step history (time, Project, Run, Step, type, Harness, Status, duration, cost, Trace link), filtered by Project and Status.
**Consequences (testable):**
- The queue is read from the engine's queued workflows, not from a separate table.
- A `needs-you` Run appears in the queue section with position `—` and reason `waiting for your answer`.
- History rows link to the Run detail.

### 4.9 Observability and cost
**Description:** one Trace per Run; every model call through the Gateway; cost attributable to Run, Story, Harness, and Project.

#### FR-26: Gateway routing
Every model call from every Harness passes through the Gateway with the Project's virtual key and Run tags.
**Consequences (testable):**
- A Harness process with the Gateway unreachable fails its Step with `error` (credential rule: FR-14, NFR-3).
- Gateway spend logs carry tags `run:{id}`, `story:{id}`, `harness:{name}`, `project:{name}`.

#### FR-27: One Trace per Run
The system creates a Trace per Run and attaches orchestrator Step spans; Harness and Gateway generations join by the Run's trace id or session id.
**Consequences (testable):**
- The Run detail's Trace link opens a Langfuse view containing, at minimum, every Step span and every Gateway generation for the Run.
- For `claude`, harness spans are children of the Run trace; for `codex` and `local`, generations carry the Run id as Langfuse session id. `[ASSUMPTION: span parenting differs per Harness]`

#### FR-28: Cost per Step
Every Story step records tokens in/out and cost from Gateway spend, per model.
**Consequences (testable):**
- Run cost = sum of Step costs; shown on the card summary and Run detail; per-Project monthly spend shown on the Project.
- Gateway spend logs are the authoritative figure; harness-reported usage is shown as provisional until the Gateway figure for the Step is available.

## 5. Non-goals (explicit)
- The orchestrator does not write specs, epics, or stories, and does not ingest issues. The human authors the Spec folder.
- It does not generate or run end-to-end tests, provision test environments, or judge acceptance criteria. The only oracle is the Repository's own commands.
- It never merges, never pushes to a default branch, never force-pushes.
- It is not a visual workflow editor; the diagram is read-only.
- It is not multi-user, has no roles, and no notification channel outside the UI.
- It is not a harness: it does not implement code itself, only dispatches to Claude Code, Codex, or OpenCode.
- It does not resume or replay harness sessions across containers; session content is harness-local and may be lost.

## 6. MVP scope

### 6.1 In scope
Token login · Projects with context, credentials, Repositories and Clone check · one Template (`dev-loop`) with editable versioned YAML and rendered diagram · Runs with pre-flight, durable execution, repository lock, checkpoints, blocked-answer, skip/retry/cancel, budget halt, Step timeouts · three Harnesses (`claude`, `codex`, `local`) through LiteLLM · one Langfuse Trace per Run with per-Step cost · Board, Run detail (+ diagram view), Runs, Projects, Templates screens in the instrument-dark visual system (`DESIGN.md`).

**Definition of done for the MVP.** `claude` is required. `codex` is required, because SM-3 exists to compare Harnesses. `local` ships if the deferred OpenCode and Mac mini questions (§8) resolve in time; otherwise the fallback in `addendum.md` §C (Codex CLI pointed at the Gateway for local models) satisfies the MVP.

**Tiers.** MUST: FR-1 (without lockout), FR-2, FR-3, FR-4 (on save), FR-5, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14 (`claude`, `codex`), FR-15..FR-20, FR-22 (board), FR-23 (header, alert, Question/Answer, Steps, Stories, cost), FR-24, FR-25 (queue), FR-26..FR-28. SHOULD: FR-6 (save as new Version), FR-7 (diagram), FR-14 `local`, FR-21, FR-23 artifacts tree and active time, FR-25 history, FR-29 (Run diagram — shares FR-7's renderer, so it rides on FR-7). COULD: FR-1 lockout, FR-4 daily re-check, FR-22 LIST view, FR-23 changed-since-last-opened marks, FR-28 per-Project monthly figure.

**Slips first, in order:** the `local` adapter, in-browser Template editing, Runs history pagination, cancel rollback of the branch.

### 6.2 Out of scope for MVP
- Intake and spec generation (long-term PRD M2). Deferred.
- Executable-spec oracle (Playwright from criteria, test-id contract, G2/G3 gates). Deferred to the long-term PRD.
- Multi-repository Runs — one Run, one Repository. `[NOTE FOR PM]` this is the first thing an epic spanning front-end and back-end will hit; the workaround is two Runs, one per Repository.
- Mattermost or any notification outside the Board. Deferred.
- Second container / multi-machine execution. The architecture does not change shape; deferred until one container is saturated.
- Session-store based resume across containers. Deferred; the Answer path does not need it.
- The verdict metric dashboard (manual estimate ÷ actual). The manual estimate field is captured now because it cannot be retrofitted; the dashboard is deferred.
- `unit_test_command` and `package manager` as consumed fields (`install_command` is consumed by checkout). Both stored for later Templates, unused in `dev-loop` v3. `[NOTE FOR PM]` cheap to add as a Step once the loop is proven.

## 7. Success metrics

**Primary**
- **SM-1: Unattended completion rate** — share of Runs that reach `done` without any human action other than declared Checkpoints, reported per Harness. Target ≥ 50% over the first 10 `claude` Runs; `codex` and `local` are reported without a target — local models are a cost lever, not a peer. Validates FR-10, FR-14, FR-16.
- **SM-2: Cold-reload time** — Operator time from opening a `needs-you` Run to submitting an Answer or Continue, measured as active time on the Run detail. Target ≤ 5 minutes median. Validates FR-18, FR-23.
- **SM-3: Cost and time per done Story, per Harness** — recorded for every Story step; no target; this is the comparison the three-harness design exists to produce. Validates FR-26, FR-28.

**Secondary**
- **SM-4: Recovery correctness** — Runs interrupted by restart that resume at the correct Step. Target 100% in the day-6 test and thereafter. Validates FR-12.
- **SM-5: Configuration-time failures** — share of credential/URL problems caught by the Clone check rather than by a Run. Target ≥ 90%. Validates FR-4.

**Counter-metrics (do not optimize)**
- **SM-C1: Verify steps `skipped`** — a rising share means Repositories are being onboarded without a quality command; SM-1 would look better while meaning less. Counterbalances SM-1.
- **SM-C2: Answers per Run** — a falling count driven by agents assuming instead of blocking is worse than a higher count; watch alongside post-merge defects. Counterbalances SM-1, SM-2.
- **SM-C3: Skipped Stories** — skipping raises completion; every skip is listed on the Run.

## 8. Open questions

**Resolved 2026-08-26.**
- ~~Does `claude -p --bare` keep the subagent tool, and does `--add-dir` load the Repository's skills under it?~~ **No to both.** `--bare` exposes `Bash, Edit, Read` only; neither `--add-dir` nor `--tools default` restores the subagent tool or `Write`. The Claude adapter uses default discovery with an explicit allowlist (FR-14).

**Open, blocking the build.**
1. What is the Claude tool allowlist that lets `bmad-build-auto` reach `done` on a real Repository under `dontAsk`? The base set is `Task, Bash, Edit, Read, Write, Skill, ToolSearch`; the Bash patterns are repository-specific (uv, git, package manager, test runners). Day 3.
2. Does `TRACEPARENT` survive Claude Code → Gateway → Langfuse as one Trace, and do non-Claude generations land under the Run's session id via the Gateway's Langfuse callback? Day 1.

**Deferred — resolved from harness documentation at implementation time, not by local testing.** None blocks the architecture; each is confined to one adapter behind the FR-14 capability contract.
3. Codex: whether its subagent support satisfies `bmad-build-auto`, and its exact `exec` / session-capture invocation. `codex` is a MUST for SM-3 but its technical detail is deliberately out of scope until the adapter is built.
4. OpenCode: its headless invocation, permission configuration, and how a Session id is obtained. Retained as the harness for open-weight models.
5. Local model serving on the Mac mini (a separate machine): model choice, runtime, and throughput. Decides whether `local` runs whole Stories or small ones. Out of scope for this PRD; `local` is already tiered SHOULD in §6.1.

## 9. Assumptions index
- §4.1 FR-1 — lockout: 5 failures / 15 minutes.
- §4.2 FR-4 — Clone check re-runs daily.
- §4.4 — the Spec folder always contains `SPEC.md` and `stories.yaml` produced by `bmad-spec`; `epics.md` is optional context.
- §4.4 — one Repository per Run; multi-repository epics are split by the Operator.
- §4.4 FR-9 — Worktrees of terminal Runs are kept 7 days.
- §4.4 FR-10 — the implementation step reads the appended `## Verify Failure` section as part of the spec when re-entering at `in-progress`.
- §4.6 FR-18 — the Answer as planning context resolves the intent gap on re-planning; SPEC.md gaps are fixed by editing SPEC.md.
- §4.6 FR-21 — resume-by-terminal detection is by polling the Worktree (Story file and `git status`).
- §4.7 FR-22 — `cancelled` Runs share the Failed column.
- §4.9 FR-27 — span parenting differs per Harness.

## 10. Cross-cutting NFRs
- **NFR-1 Durability:** no completed Step is ever re-executed after a restart; a Run may park 30 days.
- **NFR-2 Honesty of status:** `skipped` and `unvalidated` are words, never green; no Step without a Gate strength renders as passed. Tested by a Template with a Step lacking `gate`.
- **NFR-3 Isolation:** agent processes run as a non-root user in the orchestrator container; they hold no GitHub token and no direct provider key; a Run for Project A cannot read Project B's environment variables or key.
- **NFR-4 Egress:** the container's outbound network is limited to the git host, package registries, the Gateway, Langfuse, and the host model server.
- **NFR-5 Observability:** every Step has a span; every model call has a Gateway spend log with Run tags.
- **NFR-6 UI:** desktop, ≥ 1280 px wide, single theme (dark), WCAG 2.2 AA contrast for primary and secondary text; status is always a word token, never colour alone; on any card or row exactly one element carries a signal colour (green running, amber needs you, red failed), and a screen with nothing needing the Operator has no amber or red pixel.
- **NFR-7 Build size:** the whole MVP is one docker-compose file (orchestrator, Postgres, LiteLLM, Langfuse) plus the host model server; `/work` and the Harness config/session directories are named volumes; first run from clone in under 30 minutes on the Mac mini.
- **NFR-8 Voice:** product copy states facts and identifiers, never congratulates or apologises, and names the mechanism wherever an action changes a file or a branch ("archived to stories/.answers/…, story re-dispatched"). `skipped`, `unvalidated`, `blocked`, `exit 1` are words on the screen, not icons.

## 11. Constraints and guardrails
- **Safety:** agents never merge, never push to a default branch (FR-11); cancel deletes only branches the Run created and never pushed (FR-20).
- **Privacy:** prompt and tool content are redacted in Langfuse by default; enabling content logging is a per-Project switch (`log_prompt_content`, FR-2) that puts source code in Langfuse.
- **Cost:** per-Run budget with halt (FR-17) is the only enforcement in the MVP; per-Project spend is displayed (FR-28), not capped. Local model spend is recorded as $0 with tokens.

## 12. Platform
Web, desktop-first, single dark theme, one operator. Backend and tooling in one container on the Mac mini; model server on the host (Docker on macOS has no GPU). Technology choices and the week plan: `addendum.md` and `../v1-dev-loop-2026-08-26/architecture-v1.md`.
