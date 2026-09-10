---
title: 'OpenCode readiness passes end to end with host model serving'
type: 'feature'
created: '2026-09-10'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: 'ac4360fff3a1dc55bfaef1da01abae8b7de28b89'
---

<intent-contract>

## Intent

**Problem:** `local` is registered and offered on New workflow (7.3), but every CLI-native
constant in `opencode/{adapter,events,sessions}.py` and `tracing/user_level.py` is provisional
— nothing has ever run against a real OpenCode binary or a real model on the Mac mini. The MVP's
definition of done for `local` needs either a passing readiness Run on a served model, or the
PRD §6.1 fallback recorded honestly.

**Approach:** A coding agent cannot close this — it needs a model server on the Mac mini, the
Operator's own judgement on whether a local model can finish the fixture story, and it must
never apply a host change or run the real CLI itself. So this dispatch: (1) verifies the proposed
host configuration `briefs/7-4-opencode-readiness-end-to-end.md` asks for already exists and is
live, rather than re-authoring it; (2) confirms — by reading the codebase, not by guessing —
that no new fallback code is required beyond what 7.2 and 7.3 already built; (3) lands a runbook
in this file that settles all eleven of 7.3's provisional values and drives the readiness Run;
(4) halts `blocked`, naming exactly what the Operator must start and run, because the host
precondition check performed during this dispatch already found one of the three services down.

## Boundaries & Constraints

**Always:** AD-2 (`domain`/`application` import no SDK); AD-10 (no adapter interprets model
output; static configuration is `opencode.sh`'s); AD-11 (`local` is found by user and session,
never by a parented span); AD-20 (a new setting lands in `settings.py` and `.env.example` in the
same change — moot here, see below); a module is at most 400 lines; new coverage goes in **new**
test files only.

**Block If:** landing this story requires editing an existing test file, `SPEC.md`,
`stories.yaml`, `epics.yaml` or any `AGENTS.md` — halt, naming the file and the assertion. **And
in every case: this story halts `blocked` once the host config is verified, the runbook is
committed, and any strictly-required code lands.** A coding agent never runs `opencode`, never
starts a model server, never calls `POST /harnesses/local/readiness`, and never writes a
"OpenCode — verified" block into `addendum.md` §B from anything it did not itself observe on a
live host — only the Operator's own run can supply that.

**Never:** proposing a host config change that is not actually needed (the story's own scope
says "written, not applied" — it does not say "written even when nothing needs to change");
recording any of 7.3's eleven provisional values as settled without a live observation behind
it; widening any harness's trace rule beyond what AD-10/AD-11 already assign it; guessing an
OpenCode flag or event field name — the runbook settles them.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Precondition check, this dispatch | `curl` against the host stack's own published ports, read-only | LiteLLM `/v1/models` `200` and lists `local-coder`/`local-general`; Langfuse `/api/public/health` `200` but `/api/public/observations` `404` (`events_only`); oMLX (`localhost:8000`) unreachable | Documented as a finding, not fixed — host changes are the Operator's |
| Host config, read against the brief's own AC | `host/litellm.config.yaml`, `host/README.md` | Both already state every `LOCAL_MODELS` alias as `openai/<served model>` with `use_chat_completions_api: true`, the `langfuse_otel` callback, and the restart command | No edit needed; recorded as verified-in-place rather than re-authored |
| Code fallback survey | every provisional constant 7.3 left in `opencode/*.py` and `tracing/user_level.py`, and the generic `LITELLM_SPEND_MATCH` fallback 7.2 built | all of it is structurally generic already — no harness-specific gap found that a new fallback would close | Recorded as "no code change" rather than invented to have something to land |
| Operator runs the runbook, oMLX still down | Step 0b's live check | `local-coder`/`local-general` answer `4xx/5xx`/timeout through the Gateway | **Stop and report** before dispatching a Run |
| Operator runs the runbook, Langfuse still `events_only` | Step 0c's live check | `trace observed` can never be `ok` however well the plugin traces | Continue anyway for the other five lines' evidence; record the PRD §6.1 fallback if `enabled` is never reached |
| Fixture story does not reach `done` on the bound local model within the readiness budget | Step 4's Run outcome | `local` stays `disabled: {failing line}` | The honest, acceptable outcome (PRD §6.1) — recorded in `addendum.md` §B by the *next* dispatch, once the Operator reports |

</intent-contract>

## Code Map

- `host/litellm.config.yaml:38-50` -- **already** carries `local-coder`/`local-general` as
  `openai/qwen3.8-27b-4bit` and `openai/qwen3.6-35b-a3b-4bit`, both `use_chat_completions_api:
  true`, `api_base: os.environ/OMLX_BASE_URL` -- matches `LOCAL_MODELS=local-coder,local-general`
  in `.env.example:49` exactly. Landed in `bb756f0` ("container images and the compose stack"),
  well before 7.3. Verified live this dispatch: `GET /v1/models` on the running host proxy lists
  both aliases (see below). **No change proposed.**
