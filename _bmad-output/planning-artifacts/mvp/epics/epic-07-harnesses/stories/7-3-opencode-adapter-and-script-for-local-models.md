---
title: 'OpenCode adapter and script for local models'
type: 'feature'
created: '2026-09-10'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred: []
baseline_revision: '4599955cd19c16b297944a78205b39dc961b4226'
---

<intent-contract>

## Intent

**Problem:** `local` is the third name `HARNESS_NAMES` declares and the only one with no adapter,
so an open-weight model served on the host is a plan and not a cost lever — nothing can dispatch
to it, nothing can find its calls under the Run, and nothing records its tokens at zero cost.

**Approach:** Add `infrastructure/harness/opencode/` — the `opencode run --format json`
invocation, the session id read from the stream with the session store as its fallback,
`local_aliases` for the two names `scripts/harness/opencode.sh` declares — plus a `local` branch
in `attempt_observed` that finds the plugin's generations by `userId == run_id` inside the
attempt's own window, and the tests that pin all of it.

## Boundaries & Constraints

**Always:** AD-10 (the adapter interprets nothing beyond the harness's own framing: session id,
exit code, usage, log path, `raw_result` verbatim; static configuration is `opencode.sh`'s and no
adapter writes under `AGENT_HOME`); AD-14 (`start` hands back the group before anything waits on
it, `wait` kills the group if it raises); AD-11 (`local` is found by user and session, never by a
parented span — it receives `TRACEPARENT` and exports nothing under it); AD-5 (`env_for` receives
no credential the contract does not already carry); AD-2; a module is at most 400 lines and a
capped module is **split**, never trimmed; new coverage goes in new test files only.

**Block If:** landing the story requires editing an existing test file, `SPEC.md`, `stories.yaml`,
`epics.yaml` or any `AGENTS.md` — with one exception already ruled on for this epic: the harness
*registry* assertions bound to `HARNESS_NAMES` in story 7.1.

**Never:** running the real OpenCode CLI or a real local model server (7.4 owns both); shipping a
value only a live run could confirm as if it were verified — every `[verify]`/`[ASSUMPTION]`
marker in the brief is implemented as the documented shape, marked provisional in a code comment
per `addendum.md` §B, and listed in the hand-back; parsing model output; writing
`~/.config/opencode/opencode.json` from Python; reading the other stories' briefs.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First dispatch | worktree, prompt, model, log path | `opencode run --format json --dir <worktree> -m litellm/<model> "<prompt>"`, prompt last | No error expected |
| No model bound | `model=None` | `-m litellm/<first LOCAL_MODELS alias>` | No error expected |
| Session in the stream | an object carrying `sessionID` | `HarnessResult.session_id` is that id | No error expected |
| Session absent | stream names none, store holds a session for the worktree | the store's newest matching id | No error expected |
| Store absent/unreadable | no db file, no table, a locked file | `session_id` is `None` | Logged, never raised |
| Usage | an object carrying `tokens.input`/`tokens.output` | `HarnessUsage(tokens_in, tokens_out, cost_usd=0)` | Missing/partial → `usage=None` |
| Aliases | the contract | `LANGFUSE_BASEURL`, `LANGFUSE_USER_ID == ORCH_RUN_ID`, and no third name | No error expected |
| Resume | `capabilities.resume` is `False` | `resume_command` is `None`; `resume` raises rather than starting a new session silently | Never called (`agent.py` gates on the capability) |
| `attempt_observed` local | one observation, `userId == run_id`, `start_time` inside the window | `True`, logged `path=user` | No error expected |
| `attempt_observed` local | another user id, or a time outside the window, or no window | `False` | Query failure logged, never raised |
| Spend | Gateway rows with `spend 0` and tokens | `cost_usd == 0`, tokens set, `cost_provisional` `False` | No error expected |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- the adapter shape this
  one mirrors: `run = wait(start(...))`, guarded `wait`, `_record_prompt`, `<name>_aliases`.
