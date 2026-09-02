---
review: reconcile-guidelines
target: ../ARCHITECTURE-SPINE.md (status: draft, 2026-09-02)
inputs: GUIDELINES.md; architecture/.memlog.md `(constraint) [user]` lines; user's chosen GUIDELINES rules (memlog decision "GUIDELINES.md rules adopted")
date: 2026-09-02
---

# Reconciliation review — spine vs user bullets vs GUIDELINES.md

**Verdict: reconcilable with edits.** Every user bullet is honoured or honoured
partially with a stated reason (three partials, all justified). Of the four
GUIDELINES principles the user chose, two are fully enforceable in the spine
(frozen anchors — mostly; linter+formatter), one is enforceable but not yet
stated as a rule (machine-checkable exits), and one is bound but never turned
into a rule (maker ≠ checker). No un-chosen GUIDELINES principle is imposed.
Four internal points contradict the "constitution describes reality / rules are
checkable" framing of §5/§9 and should be fixed before the spine is frozen.
The DSL's bounded `retry` / `on_fail.max` is acceptable under "no silent
auto-retry" **only if** the spine states the four conditions listed in D-2.

Scope of this review: the spine text only. AGENTS.md drafts, harness scripts and
the DSL draft were not opened; where a finding depends on them it says so.

---

## A. User bullets the spine does not honour, or honours partially

Legend: OK = honoured; PARTIAL = honoured with a stated limitation; GAP = not honoured.

