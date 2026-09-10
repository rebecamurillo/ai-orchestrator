---
title: 'Codex readiness passes end to end'
type: 'feature'
created: '2026-09-10'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred: []
baseline_revision: 'b7ec4c25595273e1abe814508804a057aeccf4ca'
---

<intent-contract>

## Intent

**Problem:** `codex` has an adapter (7.1) and is registered, but nothing about it has been
observed: eleven values are provisional, `TRACEPARENT` honouring is source-verified only, and
whether `/spend/logs/v2` sees an attempt dispatched over the `responses` wire API is unknown.
A coding agent cannot close any of that — it needs the live CLI, the host LiteLLM and the host
Langfuse — so the story splits: the agent lands the code the two documented fallbacks require
and the runbook that settles the eleven values, and the Operator runs it.

**Approach:** Land three things and then halt `blocked`. (1) `Tracer.attempt_observed` gains a
harness-scoped, session-level acceptance path so a `codex` attempt whose spans did not parent
under the attempt span is still observable by `session_id == run_id` + the `attempt:` tag, and
logs which path answered. (2) `LiteLLMSpend` gains the tag-based query 5.3 left as a
swap-in — selected by one new setting, defaulting to today's verified `session` mode. (3) A
runbook in this file: every command the Operator runs, what to read in each output, and what
each outcome forces as a decision.

## Boundaries & Constraints

**Always:** AD-2 (`domain`/`application` import no SDK; the Langfuse and httpx calls stay in
`infrastructure/`); AD-10 (the trace check is still `Tracer.attempt_observed`, and `enabled` is
still written only by `harness_readiness_evaluate`); AD-11 (one exporter per harness; the
Gateway's spend log is the settled figure); AD-20 (a new setting lands in `settings.py` and
`.env.example` in the same change); AD-5 (`LITELLM_SPEND_KEY` stays backend-only); a module is
at most 400 lines — `langfuse_tracer.py` is at 328, so the new query goes in a sibling; new
coverage goes in **new** test files only.

**Block If:** the story cannot land beside an existing test, `SPEC.md`, `stories.yaml`,
`epics.yaml` or any `AGENTS.md` — halt, naming the file and the assertion. **And in every
case: this story halts `blocked` after the code and the runbook are committed.** Completing it
needs the Operator's run.

**Never:** running `make up`, starting the compose stack, calling `POST /harnesses/codex/
readiness`, installing or executing the Codex CLI, or running `make e2e-api`/`make e2e-ui`.
Never writing a "Codex — verified" block, or any value in it, that the Operator did not
observe — 5.7 shipped `stop_reason: "max_budget"` as a plausible constant behind a green test
and 5.11 disproved it. Never widening the trace check for `claude`: AD-10 makes parented spans
that harness's rule, and a fallback that silently applied to it would change what `enabled`
means for a harness this story is not about. Never guessing a Codex flag, event name or field
name: the runbook settles them.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parented, any harness | an observation under the trace names `attempt_id` in metadata, another names it as `parent_observation_id` | `True`; one log line, `path=parented` | unchanged |
| Codex, not parented, session-level present | no parenting observation; a trace with `session_id == run_id` carries tag `attempt:{id}` and names ≥1 observation | `True`; one log line, `path=session` | a failing query answers `False`, never raises |
| Codex, not parented, nothing session-level | the tagged query returns no trace | `False`; one log line, `path=none` | as above |
| Codex, tagged trace with zero observations | the trace is returned with `observations: []` | `False` — a trace row with no observation is not an observation | not an exception |
| Claude, not parented | a tagged session-level trace exists | `False` — the fallback is not offered to `claude` | not an exception |
| Harness unknown / not passed | `harness=None` | strict parented check only | not an exception |
| Spend, `session` mode (default) | `LITELLM_SPEND_MATCH=session` | query carries `end_user` **and** `session_id`; rows matched on both, exactly as 5.3 | unchanged: provisional zero |
| Spend, `attempt_tag` mode | `LITELLM_SPEND_MATCH=attempt_tag` | query carries `end_user` only; a row matches when `end_user == run_id` **and** its `request_tags` hold `attempt:{attempt_id}` | provisional zero, one log line naming the mode |
| Spend, tags in either shape | `request_tags` is a JSON list, or one comma-joined string | both read the same way | anything else → no match |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/tracer.py:80` -- `attempt_observed(run_id,
  attempt_id) -> bool`. Gains one keyword-only `harness: str | None = None`; defaulted so every
  existing caller and `tests/unit/test_tracer_port.py` (frozen) keep compiling.
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py:235` --
  `attempt_observed`'s real query (`api.observations.get_many`, page limit 100, matching
  `metadata["attempt_id"]` then any `parent_observation_id`). The primary check, unchanged; the
  fallback is called from here. **328 lines** — the new query cannot live here.
