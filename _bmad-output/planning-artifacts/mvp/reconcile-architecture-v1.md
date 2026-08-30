---
title: Reconciliation — architecture-v1.md against PRD (prd.md + addendum.md)
status: draft
created: 2026-08-26
input: ../v1-dev-loop-2026-08-26/architecture-v1.md
against: prd.md, addendum.md (this directory)
---

# Reconciliation: architecture-v1 → PRD

Method: every behaviour architecture-v1.md assumes (not every technology choice — those correctly live only in architecture/addendum) is checked against the PRD's FRs/NFRs and the addendum. "Landed" = an FR/NFR or addendum line states the same behaviour. "GAP" = the architecture assumes/implements a behaviour with no corresponding FR/NFR/addendum line. "CONTRADICTION" = the two disagree (numbers, statuses, step names, or an implied answer vs. a PRD open question).

## 1. Front-end / auth / polling

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| `POST /api/login {token}` → HttpOnly cookie, 30 d | Landed — FR-1 | Same duration (30 days). |
| Every `/api/*` requires the session | Landed — FR-1 | "every /api/* call requires the resulting session." |
| Login lockout mechanism (not specified in architecture) | N/A | Architecture is silent on lockout; PRD FR-1 adds "5 failures / 15 min" as `[ASSUMPTION]`. Not a gap — PRD adds a rule architecture didn't need to specify. |
| Polling 5 s while any Run `RUN`, else 30 s; no websockets in v1; SSE is the upgrade path | Landed — FR-24 | Same cadence. PRD does not explicitly state "no websockets in v1" as a non-goal, but §5 non-goals ("no notification channel outside the UI") and §6.2 out-of-scope don't mention SSE/websockets either way — low-risk omission, not a behavioural gap since polling-only is fully specified by FR-24. |
| Endpoints: `answer`, `continue`, `skip-story`, `retry-step`, `cancel` | Landed — FR-18, FR-19, FR-20 | Behaviour matches; endpoint names correctly omitted from PRD (technology). |
| Diagram: pure function `yaml → nodes/edges`, updates on valid YAML, read-only | Landed — FR-7 | "updates on every successful validation... invalid YAML leaves the last valid diagram... No node can be dragged, added, or edited." |
| Clone check runs synchronously on `POST /api/projects/:id/repositories`, returns per-check results | Landed — FR-4 | Matches "reports per check." |

