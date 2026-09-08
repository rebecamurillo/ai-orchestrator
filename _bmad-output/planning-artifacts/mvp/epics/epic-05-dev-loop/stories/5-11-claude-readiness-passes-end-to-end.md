---
title: 'Claude readiness passes end to end'
type: 'feature'
created: '2026-09-08'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: "scripts/readiness_fixture.sh bare-origin HEAD fix diagnosed, patched and proven, but not committed: it turns `make e2e` red for reasons on an Epic 4 surface this story may not change."
    evidence: "make e2e exit 0 / 145 passed without the patch; exit 2 / 5 failed with it, on the same commit."
    location: "scripts/readiness_fixture.sh:30"
    severity: high
  - summary: "application/templates/lists.py::read_list records the working branch even when the remote does not hold it, so plan.check parks plan_stale on the first epic@1 Run of any new branch."
    evidence: "list_branches {\"specs/readiness/stories.yaml\": \"readiness/claude/2026-09-08\"} on Run 01a08187-cfb1-709d-8ebe-04999822573e; PlanReader.record's own docstring states the opposite contract."
    location: "backend-api/src/orchestrator/application/templates/lists.py:110"
    severity: high
  - summary: "continue on a plan_stale park takes the row error -> running and nothing enqueues it; walk.close_run then parks internal and the Run is unrecoverable."
    evidence: "alert `no runnable step: plan is running`, park_kind internal, on Run 01a08187-cfb1-709d-8ebe-04999822573e after POST /signals {kind: continue}."
    location: "backend-api/src/orchestrator/application/use_cases/signal_effects.py:24"
    severity: high
  - summary: "POST /harnesses/{name}/readiness accepts any name and creates a real epic@1 Run for a harness that does not exist; the GET on the same path answers 404."
    evidence: "POST /api/v1/harnesses/not-a-harness/readiness -> 201, Run 01a08198-27e3-72e7-855c-d7ed513cd142."
    location: "backend-api/src/orchestrator/application/use_cases/harness_readiness.py:82"
    severity: medium
  - summary: "The readiness Run binds no model, so Claude Code asks for its own default (claude-opus-5 at 2.1.258), which no Gateway model_list here serves."
    evidence: "API Error: 400 ... Invalid model name passed in model=claude-opus-5."
    location: "backend-api/src/orchestrator/application/use_cases/harness_readiness.py:87"
    severity: high
  - summary: "ANCHOR CONFLICT: the observed cap-exit field cannot be written into agent_tail's constants without editing a frozen test."
    evidence: "tests/unit/application/steps/test_agent_tail_budget.py:88 scripts raw_result={\"stop_reason\": \"max_budget\"} as a literal."
    location: "backend-api/tests/unit/application/steps/test_agent_tail_budget.py:88"
    severity: high
  - summary: "ANCHOR CONFLICT: render_budget's NO_BUDGET = \"0.00\" is refused by the CLI, and correcting it edits a frozen assertion."
    evidence: "claude --max-budget-usd 0.00 -> `must be a positive number greater than 0`; tests/unit/test_claude_adapter.py:459 asserts \"0.00\"."
    location: "backend-api/tests/unit/test_claude_adapter.py:459"
    severity: medium
---

<intent-contract>

## Intent

**Problem:** The `claude` harness has never run for real. Everything Epic 5 built — the adapter, the tracer, the Gateway spend read, the agent executor, the budget halt, the readiness Run — was proven against fakes only, and PRD §8 items 1–5 were still open questions rather than observed facts.

**Approach:** Drive `POST /harnesses/claude/readiness` on the dev compose stack against the real host LiteLLM and Langfuse, resolve each §8 item from what the run actually shows, and record the verified invocation, allowlist, cap-exit field, header behaviour and key setup in `addendum.md` §B and `host/README.md`.

## Boundaries & Constraints

**Always:** Observe, never infer — a run not seen reaching `enabled` has not reached `enabled`. Every fix to 5.1–5.8 carries a unit test. `make lint` and `make test` pass; `make e2e`, `make e2e-ui` and `make durability` stay at the result they had before this story.

**Block If:** The host services cannot serve a model call, or a required correction can only be made by editing a frozen test, `SPEC.md`, `stories.yaml` or an `AGENTS.md`, or the correct fix lies on an Epic 4/6 surface this story does not name.

