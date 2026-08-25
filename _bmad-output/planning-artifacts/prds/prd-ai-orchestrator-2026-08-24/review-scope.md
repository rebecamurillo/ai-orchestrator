---
title: Scope & Buildability Review — AI Orchestrator PRD
reviewer: staff engineer (skeptical pass)
date: 2026-08-25
targets: prd.md (2026-08-24), addendum.md (2026-08-24)
verdict: Not minimal, not buildable as written. Roughly 3x the scope a one-engineer PoC can carry, and the load-bearing requirement (FR-28b) is one unspecified sentence.
---

# Scope & Buildability Review

Severity legend: **[CRITICAL]** blocks the build or invalidates the PoC's purpose · **[HIGH]** will cost weeks or force a redesign · **[MEDIUM]** will cause rework · **[LOW]** tidy-up.

Baseline observation: the repository contains `idea.md` and `_bmad-output/` and nothing else. This is greenfield. Every FR below is net-new code.

Requirement count: FR-1 through FR-52 plus lettered variants ≈ **75 discrete functional requirements**, 8 NFRs, 9 SEC items, 7 durability constraints, and a 7-item verification queue that is not scheduled. For one engineer, one operator, two repos.

---

## 1. Is this PoC actually minimal?

No. It is a platform PRD wearing a PoC label. §3 "Out of scope" cuts *categories* (multi-tenancy, visual editor, Mattermost) that were never going to be built anyway, while the in-scope list keeps every hard thing: a durable DSL interpreter with version pinning, sub-workflow references, a cross-machine session store, an AC→Playwright translation oracle, a prod-like test environment, a full web front-end, a Guacamole/SSH gateway, two harnesses, distributed tracing, and cost/budget enforcement.

The test for a PoC is: *what is the shortest path to one feature going spec → merged PR through the machine?* Everything not on that path is deferrable, because none of it produces evidence until the path works once.

### 1.1 Cut list — recommended, with evidence lost

**[CRITICAL] Cut Apache Guacamole entirely (§4, SEC-9, NFR-8, Addendum §B "Interactive session access").**
This is the single largest cut available. Guacamole is a separate stack — `guacd`, the client webapp, its own auth and datastore — plus an `sshd` inside the execution container, plus authentication, plus worktree scoping, plus the SEC-9 audit trail. The addendum already concedes it "is infrastructure the PoC's single-container assumption does not cover — it sits alongside, not inside," which means **NFR-1 is false at design time**. An sshd running in a container that SEC-3 wants read-only, non-root, `no-new-privileges` and cap-dropped is a fight you will lose or silently abandon.
*Replacement:* the orchestrator creates the session with a pre-assigned id (FR-21), then prints `claude --resume <id>` to the run view. The operator pastes it into their own terminal.
*Evidence lost:* the browser-chat UX only. **The invariant the PRD actually cares about — "orchestrator creates the session first, human resumes it, identity is never handed over after the fact" (§4) — is fully preserved.** Guacamole is a skin over that exact command. This is 2-3 weeks plus an ongoing security burden bought for zero PoC evidence.

**[HIGH] Cut Codex (FR-20, and the "more harnesses addable" abstraction).**
C-5 states the abstraction "leaks on day one": no defer round trip, no tracing exporter, unverified session paths. FR-31 and FR-43 are unsatisfiable for Codex. Building a capability-flag abstraction (`supports_defer`, `supports_native_tracing`, …) to serve one working harness and one degraded one is speculative generality.
*Evidence lost:* harness portability. You learn more from one harness driven well; the capability model can be inferred later from the seams the first integration leaves.

**[HIGH] Cut the review loop's session resumption (FR-19a, FR-19b, FR-19c) and, with it, FR-22.**
FR-19a ("resuming the existing harness sessions") is what forces FR-22 (Postgres-backed `sessionStore` adapter via the Agent SDK), which is a multi-day spike with a real chance of failing (C-4: "SessionKey.projectKey encodes the working directory"). And see §4.2 — FR-19a is *incompatible with FR-12c as written*, because the shaping session's cwd is the Phase A clone and the story worktrees are different directories.
*Replacement:* a G3 rejection starts a **cold** re-run of the affected stories with the rejection note and prior diff appended to the prompt.
*Evidence lost:* whether retained agent reasoning makes fix cycles cheaper. Real, but second-order — and you cannot measure it before you have baseline fix cycles to compare against. Defer to a spike after the first end-to-end run.

**[HIGH] Cut the bugfix variant (FR-11b, and the bugfix column of the §5 gate table).**
Two paths double the gate matrix, the template variants, the plan-generation branches, and the test surface, for a path you will exercise a handful of times. Worse, it has a hole (§4.1): bugfix skips architecture, but architecture is the step that produces the signed GWT `epics.md` — so the bugfix path has no defined source for the artifact that anchors the oracle.
*Evidence lost:* whether the short path is materially cheaper. Untestable at PoC volume anyway (n < 10).

