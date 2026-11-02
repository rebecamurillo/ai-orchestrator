---
title: 'Senior consult at a blocked stop'
type: 'feature'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: 'da1c73d99d64d496add4d22ded209c1bf9d0784e'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A `blocked` stop waits for a person even when the question needs no human decision. In the baseline Run, an agent the Operator started by hand answered five delegated stops in minutes. The Run sat parked until someone was awake to start it.

**Approach:** AD-22, on story 1-7's attempt roles. An `agent` row may declare `consult`. When it blocks, it is requeued instead of parked. Its next attempt is a `consult` attempt: a new senior session on `consult.model` that writes a decision file. `answer` resumes the original agent's session in a new `agent` attempt. Every other outcome parks the original `blocked` stop, with the senior's reason added when it gave one.

## Boundaries & Constraints

**Always:** The Run stays `running` and sends no alert during a consult. One consult per row per stop kind, for the life of the row. The senior runs on `consult.harness` (the row's harness by default), in a new session that is never resumed, billed, traced and logged through its own attempt. A consult is offered only when the stopped attempt can be resumed: it has a `session_id`, and the row's harness has `resume`. The decision is read from the file by `rules/consult.py`, never from model output. Fail-closed cases: `escalate`, `accept` (until 1-5), a missing or unreadable decision, a non-zero exit, a stall or a timeout, an unknown harness, no remaining budget (nothing is dispatched), a git or harness error, and any change to either tree's HEAD or status since the offer (the reason names the files). The walker's five steps are unchanged, and `DBOS_APPLICATION_VERSION` is not bumped. A blank `senior_model` plans no consult.

**Never:** No consult on `protected_path` (1-5), `verify_failed` (1-6), `budget`, `checkpoint`, `misconfigured`, `plan_stale`, `dependency`, or an anchor hit. No new Run, Step or park status token. No consult in the `auto` family. No test pins shipped template content. No `.gitignore` of the target repository is edited.

**Decided (lead review, 2026-11-02):**
- *Alphabets:* `consult` and `senior_answer` join `MACHINE_EVENTS`, and `senior` joins `ACTORS`. `test_run_statuses.py::test_the_actors_are_the_three_a_gate_record_can_name` and `test_gate_events.py::test_the_machine_events_are_ad_9s_two_bounded_re_executions` are revised under hard rule 1(b), citing AD-8's and AD-22's 2026-11-01 amendments. The AD-8 amendment declares this exact change. A side alphabet would leave `ACTORS` claiming three actors while records name a fourth. `chat` is story 4-1's.
- *Skill name:* `senior-consult`. The `staged-*` set is pinned at three, and this skill takes no `args`.
- *Decision file:* `{tree}/.orchestrator/consult/{seq:03d}-{n}.decision.md`, where `{tree}` is the dispatch tree. `.orchestrator/` holds a `.gitignore` of `*`, the `_bmad/render/` precedent, so HEAD and status never see it. This is the spine's open-item-7 fallback, used for every harness. It needs no harness branch (AD-10), no OpenCode permission change and no live check before shipping.
- *Clean snapshot:* the offer first sweeps both trees into `wip: story {id} attempt {n} (consult)`. Porcelain status cannot see a further edit to a file the agent left modified. A clean tree makes "HEAD and status unchanged" exact.
- *Orphans:* when `start_attempt` closes an interrupted `consult` attempt, it copies that attempt's `pgid` onto the entry. `agent_consult.run` kills that group before anything else. Accepting the orphan is wrong: the timers lived in the dead backend's `ProcessRunner`, so `timeout_min` bounds nothing.
- *Stopped attempt status:* attempt n closes `error` with reason `consult: {question}`. AD-8's amendment fixes the requeue to `retry`'s `error → queued`, `_close_attempt` writes the result's status, and `retry_auto` already closes a resumable attempt `error`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Answer | `consult {on: [blocked]}`; the agent blocks; the senior writes `status: answer` and a body | Records `consult` (actor `machine`) then `senior_answer` (actor `senior`). Attempt n+2 (`agent`) resumes attempt n's session with `consult.prompts.answer`; `retry_count` is unchanged | N/A |
| Escalate | `status: escalate`, `reason: R` | Park `blocked`, reason = question + ` · senior: R` | N/A |
| No decision | File absent, no frontmatter, unknown status, `accept`, or `answer` with an empty body | Same park, ` · consult failed: no readable decision` | Fail closed |
| Senior crash | Non-zero exit, stall or timeout | Same park, naming the exit or the limit | Fail closed |
| No budget | Remaining budget ≤ 0 when the consult attempt starts | No dispatch; same park, ` · consult failed: no remaining budget` | Fail closed |
| Answer over budget | The consult's own spend exhausts the budget | Park `blocked` (` · senior answered: {first line}`), with the `budget` record on top | N/A |
| Tree touched | HEAD or status differs in either tree | Same park, naming the changed files | Fail closed |
| Sweep fails | Git refuses the offer's WIP commit | No consult; park as today, plus ` · consult failed: {git output}` | Fail closed |
| Blocks again | The resumed agent blocks again | Parks as today; no second consult | N/A |
| Not offered | No `consult`; blank model; not resumable; another stop kind; `budget_park` set | Behaviour as today | N/A |
| Restart mid-consult | Backend killed during the consult attempt | The orphan group is killed, and a new `consult` attempt runs; no second `consult` record | N/A |
| Operator after escalation | `answer`, `mode: session` | Resumes attempt n's session | N/A |
| Validator | `consult` on a non-`agent` row; missing `model`, `skill`, `prompts.dispatch` or `prompts.answer`; an `on` token other than `blocked`; an unknown sub-key | Validation error naming the line | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/statuses.py` -- the two events and the actor. `domain/entities/step_run.py` -- `consults: dict[str, Any] = {}`, mapping a kind to `{state: due|answer|escalate|failed, question, snapshot, answered_by?, orphan_pgid?}`. `domain/values.py` -- `StepResult.consult: Consult | None`. A recorded output without the field still deserializes.
- `alembic/versions/0024_step_run_consults.py` -- `JSONB NOT NULL server_default '{}'`. The column is NOT NULL, so it stays out of the frozen `NULLABLE` set.
- `templates/consult.py` (new), `templates/table.py`, `templates/model.py`, `validate.py::_agent` -- the shape checks. `templates/agent_row.py` -- plans `with_resolved["consult"]` only when the resolved model is non-empty.
- `steps/agent_consult.py` (new) -- `offer` and `run`. `offer(ctx, attempt, final)` turns a qualifying `blocked` park into `status: error` plus `Consult{kind, question, snapshot}`. `run(ctx)` is the consult attempt, in this order: kill the orphan; check the budget; look up the harness; write the `.gitignore`. Then it fills `consult.prompts.dispatch` (`{skill} {spec_folder} {story_id} {condition} {decision}`, scoped by `agent_workdir.prompt_scope`). It runs `mark_started` (no start SHAs), then `start` in a new session (cwd `agent_workdir.tree`, with the root in `add_dirs` on a `workdir` row), then the `pgid` update, `wait`, `mark_finished` and `record_attempt_spend`, all inside the attempt span. It then checks the tree against `snapshot` and reads the decision through the Workspace port. Every error is caught and becomes a park.
- `steps/agent_tail.py::tail` -- passes `_spend_and_budget`'s result through `agent_consult.offer`. `steps/agent.py::execute` -- its first line hands a `consult` attempt to `agent_consult.run`. `steps/agent_workdir.py` -- `_sweep` becomes public with a message parameter.
- `rules/consult.py` (new, pure) -- `parse`, `offered`, `delivers(row, attempts, records)`: the row's latest `senior_answer` while `state = answer` and no `agent` attempt numbered above `answered_by` has an `end_sha`.
- `use_cases/apply_consult.py` (new) -- `apply_step_result._route` calls it first. On an offer, it writes the entry as `due`, records `consult` and requeues through `("error", "retry")` without touching `retry_count`. On a consult attempt's result, it marks the entry. On an answer, it records `senior_answer` with payload `{mode: session, text, kind}`, where `text` is `consult.prompts.answer` filled with `{condition}` = question and `{answer}` = body, sets `answered_by`, and requeues. Requeued results return before `_on_fail`.
- `use_cases/start_attempt.py` -- a `due` entry opens `role="consult"`, and the orphan `pgid` is copied as decided.
- `use_cases/walk_context.py` (new) -- `walk._context` moves here. `resume_signal` is the Operator's record, or else `delivers`'s.
- `preflight/lists.py::installed_skill_lines` -- also checks `consult.skill`.
- `api/schemas/run_views.py` -- `event` and `actor` widen.
- `ia-agents-skills/senior-consult/SKILL.md`, `ia-agents-skills/README.md` -- the skill, plus one line.
- `templates/staged-story.yaml`, `staged-hub-story.yaml` -- `consult` on `plan`, `implement` and `review`, with `answer` worded "from the senior reviewer". `senior_model` (`required: false`) is threaded through `staged-epic`, `staged-hub-epic`, `staged-initiative-repo` and `staged-initiative-hub`.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_consult_*.py` -- new; cover every matrix row through the shared fakes and fixture YAML, seen failing first -- TDD.
- [x] `backend-api/tests/unit/application/test_walk_consult_loop.py` -- new; `next_row` → `attempt_row` → `apply_result` three times over `FakeHarness`, ending in a resumed session.
- [x] `backend-api/tests/unit/test_run_statuses.py`, `tests/unit/test_gate_events.py` -- revise the two named assertions as decided.
- [x] Domain, migration, templates, rules, steps, use cases, preflight, schemas -- per Code Map. Files at the 400-line cap make room by extracting a cohesive function into a new module with its test pair, never by deleting comments.
- [x] `ia-agents-skills/senior-consult/SKILL.md` and `backend-api/tests/unit/test_senior_consult_skill.py` (new). The skill states the architect role ("review and validate the agent's concern against the story's intent"), the SPEC must-escalate list, the decision format (frontmatter `status`, `reason`; the body is the answer), and "change nothing but the decision file". The test asserts each.
- [x] Shipped templates -- per Code Map; validated by the existing loader only.

**Acceptance Criteria:**
- Given a fixture Run whose agent blocks and whose senior answers, when the walk finishes the row, then no `blocked` gate record exists, the Run never left `running`, and the harness received `resume` with attempt n's `session_id`.
- Given a fixture row declaring `on_fail: fail` and a consult, when the agent blocks, then the Run is not `failed` and the next attempt is a `consult`.
- Given an existing database, when migrations run, then every row reads `consults = {}`.

## Design Notes

The snapshot is taken in `offer`, after the sweep, and stored on the entry. A re-run after a crash is therefore compared with what the agent left, not with what the dead senior changed. The answer travels as a real `senior_answer` record, resolved as `resume_signal`. So `_prepare` (moves only), `_planned` (session) and `_session_message` (payload `text`) need no change, and `retrying()` reads `False`. A crash during the resumed attempt itself redispatches fresh, as an Operator session answer does today; the stop that follows parks.

## Verification

**Commands:**
- `make lint` -- expected: passes.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift after generation.
- `make e2e` -- expected: passes; the migrations test covers 0024.

**Manual checks (if no CLI):**
- On the dev stack, the Operator runs one consult each on `claude`, `codex` and `local`, and sees the decision file written. This closes spine open item 7.
- A planned `staged-initiative-repo` Run with `senior_model` set carries `consult` on its three story agent rows; with it blank, none.

## Implementation Notes

- **Decided: trajectory.** AD-19 says the row records the Story's *agent* attempts. `record_trajectory` now lists `agent_attempts(...)` in `attempts` and reads `harness`, `model` and `start_sha` from them, so a senior's session never reads as the trajectory of the agent that built the Story. `cost_usd`, the tokens and `wall_clock_seconds` still sum every role, because AD-21 has spend read every role and the consult is part of what the Story cost. `AttemptRecord` gains no `role`. Where every attempt is `agent`, the row is unchanged. Covered by `test_consult_trajectory.py`.
- **Decided: role on every write.** `start_attempt` always writes `role` explicitly: `consult` while the row's entry is `due`, `agent` otherwise. `agent_consult.run` writes the attempt only through `model_copy` of that entity, so `mark_started`, the `pgid` update and `mark_finished` keep it. `test_consult_start_attempt.py` and `test_consult_run.py` assert the stored role.
- **Decided: orphans.** When `start_attempt` closes an interrupted `consult` attempt, `_hand_over_the_orphan` copies its `pgid`, even `None`, onto the due entry as `orphan_pgid`. `agent_consult.run` kills that group first, before the budget check. `apply_consult` drops `orphan_pgid` when it marks the entry. Covered by `test_consult_start_attempt.py` and `test_consult_run.py::test_an_orphaned_senior_is_killed_before_anything_else`.
- **Decided: the senior's harness.** The offer checks that the *row's* harness can resume, since that is the session the answer goes to. The consult itself runs on `consult.harness`, or the row's harness when that is blank. Stall reads the row's `stall_min`, default 30. The timeout is `consult.timeout_min`, and none means no limit. A tree change is checked first, then a crash, then the decision. Each one fails closed with its own reason.
- **Decided: answer over budget.** The entry is marked `answer` with no `answered_by`, and no `senior_answer` is recorded. The stop parks `blocked` (` · senior answered: {first line}`) with the `budget` record on top. Nothing is delivered later, since `delivers` needs a recorded answer. An escalation or failure over budget gets the `budget` record too.
- **Surprised: `on` is a YAML 1.1 bool.** The bare key `on:` loaded as `True`, so the spine's `consult {on: [...]}` reported an unknown key. `templates/lines.py::LineLoader` now takes an untagged plain-scalar key that resolves to a bool as the text it was written as (see Review Triage 2). Explicit `!!bool` keys, aliases used as values, and all values keep YAML's reading. Values such as `flag: on` stay booleans. No shipped or fixture template had such a key. Covered by `test_consult_template.py::test_a_plain_on_key_is_text_and_a_plain_on_value_stays_a_bool`.
- **Surprised: line caps.** `apply_step_result.py` was at 400. `_redispatch` moved whole to `use_cases/apply_redispatch.py`, which has its own test. `VERIFY_FAILED`, `REDISPATCHED` and `REBASELINE_FAILED` stay reachable from `apply_step_result` (`test_skip_story_admitted.py` imports the last one). To keep ruff's six-return limit, `_route` now ends in one conditional return. `agent.py`'s `_environment`, `_remaining` and `_add_dirs` moved to `steps/agent_env.py`, which the consult reuses. `walk._context` and its helpers moved to `use_cases/walk_context.py`, and `walk.VERIFY_LOG_LINES` stays importable. `agent_tail.py` is still at 400: the hook changed two existing lines and added none.
- **Surprised: no schema edit was needed.** `api/schemas/run_views.py` types `event` and `actor` as `GateEvent` and `Actor`. Widening the two Literals widens the contract. `make openapi` regenerated `contracts/openapi.json` and `schema.d.ts`.
- **Tests revised (rule 1(b)).** `test_run_statuses.py::test_the_actors_are_the_three_a_gate_record_can_name` now pins `senior`. `test_gate_events.py::test_the_machine_events_are_ad_9s_two_bounded_re_executions` now pins `consult` and `senior_answer`. Each edit cites story 1-4, 2026-11-02, and the AD-8/AD-22 amendments of 2026-11-01. No other existing test was edited.
- **Not run.** `make e2e`, `make e2e-ui` and the dev-stack manual checks were not run in this session (out of scope by instruction). The migrations e2e for 0024 and spine open item 7's live check per harness are still open.

## Spec Change Log

- 2026-11-02, lead review: AD-21 split to 1-7. Sweep before the snapshot, orphan kill and the `_on_fail` bypass added (see Decided). Known-bad states avoided: a senior edit to an already-dirty file passing the check; an unbounded orphan; `on_fail: fail` ending an offered Run. KEEP: matrix outcomes, delivery through `resume_signal`.

## Review Triage

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| 1 | A `senior_answer` resume never archived the blocked marker (`agent_answer.answering` accepted `answer` only), so a resumed session that left the marker re-parked on the old question with the consult used. A fresh redispatch after a crash also lost the answer (`compose_prompt` appended `answer` only) | fix | `agent_answer.senior_answering` sits beside `answering`, which is unchanged, so `_session_message` still sends the consult's clause. `archive_with_answer` archives on either, with the senior's text under `## Senior Answer` (`{at} · senior`). `compose_prompt` appends a `senior_answer`'s payload `text`, already the consult's filled `answer` clause, and `halts_after_planning` halts again after one, as after an Operator answer. A marker left untouched now empties the glob, so the stop is FR-16's `no story file` park, the same one an Operator answer reaches. It is not a retry, because that case is never auto-retried (Operator decision 2026-09-20). `test_consult_answer_delivery.py` covers the archive, the session message, the fresh clause, the halt, the untouched-marker loop and crash-then-redispatch, all seen failing first |
| 2 | The loader converted explicitly tagged `!!bool` keys too, and it mutated the key node, so an alias of that key used as a value became text | fix | `LineLoader.construct_mapping` builds pairs one at a time and leaves nodes unmutated. A key is taken as text only when it is an untagged plain scalar that resolves to a bool, which `_bool_text` reads from the source. Merge keys and the unhashable-key refusal are kept. `test_loader_bool_keys.py` covers the explicit tag, the alias, an anchored key, merge, unhashable keys and values |
| 3 | `apply_step_result.py`'s re-export comment narrated the move | fix | Reworded to state why the names are there |
| — | AD-14 window between the senior's `start` and its `pgid` commit (shared with agents) | defer | Coordinator deferred |