**Never:** Fabricate a readiness result. Stop, restart or reconfigure the host containers. Build the `codex` or `local` adapters. Commit a change that turns a landed gate red.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Readiness run, all six lines ok | host services serving model calls | `GET /harnesses` shows `claude · enabled`, `last_readiness_at` set | not reached — see Auto Run Result |
| Harness key on `/spend/logs/v2` | `key_type: llm_api` virtual key | `403`, `Virtual key is not allowed to call this route` | observed, closed |
| Spend key on `/spend/logs/v2` | master key | `200` with rows | observed, closed |
| Skill discovery from the worktree | global stub + committed `_bmad/` | `render_skill.py` resolves the worktree as project root | observed, closed; no fallback needed |
| Cap exit | `--max-budget-usd` reached | result `subtype: error_max_budget_usd` | read from the CLI's own result schema |
| `--max-budget-usd 0.00` | budget exhausted | CLI refuses the argument outright | anchor conflict, reported |
| Bare origin with unborn HEAD | `git init --bare` without `-b` | `git ls-remote -- url HEAD` answers nothing | diagnosed, patched, held back |

</intent-contract>

## Code Map

- `scripts/readiness_fixture.sh:30` -- `git init --bare -q "${ORIGIN}"`; the missing `-b main` is finding 1.
- `backend-api/src/orchestrator/application/use_cases/clone_check.py:265` -- `_reachable` calls `Git.ls_remote(url)` with no ref; `None` becomes `the remote answered no refs`.
- `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py:146` -- `ls_remote(url)` with `ref=None` runs `git ls-remote -- <url> HEAD`, which is what an unborn HEAD answers nothing to.
- `backend-api/src/orchestrator/application/templates/lists.py:110` -- `read_list`; `reader.record(path, ref_used, branch=frame.branch)` records the working branch unconditionally (finding 2).
- `backend-api/src/orchestrator/application/templates/reader.py:70` -- `PlanReader.record`'s docstring states the contract the line above breaks.
- `backend-api/src/orchestrator/application/templates/plan.py:97` -- `Frame.branch = working_branch(...)`, set even when `plan_ref` had to fall back to the base branch.
- `backend-api/src/orchestrator/application/steps/plan_check.py:74` -- `_first_stale_path`; `ls_remote(url, branch)` is `None` for a branch the remote lacks, so `current` is `None` and the row parks.
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py:24` -- `continue` on `plan_stale` is `error → running` (finding 3).
- `backend-api/src/orchestrator/application/use_cases/walk.py:384` -- `close_run` parks `internal` when a row is neither queued nor finished.
- `backend-api/src/orchestrator/application/use_cases/harness_readiness.py:82` -- `start`; no `{name}` validation (finding 4), no `model` bound (finding 5).
- `backend-api/src/orchestrator/application/steps/agent_tail.py:111` -- `CAP_EXIT_FIELD` / `CAP_EXIT_VALUE`, the placeholders this story was to close.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:115` -- `NO_BUDGET = "0.00"`, refused by the CLI.
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py:235` -- `attempt_observed`, a read-API call the host's `events_only` mode does not serve.
- `backend-api/tests/e2e/test_schemathesis.py` -- drives every published operation; why finding 4 costs 74 Runs.

## Tasks & Acceptance

**Execution:**
- `_bmad-output/planning-artifacts/mvp/addendum.md` -- add a dated "Claude — verified against the image, 2026-09-08" block to §B -- the brief's own Record requirement.
- `host/README.md` -- add the verified two-key commands, the upstream-provider gap, and the Langfuse `events_only` finding -- the brief's own Record requirement.

**Acceptance Criteria:**
- Given the stack against the host services, when the readiness Run for `claude` completes, then `GET /harnesses` shows `claude · enabled` — **NOT MET**; see Auto Run Result.
- Given the cap probe, when it stops, then the Run parks `budget` and the marking field is recorded — **field recorded, probe not runnable**; see Auto Run Result.
- Given `addendum.md` §B and `host/README.md`, when read, then they contain the verified Claude block and the key commands, dated — **MET**.
- Given any fix made to 5.1–5.8, when `make lint test` runs, then it is covered by a unit test and green — **vacuous**: no fix was committed, and every gate is at the result it had before this story.

## Design Notes

**The cap-exit field, closed by reading the artefact rather than by guessing.** A `--max-budget-usd` stop needs real spend, and no model call can complete on this host, so the probe the brief specifies could not run. The next-best evidence is the CLI's own shipped result schema, which is not a guess: at 2.1.258 the error result variant declares `subtype: ["error_during_execution", "error_max_turns", "error_max_budget_usd", "error_max_structured_output_retries"]`, and the emitting branch reads `terminal_reason === "budget_exhausted"` → `subtype: "error_max_budget_usd"`. The literal `"max_budget"` occurs **zero** times in the whole bundle, so 5.7's placeholder is not merely unconfirmed, it is disproved. `CAP_EXIT_FIELD` should become `"subtype"` and `CAP_EXIT_VALUE` `"error_max_budget_usd"`.

**The two held-back patches, recorded verbatim so applying them is mechanical.**

`scripts/readiness_fixture.sh` — replace line 30:

```bash
# -b main, not the default: `git init --bare` would leave HEAD a symbolic ref to a
# `master` this fixture never creates, and `git ls-remote -- <url> HEAD` — which is
# exactly what the clone check's first line runs — answers nothing for an unborn HEAD.
git init --bare -q -b main "${ORIGIN}"
```

Its regression test (`backend-api/tests/unit/test_readiness_fixture_script.py`, written and run
green, 4 passed; verified non-vacuous by reverting the patch and watching it fail) asserts two
things: textually, that the `git init --bare` line carries `-b main`; and behaviourally, against
real `git` in `tmp_path`, that `git ls-remote -- file://<origin> HEAD` answers zero lines when
the bare origin's HEAD is on a `master` nothing creates and exactly one line when it is on
`main`. Both halves are needed — the first is the guard, the second is the reason.