- `host/litellm.config.yaml:52-57` -- `callbacks: ["langfuse_otel"]` with the `LITELLM_OTEL_V2`
  comment already present. **No change proposed.**
- `host/README.md:92-108` -- the "## LiteLLM" section already documents `model_list`'s local
  entries and the restart command (`litellm --config host/litellm.config.yaml --port 4000`).
  **No change proposed.**
- `host/.env.example:51-52` -- `OMLX_BASE_URL=http://host.docker.internal:8000/v1`,
  `OMLX_API_KEY=not-set`. `host/README.md:168-192` already documents the port-8000 collision with
  `BACKEND_API_PORT` (`.env.example:14`) as an observed 2026-09-08 finding, and the fix (get a
  real oMLX serving that port, or point `OMLX_BASE_URL` elsewhere). **No change proposed.**
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py`,
  `events.py`, `sessions.py` -- 7.3's adapter, unchanged; read fully this dispatch. Every
  `[verify]` constant is exactly what the runbook below settles. No structural gap: the
  session-store fallback, the two-source session read, and the tokens-only usage envelope are
  all generic already.
- `backend-api/src/orchestrator/infrastructure/tracing/user_level.py` -- 7.3's `local` trace
  rule. Read fully this dispatch, including a static check of the installed SDK it calls (see
  Design Notes) -- both the query's keyword arguments and the response object's attribute names
  are confirmed, by source, to be real names on `langfuse==4.15.1` (the version pinned in
  `backend-api/pyproject.toml` / installed in `.venv`), which substantially de-risks two of the
  eleven provisional values without needing the live host. Still marked `provisional` in the
  code and in `addendum.md` §B -- a source-shape match is not the same claim as "observed on a
  live Run", and only the runbook below may promote it.
- `backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py`,
  `infrastructure/settings.py:litellm_spend_match` -- 7.2's `session`/`attempt_tag` fallback is
  harness-agnostic (it reads `end_user`/`session_id`/`request_tags` off any Gateway row); the
  `local` provider's own header config
  (`scripts/harness/opencode.sh:38`, `x-litellm-end-user-id`/`x-litellm-session-id`/
  `x-litellm-tags`) sends the identical shape `codex` does, so the same setting and the same
  runbook step (7b, mirroring 7.2's) cover `local` with no new code.
- `backend-api/src/orchestrator/application/use_cases/harness_readiness.py`,
  `harness_readiness_evaluate.py` -- both fully generic over `HARNESS_NAMES`; `local` needs no
  registry or evaluation change (confirmed by reading `start()` and `_lines()`/`_trace_line()`
  this dispatch -- neither branches on harness name beyond what 7.2/7.3 already added).
- `scripts/harness/opencode.sh` -- the `doctor()`/`configure()` shape the runbook's steps 2-3
  read back; not edited.
- `_bmad-output/planning-artifacts/mvp/addendum.md:250-281` -- 7.3's ten-row §B table for
  OpenCode; the runbook below is what the *next* dispatch turns into a "OpenCode — verified"
  block, once the Operator has reported.
- `_bmad-output/planning-artifacts/mvp/epics/epic-07-harnesses/stories/
  7-2-codex-readiness-passes-end-to-end.md` -- the shape this runbook reuses: front-loaded
  preconditions, numbered steps with a `→ report` / `**Decision:**` pattern, and a "What to send
  back" checklist. Read fully; not copied verbatim, because the harness differs.

**Read-only evidence (nothing here needs to change; recorded for the next dispatch).**
- `backend-api/tests/unit/test_source_limits.py` -- the 400-line cap; unaffected, nothing grew.
- `backend-api/tests/e2e/test_harnesses.py`, `tests/unit/test_harnesses_router.py` -- the closed
  field-set assertions 7.3 already revised under its own ruling; untouched here.

## Tasks & Acceptance

**Execution:**
- (none — see Design Notes for why no production file changes). No test, source, or config file
  under `backend-api/`, `host/`, or `.env.example` is edited by this dispatch.
- `_bmad-output/planning-artifacts/mvp/epics/epic-07-harnesses/stories/
  7-4-opencode-readiness-passes-end-to-end-with-host-model-serving.md` -- this file: the
  intent-contract, the code-map verification, and the Operator runbook below.

**Acceptance Criteria:**
- Given `host/litellm.config.yaml`, when read, then it lists every `LOCAL_MODELS` alias
  (`local-coder`, `local-general`) as `openai/<served model>` with `use_chat_completions_api:
  true` — **already true**, verified by reading the file and by querying the live host proxy's
  `GET /v1/models` during this dispatch (see below).
- Given any fix made to 7.3 or the tracer, when `make lint`/`make test` run, then it is
  unit-covered and green — **vacuously true**: no fix was needed, so nothing new needs coverage;
  `make lint` and `make test` still both exit 0 on the unchanged tree (see Verification).
- Given the host services' reachability at the moment of this dispatch, when checked, then the
  Blocking condition below names exactly which of the three is not reachable and why the Run
  cannot be dispatched by this agent.
- Given the runbook below, when the Operator follows it, then every one of 7.3's eleven
  provisional values has a numbered step that settles it from a live observation, and `GET
  /harnesses` is read verbatim rather than summarized.

## Design Notes

**Why no code lands in this dispatch.** The brief's own scope item 2 is "any code the fallbacks
require" — conditional on a fallback actually being required. 7.2 built two generic mechanisms
precisely because Codex's `responses` wire API might drop `TRACEPARENT` and the session header:
a session-level trace acceptance path, and a spend-match mode setting. Both are harness-agnostic
by construction (`SpendMatch` reads any Gateway row; `session_level.py`'s sibling,
`user_level.py`, already **is** `local`'s equivalent structural fallback, built in 7.3 — a time
window is `local`'s whole rule, not a fallback bolted onto a stricter default). Re-reading
`harness_readiness.py::start`, `harness_readiness_evaluate.py::_lines`/`_trace_line`, and
`litellm_spend.py` confirms none of the three branches on `"local"` in a way that is missing a
case — they are already exactly as generic as `codex`'s equivalents. Inventing a fallback here
to have something to land would be exactly the kind of speculative code hard rule 7 (no silent
retry) and the brief's own "Never" guard against — a constant nobody has observed yet, shipped
as if it were needed.

**Why the host config needed no changes.** `host/litellm.config.yaml` and `host/README.md`'s
model section were authored in `bb756f0`, ahead of this epic, as the reference shape the whole
epic's `local` harness was built against — 7.3's own module docstrings already point at
`LOCAL_MODELS`/`openai/<alias>`/`use_chat_completions_api` as settled facts about the *config*,
only the *CLI and model* being what is unverified. Querying the live host proxy this dispatch
(`GET /v1/models` against `http://localhost:4000`, the same port `LITELLM_BASE_URL` resolves to
from inside a container) returned exactly `claude-sonnet-4-6`, `gpt-5.4`, `local-coder`,
`local-general` — so the config is not just textually correct, it is the config a running proxy
is actually serving right now. Writing a second, unnecessary revision of it would contradict the
brief's own "written, not applied" framing, which presumes something needs proposing.

