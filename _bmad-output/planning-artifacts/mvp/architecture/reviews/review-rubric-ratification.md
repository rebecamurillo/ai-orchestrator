# Rubric review — ARCHITECTURE-SPINE.md ratification of 2026-09-15

- **Artifact:** `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` (updated 2026-09-15, working tree)
- **Driving source:** `_bmad-output/planning-artifacts/mvp/prd.md` — FR-8, FR-10, FR-13, FR-14, FR-17, FR-18, FR-20, §4.6, FR-25, FR-29, FR-33, FR-34, §5, §8 "Recorded 2026-09-15", NFR-6
- **Scope reviewed:** the four ratified deltas (AD-10 probe, AD-12 partition + saved + `after:`, AD-15 diagram/dot-index, AD-16 `ia-agents-skills/`) plus collateral (AD-8 dependent resolution, AD-11 optional budget, AD-13 `mode`/`start`/`dependency`, AD-14 stall detector, seed and map updates), checked against the exact working-tree diff.

## Verdict

**Approve with changes.** The ratification lands every PRD delta in the right AD, invents no status token, keeps the two-writer rule and the reason-text discipline, and its deliberate steps beyond the PRD (partition key spelled out, saved = `engine_ref` null, dependent resolution inside the terminal-transition writers, bracket↔dot bijection confined to web-client) are consistent with the PRD's letter and intent. But four gaps would let independently built units diverge or misbehave: the frozen Run state diagram now contradicts the dependency flow it sits next to; dependent resolution has no state guard and can double-enqueue; the Probe (and the installed-skill check) has no port, so the gate it creates is unreachable from the application layer under AD-2; and the partition key's branch value is ambiguous against AD-7's fresh-name allocation. None is expensive to fix; all should be fixed before the waved epics are cut.

**Counts:** Critical 0 · High 4 · Medium 8 · Low 7.

---

## Critical

None. Nothing in the amendment is unbuildable or silently unsafe once the High items are resolved; every gap below is a resolvable ambiguity or an unwritten guard, not a wrong decision.

---

## High

### H1 — The AD-8 Run state diagram was not updated and now contradicts AD-12/AD-13

The mermaid Run state machine in AD-8 still has only `queued → running`, `queued → cancelled`, `running → needs_you`, and `needs_you → running`. The ratified flow adds two transitions it cannot express:

- **`queued → needs_you`** — a saved dependent whose predecessor ends `failed | cancelled` is parked `park_kind = dependency` while it is status `queued` (AD-12: "failed | cancelled → dependent `needs_you`"). The diagram has no such edge, so the diagram and the rule text disagree inside the same AD pair.
- **`needs_you → queued` (or an equivalent "enqueued, not yet running")** — `continue` on a `dependency` park and the resolution path both do `engine.enqueue`; the Run does not go to `running`, it re-enters the queue (it may wait on `branch held by {run}` or `global concurrency`). The diagram's only exit from `needs_you` toward execution is `→ running`, and its edge label enumerates signals (`answer / continue / retry / …`) as if `continue` always yields `running`.

The status-machine diagrams are exactly the artifact a builder of `signal_run` / `apply_step_result` copies into tests. As it stands, a faithful implementation of the diagram rejects the dependency park (rubric 3 and 5 violation inside the spine itself). Fix: add the two edges and note on the `needs_you → running` edge that `continue` on `dependency`/`start` re-enqueues rather than runs.

### H2 — Dependent resolution has no state guard: double-enqueue and parking a running Run

AD-8/AD-12: "the writer applying a Run's terminal transition resolves its dependents in the same unit of work — predecessor `done` → `engine.enqueue(dependent)`; `failed | cancelled` → dependent `needs_you`, `park_kind = dependency`." The PRD (FR-13, FR-8) explicitly allows the Operator to start a saved Run *before* its `after:` fires ("started later by the Operator **or** … by the named Run reaching done"), and AD-13's `start` signal implements that. Nothing conditions the resolution on the dependent still being saved, so:

- predecessor `done` after the Operator already sent `start` → a second `engine.enqueue` for a Run that is enqueued, running, or even terminal;
- predecessor `failed` while the dependent is already `running` → the writer stamps `needs_you`/`park_kind = dependency` onto a running Run, a transition no machine or table admits (and it would collide with the walker's own writes);
- a dependent that was cancelled while saved would be enqueued or parked post-mortem.

Fix: one clause — resolution applies only to dependents that are still saved (`engine_ref` null and status `queued`); anything else is a logged no-op, mirroring the "cancelled Run absorbs late results" idiom already in AD-8.

### H3 — The Probe (and the installed-`skill:` check) has no port; the gate it creates is unreachable under AD-2

AD-10 now gates `create_run` and pre-flight on the live Probe ("read the Probe result … rejects a model outside the probed list"), and AD-16 adds "pre-flight verifies a `skill:` Step names an installed skill." Both checks live in `application/` use cases (`create_run`, `use_cases/preflight.py`), and AD-2 forbids `subprocess`/`os` there. But the `Harness` port protocol in AD-10 is unchanged — `{name, capabilities, run, resume, resume_command}` — no `probe()`, no model enumeration, no installed-skill listing; the probe is only "a verb on `scripts/harness/<name>.sh`" and a route. As written, the application layer has no legal way to reach the result it is required to gate on. This is the exact divergence the rubric asks about: the harness-adapter builder will put the probe behind the script, the `create_run` builder will need it behind a port, and the New-workflow island builder will read a third shape from `GET /harnesses`.

Fix: extend the port — e.g. `Harness.probe() -> ProbeResult{ok, failing_check: str | None, reason, models: [str]}` (adapter shells out to the script's `probe` verb) — and give the installed-skill check a named home (the same port, `Harness.installed_skills()`, or a small `SkillCatalog` port), with `GET /harnesses` and `GET /harnesses/{name}/probe` serving exactly `ProbeResult`.

### H4 — Partition key: "the plan's Working branch" is ambiguous against AD-7's fresh-name allocation

AD-12 keys the partition on `"{repository_id}:{branch}"` — "the plan's Working branch." Untouched AD-7 says `plan_run` "allocates **every branch a Template declares** a fresh name — the first ordinal `{branch}-{n}` the origin does not already hold — so two Runs of one Template never meet on one branch," and AD-14's refusal parenthetical leans on it ("the allocated name is fresh by construction, so only the declared one can collide"). If the partition key uses the **allocated** name, no two Runs ever share a key and the (Repository, branch) lock is vacuous — FR-13's `waiting: branch held by {run}` scenario becomes unreachable. Only the **declared** Working branch makes FR-13 implementable. The queue builder and the `plan_run` builder can legitimately read this either way today.

Fix: one word — "partition_key = the **declared** Working branch (the Run input / `epics.yaml` value), never an AD-7-allocated name." While there, state which of the two the `run.worktrees[].branch` entry records, since the held-branch refusal joins on it.

---

## Medium

### M1 — Amendments now read `run.engine_ref` in the application layer; untouched AD-6 forbids it

AD-6 (untouched): "`run.engine_ref` and `attempt.engine_ref` are JSON written and read **only by the adapter**." The ratification makes three application-layer readers: `start`'s validity condition ("`engine_ref` null"), `use_cases/queue.list_queue()` ("appends the saved Runs" — found by null `engine_ref`), and H2's needed guard. Either amend AD-6 to permit nullness tests (`engine_ref is null` as the saved predicate, contents still adapter-only), or give the domain a derived `run.is_saved` predicate owned by the repository port. As written the two ADs contradict each other and import-linter cannot arbitrate.

### M2 — Session-mode Answer/Retry: Attempt semantics unspecified

AD-13's `answer {mode: session}` and `retry {mode: session}` deliver into the recorded session via `Harness.resume`, with row transitions `blocked → queued` / `error → queued`. AD-8 says every `queued → running` goes through `start_attempt`, which creates a **new** `attempt` — but FR-20 phrases the contrast as "`restart` (**a new Attempt**, the mechanism above) or `session` (the recorded session resumes…)", implying session mode is *not* a new Attempt. This matters mechanically: spend attribution (AD-11) and `Gateway.spend_for_attempt` key on `ORCH_ATTEMPT_ID` from `env_for(attempt)`, and `Harness.resume(cwd, session_id, message, env)` needs an env for *some* attempt. State it once: session-mode resume is a new `attempt` row (new `n`, new `ORCH_ATTEMPT_ID`, spend attributed to it) that inherits the predecessor's `session_id`; `attempt.session_id` continuity is what "context kept" means.

### M3 — The stall detector's condition cannot be computed from `ProcessRunner.start`'s inputs

AD-14 puts both timers in the `ProcessRunner` and defines the stall as "the **expected Story file not created** and no file, commit, or log activity in the worktree for `n` minutes." `start(cmd, cwd, env, timeout_min?, stall_min?)` carries neither the expected-file globs (a template-level fact, `expect.files`) nor which log file counts as activity. Either drop the story-file clause from the port-level condition (activity-only stall, with the step's `expect` evaluated after exit as today), or extend the signature (`stall_watch: {globs, log_path}`). Otherwise the process-runner builder and the `agent`-executor builder will each hold half the condition.

### M4 — Never-enqueued Runs are outside the `recv`/cancel machinery the signals assume

The 30-day expiry is "applied by the walker" on the engine adapter's `recv human:{run_id}` — but a dependency-parked dependent and a saved Run were never enqueued: no workflow, no `recv`, no walker. So (a) a `dependency` park can sit forever with no expiry (PRD NFR-1 says a Run may park 30 days — silent immortality here is at least undocumented), and (b) `cancel` on a saved or dependency-parked Run calls `engine.cancel(run_id)` with nothing to cancel — the adapter must treat a null `engine_ref` as a no-op, which is nowhere stated. Also state that a `dependency` park writes `park_kind` with **null `park_path`** (the table implies it — skip validity keys on `park_path` — but the Structural Seed does not say the field is nullable for this kind). One sentence per case closes all three. Related: the 30-day-expiry `failed` write itself is attributed to "the walker," which AD-8 says only reads — name the use case that applies it, since per the new rule that writer must also resolve dependents.

### M5 — Probe freshness between the form and `create_run` is unspecified

AD-10: "`create_run` and pre-flight **read the Probe result**… nothing re-probes after create." Read from where? There is deliberately no stored flag, so either `create_run` runs a fresh probe inline (then FR-8's "pre-flight runs on every field change" implies a CLI probe per keystroke — probably unintended), or a recent `GET /probe` result is trusted (then a TTL and holder must exist, which starts to look like the stored flag the delta abolished). Pick one: e.g. "pre-flight reads the last `GET /probe` result the form obtained; `create_run` re-runs the probe inline, once, at create — that is the result 'nothing re-probes after' refers to."

### M6 — The held-branch pre-flight refusal races with an initiative that has not reached that epic yet

AD-12 explicitly delegates the initiative's per-epic branches to "AD-14's held-branch pre-flight refusal, not… the key." AD-14's refusal checks branches "held by a **worktree** of a non-terminal Run" — but an initiative Run materialises epic 2's worktree only when it reaches it. An `epic` Run created on the same declared branch in that window passes pre-flight, and the guard the ratification points at never fires. The planned rows exist from `create_run` (AD-7), so the fix is cheap: the refusal checks the **declared branches of `git.worktree` rows of every non-terminal Run**, not only materialised worktrees.

### M7 — `harness.enabled` survives with badge semantics under a gate's name

The seed keeps `harness{name, enabled, …}` and AD-10 now calls the row "an informational badge read by no gate." A column named `enabled` on the harness table is precisely the stored flag FR-33 demoted; a builder wiring the New-workflow island (or a later maintainer of `GET /harnesses`) will filter on it by reflex. Rename it (`readiness_ok`, `badge_green`) or annotate the column itself, not just the AD prose.

### M8 — `prompt` + `prompt_file` together: PRD-legal, seed-silent

PRD FR-5 (amended): "`prompt:`/`prompt_file:` (inline text **and/or** a path…; the two prompt keys **may combine**)." The new seed row says "exactly one of `skill {…}` or `prompt` / `prompt_file`" and "neither or both **dispatch forms** is a validation error" — correct at the form level, but silent on whether `prompt` and `prompt_file` may coexist within the form and, if so, in what order `compose_prompt` concatenates them. The validator builder and the `compose_prompt` builder can diverge. Add: both keys may coexist; `compose_prompt` emits `prompt` then the `prompt_file` content (or the chosen order — but choose it here).

---

## Low

### L1 — `gate_record.event` now has two meanings of `start`

AD-8's event vocabulary is "the `Park.kind` for machine stops, the `Signal.kind` for operator actions, plus `start`, `done`, `failed`, `cancelled`." The new `start` Signal makes `start` both "the Run began executing" and "the Operator started a saved Run." A gate-record reader (or FR-25 history) cannot distinguish them. Rename one (e.g. Signal `start` records as `started_by_operator`, or the transition event becomes `run_started`).

### L2 — Binds lines not extended

AD-13 still binds "FR-16..FR-21" though it now carries `start` (FR-8/FR-13) and `dependency` (FR-13); AD-8 binds "FR-10, FR-16..FR-20, NFR-2" though dependent resolution is FR-13. The Capability Map is correct; the AD headers lag it.

### L3 — Dot-index bijection: numeric slugs would break it; and it has no named home

`epics.0.stories.3.build ↔ epics[0].stories[3].build` is a bijection only if no step `id` slug is purely numeric (a step id `2` makes `stories.2` ambiguous). The validator's `slug` type should exclude all-digit ids — one clause in the seed. Also "the bijection lives in web-client only" names a component, not a module; with both `RunDiagram` (encode) and the step page (decode) needing it, name one util so two converters don't grow.

### L4 — Claude adapter's `--max-budget-usd` with a null budget

AD-11 makes `budget_usd` nullable; AD-10 still says the Claude adapter "additionally passes `--max-budget-usd` = remaining budget" unconditionally. Remaining budget is undefined when `budget_usd` is null — state that the flag is omitted then.

### L5 — Row-transition cells for `continue` on `plan_stale` and `dependency` are silent

The `continue` row's transition column lists checkpoint and `protected_path` outcomes only. `dependency` has no row ("none" belongs in the cell), and `plan_stale`'s `plan.check` row transition on continue (presumably `error → done`, plan proceeds) is unstated.

### L6 — Queue reason `global concurrency, held by {runs}`

AD-12's reason set `{…, global concurrency, held by {runs}, …}` reads as two reasons where PRD FR-13 shows one composed text ("waiting: global concurrency, held by {runs}"). Brace it as one member or two; the set is otherwise the FR-25 + FR-13 union, correctly including `waiting for run {x}` and `saved — not started`.

### L7 — `k/n steps` producer unassigned

AD-15: a group box's "`k/n steps` is a count over its rows" — counted by `graph.py` (into the `groups` payload) or by the island? Counting within one response doesn't violate the no-joins convention, but naming the producer keeps the graph payload contract stable. (PRD FR-29 note: the spine's node-token list omission of `DON` variants is fine — FR-29's token list `QUE RUN BLK CHK ERR DON SKP` is matched by "stored tokens" + group rule.)

---

## Rubric answers in brief

1. **Divergence points fixed, none missed?** Mostly fixed: saved-state representation, dependency writer, reason-text set, diagram token source, route/path forms, and the DSL dispatch forms are each pinned to one owner. Missed: H2 (resolution guard), H3 (probe port), H4 (which branch string), M2 (session-resume attempt), M3 (stall inputs), M5 (probe freshness), M8 (prompt-key combination) — each is a spot where two builders can still choose incompatibly.
2. **Every amended Rule enforceable?** AD-11, AD-12 (modulo H4), AD-13 (modulo H1/H2 wording), AD-15, AD-16 (modulo H3's port) are checkable as written. AD-10's gate is not enforceable until the probe is behind a port; AD-14's stall clause is not computable from the declared signature.
3. **Contradictions with untouched ADs / seeds?** Two: the AD-8 Run state diagram (H1) and AD-6's engine_ref-adapter-only rule (M1). Status vocabularies are clean — no new token anywhere, saved and dependency states are reason texts and `park_kind` respectively; the two-writer rule is extended explicitly, not broken.
4. **Agreement with the PRD; deliberate extensions consistent?** Yes. Partition-for-initiative-on-base, `engine_ref`-null-as-saved, in-writer dependent resolution (the PRD's "by the scheduler" in FR-13 is superseded by a stronger mechanism that satisfies its observable contract — worth a parenthetical), and the web-client-only bijection all refine rather than contradict. §4.6's table matches AD-13's admitted-signal and reason sets exactly, including skip exclusions on `budget`/`plan_stale`/`dependency` and push_rejected's skip_story exclusion.
5. **AD-13 table internal consistency?** Good except: the `start` row's validity is a field predicate, not a status, and its event name collides (L1); dependency parks need the null-`park_path` statement and the no-`recv` expiry/cancel story (M4); `continue`'s transition cell is incomplete (L5). The `mode` machinery is consistent across answer/retry (`reply_available` defined once, in AD-10) apart from the attempt-semantics gap (M2).

## Recommended edit order

H1, H2, H4 are wording-level fixes in AD-8/AD-12 (half a day, no design). H3 is the one real design addition (a port method and a result shape) and should land before the FR-33/FR-8 epics are cut. M1–M8 fold into the same editing pass; the Lows can ride along.