**[HIGH] Cut multi-repo stories and multi-PR epics (FR-12d, FR-40a; trim FR-12b to the single target repo).**
§12.2 already recommends building nothing for cross-repository ownership. Yet FR-12b clones *every* repo in the project, FR-12c branches conditionally per repo, FR-12d splits stories per repo, and FR-40a bundles multiple PRs into one G3 unit — that is a coordination subsystem serving a case §12.2 says is invisible at one operator.
*Evidence lost:* multi-repo feature decomposition. Deliberately deferred by the PRD's own §12.2 reasoning; keeping it here contradicts that section.

**[MEDIUM] Cut `run.container` from FR-7's step types.** §3 puts multi-container execution out of scope and NFR-1 mandates one container. `run.container` requires docker-in-docker or socket mounting, which SEC-3 forbids in spirit. *Evidence lost: none.*

**[MEDIUM] Cut FR-38 (GitHub issue ingest).** Replace with a text field where the operator pastes the issue body and URL. *Evidence lost: none — the pipeline never learns anything from the ingest mechanism.*

**[MEDIUM] Cut FR-41 (report gate status onto the PR).** A link to the run view in the PR body (already required by FR-40) is sufficient at one operator. *Evidence lost: none.*

**[MEDIUM] Cut FR-16's failure taxonomy.** "Distinguish infrastructure failure (retry) from task failure (escalate)" is a classifier nobody has specified. Ship fixed retries on transport errors only; everything else escalates. *Evidence lost: retry-tuning data you have no volume to produce.*

**[MEDIUM] Cut FR-18 (cancel + rollback working branch).** `git worktree remove --force` plus a status flag. *Evidence lost: none.*

**[MEDIUM] Cut FR-45 (orchestrator-side budget enforcement).** LiteLLM virtual keys already carry `max_budget` / `budget_duration` (Addendum §C). Let the gateway 4xx and treat it as a step failure. Do not build a second enforcement point. Also see §3.9 — as written FR-45 is unimplementable anyway. *Evidence lost: none; the cap still holds.*

**[MEDIUM] Cut FR-27's `adversarial` tier.** No FR anywhere implements it — no refutation prompt, no success criterion, no behavior on refutation. It is a taxonomy entry with no code behind it. Collapse FR-27 to `validated` / `unvalidated` / `human`. *Evidence lost: none, because nothing consumes the tier today.*

**[MEDIUM] Cut FR-52's alerting.** Keep the recorded rejection counts; drop "alert on a sustained zero." At PoC volume (a handful of epics) a zero rejection rate is indistinguishable from noise, so the alert can only mislead. *Evidence lost: none — the instrument cannot fire meaningfully below n≈10.*

**[MEDIUM] Trim FR-2 to a directory of markdown files mounted into the workspace.** "Retrievable by agent tasks as prompt context" invites a retrieval subsystem. *Evidence lost: retrieval-quality data, which is not what this PoC is testing.*

**[LOW] Trim FR-33/34's "across projects."** One project in the PoC.

**[LOW] Trim SEC-4 (egress ipset allowlist) and SEC-3's read-only rootfs.** Keep non-root, keep no-new-privileges, keep SEC-1/2/7. The default-deny firewall is a day of work that becomes a week of debugging DNS and registry mirrors on a single operator's own machine.

### 1.2 The spine that remains

FR-1, 3, 3a, 5, 6, 7 (shell/script/agent/gate.human/sequence only), 7a, 7b, 8, 9, 11, 11a, 11c, 12a, 12b, 12c, 12e, 13, 14, 15, 17, 19, 20 (Claude Code only), 21, 23, 24, 25, 26, 28, 28a, 28b, 30, 32, 33, 34, 35, 36, 39, 40, 42, 43, 44, 47, 48, 50, 51.

That is ~44 requirements instead of ~75, and it still delivers everything in the user's stated PoC scope: onboarding, single login, optional per-repo commands, a chat with a BA/PM agent against a live orchestrator-owned harness session, a four-phase new-feature workflow, YAML workflows that reference other workflows, shell-or-agent instructions, and persisted session ids.

---

## 2. What is missing that would block a build

These are the day-three questions with no answer in either document.

**[CRITICAL] 2.1 — The DSL schema does not exist.**
FR-6 says workflows are YAML "with a documented schema." No FR defines a step's shape. Unanswerable on day three: How is a step's output named and referenced by a later step? What is the variable substitution syntax (FR-8)? What is a variable's scope — run, workflow, step? What happens on an unbound variable — hard fail, empty string, skip? How does a `gate.human` step declare what it is asking and what artifact it approves? How does `run.workflow` (FR-7a) declare its input binding and its return shape? What are a step's failure/retry/timeout declarations? Every one of these is a schema decision, and every one is load-bearing for FR-9 version pinning. **This is the first thing to write and it is entirely absent.**