**The static SDK check, and what it does and does not settle.** `backend-api/.venv`'s installed
`langfuse==4.15.1` was read directly (not executed against a live server): `ObservationsClient
.get_many` genuinely takes `user_id`, `from_start_time`, `to_start_time` as keyword parameters,
its docstring states the response defaults to `core` **and** `basic` field groups (`basic`
includes `userId`/`sessionId`) when `fields` is not passed — exactly how `user_level_observed`
calls it — and `ObservationV2` genuinely carries `.user_id`/`.start_time` as real attributes
(Pydantic-aliased from `userId`/`startTime`). This settles that the code is not guessing the
*shape* of a library it depends on. It settles nothing about whether the OpenCode Langfuse
plugin actually populates `userId` the way `research/tracing.md` documents, and nothing about
whether this Langfuse deployment's read API can ever answer the query at all (`events_only`
still returns `404` regardless of parameter names) — both of those need the live host, and stay
provisional in `addendum.md` §B until the runbook below is run.

**Why the precondition check was performed by this agent rather than deferred whole to the
runbook.** The story's own dispatch text says "halt blocked with the reason if they are not
[reachable]" — an instruction to check, not merely to describe how the Operator would check.
Reading already-running host-service ports with `curl` is not starting the compose stack, not
calling the readiness endpoint, and not running a harness; it is the same class of read-only
check `host/README.md` itself documents. The result is below and drives the Blocking condition.

## Verification

**Commands:**
- `make lint` -- expected: exit 0 (no source changed; run to confirm the tree this story hands
  back is exactly as green as it was before this dispatch).
- `make test` -- expected: exit 0, same reason.
- `make openapi` -- not run: nothing API-shaped moved.
- `make e2e-api` / `make e2e-ui` / `make up` / `POST /harnesses/local/readiness` -- **not run**,
  by the brief's own "Operator and agent split": the first two need the compose stack and this
  dispatch does not bring it up; the last three are explicitly the Operator's.

**Manual checks performed this dispatch (read-only, against the already-running host stack):**
- `curl http://localhost:4000/v1/models` with `$LITELLM_API_KEY` → `200`, lists
  `local-coder`/`local-general` alongside the hosted models.