- `backend-api/src/orchestrator/infrastructure/tracing/session_level.py` -- new sibling: the
  `api.trace.list(session_id=…, tags=[…])` query and `SESSION_LEVEL_HARNESSES`.
- `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py:203` --
  `_trace_line`, the one caller. Passes `harness=build_attempt.harness` (`Attempt.harness` is
  `str | None`, `domain/entities/attempt.py:59`).
- `backend-api/tests/unit/fakes/tracer.py:60` -- `FakeTracer.attempt_observed`, the one fake for
  the port (AD-18, do not write another). Takes the same keyword and records it.
- `backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py:99` -- `_page` (the
  query params) and `:120` `_matches` (the client-side narrowing). These two are 5.3's "single
  function to swap". `LiteLLMSpend.__init__` already holds `Settings`.
- `backend-api/src/orchestrator/infrastructure/harness/env.py:92` -- `TAG_POSITIONS` and `:117`
  `tag_list`: the one place `attempt:{id}` is written today. Gains `attempt_tag(...)`, which the
  two readers import, so the writer and the readers cannot drift.
- `backend-api/src/orchestrator/infrastructure/settings.py:119` -- the Gateway block. One new
  field, defaulted (the `orch_test_mode` precedent at `:170`), plus its `.env.example` line —
  `scripts/check_env_contract.py` checks both directions inside `make lint`.
- `backend-api/tests/unit/test_langfuse_tracer.py:413` -- the `_StubClient`/`_StubObservation`
  shape the new tracer test copies. **Frozen**; new files instead.
- `backend-api/tests/unit/test_litellm_spend_adapter.py:26` -- the `httpx.MockTransport` shape
  the new spend test copies. **Frozen**.
- `backend-api/tests/unit/test_source_limits.py` -- the 400-line cap. **Frozen.**
- `host/README.md:253` -- Langfuse `events_only` blocks every public read API, so the
  `trace observed` line can never be `ok` against that deployment mode. This is the runbook's
  step 0 and the reason it can end `blocked` before the Run is ever dispatched.
- `_bmad-output/planning-artifacts/mvp/addendum.md:221` -- the 7.1 table of eleven provisional
  values. The runbook settles each; §B gains the verified block **only** once the Operator
  reports.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/infrastructure/harness/env.py` -- add `ATTEMPT_TAG_POSITION` and
  `attempt_tag(attempt_id)`. -- the `attempt:` tag is now read by two adapters; one definition.
- `backend-api/src/orchestrator/domain/ports/tracer.py` -- widen `attempt_observed` with the
  keyword-only `harness`. -- the acceptance rule differs per harness (AD-10, AD-11).
- `backend-api/src/orchestrator/infrastructure/tracing/session_level.py` -- new:
  `SESSION_LEVEL_HARNESSES`, `SESSION_TRACE_PAGE_LIMIT`, `session_level_observed(client, run_id,
  attempt_id)`. -- the fallback query, kept out of a module at 328 of 400 lines.
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py` -- take `harness`,
  call the fallback when the primary fails and the harness is in the set, and log which path
  answered. -- the Operator's only way to tell "honoured" from "fallback".
- `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py` -- pass the
  attempt's harness. -- the evaluation is the one caller that knows it.
- `backend-api/tests/unit/fakes/tracer.py` -- accept and record `harness`. -- the one fake for
  the port; a new double would violate AD-18.
- `backend-api/src/orchestrator/infrastructure/settings.py` -- `litellm_spend_match: SpendMatch =
  "session"`. -- AD-20; defaulted so an operator's existing `.env` keeps starting.
- `.env.example` -- the matching `LITELLM_SPEND_MATCH` line. -- AD-20, same change.
- `backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py` -- the two query/match
  modes. -- 5.3's documented fallback, made selectable.
