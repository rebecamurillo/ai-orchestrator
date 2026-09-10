# Addendum — AI Orchestrator MVP

Depth that belongs downstream (architecture, solutioning, stories) or that earned a place but is not a requirement. The PRD states *what*; this file records *how* and *why not otherwise*. The binding technical contract is `architecture/ARCHITECTURE-SPINE.md` (2026-09-02, `AD-1..AD-20`), which supersedes `../v1-dev-loop-2026-08-26/architecture-v1.md`; full rationale and research citations are in `../v1-dev-loop-2026-08-26/challenge-v1.md` and `architecture/research/`. This addendum does not duplicate them; it indexes and adds what the PRD conversation surfaced. Updated 2026-09-02 to match the spine.

## A. Technology decisions (pointers)
| Concern | Decision | Where |
|---|---|---|
| Durable engine | DBOS (Python) on the same Postgres, behind a `WorkflowEngine` port with opaque engine references, so a different engine is a new adapter only; the walker executes pre-planned `step_run` rows in order; human waits are `recv` on a per-Run topic; queue partitioned by Repository (`partition_concurrency=1`, `global_concurrency=2`); scheduled jobs (daily clone check, worktree GC, terminal poll) through the same port | spine AD-6, AD-7, AD-12 |
| Backend | Python 3.14, FastAPI + DBOS in one process, SQLAlchemy, Alembic, Pydantic, PyYAML; strict clean architecture (domain ← application ← api, infrastructure ← main) enforced by import-linter | spine AD-2, Stack |
| Contract | Pydantic schemas are the single source; OpenAPI exported to `contracts/openapi.json`; TypeScript types generated, never hand-written | spine AD-3 |
| Front-end | Astro 7 SSR on Node 24 with React islands, nanostores polling, CodeMirror 6, dagre layout; the browser talks only to the Astro server, which proxies to the backend with the bearer token | spine AD-1, Stack |
| Gateway | LiteLLM on the host; one instance key; attribution by tags + Langfuse session (Run id) + Gateway end-user (Run id) and session (Attempt id); spend read from `/spend/logs/v2`; `langfuse_otel` callback with `LITELLM_OTEL_V2=true`; local models as `openai/<alias>` with `use_chat_completions_api: true` so Codex's `/v1/responses` bridges | spine AD-11, research/spend.md |
| Tracing | Langfuse OTLP `/api/public/otel` (HTTP/protobuf, traces only); Run trace id seeded from the Run id, session id = Run id; Claude Code and Codex spans via inbound `TRACEPARENT` (native OTLP); OpenCode via the Langfuse plugin, session/user id only | spine AD-11, research/tracing.md |
| Method | BMAD pinned in the image (skill stubs under the agent home for every harness); target repositories commit `_bmad/` only; `repo-init@1` initialises them | spine AD-16 |
| Local models | oMLX on the host; Qwen3.8-27B 4-bit (coder, pinned), Qwen3.6-35B-A3B 4-bit (general, LRU); wired GPU limit raised to ~42 GB | challenge-v1 §6 |
| Containers | two (`web-client`, `backend-api`) plus Postgres in one compose file; backend non-root, `cap-drop ALL`, `no-new-privileges`, tooling: git gh node uv claude codex opencode bmad; per-harness `install · configure · doctor` scripts; every setting from `.env` | spine AD-20, Structural Seed |

## B. Harness matrix (from documentation, 2026-08-26)

> **Status: to be re-verified from each harness's own documentation when its adapter is built.** These CLIs change between releases — the 2026-08-26 pass already found `--full-auto` deprecated in Codex and `wire_api = "chat"` removed. Treat every flag below as a starting point, never as a contract; the contract is FR-14's capability list. **Codex and OpenCode technical details are deliberately deferred** (PRD §8).

**One item is confirmed by direct observation and is not provisional:** Claude Code 2.1.246 `-p --bare` exposes exactly `Bash, Edit, Read` — no subagent tool, no `Write`, no `Skill` — and neither `--add-dir` nor `--tools default` restores them, while default discovery exposes `Task`, `Write`, and `Skill`. `--bare` cannot run `bmad-build-auto`. Use default discovery with an explicit allowlist plus `--disallowedTools "mcp__*"` (a container has no personal MCP connectors, but the exclusion should be explicit).