**Why nothing was committed beyond the two records.** See the last paragraph of §B: the fixture
patch alone moves `make e2e` from exit 0 / 145 passed to exit 2 / 5 failed, because it makes an
`epic@1` path reachable that then hits two Epic 4/6 defects. Hard rule 6 makes a landed gate's
green a precondition, and a red `make e2e` on this branch would block every subsequent story.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: exit 0
- `make openapi` -- expected: exit 0, no drift
- `make e2e` -- expected: exit 0, unchanged from before this story
- `make e2e-ui` -- expected: exit 0
- `make durability` -- expected: exit 0

**Manual checks:**
- `addendum.md` §B carries a dated 2026-09-08 "Claude — verified against the image" block.
- `host/README.md` carries the four dated key-probe commands and the two host-gap sections.

## Auto Run Result

Status: blocked

Blocking condition: the `claude` readiness Run cannot reach `enabled`. Two host-side reasons,
each sufficient on its own, and three orchestrator defects reached on the way.

**The host cannot serve a model call.** `host/.env` carries `ANTHROPIC_API_KEY=not-set`,
`OPENAI_API_KEY=not-set` and `OMLX_API_KEY=not-set`, and `OMLX_BASE_URL` resolves to the
orchestrator's own API port rather than a running oMLX — confirmed by reading the LiteLLM
container's environment directly. Every model on `model_list` therefore fails at the first
completion: `claude-sonnet-4-6` → `401 invalid x-api-key`, `gpt-5.4` → `401 Incorrect API key
provided: not-set`, `local-coder`/`local-general` → `404` from the orchestrator's own RFC 9457
handler. `host/.env`'s own comment says as much: "Real inference needs at least one of these to
be a real key; the proxy starts, answers /health and lists /v1/models without them, which is
all the harness `doctor` check requires." The five values provisioned for this story are all
real and all verified — they authenticate *to* the Gateway; what is missing is the Gateway's
own credential to a provider. Without a completable model call there is no agent attempt, no
spend row, and no cap stop, so PRD §8 items 1, 2 and 4 cannot be closed.

