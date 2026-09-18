---
title: "Serve any Attempt's full log"
type: 'feature'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
baseline_revision: '87aac942576cddb96fbc3729472fe545a8ec4483'
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      RealLogReader.read_from limit-path falls through when file uses CR-only line endings
    evidence: |-
      The byte-count loop in read_from counts \n bytes; splitlines() splits on \r too.
      If limit is exceeded and the file uses \r-only line endings, no \n is found and
      all_lines is returned untruncated. Theoretical only — subprocess/TTY logs never
      use \r-only endings in practice.
    location: >-
      backend-api/src/orchestrator/infrastructure/process/logs.py
    severity: low
  - summary: >-
      FakeLogReader.read_from mirrors RealLogReader pagination logic rather than providing simple canned control
    evidence: |-
      The fake re-implements the byte-cursor algorithm to match real behaviour, meaning
      a fix to the real logic must also be applied to the fake. Acceptable for now but
      couples test fixture to implementation detail.
    location: >-
      backend-api/tests/unit/fakes/logs.py
    severity: low
  - summary: >-
      AD-1 proxy constraint (browser never touches log volume) is asserted only in prose, not in a test
    evidence: |-
      The module docstring and spec state that all delivery goes through the web-client
      proxy. No test verifies the backend is unreachable without the proxy or that CORS
      headers prevent direct browser access. This is a deployment/architectural guarantee
      that predates this story.
    location: >-
      backend-api/src/orchestrator/api/routers/run_attempts.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** No endpoint exists to page through a step attempt's log. The UI can only see the last 40 lines embedded in the Run detail; it cannot follow a live log or download the full file.

**Approach:** Add `GET /api/v1/runs/{run_id}/attempts/{attempt_id}/log` with byte-cursor paging and a `?download=true` variant. Extend `LogReader` for cursor reads and `AttemptRepository` for direct ID lookup; regenerate the OpenAPI contract.

## Boundaries & Constraints

**Always:**
- All delivery through the web-client catch-all proxy; the browser never reaches the log volume directly (AD-1).
- TDD: unit tests written first, all failing, before any implementation task (AD-18).
- `make openapi` then `pnpm gen:api` complete with no drift after the route lands (AD-3); `schema.d.ts` is never hand-edited.
- Route reads state only; no status writes anywhere (AD-8).
- Extend `FakeLogReader` and `FakeAttemptRepository` for new port methods; no new doubles (AD-18).
- `LogPageOut` lives in `api/schemas/`; `application/` and `domain/` never import from `api/` (AD-2).
- The new router reuses `Depends(run_view_ports)` — no new provider function in `providers.py`.

**Block If:** Any pre-existing test fails after these changes — classify and report per AGENTS.md rule 1 before proceeding.