See challenge-v1 §5 for the full table with doc citations. Facts that changed since the 2026-08-24 PRD's addendum and matter for stories:
- Codex `wire_api` accepts only `responses`; `--full-auto` is deprecated; `codex exec` is always approval `never`; `[otel]` now has separate `trace_exporter`; skills are read from `.agents/skills`; session ids cannot be pre-assigned.
- Claude Code: the docs recommend `--bare` for scripted calls — **do not follow that here** (see above); `.agents/skills` is **not** read; OTLP traces are beta behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`.
- OpenCode reads both `.claude/skills` and `.agents/skills`; `opencode run --format json --session <id>` (no `--auto` flag: auto-approval is config-driven through `opencode.json` permissions); provider config supports `headers` with `{env:NAME}` references; tracing through `@langfuse/opencode-observability-plugin`.
- Per-harness setup scripts (`scripts/harness/{claude,codex,opencode}.sh`, drafted in `architecture/deliverables/`) are the place these facts land; each writes its harness's static config from environment variable names only.
- LiteLLM: `/v1/messages` translation to any provider, Anthropic-native `/v1/models` for Claude Code gateway model discovery, header-driven Langfuse metadata (`langfuse_*`, `x-litellm-tags`, `x-litellm-session-id`), tag budgets via `/tag/new`.

### Claude — flags re-verified 2026-09-07 (story 5.1)

The brief requires the record whether or not anything changed. Nothing changed.

`claude --help` was read on the development host at **2.1.236**; `CLAUDE_CODE_VERSION` pins **2.1.258**, and only the older CLI was reachable, so this is a re-verification one patch line behind the pin and not against it. Every flag of the FR-14 invocation exists at 2.1.236 with the meaning the brief assumes, and no equivalent had to be substituted:

| Flag | Confirmed at 2.1.236 |
|---|---|
| `-p, --print` | "Print response and exit" — the headless mode |
| `--session-id <uuid>` | "Use a specific session ID … (must be a valid UUID)" — so `capabilities.preassign_session = true` holds |
| `--permission-mode <mode>` | choices include `dontAsk` |
| `--allowedTools, --allowed-tools <tools...>` | "Comma or space-separated list of tool names to allow" — the adapter passes the comma-joined `CLAUDE_ALLOWED_TOOLS` |
| `--disallowedTools, --disallowed-tools <tools...>` | same shape; `mcp__*` is passed as one word |
| `--output-format <format>` | choices `text \| json \| stream-json`, "only works with `--print`" |
| `--max-budget-usd <amount>` | "Maximum dollar amount to spend on API calls (only works with `--print`)" |
| `--model <model>` | present; omitted entirely when the Template bound no model |
| `-r, --resume [value]` | "Resume a conversation by session ID" — so `capabilities.resume = true` holds |

`--bare` is still the wrong tool and is still not used: its 2.1.236 help text now says so itself ("skip hooks, LSP, plugin sync … and CLAUDE.md auto-discovery", "Anthropic auth is strictly `ANTHROPIC_API_KEY` or `apiKeyHelper`"), which would break both skill discovery for `bmad-build-auto` and the gateway token the contract supplies as `ANTHROPIC_AUTH_TOKEN`. The 2026-08-26 observation above stands.

One deliberate deviation from the brief's own spelling, recorded because the brief requires deviations recorded: the brief writes resume as `claude -p --resume {id} --permission-mode dontAsk --allowedTools … --output-format json "{message}"`, and the adapter also passes `--disallowedTools "mcp__*"` there. A resumed attempt runs in the same container, on the same worktree, as the dispatch that opened the session; letting the MCP exclusion depend on which call started the turn would make the sandbox a property of the call rather than of the container. The flags `--resume` genuinely drops are `--session-id` (the session is named by `--resume`) and `--max-budget-usd` (the cap belongs to a dispatch).

Still open, and 5.11's to close by observation rather than by documentation: **the JSON field that marks a stop caused by `--max-budget-usd`.** `--help` does not name it, and 5.1 does not guess — `HarnessResult.raw_result` carries the parsed result object verbatim so 5.7 can read whichever field 5.11 records here.

### Claude — verified against the image, 2026-09-08 (story 5.11)

Everything below was observed on the dev compose stack (`make up`, project `aio-dev`) against
the running host LiteLLM (`:4000`) and Langfuse (`:3000`), on the **image's own** Claude Code —
which closes 5.1's disclosed gap: 5.1 read `--help` at 2.1.236 on the host, this pass read it
inside the container at **2.1.258**, the version `CLAUDE_CODE_VERSION` pins. No flag differs
from what 5.1 recorded, and `--permission-mode`'s choice list now reads verbatim
`acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`.

**Verified invocation** (`infrastructure/harness/claude/adapter.py::_argv`, unchanged):

```
claude -p --session-id <uuid> --permission-mode dontAsk \
  --allowedTools "$CLAUDE_ALLOWED_TOOLS" --disallowedTools "mcp__*" \
  --output-format json --max-budget-usd <remaining> "<prompt>"
```

**Allowlist.** `.env.example`'s default is unchanged and is what the dispatch would carry:
`Task,Bash(uv run *),Bash(git *),Bash(pnpm *),Bash(npm *),Bash(make *),Edit,Read,Write,Skill,ToolSearch`.
It was **not** exercised by a real agent dispatch — see "What is still open" — so PRD §8 item 1
is not closed. `--permission-mode dontAsk` itself is confirmed to exist and be accepted at
2.1.258.

**Cap-exit field — closed.** `--max-budget-usd` does **not** surface through `stop_reason`.
5.7's placeholder pair (`CAP_EXIT_FIELD = "stop_reason"`, `CAP_EXIT_VALUE = "max_budget"`) is
wrong: the literal `"max_budget"` occurs **zero times** anywhere in the shipped 2.1.258 bundle,
and `stop_reason` carries the model's own stop reason (`stop_sequence`, or `null`). The result
object's own zod schema in the shipped bundle declares the error variant as

```
subtype: ["error_during_execution", "error_max_turns",
          "error_max_budget_usd", "error_max_structured_output_retries"]