**Langfuse runs in v4 `events_only` mode.** `GET /api/public/observations` and
`GET /api/public/traces` both answer `404 — This endpoint is not available on deployments
running in Langfuse v4 events_only mode` on this 4.27.0 instance, while `/api/public/health`
and `/api/public/projects` answer `200`. `LangfuseTracer.attempt_observed` is exactly
`api.observations.get_many(trace_id=…)` and answers `False` on any query failure rather than
raising (SM-3, deliberate). So readiness line 3, `trace observed`, can never be `ok` against
this deployment, whatever the harness emits — ingestion is unaffected, only reads are gone.
AD-10 makes the readiness verdict depend on a read API this mode does not serve.

**The run itself.** Run `01a08187-cfb1-709d-8ebe-04999822573e`, `epic@1`, Project `readiness`,
budget `5.000000`, `plan_ref ecd7fa9dd0b73672e15f1044b45b004987dc48ba`, trace_url rendered as
`http://host.docker.internal:3000/project/ai-orchestrator/traces/3de21469dfc419226ed33077de3bef5e`.
Final status **`needs_you`**, alert `no runnable step: plan is running`, `park_kind: internal`.
Nine rows planned exactly as the SPEC's success signal predicts — `plan · checkout · baseline ·
stories[0].{sync,build,verify,commit-guard} · push · link` — and **only row 1 ever executed**.
`GET /harnesses` for `claude` afterwards, verbatim:

```json
{"name": "claude", "enabled": false, "last_readiness_at": null, "failing_check": null,
 "version_pin": "2.1.258", "last_readiness_run_id": null, "lines": []}
```

`lines` is empty and `last_readiness_at` is null because `evaluate` fires from
`WalkerDeps.on_terminal`, and `needs_you` is not a terminal status — so a Run parked before it
ever dispatched leaves the harness row untouched. That is consistent with 5.8's design, and it
means the readiness Run was **not observed reaching `enabled`** in any sense.

**PRD §8, item by item.**

1. **Allowlist under `--permission-mode dontAsk` — NOT closed.** No agent row executed, so the
   allowlist was never exercised by a real dispatch. What is confirmed: `--permission-mode`
   exists at 2.1.258 with `dontAsk` among its choices, and `.env.example`'s default list is
   unchanged.
2. **Trace continuity via `attempt_observed` — NOT closed, and not closable here.** No attempt
   existed to observe, and the host's `events_only` mode makes the query itself unavailable.
3. **Skill discovery from the worktree — CLOSED, positively.** The image carries 49 stubs under
   `~/.claude/skills/` including `bmad-build-auto/SKILL.md`; `scripts/harness/claude.sh doctor`
   reports `bmad-build-auto discoverable in /home/agent/.claude/skills` and
   `gateway reachable at http://host.docker.internal:4000`. In a clone of the readiness origin
   the stub's own command answered
   `read and follow /tmp/fx/_bmad/render/bmad-build-auto/fx-3967cfab482c/58c3c8dd2c0f25687f02/workflow.md`.
   The worktree resolves as project root. **`SKILL_STUBS_INTO_WORKTREE` was not needed and was
   not built**; no new setting was added.
4. **Spend and session headers coexisting — NOT closed.** No attempt produced a spend row.
   `_query` was left exactly as 5.3 wrote it.
5. **Two keys — CLOSED, positively, and confirmed first-hand rather than taken on report.**
   `LITELLM_API_KEY` → `200` on `/v1/models`, **`403`** on `/spend/logs/v2` with the proxy's own
   `Virtual key is not allowed to call this route. Only allowed to call routes:
   ['llm_api_routes']. Tried to call route: /spend/logs/v2`. `LITELLM_SPEND_KEY` → `200` on
   `/spend/logs/v2` with real rows. Commands recorded in `host/README.md`.

**The cap probe.** `--max-budget-usd 0.01` was accepted as an argument and the dispatch reached
the Gateway, but the API call itself failed (no upstream credential), so no cap stop occurred
and none could. The field was instead read out of the shipped 2.1.258 bundle's own result
schema: **`subtype` = `error_max_budget_usd`**, emitted when `terminal_reason ===
"budget_exhausted"`. `"max_budget"` appears zero times in the bundle. `CAP_EXIT_FIELD` and
`CAP_EXIT_VALUE` are therefore **unchanged and still wrong** — see the anchor conflict below.

**Two ANCHOR CONFLICTS, reported and not worked around.**