- `curl http://localhost:3000/api/public/health` → `200`; `curl .../api/public/observations
  ?limit=1` and `.../api/public/traces?limit=1` → both `404` (`events_only` mode, matching the
  documented 2026-09-08 finding — still true today).
- `curl http://localhost:8000/v1/models` (oMLX direct) → connection refused / no response.

---

# Operator runbook — proving `local` on the real host

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

This dispatch already ran 0a and 0c once, from this host, on 2026-09-10 (see `## Verification`
above). **Re-run all three anyway** — state may have changed since, and 0b in particular is the
one this dispatch could not check (oMLX answered nothing at all).

**0a. The Gateway answers, and serves both `LOCAL_MODELS` aliases.**

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $LITELLM_API_KEY" \
  "${LITELLM_BASE_URL%/}/v1/models"
curl -s -H "Authorization: Bearer $LITELLM_API_KEY" "${LITELLM_BASE_URL%/}/v1/models" \
  | grep -o '"id":"[^"]*"'
```

→ report the status code and the model ids. **Decision:** the first must be `200` and the list
must contain **`local-coder`** (the `local` entry of `READINESS_MODELS` in `.env`) and
**`local-general`**. This dispatch observed exactly that. If either is now missing, `host/
litellm.config.yaml` changed since — stop and report `host services unreachable: gateway no
longer serves local-coder/local-general`.

**0b. The local model server itself answers, and the Gateway can actually complete a call
through it — not merely list it.** This is the one precondition this dispatch could not check:
`curl` to `${OMLX_BASE_URL}` from this dev machine got no response at all (oMLX not running).

```bash
curl -s -o /dev/null -w 'omlx direct: %{http_code}\n' --max-time 5 "${OMLX_BASE_URL%/}/models"
curl -s -o /tmp/local-resp.json -w 'via gateway: %{http_code}\n' -X POST \
  -H "Authorization: Bearer $LITELLM_API_KEY" -H 'Content-Type: application/json' \
  -H 'x-litellm-end-user-id: precheck-run' -H 'x-litellm-session-id: precheck-attempt' \
  -H 'x-litellm-tags: run:precheck-run,attempt:precheck-attempt,story:0,harness:local,project:precheck' \
  -d '{"model":"local-coder","messages":[{"role":"user","content":"reply with the single word ok"}]}' \
  "${LITELLM_BASE_URL%/}/v1/chat/completions"
head -c 400 /tmp/local-resp.json; echo
```

→ report both status codes and the response body's first 400 characters. **Decision:** `omlx
direct` need not be `200` (oMLX's own `/models` route may differ) but must not be connection
refused/timeout — that alone means oMLX is not up. `via gateway` must be `200` with an actual
completion in the body. Anything else — **stop and report `host services unreachable: local
model server not serving local-coder`** — starting oMLX, pointed at the port `OMLX_BASE_URL`
names and serving both aliases, is the Operator action this story exists to ask for. Repeat for
`local-general` if you plan to bind the readiness Run to it instead.

Then check the spend log for the precheck request, exactly as 7.2's runbook does, because it
settles the same question for `local`'s own header shape (the `@ai-sdk/openai-compatible`
provider may or may not forward the `x-litellm-*` headers `scripts/harness/opencode.sh`'s
`opencode.json` configures):

```bash
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=precheck-run&start_date=2020-01-01&end_date=2099-12-31" \
  | head -c 1200; echo