**[CRITICAL] 2.2 — Loops are required and forbidden at the same time, with no mechanism.**
FR-11 binds "**loop counts**" as a variable. FR-11a says `epics` "loop over epics" and `stories` runs "development loop per story." FR-10 says the DSL has "**no user-authored loops**." There is no third construct named that would reconcile these. A developer needs to know: is iteration a built-in property of `run.workflow` (fan-out over a bound list), or a `foreach` step type, or does plan generation unroll the loop into N literal steps at G2? Each choice has different consequences for FR-9 pinning and for the DBOS determinism constraint. **Nothing in the PRD picks one.**

**[CRITICAL] 2.3 — The DBOS "cannot start or enqueue workflows from inside a step" constraint collides with FR-7a + FR-11, and nothing addresses it.**
The addendum lists this limitation and then never returns to it. But FR-11 generates the execution plan *during the run* (journey step 6), and FR-7a requires the parent workflow to invoke child workflows. Plan generation is a side effect (it reads session output, calls a model or a parser) and therefore must be a `@DBOS.step()` — from which child workflows cannot be started. The workaround (step returns the plan as data; the deterministic workflow body iterates it) is viable but has to be designed, and it constrains the DSL: the plan must be a serializable value under the pickle/1GB cap, and the loop must be deterministic on replay. **No FR names this. It will stop the build cold in week two.**

**[CRITICAL] 2.4 — No data model.**
Nothing names the entities or their identity. FR-21 requires persisting session ids "against the task, story, epic, and project," implying a four-level hierarchy that is never defined. FR-17 filters runs "by project, repository, status, and epic" — so a run has an epic FK, but §5 describes intake as a run that precedes any epic. FR-32 records a decision "against which artifact version" — artifacts have versions, but no FR creates, stores, or versions an artifact. A developer cannot write the first migration.

**[CRITICAL] 2.5 — The workspace/artifact contract is undefined, and the pieces that exist do not connect.**
FR-12b clones every repo at base branch **and installs dependencies**. FR-12c creates worktrees after G2. A `git worktree` is a *separate directory* with no `node_modules` / `.venv` / build cache — **nothing in the PRD reinstalls dependencies per worktree**, so FR-12e ("run the test suite after worktree creation") fails on a missing toolchain on the first attempt.
Compounding it: where does `epics.md` live? The shaping session runs in Phase A (FR-12b), at base branch, no branch created — so `epics.md` is an untracked file in a shared clone. FR-28a inspects "the working directory" (*which* one?). Story worktrees created in Phase B are different directories that do not contain it. **No FR moves, commits, or otherwise transports the signed artifact from Phase A to Phase B.** This is the single most concrete day-three blocker in the document.

**[HIGH] 2.6 — Rejection behavior is defined for exactly one gate.**
FR-19a defines what a G3 rejection does. **G1a, G1b and G2 have no defined rejection path.** Does rejecting G1a re-run the analyst session with feedback, park for a manual edit, or terminate the run? Does rejecting G2 regenerate the plan from the same artifacts, or send you back to G1b? FR-52 tracks "rejection rate per gate" for three gates whose rejection is unimplemented.

**[HIGH] 2.7 — Nothing provisions the test environment.**
Section F9 is titled "Test environment provisioning" and contains FR-47 (serialize), FR-48 (enforce), FR-49 (tear down). **There is no FR that creates the environment.** FR-29 requires "a prod-like environment with a real database" — who starts it, how is the schema migrated, how is it seeded, how does Playwright get its base URL, how is the app under test built and served? FR-49 tears down something nothing brings up. This is easily 2-4 weeks of work with no requirement behind it.

**[HIGH] 2.8 — FR-34 asks for information the design forbids collecting.**
FR-34 requires each inbox item to carry "what the agent has done so far." The only place that lives is the harness transcript, and C-4 says the format is "explicitly internal and liable to break on any release — **do not parse it**." FR-24's structured output schema has no field for work performed (`status`, `artifacts_written`, `open_questions`, `assumptions`). So either FR-24's schema grows a `work_summary` field, or FR-34 is unbuildable. Neither document notices.

**[HIGH] 2.9 — The front-end has no requirements.**
An Astro front-end is in the stack and the PRD depends on it (FR-12, FR-12a, FR-33 through FR-37, plus the G2 plan display in journey step 6). There is no FR for: the API contract, authentication mechanism for the single login (FR-4a says "one authenticated user" and stops), session handling, how the inbox updates (poll? SSE? manual refresh?), or how a long-running run's status is streamed. This is 3-4 weeks of work described in zero requirements.

**[HIGH] 2.10 — Schema-validation failure has no defined handling.**
FR-24 requires schema-validated structured output. What happens when an agent returns output that fails validation? It is neither "infrastructure failure (retry)" nor cleanly "task failure (escalate)" under FR-16. Retry the same prompt? Retry with the validation error appended? Count against FR-19's cap? Undefined, and it will happen on day one.