- `backend-api/tests/unit/test_attempt_tag.py` -- new: the helper equals `tag_list`'s `attempt:`
  position. -- binds reader to writer without an index.
- `backend-api/tests/unit/test_tracer_session_level.py` -- new: every row of the matrix's trace
  half, over the fake and over `LangfuseTracer` with a stub client.
- `backend-api/tests/unit/test_readiness_trace_harness.py` -- new: `evaluate` passes the
  attempt's harness through to the tracer.
- `backend-api/tests/unit/test_litellm_spend_tag_mode.py` -- new: every row of the matrix's spend
  half, plus the setting's default and its `.env.example` line.
- `_bmad-output/planning-artifacts/mvp/epics/epic-07-harnesses/stories/7-2-codex-readiness-passes-end-to-end.md`
  -- the runbook below. -- the story's second deliverable.

**Acceptance Criteria:**
- Given a `codex` attempt whose spans did not parent, when a trace with `session_id == run_id`
  carries the tag `attempt:{id}` and names at least one observation, then `attempt_observed` is
  `True` and one log line records `path=session`.
- Given the same state but `harness="claude"`, when `attempt_observed` runs, then it is `False`
  and no session-level query is made.
- Given `LITELLM_SPEND_MATCH=attempt_tag`, when `spend_for_attempt` runs, then the request
  carries no `session_id` parameter and only rows whose `request_tags` hold `attempt:{id}` are
  summed.
- Given `LITELLM_SPEND_MATCH` unset, when `Settings()` is built, then the mode is `session` and
  the adapter's request is byte-for-byte what 5.3 already sends.
- Given `make lint` and `make test`, when run, then both exit 0.
- Given this file, when read, then the runbook names every command, every fact to report, and
  the decision each outcome forces — and every one of 7.1's eleven provisional values is settled
  by a numbered step.

## Design Notes

**Why the harness is a parameter and not a mode.** AD-10 pins the trace check per harness:
spans under the attempt span for `claude` and `codex`, generations under the Run session for
`local`. A fallback applied to whichever harness happened to miss would change what `enabled`
means for `claude`, whose readiness 5.11 left open for other reasons entirely. Keyword-only and
defaulted, so the port widens without a single existing call site or frozen test moving.

**Why a trace query and not an observation query.** `api.observations.get_many` accepts
`session_id`, but an observation carries no tags — the `attempt:` tag arrives as
`langfuse_tags` on the *trace*. `api.trace.list(session_id=…, tags=[…])` is the one query that
states both halves of "found by `session_id == run_id` with the attempt tag" server-side. A
returned trace whose `observations` list is present and empty is rejected: a trace row is not an
observation. Absent (the API did not expand the field) is accepted — the trace exists because
something was ingested under it — and the runbook has the Operator confirm that in the UI rather
than leaving it inferred.

**Why one log line and not a richer return value.** `attempt_observed -> bool` is the port, and
the readiness line's text is asserted verbatim by `tests/e2e/test_harnesses.py`. Neither may
move here. So which path answered is reported the only way that costs nothing: a structured log
the runbook greps.

**Why a setting for the spend mode, and why `session` is the default.** `attempt_tag` mode
cannot narrow the query server-side — `/spend/logs/v2` has no tag filter (`research/spend.md`) —
so it pulls every row of the Run and narrows client-side. That is strictly more work and is only
correct if the `x-litellm-tags` header survives the path `session_id` did not. Making it
automatic would be a silent retry (hard rule 7) and would hide the very finding this story
exists to record. One flag, one restart, one line in the runbook.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: exit 0

**Manual checks (if no CLI):**
- The runbook below is the manual check, and it is the Operator's, not this agent's.

---

# Operator runbook — proving `codex` on the real host

Everything below runs on the development host, from the repository root, with `.env` carrying
real host values. Nothing in it is optional and nothing in it is a guess: each step names what
to read and what the reading forces. **Report the facts marked → back verbatim.**

Set these once, in the shell you will use throughout:

```bash
cd <repo root>
set -a; . ./.env; set +a
API="http://127.0.0.1:${BACKEND_API_PORT}/api/v1"
AUTH="Authorization: Bearer ${ORCHESTRATOR_TOKEN}"
```

## Step 0 — the three preconditions, before anything is built