```

→ report: did any row come back? For the row, report **`end_user`**, **`session_id`** and
**`request_tags`** verbatim. **Decision, carried into step 7:**
- `session_id == "precheck-attempt"` → the default `LITELLM_SPEND_MATCH=session` is correct.
- `session_id` empty/absent but `request_tags` holds `attempt:precheck-attempt` → **set
  `LITELLM_SPEND_MATCH=attempt_tag` in `.env` now**, before step 3, and say so in the report.
- no row at all → report it; `spend attributable` will fail regardless of the model.

**0c. Langfuse can be read back, not only written to.** This dispatch found this instance in v4
`events_only` mode on 2026-09-10 — every public read API answers `404`. Re-check; it may still
be true:

```bash
curl -s -o /dev/null -w 'observations %{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "${LANGFUSE_BASE_URL%/}/api/public/observations?limit=1"
curl -s -o /dev/null -w 'traces       %{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "${LANGFUSE_BASE_URL%/}/api/public/traces?limit=1"
```

→ report both status codes. **Decision:** both `200` → continue normally. Either `404` → the
`trace observed` line can never be `ok`, whatever the plugin does, and **`local` can never reach
`enabled` while this holds** (`host/README.md`'s own "Recorded, not decided" note). You can
still run steps 1-8 below for their settlement value — every one of 7.3's other provisional
values is independent of this — but plan for the outcome to be the PRD §6.1 fallback rather than
a pass, and record that this is *why*, not "the model failed," when you report back.

## Step 1 — build and start the stack

```bash
make up
docker compose ps
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:${BACKEND_API_PORT}/healthz"
```

→ report that `backend-api`, `web-client` and `postgres` are up and `/healthz` is `200`.
**Decision:** a `backend-api` that will not become healthy stops the runbook; report the tail of
`docker compose logs backend-api`.

## Step 2 — the CLI itself, before any Run *(settles value 1 — the argv)*

```bash
docker compose exec backend-api opencode --version
echo "pin: $OPENCODE_VERSION"
docker compose exec backend-api opencode run --help
```

→ report both version strings (must match) and the verbatim `opencode run --help` output.
**Decision:** confirm `--format json`, `--dir <path>`, and `-m <provider/model>` are real flags
spelled exactly as `adapter.py`'s `FORMAT_FLAG`/`DIR_FLAG`/`MODEL_FLAG` assume. If any differs,
the constant changes to what the help says and `addendum.md` §B records both old and new.

## Step 3 — the harness's own doctor and config *(settles values 7, 11)*

```bash
docker compose exec backend-api scripts/harness/opencode.sh doctor
docker compose exec backend-api cat "$AGENT_HOME/.config/opencode/opencode.json"
docker compose exec backend-api sh -c \
  "find / -path '*opencode-observability-plugin*' -iname '*.js' 2>/dev/null | head -5"
```

→ report: the doctor output (version, skill-discovery line, gateway-reachable line); whether
`opencode.json` carries the `litellm` provider, the five `{env:...}` headers, and both model
entries; and, for the first plugin file found, `grep -n "LANGFUSE_USER_ID\|userId" <file>` —
paste the matching lines. **Decision:** the plugin file confirms or corrects value 11 (that the
plugin reads `userId` from the `LANGFUSE_USER_ID` environment name at all, independent of what
value ends up in it). If no plugin file is found, report that too — `configure()`'s install may
not have completed and that is a finding in its own right, not a silent pass.

Also settle value 7 (**"no content switch"**) while you are in the file tree:

```bash
docker compose exec backend-api sh -c \
  "find / -path '*opencode-observability-plugin*' -iname 'README*' -o -path '*opencode-observability-plugin*' -iname 'package.json' 2>/dev/null | head -5"
docker compose exec backend-api sh -c \
  "grep -ril 'prompt\|content\|redact' \$(find / -path '*opencode-observability-plugin*' -iname '*.js' 2>/dev/null) 2>/dev/null | head -5"
```

→ report what, if anything, matched. **Decision:** nothing matching means the plugin documents
no content-logging toggle, which **confirms** `local_aliases`' docstring's recorded "no content
switch" rather than leaving it merely assumed. Anything matching is a new finding to report
verbatim, not to act on unattended.

## Step 4 — dispatch the readiness Run

Only if steps 0a/0b passed. If 0b failed, stop here — everything past this point needs a
completable model call.

```bash
curl -s -X POST -H "$AUTH" "$API/harnesses/local/readiness" | tee /tmp/readiness.json; echo
RUN=$(python3 -c 'import json;print(json.load(open("/tmp/readiness.json"))["id"])')
echo "run: $RUN"
```

→ report the status and the Run id. **Decision:** `404` means `local` is not in
`HARNESS_NAMES` (it is — this would be a real regression); `409` means either a readiness Run
for `local` is already in flight or `READINESS_MODELS` binds no `local` model (it does —
`local-coder`); `422` means the plan could not be read; report the body verbatim and stop.

Watch it:

```bash
watch -n 10 "curl -s -H '$AUTH' $API/runs/$RUN | python3 -m json.tool | head -40"
```

→ report the terminal status (`done`, `failed`, `needs_you`, `cancelled`) and, if `needs_you`,
the park kind and reason. **Decision:** any non-`done` outcome is a finding, not a retry —
capture it and continue to step 5 anyway.

## Step 5 — the six evaluation lines

```bash
curl -s -H "$AUTH" "$API/harnesses" | python3 -m json.tool
```

→ report, for the `local` item: `enabled`, `failing_check`, `last_readiness_at`,
`last_readiness_run_id`, `models`, and **all six `lines` entries with their `check`, `ok` and
`text` verbatim**. They are, in order: `story file done`, `session id recorded`, `trace
observed`, `spend attributable`, `verify exit 0` **or** `no quality gate to run`, `run done`.

**Decision, line by line:**
- `story file done` fails → step 8 says why.
- `session id recorded` fails → step 6 settles the field names from the stream, then the store.
- `trace observed` fails → if step 0c already answered `404`, this is expected and not a new
  finding — it is the PRD §6.1 trigger. If 0c answered `200` and this still fails, step 7a digs
  further.
- `spend attributable` fails → step 7b.
- the fifth line reading `no quality gate to run · ok` is **correct and expected**.
- `run done` fails → step 4 already recorded why.

## Step 6 — the event stream *(settles values 2, 3, 4, 5, 6)*

The log is `$WORK_DIR/logs/{run id}/{seq}-{attempt}.log`; the build row is the one whose path
ends `.build`.

```bash
docker compose exec backend-api sh -c "cat $WORK_DIR/logs/$RUN/*.log" > /tmp/opencode-stream.log
python3 -c "
import json
seen_session=None
for line in open('/tmp/opencode-stream.log'):
    line=line.strip()
    if not line.startswith('{'): continue
    try: o=json.loads(line)
    except Exception: continue
    if seen_session is None and 'sessionID' in o: seen_session=o['sessionID']
