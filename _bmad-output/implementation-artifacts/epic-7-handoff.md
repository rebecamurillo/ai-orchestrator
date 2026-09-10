# Epic 7 handoff — the two remaining harnesses, and the host wall in front of all three

Written 2026-09-10, after story 7-6. For whoever builds Epic 8 and after.

`epic-1-handoff.md` … `epic-6-handoff.md` all still hold; nothing in them was undone here. Read this
once before your first Epic 8 story; you should not need it again.

Six stories were dispatched. **Four landed with every gate green. Two are `blocked` by design** —
7-2 and 7-4 are the readiness proofs, and an agent may not run a real harness. Four anchor rulings
were granted by the Operator, each recorded in the story that used it.

The epic's headline is not a feature either. **Every readiness proof in this product is blocked behind
one host setting**, and story 7-4 is what found it. See §2.

---

## 1. What you can rely on

Three adapters now sit behind one port, and the registry holds exactly the names the domain declares.

```
infrastructure/harness/claude/     ClaudeHarness      preassign_session · resume · native_tracing
infrastructure/harness/codex/      CodexHarness       resume · native_tracing        (7.1)
infrastructure/harness/opencode/   LocalHarness       none of the three              (7.3)
infrastructure/harness/fake/       FakeHarness        ORCH_TEST_MODE only
infrastructure/harness/jsonl.py    the shared JSON-log primitives both new adapters read   (7.1)
```

```
registry.py::ALIASES               claude · local          the static harness-native name builders
registry.py::SUBSCRIPTION_ALIASES  claude                  overrides, merged per harness (7.3)
registry.py::alias_table(settings) the instance table — the static ones plus codex's factory (7.1)
```

`codex` has **no** `ALIASES` entry and that is correct: `scripts/harness/codex.sh` declares
`HARNESS_ENV_ALIASES=()` because Codex reads the contract names directly. Its one addition is
`CODEX_HOME`, which is `AGENT_HOME`'s and therefore needs a factory over `Settings` — which an
`AliasBuilder` may not take. That is the whole reason `alias_table` exists beside the static tables.

Two read-outs landed, each as a **sibling trio** — router, use case, schema — because
`api/routers/runs.py` and `api/routers/projects.py` both have pinned route counts:

```
GET /steps                              api/routers/history.py       + use_cases/history.py
                                        + schemas/history.py + domain/ports/history.py
                                        + infrastructure/db/repositories/history.py       (7.5)
GET /projects/{id}/trajectories.jsonl   api/routers/trajectories.py  + use_cases/trajectory_export.py
                                        + schemas/trajectories.py + api/providers_trajectories.py (7.6)
```

**Two settings**, both with their `.env.example` line (AD-20): `LITELLM_SPEND_MATCH` (`session` |
`attempt_tag`, default `session`) and — from the pre-epic fix — `READINESS_MODELS`.

**Two fallbacks are built and dormant**, waiting on evidence rather than on code:

- `infrastructure/tracing/session_level.py` — when a `codex` attempt's spans did not parent under the
  attempt span, accept a Langfuse trace of session `run_id` carrying tag `attempt:{id}`. The log line
  `attempt trace observed` says which rule answered: `path=parented`, `path=session`, `path=none`.
- `LITELLM_SPEND_MATCH=attempt_tag` — when the `responses` wire API fills no `session_id` column, find
  the attempt's rows by `end_user=run_id` and the `attempt:` tag in `request_tags` instead.

Neither has ever fired against a real gateway. **Do not delete either as dead code**; each has a
runbook step that decides whether it is needed.

---

## 2. The finding that matters — read this one

**The host Langfuse is in v4 `events_only` mode, and that blocks the readiness gate for every
harness.** Story 7-4 checked the host before planning, and it was independently re-checked:

```
GET /api/public/observations   404
GET /api/public/traces         404
litellm  :4000  health         200
omlx     :8000  /v1/models     no answer
```

Every public read API answers 404. `Tracer.attempt_observed` — its primary parented query, 7-2's
session-level fallback, and 7-3's user-level rule alike — can then only ever return `False`. So the
`trace observed` evaluation line **cannot pass**, and a harness cannot reach `enabled`, for `claude`
(story 5-11), `codex` (7-2) or `local` (7-4). It is not a code defect and no amount of correct tracing
changes it.