```

and the emitting branch reads `terminal_reason === "budget_exhausted"` → `subtype:
"error_max_budget_usd", is_error: true`. `terminal_reason` is `.optional()` in that schema;
`subtype` is not. **So the field is `subtype` and the value is `error_max_budget_usd`**, with
`terminal_reason: "budget_exhausted"` as the corroborating second marker.

This was read out of the CLI's own result schema rather than out of an observed cap stop: a
cap stop needs real model spend, and no model call can complete on this host (below). The two
constants in `application/steps/agent_tail.py` are therefore **still the placeholders** — see
"What is still open".

**`--max-budget-usd 0` and `0.00` are refused outright**, before any dispatch:
`option '--max-budget-usd <amount>' argument '0.00' is invalid. --max-budget-usd must be a
positive number greater than 0` (exit 1, no JSON at all). `render_budget`'s `NO_BUDGET =
"0.00"` therefore produces an argv the CLI rejects whenever a Run's remaining budget is zero
or negative. `0.01` and `0.001` are both accepted.

**Skill discovery from the worktree — closed, no fallback needed.** The image's
`~/.claude/skills/` carries all 49 BMAD stubs including `bmad-build-auto/SKILL.md`
(`scripts/harness/claude.sh doctor` reports `bmad-build-auto discoverable in
/home/agent/.claude/skills`), and the readiness fixture's origin carries a committed `_bmad/`
with `_bmad/scripts/render_skill.py`. Run inside a clone of that origin, the stub's own command

```
uv run --no-cache "<worktree>/_bmad/scripts/render_skill.py" \
  --project-root "<worktree>" --skill "/home/agent/.claude/skills/bmad-build-auto"