## 2. Backend — data model, template schema, interpreter

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| `repo_lock` table (`repository_id → run_id`) in the app schema | Partially landed / minor tension | §2.3 separately says the repository lock is "for free" via the DBOS queue partition (`partition_concurrency=1`), with no table needed. The data model then lists a `repo_lock` table too. Not a PRD contradiction (PRD never names a table), but worth flagging to the architect: two lock mechanisms described (queue partition vs. app-schema table) — likely the table is just a queryable projection (as `run`/`step_run` are), but this isn't stated. |
| Template schema: Inputs `project\|repository\|string\|path\|enum\|number`; Steps `git.worktree\|shell\|agent\|git.commit\|git.push` | Landed — FR-5 | Identical enumerations, identical names, no drift. |
| One `for_each` construct, no nesting, no expressions, no string functions, `{{var}}` only | Landed — FR-5, FR-10 | "No loop other than for_each, no conditionals, no string functions"; "read once at Run start, never re-read" (FR-10) matches §2.3's "read once at start... never changes on recovery." |
| Validator rejects unknown keys, unbound variables, **non-prefix-free story ids** (§2.2) | Landed, but placement inconsistent | §2.2 attributes "non-prefix-free story ids" to *Template* validation, yet story ids only exist once `stories.yaml` (an external, per-Run-bound file) is read — the Template YAML itself never contains story ids. PRD correctly places this check in Run **pre-flight** (FR-8: "stories.yaml parses with N Stories and prefix-free ids"), not Template validate (FR-5). The architecture's own §2.2 wording is the odd one out — worth a line fix there, not a PRD gap. |
| `gate: liveness \| deterministic \| human` | Landed — FR-5, glossary | Identical three values and definitions. |
| `on_fail: escalate \| fail \| continue` (default escalate); `retry: {attempts: 1}` for infra failures only | **GAP** | No FR/NFR describes a per-step failure-handling policy with three modes. PRD only gives concrete outcomes for two cases: baseline non-zero exit → Run `failed` directly (FR-9, i.e. behaves like `on_fail: fail`, not the architecture's stated default of `escalate`), and verify failure → one re-dispatch then `needs-you` (FR-10). `on_fail: continue` is never exercised or explained anywhere in the PRD/addendum — unclear which step, if any, uses it. |
| `escalate_when` / `pause_when` on `agent` steps | Landed — FR-16, FR-19 | Behaviourally equivalent to FR-16's status routing and FR-19's checkpoint handling. |
| Interpreter mapping: `blocked→BLK`, `ready-for-dev`+`spec_checkpoint→CHK`, `done→next`, other→`BLK unexpected status` | Landed — FR-16 | Line-for-line match including the catch-all "unexpected status: {status}". |
| **`pause_when` is only listed as an `agent`-step extra**, yet PRD defines "done checkpoint" as pausing **after the Story's commit step** | **CONTRADICTION / mechanism gap** | Glossary: "done checkpoint (after the Story's commit)"; FR-19: "done checkpoint: Continue starts the next Story." The interpreter pseudocode (§2.3) only evaluates `result.pause`/`result.escalate` from `run_step`, and `pause_when` is defined solely as an `agent` step attribute (§2.2) tied to reading the story file's frontmatter after the harness exits — there is no described mechanism for the `git.commit` step (a non-agent step with no story-file output) to produce a pause. As written, architecture has no path to implement the done-checkpoint behaviour PRD requires. |
| Human wait: `DBOS.recv(topic, timeout=30*24*3600)`; API endpoints `send` to resume | Landed — FR-12 | "A Run parked in needs-you for 30 days resumes correctly." Same 30-day figure. |
| Queue: `global_concurrency=2`, `partition_concurrency=1` by repository → repo lock "for free" | Landed — FR-13 | Same numbers: "at most one active Run per Repository and at most two active Runs overall." |
| Repository lock released while a Run is parked `needs-you` (queue-partition leave) | Landed as assumption — addendum §D, PRD §9 assumptions index (FR-13) | Both documents flag it explicitly as an assumption/open question (PRD §8 Q5), and addendum §D gives the mechanism and a documented fallback ("If this proves confusing... flip to hold"). Good — consistent, and the uncertainty is honestly carried through both documents. |
| Cancel: `DBOS.cancel_workflow` + compensating step removes worktree, deletes branch only if `created_branch && !pushed` | Landed — FR-20, addendum §D | Identical condition. |
| Recovery: DBOS resumes every `PENDING` workflow at last completed step; interrupted agent step re-runs as a new attempt; story file status (`draft→plan`, `in-progress→implement`, `in-review→review`) tells build-auto where to resume | Landed (PRD at the right altitude) — FR-12 | FR-12 states the user-visible contract ("resumes the Run at that Step... new attempt with a new Session id... resumes from the Story file's own status") without the build-auto internal state-mapping table, which correctly stays in architecture. |
| Every side effect is a `@DBOS.step`; `retries_allowed` only for `git.*` network failures; agent steps never auto-retried | **GAP (minor)** | The automatic infra-level retry for git network failures has no corresponding FR/NFR — only the operator-triggered "Retry a Step" (FR-20) is specified. Likely fine to leave as an architecture-only resilience detail, but it is a retry behaviour the architecture assumes that the PRD never mentions. |