- `backend-api/src/orchestrator/infrastructure/harness/jsonl.py` -- `read_text`, `json_objects`,
  `objects_with`, `as_int`. **Reuse; do not write a second parser** (7.1 landed it for this).
- `backend-api/src/orchestrator/infrastructure/harness/env.py` -- `AliasBuilder` takes the
  contract and nothing else. `local_aliases` needs no `Settings`, so it is a plain builder.
- `backend-api/src/orchestrator/infrastructure/harness/registry.py:47` -- `ALIASES`, the static
  table whose docstring says "Epic 7's `codex` and `local` adapters add a line here". **The line
  cannot land: see `## Auto Run Result`.**
- `scripts/harness/opencode.sh:8` -- normative `HARNESS_ENV_ALIASES=(LANGFUSE_BASEURL=…
  LANGFUSE_USER_ID=ORCH_RUN_ID)`, the `opencode.json` `configure` writes, the invocation comment.
- `backend-api/src/orchestrator/domain/ports/harness.py:124` -- `HarnessHandle`: gains a defaulted
  `cwd`, because only `wait` can consult the session store and only `start` knows the directory.
- `backend-api/src/orchestrator/domain/ports/tracer.py:80` -- `attempt_observed`; gains two more
  keyword-only defaulted arguments, exactly as 7.2 added `harness`.
- `backend-api/src/orchestrator/infrastructure/tracing/session_level.py` -- 7.2's sibling module
  and the precedent for keeping a second query out of `langfuse_tracer.py` (375 of 400 lines).
- `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py:196` --
  `_trace_line`, the one caller that holds the attempt and therefore its window.
- `backend-api/src/orchestrator/application/use_cases/spend.py:80` -- `_priced_attempt`: rows found
  ⇒ `provisional=False` and the summed `usd`, which is already `0` for a local model. No change.
- `backend-api/tests/unit/fakes/{process,tracer}.py` -- the one fake per port (AD-18).
- `backend-api/tests/unit/test_codex_env_contract.py` -- the contract-test shape to copy.
- `_bmad-output/planning-artifacts/mvp/addendum.md:221` -- 7.1's §B table; this story appends its own.

**Read-only evidence (anchors this story must not edit).**
- `tests/unit/test_harness_registry.py:77` and `tests/unit/test_harness_env_subscription.py`
  (`test_the_default_table_is_not_the_subscription_one`) both assert
  `ALIASES == {"claude": claude_aliases}`.
- `tests/unit/test_harnesses_router.py:109` and `tests/e2e/test_harnesses.py:50` assert the
  `HarnessOut` field set as a closed equality of seven names.
- `tests/unit/test_codex_registry.py` `REGISTERED` and `alias_table` exactness — its own docstring
  names 7.3 as their reviser, so they are reported rather than acted on while the story is halted.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/ports/harness.py` -- `HarnessHandle.cwd: Path | None = None`;
  `resume_command -> str | None`. -- a harness that looks its session up by directory needs the
  directory in `wait`; a harness that cannot resume has no line to print.
- `backend-api/src/orchestrator/application/use_cases/terminal.py` -- treat a `None` resume line as
  a sixth "no terminal" case. -- the port now admits one.
- `backend-api/src/orchestrator/infrastructure/harness/opencode/events.py` -- new:
  `session_id_from`, `result_object`, `usage_from`. -- reading the stream, separate from writing it.
- `backend-api/src/orchestrator/infrastructure/harness/opencode/sessions.py` -- new:
  `session_for_directory`. -- the store fallback, read-only sqlite, never raising.
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` -- new: `LocalHarness`,
  `local_aliases`. -- the invocation, the three-way split, the aliases the script declares.
- `backend-api/src/orchestrator/infrastructure/harness/opencode/__init__.py` -- new: re-exports.
- `backend-api/src/orchestrator/domain/ports/tracer.py` -- `attempt_observed` gains keyword-only
  `started_at`/`ended_at`. -- `local`'s rule is a time window and the port carries only ids.