**[MEDIUM] 2.11 — Secrets have no storage requirement.**
FR-4 registers credentials; SEC-5 requires per-project scoping "enforced." No FR says where they are stored, whether they are encrypted at rest, what the encryption key's lifecycle is, or what mechanism enforces the scope boundary at agent-launch time.

**[MEDIUM] 2.12 — No model selection requirement.**
§2 wants cost "broken out per model so pipelines can be re-run across models for comparison later." No FR binds a model to a step, a task type, or a run. The comparison the metric exists for is not expressible.

**[MEDIUM] 2.13 — Commit granularity is unspecified.**
FR-39 says "create branches, commit, and push." Who runs `git add` — the agent or the orchestrator? One commit per story or per agent turn? What is the message format? Who resolves a dirty worktree left behind by a failed agent run?

**[MEDIUM] 2.14 — Artifact storage contradicts NFR-1.**
The addendum's DBOS notes say pickle with a 1GB field cap means "store artifacts in object storage, pass pointers." NFR-1 says one container plus Postgres. No object storage exists in the stack and no FR mentions it.

**[MEDIUM] 2.15 — Nothing reconciles the SSH session with the serialization lock.**
FR-47/48 serialize per worktree. SEC-9 says the SSH path "bypasses every workflow gate by construction." Does an interactive session take the lock? Can a human be shelled into a worktree while the orchestrator runs steps in it? NFR-8 says the activity is "traced like any other step" — by what mechanism, given it is a raw shell?

**[LOW] 2.16 — FR-5 is not checkable as stated.** "Declared commands exist" — there is no way to verify `pnpm test:e2e` exists short of running it, which has side effects.

---

## 3. Underspecified to the point of being unimplementable

**[CRITICAL] 3.1 — FR-28b, the load-bearing requirement of the entire product.**
> "**Translate signed Given/When/Then acceptance criteria into Playwright specs before any build step runs.** Report any acceptance criterion with no corresponding spec, and any spec with no corresponding criterion. The translation must be traceable back to the signed criteria."

Everything in this PRD rests on this sentence, and it is one sentence. Unanswered:
- **The app does not exist yet.** A Playwright spec needs routes, selectors, a login flow, seed fixtures, and a base URL. At the moment this step runs (before any build step), none of those exist. Either the spec is written against a UI contract that no FR requires anyone to produce, or the specs are written blind and immediately fail — in which case FR-12e's "known-clean starting point" and FR-29's "green E2E" are meaningless.
- **Bidirectional coverage matching needs stable identity.** "Any criterion with no corresponding spec" requires each GWT criterion to carry a durable id that survives into the TypeScript. No FR mandates one, and `bmad-create-epics-and-stories` output is prose.
- **The translator is an agent**, and FR-27 defines `deterministic-oracle` as a "test suite **the agent did not write**." See §4.5 — the oracle fails its own taxonomy.
- **"Traceable" is undefined.** A comment? A registry table? A naming convention? Verification-queue item 6 asks someone to confirm this works, but the requirement gives them nothing to confirm against.

**[CRITICAL] 3.2 — FR-30 escalates on essentially every task.**
> "**Escalate to a human when an agent returns non-empty `open_questions` OR non-empty `assumptions`**"

Every competent coding agent returns assumptions on every non-trivial task — that is what the field is for. As written, the escalation rate approaches 100%, which destroys §1's "hands it to the orchestrator and walks away" and makes the §2 target "Epics reaching human review without intervention ≥ 60%" **unreachable by construction**. There is no severity, confidence, threshold, or category concept anywhere. The intent (§12 / Addendum §E) is sound; the requirement as written is not implementable without inventing the missing filter.

**[HIGH] 3.3 — FR-22.**
> "Persist enough session state to **reconstruct or resume a session after container replacement**"

"Reconstruct **or** resume" are two different products. "Enough state" is undefined. C-4 says the only supported path is the SDK `sessionStore` adapter — but that lives in the addendum and no FR mandates driving the SDK rather than the CLI, which is a foundational architecture decision hidden in an appendix. C-4 also notes `SessionKey.projectKey` encodes the working directory, which FR-22 does not acknowledge.

**[HIGH] 3.4 — FR-19c states a problem and specifies no behavior.**
> "Check per-story state before resuming a review loop. A story whose PR already merged cannot simply be re-run; it needs a follow-up change, not a replay."

What does the orchestrator *do*? Create a new story? Escalate? Skip? Fail the epic? This is the most fragile branch in the system and the requirement is a sentence of analysis with no directive.

**[HIGH] 3.5 — FR-13's durability claim excludes the filesystem.**
> "a run survives process restart, container restart, and machine reboot without losing position or repeating completed steps"

DBOS durably records position in Postgres. The worktree, the installed dependencies, the untracked `epics.md` and the agent's partial edits live on a container filesystem, and **no FR or NFR requires a persistent volume**. Position without workspace is not resumption — the run resumes at step 14 into an empty directory.

