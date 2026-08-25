---
title: AI Orchestrator — PRD
status: final
created: 2026-08-24
updated: 2026-08-25
---

# AI Orchestrator — PRD

## 1. What this is

An **asynchronous specification-and-verification cockpit** for agent-driven software delivery.

One engineer shapes a feature with AI assistance until acceptance criteria are agreed, hands it to the orchestrator, and goes to do something else. The orchestrator runs a durable workflow per epic and story — deterministic steps (git, tests, quality commands) interleaved with non-interactive agent tasks — and stops for a human only when an **epic completes** or a **story blocks**. The human returns, answers or validates, and the workflow resumes.

The product moves a senior engineer from *writing* implementations to *specifying and verifying* them.

> **On parallelism.** The long-term value is several pipelines advancing while one human's attention moves between them. **The PoC does not deliver this** — execution is serialized (FR-47), so a run parked at a gate blocks the queue. The PoC proves the *loop*; parallelism is what the loop is worth once it works. Velocity figures from the PoC therefore include queue time and must not be read as throughput.

**Rejected framings** (`_bmad-output/forge/agent-workflow-os/forged-idea.md`): not an OS, not an autonomous SWE agent, not a general workflow platform.

## 2. Milestones

Reviewers estimated the full requirement set at 8–12 months for one engineer. The response is not to cut quality but to **order the work by risk** — everything unproven lives in the story loop, and the front half of the pipeline is mostly orchestrating a session the operator already runs by hand today.

| | Milestone | What it proves | FRs |
|---|---|---|---|
| **M1** | **Prove the loop** | Machine builds, human validates, and it is worth it. Fed a **hand-authored `epics.md`**; runs epic → story → PR. One repository (the fullstack app, which already has a Playwright suite). One harness (Claude Code). | M1-tagged |
| **M2** | **Close the front** | The intake half: analyst/PM session, architecture and epic planning, checkpoint validation, G1a/G1b, and the full review inbox. | M2-tagged |
| **M3** | **Deferred** | Guacamole web chat, Codex, the bugfix variant, multi-repo stories, session-resuming review loops, multi-container execution. | M3-tagged |

**M1 deliberately skips intake.** Its output is a file the operator can write by hand, so building it first would delay every risky question. M1 answers the questions that decide the project; M2 makes it pleasant.

*FR ids are stable across milestones. Gaps in the sequence are cut requirements, retained so review findings stay traceable.*

## 3. Goals and success metrics

**Primary metrics.**

| Metric | Unit | Why |
|---|---|---|
| **Token cost per issue / repo / project** | cost + raw tokens, per model | What a delivered change costs. Broken out per model so pipelines can be re-run across models for comparison later. |
| **Velocity, spec → PR merged** | wall-clock, start/end timestamps | End-to-end duration including parked and queued time. *Under M1 serialization this includes queue time — see §1.* |

**The verdict metric.** `estimated_manual_minutes ÷ actual_human_minutes` (FR-50, FR-51).

**Pre-registered thresholds** — declared now, before any data exists, because deciding them afterwards is the contamination FR-50 exists to prevent:

| Ratio over 10 consecutive merged epics | Verdict |
|---|---|
| **≥ 2.0** | The concept works. Proceed to M2. |
| **1.3 – 2.0** | Marginal. Continue only with a named hypothesis for what would move it. |
| **< 1.3** | **Kill.** A senior engineer is faster by hand, and no amount of scaling changes that. |

**Supporting metrics.**

| Metric | Target |
|---|---|
| Epics reaching human review without intervention | ≥ 60% |
| Blocked-step resumes that succeed on first human answer | ≥ 70% |
| Rework cycles per story | tracked; the FR-19 cap is 2, so a story hitting the cap is a failure signal |

**Counter-metrics** — what reveals a primary metric being gamed:

| Counter-metric | Watch for |
|---|---|
| **Gate rejection rate** | **A gate with a 0% rejection rate is not a gate.** Alert on a sustained zero. |
| **Active time inside each gate** | Falling time = a gate degrading into a rubber stamp |
| Post-merge defect rate | Velocity bought by degraded review |
| Reopened / reverted PRs | Wrong-but-plausible work reaching main |
| Token cost per *merged* PR | Cheap runs that never ship |

