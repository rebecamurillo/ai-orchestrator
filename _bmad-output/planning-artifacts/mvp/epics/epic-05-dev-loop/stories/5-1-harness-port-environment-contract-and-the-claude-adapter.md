---
title: 'Harness port, environment contract, and the Claude adapter'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      A Project variable named ANTHROPIC_BASE_URL or ANTHROPIC_API_KEY can re-point the
      harness off the Gateway, defeating the budget cap, the spend tags and AD-11 attribution.
    evidence: |-
      env_for strips GITHUB_TOKEN, LITELLM_SPEND_KEY, DATABASE_URL, ORCHESTRATOR_* and
      OTEL_LOG_*, and the alias builder wins for ANTHROPIC_AUTH_TOKEN and
      ANTHROPIC_CUSTOM_HEADERS. ANTHROPIC_BASE_URL is set only in ~/.claude/settings.json,
      which an environment variable overrides. Extending the refusal list to a new prefix is
      an invariant neither the brief nor AD-5 states, so it is an operator decision.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/env.py:75
    severity: medium
  - summary: >-
      usage.cache_creation_input_tokens and cache_read_input_tokens are not counted into
      tokens_in, so a cached attempt's provisional token figure under-reports.
    evidence: |-
      The brief pins usage to total_cost_usd, usage.input_tokens and usage.output_tokens, so
      the adapter follows it. On a bmad-build-auto run the cache fields dominate. AD-11 has
      Gateway.spend_for_attempt replace the provisional figures, so 5.3 is where this is
      decided.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:344
    severity: low
  - summary: >-
      Nothing asserts the backend image sets HOME to AGENT_HOME, which is what makes
      ~/.claude/settings.json reachable by a harness process.
    evidence: |-
      RealProcessRunner._child_env takes HOME from this process's environment, not from the
      mapping env_for built, so the contract's HOME=AGENT_HOME holds only because
      backend-api/Dockerfile sets HOME=${AGENT_HOME}. tests/unit/test_dockerfiles.py checks
      the build args and not that line, and it is a frozen file.
    location: >-
      backend-api/Dockerfile:35
    severity: medium
  - summary: >-
      The comma-joined --allowedTools word carries entries with embedded spaces
      (Bash(uv run *)) and nothing exercises the real CLI's parsing of it.
    evidence: |-
      The adapter test asserts ",".join(settings.claude_allowed_tools), which recomputes the
      implementation's own expression. A mis-split would only surface in 5.11's readiness run
      against the real binary.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:199
    severity: medium
  - summary: >-
      bash_array's regex stops at the first ")", so an Epic 7 alias array containing one is
      silently truncated.
    evidence: |-
      The pattern is ^{name}=\((.*?)\) with DOTALL. Today no harness array holds a ")", but
      CLAUDE_ALLOWED_TOOLS in .env.example shows the style is in use nearby.
    location: >-
      backend-api/tests/unit/test_harness_env_contract.py:58
    severity: low
  - summary: >-
      The registry key "local" and the script name "opencode" diverge, so ORCH_HARNESS will
      not name the script that configured the harness.
    evidence: |-
      main.HARNESS_VERSION_SETTINGS maps local -> opencode_version while
      scripts/harness/opencode.sh sets HARNESS_NAME=opencode.
      test_harness_env_contract.py hardcodes ALIAS_SCRIPT = claude.sh, so Epic 7 needs a
      registry-key to script-name map. Pre-existing, surfaced by this story.
    location: >-
      backend-api/src/orchestrator/main.py:162
    severity: low
  - summary: >-
      result_object reads the whole attempt log into memory and rescans from every "{".
      Agent logs are unbounded.
    evidence: |-
      json_objects offers every "{" to raw_decode over the full text. A long dev-loop
      attempt can write a very large interleaved log; only the tail can hold the result
      envelope.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:277
    severity: low
baseline_revision: '48872a6f44ba63e4415d7865c9eda28f8bc8167c'
---