**One host setting unblocks three stories.** Take that Langfuse out of `events_only` before the
Operator session, or all three record `trace observed · not ok` and the PRD §6.1 fallback — honest,
and much less valuable.

`oMLX` not running blocks `local` alone and is a minute's work at the terminal.

**What is *not* blocked:** `host/litellm.config.yaml` and `host/README.md` already carry both
`LOCAL_MODELS` aliases as `openai/<served model>` with `use_chat_completions_api: true`, the
`langfuse_otel` callback and the restart command — landed in Epic 1, verified in 7-4, and correct.
Story 7-4 wrote no duplicate proposal, which is why its diff is one file.

---

## 3. What 7-2 and 7-4 still need, and what they are

They are **not unfinished work**. Each landed its code, its fallbacks and a runbook, then halted
`blocked` — the split `pipeline-handoff.md` §2 describes, working as designed.

```
stories/7-2-codex-readiness-passes-end-to-end.md                       steps 0–8 + "What to send back"
stories/7-4-opencode-readiness-passes-end-to-end-with-host-model-serving.md    the same shape
```

Both runbooks front-load the preconditions that can end the story in five minutes rather than after a
full Run — the gateway's model list, the `/v1/responses` route, and the Langfuse read APIs of §2. Both
name what to read in each output and what each reading forces as a decision.

**Twenty-two values are provisional**, eleven per harness, each marked at its definition and tabulated
in `addendum.md` §B: argv flags, event and field names (`thread.started`/`thread_id`,
`sessionID`, `tokens.input`), the OpenCode session-store path, table and columns, the Langfuse query
parameters, and the two `[ASSUMPTION]`s the briefs carried. **Every one has a runbook step that
confirms or corrects it.** Nothing was guessed to make a gate green.

Story 7-1 deliberately left one value *unset* rather than guess it: whether `--skip-git-repo-check` is
needed under `cap_drop ALL`. It did not add the flag, on the reasoning that a flag guessed in is as
wrong as one guessed out. **Keep that instinct.** Epic 5's story 5-7 shipped `stop_reason:
"max_budget"` as a plausible constant behind a passing test and 5-11 later found the string occurs
nowhere in the shipped bundle.

Story 7-2's runbook contains one step worth copying into every future runbook: it asks the Operator to
report whether the Codex stream carries **any money field at all**, because 7-1 recorded
`STREAM_COST_USD = Decimal("0")` as *non*-provisional on the belief that Codex reports tokens and not
money. It is the one 7-1 value the runbook can falsify. **Write the step that could prove you wrong.**

---

## 4. Decisions that are load-bearing — do not undo these by accident

**`alias_table` merges per harness; it used to swap.** Story 7-3 found that
`SUBSCRIPTION_ALIASES if subscription else ALIASES` contradicted `SUBSCRIPTION_ALIASES`' own
docstring, which promises a per-harness fallback. Invisible while only `claude` was in either table —
but with `local` in one, a `CLAUDE_SUBSCRIPTION_AUTH=true` instance would have given OpenCode no
`LANGFUSE_USER_ID`, and every local generation would have reached Langfuse un-keyed. AD-11 attribution
broken silently, which is the worst kind. `test_alias_table_merge.py` covers the case that was broken.

**`configurePolling` is last-writer-wins, and `/runs` is the first screen with two islands on the
shared `$poll` loop.** The history island reporting "nothing executing" slowed the queue from 5 s to
30 s; a frozen poll-tick spec caught it. `RunsHistory` now *subscribes* to `$poll` and never re-times
it, because the queue is the right authority — an executing attempt belongs to a Run `GET /queue`
already reports as `running`. **A third island on that screen must subscribe too, not re-time.**

**`BLK` selects `blocked` *and* `error`**, per the brief's own acceptance criterion, so `ERR` is a
subset of `BLK` and the tokens are not a partition. Documented at `STATUS_FILTERS`. Consequence worth
knowing: the bar offers no `CHK` or `SKP`, so a `checkpoint` or `skipped` attempt is reachable only
with no status filter at all.

**A history page always carries a cursor when full and never when short.** A `limit+1` look-ahead
cannot produce the brief's "the third page is empty with `next_cursor null`". The cost is one empty
read when the history divides exactly by the page size, and *more* surviving one click past the end.

**`trace_url` on a history row resolves per Run, not per attempt.** No attempt-level trace id is
stored — `domain/entities/attempt.py` has none, only `Run.trace_id`. That is the honest behaviour and
it is stated at the field rather than derived into something that is not recorded.

**`HistoryQuery` is a query port, not a fifth `AttemptRepository` method.** The unit is the attempt,
the order spans every Run, and a row needs four entities at once.

---

## 5. The rules that will bite you

**Modules at or near their caps, checked this epic:**

```
api/providers.py                     391/400   → 7.6 added api/providers_trajectories.py beside it
application/use_cases/projects.py    395/400   → 7.6 threaded trajectory_count through a second
                                                 independent dependency rather than growing it