print('first sessionID:', seen_session)
"
tail -5 /tmp/opencode-stream.log
```

→ report: the first event carrying a session id, **verbatim, including the field name that
holds it** (settles value 2, `SESSION_ID_FIELD`); the **last event of the stream, verbatim**,
including whether it carries a `tokens` object with `input`/`output` keys (settles value 3,
`TOKENS`/`INPUT_TOKENS`/`OUTPUT_TOKENS`); and whether any event carries a cost/money field
(`events.py::STREAM_COST_USD = 0` is a recorded figure per PRD §11, not a placeholder — a money
field appearing would still be worth reporting).

**Decision:** if `sessionID` never appears in the stream, that is not a failure of this step —
it is exactly the case `adapter.py::_stored_session` exists for. Continue to the store check
below regardless, because it also settles values 4-6 independent of whether the fallback path
was exercised:

```bash
docker compose exec backend-api sh -c \
  "sqlite3 \"\$AGENT_HOME/.local/share/opencode/opencode.db\" '.schema session'"
docker compose exec backend-api sh -c \
  "sqlite3 \"\$AGENT_HOME/.local/share/opencode/opencode.db\" \
   \"SELECT id, directory, time_created FROM session ORDER BY time_created DESC LIMIT 5;\""
```

→ report the schema verbatim (settles values 4 and 5 — the store's path, table name `session`,
and column names `id`/`directory`/`time_created`), and the five most recent rows. **Decision:**
if the schema names these columns differently, `sessions.py`'s `SESSION_TABLE`/`ID_COLUMN`/
`DIRECTORY_COLUMN`/`ORDER_COLUMN` change to match. If the newest row for the attempt's own
worktree directory is indeed the session the stream named (or would have been the one picked had
the stream named none), that **confirms** value 6, "newest row for this directory" as the
fallback's rule; if a second session for the same directory sorts newer for an unrelated reason,
report that as a finding — it would mean the approximation `sessions.py`'s docstring already
flags is a live risk, not merely a documented one.

## Step 7 — trace and spend *(settles values 8, 9, 10)*

**7a. Whether the Langfuse plugin's generations show up under the Run's own user id, inside the
attempt's own window.** Skip straight to reporting `404`/unreachable if step 0c already found
`events_only` — there is nothing more to read from the API in that mode, and that finding *is*
the answer here too. Otherwise:

```bash
ATT=<attempt id from step 5's "session id recorded" line, or the Run detail's build attempt>
curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "${LANGFUSE_BASE_URL%/}/api/public/observations?userId=$RUN&limit=20" \
  | python3 -m json.tool | head -80
```

→ report the row count and, for one row, its `userId`, `startTime`, `sessionId` and `type`.
**Decision:** this is `user_level_observed`'s own query restated by hand — a row with `userId ==
$RUN` and a `startTime` inside the attempt's window (the Run detail's build attempt
`started_at`/`ended_at`) is what makes `attempt_observed` answer `True`. This dispatch already
confirmed, by reading the installed SDK, that `user_id`/`from_start_time`/`to_start_time` and
`.user_id`/`.start_time` are the SDK's real names (see Design Notes) — so a failure here is
evidence about the *plugin* or the *deployment*, not about a guessed parameter name. Report
which.

**7b. Whether `/spend/logs/v2` returned the attempt's rows** — the same two-query check as
0b's precheck, now against the real attempt:

```bash
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=$RUN&session_id=$ATT&start_date=2020-01-01&end_date=2099-12-31" \
  | python3 -m json.tool | head -40
curl -s -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "${LITELLM_BASE_URL%/}/spend/logs/v2?end_user=$RUN&start_date=2020-01-01&end_date=2099-12-31" \
  | python3 -m json.tool | head -60
