# Adversarial review — ARCHITECTURE-SPINE.md, 2026-09-15 ratification

- **Target:** `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` (updated 2026-09-15)
- **Scope attacked:** AD-8 (dependent fan-out), AD-10 (live Probe), AD-11 (optional budget), AD-12 ((repository, branch) partition, saved Runs, `after_run_id`), AD-13 (`mode`, `start` signal, `dependency` park), AD-14 (stall detector), AD-15 (embedded diagram, `k/n`, dot-index), AD-16 (`ia-agents-skills/`), seed tables
- **Method:** for each finding, two constructions one level down that each obey every AD to the letter yet build incompatibly (or a state neither writer can legally produce), then the minimal tightening that closes it.
- **Severity:** S1 critical (two conforming builders produce incompatible or unsound systems on a mainline path) · S2 major (incompatible on a reachable path, or a rule contradicts another AD) · S3 minor (edge path, both constructions defensible, one is wrong) · S4 nit.

**Counts: S1 ×4 · S2 ×6 · S3 ×4 · S4 ×3 — 17 findings.**

---

## S1 — critical

### S1-1 · A saved Run with `after_run_id` can be started twice: `start` signal and predecessor-`done` fan-out race, and `engine.enqueue` idempotency is nowhere stated

**The rules, to the letter.** AD-13: `start` is valid whenever `engine_ref` is null; `signal_run` writes a gate record and calls `engine.enqueue`. AD-12/AD-8: the writer applying the predecessor's terminal transition resolves dependents *in that writer's unit of work* — predecessor `done` → `engine.enqueue(dependent)`. These are two different units of work (the router's request UoW for `signal_run`; the engine adapter's step UoW for `apply_step_result`). Both read `engine_ref` null, both are entitled to enqueue. Nothing serialises them, and AD-6 declares `enqueue(run_id, partition_key)` with no idempotency contract (`engine_ref` is opaque JSON written by the adapter — *after* the enqueue).

**Two conforming constructions.**
- *Builder A* keys the DBOS workflow on `run_id`, so the second `enqueue` is a same-id no-op. Conforms (AD-6 says nothing about workflow identity).
- *Builder B* starts a fresh engine workflow per `enqueue` call and stores its id into `engine_ref`. Also conforms. Under the race, B produces **two walkers over one Run**: both call `start_attempt(run_id, seq=0)`, two `attempt` rows race `mark_started`, two harness processes share one worktree. Every individual write still goes through the two blessed writers, so AD-8 is satisfied while the system is unsound.

Note `plan.check` does not save B: it checks list-file drift, not double execution.

**Minimal tightening.** Two sentences in AD-12: (a) *"`engine.enqueue` is idempotent on `run_id`: the adapter derives the workflow identity from `run_id`, so a second enqueue of the same Run is a recorded no-op."* (b) *"`start` on a Run with `after_run_id` set clears `after_run_id` in the same unit of work; dependent resolution skips a Run whose `after_run_id` is already null."* (Either sentence alone closes the double-walker; both close the double-gate-record too.)

### S1-2 · The (repository, branch) partition wedge is real: a queued/saved initiative on base `A` declaring branch `B` slips past the held-branch refusal, then collides with a live epic Run on `B` — in the *same worktree directory*

**The wedge, precisely.**
1. `t0` — initiative Run I is created (or saved): base `A`, key `{repo}:{A}`; its plan's `epics[0]` `git.worktree` row was *declared from* `B` (or will create `B`). At `t0` nothing holds `B`; pre-flight passes. I queues behind `MAX_ACTIVE_RUNS` (or is saved).
2. `t1` — epic Run E is created on Working branch `B`, key `{repo}:{B}`. AD-14's refusal fires only when the declared branch "is held by a **worktree** of a non-terminal Run" — i.e. an entry in some `run.worktrees[]`. I has not executed its `git.worktree` row, so `I.worktrees[]` is empty. E passes pre-flight (at most the FR-8 shared-*repository* warning, which the Operator confirms). E starts on `B`.
3. `t2` — I dequeues (keys differ, so the partition does not serialise them) and reaches `epics[0].git.worktree` for `B` **while E is mid-flight on `B`**. Nothing re-checks at dequeue — the refusal is a create-time pre-flight rule only, exactly as the spine writes it.