**Never:** Return HTTP 4xx/5xx when a log file is garbage-collected — answer 200 with `lines=["log no longer on disk"]`. Add signal actions or status transitions.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First page | `log_path` set, file exists, `cursor=0`, `limit=200` | 200 `LogPageOut`; `lines` non-empty, `next_cursor` = byte offset after last returned line, `eof=false` when file has more content | No error |
| Live follow | Running attempt; client sends last `next_cursor` | Only newly appended lines returned; `eof=false`; `lines=[]` with `eof=false` if no new bytes yet | No error |
| Cursor at end | `cursor >= file_size` | `lines=[]`, `next_cursor=cursor`, `eof=true` | No error |
| GC'd log | `log_path` non-null, file absent from disk | 200 `LogPageOut(lines=["log no longer on disk"], next_cursor=0, eof=true)` | Never 4xx/5xx |
| Null log path | `log_path is None` | 200 `LogPageOut(lines=[], next_cursor=0, eof=true)` | No error |
| Download, file exists | `?download=true`, file present | 200, `Content-Type: text/plain; charset=utf-8`, `Content-Disposition: attachment; filename="{attempt_id}.log"`, full raw bytes | No error |
| Download, GC'd | `?download=true`, file absent | 200, `text/plain`, body `"log no longer on disk"` | Never 4xx/5xx |
| Attempt not found | `attempt_id` absent from DB | 404 problem+json | Standard problem response |
| Wrong run | `attempt.run_id != run_id` | 404 problem+json | Same shape as not-found |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/logs.py:22` — `LogReader` protocol; add `read_from(path, cursor, limit) -> tuple[list[str], int, bool] | None` (None signals GC'd: non-null path, file missing) and `read_raw(path) -> bytes | None`
- `backend-api/src/orchestrator/infrastructure/process/logs.py:17` — `RealLogReader`; implement `read_from` (binary-mode seek, line-split, None on OSError when path non-null) and `read_raw` (bytes or None); both return None on OSError for non-null path
- `backend-api/tests/unit/fakes/logs.py:6` — `FakeLogReader`; add `read_from` and `read_raw` to match protocol
- `backend-api/src/orchestrator/domain/ports/repositories.py:138` — `AttemptRepository` protocol; add `get(attempt_id: UUID) -> Attempt | None`
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py:121` — `SQLAlchemyAttemptRepository`; implement `get` via `session.get(AttemptRow, attempt_id)` + existing `to_entity(row)` at line 55; return None if row absent
- `backend-api/tests/unit/fakes/runs.py:124` — `FakeAttemptRepository`; add `get(attempt_id)` returning `self.attempts.get(attempt_id)`
- `backend-api/src/orchestrator/api/schemas/run_attempts.py` — new; `LogPageOut(lines: list[str], next_cursor: int, eof: bool)` Pydantic model
- `backend-api/src/orchestrator/api/routers/run_attempts.py` — new router; `GET /runs/{run_id}/attempts/{attempt_id}/log`; injects `RunViewPorts` via `Depends(run_view_ports)` (already carries `attempts` and `logs`); 404 when attempt absent or `attempt.run_id != run_id`; GC'd→200 `["log no longer on disk"]`; download via `read_raw`; paged via `read_from`
- `backend-api/src/orchestrator/main.py` — import `run_attempts` router and register it in `_mount()` alongside other run-scoped routers (lines 279–318)
- `backend-api/tests/unit/test_run_attempt_log_router.py` — new; all I/O matrix scenarios via `app.dependency_overrides` with `FakeLogReader` + `FakeAttemptRepository`
- `contracts/openapi.json` — regenerated by `make openapi`
- `web-client/src/api/schema.d.ts` — regenerated by `pnpm gen:api` inside `web-client/`

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_run_attempt_log_router.py` -- WRITE FIRST (TDD): all I/O matrix scenarios using `FakeLogReader` and `FakeAttemptRepository` via dependency overrides; every test must fail before the remaining tasks are touched
- `backend-api/src/orchestrator/domain/ports/logs.py` -- add `read_from` and `read_raw` to `LogReader` protocol
- `backend-api/src/orchestrator/infrastructure/process/logs.py` -- implement `read_from` and `read_raw` in `RealLogReader`
- `backend-api/tests/unit/fakes/logs.py` -- add `read_from` and `read_raw` to `FakeLogReader`
- `backend-api/src/orchestrator/domain/ports/repositories.py` -- add `get(attempt_id: UUID) -> Attempt | None` to `AttemptRepository` protocol
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py` -- implement `get` in `SQLAlchemyAttemptRepository`
- `backend-api/tests/unit/fakes/runs.py` -- add `get` to `FakeAttemptRepository`
- `backend-api/src/orchestrator/api/schemas/run_attempts.py` -- create `LogPageOut` Pydantic model
- `backend-api/src/orchestrator/api/routers/run_attempts.py` -- create the log router
- `backend-api/src/orchestrator/main.py` -- import and register `run_attempts.router`
- `contracts/openapi.json` -- run `make openapi`
- `web-client/src/api/schema.d.ts` -- run `pnpm gen:api` in `web-client/`

**Acceptance Criteria:**
- Given an attempt with an existing log file and `cursor=0`, when `GET /runs/{run_id}/attempts/{attempt_id}/log`, then 200 with `lines` containing log content, `next_cursor > 0`, and `eof=false` when bytes remain beyond that cursor
- Given a running attempt, when the client polls with its last `next_cursor`, then only lines appended since that cursor are returned
- Given an attempt whose log file was garbage-collected, when `GET /runs/{run_id}/attempts/{attempt_id}/log`, then 200 with `lines=["log no longer on disk"]` and `eof=true`
- Given `?download=true` with an existing file, when the endpoint is called, then 200 response carries `Content-Type: text/plain; charset=utf-8`, `Content-Disposition: attachment`, and the full raw file bytes
- Given an unknown `attempt_id` or one whose `run_id` does not match the URL, when the endpoint is called, then 404 problem+json
- Given `make openapi` then `pnpm gen:api`, when run after all changes land, then both exit 0 with no schema drift (AD-3)

## Design Notes

