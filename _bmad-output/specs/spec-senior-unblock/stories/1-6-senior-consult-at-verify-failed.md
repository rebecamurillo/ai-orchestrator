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
- *The offer is made by `apply_redispatch`, where the bound is decided,* not by an executor: the `shell` executor does not see the target's counter. `verify_consult.offer` takes the clean snapshot there through the `Git` port (WIP sweep of both trees, then HEAD and status), exactly the snapshot 1-4 takes, stored on the entry.
- *What the senior is given:* the dispatch clause fills the existing tokens plus `{command}`, `{code}`, `{tail}` (`VerifyFailure`, as the walker resolved it) and `{log}`, the target's last `agent` attempt's log path. `{condition}` is the park's own reason (`verify failed n/n`). The story context is `{spec_folder}` and `{story_id}`.
- *How the diagnosis reaches the redispatch:* `VerifyFailure.diagnosis`, filled by `walk_context` while the row still owes it (`rules.consult.diagnosis`). `redispatch_clause` appends it after the row's `redispatch` clause, unfilled, so the existing redispatch path (`redispatched(ctx)`, a `start`, a new session id) carries both. A row with no clause is still told it. A dispatch a crash interrupted before it came back tells both again.
- *The count:* the answer counts as one further redispatch (`redispatch_count + 1`), so the park after it reads `verify failed n/n` with the true total, and the bound stays used up.
- *The consult attempt closes `error` on an answer* (AD-8's `retry` pair requeues the target) *and `done` on any other outcome,* which returns the target to the status it had before the offer. The park names the verify row.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Offer | `on_fail {redispatch: implement, max: 2, consult}`; verify fails; `implement.redispatch_count` = 2; no entry | Trees swept and snapshotted; `consult` recorded (actor `machine`, on `implement`); entry `due`; `implement` queued; Run `running`; verify row stays `error` | N/A |
| Answer | Senior writes `status: answer` and a body | `senior_answer` (actor `senior`, no `mode`) with the filled `answer` clause; `redispatch_count` 3; `implement` requeued; its next attempt is a fresh `agent` dispatch whose prompt holds the redispatch clause then the diagnosis | N/A |
| After the diagnosis | The redispatched `implement` finishes; verify fails again | Park `verify_failed` on the verify row, `verify failed 4/4`; no second consult | N/A |
| After the diagnosis, passing | Verify passes | The Run continues | N/A |
| Escalate | `status: escalate`, `reason: R` | Entry `escalate`; `implement` back to `done`; park `verify_failed` on the verify row, reason `verify failed n/n · senior: R` | N/A |
| No decision | File absent, no frontmatter, unknown status, `accept`, or `answer` with an empty body | Same park, ` · consult failed: no readable decision` | Fail closed |
| Senior crash | Non-zero exit, stall or timeout | Same park, naming the exit or the limit | Fail closed |
| No budget | Remaining budget ≤ 0 when the consult attempt starts | No dispatch; same park, ` · consult failed: no remaining budget` | Fail closed |
| Answer over budget | The consult's own spend exhausts the budget | Park `verify_failed` (` · senior answered: {first line}`) with the `budget` record on top | N/A |
| Tree touched | HEAD or status differs in either tree | Same park, naming the changed files | Fail closed |
| Sweep fails | Git refuses the offer's WIP commit | No consult; the ordinary park, plus ` · consult failed: {git output}` | Fail closed |
| Not offered | No `consult` on `on_fail`; blank model; entry already present; target skipped; below the bound; no git port or worktree | Behaviour as today | N/A |
| Restart mid-consult | Backend killed during the consult attempt | The orphan group is killed and a new `consult` attempt runs; no second `consult` record | N/A |
| Validator | `consult` on `on_fail` of a non-`shell` row; missing `model`, `skill` or `prompts.dispatch`; `on` other than `[verify_failed]`; an unknown sub-key | Validation error naming the line | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `application/templates/on_fail.py` (new) -- `check_on_fail` moves out of `keys.py` (at 394 lines) and learns the optional `consult` key; `parse_redispatch_consult`. `templates/consult.py::check_consult` and `parse_consult` take the stop list, the required keys and the implied `on`. `templates/table.py`, `model.py::Step.redispatch_consult`, `validate.py`.
- `application/templates/rows.py::_routing`, `plan_model.py::Redispatched.consult`, `plan.py::_routed` -- the planned block rides in `with_resolved["on_fail"]["consult"]` only when the senior model resolves non-empty. The shell executor reads the two keys it always read.
- `application/rules/consult.py` -- `verify_block`, `block_of`, `diagnosis`; `answer_text` takes the entry; `delivers` skips the `verify_failed` kind; the placeholder set gains `command`, `code`, `tail`, `log`.
- `application/use_cases/verify_consult.py` (new) -- `offer(ports, run, sender, target, exhausted)`. `apply_redispatch.py` calls it at the bound and reports `verify failed {count + 1}`. `apply_consult.py` -- a `verify_failed` answer is recorded without `mode` and counts one redispatch.
- `application/steps/agent_consult.py` -- `_Stop.block`; `_failure` supplies the four tokens; `_parked` returns `done` and the entry's `park_path` for this kind. `agent_consult_tree.snapshot_trees` and `agent_workdir.sweep_trees` / `declared_in` take the git port and paths instead of a `StepContext`.
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

The offer needs `ports.git` and `run.worktree_path`; the walker's `open_ports` scope carries the first (`startup.py`), and a scope without either simply offers nothing. The sweep runs inside `apply_step_result`'s unit of work, as `record_trajectory`'s git reads already do. The alternative, taking the snapshot at the start of the consult attempt, would let a senior that crashed after editing be absorbed into the next attempt's baseline, which is the state 1-4's lead review ruled out.

A consult that fails closed returns the target to `done`, not `blocked` or `error`: its work was finished before the gate failed, and the graph should not show a stuck Story when the stop is the gate's.

## Verification

**Commands:**
- `make lint` -- expected: passes.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift (no schema changed).
- `make e2e` -- expected: passes.

**Manual checks (if no CLI):**
- On the dev stack, a `staged-initiative-repo` Run with `senior_model` set and a deliberately failing unit test: after two redispatches the `implement` row shows a `consult` attempt, then a fourth `agent` attempt; the next failure parks. With `senior_model` blank, the park comes after the second redispatch as before.

## Implementation Notes

- **Gates.** `make lint` passes. `make test` passes with 8576 backend and 1711 web-client tests, and `domain` and `application` at 100% branch coverage. `make openapi` was not needed: no schema changed.
- **Not run.** `make e2e`, `make e2e-ui` and the dev-stack manual checks were not run (out of scope by instruction).
- **Known limit.** A crash during the diagnosed redispatch's own attempt redispatches fresh and tells the failure and the diagnosis again, through `_sent_back`. A crash after that attempt came back (its `end_sha` written) no longer owes the diagnosis, as in 1-4.
- **Existing tests.** None edited. `agent_prompt.redispatch_clause`, `delivers`, `answer_text`, `check_consult` and `parse_consult` keep their old call shapes through defaults.

## Spec Change Log

- 2026-11-02, brief: consult attempt on the redispatch target, offer in `apply_redispatch`, diagnosis through `VerifyFailure`. KEEP: 1-4's machinery reused, no walker change.

## Review Triage

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| — | None yet | — | — |