And the collision is worse than a logical race: AD-14 fixes worktrees at `/work/{project}/{repo}/wt/{branch}` — keyed by *branch alone*, despite the heading "one worktree per (Run, branch)". So I's `git.worktree` finds E's **live** worktree at `wt/B` and, per the rule, *reuses it when clean* — two Runs, one working tree, one `.git/index`. ("Refuse when dirty" is the lucky path, and even that refusal maps to no enumerated park kind.)

**Two conforming constructions.** *Builder A* reads "held by a worktree of a non-terminal Run" generously and also scans the *planned* `git.worktree` rows of queued/saved Runs — closes the window at `t1`, but exceeds the written rule. *Builder B* implements the letter (scan `run.worktrees[]` only) — wedge above. Both conform; only one is sound.

**Minimal tightening.** In AD-14: (a) extend the refusal to *"…is held by a worktree **or declared by a `git.worktree` row** of a non-terminal Run"* (plans are materialised `step_run` rows, so this is one indexed query, still create-time and pure); (b) make the executor the backstop: *"`git.worktree` parks `misconfigured: branch held by {run}` when `wt/{branch}` is registered in another non-terminal Run's `worktrees[]`"* — this converts the residual race (two creates passing pre-flight simultaneously) into a park instead of a shared index.

### S1-3 · `mode: session` on answer/retry has no Attempt identity: spend, SHAs, and the protected-path check are unowned for the resumed execution

**The gap.** AD-13 `answer`/`retry` with `mode: session`: "`Harness.resume` delivers … nothing archived, no re-plan"; row `blocked → queued` / `error → queued`. AD-10 declares `resume(cwd, session_id, message, env)` — with **no return type** (`run` returns `HarnessResult`; `resume` returns nothing stated). AD-8's recording protocol (`mark_started` with `start_sha`/`pgid` before `wait`, `mark_finished` with `end_sha`/`usage` after exit) is written for the *dispatch* path. AD-17 checks "agent ranges" `(start_sha, end_sha)` per attempt. AD-11 charges spend per `attempt_id` via `x-litellm-session-id: <attempt_id>` from `env_for(attempt)`. The spine never says whether a session resume is a **new Attempt or the continuation of the old one** — and everything downstream keys on the answer.