<intent-contract>

## Intent

**Problem:** Nothing in the codebase can start a coding agent. There is no `Harness` port, no
statement in Python of the environment `scripts/harness/_common.sh` declares normative, and no
Claude Code adapter — so Epic 5's agent executor has nothing to dispatch through and no way to
prove that a harness process receives exactly the contract and never `GITHUB_TOKEN` or
`LITELLM_SPEND_KEY`.

**Approach:** Add `domain/ports/harness.py` (the `Harness` protocol plus `HarnessResult`),
`infrastructure/harness/env.py` (`env_for`, shared by every adapter, whose key set is the
scripts' two declared lists plus the Project's variables plus the four base names),
`infrastructure/harness/claude/adapter.py` (`claude -p` through the `ProcessRunner` port), a
`FakeHarness` for the port, and a registry builder in `main.py`. A unit test parses the bash
arrays out of the two scripts and asserts the adapter's key set equals them, so the Python and
the shell cannot drift.

## Boundaries & Constraints

**Always:**
- AD-10: the adapter returns `HarnessResult` and nothing interpreted from model output beyond
  `usage`, `session_id` and the raw JSON result object; it writes nothing under `AGENT_HOME`.
- AD-5: `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL` and every `ORCHESTRATOR_*` name are
  absent from any harness environment. A Project variable never overrides a contract name.
- AD-2: `domain/ports/harness.py` imports nothing but the standard library and pydantic-free
  dataclasses; `infrastructure/harness/claude/adapter.py` imports the `ProcessRunner` port,
  `Settings` and `json`, and nothing from `application/`.
- AD-14: every harness process goes through the `ProcessRunner` port — its own process group,
  its own deadline. The adapter never touches `subprocess`.
- `scripts/harness/_common.sh` is the normative contract list; the Python constant mirrors it
  and a test proves the mirror.
- Every new source module is imported by a unit-test module (AD-18, `check_test_pairs`), is at
  most 400 lines, and carries no `pragma: no cover` under `domain/`.

**Block If:**
- Landing this story would require editing `SPEC.md`, `stories.yaml`, an `AGENTS.md`, or any
  existing test file.
- A documented Claude Code flag in the brief's invocation does not exist at the pinned
  `CLAUDE_CODE_VERSION` and no equivalent is documented.

**Never:**
- No agent executor, no `compose_prompt`, no `StepPorts` field, no walker wiring (5.4).
- No `Tracer`, no real `TRACEPARENT` value — the contract key exists and is the empty string
  until 5.2.
- No budget-cap interpretation, no spend, no routing (5.5, 5.7): the adapter exposes
  `raw_result` and stops there.
- No `codex` or `local` adapters (Epic 7).
- No new `Settings` field and no `.env.example` line: the pins and the allowlist are present.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Contract env for `claude` | attempt on a Project with two variables, `log_content` false | keys are exactly contract ∪ `{ANTHROPIC_AUTH_TOKEN, ANTHROPIC_CUSTOM_HEADERS}` ∪ the two Project names ∪ `{HOME, PATH, LANG, TERM}`; `ANTHROPIC_AUTH_TOKEN == LITELLM_API_KEY`; five header lines carry the right ids; `TERM=dumb`, `HOME=$AGENT_HOME` | No error expected |
| Content logging on | same, `log_content` true | `ORCH_LOG_CONTENT=1` and both `OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_TOOL_CONTENT=1` present | No error expected |
| Credentials by absence | any attempt | `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL`, any `ORCHESTRATOR_*` absent | No error expected |
| Project variable shadowing a contract name | project env carries `ORCH_RUN_ID` | the contract value wins | No error expected |
| Script mirror | `_common.sh` gains a name | the contract test fails naming it | Test failure is the handling |
| Dispatch with model and budget 12.5 | `run(...)` on the fake runner | argv is exactly the documented invocation with `--max-budget-usd 12.50`, `--model`, prompt last; `cwd` is the worktree; result carries the pre-assigned `session_id`, exit code, log path, parsed usage | No error expected |
| Dispatch without a model | `model=None` | argv omits `--model` entirely | No error expected |
| Timeout | runner reports `timed_out` | `HarnessResult.timed_out` is true, `pgid` recorded, the group was killed by the runner | No error expected |
| Non-JSON output | log holds plain text | `usage is None`, `raw_result is None`, exit code still reported | No exception |
| Trailing JSON among noise | log holds text then a JSON result object | the last JSON object is parsed; `usage` filled from `total_cost_usd` and `usage.input_tokens`/`output_tokens` | Missing fields yield `usage = None` |
| Resume | `resume(...)` | argv uses `--resume {session_id}`, the message last, no `--max-budget-usd`, no `--session-id` | No error expected |
| Resume command | `resume_command(cwd, id)` | `cd /work/p/r/wt/feat-x && claude --resume {id}` | No error expected |