**[MEDIUM] 3.6 — FR-2.** "Store per-project context artifacts … **retrievable by agent tasks as prompt context**." Retrievable by what — a mount, a tool call, prompt concatenation, embedding search? Four different builds, four different costs.

**[MEDIUM] 3.7 — FR-11.** "binding variables — target repository, per-repo commands, story list, **loop counts**" — see §2.2. Not implementable until the loop mechanism is chosen.

**[MEDIUM] 3.8 — FR-27's `adversarial` tier.** "an independent agent instructed to refute" — with what prompt, judged how, and with what consequence when it refutes? No implementing requirement exists.

**[MEDIUM] 3.9 — FR-45.** "Enforce a per-run and per-project budget; **halt** and escalate on breach." Spend is only known after the gateway reports it, which is after the tokens are spent. You cannot halt mid-turn. The enforcement point is unspecified and the only realistic one (the gateway's own `max_budget`) is in the addendum, not the FR.

**[LOW] 3.10 — NFR-5 sits exactly on the failure boundary.** "A workflow parked for **30 days** resumes correctly" against C-4's "default **30-day** retention." Zero margin, and the parenthetical "(Bounded by the session-retention constraint in §9)" acknowledges the NFR may be unsatisfiable while leaving the number at 30.

---

## 4. Internal contradictions

### 4.1 Gates (G1a / G1b / G2 / G3)

**[CRITICAL] §1 contradicts §5 on the product's core claim.** §1: the orchestrator "stops for a human only on two events: an **epic completing**, or a **story blocking**." §5: **four** human gates, three of which (G1a, G1b, G2) fire before the run starts, plus a human-triggered checkpoint validation (journey step 5) that is a fifth stop and is not counted as a gate. The one-sentence pitch describes a system with two interrupts; the requirements describe one with five. Both cannot brief the build.

**[HIGH] The bugfix path has no source for its signed artifact.** §5 (Q1, and "G1b carries the signature that anchors the oracle") makes the GWT criteria in `epics.md` the signed artifact. FR-11b: bugfix "**skips architecture and runs a single intake checkpoint**," and §5 says "intake produces stories directly." Architecture-and-epic-planning is the step that *produces* `epics.md`. So on the bugfix path the anchoring artifact is produced by a step that has been removed, and FR-28b has nothing to translate.

**[HIGH] G2 approves an artifact nothing persists.** FR-32 requires every gate decision recorded "against which **artifact version**." G2 approves a generated workflow instance (FR-11, FR-12a). No FR requires that instance to be stored or versioned — FR-9 versions the *template document*, and FR-11c explicitly says structure is never generated, so the instance is "just bindings." But the bindings (story list, target repos, AC set) are exactly what G2 is approving, and they are unversioned.

**[MEDIUM] Is a run per-feature or per-epic?** FR-7b pins referenced workflows "at the document version pinned by the **calling run**," implying one run spans intake → epics → stories. FR-17 filters "runs … by **epic**," implying runs are per-epic. FR-12a requires G2 approval "to **start** it," but D2 places G2 *inside* the `intake` template — so the run has already started. Three statements, three different run boundaries. This determines the entire DBOS workflow topology and must be settled before any code.

**[MEDIUM] G2's only preceding validation is a liveness check.** FR-28a's checkpoint validation confirms artifacts "exist and are well-formed" — which FR-27 classifies as `liveness` and FR-28 says "must **never** be presented as correctness." Yet journey steps 5-6 treat it as sufficient to generate the plan and open G2. Consistent with the letter of FR-28, contrary to its spirit, and worth an explicit `unvalidated` badge on the G2 screen.

### 4.2 Two-phase workspace (FR-12b / FR-12c)

**[CRITICAL] FR-19a is incompatible with FR-12c under C-4.** FR-19a resumes "the existing harness sessions" on a review loop. C-4: "The session key encodes the working directory, so the resuming host must match it." The shaping session runs in the Phase A clone (FR-12b, no branch); the story sessions run in Phase B worktrees (FR-12c, separate directories). Resuming a session from a different cwd than it was created in is exactly the case C-4 flags. Neither FR acknowledges the other.

**[CRITICAL] Dependencies are installed in the wrong directory.** FR-12b installs dependencies in the Phase A clone. FR-12c creates worktrees, which are fresh directories without them. FR-12e then runs the test suite in the worktree. Nothing installs. First run fails.

**[CRITICAL] The signed artifact has no route from Phase A to Phase B.** See §2.5. `epics.md` is written untracked into a base-branch clone and the story worktrees never see it.

**[HIGH] FR-12e contradicts FR-3a.** FR-12e: "Run the target repository's test suite … and fail the story early if it is already red." FR-3a: "Every command is optional. A repository may define none," and a skipped step "must render as `unvalidated`." On a repo with no `unit_test_command`, FR-12e's baseline is vacuous — and see §4.5, this cascades into FR-29 making the story's PR unopenable. A legal configuration produces a dead path nobody designed.

### 4.3 Serialization (FR-47 / FR-48)

**[CRITICAL] Serialization contradicts the product's stated value.** §1: the tool moves an engineer to specifying and verifying "**across several pipelines running in parallel**." FR-47: "Serialize execution per worktree… The PoC **iterates through epics sequentially**." Q7: "**no concurrency in the PoC**." Journey step 8 ("She switches to the other project") only works because there are *two projects*, not because pipelines run in parallel. The headline benefit is explicitly disabled by the requirements. This deserves an honest rewrite of §1, because it changes what the PoC can prove: it can show async hand-off, but not throughput.

**[HIGH] FR-47 states four different lock granularities in four sentences.** "per worktree" · "same repository branch" · "iterates through epics sequentially" · and FR-48's "share a worktree **or a database**." These are not the same lock. And since FR-29 requires "**a** real database" and the §6 callout says "two runs sharing a database produce failures that are neither reproducible nor real," **the effective lock is global**, not per-worktree — which makes the FR-47 parenthetical ("this is narrower than serializing per project") actively misleading. Pick one: a single global execution lease is the honest PoC answer.

**[HIGH] A parked run holds the lock forever.** FR-14 parks "**indefinitely** — days or weeks — without holding compute." It does hold the worktree, and under the global-DB reading it holds the entire pipeline. A story blocked on a question on Friday blocks every other epic until Monday. No FR releases or reacquires the lease across a park, and none defines what a queued second run does while waiting.

### 4.4 Review loops (FR-19a / 19b / 19c)

**[HIGH] FR-19b makes most G3 rejections unfixable.** FR-19 caps rework at 2 per story. FR-19b: "Review loops count against the FR-19 cap." A story that used both cycles during the build has **zero** budget when G3 rejects, so FR-36's "rejection creating a fix cycle bounded by FR-19" immediately escalates instead of fixing. Meanwhile §12/FR-52 wants a *healthy nonzero* G3 rejection rate. The design punishes the behavior it is trying to encourage. Fix: give review loops their own separate budget.

**[HIGH] FR-19a re-runs work that already shipped.** "A G3 rejection **re-runs the epic and its stories**." FR-19c then says a merged story must not be replayed. Under FR-42 the orchestrator never merges and G3 is the merge gate, so the only way a story is merged at rejection time is FR-40a's "merge order is the human's decision" — partial merges. So FR-19c's condition is real and reachable, and FR-19c specifies no behavior for it (§3.4). This is the most likely path to the orchestrator clobbering shipped work.

**[MEDIUM] Review-loop resumption collides with retention.** A G3 rejection arrives days or weeks later. NFR-5 wants 30-day parks; C-4's local retention default is 30 days; the durable store that would fix it (FR-22) is scoped only to "after container replacement," not to long parks.

### 4.5 Validation tiers (FR-27 / FR-28)

**[CRITICAL] The oracle fails the PRD's own definition.** FR-27: `deterministic-oracle` = "compiler, linter, test suite **the agent did not write**." FR-28b requires the orchestrator to *translate* signed criteria into Playwright specs — and the only mechanism available for translating prose GWT into TypeScript is an agent task. So the E2E suite **is** agent-written. §5 tries to rescue this with an *independence-by-timing* argument ("criteria signed before implementation cannot be a mirror of that implementation"), which is a good argument — but it is not what FR-27 says. FR-27's test is authorship, not timing. Either FR-27 is rewritten to define independence as *"derived from criteria signed before implementation, by a task that does not see the implementation,"* with a hard requirement that the translating agent and the implementing agent are separate sessions with separate context — or the product's central claim does not survive its own taxonomy.

**[HIGH] FR-3a + FR-28 + FR-29 create an unreachable state for a legal configuration.** FR-3a permits a repo with no commands at all. FR-29 requires "green Playwright E2E … **before any PR is offered for human review**." If `e2e_command` is undefined, FR-3a says the step is skipped and renders `unvalidated`, FR-28 says `unvalidated` is never green, so FR-29 can never be satisfied and **no PR can ever be opened for that repo**. Nothing in the PRD says what happens; a developer will either quietly treat skipped as passed (violating FR-3a's explicit prohibition) or ship a system that deadlocks on a supported configuration.

**[HIGH] `unvalidated` has no propagation rule.** FR-40 opens a PR "when an epic's workflow completes with **all gates satisfied**." Is an `unvalidated` gate satisfied? Does one `unvalidated` story block the epic, or surface as a warning at G3? This decides whether FR-28 is a real constraint or a badge.

### 4.6 Other contradictions

**[HIGH] NFR-1 is already false.** "**Single** Docker container for the PoC" versus §4's Guacamole (addendum: "sits alongside, not inside"), plus LiteLLM (requires its own Postgres), plus Langfuse, plus the FR-29 prod-like test environment with its own database. The real deployment is 5-6 services. Say so, because it changes the ops story and NFR-2's "must not change shape when moving to multiple containers."

**[HIGH] The dogfood target fails the admission criterion.** §3: "the change must be *fast to verify* — its acceptance criteria expressible as **Playwright assertions**." The primary dogfood repo is `ai-orchestrator` itself, whose core correctness properties — durable resume across restart (FR-13), document version pinning (FR-9), serialization (FR-47), session persistence (FR-21) — are precisely the things **not** expressible as browser assertions. §11 hand-waves this ("E2E for both the Python backend and the Astro front-end are built during bootstrapping"). Either the admission criterion is broader than Playwright, or the dogfood repo is mostly inadmissible to its own pipeline.

**[MEDIUM] §3 in-scope contradicts C-5.** In-scope: "non-interactive agent task execution against Claude Code **and Codex**." C-5: the abstraction "leaks on day one," Codex has no defer and no tracing exporter. FR-43 (single trace) and FR-31 (defer) are unsatisfiable for Codex, and only FR-31 carries a fallback clause.

**[MEDIUM] SEC-3 versus the SSH surface.** SEC-3 wants "read-only root filesystem where possible, non-root user"; SEC-9 requires an interactive shell into that same container. An sshd, a writable home, a shell history, and a `--read-only` rootfs do not coexist without exceptions nobody has enumerated.

**[LOW] FR-7's `run.container` versus §3 and NFR-1.** Already noted in §1.1.

---

## 5. The single biggest risk

**[CRITICAL] You will spend six to ten months building a platform before producing the one piece of evidence the project exists to obtain — and the instrument that would produce it is the least specified requirement in the document.**

§12.1 is admirably honest: the central question is *"is this better than doing it myself?"*, the primary metrics do not answer it, and the failure mode the design is most exposed to (a gate degrading into a rubber stamp) *improves* both primary metrics while quality drops. The PRD's response is three cheap instruments (FR-50/51/52). But:

1. **The instruments need volume the design cannot produce.** FR-47/48 serialize everything, one operator drives all gates, and every task escalates under FR-30 as written. A PoC of this shape yields maybe 5-15 completed epics. FR-52 ("alert on a sustained zero rejection rate") and the ≥60%/≥70% supporting metrics are not measurable at that n.
2. **The one honest baseline is a hard sequencing dependency and it is not scheduled.** Verification-queue item 7: "Establish a manual baseline on two or three comparable features — **before** the pipeline exists, or the 'better than by hand' question can never be answered honestly." Nothing in §5, §6, or the metrics section reserves time for it. If the build starts first, that answer is permanently unavailable.
3. **The load-bearing plank is a single sentence.** If FR-28b's AC→Playwright translation does not work — and there is good reason to doubt it works against an application that does not exist yet — then FR-29's green E2E is theatre, FR-27's tiers collapse to `liveness`, the "admission criterion" (§3) has nothing to admit against, and every other requirement is scaffolding around a hole. §12.4 already concedes "a good result does not generalize"; the sharper risk is that there is no result at all.
4. **Seven of the addendum's own verification items can invalidate the design**, and none has an owner, a timebox, or an FR: Guacamole session resume, the defer-hook round trip, TRACEPARENT survival through LiteLLM, DBOS `recv_async` across a multi-day restart, version pinning against a mid-flight YAML change, AC→Playwright traceability, and the manual baseline.

**Mitigation, and it is the main recommendation of this review:** invert the order. Spend **two weeks** on the verification queue (items 2, 3, 4, 5, 6) plus item 7's manual baseline, as throwaway spikes with no product code. Then build the §1.2 spine to a **single hardcoded happy path** — one repo, one epic, one story, one gate, real Playwright — and only then generalize. If FR-28b fails the spike, you have lost two weeks instead of six months, and you still know something true.

---

## 6. Effort sanity check

One engineer, greenfield, sustained focus. Ranges are optimistic-to-realistic for working, debugged code — not demo code.

### 6.1 Full PRD as written

| Cluster | FRs | Estimate |
|---|---|---|
| DSL schema, interpreter, version pinning, sub-workflow refs, variable binding, plan generation | FR-6…FR-12a | **4–6 wks** |
| DBOS durable execution, gates, park/resume, retry, cancel, query, rework caps, review loops | FR-13…FR-19c | **3–5 wks** (FR-19a-c is a long tail) |
| Harness integration: SDK driving, pre-assigned ids, structured-output schemas, resume, defer hook, Postgres sessionStore, Codex parity | FR-20…FR-26, C-4, C-5 | **4–6 wks** |
| Workspace, git, worktrees, dependency install, branches, PRs, issue ingest | FR-12b…FR-12e, FR-38…FR-42 | **2–3 wks** |
| **Oracle + test environment**: AC→Playwright translation, traceability, prod-like env with real DB, provisioning, serialization, teardown | FR-27…FR-29, FR-28b, FR-47…FR-49 | **5–9 wks**, widest variance |
| Astro front-end: inbox, run view, workflow view, gate UIs, plan approval, auth, live updates | FR-12, 12a, 33…37 | **3–4 wks** |
| Guacamole + SSH + auth + worktree scoping + audit | §4, SEC-9, NFR-8 | **2–3 wks** |
| Observability + cost: LiteLLM, Langfuse, traceparent, per-entity attribution, budgets, metrics | FR-43…46, 50…52, C-6, C-7 | **2–3 wks** |
| Security hardening | SEC-1…9, NFR-3/4 | **1–2 wks** |
| Onboarding, data model, migrations, secrets storage | FR-1…FR-5, FR-4a | **1–2 wks** |
| Bootstrapping `ai-orchestrator`'s own unit + E2E suites (Q6 — prerequisite for dogfooding) | — | **2–3 wks** |

Sum of focused work: **29–46 weeks.** Add integration, and add the specific tax of durable-workflow development — DBOS determinism violations "surface at *recovery*, not at write time," so a class of bugs is only reproducible by killing the process mid-run. Add the six unresolved design questions in §2 that must be answered before the first migration.

**Honest range for the full FR set: 8–12 months.** The document reads as though it is describing a 2-3 month effort. It is not.

### 6.2 The cut scope (§1.2 spine)

- Verification spikes + manual baseline: **2 wks**
- First end-to-end run, one repo / one story / hardcoded happy path: **5–7 wks** from spike completion
- Defensible PoC on the spine — real templates, review loop (cold), inbox, tracing, cost: **11–15 wks total**

### 6.3 What dominates

Four clusters are ~70% of the estimate:

1. **Oracle + test environment (5–9 wks)** — the largest, the least specified, and the one that can silently consume the whole schedule. FR-28b alone deserves a spike before anything else is built.
2. **Harness session durability (4–6 wks)** — the Postgres `sessionStore` adapter and the defer-hook round trip are each multi-day spikes against interfaces the addendum flags as unstable ("verify before relying on any specific flag or path").
3. **DSL + durable engine (7–11 wks combined)** — inflated well beyond its natural size by FR-9 version pinning, FR-7b pinned sub-workflow resolution, and the unaddressed DBOS "cannot start workflows from a step" collision (§2.3).
4. **Front-end (3–4 wks)** — currently specified by zero requirements, so this number is the least trustworthy on the list.

Cutting Guacamole, Codex, the bugfix variant, multi-repo, and session-resuming review loops removes roughly **10–14 weeks** without removing a single piece of evidence the PoC needs.

---

## Summary of critical findings

| # | Finding | Severity |
|---|---|---|
| 1 | FR-28b — the oracle, on which everything rests — is one unspecified sentence, and targets an app that does not exist when it runs | CRITICAL |
| 2 | FR-27's authorship-based `deterministic-oracle` definition disqualifies the agent-written Playwright suite; the central claim fails its own taxonomy | CRITICAL |
| 3 | Phase A / Phase B workspace split has no path for `epics.md`, no per-worktree dependency install, and breaks FR-19a's session resume under C-4 | CRITICAL |
| 4 | §1's "several pipelines running in parallel" is contradicted by FR-47/48 and Q7; the effective lock is global, not per-worktree | CRITICAL |
| 5 | FR-30 escalates on non-empty `assumptions`, i.e. ~always — making the ≥60% no-intervention target unreachable and the "walk away" premise false | CRITICAL |
| 6 | No DSL schema, no data model, no loop construct, and an unaddressed DBOS "cannot start workflows from a step" collision | CRITICAL |
| 7 | Six-to-ten months of platform before the first piece of evidence; verification queue unscheduled; manual baseline (item 7) is a one-way door | CRITICAL |
| 8 | §1 promises two human interrupts; §5 specifies five | CRITICAL |
| 9 | FR-3a + FR-28 + FR-29 deadlock a legal repo configuration — no PR can ever be opened | HIGH |
| 10 | FR-19b spends the rework budget before G3 can ever use it; FR-19c specifies no behavior on its own most dangerous case | HIGH |
| 11 | No FR provisions the test environment that FR-49 tears down and FR-29 depends on | HIGH |
| 12 | FR-34 requires agent progress context that C-4 forbids reading and FR-24's schema does not carry | HIGH |
| 13 | The Astro front-end has zero requirements | HIGH |
| 14 | NFR-1's "single container" is already false (Guacamole, LiteLLM+PG, Langfuse, test DB) | HIGH |
| 15 | The dogfood repo's core correctness is not expressible as Playwright assertions, failing the §3 admission criterion | HIGH |
| 16 | G1a/G1b/G2 have no defined rejection behavior, while FR-52 measures their rejection rate | HIGH |
| 17 | FR-13's durability covers position but not the workspace; no persistent volume is required | HIGH |