**Two conforming constructions.**
- *Builder A*: session resume is a new Attempt `n+1` — new `start_sha = HEAD`, `env_for(new attempt)`, own spend rows, own protected-path range. Conforms (AD-10's "no row ever resumes another row's session" is satisfied: same row).
- *Builder B*: session resume *continues* the parked Attempt — no `mark_started` (it already ran), `end_sha` overwritten on exit, spend accrues under the **old** `ORCH_ATTEMPT_ID`, the protected-path check re-runs over the widened `(old start_sha, new end_sha)` range. Also conforms — AD-9's "each is a recorded attempt" clause covers only *template* retry and redispatch, not the Signal.

A and B disagree on: `attempt` cardinality, which attempt the resumed model calls bill to, whether `Gateway.spend_for_attempt` after the resume finds anything, what `trajectory` counts as "agent attempts", and which SHA range AD-17 inspects. If B skips a fresh `mark_started`, a crash during the resume also breaks FR-12 recovery (no recorded `pgid` for the new process).

**Minimal tightening.** One sentence in AD-10 + one in AD-13: *"`Harness.resume` returns a `HarnessResult` like `run`."* And: *"A `mode: session` answer or retry is a **new Attempt** on the same row: `n+1`, `session_id` copied from the resumed Attempt, `start_sha = HEAD` at delivery, `env_for` of the new Attempt; `mark_started`/`mark_finished`, the protected-path check, FR-16 routing, `Gateway.spend` and the budget rule run exactly as after a dispatch."* (The prepare-commit is legitimately skipped — nothing was written — but `start_sha` must still be recorded.)

### S1-4 · Signalling a Run that was never enqueued: `signal_run`'s "calls `engine.signal`" contradicts the `dependency`/`start` rows, and the `dependency` park itself is a state the Run status machine cannot legally enter

**Three letter-level contradictions stacked on one path.**
1. AD-8: `signal_run` "…applies the transition, clears `park_*`, **then calls `engine.signal`**" — stated generally. AD-13's `continue`-on-`dependency` row instead says "**`engine.enqueue` — start anyway**", and `start` says `engine.enqueue`. A dependency-parked Run has `engine_ref` null: **no walker exists, no `recv` waiter on `human:{run_id}`** — `engine.signal` has nothing to deliver to.
2. AD-12: predecessor `failed | cancelled` → dependent `needs_you`, `park_kind = dependency`. The dependent is a *saved* Run: status `queued`. The Run state diagram has **no `queued → needs_you` edge** (only `running → needs_you: park`). So the fan-out writer performs a transition the published machine forbids — and `signal_run`'s own "validates the signal against the current status (409 otherwise)" has no row to validate `continue` against.
3. After `continue` on `dependency`, the Run is enqueued — possibly behind the partition or the global slots. Is it `needs_you → running` (the only `continue` edge in the diagram) while actually waiting in the queue, or `needs_you → queued` (no such edge)? Neither is writable by the letter.

**Two conforming constructions.** *Builder A* implements AD-8's general sentence: `signal_run` uniformly ends in `engine.signal` — on a dependency park this either raises inside DBOS or silently `send`s to a nonexistent workflow; the Run is stuck in `needs_you` forever. *Builder B* special-cases `dependency` and `start` to `enqueue` and invents the `queued → needs_you` / `needs_you → queued` edges. Both can cite the spine.

**Minimal tightening.** In AD-8, qualify: *"…then calls `engine.signal` — except the `start` Signal and `continue` on a `dependency` park, which call `engine.enqueue` (the Run was never in the engine)."* Add two edges to the Run diagram: `queued --> needs_you: predecessor failed/cancelled (dependency)` and `needs_you --> queued: continue on dependency (enqueued)`. Three lines total.

---

## S2 — major

### S2-1 · A saved Run started weeks later is never re-probed: model and CLI-version drift pass every gate

AD-10: "`create_run` and pre-flight read the Probe result … `create_run` rejects a model outside the probed list with 422 … **on every create** … **nothing re-probes after create**." AD-13's `start` is not a create. So a Run saved in week 1 and started in week 5 — after `sync_pins()` registered a CLI version bump ("the Probe's version check is what refuses a drifted CLI" — but no gate runs the Probe here), or after the gateway's model list dropped the pinned model — enqueues without any check. *Builder A* treats `start` as create-adjacent and re-probes (helpful, but violates "nothing re-probes after create"). *Builder B* obeys the letter and dispatches a harness at an unpinned version, failing at runtime as `misconfigured: harness exit {code}` with no diagnosis — and note `misconfigured`'s reason list has no `harness version drifted` / `model unknown` text. The sentence "Queued and parked Runs keep their harness and resume on it" was written for the *enqueued* population; a saved Run is neither queued-in-engine nor parked, and the spine doesn't say which regime it belongs to.

**Tightening.** One clause in AD-10 or AD-13's `start` row: *"`start` re-reads the Probe exactly as `create_run` does (same 422s, model list included); it is the one exception to 'nothing re-probes after create'."* (Alternative — declare saved Runs dispatch as-pinned and add the two `misconfigured` reason texts — but the Probe exists precisely to put the reason in front of the Operator before the queue, so re-probe is the smaller change.)

### S2-2 · The stall detector's three inputs cannot all be computed by `ProcessRunner`, and its applicability to `shell` is decided by the caller, not the rule

AD-14 puts `stall_min` in `ProcessRunner.start(cmd, cwd, env, timeout_min?, stall_min?)` and defines stall as "the **expected Story file** not created and no **file, commit, or log** activity in the worktree for n minutes". But: the expected Story file comes from the Template's `expect.files` glob — application-layer knowledge with **no parameter in `start()` to carry it**; "commit activity" is `Git`'s domain; "log activity" means `attempt.log_path`, which the ProcessRunner does own. *Builder A* watches only child stdout/stderr (log growth) — pure, but the Story-file and commit clauses are enforced nowhere. *Builder B* recursively stats `cwd` and polls `.git/HEAD` inside the process adapter — duplicating `Workspace`/`Git` knowledge in a second place (AD-2's *spirit*; the letter allows it since infrastructure may do I/O) and still cannot evaluate "expected Story file not created". Separately: the shipped-kinds table gives `shell` a 30-min timeout and no stall, and AD-14 says stall is "the default liveness signal **for `agent` rows**" — but nothing forbids passing `stall_min` for `shell`, so builder A's long-quiet `install_command` survives and builder B's is killed. Finally, `wait`'s return carries no stall/timeout discriminant, so a stalled kill (SIGKILL, exit −9) is indistinguishable from a crash unless the adapter invents a flag.

**Tightening.** In AD-14: *"`stall_min` is passed only by the `agent` executor, never for `shell`. The ProcessRunner's stall signal is exactly: no mtime change under `cwd` (`.git` included, which covers commits) and no growth of the process log for n minutes; `wait` returns a result discriminated `{exited(code) | timed_out | stalled}`. The 'expected Story file' clause is evaluated by the `agent` executor when composing the park reason, not by the ProcessRunner."*

### S2-3 · `k/n steps` is uncomputable from the text: skipped rows, checkpoint rows, and plan-time skips make three defensible counts

AD-15: the group's "`k/n steps` is a count over its rows" — neither k nor n is defined. A story frame planned with 6 rows of which 2 are `skipped · no command`, at completion 4 `done`: *Builder A* renders `k = done|skipped, n = all` → **6/6** (visually "complete", brushing against "`skipped` … never green"); *Builder B* renders `k = done, n = rows not skipped at plan time` → **4/4**; a third defensible read gives **4/6** forever. All satisfy "a count over its rows". Two builders' diagrams disagree on every loop group.

**Tightening.** One sentence: *"`k` counts rows with stored status `done`; `n` counts the group's rows whose status is not `skipped`; a group whose rows are all `skipped` shows no count."*

### S2-4 · `ia-agents-skills/` vs BMAD stubs: name collisions are resolved by copy order, and the pre-flight "installed skill" check has no port to read the image with

Two sub-holes in AD-16. (a) The image copies the BMAD stubs **and** `ia-agents-skills/` into the same `~/.claude/skills` / `~/.agents/skills`. An operator folder named `bmad-build-auto` silently wins or loses depending on which `COPY` runs last — two Dockerfile authors, two behaviours, both conforming. (b) "pre-flight verifies a `skill:` Step names an installed skill — `validate.py` stays pure": pre-flight lives in `application/` (AD-2: no `os`, no filesystem), `Workspace` is rooted at a Run worktree (and unavailable at pre-flight time), `Harness` has no skill enumeration, and `harness{…}` the table stores no skill list. *Builder A* adds `installed_skills()` to the Harness port; *Builder B* bakes a manifest file at image build and reads it through settings; *Builder C* shells out from the router. All "conform"; the check joins against three different sources of truth.

**Tightening.** In AD-16: *"The image build **fails** on a name collision between the stub set and `ia-agents-skills/`. It writes `/app/skills-manifest.json` (the union, per harness home); a `SkillCatalog` port (or `Harness.installed_skills()`) exposes it read-only; pre-flight's installed-skill check reads exactly that manifest."*

### S2-5 · The 30-day expiry has no waiter on walker-less parks, and its writer is neither of the two writers

"parked 30 days (recv expiry) … expiry is applied **by the walker** as Run `failed`". A dependency-parked Run (and a saved Run, if one counts `saved — not started` as parked-adjacent) has **no walker and no `recv`** — its 30 days never elapse anywhere; *Builder A* assumes uniform expiry and reports it in the queue UI, *Builder B* knows no timer exists — the Run waits forever. Worse: even on the normal path, the walker applying `failed` on recv-timeout is a Run transition performed by **neither `apply_step_result` (no `StepResult` exists) nor `signal_run` (no Signal arrived)** — AD-8's own two-writer letter is broken by AD-13's parenthetical. And since expiry-`failed` is a *terminal* transition, AD-8's "dependent resolution belongs to whichever of the two writers applied the terminal status" has no owner for the fan-out.

**Tightening.** In AD-8/AD-13: *"Recv expiry is applied through `apply_step_result` with the reserved result `expired` (so it is the execution writer, fan-out included). Parks written outside any step (`dependency`) do not expire; the queue row keeps its reason until the Operator acts."* (Or a scheduled job that routes through `signal_run` with a system Signal — pick one and name it.)

### S2-6 · Terminal fan-out couples a DB commit to an engine call with no atomicity statement

AD-8/AD-12: the terminal writer resolves dependents "in the same unit of work — predecessor `done` → `engine.enqueue(dependent)`". `engine.enqueue` is a port call into DBOS. *Builder A* enqueues inside the open transaction (DBOS queues live in the same Postgres, so this can be genuinely atomic — but only if the adapter shares the connection/transaction, which AD-6 neither requires nor mentions). *Builder B* commits the UoW then enqueues — a crash between the two silently strands the dependent as a saved Run forever (`engine_ref` null, `after_run_id` pointing at a Run already `done`; no poller exists by design, AD-12 "prevents: a dependency poller"). The reverse order ghost-enqueues a dependent whose gate record rolled back.

**Tightening.** One sentence in AD-12: *"The adapter's `enqueue` participates in the caller's unit of work (DBOS queue insert on the same connection); dependent resolution is therefore atomic with the terminal transition."* If the adapter cannot share the transaction, mandate the S1-1 idempotent enqueue plus a startup sweep: *"on launch, enqueue every Run whose `after_run_id` names a `done` Run and whose `engine_ref` is null."*

---

## S3 — minor

### S3-1 · `start` is valid on a dependency-parked Run, giving it two contradictory admitted signals

`start`'s validity is "`engine_ref` null" — true of a dependency-parked Run too, whose §4.6 contract admits only *Continue / Cancel*. *Builder A* accepts `start` there (writes a gate record, enqueues, but never clears `park_kind = dependency` — the table's writes don't include it — leaving a Run that is enqueued **and** `needs_you`); *Builder B* 409s citing the PRD table. **Tightening:** `start` valid when *"`engine_ref` null **and** status `queued`"*.

### S3-2 · `cancel` on a saved or dependency-parked Run dereferences things that don't exist

`cancel` "any non-terminal" runs `ProcessRunner.kill_group(attempt.pgid)` — no attempt exists — `engine.cancel` — no engine workflow — and iterates `run.worktrees[]` — empty, fine. *Builder A* guards each effect; *Builder B* crashes the request on the first `None`. **Tightening:** one clause: *"each of `cancel`'s effects is a recorded no-op when its referent (attempt, engine workflow, worktree) does not exist."*

### S3-3 · `--max-budget-usd` with `budget_usd` null

AD-10: the Claude adapter "additionally passes `--max-budget-usd` = remaining budget"; AD-11 makes `budget_usd` nullable. Remaining budget is then undefined: *Builder A* omits the flag (uncapped — correct spirit); *Builder B* passes `0` (every attempt halts instantly as park `budget` — on a Run whose budget rule "is a no-op"). **Tightening:** *"when `budget_usd` is null the flag is omitted."*

### S3-4 · `plan.check` at deferred start covers list files only — a Story done in the interim re-runs

A saved Run started weeks later re-checks only "every list file at the branch head vs `plan_ref`". The `skipped · already done` decisions were taken at `plan_ref`; a Story that reached `done` on the branch since then (by another Run on a different branch later merged, or by hand) is re-dispatched — `bmad-build-auto` will likely halt on the status, parking `misconfigured: unexpected status`, which is survivable but noisy, and two builders will argue whether `plan.check` "should" have caught it. **Tightening:** either extend `plan.check`'s comparison to the frames' Story-file statuses, or (cheaper) add one sentence to AD-7 stating the exposure is accepted and `misconfigured: unexpected status` is its designed landing.

---

## S4 — nit

### S4-1 · The colour dialect never maps stored tokens to its five colours

"done green, running blue, error red, waiting amber, scheduled grey" — is `queued` *waiting* (amber) or *scheduled* (grey)? Is `blocked` red-adjacent or amber? Two diagrams disagree. **Tightening:** an explicit token→colour table: `done`→green, `running`→blue, `error`→red, `blocked | checkpoint`→amber, `planned | queued`→grey, `skipped | cancelled`→faint grey.

### S4-2 · The dot-index bijection breaks if a step id is numeric

Step `id` is a "slug"; if slugs admit `0`, then `epics.0.build` is ambiguous between `epics[0].build` and a step literally named `0`. Same for the `before`/`after` checkpoint suffixes if an operator names a step `before`. **Tightening:** `validate.py` rejects step ids that are all digits or in `{before, after}`.

### S4-3 · "pre-flight runs on every field change" now includes a live Probe

Each keystroke in New workflow re-reads `GET /harnesses/{name}/probe`, which shells `doctor` (CLI invocation, credential check, gateway round-trip). **Tightening:** note that the form probes on harness selection and on submit, and `create_run` re-reads it server-side; field changes elsewhere re-run pure `plan_run` only.

---

## What survived attack (for the record)

- The `plan_stale` first row genuinely closes the stale-saved-plan hole for *list files* (S3-4 is the residue).
- `budget_raise`'s no-`engine.signal` exception is internally consistent: the Run stays `needs_you`, the earlier gate record remains the Question.
- AD-17's session-resume exposure is closed **iff** S1-3 lands the new-Attempt reading; with builder B's reading it re-opens (widened ranges spanning an operator `spec: operator edit` are still excluded only because `PUT /files` requires `needs_you` — which is exactly the parked window — so B would false-park on the operator's own edit; one more reason S1-3's fix must pick A).
- The fresh-ordinal branch allocation of AD-7 does make allocated-name collisions impossible; only the *declared*-branch path (S1-2) is exposed.