1. `backend-api/tests/unit/application/steps/test_agent_tail_budget.py:88` scripts the cap exit
   as the literal `raw_result={"stop_reason": "max_budget"}` and asserts `park.kind == "budget"`
   with `budget_park is None`. Correcting the constants makes that raw_result stop matching, the
   short-circuit stops firing, `route` decides on the harness exit instead, and both assertions
   fail. The file is a pre-existing test, so hard rule 1 forbids editing it. Hard rule 1's second
   exception does not apply: it requires the *test* to name the later story that replaces the
   placeholder, and this test names only "5.7" and "AC4" — the naming of 5.11 lives in
   `5-7-budget-halt-in-the-loop.md`'s Design Notes, not in the test.
2. `backend-api/tests/unit/test_claude_adapter.py:459` asserts
   `cmd[cmd.index("--max-budget-usd") + 1] == "0.00"` for a spent budget. Observed at 2.1.258:
   `option '--max-budget-usd <amount>' argument '0.00' is invalid. --max-budget-usd must be a
   positive number greater than 0` — the CLI exits 1 with no JSON, so an exhausted-budget
   dispatch would fail as a harness exit rather than as the budget park FR-17 intends. `0.01`
   and `0.001` are accepted; `0` is not. Correcting `NO_BUDGET` edits that frozen assertion.
   The test's docstring names 5.7, which has already landed, so the second exception does not
   reach 5.11 either.

**Gates, each run in the foreground with its exit code observed directly.**

- `make lint` — **exit 0**. ruff check + format, mypy `--strict`, all four import-linter
  contracts KEPT, env contract 32 settings / 38 `.env.example` variables agree,
  `check_test_pairs` 179 backend + 73 web-client, `gen:api --check` no drift, web-client
  astro-check/eslint/prettier/tsc clean.
- `make test` — **exit 0**. 4937 backend passed, 1 skipped; `domain/` + `application/` 100%
  branch under `--fail-under=100`; web-client 1014 passed, 75 files.
- `make openapi` — **exit 0**, idempotent: no drift in `contracts/openapi.json` or
  `web-client/src/api/schema.d.ts` (this story exposes nothing new over the wire).
- `make e2e` — **exit 0**, 145 passed, 11 deselected, 36 subtests passed. Also run **with** the
  held-back fixture patch applied, on the same commit: **exit 2, 5 failed / 140 passed** — the
  measurement that decided the patch could not land alone.
- `make e2e-ui` — **exit 0**.
- `make durability` — **exit 0**.

**Anchor check** (the literal command from the dispatch instructions) flags exactly the six
files earlier stories on this branch already flagged — `tests/unit/fakes/{clock,git,workspace}.py`,
`tests/e2e/test_harnesses.py`, `tests/unit/test_harnesses_router.py` — none of them touched
here. This story committed **no** test file and **no** source file.

**Files changed:** 3 modified (`_bmad-output/planning-artifacts/mvp/addendum.md`,
`host/README.md`, and this spec, which is new).

**What this run actually cost.** **$0.00.** No model call completed: every attempt was refused
upstream before any tokens were billed, which `/spend/logs/v2` confirms — the Run's own
`spend_usd` stayed `0.000000` and no row was attributable to it.

**Operator decisions needed** — this story cannot proceed without at least the first:

1. **A working upstream provider credential on the host LiteLLM** (a real `ANTHROPIC_API_KEY`,
   or `OPENAI_API_KEY`, or oMLX up on a port the orchestrator does not already hold), and a
   Langfuse not in `events_only` mode — or a decision to source `attempt_observed` differently.
2. **Whether to land the fixture patch together with the Epic 4 `plan_stale` fix** (findings 1
   and 2), which is the only combination that both makes the readiness path work and keeps
   `make e2e` green.
3. **Authorisation for the two anchor edits**, on the same terms 5.8 was granted: each an exact
   revision of one assertion, each accompanied by new coverage that strictly exceeds it.
4. **How the readiness Run should name its model** (finding 5) — a `READINESS_MODEL` setting
   threaded exactly like `READINESS_BUDGET_USD` is the obvious shape, but it needs a default,
   and choosing one is a configuration decision this story would not make on its own.

**Follow-up review recommended:** false. Nothing was implemented to review; the deliverable is
the record, and every claim in it is a first-hand observation with the command that produced it.
