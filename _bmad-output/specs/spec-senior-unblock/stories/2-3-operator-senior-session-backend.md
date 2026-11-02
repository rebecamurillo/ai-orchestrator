---
title: 'Operator senior session: lock and close'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'c4d212b2ba1bf653c085ebff988df7b611b1f0be'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** At a stop, the terminal hand-off is the Operator's only way to work with an agent inside the Run, and it bypasses billing, commits and the anchor check. AD-23's session first needs a lock that holds every other actor off the Run, and a close that refuses while an anchor edit is unconfirmed.

**Approach:** AD-23, first half; story 2-5 adds the turns. `session_start {scope, harness, model}` sets `run.senior_session`, which locks the Run. `session_end {confirmed_paths?}` releases it once every anchor edit made by the session's attempts is confirmed or reverted. `GET /runs/{id}/session` reads the state.

## Boundaries & Constraints

**Always:**
- Rules in `signals_table.py`: `session_start` has `run_statuses = PARKED`, every park kind but `dependency`, `operator_action = False`, and extra `park_path` set and neither `terminal_session` nor `senior_session`. `session_end` has `PARKED`, `ANY_PARK`, `operator_action = False`, and extra `senior_session`. `terminal_start`'s extra also requires `not senior_session`. Neither kind is offered through `admitted_signals`; the read model's `available` offers the start.
- The lock is the first check in `rules/signals.py::validate`. While `run.senior_session` is set, every kind but `session_end` and `cancel` gets 409 `senior session open: end it before {kind}`, so `signal_run`'s direct callers (chat, `terminal_poll`) are refused too. `run_admitted_signals` returns `("cancel", "session_end")` before its terminal branch. `PUT /runs/{id}/files` is refused as during `terminal_session`.
- `signal_run` reads the Run through a new `RunRepository.get_for_update` (`SELECT … FOR UPDATE`; the fake returns `get`) in each of its units of work. Signals on one Run therefore serialize, and `session_start` and `terminal_start` cannot both pass.
- After `validate`, `signals._refuse_early` calls `session_checks.refuse`. Scope: `story` needs `story_frame(park_path)`, `epic` needs `epic_frame` or `run_is_one_epic`, and `run` always passes; otherwise 422 `no {scope} frame at {path}`. The harness must be in the registry with `capabilities.resume` (422). The Probe is re-read and the model checked as `create_run` does it (422 naming the reason or the list). `run.worktree_path` must be set (409 `no worktree yet`). Remaining budget must be above 0 when `budget_usd` is set (409 `no remaining budget`).
- The session's attempts are the `role = session` attempts on the park row with `started_at` at or after the last `session_start` record (`rules/session.py`, pure). `session_end` gets 409 `turn running` while one of them has no `ended_at`.
- Anchor edits: anchors = `protected_paths.build(spec_folders = every row's and the Run's, initiative_folder, frozen_test_files = ())`, plus `check`'s `AGENTS.md` name rule, so tests are excluded (AD-23). Changes = `diff_changes(first start_sha, HEAD) ∪ uncommitted` in the dispatch tree, plus the same from `root_start_sha` at the root, spelled as `agent_workdir.changes` spells them. A session with no start SHA has none. A reverted file no longer differs, so it is not listed.
- `session_end`: unconfirmed edits get 409 naming each one. A `confirmed_paths` entry that is not a listed edit gets 422. The anchor check writes the number of session attempts it read into the payload as `turns`. Under the lock, the effect re-checks that no session attempt is open and that the count still equals `turns`; otherwise 409 `turn running`. On success, `senior_session = false`, the gate record carries `confirmed_paths`, and the Run stays parked (`resume = False`). `_cancel` also clears the flag.
- `GET /runs/{id}/session` returns `{active, available, scopes, scope, harness, model, anchor_edits}`. `active` is false on a terminal Run. `available` means `session_start` passes `validate`. `scope`, `harness` and `model` come from the last `session_start` payload.