</intent-contract>

## Code Map

- `scripts/harness/_common.sh:26-27` -- normative `HARNESS_ENV_CONTRACT` bash array (15 names,
  including `LANGFUSE_ENVIRONMENT`, which AD-10's prose omits — the script wins, AD-10 says so).
- `scripts/harness/claude.sh:8` -- `HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=LITELLM_API_KEY
  ANTHROPIC_CUSTOM_HEADERS=derived)`; lines 44-50 document the per-attempt env and the invocation.
- `backend-api/src/orchestrator/domain/ports/process.py` -- `ProcessRunner`, `Handle`, `Outcome`;
  the shape the adapter drives (`start` → `wait`, `Outcome.timed_out`).
- `backend-api/src/orchestrator/infrastructure/process/runner.py:138-147` -- `_child_env` re-adds
  `PATH`/`HOME`/`LANG`/`TERM`/`GIT_TERMINAL_PROMPT` on top of the caller's mapping. In the image
  `HOME == AGENT_HOME` (`backend-api/Dockerfile:33-35`), so the two agree.
- `backend-api/src/orchestrator/infrastructure/settings.py:71-94` -- `litellm_*`, `langfuse_*`,
  `claude_allowed_tools` (comma-separated → `list[str]`), `agent_home`, `claude_code_version`.
  Nothing new is needed.
- `backend-api/src/orchestrator/domain/entities/attempt.py` -- `id`, `run_id`, `harness`, `model`,
  `session_id`, `pgid`, `tokens_in/out`, `cost_usd`, `cost_provisional`. Carries no story id.
- `backend-api/src/orchestrator/domain/entities/run.py` -- `id`, `budget_usd`, `spend_usd`.
  Carries no project slug; `RunEnvironment.project_slug` is where the walker keeps it
  (`application/steps/context.py:86`).
- `backend-api/src/orchestrator/domain/entities/harness.py` -- the stored `Harness` **entity**;
  the new port shares its name, so `main.py` must alias one of the two on import.
- `backend-api/src/orchestrator/main.py:159-184` -- `HARNESS_VERSION_SETTINGS` and
  `seed_harness_table`; the composition root the registry belongs beside.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py:66-90` -- `walker_deps` builds
  `StepPorts` with `RealProcessRunner()`. Where 5.4 will thread the registry through.
- `backend-api/tests/unit/fakes/process.py` -- `FakeProcessRunner`: scripted `Outcome` per exact
  command string, `calls` log with `cmd`/`cwd`/`env`/`timeout_min`/`log_path`. Reuse; do not
  write another (AD-18). It writes nothing to `log_path`, so a test that wants parsed usage
  writes the sample JSON to that file itself.
- `backend-api/tests/unit/test_harness_scripts.py` -- **frozen**; already asserts the scripts'
  shape and that the contract carries `LITELLM_API_KEY` and neither forbidden name. The new
  contract test is a new file and must not touch this one.
- `backend-api/tests/unit/conftest.py` -- `REPO_ROOT`, `ENV_EXAMPLE`, `parse_env_example`, and the
  `env` fixture that puts the whole `.env.example` contract in `os.environ` so `Settings()` builds.
- `scripts/check_test_pairs.py` -- `__init__.py` and the top-level `main.py` are exempt; every
  other new module needs a unit test importing it.
- `backend-api/tests/unit/test_source_limits.py`, `test_coverage_gates.py`, `test_layering.py` --
  frozen meta-gates: 400 lines, no `print`, no `pragma: no cover` in `domain/`, import-linter.

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_harness_port.py` -- new: assert the port's shape and
  `HarnessResult`/`HarnessUsage`/`HarnessCapabilities` construction and defaults; assert
  `FakeHarness` satisfies `Harness` -- TDD first (AD-18).
- `backend-api/tests/unit/test_harness_env_contract.py` -- new: parse `HARNESS_ENV_CONTRACT` from
  `scripts/harness/_common.sh` and `HARNESS_ENV_ALIASES` from `scripts/harness/claude.sh`; assert
  `set(env_for(...)) == contract ∪ alias names ∪ project names ∪ {HOME, PATH, LANG, TERM}`, assert
  the Python mirror constant equals the parsed contract, and prove the gate fires by re-running
  the same assertion against a copy of `_common.sh` with a name appended -- the AD-10 test the
  brief names, reused by Epic 7.
- `backend-api/tests/unit/test_harness_env.py` -- new: values, not just keys — tags, JSON tags,
  header lines, `ORCH_LOG_CONTENT`, the `OTEL_LOG_*` pair, forbidden names absent, a Project
  variable not overriding a contract name.
- `backend-api/tests/unit/test_claude_adapter.py` -- new: `_argv` for run and resume, `cwd`,
  timeout, usage parsing (JSON, trailing JSON, non-JSON), `timed_out`, `pgid`, `resume_command`,
  prompt sidecar file.
- `backend-api/tests/unit/test_main_harness_registry.py` -- new: `build_harnesses` returns
  `{"claude": ClaudeHarness}` and each value satisfies the port.
- `backend-api/tests/unit/fakes/harness.py` -- new `FakeHarness`: scripted `HarnessResult` per
  call, records `prompt`, `env`, `cwd`, `model`, `session_id`, `budget_usd_remaining` -- the one
  fake for the port (AD-18); 5.4 and 5.5 reuse it.
- `backend-api/src/orchestrator/domain/ports/harness.py` -- new: `HarnessUsage`,
  `HarnessCapabilities`, `HarnessResult`, `Harness` protocol -- AD-10's port, in `domain/`.
- `backend-api/src/orchestrator/infrastructure/harness/__init__.py` -- new package marker
  re-exporting `env_for` and `ClaudeHarness`.
- `backend-api/src/orchestrator/infrastructure/harness/env.py` -- new: `HARNESS_ENV_CONTRACT`
  mirror, `env_for`, tag rendering -- shared by every adapter, Epic 7 included.
- `backend-api/src/orchestrator/infrastructure/harness/claude/__init__.py` -- new package marker.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- new `ClaudeHarness`:
  `_argv`, `claude_aliases`, `run`, `resume`, `resume_command`.
- `backend-api/src/orchestrator/main.py` -- add `build_harnesses(settings, runner)` -- the AD-10
  registry the executor looks up by `with_resolved.harness`.
- `_bmad-output/planning-artifacts/mvp/addendum.md` -- §B: record the flag re-verification result
  for Claude -- the brief requires the record whether or not anything changed.

**Acceptance Criteria:**
- Given the two script files, when the contract test runs, then it passes; and given a copy of
  `_common.sh` with an extra name in the array, when the same assertion runs against it, then it
  fails naming that name.
- Given a `ClaudeHarness` built on `FakeProcessRunner`, when `run` is called with a model and
  `budget_usd_remaining = Decimal("12.5")`, then the recorded `cmd` is exactly
  `["claude", "-p", "--session-id", <uuid>, "--permission-mode", "dontAsk", "--allowedTools",
  <joined allowlist>, "--disallowedTools", "mcp__*", "--output-format", "json",
  "--max-budget-usd", "12.50", "--model", <model>, <prompt>]`, `cwd` is the worktree, and the
  returned `HarnessResult` carries the pre-assigned `session_id`, the exit code, the log path and
  the usage parsed from a sample JSON result written to that log.
- Given the runner reports `Outcome(exit_code=None, timed_out=True)`, when `run` returns, then
  `HarnessResult.timed_out` is true and `pgid` is the handle's group.
- Given `resume_command("/work/p/r/wt/feat-x", "abc")`, when called, then it returns
  `cd /work/p/r/wt/feat-x && claude --resume abc`.
- Given `make lint`, when it runs, then `check_test_pairs`, `ruff`, `mypy --strict`,
  `lint-imports` and the env-contract check all pass with no change to any frozen file.
- Given `make test`, when it runs, then every unit test passes and `domain/` + `application/`
  stay at 100 % branch coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-07 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 1, medium 4, low 5)
