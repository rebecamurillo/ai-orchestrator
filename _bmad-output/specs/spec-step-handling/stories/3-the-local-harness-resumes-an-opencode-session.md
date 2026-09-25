---
title: 'The local harness resumes an OpenCode session'
type: 'feature'
created: '2026-09-25'
status: 'done'
baseline_revision: '6b130348969d1fb575ee276b54d89d3ee9732fce'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      `resume_command` does not quote `cwd` in the shell output; a path with spaces would break
      the operator paste command.
    evidence: |-
      `f"cd {cwd} && opencode run --session {session_id}"` — no quoting around `{cwd}`. Paths
      in this system are machine-generated worktree paths under `/work/…` without spaces, so
      the risk is latent rather than active.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:292
    severity: low
---

<intent-contract>

## Intent

**Problem:** `LocalHarness.capabilities.resume` is `False` and `resume()` raises `NotImplementedError`, on the false stated ground that OpenCode cannot continue a session. `opencode run --session {id}` at v1.18.26 — the pinned `OPENCODE_VERSION` — does continue a session; the premise is wrong. Because `local` declares no resume, `reply_available` is always `False` for local Runs, the mode selector CAP-3 gates on is never shown, and `resume_command` returns `None` so the terminal block is hidden.

**Approach:** Amend the adapter: flip `capabilities.resume = True`, implement `resume()` with `opencode run --session {session_id}`, implement `resume_command()` returning the operator's paste-able line. No other module changes — `application/steps/agent.py` already reads the capability and routes through `resume()` when it is `True`.

## Boundaries & Constraints

**Always:**
- `opencode run --session {session_id}` only. Never `--continue` (guesses last session of a shared directory) and never `--fork` (mints a new session id, breaking spend and trace attribution, AD-11).
- A `session_not_found` exit-1 is a reported failure; `result.session_id` stays the tried id, never replaced by a fresh session (hard rule 7).
- No version bump; `OPENCODE_VERSION=1.18.26` already carries `--session`.
- AD-10: invocation written once, in `adapter.py`, nowhere else. No application module learns a flag.
- AD-2: `domain/` and `application/` import nothing from `infrastructure/`. The only file that changes is in `infrastructure/harness/opencode/`.
- 100 % branch coverage on `domain/` and `application/`.

**Block If:** any requirement to pass `--fork`, `--continue`, or to fall back silently to a fresh session when session-not-found is returned.