> Token cost and velocity measure the *machine*. Neither can detect the failure this design is most exposed to — a gate that stays green while becoming ceremony. That is what the counter-metrics are for.

## 4. Scope

**Admission criterion: the change must be *fast to verify*** — its acceptance criteria expressible as Playwright assertions against named test-ids (FR-28b). Work that cannot be verified deterministically does not enter the pipeline. **Enforced at G1b (M2) and by hand-authored input in M1** (FR-24a).

### In scope
Project and repository onboarding with per-repo commands; single login; versioned YAML workflow templates composed by reference; durable execution with human gates; non-interactive agent tasks with session ids persisted in Postgres; deterministic step execution; output validation; a review inbox; blocked-step escalation and resume; GitHub issue ingest and PR creation; Playwright E2E as the correctness oracle; per-run tracing and cost attribution.

### Out of scope, with reasons
- **An Open Workflow Specification interpreter.** The spec (renamed from CNCF Serverless Workflow, now v1.0.3) has **no Python runtime** — the official `sdk-python` is a validator pinned to spec 0.8, last released April 2022. Borrow its task vocabulary; do not take the dependency.
- **A visual workflow editor.** Workflows are edited as YAML in git. Kestra's editor is not embeddable and its Human Tasks are Enterprise-only.
- **Guacamole web chat (M3).** Replaced for the PoC by the orchestrator **printing the exact `--resume` command** for the operator to run in their own terminal (FR-23a). The orchestrator-owns-session-identity invariant is fully preserved, and weeks of infrastructure are not built.
- **Codex and multi-harness support (M3).** One harness until the loop works. The capability model (FR-20a) keeps the seam.
- **The bugfix variant (M3).** One intake path.
- **Multi-repo stories and multi-PR epics (M3).** One story, one repository, one PR.
- **Session-resuming review loops (M3).** A G3 rejection opens a **new** session — restoring the upstream locked decision.
- **Multi-tenancy, RBAC, SSO.** Single operator.
- **Mattermost notification.** UI first.
- **Multi-container execution.** One container; constraints in §8 understood before scaling.

## 5. Primary journey

**Rebeca, sole operator.** M1 runs against the fullstack app, which already has a Playwright suite. `ai-orchestrator` itself is dogfooded once its own suites exist.

**M1 — the loop**

1. She authors `epics.md` by hand: epics, stories, and Given/When/Then acceptance criteria. **Each criterion names the stable test-ids and routes it touches** (FR-24a). Each story targets exactly one repository.
2. She points the orchestrator at it. The orchestrator validates the file and generates an execution plan — an epic instance looping over story instances — and **generates the Playwright specs** from the acceptance criteria.
3. The front-end displays **the plan and the generated specs together**. She approves both. **G2.** The run starts; tracking begins here.
4. The orchestrator creates a branch and worktree in the target repository, installs dependencies, and runs the quality gate to confirm a clean starting point.
5. She goes to do something else.
6. A story blocks. The workflow parks. Her inbox shows the question, the story, its criteria, what the agent has done, and **the exact command to resume the session in her terminal**.
7. She answers in her terminal. The orchestrator detects the session's completion and resumes the workflow.
8. The epic completes. Her inbox shows a PR with a green quality gate and green Playwright E2E against a real database. She runs the feature herself, then merges — or rejects, which opens a fix cycle in a **new** session.

**M2 adds the front:** steps 1 and 2 become an analyst/PM session (**G1a**), then architecture and epic planning (**G1b**), then checkpoint validation — all reached through a harness session the orchestrator creates and the operator resumes.

### Human gates

| Gate | When | What is approved | M1 |
|---|---|---|---|
| **G1a — Intent** | After the analyst/PM session | The spec for the change | M2 |
| **G1b — Acceptance** | After architecture and epic planning | Epics, stories, and the Given/When/Then criteria **with test-ids** | hand-authored |
| **G2 — Plan and spec** | After validation | The execution plan **and the generated Playwright specs** | ✓ |
| **G3 — Delivery** | After the epic completes | The running feature, then merge | ✓ |

**G2 carries the executable-spec signature.** A human sees and approves the generated Playwright specs *before* anything implements against them — which is what makes the oracle independent, and what the prose-only acceptance signature failed to deliver.