```

answers `read and follow <worktree>/_bmad/render/bmad-build-auto/.../workflow.md`. The worktree
resolves as project root and the global stub renders against it, so the
`SKILL_STUBS_INTO_WORKTREE` fallback 5.8 held in reserve was **not** built and is not needed.
(`.gitignore` in the fixture ignores `.claude/skills/bmad-*` exactly as a real repo-init does,
so the stubs are correctly absent from the worktree itself.)

**Two keys — closed (PRD §8 item 5).** Confirmed by direct call against the host proxy:

| Key | `GET /v1/models` | `GET /spend/logs/v2` |
| --- | --- | --- |
| `LITELLM_API_KEY` (virtual, `key_type: llm_api`) | `200` | **`403`** — `Virtual key is not allowed to call this route. Only allowed to call routes: ['llm_api_routes']. Tried to call route: /spend/logs/v2` |
| `LITELLM_SPEND_KEY` (master) | — | `200`, real rows |

The harness key cannot read spend and the spend key can. The generating commands are in
`host/README.md`.

**What is still open, and why — PRD §8 items 1, 2, 4 are NOT closed.** The `claude` readiness
Run did not reach `enabled`; `GET /harnesses` still reads `claude · disabled`. Four independent
findings, in the order they were hit:

1. **`scripts/readiness_fixture.sh` leaves the bare origin's `HEAD` unborn — diagnosed and
   patched, but held back; see the last paragraph.** `git init --bare` (no `-b`) leaves `HEAD`
   a symbolic ref to a `refs/heads/master` the fixture never creates, and
   `git ls-remote -- <url> HEAD` — exactly what the clone check's first line runs — then
   answers **zero lines** (exit 0, no output). The `readiness-repo` Repository read
   `clone_check.status: failed`, one line, `the remote answered no refs`; no base clone was
   made; and because `PlanReader` reads every list file out of that clone,
   `POST /harnesses/claude/readiness` answered `422 invalid plan — epic@1 line 24: list file
   not found: specs/readiness/stories.yaml`. With `git init --bare -q -b main` all four
   clone-check lines turn `ok` (`reachable, HEAD at ecd7fa9d…`, `cloned 69401 bytes`,
   `main at ecd7fa9d…`, `_bmad/_config/manifest.yaml states 6.11.0`) and the Run plans — that
   is how findings 2, 3 and 4 below were reached at all.
2. **`plan.check` parks `plan_stale` on the first `epic@1` Run of any new branch.**
   `application/templates/lists.py::read_list` records `plan_branches[path] = frame.branch`
   unconditionally, so the readiness Run recorded
   `list_branches: {"specs/readiness/stories.yaml": "readiness/claude/2026-09-08"}` — a branch
   the origin does not hold yet. `plan.check` then resolves `ls_remote(url, that branch)` to
   `None`, reads `current = None`, compares it against the real text, and parks
   `plan stale: specs/readiness/stories.yaml`. `PlanReader.record`'s own docstring states the
   intended contract — "`None` means … a Template naming one the remote does not hold yet" —
   so the recorded branch contradicts it. Every previous Run in this instance was
   `repo-init@1`, which names `{{base_branch}}`; this is the first `epic@1` Run ever executed
   here, which is why nothing caught it. **Epic 4 surface; not fixed here.**
3. **`continue` on a `plan_stale` park leaves the Run unrecoverable.**
   `signal_effects` applies `continue_accept`, taking the row `error → running` (its own
   docstring reasons this out of AD-13). Nothing then enqueues that row: the walk that
   follows finds no queued row, falls to `walk.close_run`, sees `plan` is not finished and
   parks `internal` — `no runnable step: plan is running`. Observed verbatim on Run
   `01a08187-cfb1-709d-8ebe-04999822573e`. **Epic 4/6 surface; not fixed here.**
4. **`POST /harnesses/{name}/readiness` accepts any name.** `harness_readiness.start`
   resolves the readiness Project and Repository but never checks `{name}` against the
   `harness` table, so `POST /api/v1/harnesses/not-a-harness/readiness` answers **201** and
   creates a real `epic@1` Run for a harness that does not exist —
   `GET /api/v1/harnesses/not-a-harness/readiness` correctly answers 404 for the same name.
   This is why the e2e suite reacts so strongly to finding 1: schemathesis drives every
   published operation, so once the fixture works, one fuzzing pass created **74** readiness
   Runs (`GET /templates/epic/1` then reads `pinned_by: 74` against its own frozen `== 0`).
   **Epic 5.8 surface; not fixed here** — see the last paragraph.
5. **The readiness Run binds no model, and Claude Code's default is not a Gateway model.**
   `epic@1`'s `model` input is optional and `harness_readiness.start` binds none, so the
   adapter omits `--model` and the CLI asks for its own default. Observed verbatim:
   `API Error: 400 … Invalid model name passed in model=claude-opus-5. Call /v1/models to view
   available models for your key.` The Gateway's `model_list` serves `claude-sonnet-4-6`,
   `gpt-5.4`, `local-coder`, `local-general`. **Not fixed here** — binding a model needs a
   setting and a default, which is an operator decision, not a story's.

**And the two host-side reasons the run could not have passed even so.**

- **No upstream provider credential on the Gateway.** `host/.env` carries
  `ANTHROPIC_API_KEY=not-set`, `OPENAI_API_KEY=not-set`, `OMLX_API_KEY=not-set`, and
  `OMLX_BASE_URL` resolves to the orchestrator's own API port rather than a running oMLX.
  Every model on `model_list` therefore fails: `claude-sonnet-4-6` → `401 invalid x-api-key`
  (upstream Anthropic), `gpt-5.4` → `401 Incorrect API key provided: not-set` (upstream
  OpenAI), `local-coder`/`local-general` → `404` from the orchestrator's own RFC 9457 handler.
  With no completable model call there is no agent attempt, no spend row, and no cap stop to
  observe — which is why items 1, 2 and 4 stay open and why the cap field above is read from
  the CLI's schema rather than from a run.
- **Langfuse runs in v4 `events_only` mode, and `attempt_observed` needs a read API.**
  `GET /api/public/observations` and `GET /api/public/traces` both answer
  `404 — This endpoint is not available on deployments running in Langfuse v4 events_only
  mode` on this 4.27.0 instance. `LangfuseTracer.attempt_observed` is exactly
  `api.observations.get_many(trace_id=…)`, and its `except` arm answers `False` rather than
  raising (SM-3). So readiness line 3, `trace observed`, can never be `ok` against this
  deployment mode no matter what the harness emits — OTLP **ingestion** is unaffected, only
  reads are. AD-10 makes the readiness verdict depend on a read API this mode does not serve;
  that is an architecture-level question, recorded here rather than decided.

**Why the one-line fix for finding 1 was not committed.** `make e2e` is green on this branch
today (145 passed) *because* the readiness endpoint always answers 422: nothing ever reaches
the `epic@1` path. Applying the `-b main` fix alone turns that gate red — measured, both ways,
on the same commit: **145 passed / exit 0 without it, 5 failed / 140 passed / exit 2 with it**
(`test_signals.py` ×4 and `test_templates.py::test_epic_1_shows_its_call_its_caller_and_its_inputs`).
The five failures are findings 2, 3 and 4 becoming reachable, not a defect in the fix: the
created Runs park `plan_stale`, `continue` cannot release them, and every `needs_you` Run then
outlives the sweep `test_every_needs_you_run_this_stack_holds_can_be_released` performs. No
combination of changes inside this story's authorised surface (5.1–5.8) restores green —
fixing finding 4 caps the fuzzer at three Runs rather than 74, and three still fails a frozen
`== 0`. So the fix belongs in the same change as finding 2's, on an Epic 4 surface this story
may not decide. The patch and its regression test are recorded verbatim in
`epics/epic-05-dev-loop/stories/5-11-claude-readiness-passes-end-to-end.md`.

**Deferred, not built (per the brief's own instruction to record and not build):** a target
repository's own Bash patterns extending `CLAUDE_ALLOWED_TOOLS` as a per-Project setting.
Nothing observed in this pass argued for or against it, because no agent dispatch ran.

### Codex — flags NOT re-verified 2026-09-09 (story 7.1)

The brief requires the record whether or not anything changed. **Nothing was verified, and that
is the record.** Codex CLI is not installed on the development host and story 7.1 does not run a
harness (running it is 7.2's, by the brief's own scope), so every flag below is the documented
shape from this section's 2026-08-26 pass and from `research/tracing.md` §Codex — implemented
because an adapter has to write *something*, marked provisional in the code where each one is
defined, and **not a fact until 7.2 has observed it on the real host at `CODEX_VERSION`**.

| Value | Where it lives | Status |
|---|---|---|
| `codex exec --json -C <worktree> -m <model> -o <log>.last.md "<prompt>"` | `codex/adapter.py` module docstring + `JSON_FLAG`/`WORKTREE_FLAG`/`MODEL_FLAG`/`LAST_MESSAGE_FLAG` | provisional |
| whether `--skip-git-repo-check` (or any sandbox flag) is needed under `cap_drop ALL` | **not passed**; `codex/adapter.py` docstring says why | open |
| `thread.started` / `thread_id` — the session capture | `codex/events.py` `THREAD_STARTED`, `THREAD_ID` | provisional |
| `turn.completed` / `usage.input_tokens` / `usage.output_tokens` | `codex/events.py` `TURN_COMPLETED`, `USAGE`, `INPUT_TOKENS`, `OUTPUT_TOKENS` | provisional |
| `codex exec resume <id> --json "<message>"` | `codex/adapter.py::CodexHarness.resume` | provisional |
| `-c otel.log_user_prompt=true` — the content switch | `codex/adapter.py` `CONFIG_FLAG`, `CONTENT_SWITCH` | provisional |
| `cd <cwd> && codex resume <id>` — FR-21's paste line | `codex/adapter.py` `RESUME_COMMAND` | provisional |
| `TRACEPARENT` honoured by `codex exec` | source-verified only (`research/tracing.md` §Codex) | 7.2's day-1 check |

Two decisions that are *not* provisional, because they follow from the spine rather than from the
CLI. **Cost is zero from the stream** (`codex/events.py::STREAM_COST_USD`): Codex reports tokens
and no money, and AD-11 makes the Gateway's spend log the settled figure — `agent_tail.usage`
already marks every harness figure `cost_provisional`. **`preassign_session` is `False`**, so
`HarnessHandle` carries no session on a first dispatch and `CodexHarness.wait` is the only half
that can report one; an attempt whose backend dies between `start` and `wait` therefore has no
session to resume, which is a property of a harness that names its own thread and not of the
adapter.

### OpenCode (`local`) — flags NOT verified 2026-09-10 (story 7.3)

The brief requires the record whether or not anything changed. **Nothing was verified against a
running CLI, and that is the record.** OpenCode is not installed on the development host, no
local model server is running, and story 7.3 does not run a harness — running it, against a real
model served on the Mac mini, is 7.4's by the brief's own scope. What was re-read is the
documentation this section's 2026-08-26 pass and `research/tracing.md` §OpenCode already cite;
nothing in either contradicted the shapes below, and nothing in either *confirms* them either.

| Value | Where it lives | Status |
|---|---|---|
| `opencode run --format json --dir <worktree> -m litellm/<model> "<prompt>"` | `opencode/adapter.py` module docstring + `FORMAT_FLAG`/`DIR_FLAG`/`MODEL_FLAG` | provisional |
| `sessionID` — the field the session is captured from | `opencode/events.py` `SESSION_ID_FIELD` | provisional |
| `tokens.input` / `tokens.output` — the usage envelope | `opencode/events.py` `TOKENS`, `INPUT_TOKENS`, `OUTPUT_TOKENS` | provisional |
| `~/.local/share/opencode/opencode.db` — the session store's path | `opencode/sessions.py` `STORE_RELATIVE_PATH` | provisional |
| table `session`, columns `id` / `directory` / `time_created` | `opencode/sessions.py` `SESSION_TABLE`, `ID_COLUMN`, `DIRECTORY_COLUMN`, `ORDER_COLUMN` | provisional |
| "newest row for this directory" as the attempt's session | `opencode/sessions.py::session_for_directory` | assumption |
| the plugin has **no content switch** | recorded, per the brief's `[verify; else record "no content switch"]`; `local_aliases` adds none | recorded, unverified |
| `api.observations.get_many(user_id=, from_start_time=, to_start_time=)` — the parameter names | `tracing/user_level.py::user_level_observed` | provisional |
| time-window attribution of a generation to one attempt | `tracing/user_level.py` module docstring | assumption (the brief's own `[ASSUMPTION]`) |
| `LANGFUSE_USER_ID` is what the plugin reads its `userId` from | `opencode/adapter.py` `LANGFUSE_USER_ID_ALIAS`, and `scripts/harness/opencode.sh` | doc-sourced, unverified |

Two things here are *not* provisional, because they follow from the spine and the PRD rather
than from the CLI. **Cost is zero and that is the recorded figure** (`opencode/events.py::
STREAM_COST_USD`, PRD §11): unlike Codex's identically-valued constant, this is not a placeholder
for a number the Gateway will replace — the Gateway's own spend rows for these models carry
`spend 0` too, and `record_attempt_spend` keeps them non-provisional because rows *existed*.
**All three capabilities are `False`**: OpenCode names its own session, has no resume form this
system uses, and honours no inbound `TRACEPARENT` (`research/tracing.md` §OpenCode: "no
traceparent/seed input"), so `resume_command` answers `None` and the Run detail hides FR-21's
terminal block for this harness.

## C. Rejected alternatives (MVP)
| Rejected | Why |
|---|---|
| JSON-schema structured output as the agent contract | Only Claude Code and Codex support it; the Story file frontmatter is what `bmad-build-auto` already writes and is Harness-independent. |
| Terminal `--resume` as the primary reply path | Claude/Codex only; depends on harness-local session content; invisible to the gate record. Kept as secondary. |
| Pipeline-stage board columns (Spec → Plan → Build → Review → Merged) | One dev loop; stage lives on the card; status columns put attention where it belongs. |
| Global serialization (one Run at a time) | Existed only for a shared E2E database that is out of scope. Repository-partitioned queue instead. |
| Visual workflow editor | A product in itself; YAML + rendered diagram covers the need. |
| Codex or Claude Code pointed at LiteLLM for local models instead of a third Harness | Kept as fallbacks (in that order) if the OpenCode adapter slips; OpenCode's skill discovery and chat-completions provider make it the better default. |
| Notifications inbox screen | Redundant for one operator; "Needs you" column + rail count. |
| Gateway virtual key per Project (`/key/generate`, monthly budget) | Dropped 2026-09-02: one instance key and identifier-based attribution give the same per-Run and per-Attempt figures without key management; per-Project budgets are deferred (spine AD-5, AD-11). |
| Global BMAD install in the image | Impossible: the method's scripts need `_bmad/` in the target repository. Skill stubs live in the image, `_bmad/` in the repository, `repo-init@1` puts it there (spine AD-16). |
| One endpoint per Operator action | Replaced by one `signals` endpoint with an enumerated kind, so every action shares one validation, one gate-record write, and one resume path (spine AD-13). |
| Steps created as the Run progresses | Replaced by planning every row before enqueue: "What will run" and the Run diagram are the same data as execution (spine AD-7). |

## D. Mechanisms (for solutioning)
- **Story-file evaluation** after a Story step: glob `{spec_folder}/stories/{id}-*.md`; exactly one match; parse YAML frontmatter; route on `status`; the whole `## Auto Run Result` section is shown as the Question (PRD FR-16).
- **Answer (revised at PRD finalization):** `git mv stories/{id}-{slug}.md stories/.answers/{id}-attempt-{n}.md`, append `## Human Answer` with timestamp and text, commit-guard; then dispatch folder+id again — with no `stories/{id}-*.md` present this is a *first dispatch*, so step-02 plans fresh — with the prompt suffix `Answer from the operator to the blocking condition "{condition}": {answer}`. Rejected: appending `## Human Answers` and resetting to `draft` — step-02 preserves the old `<intent-contract>` verbatim on a draft resume and the template has no such section, so the Answer would be overwritten or ignored.
- **Spec checkpoint:** dispatch prompt ends with "Halt after planning."; agent stops at `ready-for-dev`; Continue re-dispatches without the phrase; `bmad-build-auto` routes `ready-for-dev` straight to implementation.
- **Repository lock:** the engine port's partition key (`enqueue(run_id, partition_key=repository_id)`), held for the Run's whole life including `needs-you` — a workflow parked in `recv` still occupies its partition, which is exactly the lock. No release-on-park; rejected because it would require ending and re-enqueueing the workflow and would let two Runs share one Repository's worktrees (spine AD-12).
- **Planned rows:** `plan_run(template_version, inputs)` is pure, reads list files and callee versions from the remote branch at one SHA (`plan_ref`), and returns rows `{seq, path, kind, gate, status, with_resolved}`; `create_run` persists them before enqueue; pre-flight renders the same output without persisting (spine AD-7).
- **Two status writers:** `apply_step_result` for every execution transition, `signal_run` for every Operator transition; executors return results and never touch status (spine AD-8).
- **Signals:** `POST /runs/{id}/signals {kind, payload}`; validity per current status, gate-record write, and the worktree effect of each kind are the table in spine AD-13. Inline spec edits: `PUT /runs/{id}/files` (spec folder only, `needs_you`, not during a terminal session) committing `spec: operator edit (orchestrator)`. Active time: `POST /runs/{id}/activity {focused_seconds}` batched every 60 s into `run.active_seconds`.
- **Budget:** `Gateway.spend_for_attempt(run_id, attempt_id)` reads `GET /spend/logs/v2?end_user=<run_id>&session_id=<attempt_id>` after each Story step Attempt; `run.spend_usd` is the sum over Attempts (spine AD-11).
- **Protected paths:** `rules/protected_paths.check` on `Git.diff_names(attempt.start_sha)` after the harness exits and in the commit-guard against the frame's start SHA; `start_sha` is HEAD after the WIP commit *and* the prepare commit (see §I); the frozen test-file set is taken at the Story frame's first Attempt (spine AD-17, amended per §I).
- **Cancel rollback:** `git worktree remove --force` for every entry of `run.worktrees[]`; `git branch -D` only when that entry's `created_branch && !pushed`.
- **Credentials:** `GITHUB_TOKEN` per git command via `GIT_ASKPASS`; harness processes get exactly `HARNESS_ENV_CONTRACT` plus the Project's Fernet-decrypted env vars (spine AD-5, AD-10).

