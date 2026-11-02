---
title: 'Stop identity and stale answers refused'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'f92dcca08735f0eb382e93779cfe5eab7d3a83a6'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Run holds one stop at a time, but nothing says which stop an answer was written for. An answer sent late, or to the wrong Run page, lands on whatever stop is current; the past Run's 5-1 answer reached 5-3 this way.

**Approach:** Each stop gets a number (`run.park_seq`, AD-24). A signal may name it as `stop`, and a mismatch is refused with 409 naming the current stop. The Run page and kit docs send it. A signal naming no stop behaves as today.

## Boundaries & Constraints

**Always:** `park_seq` increases on every write that puts a Run on a new stop. Refusal happens before any gate record, status or engine call. `stop` is checked on every signal kind that carries it. The Run page sends it on `answer`, `retry` and `continue`.

**Never:** No required `stop` (Deferred in the spine). No chat work. No new status token. No edit to an existing test file: new behaviour gets new test files. `AGENTS.md` is not touched. `budget_raise` returning a Run to its earlier stop does not increase the number.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh Run | never parked | `park_seq` 0 | N/A |
| Each park | second park on a Run | `park_seq` 2 | N/A |
| Dependency park | predecessor failed | `park_seq` increases | N/A |
| Budget on top of a park | `budget_second_record` path | `park_seq` increases | N/A |
| Budget raise back to the stop | `budget_raise` on a blocked row | `park_seq` unchanged | N/A |
| Matching stop | `answer` with `stop` equal to `park_seq` | Applied as today | N/A |
| Stale stop | `answer` with an earlier `stop` | Nothing written, no engine call | 409 naming the current stop's number, kind and path |
| Stale on a running Run | `stop` earlier than `park_seq`, Run running | Nothing written | 409 naming the current number |
| Stale `continue` on a dependency park | Earlier `stop` | Nothing written, not enqueued | 409 |
| No stop named | `answer` without `stop` | Applied as today | N/A |
| Read models | Run never parked | `park_seq` absent from the response | N/A |
| Read models | Run parked | `park_seq` in `GET /runs/{id}`, run detail's `run`, and `GET /runs/{id}/events` | N/A |
| Run page | parked Run, `answer`, `retry` or `continue` | Body carries `stop` = `park_seq` | Server's 409 detail shows in the existing error readout |
| Run page | other kinds | Body has no `stop` | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/entities/run.py` -- add `park_seq: int = 0`, beside `terminal_clean_polls` and for the same reason: `NOT NULL` with a default stays out of the frozen nullable-column set.
- `domain/values.py::Signal` -- add `stop: int | None = None`.
- `application/use_cases/writers.py` -- `park_run` and the dependency park near line 335 increase it. `apply_step_result.py` near line 361 too. `signal_effects.py:253` (`budget_raise`) does not.
- `application/use_cases/signal_run.py` -- check inside the unit of work, after `require_run`, in the main path and `_continue_dependency_run`. Raise `domain/errors.py::Conflict`, which maps to 409.
- `application/use_cases/run_events.py` and `api/schemas/run_events.py` -- carry the number.
- `api/schemas/runs.py::RunSummaryOut` -- carry the number. `RunDetailSummaryOut.of_run` builds on it through `model_dump`.
- `api/schemas/signals.py::SignalIn` -- add optional `stop`, passed on in `as_signal`.
- Field pattern: `Field(default=0, json_schema_extra=_drop_default)` plus a wrap `model_serializer` omitting it at 0, as `RunDetailOut` does for `reply_available`. Frozen router tests pin exact keys; omission at 0 leaves them passing. `_drop_default` lives in `api/schemas/run_views.py`, which imports `runs.py`, so move nothing and define the guard where the import direction allows.
- `infrastructure/db/models/run.py`, `infrastructure/db/repositories/runs.py` -- column and both mapping directions.
- `backend-api/alembic/versions/` -- `0022_run_park_seq.py`, revises `0021_run_updated_at`: `Integer`, `NOT NULL`, `server_default "0"`.
- `web-client/src/islands/RunDetail.tsx::sendSignal` -- the one place every control posts through; add `stop` there for the three kinds. Types come from `pnpm gen:api`, never by hand.
- `deploy/kit/skills/orchestrator/references/api.md` -- signal body and events fields; `deploy/kit/skills/orchestrator/SKILL.md` near line 187 -- send `stop` with an answer.

## Tasks & Acceptance

**Execution:**
- [ ] `backend-api/tests/unit/application/test_stop_identity.py` -- new; every backend matrix row, through the shared fakes, seen failing first -- TDD.
- [ ] `backend-api/tests/unit/test_stop_identity_schemas.py` -- new; `SignalIn.stop`, read-model presence and omission -- pins the contract.
- [ ] Domain, writers, `signal_run`, repository, model, migration -- per Code Map -- the behaviour.
- [ ] API schemas -- per Code Map, then `make openapi` -- contract is generated (AD-3).
- [ ] `web-client/src/lib/run/signals.ts`, `web-client/tests/unit/run-signals-stop.test.ts` -- a pure helper adding `stop` for the three kinds, tested in a new file; `RunDetail.tsx` calls it -- Run page rows.
- [ ] Kit docs -- per Code Map -- first-party clients send it.

**Acceptance Criteria:**
- Given a Run parked at stop 2, when a client posts `answer` with `stop: 1`, then the response is 409, the detail names stop 2 with its kind and path, and the gate record is unchanged.
- Given an existing database, when migrations run, then a Run parked at the upgrade reads `park_seq` 1, every other Run reads 0, and new stops count up from there.

## Implementation Notes

Approved for implementation by the Operator's accepted stories table (2026-11-01), which sets no spec checkpoint on 1-1.

Implemented in this session, not by a fresh subagent, with three independent review subagents. All review fixes were applied in place rather than by reverting and re-deriving, because none changed the design; the frozen intent stands.

**Not done:** `make e2e` could not reach the tests. The image build was refused at `ghcr.io/astral-sh/uv:0.12.9` (`failed to fetch oauth token: denied`), a Docker credential problem on this host. The status stays `in-review` until that gate passes (hard rule 6). In its place, migration 0022 ran on a throwaway Postgres: up, down, up, and over existing rows (a parked Run reads 1, a running Run reads 0). Passing: `make lint`, `make test`, and Playwright (`make e2e-ui`: 289 passed plus 1 known skip; then the new spec alone after fixing a locator).

## Spec Change Log

## Review Triage Log

| Finding | Layer | Verdict | Route | Evidence and action |
| --- | --- | --- | --- | --- |
| Draft for stop N stamped with N+1 after a poll | edge, blind | high | patch | `AnswerBox` keeps text across renders. `StopBody` is keyed on `park_seq`; browser test added. |
| HTTP path refuses before the stale check, so the 409 does not name the stop | edge, verification | high | patch | Reproduced by the reviewer through `handle_signal`. Check moved to the top of `_refuse_early`; route tests added. |
| Run parked at upgrade reads 0, so it gets no number | edge, blind | medium | patch | Contradicts the matrix row "Run parked". The migration gives such a Run 1; checked over real rows. AC reworded outside the frozen block. |
| MCP `send_signal` cannot send `stop` | blind | medium | patch | Confirmed at `infrastructure/mcp/tools.py`. Optional argument added and tested. |
| Watcher payload and `initiative-run` omit the number | blind | medium | patch | AD-24 names the kit. Payload carries `park_seq`; docs updated; tested. |
| A refused signal leaves the old question on screen | edge, blind | medium | patch | Confirmed in `sendSignal`. A 409 re-fetches; browser test added. |
| `dependency at None` in the refusal | edge, blind, verification | low | patch | Reproduced. The path is dropped when absent; asserted. |
| `start` skips the check | edge, blind, verification | low | patch | Frozen rule says every kind carrying `stop`. Check added; tested. |
| `true`, `"3"`, `2.0`, `-1` accepted as `stop` | blind | low | patch | Reproduced by the reviewer. Strict integer, `ge=0`; tested. |
| Two concurrent answers both pass; the extra `engine.signal` may wake the next stop | edge, blind | maybe-false | defer | Medium if true. No row lock anywhere, and it predates this story. Settle by tracing a second `send` to the `human:` topic. See deferred-work. |
| Stale `skip_*` unguarded, and AD-24 says "always send" | blind | low | reject | The frozen intent limits the Run page to three kinds, and skips confirm first. Raised to the Operator in the hand-back. |
| No machine-readable stale refusal | blind | low | reject | Clients re-read the Run either way; a new problem type adds surface no current reader needs. |
| Non-zero `park_seq` never read through the real repository | verification | medium | patch | Unit round trip added. A Postgres-level test is deferred with the e2e gate. |
| Web wiring, `/events` and "never reset" untested | verification | medium | patch | New browser spec, `run_event` test and park-answer-park test. |
| Spec's Code Map names a test file that does not exist | edge | low | reject | Fixing it only edits this spec; the path was corrected in Tasks anyway. |
| Third copy of `_drop_default`, misplaced doc comment, "eleven fields" comment | blind | low | patch | One `drop_default` in `common.py`; comments corrected. |
| `run.py` module docstring lists three rules without `park_seq` | blind | low | reject | The field's own comment states it. |

## Verification

**Commands:**
- `make lint` -- expected: passes, including import-linter and test pairs.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift after generation.