> **Deviation from stock BMad, deliberate.** `bmad-qa-generate-e2e-tests` is a ship-phase skill running *after* `bmad-build`, generating tests "for implemented code" — an oracle derived from the implementation. **The orchestrator generates Playwright specs from signed criteria before any build step runs.** The stock skill's role shrinks to backfilling regression coverage.

## 6. Features and functional requirements

Each FR is tagged **[M1]**, **[M2]**, or **[M3]**.

### F1 — Onboarding
- **FR-1** **[M1]** Register a project with strategy and business context, and one or more GitHub repositories.
- **FR-2** **[M1]** Store per-project context artifacts (architecture notes, domain glossary) retrievable by agent tasks as prompt context.
- **FR-3** **[M1]** Store a per-repository command set, **all optional**, bound into workflow templates at run time:

  | Variable | Purpose |
  |---|---|
  | `unit_test_command` | Run unit tests |
  | `code_quality_command` | Lint, format, type-check |
  | `e2e_command` | Run the Playwright suite |
  | `quality_gate_command` | Composite — runs all of the above |

  Plus package manager and default branch.
- **FR-3a** **[M1]** Commands are optional and a step bound to an undefined command is **skipped and recorded as skipped** — never failed, never reported as passed. A skipped check is an absent check and renders as `unvalidated` (FR-28).
- **FR-3b** **[M1]** **A repository without an `e2e_command` cannot run the epic workflow.** The Playwright oracle is mandatory to open a PR (FR-29), so onboarding must reject such a repository for pipeline use rather than let a run discover it at the end. *(This is why M1 targets the fullstack app: `ai-orchestrator` becomes eligible only once its own suite exists.)*
- **FR-4** **[M1]** Register per-project credentials — GitHub token and agent environment variables — scoped per project and shared across that project's repositories.
- **FR-4a** **[M1]** **Single login.** One authenticated user with access to everything. No roles. *(Distinct from SEC-5: secrets are scoped per project because that boundary constrains the **agent**, not the human.)*
- **FR-5** **[M1]** Validate a repository on save — clone succeeds, declared commands exist and exit cleanly — and report failures at onboarding rather than hours into a run.

### F2 — Workflow definitions
- **FR-6** **[M1]** Define workflows as YAML under version control, with a documented schema.
- **FR-7** **[M1]** Step types: `run.shell`, `run.script`, `run.agent`, `run.container`, `run.workflow`, `gate.human`, plus `sequence` / `parallel`. Each instruction is either a command-line invocation running a script — validating a BMad step's agent output, running a repository quality command — or an agent trigger against a harness. Nothing more expressive.
- **FR-7a** **[M1]** **A workflow can reference another workflow.** `epics` references `stories`; in M2 `new-feature` references `epics`. Referenced workflows receive bound inputs and return their outcome.
- **FR-7b** **[M1]** Resolve a referenced workflow at the document version pinned by the calling run (FR-9), so a template edited mid-flight cannot change a run under way.
- **FR-8** **[M1]** Per-run variable substitution from repository commands (FR-3), so one template serves many repositories.
- **FR-9** **[M1]** **Version every workflow document explicitly and pin each run to the version it started under.** Highest-severity durability requirement — §8, C-1.
- **FR-10** **[M1]** The DSL is **not Turing-complete**: no user-authored loops, no expression language, no string manipulation.
- **FR-11** **[M1]** Generate a workflow **instance** by binding variables — target repository, commands, story list, loop counts — to an authored **template**.
- **FR-11a** Template library, versioned in git and composed by reference:

  | Template | Phases | References | Milestone |
  |---|---|---|---|
  | **`stories`** | development loop per story | — | **M1** |
  | **`epics`** | loop over epics and their stories | `stories` | **M1** |
  | **`new-feature`** | intake → architect/plan → epic split | `epics` | **M2** |

- **FR-11c** **[M1]** **Workflow structure is never model-generated.** Instances come from variable binding only — a novel graph per run would make FR-9 pinning impossible and turn G2 into a review of unfamiliar structure every time.
- **FR-12** **[M1]** Read-only workflow viewing in the UI. Editing is git.
- **FR-12a** **[M1]** Display the generated plan **and the generated Playwright specs** before the run, and require explicit approval (**G2**) to start.