**Cursor as byte offset:** seeking to a byte position in a growing file is O(1) and stays correct across appends. `read_from` opens the file in binary mode, seeks to `cursor`, reads bytes, decodes to lines (UTF-8, errors replaced), and returns the byte offset after the last `\n` in the returned set as `next_cursor`. An incomplete trailing line (no `\n`) is not returned — this keeps paging deterministic for pollers.

**`read_from` returning `None`:** distinguishes a GC'd file (`log_path` non-null but `OSError` on open) from an empty or fully-consumed file (`([], cursor, True)`). The router converts `None` to the "log no longer on disk" copy; it never reaches the wire as Python `None`.

**`run_view_ports` reuse:** `RunViewPorts` already carries `attempts: AttemptRepository` and `logs: LogReader` (wired in `providers.py` lines 238–244). No new provider, no new ports dataclass.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: all tests green including `test_run_attempt_log_router.py`
- `make openapi` -- expected: exit 0, new route in `contracts/openapi.json`
- `cd web-client && pnpm gen:api` -- expected: exit 0, no schema drift

## Spec Change Log

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 1, low 3)
- defer: 3: (high 0, medium 0, low 3)
- reject: 10
- addressed_findings:
  - `[medium]` `[patch]` RealLogReader.read_from and read_raw lacked unit tests in test_real_log_reader.py — added 8 tmp_path-based tests covering first page, live follow, cursor-at-end, limit enforcement, incomplete trailing line, OSError→None, and read_raw present/absent
  - `[low]` `[patch]` null log_path + download=True branch not tested — added test_null_log_path_download_returns_empty_text_plain asserting 200 text/plain with empty body
  - `[low]` `[patch]` GC'd download test did not assert absence of Content-Disposition — added assertion that "attachment" is absent from the content-disposition header
  - `[low]` `[patch]` LogPageOut.next_cursor had no ge=0 Pydantic field validator — changed to Annotated[int, Field(ge=0)]

## Auto Run Result

**Status:** done

**Summary:** Added `GET /api/v1/runs/{run_id}/attempts/{attempt_id}/log` to the backend with byte-cursor paging and `?download=true` variant. Extended the `LogReader` port with `read_from` and `read_raw`; extended `AttemptRepository` with `get(attempt_id)`; added `LogPageOut` schema; registered new router reusing `run_view_ports`; regenerated `contracts/openapi.json` and `web-client/src/api/schema.d.ts`.

**Files changed:**
- `backend-api/src/orchestrator/domain/ports/logs.py` — added `read_from` and `read_raw` to `LogReader` protocol
- `backend-api/src/orchestrator/infrastructure/process/logs.py` — implemented `read_from` (binary seek, line-split, limit enforcement) and `read_raw` in `RealLogReader`
- `backend-api/src/orchestrator/domain/ports/repositories.py` — added `get(attempt_id)` to `AttemptRepository` protocol
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py` — implemented `get` via `session.get`
- `backend-api/tests/unit/fakes/logs.py` — added `read_from` and `read_raw` to `FakeLogReader`
- `backend-api/tests/unit/fakes/runs.py` — added `get` to `FakeAttemptRepository`
- `backend-api/src/orchestrator/api/schemas/run_attempts.py` — new; `LogPageOut` with `ge=0` on `next_cursor`
- `backend-api/src/orchestrator/api/routers/run_attempts.py` — new router
- `backend-api/src/orchestrator/main.py` — registered `run_attempts.router`
- `backend-api/tests/unit/test_run_attempt_log_router.py` — new; 15 tests covering all I/O matrix rows
- `backend-api/tests/unit/test_real_log_reader.py` — 8 new tests for `read_from` and `read_raw`
- `contracts/openapi.json` — regenerated with new route and `LogPageOut` schema
- `web-client/src/api/schema.d.ts` — regenerated

**Review findings:** 4 patches applied, 3 deferred (all low), 10 rejected.

**Follow-up review recommended:** true (score 6 ≥ 5: 1 medium patch × 3 + 3 low patches × 1).

**Verification:**
- `make lint`: exit 0
- `make test`: 6326 passed, 23 skipped, 0 failures
- `make openapi`: exit 0, new route visible in `contracts/openapi.json`
- `pnpm gen:api`: exit 0, no schema drift

**Residual risks:** Three deferred items (CR-only line endings in limit path, FakeLogReader logic duplication, AD-1 proxy constraint untested in code) — all low severity, all pre-existing or theoretical.