**0a. The Gateway answers, and serves the model `codex` will be told to use.**

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $LITELLM_API_KEY" \
  "${LITELLM_BASE_URL%/}/v1/models"
curl -s -H "Authorization: Bearer $LITELLM_API_KEY" "${LITELLM_BASE_URL%/}/v1/models" \
  | grep -o '"id":"[^"]*"'
```

→ report the status code and the model ids. **Decision:** the first must be `200` and the list
must contain **`gpt-5.4`** (the `codex` entry of `READINESS_MODELS` in `.env`). A `200` without
`gpt-5.4` — or with `gpt-5.4` present but upstream unfunded, which 5.11 observed as
`401 Incorrect API key provided: not-set` — means the readiness Run cannot complete a single
model call. **Stop and report `host services unreachable: gateway has no usable gpt-5.4`.**

**0b. `codex` talks to LiteLLM over the `responses` wire API, so prove that route, not `/chat`.**

```bash
curl -s -o /tmp/resp.json -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer $LITELLM_API_KEY" -H 'Content-Type: application/json' \
  -H 'x-litellm-end-user-id: precheck-run' -H 'x-litellm-session-id: precheck-attempt' \
  -H 'x-litellm-tags: run:precheck-run,attempt:precheck-attempt,story:0,harness:codex,project:precheck' \
  -d '{"model":"gpt-5.4","input":"reply with the single word ok"}' \
  "${LITELLM_BASE_URL%/}/v1/responses"
head -c 400 /tmp/resp.json; echo
```

→ report the status code and the first line of the body. **Decision:** `200` means the wire API
`codex.sh` configures is live. Anything else means the Codex path cannot work at all whatever
the CLI does — **stop and report `host services unreachable: /v1/responses {code}`**.

Then, and this is the single most valuable pre-check in this runbook, look for that request in
the spend log — it tells you *before* any Run whether the `responses` path keeps the attribution
headers:

```bash
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=precheck-run&start_date=2020-01-01&end_date=2099-12-31" \
  | head -c 1200; echo