**Never:** No Run or Step status write and no new status token (AD-8). Confirmed files never join `run.accepted_paths`. `check` subtracts accepted paths from anchors too, so a confirmed `stories.yaml` would let every later agent edit it unseen (hard rule 1 prevails over AD-13's row; the Operator ratifies the amended row). No turn (2-5), no UI (2-4). `DBOS_APPLICATION_VERSION` stays `1`. No container is stopped.

**Decided:**
- Opening context, reply text and a resumed turn's pgid are settled in 2-5.
- Under rule 1(b), AD-13's 2026-11-01 amendment declares both kinds. `test_run_statuses.py::test_the_signal_kinds_are_the_twelve_ad_13_names`: the tuple gains `session_start` and `session_end` after its current last entry, and the count in the name follows. The revision cites 2-3, 2026-11-02 and the amendment. `tests/unit/fakes/runs.py` gains `get_for_update`; the Operator reviews it at the AD-17 park. No other existing test changes. `test_terminal_signals.py::test_the_scope_gate_no_longer_stands_between_a_signal_and_its_effect` picks up both kinds and must still read `invalid for status running`, which `PARKED` guarantees. `test_signal_rules.py::test_a_stop_offers_the_actions_prd_4_6_lists` holds because neither kind is an operator action.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| Start | `blocked`, scope `story`, resuming harness, listed model | `senior_session = true`; gate record with the payload | N/A |
| Start refused | `terminal_session`; already open; `dependency`; no frame; harness unknown or without `resume`; Probe fails; model unlisted; no worktree; no budget | Nothing written | 409 or 422, named |
| Race | `session_start` and `terminal_start` sent together | One applies | The other 409 |
| Locked | `answer`, `retry`, `continue`, a skip, `budget_raise`, `terminal_start`, a chat `answer`, `PUT files` | Nothing written | 409 |
| Cancel | Session open | `cancelled`, `senior_session = false` | N/A |
| End, clean | No anchor edit | Released; Run parked on the same stop | N/A |
| End, anchors | A session attempt edited `stories.yaml`; not confirmed | Nothing written | 409 naming it |
| End, confirmed | `confirmed_paths` = every listed edit | Released; record lists them; `accepted_paths` unchanged | N/A |
| End, extra path | Names an unedited file | Nothing written | 422 |
| End, busy | A session attempt has no `ended_at` | Nothing written | 409 `turn running` |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/statuses.py` -- `SignalKind` gains `session_start` and `session_end`, appended in that order. `domain/entities/run.py` -- `senior_session: bool = False`.
- `alembic/versions/{next}_run_senior_session.py`, `infrastructure/db/models/run.py`, `infrastructure/db/repositories/runs.py` -- `BOOLEAN NOT NULL server_default false`, kept out of the frozen `NULLABLE` set. Also `get_for_update`. `domain/ports/repositories.py` -- the port method.
- `application/rules/signals_table.py` (374 lines; predicates move to `rules/session.py` if it would pass 400), `rules/signals.py` -- the two rules, the lock, `SENIOR_SESSION_SIGNALS`.
- `application/rules/session.py` (new, pure) -- `session_attempts(attempts, records)`, `first_shas`, `anchor_edits(changes, anchors)`.
- `application/use_cases/session_checks.py` (new) -- start refusals, plus `anchor_edits` for the end check and the read model. It reuses `SignalPorts.preflight` (registry, Probe) and `SignalEffectPorts.git`/`read_environment`, so `api/providers.py` is unchanged.
- `application/use_cases/signal_effects.py` -- `_session_start`, `_session_end`, and `_cancel`'s flag. `signal_run.py` -- `get_for_update`. `use_cases/signals.py::_refuse_early` -- the call. `run_files.py` -- the refusal.
- `application/use_cases/session_view.py` (new), `api/schemas/session.py`, `api/routers/session.py`, `api/providers_session.py` (new), `main.py` -- `GET /runs/{id}/session`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- `make openapi` only.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_session_lock.py`, `test_session_start.py`, `test_session_end.py`, `tests/unit/test_session_router.py`, `tests/unit/test_run_repository_for_update.py` -- new. Cover every matrix row through the shared fakes, with session attempts seeded in `FakeAttemptRepository`, and see each fail first (TDD).
- [x] The two test edits named under Decided.
- [x] Code Map in order: domain and migration, rules and table, `get_for_update` and `signal_run`, checks and effects, read model and router, then `make openapi`.

**Acceptance Criteria:**
- Given a seeded session attempt on a hub Run whose parked row declares `workdir`, when it edited `repos/m/AGENTS.md` and the hub's `SPEC.md`, then `session_end` names both, spelled as AD-17 spells hits.
- Given an open session, when `GET /runs/{id}` is read, then `admitted_signals` is `["cancel", "session_end"]`, and after `session_end` it is the stop's own set again.
- Given an existing database, when migrations run, then every Run reads `senior_session = false`.

## Implementation Notes

Built tests first at baseline `c4d212b`: the new test files failed on import before any source existed.

**What HEAD already had.** Story 2-1 landed `RunRepository.get_for_update` (port, adapter, shared fake), and `signal_run` already reads the Run through `require_run(..., lock=True)` in all three of its units of work. This story reuses it, so `signal_run.py` and `tests/unit/fakes/runs.py` are unchanged. `test_run_repository_for_update.py` was not written: 2-1's `test_run_lock_adapter.py` covers the adapter's `SELECT … FOR UPDATE`. `test_session_lock.py` asserts that two signals that both passed the unlocked early read serialise on the lock, and that the second one is refused. The migration is `0026_run_senior_session`.

**Where the code went.** `signals_table.py` was at 393 lines, so the session predicates live in the new pure `rules/session.py`. The terminal predicates moved with them, because `terminal_start` now reads both flags (`no_open_session`). The table imports the module and stays at 395 lines. `session_start` is admitted on `paused` (AD-13: `paused` admits `continue`, `cancel` and `session_start`). `session_checks.SessionPorts` carries the writers, the diff port and the registry, and `use_cases/signals.py::session_ports` builds it from `SignalEffectPorts`. `read_environment` is not needed: the Run's spec folder is read from `run.inputs`, as `infrastructure/db/environment.py` reads it. `walk_frame._workdir` became the public `row_workdir`, so the anchor check reads `workdir` exactly as the walker does. `main.py` stays at 400 lines: a four-line comment on the seed re-export became two lines.

**Choices the spec left open.**
- A failing Probe is a 422 on `session_start`, as the spec says. `create_run` answers the same failure with a 409.
- An unknown scope is a 422: `unknown scope {s}: one of story, epic, run`.
- The close checks for a `confirmed_paths` entry that is not an edit (422) before it checks for unconfirmed edits (409).
- A tree contributes changes only when the session recorded a start SHA for it: the dispatch tree needs `start_sha`, and the hub root needs `root_start_sha`.
- A tree whose HEAD cannot be read contributes only its uncommitted files.
- A `session_end` that reaches `signal_run` without `turns` in its payload is refused `turn running`. A caller that skipped the anchor check is refused, not trusted.
- `PUT /runs/{id}/files` answers with the existing `PARKED_REQUIRED` sentence, unchanged.
- The `session_end` record's text names the confirmed files: `senior session ended; confirmed: …`.

**Revised test (rule 1(b), AD-13's 2026-11-01 amendment, story 2-3, 2026-11-02).** `test_run_statuses.py::test_the_signal_kinds_are_the_thirteen_ad_13_names` is now `…_fifteen_…`, and its tuple gains `session_start` and `session_end` after `pause`. No other existing test changed. `test_terminal_signals.py` and `test_signal_rules.py` pass unchanged.

**New test files.** In `application/`: `test_session_lock.py`, `test_session_start.py`, `test_session_end.py`, `test_session_rules.py`, `test_session_view.py`, and the helper `session_fixtures.py`. At the top level: `test_session_router.py` and `test_run_senior_session_storage.py`.

**Gates.**
- `make openapi` regenerated `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; `gen:api --check` reports no drift.
- `make lint` passes.
- `make test` passes: 9020 backend tests (1 skipped) and 1729 web-client tests, with 100% branch coverage on `domain` and `application`.
- `DBOS_APPLICATION_VERSION` is unchanged.
- Not run here: `make e2e`, `make e2e-ui` and `make durability`. The migrations e2e test has therefore not yet applied `0026` to a real database.

## Spec Change Log

- 2026-11-02, lead review. Turns moved to 2-5, and the three open questions were settled there. Five changes were added, each preventing a known-bad state:
  - The row lock, so `session_start` and `terminal_start` can no longer both pass. A stale whole-row write could also revert a cancel.
  - `operator_action = False` on both kinds, which keeps every PRD §4.6 offer test green.
  - The worktree and budget start refusals. Without them a session could open on a Run with no tree.
  - `accepted_paths` left untouched by `session_end`, closing an anchor hole.
  - The busy re-check under the lock, closing a close-versus-message race.
- KEEP: the matrix outcomes and the anchor rule.

## Verification

**Commands:**
- `make lint` and `make test` -- green; coverage unchanged; every new module has a test module.
- `make openapi` -- no drift after regeneration.
- `make e2e` -- green (disposable stack only); the migrations test covers the revision.
