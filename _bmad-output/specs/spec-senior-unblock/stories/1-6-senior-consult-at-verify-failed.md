---
title: 'Senior consult at verify_failed'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'a11b1dfa1a010d9ca1abc5d58022474c20651d7d'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A `verify` row that keeps failing parks `verify failed {n}/{n}` once the template's redispatches are used up, and waits for a person. Most of those failures have a cause an implementer can fix once someone reads the output and the agent's log.

**Approach:** AD-22 on story 1-4's consult machinery. A `run` row's `on_fail` may declare `consult` beside `redispatch` and `max`. When the redispatch bound is used up, the redispatch target is queued for a `consult` attempt instead of the Run parking. The senior diagnoses the failure and writes a decision file. `answer` is a diagnosis. It goes into ONE further fresh redispatch of the target, beside the failure text, in a new session (AD-10). Every other outcome parks `verify_failed` with the senior's reason added. The next `verify_failed` parks for a person.

## Boundaries & Constraints

**Always:** The Run stays `running` and sends no alert during the consult. One consult per row per stop kind, for the life of the row: the entry is written on the **redispatch target** (`step_run.consults["verify_failed"]`), so a second `verify_failed` finds it and parks whatever the consult came to. The consult attempt belongs to the target, the `agent` row with the harness, the model, the `workdir` and the story's tree. The `run` row keeps its `error` status and its park path, so *Retry* still re-queues the gate. The senior runs on `consult.harness` (the target's harness by default) in a new session that is never resumed, billed, traced and logged through its own attempt. The decision is read from the file by `rules/consult.py`, never from model output. `answer` is a diagnosis; `escalate`, `accept`, a missing or unreadable decision, a non-zero exit, a stall or timeout, an unknown harness, no remaining budget, a git or harness error and any change to either tree's HEAD or status since the offer fail closed to the `verify_failed` park, with the reason named. The walker's five steps are unchanged, and `DBOS_APPLICATION_VERSION` is not bumped. A blank `senior_model` plans no consult.

**Never:** No consult below the bound, on a skipped target, on any other stop kind, in the `auto` family, or twice. No new Run, Step or park status token. No new gate event or actor. The diagnosis never resumes a session and never travels as a `resume_signal`. No test pins shipped template content.