```

→ report: did any row come back? For the row, report the values of **`end_user`**,
**`session_id`** and **`request_tags`** verbatim. **Decision, and carry it into step 7:**
- `session_id == "precheck-attempt"` → the default `LITELLM_SPEND_MATCH=session` is correct.
- `session_id` empty/absent but `request_tags` holds `attempt:precheck-attempt` → the responses
  path drops the session header and keeps tags: **set `LITELLM_SPEND_MATCH=attempt_tag` in
  `.env` now**, before step 2, and say so in the report.
- neither, but a row exists → report the row's keys; the spend line will fail and the cause is
  neither of the two shapes this story built for.
- no row at all → report it; `/spend/logs/v2` sees nothing on this path and the `spend
  attributable` line cannot pass.

**0c. Langfuse can be read back, not only written to.** 5.11 found this instance in v4
`events_only` mode, where every public read API answers 404 and `attempt_observed` — both its
primary query and this story's fallback — can only ever answer `False`.

```bash
curl -s -o /dev/null -w 'observations %{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "${LANGFUSE_BASE_URL%/}/api/public/observations?limit=1"
curl -s -o /dev/null -w 'traces       %{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "${LANGFUSE_BASE_URL%/}/api/public/traces?limit=1"
```

→ report both status codes. **Decision:** both `200` → continue. Either `404` → the trace check
cannot pass, and no amount of correct tracing changes that. Take this Langfuse out of
`events_only` mode and re-run 0c; if that is not possible today, **stop and report
`host services unreachable: Langfuse read API is events_only`** — this story then halts with
that as its recorded outcome, exactly as 5.11 did, and nothing is written to §B.

## Step 1 — build and start the stack

```bash
make up
docker compose ps
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${BACKEND_API_PORT}/healthz"
```

→ report that `backend-api`, `web-client` and `postgres` are up and `/healthz` is `200`.
**Decision:** a `backend-api` that will not become healthy stops the runbook; report the tail of
`docker compose logs backend-api`.

## Step 2 — the CLI itself, before any Run  *(settles values 1, 2, 5, 6, 7)*

Everything here reads the CLI's own help. It changes nothing and dispatches nothing.

```bash
docker compose exec backend-api codex --version
echo "pin: $CODEX_VERSION"
```

→ report both. **Decision:** they must match. A mismatch means `sync_pins` will have disabled
`codex` with `version pin changed: …` and the readiness Run is pointless until `.env` and the
image agree; report and stop.

```bash
docker compose exec backend-api codex --help
docker compose exec backend-api codex exec --help
docker compose exec backend-api codex exec resume --help
docker compose exec backend-api codex resume --help
```

→ report, for `codex exec`, whether each of these exists **and what its help text says**:

| # | Value 7.1 left provisional | What to look for in `codex exec --help` |
|---|---|---|
| 1 | `--json` | a flag that makes `exec` print an event stream as JSON lines. Report its exact spelling — `--json`, `--experimental-json`, or something else. |
| 2 | `-C <dir>` | the working-directory flag. Report its exact spelling and whether it is `-C`/`--cd`. |
| 3 | `-m <model>` | the model flag. |
| 4 | `-o <file>` | the "write the last message to this file" flag. Report the exact spelling and whether it takes a path. |
| 5 | `--skip-git-repo-check` | whether it exists, and what its help says it skips. |
| 6 | `-c key=value` | the config-override flag, and whether `otel.log_user_prompt` is a documented key (`codex --help` and, if present, `codex config --help`). |
| 7 | `codex exec resume <id>` | from `codex exec resume --help`: the exact positional/flag form for continuing a thread. |
| 8 | `codex resume <id>` | from `codex resume --help`: the interactive form, which is FR-21's paste line. |

**Decision:** for each row, either the shape `backend-api/src/orchestrator/infrastructure/
harness/codex/{adapter,events}.py` implements is confirmed, or it is wrong and the constant
named in `addendum.md` §B's table changes to what the help says. Report the **verbatim help
lines** for every row — the constant is edited from your quote, never from a summary.

Row 5 has one extra reading, which you can only get from step 4: if `--skip-git-repo-check`
exists and the readiness attempt fails with a git-repository complaint, it is needed under
`cap_drop ALL`; if the attempt runs, it is not, and §B's "open" row closes as "not needed".

## Step 3 — the harness's own doctor  *(settles the skill-discovery precondition)*

```bash
docker compose exec backend-api scripts/harness/codex.sh doctor
docker compose exec backend-api cat "$AGENT_HOME/.codex/config.toml"
docker compose exec backend-api ls "$AGENT_HOME/.agents/skills" | head -20
docker compose exec backend-api cat "$AGENT_HOME/.agents/skills/bmad-build-auto/SKILL.md"
```

→ report: the three `doctor` lines (`codex --version`, `bmad-build-auto discoverable in …`,
`gateway reachable at …`); whether `config.toml` holds `wire_api = "responses"`,
`env_http_headers` with all five names, and the `[otel]` block with the Langfuse endpoint; and
the first 10 lines of `SKILL.md`. **Decision:** a failing `doctor` line is fixed before the Run
— an absent `bmad-build-auto` means the image build's `bmad_install_global_skills` did not land
and the build step will come back `blocked` for a reason that has nothing to do with Codex.

## Step 4 — dispatch the readiness Run

```bash
curl -s -X POST -H "$AUTH" "$API/harnesses/codex/readiness" | tee /tmp/readiness.json; echo
RUN=$(python3 -c 'import json;print(json.load(open("/tmp/readiness.json"))["id"])')
echo "run: $RUN"
```

→ report the status and the Run id. **Decision:** `404` means the name is not in
`HARNESS_NAMES`; `409` means either a readiness Run for `codex` is already in flight or
`READINESS_MODELS` binds no `codex` model — the body says which. `422` means the plan could not
be read; report the body verbatim and stop.

Watch it:

```bash
watch -n 10 "curl -s -H '$AUTH' $API/runs/$RUN | python3 -m json.tool | head -40"
```

→ report the terminal status (`done`, `failed`, `needs_you`, `cancelled`) and, if it is
`needs_you`, the park kind and reason. **Decision:** any non-`done` outcome is a finding, not a
retry: capture it and continue to step 5 anyway — the six lines below still say which half
failed.

## Step 5 — the six evaluation lines

```bash
curl -s -H "$AUTH" "$API/harnesses" | python3 -m json.tool
```

→ report, for the `codex` item: `enabled`, `failing_check`, `last_readiness_at`,
`last_readiness_run_id`, `version_pin`, and **all six `lines` entries with their `check`, `ok`
and `text` verbatim**. They are, in order: `story file done`, `session id recorded`,
`trace observed`, `spend attributable`, `verify exit 0` **or** `no quality gate to run`,
`run done`.

**Decision, line by line:**
- `story file done` fails → step 8 says why (the agent's own outcome).
- `session id recorded` fails → the `thread.started`/`thread_id` names are wrong; step 6 settles
  them from the stream.
- `trace observed` fails → step 7a.
- `spend attributable` fails → step 7b.
- the fifth line reading `no quality gate to run · ok` is **correct and expected**: the readiness
  fixture declares no quality gate. A fifth line reading `verify exit 0 · not ok` is a real
  failure.
- `run done` fails → step 4 already recorded why.

## Step 6 — the event stream, read from the attempt's own log  *(settles values 3, 4)*

The log is `$WORK_DIR/logs/{run id}/{seq}-{attempt}.log`; the build row is the one whose path
ends `.build`.

```bash
docker compose exec backend-api ls -la "$WORK_DIR/logs/$RUN"
docker compose exec backend-api sh -c "cat $WORK_DIR/logs/$RUN/*.log" > /tmp/codex-stream.log
python3 -c "
import json,sys,collections
c=collections.Counter()
for line in open('/tmp/codex-stream.log'):
    line=line.strip()
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    c[o.get('type')]+=1
for k,v in c.items(): print(v,k)
"
grep -m1 -o '{[^}]*thread[^}]*}' /tmp/codex-stream.log
tail -5 /tmp/codex-stream.log
```

→ report: **every distinct `type` value in the stream with its count**; the **first event that
carries a thread/session id, verbatim**, including the field name that holds it; and the
**last event of the stream, verbatim**, including its usage envelope and every key inside it.

**Decision:** these three quotes settle four constants in `codex/events.py` —
`THREAD_STARTED`, `THREAD_ID`, `TURN_COMPLETED`, and the `USAGE`/`INPUT_TOKENS`/`OUTPUT_TOKENS`
trio. If any differs from what 7.1 implemented, the constant changes to the observed name and
`addendum.md` §B records both. Also report whether the stream carries any **cost or money
field**: 7.1 recorded `STREAM_COST_USD = 0` on the belief that Codex reports tokens only, and a
money field would make that a wrong constant rather than a conservative one.

Also:

```bash
docker compose exec backend-api ls -la "$WORK_DIR/logs/$RUN" | grep -E 'last.md|prompt'
```

→ report whether a `*.log.last.md` file exists and is non-empty. **Decision:** it is what
`-o` was supposed to write; empty or absent means the `-o` shape (value 4) is wrong even if the
flag was accepted.

## Step 7 — trace and spend

**7a. Which path answered the trace check.**

```bash
docker compose logs backend-api | grep -i "attempt trace observed" | tail -5
```

→ report the matching lines verbatim — each carries `path=parented`, `path=session` or
`path=none`, with the run and attempt ids. **Decision:**
- `path=parented` → **`TRACEPARENT` honoured**. Codex's `traceparent_context_from_env()` works
  as `research/tracing.md` §Codex read it from source. §B's last row closes as honoured, and the
  fallback this story built stays dormant.
- `path=session` → **`TRACEPARENT` not honoured · fallback: session-level.** The fallback is
  what made the line pass. Also open the trace in Langfuse and report what is under it —
  gateway generations only, or Codex CLI spans too:

  ```bash
  curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "${LANGFUSE_BASE_URL%/}/api/public/traces?sessionId=$RUN&limit=20" | python3 -m json.tool | head -60
  ```
  → report each trace's `name`, `tags` and the number of `observations`.
- `path=none` → neither. Report the same Langfuse query anyway: if it returns nothing at all,
  Codex's OTLP export is not reaching Langfuse and the `[otel]` block, not `TRACEPARENT`, is
  what is wrong.

**7b. Whether `/spend/logs/v2` returned the attempt's rows.** Take the attempt id from the
`session id recorded` line's text in step 5 — or from the Run detail's build attempt.

```bash
ATT=<attempt id>
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=$RUN&session_id=$ATT&start_date=2020-01-01&end_date=2099-12-31" \
  | python3 -m json.tool | head -40
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=$RUN&start_date=2020-01-01&end_date=2099-12-31" \
  | python3 -m json.tool | head -60