```

→ report both row counts and one row's `end_user`, `session_id`, `request_tags`, `spend`,
`prompt_tokens`, `completion_tokens`, `model`. **Decision:** mirrors 0b — first query returning
rows means the default `session` mode is right; only the tag-narrowed second query returning
rows means flip `LITELLM_SPEND_MATCH=attempt_tag`, `make up` again, and re-run the readiness Run
(step 4 onward), reporting both before and after. Also confirm the recorded figure:

```bash
curl -s -H "$AUTH" "$API/runs/$RUN" | python3 -m json.tool | grep -n "cost\|provisional" | head -20
```

→ report `cost.provisional` and the build attempt's `cost_provisional`, and its tokens.
**Decision:** `cost_usd` should be `0` (PRD §11 — this is the recorded figure, not a
placeholder) and `cost_provisional` should be `False` once rows exist, with real token counts.

## Step 8 — the fixture story's own outcome, and the PRD §6.1 decision

```bash
docker compose exec backend-api sh -c \
  "find $WORK_DIR -path '*specs/readiness/stories/*' -name '1-*.md' | head"
docker compose exec backend-api sh -c \
  "cat \$(find $WORK_DIR -path '*specs/readiness/stories/*' -name '1-*.md' | head -1)"
```

→ report: whether the file exists, its frontmatter `status`, and its whole `## Auto Run Result`
verbatim. **Decision — this is the real one this story exists for:**
- `status: done` → the local model finished the fixture story inside the readiness budget. Combine
  with step 5's six lines: all `ok` → `local` reaches `enabled`, record the "OpenCode —
  verified" block. Any line still failing (most likely `trace observed`, if 0c was `404`) →
  `local` stays `disabled: {that line}`; record what passed and what didn't, honestly, rather
  than treating a story-level pass as a harness-level one.
- story file exists but not `status: done`, or the story was retried past the budget without
  finishing → this is the PRD §6.1 trigger on its own terms: the model could not do the work,
  independent of any plumbing question. Report the story's own `## Auto Run Result` verbatim —
  it names what the model attempted and why it did not finish — and report how many attempts the
  budget allowed and how many were used.
- no story file at all → `bmad-build-auto` was never discovered or never dispatched; report
  `docker compose logs backend-api | grep -i skill` and treat this as a plumbing finding
  distinct from the model's own capability.

**Decide, and say which:** ship `local` now (all six lines `ok`), ship it later once Langfuse
leaves `events_only` mode (everything else `ok`, only `trace observed` failing because of 0c),
or record the PRD §6.1 fallback because the model itself could not finish the fixture story. All
three are honest outcomes this story accepts.

## What to send back

One message, with:

1. step 0a — gateway status code, model ids present (re-confirming or correcting this
   dispatch's own 2026-09-10 reading).
2. step 0b — oMLX direct status, the gateway completion's status and body, and the precheck
   spend row's `end_user`/`session_id`/`request_tags` (or "no row").
3. step 0c — the two Langfuse read status codes (re-confirming or correcting `events_only`).
4. step 2 — `opencode --version` and the verbatim `opencode run --help` output.
5. step 3 — the doctor output; whether `opencode.json` holds the provider/headers/models;
   the plugin file's `userId`/`LANGFUSE_USER_ID` grep; the content-switch grep result.
6. step 4 — the Run id and its terminal status (plus park kind/reason if parked).
7. step 5 — `enabled`, `failing_check`, `models`, and all six lines verbatim.
8. step 6 — the first session-bearing event verbatim (or "none"); the last event verbatim;
   whether a money field appears; the store's `.schema session` output and its five newest rows.
9. step 7a — the observations query's row count and one row's fields (or "404 / events_only,
   as step 0c predicted").
10. step 7b — both spend queries' row counts and one row's fields; whether
    `LITELLM_SPEND_MATCH` had to change.
11. step 8 — the fixture story file's `status` and `## Auto Run Result` verbatim, and your own
    stated decision among the three outcomes step 8 lists.

Nothing is written into `addendum.md` §B until that message exists. Every value in the §B
"OpenCode — verified" block the next dispatch writes will be traceable to one of those eleven
items.

## Auto Run Result

Status: blocked
Blocking condition: **the local model server (oMLX) is not reachable.** This dispatch checked
all three preconditions live against the already-running host stack on 2026-09-10: LiteLLM
(port 4000) answered `200` on `/v1/models` and lists both `local-coder`/`local-general`; Langfuse
(port 3000) answered `200` on `/api/public/health` but `404` on `/api/public/observations` and
`/api/public/traces` (v4 `events_only` mode, the same finding 5.11 recorded for a different
reason); oMLX (port 8000) gave no response at all. Per the brief's own instruction to halt
blocked naming the missing precondition: **the Operator must start oMLX, serving both
`LOCAL_MODELS` aliases on the port `OMLX_BASE_URL` names**, then run the runbook above in order
and report back the eleven items its "What to send back" section lists. Resolving the Langfuse
`events_only` finding is not strictly required to attempt the Run (step 0c says so), but it is
required for `local` to ever reach `enabled` rather than land on the PRD §6.1 fallback — the
Operator should decide, before running, whether that resolution is worth doing first.

No host file needed a change: `host/litellm.config.yaml` and `host/README.md` already state the
proposed configuration this story's brief asks for, verified live against the running proxy
rather than re-authored. No production code needed a change: 7.2's spend-match fallback and
7.3's user-level trace rule are already exactly as generic as `local` needs, confirmed by reading
`harness_readiness.py`, `harness_readiness_evaluate.py`, and `litellm_spend.py` line by line
rather than assumed. A static check of the installed `langfuse==4.15.1` SDK (not a live call)
confirmed two of 7.3's eleven provisional values — the Langfuse query's keyword-argument names
and the response object's attribute names — match the SDK's real shape; both stay `provisional`
in `addendum.md` §B regardless, because a source-shape match is not a live observation and the
brief is explicit that only the Operator's own run may promote one.

### What landed

Nothing under `backend-api/`, `host/`, or `.env.example`. This story's landed artifact is this
spec file: the verified-in-place host config finding, the "no fallback code required" finding
with its evidence, and the Operator runbook above — which is this dispatch's whole scope per the
brief's own numbered list, items 1 (verified, not re-authored), 2 (none required, with the
evidence trail above), and 3 (this document).

### What did **not** land, and why

- **No `addendum.md` §B "OpenCode — verified" block.** Nothing was observed on a live Run, so
  nothing is recorded — the same discipline 7.2 held.
- **No `LITELLM_SPEND_MATCH` change.** Whether `local`'s provider drops the session header the
  way Codex's `responses` path did is exactly what step 0b/7b measure; this dispatch could not
  reach oMLX to make that measurement.
- **No edit to any `[verify]`/provisional constant in `opencode/*.py` or `user_level.py`.** The
  static SDK check above de-risks two of them but is deliberately not treated as settling them.

### Review pass — run inline

Run inline rather than through review subagents: this dispatch forbids spawning any (the same
constraint 7.1, 7.2 and 7.3 operated under), so the layers were executed by the same session
against the diff — which, for this story, is entirely this spec file plus the removal of no
production code, so the review's focus was the runbook's own completeness against the eleven
provisional values and the brief's four-item scope.

- intent_gap: 0 · bad_spec: 0 · patch: 2 (high 0, medium 0, low 2) · defer: 0 · reject: 1
- addressed:
  - `[low]` the first draft of step 7a queried `observations?sessionId=$RUN` (mirroring 7.2's
    trace query shape) instead of `?userId=$RUN` — `local`'s rule is user-level, not
    session-level (AD-11, `USER_LEVEL_HARNESSES`), and the wrong query parameter would have
    produced a misleading empty result even when the plugin traced correctly. Fixed to
    `userId=$RUN`, matching `user_level_observed`'s own call.
  - `[low]` step 6's store query originally assumed the stream always names no session, framing
    the store check as conditional. Reworded so the schema/rows check runs unconditionally — it
    settles values 4-6 regardless of which path the session id actually came from.
- rejected as noise: "propose a host config change anyway, so the story has a visible diff under
  `host/`" — the story's own scope is conditioned on a fallback or a config gap actually
  existing; manufacturing one to have something to show would misrepresent what this dispatch
  found.

### Verification

- `make lint` -- see the tail below.
- `make test` -- see the tail below.
- `make openapi` -- not run; nothing API-shaped moved.
- `make e2e-api` / `make e2e-ui` / `make up` -- not run; the brief's "Operator and agent split"
  reserves the stack and the real harness for the Operator.

### Residual risks

- **All eleven of 7.3's provisional values are still provisional.** This dispatch could not
  change that — it needed the live host, which this agent may not touch beyond read-only
  reachability checks. The runbook above is the only thing that can settle them.
- **The `events_only` Langfuse mode is a standing architectural question**, not something this
  story is scoped to resolve (`host/README.md`: "Recorded, not decided"). If it is still true
  when the Operator runs the runbook, `local` cannot reach `enabled` regardless of how well the
  model performs, and the honest recording is the PRD §6.1 fallback for that reason specifically
  — distinct from the model's own capability, which steps 4-8 still measure independently.
- **oMLX's own two model ids (`qwen3.8-27b-4bit`, `qwen3.6-35b-a3b-4bit`) are asserted in
  `host/litellm.config.yaml` but never confirmed against what oMLX actually serves.** Step 0b is
  where that gap closes or a real mismatch surfaces.