- defer: 7: (high 0, medium 3, low 4)
- reject: 16: (high 0, medium 4, low 12)
- addressed_findings:
  - `[high]` `[patch]` `usage_from` raised `InvalidOperation`/`ValueError` on a present-but-non-numeric `total_cost_usd` or token count, against its own "never an exception" contract — an otherwise complete attempt would have become an `internal:` park. Split into `_as_decimal`/`_as_int` guards (rejecting `bool`, which is an `int`), with two new parametrized cases.
  - `[medium]` `[patch]` A JSON object printed *after* the result — stdout and stderr share the log file — displaced the result and dropped `usage`. `result_object` now prefers the last object carrying `"type": "result"` and keeps the brief's "last JSON object" as the fallback; new test writes a trailing JSON line.
  - `[medium]` `[patch]` `env_for` merged the Project's variables after the base names, so a Project variable named `HOME`/`PATH`/`LANG`/`TERM` won; and a Project variable named `OTEL_LOG_USER_PROMPTS` turned prompt logging on while `ORCH_LOG_CONTENT` said `0` (AD-5 makes the content-logging switch the instance's). Merge order reversed and `OTEL_LOG_` added to `FORBIDDEN_PREFIXES`; six new tests.
  - `[medium]` `[patch]` `--max-budget-usd` used round-half-even, so `12.499` was capped at `12.50` — more than the Run had left (FR-17). `render_budget` now quantizes `ROUND_DOWN` and passes `0.00` rather than a negative amount.
  - `[medium]` `[patch]` `_execute` started the process and waited with no guard: a `wait` that raised left a coding agent running with its `pgid` known nowhere (AD-14's orphan). The wait is now wrapped so any `BaseException` kills the group and re-raises; tested on both `run` and `resume`.
  - `[low]` `[patch]` Log and prompt file I/O passed no encoding, letting the container locale decide what was parsed out of an attempt's record. `encoding="utf-8"` throughout.
  - `[low]` `[patch]` `ORCH_LANGFUSE_TAGS` was rebuilt by re-splitting the joined tag string, so a value containing a comma would silently add an item. `tag_list` is now the single source and the joined string is derived from it.
  - `[low]` `[patch]` Two docstrings overclaimed: `env.py` said the `ProcessRunner` "re-adds exactly these" four names (it adds a fifth and takes them from its own environment), and the port said capabilities gate the environment (`TRACEPARENT` is a contract name for every harness). Both reworded to what is true.
  - `[low]` `[patch]` The adapter keeps `--disallowedTools "mcp__*"` on `resume`, which the brief's spelled invocation does not list. Recorded as a deviation in `addendum.md` §B with its reason, as the brief requires.
  - `[low]` `[patch]` `test_a_timeout_is_reported_with_the_group_the_runner_killed` cannot assert the kill — AD-14 puts it inside `ProcessRunner.wait` and the shared fake records only the wait. A comment now says so and names `tests/unit/test_process_runner.py` as where the escalation is proved, so the AC's parenthetical is documented rather than implied.

## Design Notes

**`env_for`'s signature.** The brief writes `env_for(attempt, run, project_env, log_content)`, but
`ORCH_STORY_ID` and `ORCH_PROJECT` are on neither `Attempt` nor `Run` — the story id is on
`StepRun.story_id` and the slug is on `RunEnvironment.project_slug`. The four brief-named
parameters are kept and the missing facts are added as keyword-only arguments rather than
invented:

```python
def env_for(
    attempt: Attempt, *, run: Run, project_slug: str, project_env: Mapping[str, str],
    log_content: bool, settings: Settings, story_id: str | None = None,
    traceparent: str = "", aliases: AliasBuilder | None = None,
) -> dict[str, str]:
```

`aliases` is a callable taking the contract environment and returning the harness-native names
(`claude_aliases` lives in the claude package). That is what keeps `env.py` generic for Epic 7
while `ANTHROPIC_CUSTOM_HEADERS`, which is *derived* from contract values, stays with the harness
that defines it. `TRACEPARENT` defaults to `""` until 5.2 supplies one; the key always exists,
because the contract list is exact.

**A missing story id renders as `story:`.** `StepRun.story_id` is `str | None` (an `agent` row
outside a story frame has none). `ORCH_TAGS` keeps the five positions and leaves the value empty
rather than dropping the tag, so the tag string always parses the same way. `[ASSUMPTION]`

**`--disallowedTools` on resume.** The brief spells resume as `claude -p --resume {id}
--permission-mode dontAsk --allowedTools … --output-format json "{message}"`. The `…` is read as
the allowlist pair, so resume carries `--disallowedTools "mcp__*"` too: a resumed attempt runs in
the same container with the same tools, and dropping the MCP exclusion there would make the
sandbox depend on which call started the turn.

**Usage parsing is tolerant and terminal.** The adapter reads `log_path` after `wait`, scans for
the last balanced JSON object, and fills `HarnessUsage` from `total_cost_usd`,
`usage.input_tokens`, `usage.output_tokens`. Anything else — no JSON, a JSON value that is not an
object, missing fields — yields `usage = None`. `raw_result` carries the parsed object unchanged
so 5.7 can decide the budget-cap question from a field this story does not name (AD-10).

**Seam left open for 5.4 (`pgid` before the await).** `Harness.run` starts and waits inside one
call, so `HarnessResult.pgid` is only available after the process has ended, while AD-14 and
`Attempt`'s own docstring say `attempt.pgid` is recorded *before* the harness is awaited. The port
is implemented exactly as the brief defines it; closing that gap (a start hook, or a two-call
port) is 5.4's decision and is recorded here rather than made here.

**Registry placement.** `build_harnesses(settings, runner)` lives in `main.py` as the brief says.
`StepPorts` is built in `infrastructure/dbos/startup.py::walker_deps`, which AD-2 forbids from
importing `main`; `main()` already calls `build_engine(...)`, so 5.4 threads the registry through
that call rather than importing it upward.

**Flag re-verification.** `claude --help` at 2.1.236 confirms `-p`, `--session-id <uuid>`,
`--permission-mode dontAsk`, `--allowedTools`, `--disallowedTools`, `--output-format json`,
`--max-budget-usd <amount>` (print-only), `--model` and `--resume`. No deviation from the brief's
invocation; the pinned version is 2.1.258 and only the older CLI was reachable, which is what §B
records.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; `check_test_pairs` reports every module paired.
- `make test` -- expected: exit 0; the 100 % branch report over `domain/` + `application/` passes.
- `git status --porcelain` -- expected: only the files this spec's Execution list names.

## Auto Run Result

Status: done

**What was implemented.** The `Harness` port and its result types, the shared harness
environment builder, the Claude Code adapter, the one fake for the port, and the registry in
the composition root. A harness process now receives exactly `HARNESS_ENV_CONTRACT` (the
15 names `scripts/harness/_common.sh` declares) plus the two `HARNESS_ENV_ALIASES` from
`scripts/harness/claude.sh`, plus the Project's decrypted variables, plus `HOME`/`PATH`/
`LANG`/`TERM` — and a unit test parses both bash arrays and asserts that equality, so the
Python and the shell cannot drift. Nothing dispatches through it yet; 5.4 does.

**Files changed (12 added, 2 modified):**
- `backend-api/src/orchestrator/domain/ports/harness.py` — added: `HarnessUsage`,
  `HarnessCapabilities`, `HarnessResult` (with `raw_result`), the `Harness` protocol.
- `backend-api/src/orchestrator/infrastructure/harness/__init__.py` — added: package
  re-export of `env_for` and `ClaudeHarness`.
- `backend-api/src/orchestrator/infrastructure/harness/env.py` — added: the contract mirror,
  `is_forbidden`, `tag_list`, `env_for`.
- `backend-api/src/orchestrator/infrastructure/harness/claude/__init__.py` — added: package
  marker.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` — added:
  `claude_aliases`, `ClaudeHarness` (`_argv`, `run`, `resume`, `resume_command`),
  `render_budget`, `json_objects`, `result_object`, `usage_from`.
- `backend-api/src/orchestrator/main.py` — modified: `build_harnesses(settings, runner)`.
- `_bmad-output/planning-artifacts/mvp/addendum.md` — modified: §B gained a dated
  "Claude — flags re-verified 2026-09-07" block and the one recorded deviation.
- `backend-api/tests/unit/fakes/harness.py` — added: `FakeHarness`, the one fake for the port.
- `backend-api/tests/unit/test_harness_port.py`, `test_harness_env_contract.py`,
  `test_harness_env.py`, `test_claude_adapter.py`, `test_main_harness_registry.py` — added:
  83 tests over the five modules.

**Review findings:** 10 patched (1 high, 4 medium, 5 low), 7 deferred (frontmatter
`deferred`), 16 rejected. No `intent_gap` and no `bad_spec`, so no repair loopback ran.

**Follow-up review recommended:** true. One patched finding was `high` severity
(`usage_from` raising instead of returning `None`), which sets the flag on its own; the
medium/low score was `3 × 4 + 1 × 5 = 17`, also over the threshold.

**Verification performed:**
- `make lint` — exit 0. ruff check, ruff format --check, mypy --strict over `domain/` +
  `application/`, all four import-linter contracts KEPT, env-contract check (30 settings
  fields / 36 `.env.example` variables), `check_test_pairs` 154/154 paired, `gen:api --check`
  no drift, web-client lint.
- `make test` — exit 0. 4195 backend unit tests passed, 1 skipped; `domain/` + `application/`
  at 100 % branch under `--fail-under=100`; web-client 973 passed.
- The five new test modules alone: 83 passed.
- Matrix audit: all 12 I/O matrix rows are covered by named tests that ran and passed.
- Claude Code flags re-verified against the real CLI (`claude --help`).
- No frozen file was modified: the only two tracked files touched are `main.py` and
  `addendum.md`, both additive.

**Residual risks:**
- The `pgid`-before-await seam is open by design. `run` starts and waits in one call, so
  `HarnessResult.pgid` only exists after the process ends, while AD-14 wants `attempt.pgid`
  stored before it is awaited. The port is exactly what the brief defines; closing the gap
  (a start hook, or a two-call port) is 5.4's decision.
- The budget-cap JSON field is still unnamed. `raw_result` carries the object verbatim; 5.11
  observes the field and records it in §B, 5.7 reads it.
- The flag re-verification ran against 2.1.236, the CLI reachable on this host, while
  `CLAUDE_CODE_VERSION` pins 2.1.258. Disclosed in §B; 5.11 verifies against the image.
- `main.py` is at 394 lines against the 400-line cap. 5.4 threading the registry through
  `build_engine(...)` will need room there.