## E. FR lineage to the 2026-08-24 PRD
(ids below are the 2026-08-24 PRD's ids → this PRD's ids.) Kept in spirit: FR-1..5 (onboarding) → FR-2..4; FR-6..12 (templates, versioning, pinning) → FR-5..7; FR-13..18 (durable execution, park, resume, retry, cancel) → FR-12, FR-19, FR-20; FR-20..26 (agent tasks, session ids, per-task records) → FR-14, FR-16; FR-27/28 (gate strength, never green without oracle) → FR-16, NFR-2; FR-43..45 (trace, cost, budget) → FR-17, FR-26..28; FR-47/48 (serialization) replaced by FR-13. Dropped for MVP: FR-24a, FR-28b, FR-29, FR-12a/12f, FR-30/30a/31, FR-33..37, FR-38..42 (PR creation is a link), FR-46, FR-50..52 (only the manual-estimate capture survives), F9 entirely.

## F. The week (from challenge-v1 §7)
Day 1 infra + skeleton + the shipped Template YAML (`repo-init`, `story`, `epic`, `initiative`) · Day 2 Projects/Repositories/Clone check · Day 3 interpreter + Claude adapter + Board/New workflow · Day 4 Codex + OpenCode adapters + tracing + budget + queue + Run detail · Day 5 checkpoints, verify retry, cancel + Runs/Templates screens · Day 6 hardening + restart test + states · Day 7 dogfood on `fullstack-app`. Slips first: as PRD §6.1.