### F3 — Durable execution
- **FR-12b** **[M1]** **Phase A — project workspace.** Clone or refresh the project's repositories at their base branches and install dependencies, giving intake real code to read. No branches created. *(M1 enters at Phase B; Phase A is exercised by M2.)*
- **FR-12c** **[M1]** **Phase B — branch and worktree.** After G2, create a branch and git worktree in the target repository. Conditional and per-repository, never a fixed first step.
- **FR-12d** **[M1]** Each story targets **exactly one repository**.
- **FR-12e** **[M1]** After worktree creation, **install dependencies in the worktree** and run `quality_gate_command`. Fail the story immediately if the starting point is already red.
- **FR-12f** **[M1]** **Copy the approved `epics.md`, acceptance criteria, and generated specs into the worktree** as the run's authoritative inputs, so story tasks never depend on the Phase A clone. *(Without this the two-phase split has no route for the spec to reach the work.)*
- **FR-13** **[M1]** Execute workflows durably: a run survives process restart, container restart, and reboot without losing position or repeating completed steps.
- **FR-14** **[M1]** Park a run on a human gate for an unbounded period without holding compute. *(Bounded in practice by C-4 — see NFR-5.)*
- **FR-15** **[M1]** Resume a parked run when the required human input arrives.
- **FR-16** **[M1]** Retry failed steps with configurable attempts and backoff; distinguish infrastructure failure (retry) from task failure (escalate).
- **FR-17** **[M1]** Query in-flight and completed runs by project, repository, status, and epic.
- **FR-18** **[M1]** Cancel a run and roll back its working branch.
- **FR-19** **[M1]** **Cap rework cycles per story at 2, then escalate.** Without this a wrong premise burns budget indefinitely.
- **FR-19a** **[M1]** A G3 rejection opens a **new session** with the rejection reason as context. Sessions are not resumed across a rejection.
- **FR-19b** **[M1]** Rejection cycles count against the FR-19 cap.
- **FR-19c** **[M1]** Check per-story state before re-running. A story whose PR already merged needs a follow-up change, not a replay.

### F4 — Agent task execution
- **FR-20** **[M1]** Execute agent tasks non-interactively against Claude Code in print mode.
- **FR-20a** **[M1]** Model harnesses by **declared capability** — `supports_defer`, `supports_structured_output`, `supports_resume`, `supports_native_tracing` — so adding a harness with weaker capabilities degrades explicitly rather than silently. *(Second harness is M3; the seam is M1.)*
- **FR-21** **[M1]** **Persist every agent session id in Postgres**, captured from print-mode execution, against task, story, epic, and project. Assign the identifier before launch rather than parsing it from output. Hard requirement: without it no blocked step resumes.
- **FR-22** **[M1]** Persist enough per-task state — prompt, bound inputs, prior structured outputs — to **reconstruct** a session if harness-local content is lost. Replay-fidelity resume is M3; see C-4.
- **FR-23** **[M1]** Send a follow-up message into an existing session and resume it.
- **FR-23a** **[M1]** For human-answered blocks, **print the exact resume command** (harness, session id, working directory) in the inbox for the operator to run in their terminal, and detect the session's completion to resume the workflow.
- **FR-24** **[M1]** Require every agent task to return **schema-validated structured output**: `status`, `artifacts_written`, `open_questions`, `assumptions` — each assumption carrying a `severity` (`blocking` | `material` | `routine`).
- **FR-24a** **[M1]** Validate on ingest that every acceptance criterion names the **test-ids and routes** it touches. Reject `epics.md` that does not, at G2 in M1 and at G1b in M2.
- **FR-25** **[M1]** Supply project and repository context (FR-2, FR-3) to each agent task.
- **FR-26** **[M1]** Record per task: harness, model, session id, token usage, cost, wall-clock, exit status.

### F5 — Validation and gates
- **FR-27** **[M1]** Each step declares its **gate strength**:

  | Strength | Definition |
  |---|---|
  | `liveness` | The output exists and parses |
  | `deterministic-oracle` | A machine-checkable check **fixed before the implementation existed** — compiler, type-checker, linter, or a Playwright spec approved at G2 |
  | `human` | A person decides |

  **Independence is by timing, not authorship.** A spec generated by an agent still qualifies if it was fixed and approved before the implementation it judges. *(An `adversarial` tier — an independent agent instructed to refute — is defined in the addendum and deferred to M3.)*