## 3. Agent contract, harness adapters, git ops

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| Agent contract: story file `{spec_folder}/stories/{story_id}-*.md`, frontmatter `status ∈ {draft, ready-for-dev, in-progress, in-review, blocked, done}` | Landed — glossary, FR-16 | Identical status enum, identical path pattern. |
| Liveness check: exactly one matching file, frontmatter parses | Landed — FR-16 | "Exactly one matching file with parseable frontmatter = liveness green; zero or several... = Step error." |
| Prompt: same for every harness — skill name, spec folder, story id, `invoke_dev_with`, "Halt after planning." when checkpoint, project context prepended, "## Human Answers" phrase on re-dispatch | Landed — FR-14, FR-15, FR-18, addendum §D | Addendum §D quotes the answer-append and re-dispatch phrasing verbatim, matching architecture §2.4. |
| Fallback: harnesses that can't invoke skills by name get the rendered `workflow.md` path (`_bmad/scripts/render_skill.py`) | **GAP** | No FR/NFR/addendum line mentions this fallback at all. Given the addendum records that Claude Code's `--bare` skips auto-discovery outside `--add-dir` and that Codex/OpenCode read skills from different directories, this fallback path is plausibly load-bearing for MVP and should be at least an addendum mechanism, not silent. |
| Adapter capability matrix (`preassign_session`, `resume`, `native_tracing`) per harness | Landed — FR-14, FR-21 | Claude: pre-assigned session id, resume shown (FR-21). Codex: session captured from event, resume shown. Local: session captured from event stream, "local shows none" for resume (FR-21) — matches architecture's per-adapter capability declarations exactly. |
| Codex: "Enable `multi_agent` feature" (§2.5, treated as a settled config choice) | **CONTRADICTION (certainty mismatch)** | PRD §8 Open Question 1 asks "Does Codex CLI's `multi_agent` feature satisfy `bmad-build-auto`'s subagent requirement... Decides whether `codex` is a full peer on day 4" — i.e. PRD treats this as unresolved, while architecture already prescribes enabling the feature as if the question were answered. |
| OpenCode session id "captured from JSON events (**fallback:** `opencode session list --format json`)" (§2.5, presented as a resolved two-path design) | **CONTRADICTION (certainty mismatch)** | PRD §8 Open Question 2 asks "Does OpenCode emit the session id in `--format json` events, or must it be read from `opencode session list` after the run?" — architecture already answers this with a fallback design; PRD still lists it as unresolved. FR-14's "local: ... Session id captured from the event stream" also omits the fallback that architecture and addendum §B both assume exists. |
| Claude adapter: `--max-budget-usd $B` — a **per-process hard budget cap** enforced by the Claude Code CLI itself | **GAP** | This is a second, harness-local budget enforcement mechanism (Claude only) in addition to the after-step aggregate check. FR-17 documents only "After every Story step, spend... summed from Gateway spend logs... if spend > budget → needs-you." A Claude run could hit its own `--max-budget-usd` mid-story with a different failure mode (exit code / error) than the FR-17 aggregate-check path, and this is not described anywhere in the PRD. |
| Budget halt timing: "checked **after every agent step**" (§2.5/§3), i.e. potentially before that story's verify/commit steps run | **CONTRADICTION / ambiguity** | FR-17: "After every Story step, spend... is summed... if spend > budget the Run becomes needs-you... **before the next Story starts**." Architecture's wording implies the check happens immediately after the build/agent step — mid-story, before verify and commit of the *same* story. PRD's wording ("before the next Story starts") is compatible with that reading but is loose enough to also be read as "only at story boundaries, after verify/commit complete." Worth pinning down: can verify/commit run once spend is already over budget? |
| Adapters never receive the GitHub token; git ops run in the orchestrator, token injected per command (`GIT_ASKPASS` helper) | Landed — FR-11, FR-14, NFR-3 | "Push uses the Project token per command; the token never appears in the environment of any agent process." |
| Model traffic only ever goes to LiteLLM; harness has no direct provider key | Landed — FR-26, NFR-3 | Matches. |
| Clone check: `git ls-remote`, `git clone --depth 1` → `/work/<project>/<repo>/base`, default branch exists | Landed — FR-4 | Identical path and checks. |
| **Daily re-run of the Clone check**, flips Repository status, blocks new Runs only | **GAP** | PRD FR-4 states this as an `[ASSUMPTION]`, but architecture-v1.md contains **no scheduler, cron job, or DBOS scheduled workflow anywhere** — the only clone-check trigger described in architecture is "on repository save" (§2.6). There is no component in the architecture that could run a daily re-check; this needs a home (e.g. a DBOS scheduled workflow) before it can be built. |
| Run start: `git fetch`, `git worktree add /work/<project>/<repo>/wt/<branch>`, creating from `origin/<base>` when absent | Landed — FR-9, glossary | Identical worktree path pattern `/work/{project}/{repo}/wt/{working branch}`. |
| `commit` adds spec folder + all changes, message pattern, no-op on clean tree | Landed — FR-10 | "commit adds the Spec folder and all changes... with message `story {id}: {title}`; a clean tree commits nothing and records `no changes`." |
| `push` refuses when `working_branch == default_branch`; PR via `gh pr create --fill --draft` or compare URL fallback | Landed — FR-11, addendum §C/§A | Matches, including the `[ASSUMPTION: gh availability per Project]` tag carried in both PRD and addendum. |

