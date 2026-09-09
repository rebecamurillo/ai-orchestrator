---
title: 'Codex adapter and script'
type: 'feature'
created: '2026-09-09'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: 'aa12ca93823cf784371ae104eebea37e5a26b136'
---

<intent-contract>

## Intent

**Problem:** Only `claude` has an adapter behind the `Harness` port, so a Template that writes
`harness: codex` resolves to nothing and FR-14's "a harness is a choice on one screen" is a
promise the code cannot keep.

**Approach:** Add `infrastructure/harness/codex/` — the `codex exec --json` invocation, the
session id captured from the stream's own `thread.started` event, usage from `turn.completed`,
`resume`, and `resume_command` — mirroring `ClaudeHarness`'s three-way `start`/`wait`/`run`
split and sharing the JSON-stream primitives through a new `infrastructure/harness/jsonl.py`.

## Boundaries & Constraints

**Always:** AD-10 (the adapter interprets nothing beyond the harness's own framing: session id,
exit code, usage, log path, `raw_result` verbatim); AD-14 (`start` hands back the group before
anything waits on it, `wait` kills the group if it raises); AD-5 (`env_for` receives no
credential the contract does not already carry, and `resume_command` states identifiers only);
AD-2 (nothing under `infrastructure/harness/` is imported by `domain/` or `application/`); a
module is at most 400 lines; new coverage goes in new test files only.

**Block If:** landing the story requires editing an existing test file, `SPEC.md`,
`stories.yaml`, `epics.yaml` or any `AGENTS.md`.

**Never:** running the real Codex CLI (7.2 owns that); shipping a value only a live run could
confirm as if it were verified — every `[verify]` marker in the brief is implemented as the
documented shape and marked provisional in a code comment; guessing what 7.2 or 7.3 will do;
widening `HARNESS_NAMES` (it already names `codex`); parsing model output.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First dispatch | worktree, prompt, model, log path | `codex exec --json -C <worktree> -m <model> -o <log>.last.md "<prompt>"`, prompt last | No error expected |
| Session captured | stream holds `thread.started` with `thread_id` | `HarnessResult.session_id` is that id | No error expected |
| Session absent | stream holds no `thread.started` | `session_id` is `None`; 7.2's `session id recorded` line fails | Not an exception |
| Usage | final `turn.completed` carries usage fields | `HarnessUsage(tokens_in, tokens_out, cost_usd)` | Missing/non-numeric field → `usage=None`, `raw_result` kept |
| No model bound | `model=None` | no `-m` flag; the configured default decides | No error expected |
| Content logging | `ORCH_LOG_CONTENT == "1"` in the env | `-c otel.log_user_prompt=true` present | absent otherwise |
| Resume | session id + message | `codex exec resume <sid> --json "<message>"` | No error expected |
| Killed before writing | no log file | `usage=None`, `raw_result=None`, `session_id=None` | Not an exception |
| Timeout | runner reports `timed_out` | `timed_out=True`, `exit_code=None`, `pgid` on the record | Not an exception |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/harness.py` -- the port: `Harness`, `HarnessResult`,
  `HarnessHandle`, `HarnessCapabilities`, `HarnessUsage`. Read-only here.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:186` -- `ClaudeHarness`:
  the structure to mirror (`run` = `wait(start(...))`, guarded `wait`, `_record_prompt`).
- `backend-api/src/orchestrator/infrastructure/harness/claude/result.py` -- `read_text`,
  `json_objects`, `_as_int`, `_as_decimal`: the primitives that move to `jsonl.py` and are
  re-exported from here so every existing importer keeps working.
- `backend-api/src/orchestrator/infrastructure/harness/env.py` -- `env_for`, `AliasBuilder`,
  `HARNESS_ENV_CONTRACT`, `BASE_NAMES`. `CODEX_HOME` reaches the process through an
  `AliasBuilder`; `env.py` itself does not change.
- `backend-api/src/orchestrator/infrastructure/harness/registry.py:59` -- `build_harnesses`,
  `ALIASES`, `build_harness_env`: where registration would go. **Blocked** — see below.