| # | User bullet (memlog `(constraint) [user]`) | Status | Where | Note |
|---|---|---|---|---|
| A-1 | Multi-component repo `web-client/` + `backend-api/` | OK | Structural Seed | — |
| A-2 | Front-end Node + Astro calling the Python API | OK | AD-1 | Astro SSR + Node adapter; islands never call backend directly. |
| A-3 | Each feature has its API route | OK | Consistency › Routes | `/api/v1/<feature>` routers; signals as one sub-resource (AD-13) is still per-feature. |
| A-4 | Env-variable token security; same token logs in on the web | OK | AD-4 | See A-4n below on a second secret. |
| A-5 | Share the domain FE/BE for contract types "if possible" | OK | AD-3 | Contract types (not domain objects) are shared via OpenAPI → `openapi-typescript`. Meets the "if possible" bullet; the memlog decision records why. |
| A-6 | One user login with secret token | OK | AD-4 | — |
| A-7 | GitHub token general, in instance env | OK | AD-5 | Per-repo tokens listed under Deferred. |
| A-8 | DBOS for workflow tracking | OK (re-framed) | AD-6, AD-8 | DBOS is the durable engine behind a port; **status source of truth is the app tables**, DBOS ids are opaque `engine_ref`. This is a deliberate re-framing recorded in the memlog ("change DBOS tomorrow = new contract implementation") but the spine itself does not say why. Suggest one clause in AD-6 *Prevents* or *Rule*. |
| A-9 | PostgreSQL for orchestrator data + run tracking; same DB for DBOS | OK | Consistency › Transactions; `DATABASE_URL` | Schemas `public` + `dbos`. |
| A-10 | Orchestrator + harnesses in one docker container in production | OK (interpretation) | Structural Seed, backend-api Dockerfile | backend-api image = FastAPI + DBOS walker + claude/codex/opencode + bmad-method: one container. web-client and Postgres are separate containers. The spine's "Two deployables" (AD-1) reads as a departure unless the reader knows "orchestrator" = backend-api. Suggest naming the mapping in AD-1 or the seed comment. |
| A-11 | Harnesses claude/codex/opencode with BMAD **pre-installed globally** | **PARTIAL** | AD-16 | Global skill stubs live in the image (`~/.claude/skills`, `~/.agents/skills`), but every target repository must still carry `_bmad/` and pass a manifest-version check; `repo-init@1` exists for that. **Reason is in the memlog only** ("BMAD has no global install mode: every SKILL.md runs `uv run {project-root}/_bmad/scripts/render_skill.py`, which fails without `_bmad/`"). The spine's AD-16 does not state the impossibility, so a reader sees an unexplained departure. Fix: add one clause to AD-16 *Prevents* or *Rule*. |
| A-12 | Harnesses connected to LiteLLM + Langfuse; one clear isolated setup script per harness | OK | AD-10, AD-20, `scripts/harness/<name>.sh` | Config files generated only by the script (AD-20). |
| A-13 | Run start creates Langfuse span ids sent to each harness; whole workflow visible in Langfuse | **PARTIAL** | AD-11, Deferred, Open at handoff #1 | claude: full parenting. codex: `TRACEPARENT` honoured in source, not documented — day-1 check with a flat fallback. opencode: no inbound traceparent; session/user id only (one Langfuse *session* view, not one trace tree). Reasons are stated in the spine. Acceptable; nothing to change beyond keeping the day-1 check. |
| A-14 | LiteLLM + Langfuse already on host; prepare env vars | OK | Variable table, seed diagram (`host.docker.internal`) | — |
| A-15 | Run trigger converts template into planned step runs saved as planned tasks | OK | AD-7 | `step_run` rows `planned`, one transaction, before enqueue. |
| A-16 | Templates like shell command lines / script executions (CI/CD-like) | OK | AD-9 | `run: <command>` + `uses: <kind>`. |
| A-17 | Track planned steps and status, linked to DBOS data | OK | AD-6, AD-7, AD-8 | `engine_ref` on run and attempt. |
| A-18 | Strict clean architecture | **PARTIAL** | AD-2 (backend only) | Enforced by import-linter in backend-api. **web-client has directory conventions but no enforced boundary** (nothing stops an island importing `astro:env/server` or fetching `BACKEND_API_URL` directly; AD-1's "islands never hold a backend credential" has no check). See D-4. |
| A-19 | TDD | **PARTIAL** | AD-18 | "tests exist first" is asserted, not checked. See B-3 / D-3. |
| A-20 | Coding guidelines picked from GUIDELINES.md | see §B | AD-17, AD-18, AD-19, Code quality | — |
| A-21 | Unit tests + independent E2E suites (API, UI) from project setup | OK | AD-18 | Two E2E suites, decoupled (`msw`-style stubs or `E2E_BACKEND=real`). |
| A-22 | AGENTS.md: one root + one per component | OK | companions, seed | Content rules for AGENTS.md are not in the spine; see D-5. |

A-4n (low): AD-4 introduces `ORCHESTRATOR_SESSION_SECRET` — a second secret next
to "the one credential". It is a signing key, not a login credential, so the
bullet is honoured; if the user wants literally one secret, derive the cookie
key from `ORCHESTRATOR_TOKEN` with HKDF and drop the variable. Optional.

---

## B. Chosen GUIDELINES principles not turned into an enforceable rule

The user chose four rules (memlog): (1) machine-checkable exits + maker ≠ checker;
(2) frozen anchors; (3) trajectory capture; (4) linter + formatter per stack.

### B-1 — maker ≠ checker: bound, never ruled  (**high**)

AD-18 *Binds* §1.6 but its *Rule* is entirely about test layering and fakes.
Nothing in the spine says who checks an agent's work or that the checker must
not be the maker:

- For **target-repo Runs**: the shipped `story@1` has a build step and a verify
  step (AD-19 mentions "its verify step"; memlog: "verify re-dispatch has its own
  counter"), but no rule prevents the verify `agent` step from **resuming the
  build session** (AD-10 exposes `resume(cwd, session_id, …)` and
  `capabilities.resume`). A resumed session *is* the maker checking itself —
  exactly what §1.6 forbids.
- For the **orchestrator's own development**: the only trace is "a review-layer
  rule in AGENTS.md" (AD-17), which concerns test assertions, not authorship.

Suggested rule (AD-10 or a new clause in AD-9 for kind `agent`):
"An `agent` step whose `role` is `verify`/`review` always starts a **new**
harness session — `session_id` is freshly assigned, `resume` is forbidden — and
receives the Story file plus the diff, never the build session's transcript.
`validate.py` rejects `resume: true` on such a step." Add to AD-18: "A story of
this repository is merged only after `bmad-code-review` (or a human) reviews
from a fresh context; the reviewer is never the author session." Only the first
half is machine-checkable; say so.

### B-2 — machine-checkable exits: enforced in practice, not stated  (**medium**)

The step machine (AD-8) exits on `expect miss / exit≠0 / timeout`, and AD-10 says
adapters "return nothing interpreted" — that *is* a machine-checkable exit. But
the spine never says the rule: "a step's `status` is derived only from exit code,
declared `expect`, timeout, and the Story file's status field; no step kind may
set `done` from model text." Add that sentence to AD-9 (StepResult) so a future
kind cannot parse "looks done" out of a log. Also state that `agent` steps'
turn/budget caps (FR-17, PRD) are the stop condition — one line, since §8 caps
were deliberately *not* adopted from GUIDELINES but are inherited from the PRD.

### B-3 — TDD as a checkable rule  (**medium**, also D-3)

AD-18: "a story is done only when its layer's tests exist first (TDD) and all
four pass." "Exist first" cannot be checked by `make lint` or CI; §5 says keep
constitution rules checkable. Restate as what *can* be checked, e.g.:
"every module under `src/orchestrator/{domain,application}` has a test module
under `tests/unit/…` (a script diffs the two trees); coverage of changed lines
≥ N% on the story's diff (`pytest --cov`, `vitest --coverage`)". Keep "write the
test first" as a *convention* line in AGENTS.md, explicitly labelled
not-enforced. (Coverage-of-changed-lines is §2.5.3's counter-metric — the user
did not choose §2.5.3, so present it as the minimal checkable proxy, not as a
new principle; a simple "test module exists" check is enough if they decline.)

### B-4 — frozen anchors: one anchor left non-deterministic  (**medium**)

AD-17 is solid for `SPEC.md`, `stories.yaml`, `epics.yaml`, `AGENTS.md`
(commit-guard, park `needs_you`, no automatic retry). The user's chosen list
also names **existing test assertions**; AD-17 demotes that to "a review-layer
rule in AGENTS.md, not a deterministic check". A cheap deterministic form
exists: treat existing files under `tests/**` (and `*.test.*`, `*_test.py`) as
**add-only per attempt** — new test files allowed, a modified or deleted
existing test file parks the Run with reason `existing test modified: {path}`.
Refactors of tests then need a human `continue`, which is the intended cost.
Add to AD-17 or explicitly keep it as a labelled non-enforced convention.

Secondary (low): the guard runs only inside `git.commit`. A template with no
commit step (pure shell/CI-like) never checks protected paths, and an `agent`
step that edits `SPEC.md` is only caught after the *next* agent step already
read the edited spec. Consider running the same diff at the end of every
`agent` step; it is one `Git.status` call.

### B-5 — trajectory capture  (**low**)

AD-19 is enforceable (append-only table, export endpoint). Two deltas from §10
worth a line each, no rule change needed:
- §10.1 makes the **merge** the provenance anchor (`human_signal`,
  `human_edits`, `reverted-later`). AD-19 records at Story `done`, before any
  merge, and forbids updates — so the merge signal can never be attached.
  Suggest a separate `trajectory_outcome` row (append-only) written later, or
  list "merge signal" under Deferred so the omission is deliberate.
- The record includes "attempts, gate results" but not the red→green sequence.
  Fine for MVP; note it as deferred.
- If the verify step was `skipped`, the record has no gate result; §10 says only
  fully green units are training-eligible. Add an `eligible` boolean or exclude
  skipped-verify stories from the export.

### B-6 — linter + formatter per stack  (**OK**)

Consistency › Code quality: ruff (lint+format), mypy strict on `domain/` and
`application/`, eslint + prettier + `tsc --noEmit`, all in `make lint`, and CI
order lint → unit → e2e-api → e2e-ui (AD-18). Enforced. Nothing to add.

---

## C. GUIDELINES principles NOT chosen that the spine nevertheless imposes

**None found.** Checked against the memlog's explicit non-adoption (§7/§8 tool
minimalism) and the rest of GUIDELINES:

- §2.5.3 counter-metrics (mutation score) — not imposed.
- §2.5.7 audit loop — not imposed.
- §3 allow-list / deny-list of inputs per agent — not imposed.
- §8 turn/budget caps, no-auto-retry — present, but sourced from the PRD
  (FR-17) and the user's frozen-anchor choice (AD-17 "no automatic retry"), not
  from GUIDELINES.
- §9 human gates at merge — `git.push` refuses the default branch (AD-14) and
  `pr.link` hands off; this comes from PRD FR-11, not GUIDELINES.
- mypy strict is a type checker, not a "linter+formatter" — a reasonable
  reading of the bullet, not scope creep from GUIDELINES (which never mentions
  it).

---

## D. Contradictions with strict clean architecture / TDD as §5 and §9 frame them

### D-1 — AD-8 cannot be followed literally  (**medium**)

AD-8 title: "Status is written only by use cases, **from inside an engine
step**." But:
- AD-13: routers call `signal_run`, which "appends the `gate_record`, then calls
  `engine.signal`" — a write outside any engine step.
- Run machine: `queued --> cancelled: cancel` happens while no walker step is
  running; only a router-driven use case can write it.
- Step machine has no edge for automatic re-dispatch: AD-7 says "re-execution is
  a new `attempt` on the same row", AD-9 has `next: Redispatch`, but the machine
  offers only `error --> queued: retry` (a human signal per AD-13) and no
  `done --> queued` at all (verify fails → build re-dispatched, but build is
  `done`).

Per §5 the constitution must describe reality. Fix AD-8 *Rule*: "…written only
by `application/` use cases through repository ports. Walker-driven transitions
happen inside an engine step; `signal_run` and `cancel_run` write from the
request path and then call `engine.signal`/`engine.cancel`." Add edges
`done --> queued: redispatch (on_fail, n < max)` and
`error --> queued: redispatch (retry, n < max)` to the step machine, and make
`gate_record` per-Run *and* per-redispatch explicit.

### D-2 — Declared bounded `retry` vs "no silent auto-retry"  (**medium**, verdict: acceptable with conditions)

GUIDELINES §8: "A failed loop flags a human; it does not silently re-enter the
queue." §9: "Failures flag a human and stop; nothing auto-retries." §2 defines
the goal-based loop as "evaluator confirms criteria, **or a turn cap hits**".

The DSL's `retry` / `on_fail.max` (surfaced in the spine as `StepResult.next:
Redispatch`, memlog "verify re-dispatch has its own counter") is the **turn cap
of the goal loop**, not a re-enqueue of a failed Run. That is the distinction
that makes it acceptable: the loop iterating until its evaluator passes is what
§2 prescribes; what §8/§9 forbid is a *finished-failed* unit quietly going back
into the queue. The spine already meets most conditions but states none of
them. Acceptable **iff** AD-9 (or AD-13) says:

1. The bound is declared in the **pinned, immutable template version** (AD-15) —
   the fast loop cannot raise its own cap (§2.5.4).
2. Every re-dispatch is a **recorded `attempt`** with a `gate_record`, visible
   in run detail and "What will run" — it is not silent.
3. Exhaustion transitions to `failed` or parks `needs_you`; **never**
   `engine.enqueue` again. (Run machine already has no `failed --> queued`.)
4. Some failures are **never** re-dispatched: protected-path hit (AD-17 already
   says so), budget halt (FR-17), timeout, and `blocked` (agent asked a
   question) — these park for a human immediately.

Also state that a human `retry` signal on `needs_you` is the only path back for
anything outside the declared bound. Without these four lines a reader of the
spine alone cannot tell the bounded loop from a silent retry.

### D-3 — TDD asserted, not checked  (**medium**) — see B-3.

### D-4 — Clean architecture is enforced in one component of two  (**medium**)

The paradigm line says "clean architecture (ports & adapters) **per
component**"; the enforcement (AD-2, import-linter) exists only for backend-api.
web-client has layout conventions (`islands/`, `components/`, `stores/`,
`api/`) and the security invariant "islands never hold a backend credential"
(AD-1) with no check. Under §5 an unchecked rule is aspiration. Minimal
enforcement to add under Consistency › Code quality (and reference from AD-1):
- eslint `no-restricted-imports`: `src/islands/**` and `src/stores/**` may not
  import `astro:env/server`, `node:*`, or anything under `src/pages/`.
- A `make lint` grep: `BACKEND_API_URL` / `ORCHESTRATOR_TOKEN` appear only in
  `src/pages/api/[...path].ts`, `src/middleware.ts`, and Astro Actions.
- Islands reach the API only through `src/api/client.ts` (same eslint rule:
  forbid bare `fetch(` outside `src/api/`).

### D-5 — Application code touches the filesystem without a port  (**medium**)

Strict ports & adapters: `application/` may import only `domain`. Yet:
- FR-15 map row: `application/steps/agent.py` "writes `project-context.md` via
  `Git`/**fs** port" — no `fs` port exists in the seed's port list
  (`ports/{engine,harness,git,process,gateway,tracer,clock,repositories}.py`),
  and `Git` has no read/write-file method (AD-14).
- AD-7: `for_each` "list files read once" during `plan_run` — a file read in
  `application/templates/plan.py`.
- FR-16: the Story file is "evaluated by `application/steps/agent.py`" — a file
  read.

Either these use `open()`/`pathlib` inside application (a leak import-linter
cannot see, since `open` is a builtin) or the port is missing. Fix: add a
`Workspace` port (`read_text(path)`, `write_text(path, text)`, `glob(pattern)`,
`exists`) to the domain port list, add its fake to `tests/unit/fakes/`, and
extend the AD-2 forbidden list with `pathlib`, `os`, `shutil`, `io` for
`domain/` and `application/` so the leak is at least partly lintable.

### D-6 — AGENTS.md at day 0 will describe an architecture that does not exist yet  (**low**)

§5: "describe reality, not aspiration". The three AGENTS.md are companions
drafted from the spine before any code. Add one rule (AD-18 or a new AD-21):
"AGENTS.md hard rules are exactly the checks `make lint` runs; everything else is
listed under *Conventions (not enforced)*. A rule enters the hard-rules section
only with the check that enforces it." This also gives the frozen-anchor
protection of `AGENTS.md` (AD-17) something concrete to protect.

### D-7 — Minor consistency nits  (**low**)

- AD-6 lists `attempt_record(engine_ref)` on the engine port but nothing says who
  calls it or in which layer; if the adapter calls back into a use case, name
  the use case so AD-8's "walker never touches repositories" holds.
- AD-19 fires when "verify is `done` or `skipped`"; combined with the `eligible`
  point in B-5.
- Capability map row FR-2..FR-4 reads "`steps` not involved" — fine, but the
  daily re-check via `engine.schedule` executes `infrastructure/git` from a
  scheduled job; state that it too goes through a use case, or AD-8/AD-14 are
  bypassed by the scheduler.

---

## Summary of suggested edits by location

| Location | Edit |
|---|---|
| AD-1 / seed | Name "orchestrator + harnesses = backend-api container"; add eslint boundary for islands (D-4). |
| AD-6 | One clause: why status truth is in app tables, not DBOS (A-8). |
| AD-8 | Rewrite *Rule* to cover request-path writes; add redispatch edges (D-1). |
| AD-9 | State the machine-checkable exit rule (B-2) and the four bounded-retry conditions (D-2). |
| AD-10 | Verify/review `agent` steps: fresh session, no resume; validator rejects (B-1). |
| AD-14 / port list | Add `Workspace` port; extend AD-2 forbidden imports (D-5). |
| AD-16 | Add the "no global install mode" reason from the memlog (A-11). |
| AD-17 | Existing test files add-only per attempt, or label as non-enforced (B-4); optionally guard after every `agent` step. |
| AD-18 | Replace "tests exist first" with checkable proxies; add reviewer ≠ author line; AGENTS.md hard rules = `make lint` checks (B-3, B-1, D-6). |
| AD-19 / Deferred | Merge-signal outcome row or explicit deferral; `eligible` flag (B-5). |
| Consistency › Code quality | web-client boundary lint (D-4). |