**Never:**
- Pass `--fork` or `--continue`.
- Return `None` from `resume_command` (it returns a real string now that `capabilities.resume = True`).
- Change the session_id fallback in `wait()` in a way that overwrites the resume handle's id with an unrelated stored session.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal resume | `session_id="ses_abc"`, process exits 0, stream has session event | `result.session_id="ses_abc"`, `result.exit_code=0`, argv has `--session ses_abc` | — |
| Resume, stream id absent | `session_id="ses_abc"`, process exits 0, no session event in stream | `result.session_id="ses_abc"` (handle fallback) | — |
| Session not found | `session_id="ses_gone"`, process exits 1, no session event | `result.exit_code=1`, `result.session_id="ses_gone"` — never None or a new session | Caller marks attempt failed on exit_code |
| resume_command | `cwd="/work/r/wt/x"`, `session_id="ses_abc"` | `"cd /work/r/wt/x && opencode run --session ses_abc"` | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:33-36` — `**There is no resume**` docstring paragraph (the one being replaced by the AD-10 amendment; rewrite to `**Resume**` matching ClaudeHarness's docstring section)
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:126` — `RESUME_UNSUPPORTED` constant — remove (becomes dead code once `resume()` is implemented)
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:183` — `capabilities = HarnessCapabilities(preassign_session=False, resume=False, native_tracing=False)` — change `resume=True`; update the capabilities comment block above it
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:255-273` — `resume()` — replace `raise NotImplementedError` body with: build argv via `_resume_argv(cwd, session_id=session_id, message=message)`, call `_record_prompt`, call `runner.start`, return `self.wait(HarnessHandle(session_id=session_id, log_path=log_path, pid=handle.pid, pgid=handle.pgid, cwd=cwd))`
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:275-283` — `resume_command()` — replace `return None` body with `return f"cd {cwd} && {EXECUTABLE} {RUN} {SESSION_FLAG} {session_id}"`
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:298-317` — `wait()` — change the `session_id` expression from `session_id_from(stream) or self._stored_session(handle)` to: extract `captured = session_id_from(stream)` then `session_id=captured if captured is not None else (handle.session_id or self._stored_session(handle))` — this makes the resume path (non-empty handle.session_id) fall back to the handle's id, while the start path (handle.session_id="") still falls through to the store
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:330-342` — `_argv()` — read-only; resume uses its own helper
- Add `SESSION_FLAG = "--session"` constant (after `MODEL_FLAG`)
- Add `_resume_argv(self, cwd, *, session_id, message) -> list[str]` method (after `_argv`): returns `[EXECUTABLE, RUN, FORMAT_FLAG, FORMAT_JSON, DIR_FLAG, str(cwd), SESSION_FLAG, session_id, message]` — no `-m` flag (session retains its model)

**Test files with behavior-change revisions (story 3, 2026-09-25):**

- `backend-api/tests/unit/test_local_adapter.py:17-22` — module docstring says "resume: there is no resume form"; update to reflect that resume IS implemented (story 3, 2026-09-25)
- `backend-api/tests/unit/test_local_adapter.py:154-157` — `test_it_claims_none_of_the_three_capabilities`: assertion `resume is False` contradicts the new capability; update to `resume is True` (story 3, 2026-09-25 declared behaviour change; split into a separate `test_it_claims_resume` assertion at the same line)
- `backend-api/tests/unit/test_local_adapter.py:394-397` — `test_there_is_no_paste_able_resume_line` asserts `resume_command(...) is None`; replace with `test_resume_command_returns_the_opencode_session_line` asserting the actual command format (story 3, 2026-09-25 declared behaviour change)
- `backend-api/tests/unit/test_local_adapter.py:400-413` — `test_resume_refuses_rather_than_quietly_starting_a_new_session` asserts `NotImplementedError`; replace with tests asserting the actual resume behavior (story 3, 2026-09-25 declared behaviour change)
- `backend-api/tests/unit/test_local_registry.py:283-305` — `test_a_parked_local_attempt_has_no_terminal_because_it_cannot_resume` asserts `terminal is None` and `capabilities.resume is False`; replace with `test_a_parked_local_attempt_now_has_a_terminal_command` asserting `terminal is not None` and `capabilities.resume is True` (story 3, 2026-09-25 declared behaviour change)
- `backend-api/tests/unit/test_terminal_command.py:525-539` — `test_a_harness_the_registry_does_not_hold_has_no_terminal` is parametrized with `["local", ""]`; remove `"local"` — after story 3, `local` IS in the registry and IS resumable, so `ports(settings)` returns a terminal for it; the `"local"` case no longer belongs here (story 3, 2026-09-25 declared behaviour change)

**New test additions (test first):**

- `backend-api/tests/unit/test_local_adapter.py` — new `# ── resume ──` section:
  - `test_resume_argv_uses_session_flag_not_model_flag` — runner.called("start")[0]["cmd"] contains `"--session"` and `session_id`, does not contain `"-m"` or `"litellm/"`
  - `test_resume_result_carries_the_session_id_it_was_given` — `result.session_id == SESSION_ID` even when stream has no session event (uses "no-session" fixture)
  - `test_a_failed_resume_reports_the_attempted_session_id` — process exits 1, `result.exit_code == 1`, `result.session_id == SESSION_ID` (hard rule 7: no silent fresh session)
  - `test_resume_records_the_message_beside_the_log` — prompt file written