- **FR-28** **[M1]** **A step with no oracle renders as `unvalidated`, never green.** File-existence is liveness and must never be presented as correctness.
- **FR-28b** **[M1]** **Generate Playwright specs from signed acceptance criteria before any build step**, targeting the test-ids named under FR-24a. Report every criterion with no spec and every spec with no criterion; **an unmatched criterion blocks G2** rather than being noted and passed over.
- **FR-29** **[M1]** Run Playwright E2E against a provisioned environment with a real database before any PR is offered for review.
- **FR-30** **[M1]** Escalate to a human when an agent returns any `open_questions`, **or any assumption of severity `blocking` or `material`**. Routine assumptions are recorded and shown at G3, not escalated. Escalating on every assumption would fire on nearly every task and destroy the walk-away premise.
- **FR-30a** **[M1]** Remember dismissed escalations per story so the same assumption does not re-escalate on a retry.
- **FR-31** **[M1]** Where the harness supports deferred tool calls, use that as the blocked signal — the process exits cleanly with a deferred-tool payload, the orchestrator collects the answer, and the resumed run supplies it. Fall back to FR-30 output inspection where unsupported.
- **FR-32** **[M1]** Record every gate decision — who, when, what was approved, against which artifact version — as an auditable record.

### F6 — Review inbox
- **FR-33** **[M1]** A single inbox of everything awaiting the human, typed: **blocked story**, **epic ready for QA**, **budget breach** (FR-45), **rework cap reached** (FR-19), **infrastructure failure** (FR-16), **unmatched criterion** (FR-28b). Each carries age and project.
- **FR-34** **[M1]** Each item carries enough context to reload cold: the question, the story, its criteria, what the agent has done, and links to the diff and the trace.
- **FR-35** **[M1]** Answer a blocked step — in M1 by running the printed resume command (FR-23a); in M2 from the inbox directly.
- **FR-36** **[M1]** Approve or reject an epic at G3; rejection opens a fix cycle bounded by FR-19.
- **FR-37** **[M1]** Notify in the UI.

### F7 — GitHub
- **FR-38** **[M2]** Ingest GitHub issues as work items. *(M1 is fed `epics.md` directly.)*
- **FR-39** **[M1]** Create branches, commit, and push using repository-scoped short-lived credentials.
- **FR-40** **[M1]** Open a PR when an epic's workflow completes with all gates satisfied, linking the originating work item, the trace, and the gate record. **The PR is opened before G3** — G3 reviews an open PR and decides merge.
- **FR-41** **[M1]** Report gate status onto the PR so it is legible in GitHub, not only in the orchestrator.
- **FR-42** **[M1]** **Never merge.** Merge is a human action.

### F8 — Observability and cost
- **FR-43** **[M1]** Emit one trace per workflow run; orchestrator spans and harness spans share the trace id.
- **FR-44** **[M1]** Attribute LLM cost per task, story, epic, project, and repository.
- **FR-45** **[M1]** Enforce per-run and per-project budgets; halt and escalate on breach rather than continuing to spend.
- **FR-46** **[M1]** Record primary metrics and counter-metrics as first-class queryable data.
- **FR-50** **[M1]** Capture a **pre-registered manual estimate** — "writing this yourself, how long?" — at G1b in M2, and **at ingest in M1**, recorded before the run begins.
- **FR-51** **[M1]** Record **active time inside every gate** and derive `estimated_manual_minutes ÷ actual_human_minutes` per epic.
- **FR-52** **[M1]** Track **rejection rate per gate** and alert on a sustained zero.

### F9 — Test environment
- **FR-47a** **[M1]** **Provision the environment** an E2E run requires: start the repository's declared services, create a database, apply migrations, and seed fixtures. *(Previously absent — F9 tore down an environment nothing created.)*
- **FR-47** **[M1]** **Serialize execution.** One active run at a time in the PoC. Because a single Postgres backs the E2E database, the lock is **global**, not per-worktree — a run parked at a gate blocks the queue. Accepted for M1; lifting it requires per-run database isolation.
- **FR-48** **[M1]** Enforce serialization explicitly — queue a second run rather than let two share a worktree or database.
- **FR-49** **[M1]** Tear down the environment when a run reaches a terminal state — merged, cancelled, or timed out. **Not on epic completion**, since G3 and any fix cycle still need the worktree and the running feature.