- `scripts/harness/codex.sh` -- normative for `HARNESS_ENV_ALIASES=()`, `CODEX_HOME`, the
  `config.toml` this adapter must not write, and the invocation comment.
- `backend-api/tests/unit/fakes/process.py` -- `FakeProcessRunner`, the one fake for that port.
- `backend-api/tests/unit/test_harness_env_contract.py` -- the shape the new codex contract test
  copies (bash-array parsing, key-set equality). **Frozen**; a sibling module is added instead.

**Read-only evidence (anchor conflict).** Four existing assertions pin the registry to the
adapters Epic 5 landed, so `codex` cannot be added to `build_harnesses`:
`tests/unit/test_main_harness_registry.py:27`, `tests/unit/test_harness_registry.py:60`,
`tests/unit/test_dbos_startup_agent.py:44` (`list(...) == ["claude"]`) and
`tests/unit/test_fake_harness_registry.py:52` (`sorted(built) == ["claude", NAME]`). None names
a later story, so hard rule 1's exceptions do not reach them. The adapter lands; the
registration line does not, and the story halts `blocked` on it.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/infrastructure/harness/jsonl.py` -- new: `ENCODING`, `read_text`,
  `json_objects`, `as_int`, `as_decimal`, `objects_with`. -- one statement of the tolerant
  primitives both adapters need.
- `backend-api/src/orchestrator/infrastructure/harness/claude/result.py` -- import the four
  primitives from `jsonl.py` and re-export them. -- no public name of this module changes.
- `backend-api/src/orchestrator/infrastructure/harness/codex/events.py` -- new: `session_id_from`,
  `usage_from`, `result_object`. -- reading the event stream, separate from writing the argv.
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- new: `CodexHarness`,
  `codex_aliases`. -- the invocation, the three-way split, `resume`, `resume_command`.
- `backend-api/src/orchestrator/infrastructure/harness/codex/__init__.py` -- new: re-exports.
- `backend-api/tests/unit/infrastructure/harness/fixtures/codex/*.jsonl` -- new: sample streams.
- `backend-api/tests/unit/test_harness_jsonl.py` -- new: the shared primitives.
- `backend-api/tests/unit/test_codex_events.py` -- new: session capture and usage parsing.
- `backend-api/tests/unit/test_codex_adapter.py` -- new: argv, dispatch, resume, resume_command.
- `backend-api/tests/unit/test_codex_env_contract.py` -- new: the contract test for `codex`.
- `_bmad-output/planning-artifacts/mvp/addendum.md` -- append a §B record for story 7.1. -- the
  brief requires the record whether or not anything changed, and here nothing could be verified.

**Acceptance Criteria:**
- Given the contract test for `codex`, when run, then the key set of `env_for` equals
  `HARNESS_ENV_CONTRACT` ∪ `codex.sh`'s (empty) `HARNESS_ENV_ALIASES` ∪ the Project's variables ∪
  `{HOME, PATH, LANG, TERM, CODEX_HOME}`, and no secret beyond `LITELLM_API_KEY` and the Langfuse
  keys is present.
- Given a sample `codex exec --json` stream with a `thread.started` and a `turn.completed`, when
  `run` is called, then the argv is the documented invocation with `-C <worktree>` and the prompt
  last, `session_id` is the event's id, `usage` is parsed, and `exit_code`/`log_path` are set.
- Given a stream with no `thread.started`, when `run` is called, then `session_id` is `None`.
- Given `resume`, when called, then the argv is `codex exec resume <sid> --json "<message>"`.
- Given `resume_command`, when called, then it returns `cd <cwd> && codex resume <sid>` and holds
  no secret value.
- Given `ORCH_LOG_CONTENT == "1"` in the process environment, when the argv is built, then
  `-c otel.log_user_prompt=true` is present; given `"0"`, it is absent.
- Given `make lint` and `make test`, when run, then both exit 0.

## Spec Change Log

_No loopback: no finding was routed `bad_spec` or `intent_gap`._

## Review Triage Log

### 2026-09-09 — Review pass

Run inline rather than through review subagents: this dispatch forbids spawning any (two Epic 6
stories deadlocked that way), so the layers were executed by the same session against the diff.

- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 1, medium 0, low 2)
- defer: 0
- reject: 4
- addressed_findings:
  - `[high]` `[patch]` `HarnessResult.session_id` was annotated `str` while this adapter is the
    first that can answer `None` (a harness that names its own session and then printed none).
    Widened the port field to `str | None` with the reason on it; `mypy --strict` over `domain/`
    and `application/` still passes, and `Attempt.session_id` was already `str | None`.
  - `[low]` `[patch]` a line over 100 characters and an unsorted import block in the new test
    modules — `ruff format` / `ruff check --fix`.
  - `[low]` `[patch]` two malformed assertions left in `test_codex_adapter.py` while drafting
    (`runner.called("start")[0:0]`, `... and True`) — removed; both were vacuous.

Rejected as noise: "assert the `-C` flag is redundant with the runner's `cwd`" (the brief pins the
shape and 7.2 verifies it); "parse the `.last.md` file the `-o` flag writes" (AD-10 — the adapter
interprets nothing); "add `codex` to `templates/*.yaml`" (already there); "read a cost field out of
`turn.completed`" (guessing a field name is exactly what this story must not do).

## Design Notes

`CODEX_HOME` is `${AGENT_HOME}/.codex`, which is a `Settings` value, and `AliasBuilder` takes the
contract alone. So `codex_aliases` is a *factory*: `codex_aliases(agent_home)` returns the
builder. That is also why it cannot simply be a line in the module-level `ALIASES` table.

`capabilities.preassign_session` is `False`, and that has a consequence worth stating: `start`
cannot know the session, so its `HarnessHandle` carries `""` and only `wait` reports the captured
id. An attempt whose backend dies between `start` and `wait` therefore has no session to resume —
inherent to a harness that names its own session, not a defect of this adapter.

Every argv detail carries a `[verify]` marker in the brief and is implemented as the documented
shape with a `provisional` comment beside it: the `--json`/`-C`/`-m`/`-o` flags, whether
`--skip-git-repo-check` is needed under `cap_drop ALL`, the `thread.started`/`thread_id` names,
the `turn.completed` usage fields, the `codex exec resume` form, and `-c otel.log_user_prompt=true`.
7.2 settles them against the real CLI.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: exit 0

## Auto Run Result

Status: blocked
Blocking condition: anchor conflict — `codex` cannot be registered in `build_harnesses`

The adapter, its parser, the contract test and the fixtures all landed and both gates are green.
The one part of the brief's scope that did **not** land is the registration line, because four
existing test assertions pin the harness registry to the adapters Epic 5 shipped:

| File | Assertion | What it pins |
|---|---|---|
| `backend-api/tests/unit/test_main_harness_registry.py:27` | `assert list(harnesses) == ["claude"]` | the registry `main.py` re-exports holds exactly one adapter |
| `backend-api/tests/unit/test_harness_registry.py:60` | `assert list(harnesses) == ["claude"]` | the same, in the registry's own home |
| `backend-api/tests/unit/test_dbos_startup_agent.py:44` | `assert list(ports.harnesses) == ["claude"]` | the walker's `StepPorts.harnesses` |
| `backend-api/tests/unit/test_fake_harness_registry.py:52` | `assert sorted(built) == ["claude", NAME]` | test mode adds `fake` *beside* `claude` and nothing else |

Adding `CodexHarness` to `build_harnesses` makes all four red. **Why the story cannot land beside
them:** the brief's Scope puts "registration as `codex`" In, and `build_harnesses` is the one place
an adapter class is named (its own docstring says so) — there is no second seam. Hard rule 1's
exceptions do not reach these four: none is a pending-*gate* registry entry, and none names a later
story as the thing that replaces it (`test_the_registry_holds_the_one_adapter_this_epic_lands` says
"this epic", meaning Epic 5, the same wording the operator ruled insufficient for story 6-1). A
fifth assertion, `ALIASES == {"claude": claude_aliases}`
(`test_harness_registry.py:76`, `test_harness_env_subscription.py:193`), is **not** in conflict:
`codex_aliases` is a factory over `AGENT_HOME` and could never have been a line in that table.

An operator ruling is required. Nothing was edited, skipped or worked around.