## G. Corrections surfaced at PRD finalization (applied in the spine 2026-09-02)
Every item below was taken up by `bmad-architecture`; the note in brackets says where it landed.
- **The agent commits:** `bmad-build-auto` step-04 commits reviewed work and halts `done` only on a clean tree; step-01 halts `blocked` on a dirty tree. The loop is therefore build (agent commits) → verify (deterministic, on the committed tree) → commit-guard (orchestrator commits leftovers only). [`story@1` Template, spine AD-9]
- **Dirty-tree pre-dispatch rule:** Before any Story step attempt: `git add -A && git commit -m "wip: story {id} attempt {n} (interrupted)"` when the Worktree is dirty (FR-12). [`steps/agent.py`; `attempt.start_sha` is taken after this commit and the prepare commit of §I — spine AD-17]
- **Step timeouts:** `timeout_min` per Step in the Template schema (defaults 90 / 30 / 5); process kill → Step `error` → Run `needs-you` (FR-10). [The `ProcessRunner` port owns the timer; the engine never times a step — spine AD-14. Earlier wording "the DBOS step wrapper owns the timer" is withdrawn.]
- **Done checkpoint mechanism:** `pause_when` cannot hang off the `agent` Step alone. [`for_each` carries `pause_before_item_when` / `pause_after_item_when`; the planner turns them into `checkpoint` rows at `…stories[n].before` / `…stories[n].after`; the spec checkpoint stays a status of the `agent` row — spine AD-7, AD-9]
- **Budget check timing:** After each Story step attempt, before verify (FR-17). The Claude adapter additionally passes `--max-budget-usd = remaining budget` as a harness-local cap; Codex/OpenCode have no equivalent, so the Gateway sum is the contract. [spine AD-10, AD-11]
- **Daily Clone check:** a scheduled job. [`engine.schedule(name, cron, job)` on the engine port; DBOS `create_schedule` in the adapter — spine AD-6, AD-14]
- **Worktree retention, PR link:** as PRD FR-9 and FR-11. [`worktree_gc` job; `pr.link` kind appends compare URLs per epic — spine AD-14]
- **Verify failure re-dispatch:** append `## Verify Failure` (command, exit code, output tail) to the Story file, set `status: in-progress` → `bmad-build-auto` step-01 routes `in-progress` to step-03 (implement → verify → review). Rejected: re-dispatching a `done` file (routes to a review pass that never sees the failure) and a freeform fix prompt (its spec lands outside the Spec folder). [`on_fail: {redispatch, max: 1}` on the verify Step — spine AD-9]
- **Skip:** the frame's remaining agent/checkpoint rows are marked skipped, its verify row runs as the re-baseline, its commit-guard commits `story {id}: skipped by operator`; no reset to a pre-story SHA in the MVP (COULD later: `git reset --hard {story_start_sha}` option). [spine AD-13]
- **Orphan control:** `start_new_session=True` / `os.setsid`, PGID on the Attempt; re-attempt kills the group and waits for `.git/index.lock`. [`ProcessRunner.kill_group`, `attempt.pgid` — spine AD-14]
- **Harness readiness check:** a fixture Repository with a one-line Story; each adapter must reach `done` and its spend must be attributable before it is enabled. [PRD FR-33; `fixtures/readiness-repo/`, spine AD-10.] `claude` allowlist must include the subagent tool (`CLAUDE_ALLOWED_TOOLS`, PRD §8 item 1). Per-harness overrides of `implementation_handoff`/`review_layers` live in the *target Repository's* `_bmad/custom/bmad-build-auto.toml`, so the orchestrator would have to write them into the Worktree — avoid unless the readiness run fails.
- **Gate record:** a first-class entity (see Glossary): `gate_record(run_id, at, path?, event, actor, text)`, append-only, written on every Run transition. [spine AD-8]