## 4. LiteLLM / Langfuse

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| One virtual key per Project, `max_budget`, `budget_duration: monthly`, tags `project:<p>` | Landed — FR-2 (implied by "GitLLM key ref"), Constraints §Cost | "per-Project monthly budget on the Gateway key." |
| Key ref stored, key itself never in clear in the app DB | Landed — FR-2 (for the GitHub token) / consistent with NFR-3 | PRD is explicit about the GitHub token being encrypted at rest; the LiteLLM key-ref-not-cleartext behaviour is implied by NFR-3 + addendum §D ("stored as a reference in the app DB, secret in pgcrypto") rather than stated as its own FR — acceptable, addendum covers it. |
| Per-run tags `x-litellm-tags: run:<id>,story:<sid>,harness:<h>`; spend summed via `GET /spend/logs` by tag, cached on `run.spend_usd` | Landed — FR-17, FR-26, addendum §D | FR-26 adds `project:{name}` to the tag list, which architecture supplies via the virtual key's own `project:<p>` tag rather than the per-request header — consistent once both mechanisms are combined, not a contradiction. |
| Local models: cost implicitly $0 through LiteLLM (not explicitly stated in architecture) | Landed (PRD adds it) | Constraints §Cost: "local model spend recorded as $0 with tokens" — an elaboration PRD adds; architecture doesn't contradict it, just doesn't say it. |
| One Langfuse trace per Run, id = orchestrator-created W3C trace id; Claude spans join via inbound `TRACEPARENT`; Codex/OpenCode join via `langfuse.session.id = run id` | Landed — FR-27, addendum §A/§B, PRD §9 assumptions index | PRD explicitly carries the "span parenting differs per harness" caveat as an assumption, matching PRD §8 Open Question 3. |
| Content redaction on by default; `OTEL_LOG_USER_PROMPTS` per-project switch | Landed — Constraints §Privacy | Verbatim match in spirit: "redacted... by default; enabling content logging is a per-Project switch that puts source code in Langfuse." |

## 5. Container / security / local models

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| Non-root user, `cap-drop ALL`, `no-new-privileges` | Landed — NFR-3 + addendum §A | NFR-3 states non-root + no credentials; the specific cap-drop/no-new-privileges flags correctly live only in addendum (technology). |
| Egress allowlist: GitHub, npm/PyPI, LiteLLM, Langfuse, host model server | Landed — NFR-4 | "git host, package registries, the Gateway, Langfuse, and the host model server" — same five categories. |
| No host credential mounts | **GAP (minor)** | Not explicitly stated as an FR/NFR. Arguably implied by NFR-3 ("hold no GitHub token and no direct provider key") but that covers *runtime* secrets, not host filesystem mounts (e.g. `~/.ssh`, `~/.aws`) specifically — worth an explicit NFR line if this guarantee matters operationally. |
| Project secrets injected per step from the orchestrator's secret store (pgcrypto) | Landed — FR-2, addendum §D | "GitHub token is stored encrypted at rest"; addendum §D gives the pgcrypto mechanism. |
| Local model serving: oMLX, two pinned models, `--memory-guard-gb 40`, expected throughput ranges | Out of PRD scope (correctly) | This is pure technology/ops detail; PRD §8 Open Question 4 ("What throughput does the Mac Mini actually deliver...") shows the PRD is aware of the uncertainty without duplicating the numbers — appropriate split. |

## 6. Future-growth section (§6)

| Architecture item | Landed / GAP / CONTRADICTION | Note |
|---|---|---|
| Second container, shared worktree volume, SSE, Mattermost notifier, `new-feature` template (M2) | Landed as non-goals — §6.2 out of scope | "Second container / multi-machine execution... deferred"; "Mattermost or any notification outside the Board... Deferred"; "Intake and spec generation (long-term PRD M2). Deferred." All match. |

---

## Summary of the most important items

1. **Budget check timing is ambiguous between the two documents.** Architecture: halted "after every agent step" (potentially before that story's verify/commit run). PRD FR-17: "after every Story step... before the next Story starts" — compatible but loose enough to be read as story-boundary-only. Needs pinning down before implementation.
2. **Done checkpoint has no described mechanism.** PRD requires pausing *after the commit step*; architecture's `pause_when` is defined only as an `agent`-step attribute evaluated from story-file frontmatter, with no path for a non-agent step (`git.commit`) to trigger a human pause.
3. **The daily Clone-check re-run (PRD FR-4) has no home in the architecture** — no scheduler, cron, or DBOS scheduled workflow appears anywhere in architecture-v1.md; only "on repository save" is described.
4. **Architecture presupposes answers to two of the PRD's own open questions** — it already configures Codex's `multi_agent` feature and an OpenCode session-id JSON/fallback design as settled, while PRD §8 Q1 and Q2 explicitly mark both as unresolved and day-4-deciding.
5. **A second, harness-local budget cap (`--max-budget-usd` on the Claude adapter) is undocumented in the PRD**, which describes only the after-step aggregate Gateway-spend check (FR-17) — a Claude run could fail mid-story via a different path than FR-17 describes.

Lower-priority gaps also recorded above: `on_fail: continue` is never exercised in the PRD; the `render_skill.py` skill-fallback path for harnesses that can't invoke skills by name is unmentioned outside architecture; automatic infra-only git retries have no FR; "no host credential mounts" isn't an explicit NFR; and architecture's §2.2 attributes prefix-free-story-id validation to the Template validator when it can only be checked once `stories.yaml` is bound (PRD correctly places it in pre-flight, FR-8).