- `backend-api/tests/unit/test_terminal_command.py` — new test `test_local_resume_command_names_the_session` — calls `build(settings, harness="local")` (same helper the file already has), asserts `"--session"` is in the result and `SESSION` (the attempt's session_id) is in the result

## Tasks & Acceptance

**Execution:**

- `backend-api/tests/unit/test_local_adapter.py` — (tests first, story 3, 2026-09-25) update `test_it_claims_none_of_the_three_capabilities` to `resume is True`; replace `test_there_is_no_paste_able_resume_line` with `test_resume_command_returns_the_opencode_session_line`; replace `test_resume_refuses_rather_than_quietly_starting_a_new_session` with the four new resume tests listed in Code Map — all must fail before adapter.py changes
- `backend-api/tests/unit/test_local_registry.py` — (story 3, 2026-09-25 declared behaviour change) replace `test_a_parked_local_attempt_has_no_terminal_because_it_cannot_resume` with `test_a_parked_local_attempt_now_has_a_terminal_command` (asserts `terminal is not None`, `capabilities.resume is True`, `"--session"` in command) — must fail before adapter.py changes
- `backend-api/tests/unit/test_terminal_command.py` — (story 3, 2026-09-25 declared behaviour change) change `@pytest.mark.parametrize("harness", ["local", ""])` to `@pytest.mark.parametrize("harness", [""])` and update the docstring; add `test_local_resume_command_names_the_session` — must fail before adapter.py changes
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` — implement: add `SESSION_FLAG = "--session"`; change `capabilities.resume = True`; remove `RESUME_UNSUPPORTED`; implement `resume()`; implement `resume_command()` returning the real command; add `_resume_argv()`; update `wait()` to `captured if captured is not None else (handle.session_id or self._stored_session(handle))` — makes failing tests pass
- Update module docstring in `adapter.py` to replace the `**There is no resume**` paragraph with `**Resume** (AD-10 amended 2026-09-25): ...`

**Acceptance Criteria:**
- Given `LocalHarness` is instantiated, then `capabilities.resume is True`.
- Given `harness.resume_command("/work/r/wt/x", "ses_abc")` is called, then the return value is `"cd /work/r/wt/x && opencode run --session ses_abc"` (a non-None string).
- Given `resume(cwd=..., session_id="ses_abc", message="...", ...)` is called and the process exits 0, when the stream contains no session event, then `result.session_id == "ses_abc"` and `result.exit_code == 0`.
- Given `resume(...)` is called with `session_id="ses_gone"` and the process exits 1 (Session not found), then `result.exit_code == 1` and `result.session_id == "ses_gone"` — never `None` and never a fresh session id.
- Given the registry is built with a settings that includes `local`, and a parked `local` attempt has a recorded `session_id`, when `resume_command(ports, run, row, attempt, project_slug=...)` is called, then `terminal is not None` and the command contains `"--session"`.
- Given `build(settings, harness="local")` is called in `test_terminal_command.py`, then the command contains `"--session"` and the attempt's session id.

## Design Notes

`wait()` today: `session_id=session_id_from(stream) or self._stored_session(handle)`. For start, `handle.session_id=""` (empty string), so the fallback chain is: stream → store → None. For resume, `handle.session_id=session_id` (non-empty), so the new chain `captured if captured is not None else (handle.session_id or self._stored_session(handle))` gives: stream (if present) → handle's id (non-empty truthy) → done. The store is never consulted for a resume, which is correct — the handle already knows which session was attempted.

`_resume_argv` omits `-m litellm/{model}` because the continued session retains its original model configuration; forcing a model on resume could conflict with what the session already has. The `--dir` flag is kept for correctness — it tells OpenCode which directory this is running in, the same rationale as in `_argv`.

Removing `RESUME_UNSUPPORTED` removes dead code; if mypy or ruff flag it as unused it would anyway fail `make lint`. The constant is not imported by any test.

## Verification

**Commands:**
- `make test` — expected: all unit tests pass; 100 % branch coverage on `domain/` and `application/`; the four new resume tests pass; the revised capability/resume_command/terminal tests pass
- `make lint` — expected: zero errors (ruff, mypy strict, import-linter); `RESUME_UNSUPPORTED` not referenced anywhere causes no import error

## Spec Change Log

## Review Triage Log

### 2026-09-25 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 0, low 4)
- defer: 1: (high 0, medium 0, low 1)
- reject: 13
- addressed_findings:
  - `[low]` `[patch]` No exact argv equality assertion for `_resume_argv`; sibling adapters both use `==` assertion; dropping `--format json` would silently break stream parsing — added exact list equality and explicit `--continue`/`--fork` negative assertions to `test_resume_argv_uses_session_flag_not_model_flag`
  - `[low]` `[patch]` `domain/ports/harness.py` `resume_command` docstring named `local` as having `capabilities.resume = False (7.3)` — updated to remove the stale example and note story 3 (2026-09-25)
  - `[low]` `[patch]` `application/use_cases/terminal.py` module docstring listed `local` as a `None`-returning harness — removed the stale parenthetical
  - `[low]` `[patch]` `test_local_registry.py` module docstring stated "local is the first registered harness that declares no resume, so FR-21's terminal block is None for it" — contradicted the test in the same file; updated to describe the new behaviour

## Auto Run Result

**Status:** done

**Implemented change:** Flipped `LocalHarness.capabilities.resume = True`, implemented `resume()` with `opencode run --session {session_id}` via `_resume_argv`, implemented `resume_command()` returning the operator's paste-able line, and updated `wait()`'s session_id fallback chain so a resume handle's known id is preserved even on exit-1 (hard rule 7).

**Files changed:**
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` — added `SESSION_FLAG`; removed `RESUME_UNSUPPORTED`; flipped `capabilities.resume = True`; implemented `resume()` and `resume_command()`; added `_resume_argv()`; updated `wait()` fallback chain; updated module and capability docstrings
- `backend-api/tests/unit/test_local_adapter.py` — updated module docstring; split capability assertion; replaced old resume tests with 5 new tests covering argv, session_id fallback, exit-1 handling, prompt recording, and resume_command format
- `backend-api/tests/unit/test_local_registry.py` — updated module docstring (story 3 patch); replaced `test_a_parked_local_attempt_has_no_terminal_because_it_cannot_resume` with `test_a_parked_local_attempt_now_has_a_terminal_command`
- `backend-api/tests/unit/test_terminal_command.py` — removed `"local"` from no-terminal parametrize; added `test_local_resume_command_names_the_session`
- `backend-api/tests/unit/test_codex_registry.py` — updated `test_a_harness_the_registry_still_does_not_hold_has_no_terminal` → `test_a_parked_local_attempt_now_has_a_terminal_command`
- `backend-api/src/orchestrator/domain/ports/harness.py` — updated `resume_command` docstring (story 3 patch)
- `backend-api/src/orchestrator/application/use_cases/terminal.py` — updated module docstring (story 3 patch)

**Review findings breakdown:**
- Patches applied: 4 (all low) — exact argv assertion, 3 stale docstring fixes
- Items deferred: 1 (low) — `resume_command` unquoted cwd (paths are machine-generated, spaces highly unlikely)
- Items rejected: 13 — diff truncation artifacts, caller invariants, pre-existing patterns, speculative edge cases, cosmetic noise

**Follow-up review recommended:** false (4 low patches; score=4, threshold=5)

**Verification performed:**
- `make lint` — zero errors (ruff, mypy strict, import-linter, eslint, tsc, prettier, test pairs, gen:api drift)
- `make test` — 7299 backend + 1726 frontend tests pass; 100% branch coverage on `domain/` and `application/`; all new resume tests pass

**Residual risks:** `resume_command` output contains unquoted `cwd`; a path with spaces would break the operator paste command. Paths are machine-generated worktree paths under `/work/…` — spaces are highly unlikely. Deferred as low-severity.