## 7. Non-functional requirements

- **NFR-1** Single Docker container: orchestrator, tooling (git, gh, Claude Code, skills), and a reachable Postgres.
- **NFR-2** The execution model must not change shape when moving to multiple containers. Constraints in §8.
- **NFR-3** Agent containers **run as a non-root user**. Permission-bypass modes refuse to start as root.
- **NFR-4** Prefer an explicit tool allowlist over blanket permission bypass.
- **NFR-5** A workflow parked for up to **30 days** resumes correctly. Beyond that, harness session content may have expired (C-4) and the run requires reconstruction (FR-22). *This is a harness constraint, not a design choice.*
- **NFR-6** Agent logs and structured outputs are retained per run and readable from the inbox.
- **NFR-7** Recovery is automatic on restart.

## 8. Security and durability constraints

### Security
Threat model: **prompt injection reaching an agent that holds credentials and can write to a repository.** Repository contents are untrusted input.

- **SEC-1** Repository-scoped, short-lived tokens. Never long-lived org-wide credentials.
- **SEC-2** Agent containers never mount `~/.ssh`, `~/.aws`, or host credential stores.
- **SEC-3** Drop capabilities, `no-new-privileges`, read-only root filesystem where possible, non-root user.
- **SEC-4** Restrict egress to an allowlist: git host, package registries, model gateway, telemetry.
- **SEC-5** Scope secrets per project. A task for project A can never read project B's credentials — enforced despite the single operator, because retrofitting this boundary later is far harder.
- **SEC-6** Prefer credential injection at the proxy so the agent process never holds a usable secret.
- **SEC-7** Agents never merge, never force-push, never push to a default branch.
- **SEC-8** Route model traffic through a gateway with per-project virtual keys and budgets.

### Durability
**C-1 — Workflow document versioning.** *(Highest severity.)* A durable engine that versions by hashing workflow *source* does not change version when the **YAML** changes. An in-flight run is then recovered against a different document and fails. **Mitigation:** version the document explicitly, pin each run, keep old versions resolvable while any run references them (FR-9, FR-7b).

**C-2 — Application version pinning.** Deploying orchestrator code strands runs started under the old version until a process on that version exists. With multi-day gates this is routine. **Mitigation:** drain strategy, or explicit fork-with-version on resume.

**C-3 — Multi-container recovery.** Recovery across processes is either a paid vendor component or self-managed via static per-process identity, where a crashed process's runs are not adopted until that identity returns. **Decide before scaling (NFR-2).**

**C-4 — Harness session state is not durable.** Local session files carry a default 30-day retention and an explicitly internal format that may break on any release — **do not parse them**. Three session paths exist and do not share an integration:

| Path | Mechanism | Milestone |
|---|---|---|
| Human answers a block | Operator runs the printed `--resume` command in their terminal | **M1** |
| Automated agent tasks | Print-mode CLI, session id pre-assigned and stored in Postgres | **M1** |
| Cross-container durable resume | Agent SDK with a Postgres session store | **M3** |

**PoC decision: print-mode CLI, risk accepted.** The orchestrator owns session **identity** in Postgres (FR-21); the harness owns session **content** on local disk. Consequences: an epic parked past the retention window loses resumability (NFR-5), and container replacement loses content. FR-22 stores enough to **reconstruct**, not replay.

**C-5 — Harness capability asymmetry.** Codex can resume but has no documented deferred-input round trip and no documented tracing exporter. Deferred to M3, but FR-20a keeps the seam so the asymmetry is modelled rather than discovered.

**C-6 — Gateway side effects.** A non-first-party model gateway silently disables behaviours including trace-context propagation, which FR-43 depends on. Each must be re-enabled explicitly, and context/output token limits pinned — unrecognized gateway model IDs fall back to a low default.

**C-7 — Telemetry accepts traces only.** The observability backend ingests OTLP traces, not metrics or logs, over HTTP only. Prompt and tool content are redacted unless explicitly enabled — enabling puts source code into the telemetry backend.

## 9. Glossary

Three terms carry multiple meanings in this domain. These are the meanings used here.