```

→ report, for both queries: the row count, and for one row the `end_user`, `session_id`,
`request_tags`, `spend`, `prompt_tokens`, `completion_tokens` and `model`. **Decision:**
- first query returns the attempt's rows → the default mode is right; nothing changes.
- first empty, second returns rows tagged `attempt:$ATT` → **the responses path drops
  `x-litellm-session-id` and keeps `x-litellm-tags`.** Set `LITELLM_SPEND_MATCH=attempt_tag` in
  `.env`, `make up` again, and re-run the readiness Run (step 4 onward). Report both the before
  and after.
- both empty → no attribution at all on this path; report it and the `spend attributable` line
  stays failing. Neither fallback helps and that is the finding.

Finally, whether the money is settled rather than the harness's guess:

```bash
curl -s -H "$AUTH" "$API/runs/$RUN" | python3 -m json.tool | grep -n "cost\|provisional" | head -20
```

→ report `cost.provisional` and the build attempt's `cost_provisional`. **Decision:** the
story's acceptance says the attempt's cost is non-provisional; `true` means the Gateway figure
never replaced the stream's zero.

## Step 8 — skill discovery and the subagent requirement

```bash
docker compose exec backend-api sh -c \
  "find $WORK_DIR -path '*specs/readiness/stories/*' -name '1-*.md' | head"