**Decided (lead brief, 2026-11-02):**
- *Where the senior runs:* on the redispatch target. The verify row is a `shell` row: it has no harness, no model and no session history. The offer marks the target's entry, so "one consult per row per stop kind" holds per Story frame, and the target returns to `done` when the consult fails closed.
- *The block travels with the entry.* The target declares no `consult` for this stop; the verify row does. The offer copies the planned block onto the entry (`declared`), with the verify row's path (`park_path`), and `agent_consult.run` runs on it.
- *The offer is made by `apply_redispatch`, where the bound is decided,* not by an executor: the `shell` executor does not see the target's counter. `verify_consult.offer` writes rows only: the entry `due` with the block and the park path, and the target requeued. The sweep and the snapshot are git work and belong to the engine step that runs an executor (AD-8, AD-22; review ruling 2026-11-02): the target's first consult attempt finds an entry with no snapshot, takes exactly the snapshot 1-4 takes, and returns it as an offer. `apply_consult` merges it into the entry, records `consult` once, and requeues. The next attempt is the senior's.
- *What the senior is given:* the dispatch clause fills the existing tokens plus `{command}`, `{code}`, `{tail}` (`VerifyFailure`, as the walker resolved it) and `{agent_log}`, the tail of the target's last `agent` attempt's log, read through the `LogReader` port as `{tail}` is, never a path. `{condition}` is the park's own reason (`verify failed n/n`). The story context is `{spec_folder}` and `{story_id}`.
- *How the diagnosis reaches the redispatch:* `VerifyFailure.diagnosis`, filled by `walk_context` while the row still owes it (`rules.consult.diagnosis`). `redispatch_clause` appends it after the row's `redispatch` clause, unfilled, so the existing redispatch path (`redispatched(ctx)`, a `start`, a new session id) carries both. A row with no clause is still told it. A dispatch a crash interrupted before it came back tells both again.
- *The count:* the answer counts as one further redispatch (`redispatch_count + 1`), so the park after it reads `verify failed n/n` with the true total, and the bound stays used up.
- *The consult attempt closes `error` on an answer or a snapshot offer* (AD-8's `retry` pair requeues the target) *and on any outcome that parks.* The target row returns to `done`, the status it had before the offer. The park names the verify row, and its gate record carries no attempt number, since the attempt is another row's.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Offer | `on_fail {redispatch: implement, max: 2, consult}`; verify fails; `implement.redispatch_count` = 2; no entry | Entry `due` with the block and park path, no snapshot; `implement` queued; Run `running`; verify row stays `error`; no git, no record yet. Its first consult attempt sweeps and snapshots both trees, `consult` is recorded once (actor `machine`, on `implement`), and the entry gains the snapshot | N/A |
| Answer | Senior writes `status: answer` and a body | `senior_answer` (actor `senior`, no `mode`) with the filled `answer` clause; `redispatch_count` 3; `implement` requeued; its next attempt is a fresh `agent` dispatch whose prompt holds the redispatch clause then the diagnosis | N/A |
| After the diagnosis | The redispatched `implement` finishes; verify fails again | Park `verify_failed` on the verify row, `verify failed 4/4`; no second consult | N/A |
| After the diagnosis, passing | Verify passes | The Run continues | N/A |
| Escalate | `status: escalate`, `reason: R` | Entry `escalate`; `implement` back to `done`; park `verify_failed` on the verify row, reason `verify failed n/n · senior: R` | N/A |
| No decision | File absent, no frontmatter, unknown status, `accept`, or `answer` with an empty body | Same park, ` · consult failed: no readable decision` | Fail closed |
| Senior crash | Non-zero exit, stall or timeout | Same park, naming the exit or the limit | Fail closed |
| No budget | Remaining budget ≤ 0 when the consult attempt starts | No dispatch; same park, ` · consult failed: no remaining budget` | Fail closed |
| Answer over budget | The consult's own spend exhausts the budget | Park `verify_failed` (` · senior answered: {first line}`) with the `budget` record on top | N/A |
| Tree touched | HEAD or status differs in either tree | Same park, naming the changed files | Fail closed |
| Sweep fails | Git refuses the snapshot attempt's WIP commit | No senior; park `verify_failed`, ` · consult failed: {git output}` | Fail closed |
| Sweep raises otherwise | An exception that is not git's own | The registry parks `internal`; the Run does not stay `running` | N/A |
| Not offered | No `consult` on `on_fail`; blank model; entry already present; target skipped; below the bound | Behaviour as today | N/A |
| Restart mid-consult | Backend killed during the snapshot or the senior attempt | The orphan group is killed and a new `consult` attempt runs; a replayed snapshot step finds a clean tree and commits nothing; one `consult` record | N/A |
| Validator | `consult` on `on_fail` of a non-`shell` row; missing `model`, `skill` or `prompts.dispatch`; `on` other than `[verify_failed]`; an unknown sub-key | Validation error naming the line | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `application/templates/on_fail.py` (new) -- `check_on_fail` moves out of `keys.py` (at 394 lines) and learns the optional `consult` key; `parse_redispatch_consult`. `templates/consult.py::check_consult` and `parse_consult` take the stop list, the required keys and the implied `on`. `templates/table.py`, `model.py::Step.redispatch_consult`, `validate.py`.
- `application/templates/rows.py::_routing`, `plan_model.py::Redispatched.consult`, `plan.py::_routed` -- the planned block rides in `with_resolved["on_fail"]["consult"]` only when the senior model resolves non-empty. The shell executor reads the two keys it always read.
- `application/rules/consult.py` -- `verify_block`, `block_of`, `diagnosis`; `answer_text` takes the entry; `delivers` skips the `verify_failed` kind; the placeholder set gains `command`, `code`, `tail`, `agent_log`.
- `application/use_cases/verify_consult.py` (new) -- `offer(ports, sender, target, exhausted)`, rows only. `apply_redispatch.py` calls it at the bound and reports `verify failed {count + 1}`. `apply_consult.py` -- an offer merges into the entry, a `verify_failed` answer is recorded without `mode` and counts one redispatch, and `attempt_status` closes a parked consult attempt `error`. `apply_step_result._park` gives a stop another row owns no attempt number.
- `application/steps/agent_consult.py` -- `_Stop.block`; `_snapshotted` is the first attempt (sweep, snapshot, offer; git's refusal parks, anything else reaches the registry); `_failure` supplies the four tokens, `{agent_log}` through `LogReader`; `_parked` returns `done` and the entry's `park_path` for this kind.
- `application/steps/verify_failure.py` (new) -- `VerifyFailure` moves out of `context.py` (at 398 lines) and gains `diagnosis`. `agent_prompt.redispatch_clause`, `agent.py::_sent_back`. `use_cases/walk_context.py` fills the diagnosis.
- `application/preflight/lists.py::_row_skills` -- also checks the skill of an `on_fail` consult on any row.
- `ia-agents-skills/senior-consult/SKILL.md`, `ia-agents-skills/README.md` -- the second stop.
- `templates/staged-story.yaml`, `staged-hub-story.yaml` -- `consult` on the `verify` row's `on_fail`, on `senior_model`.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/templates/test_on_fail_consult.py` -- new; shape, parse, plan.
- [x] `backend-api/tests/unit/application/test_verify_consult{,_rules,_apply,_run,_walk_context,_preflight}.py` and `steps/test_agent_verify_diagnosis.py` -- new; every matrix row through the shared fakes, seen failing first.
- [x] `backend-api/tests/unit/application/test_walk_verify_consult_loop.py` -- new; `next_row` → `attempt_row` → `apply_result` over the real `agent` and `shell` executors and `FakeHarness`, from the first failure to the park.
- [x] `backend-api/tests/unit/test_senior_consult_verify_skill.py` -- new.
- [x] Code, skill and shipped templates per the Code Map. No existing test was edited.

**Acceptance Criteria:**
- Given a fixture Run whose verify fails past the template's bound and whose senior answers, when the walk finishes, then the Run never left `running`, the diagnosis was told in a `start` with a new session id and no `resume` was called, and a passing verify finishes the Run.
- Given the same Run where verify fails again, then the Run parks `verify_failed` on the verify row and no second consult record exists.
- Given a verify row declaring no consult, then the walk and the park are as before.

## Design Notes

The snapshot is taken by the first consult attempt and stored on the entry before any senior runs, so a senior that crashes after editing is compared with what the agent left, not absorbed into a later baseline (1-4's lead review). A replay of that first step finds the swept tree clean, commits nothing, and takes the same snapshot; the `consult` record is written by the writer once per applied offer.

A consult that fails closed returns the target to `done`, not `blocked` or `error`: its work was finished before the gate failed, and the graph should not show a stuck Story when the stop is the gate's.

## Verification

**Commands:**
- `make lint` -- expected: passes.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift (no schema changed).
- `make e2e` -- expected: passes.

**Manual checks (if no CLI):**
- On the dev stack, a `staged-initiative-repo` Run with `senior_model` set and a deliberately failing unit test: after two redispatches the `implement` row shows two `consult` attempts (snapshot, senior), then a fifth `agent` attempt; the next failure parks. With `senior_model` blank, the park comes after the second redispatch as before.

## Implementation Notes

- **Gates.** `make lint` passes. `make test` passes with 8576 backend and 1711 web-client tests, and `domain` and `application` at 100% branch coverage. `make openapi` was not needed: no schema changed.
- **Not run.** `make e2e`, `make e2e-ui` and the dev-stack manual checks were not run (out of scope by instruction).
- **Known limit.** A crash during the diagnosed redispatch's own attempt redispatches fresh and tells the failure and the diagnosis again, through `_sent_back`. A crash after that attempt came back (its `end_sha` written) no longer owes the diagnosis, as in 1-4.
- **Existing tests.** None edited. `agent_prompt.redispatch_clause`, `delivers`, `answer_text`, `check_consult` and `parse_consult` keep their old call shapes through defaults.

## Spec Change Log

- 2026-11-02, brief: consult attempt on the redispatch target, offer in `apply_redispatch`, diagnosis through `VerifyFailure`. KEEP: 1-4's machinery reused, no walker change.
- 2026-11-02, review: git work moved out of the writer into the target's first consult attempt (Decided, Code Map, matrix). Known-bad states avoided: a transaction open across git calls; a Run left `running` by a non-git exception. KEEP: one consult per row per stop kind, marked on the target.

## Review Triage

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| 1 | `verify_consult.offer` ran `sweep_trees` and `head_sha`/`status` inside `apply_step_result`'s open unit of work, in the walker's separate apply step: a git exception that was not `GitError` escaped the writer and left the Run `running`, and the transaction stayed open across git calls | fix | `offer` writes the entry `due` (block, park path) and requeues the target, nothing else. `agent_consult.run` finds no snapshot, sweeps and snapshots in the executor, and returns an offer; `apply_consult._offered` merges it into the entry and records `consult`. Git's own refusal parks with its words; any other exception reaches the registry's `internal` park. Covered by `test_verify_consult.py`, `test_verify_consult_run.py`, `test_verify_consult_apply.py` and the loop test |
| 2 | The `verify_failed` record carried the target's attempt number against the verify row's path, and a consult that parked closed its attempt `done` | fix | `_park` gives a stop on another row's path no attempt number. `apply_consult.attempt_status` closes a parked `verify_failed` consult attempt `error`; the target row still returns to `done` |
| 3 | `{log}` handed the senior a raw path under the log volume, outside `add_dirs` and unscrubbed | fix | Replaced by `{agent_log}`: the last 200 lines of the target's last agent log through `LogReader.tail`, as `{tail}` is read. Templates and skill reworded |
| 4 | `verify_consult.py` docstring narrated history ("park exactly as before") | fix | Reworded to state the rule |
| 5 | No test for a non-`GitError` during the sweep, nor for a replayed step | fix | `test_a_failure_that_is_not_git_s_reaches_the_registry_as_an_internal_park`, `test_a_replayed_executor_step_sweeps_once_and_answers_the_same_snapshot` and `test_a_replayed_snapshot_step_sweeps_once_and_records_one_consult` |