| Term | Means | Does not mean |
|---|---|---|
| **Spec** | The generated Playwright test file | The PRD, or the shaping session's output — those are the *specification* or `epics.md` |
| **Session** | A harness conversation with a persistent id | A user's login, or a workflow run |
| **Instance** | A workflow produced by binding variables to a template | A container, or a database row |
| **Workflow** | An authored YAML template | A running execution — that is a **run** |
| **Gate** | A point where a human decides | An automated check — that is a **validation step** |

## 10. Resolved questions

| # | Question | Resolution |
|---|---|---|
| Q1 | What carries the human's signature? | Given/When/Then criteria in `epics.md` **plus** the generated Playwright specs at G2 |
| Q2 | Per-project secret scoping in v1? | Yes — scoped per project, shared across that project's repositories |
| Q3 | Web chat to a live session? | Deferred to M3. M1 prints the resume command for the operator's terminal |
| Q4 | Primary metric? | Token cost and velocity, plus `estimated ÷ actual` with pre-registered thresholds (§3) |
| Q5 | Which ticket class? | **Fast to verify** — criteria expressible as Playwright assertions against named test-ids |
| Q6 | Does a Playwright suite exist? | Yes for the fullstack app, which is why M1 targets it. `ai-orchestrator` becomes eligible once its own suites exist (FR-3b) |
| Q7 | Concurrency? | None. Serialized globally in M1 |
| Q8 | Can a story span repositories? | No. One story, one repository, one PR |
| Q9 | Are workflows dynamic? | Dynamic *instantiation* from authored templates; **not** dynamic structure |
| Q10 | What happens on G3 rejection? | A **new session** with the rejection as context, bounded by the FR-19 cap |

## 11. Assumptions

- `[ASSUMPTION]` Requiring acceptance criteria to name test-ids is workable in practice. **The largest untested assumption in the design** — it makes G1b heavier and pushes interface decisions earlier than engineers usually make them. First on the verification queue.
- `[ASSUMPTION]` One operator; no auth boundary between users, per-project secret scoping retained.
- `[ASSUMPTION]` The target repository's suites run inside the single container with no external dependency beyond a database.
- `[ASSUMPTION]` Epic-sized batches are the right human return unit. **The central bet** — see §12.
- `[ASSUMPTION]` A hand-authored `epics.md` is representative enough of M2's generated output that M1's evidence transfers.

## 12. Known weak points

### 12.1 The central bet
That a human can validate an epic-sized batch in materially less time than writing it, *once cold context-reload cost is counted*. Token cost and velocity cannot test this; §3's pre-registered thresholds and FR-50/51/52 can. **A rubber-stamped gate improves both primary metrics** — that is why the counter-metrics exist and why the kill threshold was declared before any data.

**Free control group:** `ai-orchestrator` is built partly by hand during bootstrapping and partly by the pipeline afterwards — same person, same codebase, same weeks. Record which commits came from which path.

**One-way door:** the manual estimate must be captured **before** each run (FR-50). Retrofitting it is impossible, and without it §12.1 is permanently unanswerable.

### 12.2 Cross-repository ownership — do not solve now
Whoever owns a repository owns the PRs this opens. If each owner must run their own G1b, "multiple projects" means multiple humans doing gates — a tool each team installs, not a portfolio system. **Build nothing.** Record the trigger: *the first time someone other than the operator must approve a gate.*

### 12.3 Competitive positioning — unresearched
The landscape scan did not complete. Immaterial for an internal tool; **required before productizing.**

### 12.4 Accepted residual risk
- **Verifiability as admission criterion narrows the tool by design.** It excludes most refactoring, performance work, and anything judged rather than asserted. **A good result here does not generalize** to those.
- **Serialization means the PoC cannot demonstrate the parallelism the concept is worth** (§1). M1 proves the loop; the value proposition remains untested until concurrency exists.
- **M1's evidence depends on hand-authored input.** If M2's generated `epics.md` is materially worse than what the operator writes by hand, M1's numbers overstate the system.

---

*Technical decisions, rejected alternatives, and mechanism detail in `addendum.md`. Decision trail in `.memlog.md`. Reviews in `review-rubric.md`, `review-scope.md`, `review-consistency.md`. Upstream: `_bmad-output/forge/agent-workflow-os/forged-idea.md`.*