docker compose exec backend-api sh -c \
  "cat \$(find $WORK_DIR -path '*specs/readiness/stories/*' -name '1-*.md' | head -1)"
```

→ report: whether the file exists, its frontmatter `status`, and its whole
`## Auto Run Result` section verbatim.

**Decision:**
- `status: done` → `bmad-build-auto` was discovered from `~/.agents/skills`, ran against the
  worktree as project root, and subagents were available. Both halves of item 3 are closed.
- `Blocking condition: no subagents` → the skill was found and Codex cannot satisfy the subagent
  requirement. Report whether `codex --help` (step 2) names any agent/subagent/multi-agent
  feature or config key. That decides between a Codex feature flag and the 5.11 fallback; it is
  a decision for the Operator, not for the runbook, and it is recorded either way.
- no story file at all → the skill was never discovered. Re-read step 3's `SKILL.md` output and
  report `docker compose logs backend-api | grep -i skill`.
- any other blocking condition → report it verbatim; it is a finding about BMAD or the fixture,
  not about Codex.

## What to send back

One message, with:

1. step 0a — gateway status code, model ids present.
2. step 0b — `/v1/responses` status code; and the precheck spend row's `end_user`,
   `session_id`, `request_tags` (or "no row").
3. step 0c — the two Langfuse read status codes.
4. step 2 — `codex --version`, and the verbatim help lines for all eight rows of the table.
5. step 3 — the three `doctor` lines; whether `config.toml` holds `wire_api`, the five
   `env_http_headers` names and the `[otel]` block.
6. step 4 — the Run id and its terminal status (plus park kind/reason if parked).
7. step 5 — `enabled`, `failing_check`, and all six lines verbatim.
8. step 6 — every event `type` with its count; the thread event verbatim; the last event
   verbatim; whether a money field appears; whether `*.last.md` was written.
9. step 7a — the `attempt trace observed` log lines verbatim, and the Langfuse session query if
   the path was `session` or `none`.
10. step 7b — both spend queries' row counts and one row's fields; and whether
    `LITELLM_SPEND_MATCH` had to change.
11. step 8 — the readiness story file's `status` and `## Auto Run Result` verbatim.

Nothing is written into `addendum.md` §B until that message exists. Every value in the §B
"Codex — verified" block will be traceable to one of those eleven items.

## Auto Run Result

Status: blocked
Blocking condition: **the Operator must run the runbook above.** This story cannot be
completed by a coding agent: it needs the live Codex CLI, the host LiteLLM and the host
Langfuse, and credentials that never reach a harness process. The brief says so in its own
"Operator and agent split" section, and this dispatch was scoped to everything before the run
and everything after it, minus the run.

### What landed

Code, all of it unit-covered over the existing fakes, `make lint` and `make test` both exit 0:

| File | What changed |
|---|---|
| `backend-api/src/orchestrator/infrastructure/harness/env.py` | `ATTEMPT_TAG_POSITION`, `attempt_tag(attempt_id)` — the `attempt:` tag now has one definition, in the module that writes it. |
| `backend-api/src/orchestrator/domain/ports/tracer.py` | `attempt_observed` takes a keyword-only, defaulted `harness`. Every existing caller and the frozen `test_tracer_port.py` are unaffected. |
| `backend-api/src/orchestrator/infrastructure/tracing/session_level.py` | **new.** `SESSION_LEVEL_HARNESSES` (`codex` alone), `session_level_observed`, and the `PATH_*` constants. Asks Langfuse for traces of session `run_id` tagged `attempt:{id}`; a trace whose `observations` list is present and empty is rejected, absent is accepted. Never raises. |
| `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py` | 5.2's query becomes `_parented`; `attempt_observed` tries it first, then the fallback for a harness in the set, and logs `TRACE_OBSERVED` with `path=parented\|session\|none`. 375 of 400 lines — which is why the query is a sibling module. |
| `backend-api/src/orchestrator/application/use_cases/harness_readiness_evaluate.py` | `_trace_line` passes the build attempt's own harness. The line's wording is untouched, so `tests/e2e/test_harnesses.py`'s authorised assertion still holds. |
| `backend-api/tests/unit/fakes/tracer.py` | takes the same keyword and records it on `observed_calls`. The one fake for the port (AD-18); no second double was written. |
| `backend-api/src/orchestrator/infrastructure/settings.py` | `SpendMatch` and `litellm_spend_match: SpendMatch = "session"`. Defaulted, on the `orch_test_mode` precedent, so an existing `.env` keeps starting. |
| `.env.example` | the matching `LITELLM_SPEND_MATCH` line (AD-20, same change). |
| `backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py` | two modes. `session` is byte-for-byte 5.3's query. `attempt_tag` drops `session_id` from the query — the route has no tag filter — and narrows client-side on whole-tag equality against `request_tags`, read from either a JSON list or a comma-joined string. |

New test files (nothing existing was edited): `tests/unit/test_attempt_tag.py`,
`tests/unit/test_tracer_session_level.py`,
`tests/unit/application/test_readiness_trace_line_names_the_harness.py`,
`tests/unit/test_litellm_spend_tag_mode.py` — 41 tests.

### What did **not** land, and why

- **No `addendum.md` §B block.** Nothing was observed, so nothing is recorded. §B's 7.1 table
  still reads `provisional`/`open` on every row, which is the true state.
- **No fix to 7.1.** Every candidate fix depends on reading the CLI's own output, and the CLI
  is not on this host (`command -v codex` → nothing; the image installs it). Step 2 of the
  runbook is what produces the readings each constant would be edited from.
- **`LITELLM_SPEND_MATCH` stays `session`.** Switching it is a decision the runbook's step 0b
  or 7b makes from a measurement, not one this dispatch may make from a plausible story.

### Review pass — run inline

Run inline rather than through review subagents: this dispatch forbids spawning any (two Epic 6
stories deadlocked that way), so the layers were executed by the same session against the diff.

- intent_gap: 0 · bad_spec: 0 · patch: 3 (high 0, medium 1, low 2) · defer: 0 · reject: 2
- addressed:
  - `[medium]` `session_level_observed` took a built client, so a lazy client construction that
    raised would have escaped into a readiness evaluation — `_parented` swallows that failure
    and answers `False`, and the fallback would then have been the call that raised. It now
    takes the caller's accessor and builds inside its own guard; a test covers it.
  - `[low]` two magic values in a new test (`ruff` PLR2004) — named constants.
  - `[low]` formatting on four files — `ruff format`.
- rejected as noise: "make the fallback automatic when the primary finds nothing, for every
  harness" (it would widen `claude`'s AD-10 rule and hide the finding); "record
  `TRACEPARENT not honoured` now, since the fallback was built" (that is the exact class of
  guess 5.7 shipped and 5.11 disproved).

### Next dispatch

Resume this story with the eleven-item report the runbook's "What to send back" asks for. That
dispatch writes the dated **"Codex — verified"** block into `addendum.md` §B from those facts
alone, lands whatever constant the readings correct, and finishes the story.