## H. Day-1 verification queue
PRD §8 items 1–4, run through the readiness run (FR-33) on the fixture repository; each under an hour; each decides a day-3 or day-4 story. The spine's "Open at handoff" adds one architecture-internal check (the engine adapter's step-id assumption) that has no PRD counterpart.

## I. Feedback to the spine (2026-09-02 PRD update)
Status: **absorbed** — applied to the spine by `bmad-architecture` (update) on 2026-09-02 (`architecture/reviews/reconcile-prd-update.md`: 13/13). Kept as the record of what the PRD gate fed back; the spine is again the binding contract.
- **Prepare commit (AD-9, AD-17):** the `agent` executor order becomes WIP commit → orchestrator writes (`project-context.md`, Answer archive, `## Verify Failure`) → commit `orchestrator: prepare story {id} attempt {n}` → `start_sha` → dispatch. Without it `bmad-build-auto` step-01 halts on the dirty tree at every first dispatch.
- **Protected test set at frame start (AD-17):** freeze `test_globs` matches at the Story frame's first Attempt, not each Attempt, or the verify redispatch parks on the agent's own new tests.
- **`story@1` is callee-only; readiness runs `epic@1` (AD-10, AD-16, Structural Seed):** `story@1` has no `git.worktree`; `fixtures/readiness-repo/` runs through `epic@1` under a built-in Project `readiness`; New workflow offers `initiative`, `epic`, `repo-init`.
- **Signals (AD-13):** `answer` also valid when `park_kind = checkpoint` (Reject with a reason); `continue` valid when `park_kind = protected_path` (accept); new `Park.kind = plan_stale` with `continue | cancel`; `budget_raise` resumes at the row's routed status (a `blocked` row goes straight back to `blocked`); `skip_epic` keeps the epic's `git.push` / `pr.link` planned unless the push is the stop; `terminal_resume` marks the `agent` row `done` (actor `terminal`) before verify.
- **Park kinds (AD-13, AD-8):** `push_rejected` also covers `sync: branch diverged`; `misconfigured` also covers `no story file`, `ambiguous story file`, `unexpected status`, `harness exit`, `gateway unreachable`; `failed` reason `parked 30 days` on `recv` expiry.
- **Stale-plan check (AD-7):** the walker's first step compares the list files at the branch head with `plan_ref` and parks `plan_stale` on difference; `PUT /runs/{id}/files` refuses `stories.yaml` / `epics.yaml`.
- **`git.sync` (kinds table):** no-op when the branch has no upstream; `retry` on `push_rejected` rows syncs first.
- **Install (kinds table vs `epic@1`):** `install_command` runs inside `git.worktree`; drop the separate `install` shell step from `epic@1`.
- **Two Gateway keys (AD-5, AD-11, `.env.example`):** `LITELLM_API_KEY` (model calls, harness env) and `LITELLM_SPEND_KEY` (orchestrator only, `/spend/logs/v2`); `HARNESS_ENV_CONTRACT` carries the first only. PRD §8 item 5.
- **Harness readiness state (new field or entity):** `harness{name, enabled, last_readiness_at, failing_check, version_pin}` and `POST /harnesses/{name}/readiness`; no counterpart exists in the spine today.
- **Clone check reads the method version (AD-14):** `clone_check{status, at, output, bmad_version}` from `_bmad/_config/manifest.yaml` at the default branch.
- **Global concurrency as a setting (AD-12, `.env.example`):** `MAX_ACTIVE_RUNS` (default 2); queue reason `global concurrency, held by {runs}`.
- **Graph (AD-15):** group token adds `SKP` when all children are skipped; cards show the human label of a path, the Steps table the raw path.