infrastructure/tracing/langfuse_tracer.py      → 7.2 left it at 375; 7.3 moved its two SpanRef
                                                 builders out whole into tracing/spans.py
web-client RunDetail.tsx             235/300   → 7.5 checked before adding anchor handling; no split
```

**Split, never trim.** Every one of those bought space by moving code out whole, not by deleting
prose. Epic 5 did the opposite and the Operator stopped it.

**New coverage goes in a new test file. Always.** Adding a test to an existing test file is itself an
anchor violation.

**A new endpoint goes in a new sibling router.** `api/routers/runs.py` and `api/routers/projects.py`
both have pinned operation counts. `run_files.py`, `history.py` and `trajectories.py` are the pattern.

**`make e2e-ui` rewrites twelve Epic 5 and Epic 6 deliverable PNGs on every run.** They are generated
output — story 5.10's anchor spec screenshots the whole Run detail page. **Restore them with
`git checkout` before committing**; every Epic 7 story did, and no Epic 7 commit carries one.
`epic-7-screens/` is this epic's own equivalent and is committed once, deliberately.

**A placeholder assertion must name the *story* that replaces it, never an epic, and must assert the
route is served rather than the placeholder's copy.** `AGENTS.md` says the second half already. Story
4-16 wrote the forbidden kind — it asserted the deferral *sentence* — and it cost Epic 7 a halt and a
ruling. Do not leave one behind for Epic 8's successor.

**`stub-backend.mjs` must answer every route an island reads**, unconditionally and empty, or that
island's own failed-fetch readout becomes a second `fetch-failed` element and Playwright strict mode
fails the frozen specs that assert on one. `GET /api/v1/queue` set the precedent; `/steps` and
`trajectories.jsonl` followed it. The same is true of `runs-empty`: give a new section its own
test-id.

---

## 6. What Epic 7 has and has not proved

**Proved on the compose stack, against real Postgres and the real walker:**

- `GET /steps` with keyset pagination, its filters, and schemathesis over the route;
- `GET /projects/{id}/trajectories.jsonl` streaming ndjson through the Astro proxy with
  `Content-Disposition` intact — including a real browser download in Playwright;
- the HISTORY table's ten columns, the `#step-{seq}` anchor arrival, *more*, and both filters;
- the New workflow model field becoming a select over `LOCAL_MODELS` when `local` is chosen.

**Proved only at the unit level, over fakes:**

- **both new adapters, entirely.** Neither `codex` nor `opencode` has ever been executed. Every argv,
  every event name, every field name is source-read or documentation-read;
- the session-level trace fallback, the user-level trace rule, and the tag-based spend mode;
- the OpenCode session-store fallback, against a fake store — the real `opencode.db` schema is unread;
- cost `0` with tokens for local models.

**Not proved at all, and the honest state:** no readiness Run has ever passed for any harness. `claude`,
`codex` and `local` are all `disabled` and none has ever been otherwise. The epic's own success
signal — the same fixture story on all three, with three trajectory lines whose cost and wall-clock
differ — is unreachable until §2 is resolved.

---

## 7. What Epic 8 inherits