- `backend-api/src/orchestrator/infrastructure/tracing/user_level.py` -- new:
  `USER_LEVEL_HARNESSES`, `PATH_USER`, `user_level_observed`. -- kept out of a 375-line module.
- `backend-api/src/orchestrator/infrastructure/tracing/spans.py` -- new: the `SpanRef` builders
  moved out of `langfuse_tracer.py`. -- a **split** to make room, never a trim (hard rule).
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py` -- take the window, add
  the `local` branch, log `path=user`. -- the Operator's only view of which rule answered.
- `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py` -- pass the
  attempt's own window. -- the one caller that knows it.
- `backend-api/tests/unit/fakes/tracer.py` -- record the window. -- the one fake for the port.
- `backend-api/tests/unit/infrastructure/harness/fixtures/opencode/*.jsonl` -- new: sample streams.
- `backend-api/tests/unit/test_opencode_events.py` -- new: session capture, usage, tolerance.
- `backend-api/tests/unit/test_opencode_sessions.py` -- new: every row of the store's matrix.
- `backend-api/tests/unit/test_local_adapter.py` -- new: argv, dispatch, fallback, capabilities.
- `backend-api/tests/unit/test_local_env_contract.py` -- new: the contract test for `local`.
- `backend-api/tests/unit/test_tracer_user_level.py` -- new: the trace half of the matrix.
- `backend-api/tests/unit/application/test_readiness_trace_line_names_the_window.py` -- new.
- `backend-api/tests/unit/test_local_spend_zero_cost.py` -- new: cost `0`, tokens, not provisional.
- `_bmad-output/planning-artifacts/mvp/addendum.md` -- append a §B record for story 7.3.

**Acceptance Criteria:**
- Given the contract test for `local`, when run, then the key set of `env_for` equals
  `HARNESS_ENV_CONTRACT` ∪ `opencode.sh`'s `HARNESS_ENV_ALIASES` ∪ the Project's variables ∪
  `{HOME, PATH, LANG, TERM}`, `LANGFUSE_USER_ID == ORCH_RUN_ID`, and no forbidden name is present.
- Given the fake runner and a stream with a session id and usage, when `run` is called, then the
  argv is the documented invocation with `-m litellm/local-coder` by default, the session id and
  usage are parsed, and `resume_command` is `None`.
- Given a stream without a session id and a store holding a session for the worktree, when `run`
  finishes, then the session id is the store's.
- Given `attempt_observed` for `local` and a stub client returning one observation with
  `userId == run_id` inside the window, when called, then it is `True`; another user id, a time
  outside the window, or a missing window each answer `False`.
- Given Gateway rows with `spend 0` and tokens, when `record_attempt_spend` runs, then
  `cost_usd == 0`, the tokens are set and `cost_provisional` is `False`.
- Given `make lint`, `make test` and `make openapi`, when run, then all three exit 0.

## Spec Change Log

_No loopback: no finding was routed `bad_spec` or `intent_gap`._

## Review Triage Log

### 2026-09-10 — Review pass

Run inline rather than through review subagents: this dispatch forbids spawning any (two Epic 6
stories deadlocked that way, and 7.1 and 7.2 were run the same way), so the layers were executed
by the same session against the diff.

- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 1, medium 1, low 2)
- defer: 0
- reject: 3
- addressed_findings:
  - `[high]` `[patch]` `user_level_observed` read the API's answer **outside** its own guard: a
    naive `start_time` compared against the attempt's aware window raises `TypeError`, and an
    observation model shaped otherwise than expected raises on attribute access — either would
    have escaped into a readiness evaluation, which is exactly what SM-3 and this module's own
    docstring forbid. The reading moved inside the `try`, a naive timestamp is now read as UTC
    rather than refused, and two tests cover both.
  - `[medium]` `[patch]` the session store was opened as `f"file:{store}?mode=ro"`. A store path
    holding a `?` or `#` truncates there, and SQLite would then have opened — or created — some
    other file. Now `store.resolve().as_uri()`, with a test for a path holding a `?`, and
    `OSError`/`ValueError` join `sqlite3.Error` in the guard.
  - `[low]` `[patch]` the two observation attributes the rule reads (`user_id`, `start_time`)
    were literals in the middle of a function while every other unobserved name in this epic is
    a constant with a `[verify]` note. Now `USER_ID_ATTRIBUTE`/`START_TIME_ATTRIBUTE`.
  - `[low]` `[patch]` `ruff` findings in the new modules: an unused `noqa`, a function-local
    import, an unused import, two unused `Path`/`caplog` parameters, one magic value. Fixed, and
    the magic-value test was widened to assert all four log paths are distinct rather than three.

Rejected as noise: "give `local` a `SESSION_LIFETIME_DAYS` entry" (a harness that cannot resume
has no lifetime to state, and 6.7 already hides the block); "sum `tokens.reasoning` and
`tokens.cache` into `tokens_in`" (AD-11 stores two numbers and inventing a third reading of the
harness's own figures is precisely what AD-10 forbids); "make `resume` fall back to a fresh
dispatch instead of raising" (that is the silent substitution hard rule 7 exists to prevent, and
`agent.py` already gates on the capability).

## Design Notes

**Why the window is on the port and not inside the adapter.** The plugin carries no attempt id —
one trace per turn, keyed by OpenCode's own session, with `userId = LANGFUSE_USER_ID = run_id`
(`research/tracing.md` §OpenCode). So the only thing that separates *this* attempt's generations
from another attempt of the same Run is when they happened, and the attempt is the only object
that knows. Keyword-only and defaulted, exactly as 7.2 widened the same method, so no existing
call site and no frozen test moves. A missing bound answers `False` rather than widening to the
whole Run: evidence nobody can attribute is not evidence.

**Why the query is narrowed twice.** `api.observations.get_many(user_id=…, from_start_time=…,
to_start_time=…)` states the rule server-side, and `user_level_observed` re-checks both halves on
what comes back. The parameter names are documented but unobserved (7.4 settles them); a
re-check costs one comparison and is what keeps a silently-ignored parameter from turning
"this attempt was observed" into "some attempt of this Run was".

**Why `spans.py` exists.** `langfuse_tracer.py` sits at 375 of the 400 lines
`tests/unit/test_source_limits.py` enforces and this story adds a branch to it. The `SpanRef`
builders are moved out whole — a split, not a trim; no comment or docstring is deleted to buy room.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: exit 0
- `make openapi` -- expected: exit 0 (no contract drift; nothing this story lands changes it)
- `make e2e-ui` -- expected: unrunnable without a stack; report honestly rather than claim a pass

## Auto Run Result

Status: done
Blocking condition: none. The story halted once, `blocked`, on two frozen assertions; the Operator
ruled on both in session on **2026-09-10**, granted both, and the rest of the scope landed in the
follow-up commit. What follows records the conflicts as they were raised, then the rulings and the
edits made under them.

### The anchor conflicts, as raised (now ruled on — see the next section)

**A — `ALIASES` (two files, one assertion).** `local` declares two aliases,
`LANGFUSE_BASEURL=LANGFUSE_BASE_URL` and `LANGFUSE_USER_ID=ORCH_RUN_ID`. Both are derived from
the contract alone, so `local_aliases` is a plain `AliasBuilder` and belongs in the *static*
table — `registry.py`'s own docstring says so in as many words ("Epic 7's `codex` and `local`
adapters add a line here and change nothing else"), and `alias_table`'s says why the alternative
does not apply ("a builder that needed a setting could not be stated as a module-level
constant"). `codex` is bound in the instance table only because `CODEX_HOME` is `AGENT_HOME`'s.
Adding the line turns these red:

| File | Assertion | What it pins |
|---|---|---|
| `backend-api/tests/unit/test_harness_registry.py:77` | `assert ALIASES == {"claude": claude_aliases}` | that the static table is keyed the way the registry is — as of Epic 5, when `claude` was the only adapter |
| `backend-api/tests/unit/test_harness_env_subscription.py` (`test_the_default_table_is_not_the_subscription_one`) | `assert ALIASES == {"claude": claude_aliases}` and `assert SUBSCRIPTION_ALIASES == {"claude": claude_subscription_aliases}` | that subscription mode is a *second* table rather than an edit to the first |

Neither can hold beside a registered `local`. Routing `local_aliases` through `alias_table`
instead would keep both green and is exactly the "worked around" the dispatch forbids, so it was
not done. **A second question rides on the ruling:** `alias_table` *swaps* tables rather than
merging them (`SUBSCRIPTION_ALIASES if … else ALIASES`), while `SUBSCRIPTION_ALIASES`'s docstring
says "A harness with no entry here falls back to `ALIASES`". With only `claude` in either table
the difference was invisible; with `local` in one of them it is not — under
`CLAUDE_SUBSCRIPTION_AUTH=true` a `local` process would lose both its aliases and the plugin
would send un-keyed generations. Either `local` goes in both tables, or `alias_table` merges and
makes the docstring true. Both need the ruling above.

**B — the `HarnessOut` field set (two files).** The brief's own shape is "`GET /harnesses`
returns `models: [...]` per harness; empty for others", and `model_dump()` renders every field,
so an eighth field breaks two closed-set equalities:

| File | Assertion |
|---|---|
| `backend-api/tests/unit/test_harnesses_router.py:109` | `assert out.model_dump() == { …seven names… }` |
| `backend-api/tests/e2e/test_harnesses.py:50` | `assert set(item) == { …the same seven… }` |

`api/schemas/harnesses.py`'s docstring records that these two were revised once before, under
the Operator's ruling on Epic 5's CAP-8 story. That was a ruling for that story; it authorises
nothing here. Moving `models` to a new sibling route would keep both green and contradict the
brief's stated shape, so it was not done. The whole web-client half of this story — the model
field becoming a select over `LOCAL_MODELS` when `local` is chosen — waits on this, because
`src/api/schema.d.ts` is generated and may not be hand-written (AD-3).

**C — `test_codex_registry.py`, reported rather than acted on.** Registering `local` also turns
`REGISTERED = {"claude", "codex"}` and `set(alias_table(Settings())) == {"claude", "codex"}` red.
This one appears to be covered already: that module's own docstring says "**The exact-set
assertions here are this story's own, and 7.3 revises them when `local` lands**", which is hard
rule 1's second exception naming this story explicitly. It was left untouched because the story
halts on A and B anyway, and because the dispatch asked for anchor conflicts to be handed over
rather than judged. **Please confirm it when ruling on A.**

**D — not a conflict, checked.** `test_terminal_command.py:525`'s `["local", ""]` parametrize
stays green with `local` registered: `_resumable_harness` turns a harness away on
`capabilities.resume`, which this adapter declares `False`. `test_codex_registry.py`'s
`test_a_harness_the_registry_still_does_not_hold_has_no_terminal` stays green for the same
reason (its name becomes inaccurate; its assertion does not). The four registry assertions 7.1
had rebound to `HARNESS_NAMES` were re-checked and all four still hold.

### What landed — backend

| File | What changed |
|---|---|
| `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` | **new.** `LocalHarness` (`name = "local"`, all three capabilities `False`) and `local_aliases`. `opencode run --format json --dir <worktree> -m litellm/<model> "<prompt>"`, prompt last, model defaulting to the first `LOCAL_MODELS` alias. `resume` refuses; `resume_command` is `None`. |
| `backend-api/src/orchestrator/infrastructure/harness/opencode/events.py` | **new.** `session_id_from` (first `sessionID` wins), `result_object` (last event reporting tokens, then last object), `usage_from` (both tokens or neither), `STREAM_COST_USD = 0`. Built on 7.1's shared `jsonl.py`; no second parser. |
| `backend-api/src/orchestrator/infrastructure/harness/opencode/sessions.py` | **new.** The `[verify]` store fallback: newest session for the worktree, read-only URI, never raising for any of missing file / missing table / not-a-database / locked. |
| `backend-api/src/orchestrator/infrastructure/harness/opencode/__init__.py` | **new.** Re-exports. |
| `backend-api/src/orchestrator/domain/ports/harness.py` | `HarnessHandle.cwd: Path | None = None` (only `wait` can consult the store; only `start` knows the directory) and `resume_command -> str | None`. Both defaulted/widening, so no existing adapter or frozen test moves. |
| `backend-api/src/orchestrator/application/use_cases/terminal.py` | a `None` resume line is the sixth "no terminal" case, so a `None` can never be interpolated into a pasteable command. |
| `backend-api/src/orchestrator/domain/ports/tracer.py` | `attempt_observed` gains keyword-only, defaulted `started_at`/`ended_at` — exactly how 7.2 added `harness`. |
| `backend-api/src/orchestrator/infrastructure/tracing/user_level.py` | **new.** `USER_LEVEL_HARNESSES` (`local` alone, disjoint from 7.2's set), `PATH_USER`, `user_level_observed`: generations of `userId == run_id` inside the attempt's window, re-checked client-side, never raising. |
| `backend-api/src/orchestrator/infrastructure/tracing/spans.py` | **new.** The two `SpanRef` builders, moved out of `langfuse_tracer.py` **whole and unchanged** to make room for the third rule (375 of 400 lines). A split, not a trim: no comment or docstring was deleted. |
| `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py` | the `local` branch and `path=user`; now 355 lines. |
| `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py` | `_trace_line` passes the build attempt's own window. Wording untouched, so `tests/e2e/test_harnesses.py` still holds. |
| `backend-api/tests/unit/fakes/tracer.py` | records the window on a new `observed_windows` list. The one fake for the port (AD-18); `observed_calls`'s tuple shape is untouched so 7.2's tests stay green. |
| `_bmad-output/planning-artifacts/mvp/addendum.md` | a §B record for 7.3: ten provisional/assumed values, and the two that are not. |

**No production change was needed for the cost rule.** `application/use_cases/spend.py` already
prices an attempt from rows that exist regardless of the amount, so `spend 0` with tokens comes
out as `cost_usd == 0`, tokens set, `cost_provisional False`. That is the finding, and
`test_local_spend_zero_cost.py` covers it rather than assuming it — including the contrast that
makes it mean something: an attempt the Gateway has no rows for is still provisional.

New test files (nothing existing was edited): `tests/unit/test_local_adapter.py`,
`test_opencode_events.py`, `test_opencode_sessions.py`, `test_local_env_contract.py`,
`test_tracer_user_level.py`, `test_tracing_spans.py`, `test_local_spend_zero_cost.py`,
`tests/unit/application/test_readiness_trace_line_names_the_window.py`,
`tests/unit/application/test_terminal_command_no_resume_line.py`, plus three fixtures under
`tests/unit/infrastructure/harness/fixtures/opencode/`.

### What did **not** land, and why

- ~~**`local` is not in `build_harnesses`.**~~ Landed under ruling A.
- ~~**`HarnessOut.models` and the New workflow select.**~~ Landed under ruling B.
- **`scripts/harness/opencode.sh` is unchanged.** It was re-read against the documented shapes
  and nothing in them contradicted it; the brief asks for changes to be recorded in §B, and the
  record is that there were none to make without a running CLI.

### Follow-up review

`followup_review_recommended: true`. Patched this pass: high 1, medium 1, low 2 —
`3 × 1 + 1 × 2 = 5`, which meets the threshold, and independently a `high` was patched.

### Verification

- `make lint` — exit 0 (ruff · mypy strict · import-linter 4/4 kept · env contract 37/43 ·
  test pairs 203/203 · contract drift · eslint · prettier · tsc · astro check · web test pairs).
- `make test` — exit 0. Backend 5816 passed, 1 skipped; web-client 94 files, 1225 passed.
  Coverage gate on `domain/` + `application/` at 100%.
- `make openapi` — exit 0, and no drift: nothing that landed changes the contract, which is
  itself the evidence that conflict B is unresolved.
- `make e2e-ui` — exit 0 (`pnpm build` then Playwright: 168 passed, 1 skipped). It needs no
  backend stack, so it was run in full rather than reported as unrunnable.
- `make e2e-api` was **not** run: it needs the compose stack, which this dispatch does not bring
  up. `tests/e2e/test_harnesses.py` is untouched and nothing that landed changes a served route.

### Residual risks

- **Ten unverified values.** Every one is a constant with a `[verify]` comment and a row in
  `addendum.md` §B; none is a value a passing test makes look observed. 7.4 settles them.
- **The time-window rule is an assumption** (the brief's own). If the plugin's clock and this
  orchestrator's disagree by more than an attempt's own duration, a `local` readiness Run reports
  "no spans" for an attempt that traced. 7.4 is the first run that could show it.
- **The store fallback approximates.** "Newest session for this worktree" is right for the
  attempt that just ran and wrong if a second OpenCode ran in the same worktree concurrently —
  which this system never does, but nothing in the store says so.

### Anchor authorisations granted (Operator, 2026-09-10, story 7-3)

Three rulings, and one defect the Operator asked to be fixed. Every authorised edit is an exact
closed-set equality that **gained a name** — none was weakened, reordered, or removed — and every
one ships coverage that strictly exceeds it, in a new file, in the same commit.

| # | File | Was | Now |
|---|---|---|---|
| A | `backend-api/tests/unit/test_harness_registry.py:78` | `assert ALIASES == {"claude": claude_aliases}` | `assert ALIASES == {"claude": claude_aliases, "local": local_aliases}` |
| A | `backend-api/tests/unit/test_harness_env_subscription.py:194` | the same equality | the same, plus the `local` key. `SUBSCRIPTION_ALIASES == {"claude": claude_subscription_aliases}` on the next line is **untouched** |
| B | `backend-api/tests/unit/test_harnesses_router.py:117` | seven names in `model_dump()` | the same seven plus `"models": []` |
| B | `backend-api/tests/e2e/test_harnesses.py:57` | seven names in `set(item)` | the same seven plus `"models"` |
| C | `backend-api/tests/unit/test_codex_registry.py:59` | `REGISTERED = {"claude", "codex"}` | `REGISTERED = {"claude", "codex", "local"}` |
| C | `backend-api/tests/unit/test_codex_registry.py:187` | `assert set(table) == {"claude", "codex"}` | `assert set(table) == {"claude", "codex", "local"}` |

Two of the four files also gain **one import line** — `from …harness.opencode.adapter import
local_aliases` — which is what the replacement assertion is written in terms of, the same shape
7.1's ruling took. Nothing else in any of the six locations changed: no docstring, no ordering, no
deletion, no skip. The one prose edit the Operator asked for is in production code, not a test:
`api/schemas/harnesses.py`'s note now records this ruling beside the CAP-8 one.

**A** was granted because `local_aliases` needs no `Settings` and so belongs in the static table
by the design's own rule; after it, `ALIASES` is complete for all three harnesses (`codex`
declares none by design), so neither assertion should need touching again.

**C** was hard rule 1's second exception all along — `test_codex_registry.py` is 7.1's own file
and its docstring names *this* story as the reviser. The Operator confirmed rather than granted.

**D — the `SUBSCRIPTION_ALIASES` defect, found while halted and fixed under the same ruling.**
`alias_table` swapped tables wholesale while `SUBSCRIPTION_ALIASES`' docstring promised a
per-harness fallback to `ALIASES`. Invisible while `claude` was the only key in either; with
`local` in one, an instance running `CLAUDE_SUBSCRIPTION_AUTH=true` would have handed OpenCode no
`LANGFUSE_BASEURL` and no `LANGFUSE_USER_ID` — the plugin would still run, still export, and every
generation would arrive keyed to no Run. No error, no failed gate, and `attempt_observed` for
`local` answering `False` forever. `alias_table` now merges per harness, so the code does what the
table already documented, and `SUBSCRIPTION_ALIASES` needs no `local` entry — which is why the
second half of that assertion is untouched.

### What the new test files pin

| File | What it pins |
|---|---|
| `backend-api/tests/unit/test_local_registry.py` (13 tests) | everything A and C's revisions stopped guaranteeing, and more: the registry is now exactly `HARNESS_NAMES`; `local` is a `LocalHarness`, satisfies the port under its own key, runs on the runner the registry was handed, is seeded in the `harness` table, and reaches the walker; `ALIASES` is keyed the way the registry is and every builder in it takes the contract alone; a `local` attempt's environment really carries the plugin's two names and neither Claude's token nor `CODEX_HOME`; the terminal exports are the script's own array and hold no secret; and a parked `local` attempt has no terminal **because the adapter cannot resume**, which is the reason that answer is still true now that the registry holds the name. |
| `backend-api/tests/unit/test_alias_table_merge.py` (10 tests) | D. Both modes bind the same harnesses; subscription mode overrides only `claude`; `codex` stays bound by the instance table in both; a `local` process is keyed to its Run in **both** modes, with the same key set either way; and subscription mode still drops `ANTHROPIC_AUTH_TOKEN`. |
| `backend-api/tests/unit/test_harnesses_models_field.py` (13 tests) | B. The table has only `local`, every key is a declared harness, it reads the shipped `.env.example` value and follows the environment rather than a row, and it is immutable; the field defaults empty, is rendered always, keeps its order, and is a copy; over the route, `local` lists the aliases, the others list none, the models come from the dependency rather than the row, and the row's own fields are untouched. |
| `web-client/tests/unit/newwf-model-select.test.ts` (16 tests) | the web-client half — see below. |

### The web-client half

| File | What changed |
|---|---|
| `web-client/src/api/schema.d.ts` | `models?: string[]` on `HarnessOut`. **Generated only** through `make openapi` / `pnpm gen:api` (AD-3); never hand-edited. `contracts/openapi.json` moved with it. |
| `web-client/src/lib/newwf/state.ts` | `modelsFor(harnesses, harness)` — the models a harness publishes, `[]` for one that takes a free-text name and for a backend predating the field. `withHarness(state, harness, harnesses)` — selecting a harness keeps a model only if the new harness still offers it. |
| `web-client/src/components/NewWorkflowFields.tsx` | the MODEL field is a `<select>` over the given models when there are any, and the text input otherwise. The `models` prop is **optional and defaults to `[]`**, on the same precedent the backend field follows, so the frozen `newwf-fields.test.ts` compiles and passes unchanged. |
| `web-client/src/islands/NewWorkflow.tsx` | passes `modelsFor(harnesses, state.harness)` and routes harness selection through `withHarness`. |

Why `withHarness` exists: a select cannot display a value that is not one of its options, so a
model typed for `claude` and carried into `local` would leave the control blank while the form
still submitted the old string. Clearing it renders "harness default", which is what an unset
model is. NFR-6 holds either way — a model list is nothing to report, so neither shape paints a
signal colour, and the test asserts it.

### Gates, after the rulings

- `make lint` — exit 0. `Contracts: 4 kept, 0 broken` · `gen:api: src/api/schema.d.ts matches
  contracts/openapi.json` · astro check `231 files, 0 errors` · `test pairs: 91 modules under src`.
- `make test` — exit 0. Backend `5854 passed, 1 skipped`; web-client `Test Files 95 passed (95) /
  Tests 1241 passed (1241)`. Coverage gate on `domain/` + `application/` at 100%.
- `make openapi` — exit 0; the contract moved by exactly the `models` field.
- `make e2e-ui` — exit 0, `168 passed, 1 skipped`. It rewrites the Epic 5/6 deliverable PNGs under
  `_bmad-output/implementation-artifacts/`; those were restored, not committed, both times.
- `make e2e-api` — still not run: it needs the compose stack this dispatch does not bring up.
  `tests/e2e/test_harnesses.py`'s field set was updated under ruling B and will be exercised by
  the next stack run.