- **`log_tail_url` names a resource that does not exist.** Nothing serves an attempt's log tail; it
  lives inside `GET /runs/{id}/detail` as `log_tail: list[str]`. Story 7-5's field resolves to that
  detail path with the gap documented, because its brief's Scope was "Out: nothing else". **Epic 8 is
  the read-model epic and is the right place to decide what that field should point at.**
- **Epic 7 was built by an assistant dispatching one sub-agent per story, not by the orchestrator.**
  `pipeline-handoff.md` was written expecting otherwise; §4 of it has been corrected. **Epic 8 is the
  first epic the product builds itself**, and it still needs a harness `enabled` first — which needs
  §2 and an Operator session.
- **Epic 8 needs no operator/agent split.** All six of its stories are read-model and UI work; none
  touches a live service. It was re-checked when this handoff was written.
- The `Harness.resume` gap Epic 6 flagged is **still open and still deferred by Operator decision**. A
  resumed dispatch records no `pgid`, and `Harness.resume` takes neither `model` nor
  `budget_usd_remaining`. It blocked nothing in Epic 7 either — but note both new adapters declare
  `resume` differently (`codex` true, `local` false), so `local`'s retries take a new session with the
  prompt prepended, which is 5.5's path and is exercised only over fakes.

---

## 8. Anchor rulings the Operator granted, and why

Four, all recorded in the story specs. They are here so the *shape* of the exception is reusable, not
so they are treated as precedent for editing tests generally.

1. **Story 7-1 — the harness registry.** Four assertions pinned `build_harnesses` to `["claude"]`.
   They were rebound to the domain's own `HARNESS_NAMES` (`set(harnesses) <= set(HARNESS_NAMES)`), a
   *permanent* invariant, with exactness restored in a new file per story. Chosen over widening the
   literal precisely so the whole registration arc cost **one** edit rather than one per adapter, and
   so no assertion would sit red between 7-1 and 7-3.
2. **Story 7-3 — the alias table.** `ALIASES == {"claude": claude_aliases}` gained `local` in two
   files. Still an exact closed-set equality; `SUBSCRIPTION_ALIASES` needed no edit because
   `alias_table` was fixed to merge.
3. **Story 7-3 — the `GET /harnesses` field set.** Two closed-set equalities over `HarnessOut`'s field
   names gained `models`, taking them from seven to eight. **Deliberately the same edit the Operator's
   Epic 5 CAP-8 ruling made to the same two files**, and `api/schemas/harnesses.py` now records both
   rulings side by side.
4. **Story 7-5 — the `/runs` HISTORY placeholder.** A frozen spec asserted the deferral *copy*,
   "history arrives with the harness comparison epic". The ruling read "epic" as naming this story,
   since Epic 7 has exactly one CAP-5 owner and `runs/index.astro`'s docstring already said "the table
   itself is Epic 7". The assertion now reads `toContainText('HISTORY')` — the route is served, not
   the wording.

Two further edits were made under exceptions that already existed, without a new ruling, and both are
recorded:

- **Story 7-1** removed the `codex` row from `test_terminal_command.py`'s
  `parametrize("harness", ["local", "codex", ""])`. Registration made that row assert something false;
  two rows remain, and the same commit added coverage that codex now *does* get a terminal. This is
  hard rule 1's first exception as story 6-6 generalised it to parametrized rows.
- **Story 7-3** revised `test_codex_registry.py`'s exact-set assertions, which are story 7-1's own file
  and whose docstring names 7-3 as the thing that revises them — hard rule 1's second exception,
  used exactly as written.

**Every ruling shipped strictly-exceeding coverage in a new file in the same commit.** No test was
deleted, skipped or relaxed to make a gate pass, and no `SPEC.md`, `stories.yaml`, `epics.yaml` or
`AGENTS.md` line changed anywhere in the epic.

One process note for whoever orchestrates next, unchanged from Epic 6: **audit the diff, not the
warning.** And one new one — **state the "no subagents" rule as being about deadlock, not about
authorship.** Story 7-6 halted `blocked · no subagents` because `bmad-build-auto`'s step 3 mandates
handing implementation to a subagent and the dispatch forbade spawning one. That reading was
defensible; the fix is a clearer instruction, not a stricter agent.
