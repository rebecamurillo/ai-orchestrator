---
title: 'Raise budget and Accept a protected-path change'
type: 'feature'
created: '2026-09-09'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred: []
baseline_revision: 'b44152ec8774eefc6ca21fd57740fc674769176e'
---

<intent-contract>

## Intent

**Problem:** Two of AD-13's actions still have no reach. `budget_raise` is refused
`budget_raise not available yet` by `handle_signal`'s scope gate, and its stop has no body
at all — the `budget` park's `admitted_signals` are `("budget_raise", "cancel")`, and
`detail.ts::stopSignals` filters `budget_raise` out (it is not one of `EFFECTIVE_KINDS`), so
an over-budget Run offers the Operator nothing but *Cancel run*. `continue` on a
`protected_path` park is refused the same way, even though 5.6 already built the executor's
whole Accept branch (`agent_tail.re_check`) and `run.accepted_paths` already reaches the
protected-path rule and the trajectory — the branch has no caller because no signal can
reach it.

**Approach:** Widen `use_cases/signals.py::_in_scope` for both (`budget_raise`
unconditionally; `protected_path` joins `CONTINUE_PARK_KINDS`), correct the two writer gaps
the brief names that 4.5 left (`_budget_raise` queues nothing, so a retry-path `error` row
resumes into a stall; the gate record says "budget raised by the operator" rather than
naming the new figure), add the hit-list 409 the Accept needs, publish `alert.payload` and a
`?diff=1` mode on `GET /runs/{id}/files`, and give the two stops the bodies UX-DR10
specifies.

## Boundaries & Constraints

**Always:**
- AD-13 stays the authority on validity. `VALID["budget_raise"]`/`VALID["continue"]` already
  carry the right park kinds and `extra` predicates (4.5) — the only change to
  `rules/signals.py::VALID` is the two record *sentences* the brief pins, which no existing
  test asserts (`test_signal_rules.py` covers `record_text` for `answer` and `retry` only).
- AD-8's two writers stay the two writers. The Run's status still moves in
  `signal_run::_apply`; `_budget_raise` only widens what it hands back.
- `agent_tail.py`'s `tail` order is frozen (`"5.6" < "route(" < "5.7"`, FR-31) and is not
  touched. `re_check` already exists, already excludes `run.accepted_paths`, and already
  runs no dispatch — this story only gives it a caller by admitting the signal.
- The `diff` mode is a **mode on the existing `GET`**, not a third operation:
  `test_run_files_router.py::test_the_router_declares_exactly_the_two_operations` stays true.
- Module cap 400: `agent_tail.py` is at exactly 400 and must not grow (it does not need to);
  `api/schemas/run_views.py` is at 382 and `StopBody.tsx` at 270 — check both after edits and
  split along a real seam if either is pushed over.
- New coverage goes in new test files; `tests/unit/fakes/` is the sole additive exception
  (`FakeGit.diff`).

**Block If:** — **TRIGGERED, see `## Auto Run Result`.** Any assertion in an existing test
file other than the two operator-named pending-gate registry rows would have to change.
Specifically: `backend-api/tests/unit/application/test_handle_signal.py::
test_continue_on_protected_path_is_refused_not_available_yet` (added by story 4-9, so it
predates this branch and is not one of the two named registries) asserts that a `continue`
on a `protected_path` park raises `Conflict("continue not available yet")` — which is
exactly the gate this story lands. HALT and report rather than self-authorise.

**Never:**
- Do not implement, test, or shape the terminal path (`terminal_start`, `terminal_release`,
  `terminal_resume`, `resume_command`, the poll) — story 6-7 owns it, and story 6-1's guess
  at 6-2's behaviour already cost this epic a halt.
- Do not widen `stopSignals`/`hasEffect`/`EFFECTIVE_KINDS`, `blockedSignals`/
  `BLOCKED_EXTRA_KINDS` or `checkpointSignals`/`CHECKPOINT_EXTRA_KINDS` — all frozen. Both
  new controls are their own components (the `AnswerBox`/`ConfirmAction` precedent), so
  neither needs a filter widened.
- Do not touch `test_signals_router.py::test_a_kind_outside_this_epics_scope_is_a_409_not_
  available_yet`: its vehicle is `terminal_start`, which this story does not land.
- Do not fix the Epic-7 gaps (`pgid` on a resumed dispatch, `Harness.resume`'s arguments).
  The Accept path resumes the tail with **no dispatch**, so neither is on this path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Raise over a `blocked` row | `budget` park, row `blocked`, `budget_raise {budget_usd: 60}` | `run.budget_usd == 60`, `park_kind == "blocked"`, Run stays `needs_you`, no `engine.signal`, record `budget raised to $60.00` | — |
| Raise over a `checkpoint` row | same, row `checkpoint` | `park_kind == "checkpoint"`, Run stays `needs_you` | — |
| Raise over a `done` row | `budget` park, row `done` | Run `running`, the frame's next unfinished row (`verify`) `queued` | — |
| Raise over an `error` row | `budget` park, row `error` (retry path) | row `queued`, Run `running` | — |
| Raise over a run-level park | `park_path is None` | Run `running`, walker starts the plan | — |
| Raise at or below spend | `budget_usd: 30`, `spend_usd: 41.20` | nothing written | 409 `new budget must exceed spend $41.20` |
| Accept the exact hits | `protected_path` park, hits `[tests/a.py ~, AGENTS.md +]`, `continue {files: [tests/a.py, AGENTS.md]}` | `accepted_paths` holds both, row `error → running`, record `continue` with `payload.files` and text `accepted: tests/a.py, AGENTS.md`, no harness call | — |
| Accept a list that is not the hits | `files: [tests/a.py]` (or `[]`, or a superset) | nothing written | 409 naming the recorded hits |
| Diff one hit | `GET …/files?path=AGENTS.md&diff=1` | unified diff of `start_sha .. worktree` for that path | 403 for a path that is not a recorded hit; 422 for an escaping path; 404 for an unknown Run |
| Protected-path body | `alert.payload.hits` present | one row per file with its `+ − ~`, a diff link each, the accept line, *Accept changes* | — |
| Budget body | `budget` park | banner `BLK · budget $41.20 / $40.00`, the cost kv, a numeric field pre-filled `spend + 10` rounded, *Raise budget*, *Cancel run*, no skips | — |

</intent-contract>

## Code Map

**Backend — the scope gate (both halves).**
- `application/use_cases/signals.py::_in_scope` (line ~72) — the tuple gains `"budget_raise"`;
  `CONTINUE_PARK_KINDS` (line ~57) gains `"protected_path"`. The module docstring's "refuses
  four of AD-13's ten kinds" paragraph is corrected to the three terminal kinds.
- `tests/unit/application/test_handle_signal.py` — the `budget_raise` parametrize row and its
  `ids` entry (lines ~233, ~239) may go under the operator's exception (a).
  **`test_continue_on_protected_path_is_refused_not_available_yet` (lines 197-206) may not** —
  see Block If.
- `tests/unit/application/test_answer_signal_scope.py` (lines ~92-99) — its registry holds
  exactly one row, `budget_raise`. Removing it empties the list, so the whole
  `test_the_kinds_this_story_did_not_land_still_answer_not_available_yet` function goes with
  it (an empty `parametrize` collects as a skipped placeholder, which asserts nothing).

**Backend — `budget_raise`'s two writer gaps (verified against the brief, 4.5 left both).**
- `application/use_cases/signal_effects.py::_budget_raise` (line ~205) — correct today for the
  `blocked`/`checkpoint` hold (`park_kind` rewritten to the row's status, `resume=False`).
  **Missing:** it queues nothing. A `done` row happens to work by accident —
  `walk.py::_start_the_plan` queues the first `planned` row because every row is then in
  `STARTABLE` — but an `error` row is in none of `first_queued`/`_resumed_in_place`/
  `STARTABLE`, so `next_row` answers `None` and `close_run` parks `internal`, a stop that
  admits only `cancel`. Fix: `Effect(run_update=update, finished=not resume_from(ports, row))`
  for the non-held case, which is `resume_from`'s own documented rule ("the parked row is the
  first candidate") — a `done` parked row is stepped over to the verify row, an `error` one is
  re-queued (`error → retry → queued`). `park_row is None` (a run-level park) keeps today's
  bare `Effect(run_update=update)`. The frozen `test_signal_run.py::test_a_budget_raise_on_a_
  row_that_kept_its_routed_status_resumes_the_run` asserts only budget/status/engine, so it
  stays true.
- `application/rules/signals.py` — `Rule.text` is `"budget raised by the operator"`; the brief
  pins `budget raised to ${new}`. Add `Rule.text_from: Callable[[dict], str | None] | None`,
  consulted by `record_text` before `text_key` and falling through on `None`; two named
  builders (`_budget_raised_text` → `BUDGET_RAISED.format(...)` off `raised_budget`, always
  present because `validate` ran first; `_accepted_text` → `ACCEPTED.format(paths=…)` off
  `accepted_files`, `None` for a checkpoint `continue`, which keeps `"continued by the
  operator"`). Also `Rule.extra_refusal: str | None`, used by `validate` when `extra` alone
  refuses, so `budget_raise` gets `BUDGET_TOO_LOW = "new budget must exceed spend ${spend}"`
  (`:.2f`, `rules/budget.py::forced`'s own convention) while a wrong park keeps `INVALID`.
  `test_signal_rules.py`'s budget refusals assert `pytest.raises(Conflict)` bare, so they stay
  true.

**Backend — the Accept's 409 and the hit list.**
- `application/rules/signals.py` — `HITS_KEY = "hits"`/`HIT_PATH_KEY = "path"` move here (one
  definition; `steps/agent_tail.py:101` re-binds `HITS_KEY` from here so its public name and
  the `rules ← steps` direction both hold), plus two pure functions: `park_payload(records,
  run)` (the last `GateRecord` whose `event == run.park_kind`, its `payload`) and
  `hit_paths(payload)`.
- `application/use_cases/signals.py` — a second refusal beside `_refuse_out_of_scope`:
  on `kind == "continue"` and `park_kind == "protected_path"`, compare
  `accepted_files(signal.payload)` against `hit_paths(park_payload(ports.signal.writers.
  records.list_for_run(run_id), run))` and raise `Conflict(ACCEPT_MISMATCH.format(hits=…))`
  when they differ as sets. `WriterPorts.records` is already on the ports — no new port.
- `application/steps/git_commit.py` (line ~68) — the commit-guard's own `protected_path`
  `StepResult` carries **no** `payload`, so that park records no structured hit list at all.
  Add `payload={HITS_KEY: [{HIT_PATH_KEY: p} for p in hits]}` (no `kind`: `ProtectedPaths.
  check` returns paths only and its member set is frozen by `test_run_environment.py`), so
  every `protected_path` park is acceptable. `test_git_commit_executor.py` asserts field by
  field, not by equality, so it stays true.

**Backend — the read model.**
- `application/use_cases/run_view_types.py::Alert` — `payload: dict[str, Any] =
  field(default_factory=dict)`, defaulted so every existing `Alert(...)` construction keeps
  compiling (`skipped_epics`' own precedent, 6.5).
- `application/use_cases/run_views_alert.py::build_alert` — one more keyword, `records`, and
  `payload=park_payload(records, run)`. `run_views.py::run_detail` already reads
  `ports.gate_records.list_for_run(run.id)` (line 202) — pass that same list into `_alert`
  rather than reading twice.
- `api/schemas/run_views.py::AlertOut` (382/400) — `payload: dict[str, Any] =
  Field(default_factory=dict, json_schema_extra=_drop_default)` plus one line in `.of()`.
  `dict[str, Any]`, not a typed `HitOut`: it is `GateRecord.payload`'s own type, and the four
  lines it costs are what keeps this module under the cap.

**Backend — the `diff` mode.**
- `domain/ports/git.py::Git` — `diff(self, worktree: Path, from_sha: str, path: str) -> str`
  ("the unified diff of one path between `from_sha` and the worktree as it stands"), beside
  `diff_names`/`diff_changes`.
- `infrastructure/git/subprocess_git.py` — `git diff {from_sha} -- {path}`.
- `tests/unit/fakes/git.py` — one more optional `diff` kwarg, one script entry, one method
  (additive; the fakes exception).
- `application/use_cases/run_files.py` (245 lines) — `RunFilesDiffPorts(runs, steps, attempts,
  records, git)` and `diff_run_file(ports, run_id, path) -> RunFileDiff(path, from_sha, diff)`.
  Refusal order mirrors `read_run_file`: 404 unknown Run → 422 `_escapes(path)` → **403 when
  `path` is not one of `hit_paths(park_payload(...))`** → 404 when the parked row has no
  attempt with a `start_sha`. The scope check is deliberately *not* `_within_spec_folder`:
  every anchor AD-17 protects (`AGENTS.md` anywhere, every frozen test file) is outside the
  spec folder by construction, so that gate would refuse exactly the paths this mode exists
  to show. The recorded hit list is a tighter scope than the spec folder, not a wider one —
  it is the Run's own record of what it is asking the Operator to judge. `_escapes` is reused
  unchanged.
- `api/schemas/run_files.py` — `RunFileDiffOut{path, from_sha, diff}`.
- `api/routers/run_files.py` — `get_file` gains `diff: Annotated[bool, Query()] = False`;
  `response_model` becomes `RunFileOut | RunFilesTreeOut | RunFileDiffOut`; the module
  docstring's "stays at exactly `GET` and `PUT`" paragraph gains the mode. Route count
  unchanged.
- `api/providers.py` (312/400) — `run_files_diff_ports`, the same `with SQLAlchemyUnitOfWork`
  shape `run_files_write_ports` uses, `git=_required_git(request, "run_files")`.

**Frontend.**
- `src/lib/run/budget.ts` (new, pure) — `BUDGET_RAISE_LABEL = 'Raise budget'`,
  `prefilledBudget(cost)` (`spend + 10`, rounded — see Design Notes), `budgetRaiseBody(value)`
  → `{kind: 'budget_raise', payload: {budget_usd: value}}`, `offersBudgetRaise(kind, admitted)`.
- `src/lib/run/accept.ts` (new, pure) — `ProtectedHit{path, kind}`, `protectedHits(alert)`
  (defensive read of `alert.payload.hits`, the `misconfiguredFiles` precedent),
  `hitMark(kind)` (`added → +`, `deleted → −`, anything else → `~`), `diffHref(runId, path)`
  (`/runs/{id}/files?path=…&diff=1`), `ACCEPT_LABEL = 'Accept changes'`,
  `acceptLine(storyId)` (verbatim: `Accept records these files as accepted for story {id};
  the check resumes on the same tree and the files ship with the story`),
  `acceptBody(paths)` → `{kind: 'continue', payload: {files}}`,
  `offersAccept(detail, kind)`.
- `src/components/run/BudgetRaiseBox.tsx` (new) — the cost kv line, `<input type="number"
  data-testid="wf-budget-raise-input">`, primary `wf-budget-raise`. Owns its own input state,
  the `AnswerBox` precedent; `StopBody` stays stateless.
- `src/components/run/AcceptBox.tsx` (new) — the `<ul data-testid="wf-accept-files">` of
  `{mark} {path}` rows each with an `<a>` to `diffHref`, the accept line, primary `wf-accept`.
  No `dangerouslySetInnerHTML`.
- `src/components/run/StopBody.tsx` (270 lines) — render `BudgetRaiseBox` for
  `kind === 'budget'` and `AcceptBox` for `kind === 'protected_path'`; on the
  `protected_path` body only, drop `'continue'` out of the rendered button row (the
  `AcceptBox` is that action). No filter is widened: `budget_raise` is not in
  `EFFECTIVE_KINDS` and never enters `signals`. Existing `protected_path` assertions
  (`run-stop-body-skip.test.ts`, `run-stop-body-skip-epic.test.ts`) never list `continue` in
  `admitted_signals`, and every `wf-signal-continue` assertion anywhere is on a `plan_stale`
  or `checkpoint` body, so all stay true.
- `src/islands/RunDetail.tsx` — two more callbacks through the payload-carrying `sendSignal`
  6.1 added (`onRaiseBudget`, `onAccept`), the `onAnswer` precedent exactly.
- `src/styles/run-detail.css` — additive `.wf-budget*`/`.wf-accept*` at the end.

**E2E (backend, on the fake harness — no fixture change needed).**
`tests/e2e/test_budget_raise.py`: create the gates Run with `budget_usd: "0.005"`. Story 1's
`attempt-1.yaml` costs `0.01` and routes `blocked`, so the Run parks `blocked` and
`budget_second_record` rewrites `park_kind` to `budget` on a **`blocked`** row — AC1 end to
end. Raise to `"0.02"`: `park_kind` is `blocked` again, the Run is still `needs_you`, the
Question body is back. Answer; `attempt-2.yaml` costs `0.02`, routes `done`, spend `0.03`
exceeds `0.02`, so the Run parks `budget` on a **`done`** row. Raise to `"0.50"`: the Run
reaches `running` and the frame's `verify` row starts — AC2 end to end.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/application/rules/signals.py` -- `Rule.text_from`/
  `Rule.extra_refusal`, `BUDGET_RAISED`/`BUDGET_TOO_LOW`/`ACCEPTED`, `HITS_KEY`/
  `HIT_PATH_KEY`, `park_payload`/`hit_paths` -- the table stays the one place a signal's
  sentence and its refusal are written.
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py` -- `_budget_raise`
  resumes through `resume_from` -- a retry-path `error` row otherwise resumes into a stall.
- `backend-api/src/orchestrator/application/use_cases/signals.py` -- `budget_raise` joins
  `_in_scope`, `protected_path` joins `CONTINUE_PARK_KINDS`, the accept's hit-list 409 --
  the two kinds AD-13 admits finally have an effect to reach.
- `backend-api/src/orchestrator/application/steps/git_commit.py` -- the protected park
  records its hit list -- otherwise a commit-guard park can never be accepted.
- `backend-api/src/orchestrator/application/steps/agent_tail.py` -- re-bind `HITS_KEY` from
  `rules/signals.py` -- one definition, and the module stays at 400.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py`,
  `run_views_alert.py`, `run_views.py`, `api/schemas/run_views.py` -- `Alert.payload` and its
  wire projection -- the body needs the hits and their kinds.
- `backend-api/src/orchestrator/domain/ports/git.py`,
  `infrastructure/git/subprocess_git.py`, `tests/unit/fakes/git.py` -- `Git.diff` -- the
  unified diff the file list links to.
- `backend-api/src/orchestrator/application/use_cases/run_files.py`,
  `api/schemas/run_files.py`, `api/routers/run_files.py`, `api/providers.py` -- the `diff`
  mode -- a mode on the existing `GET`, never a third operation.
- `backend-api/tests/unit/application/test_handle_signal.py`,
  `test_answer_signal_scope.py` -- remove the `budget_raise` registry rows -- the gate has
  landed. **(The third pending-gate assertion in the first file is the Block If.)**
- New backend test files, one concern each: `tests/unit/application/
  test_budget_raise_signal.py`, `test_budget_raise_resume.py`, `test_accept_protected_path_
  signal.py`, `test_signal_record_sentences.py`, `test_run_views_alert_payload.py`,
  `tests/unit/test_run_files_diff.py`, `tests/unit/test_run_files_diff_router.py`,
  `tests/unit/test_git_port_diff.py`, `tests/e2e/test_budget_raise.py`.
- `web-client/src/lib/run/{budget,accept}.ts`, `src/components/run/{BudgetRaiseBox,
  AcceptBox}.tsx`, `src/components/run/StopBody.tsx`, `src/islands/RunDetail.tsx`,
  `src/styles/run-detail.css` -- the two bodies.
- New frontend test files: `tests/unit/run-budget-lib.test.ts`,
  `tests/unit/run-accept-lib.test.ts`, `tests/unit/run-stop-body-budget.test.ts`,
  `tests/unit/run-stop-body-protected-path.test.ts`,
  `tests/e2e/run-detail-accept.spec.ts`.
- `make openapi` -- regenerate: `AlertOut.payload` and `RunFileDiffOut` are new wire shapes.

**Acceptance Criteria:** the brief's own five (verbatim,
`briefs/6-6-raise-budget-and-accept.md`) govern; implement exactly as written there.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why the `diff` mode is scoped to the recorded hits, not to the spec folder.** The operator's
hand-off says to reuse `read_run_file`'s scope and escape checks. `_escapes` is reused as is.
`_within_spec_folder` cannot be: AD-17's anchors are `AGENTS.md` *anywhere* and every frozen
test file (`rules/protected_paths.py::build`/`check`), so every path the protected-path body
links to is outside the Run's spec folder by construction and would 403. The honest
alternative is not to widen the scope but to *narrow* it differently: the path must be one of
the hits this Run's own park recorded. That is strictly tighter than "any file in the
worktree" and is derived from state the Run wrote itself.

**Why the hit list needed `git_commit.py` to change too.** `agent_tail.protected` returns
`payload={"hits": [{"path", "kind"}]}`, which `apply_step_result::_park` carries onto the
gate record. `GitCommitExecutor` returns the same park kind with no payload at all — so a
commit-guard `protected_path` park had no machine-readable hit list, and the brief's "`files`
must equal the hit list" would have had to be parsed out of the reason sentence for that
half. One `payload=` on that `StepResult` makes both halves the same read. No `kind` is
invented for those hits: `ProtectedPaths.check` answers paths only and its member set is
frozen, so the body shows `~` for a hit with no kind.

**Why `Rule.text_from` rather than formatting `Rule.text`.** `record_text(rule, payload)`
would have to `.format(**payload)` a template with the operator's own dict — fine for our own
templates but it would print the raw payload value (`"60"`), where the brief pins the
*validated* figure (`$60.00`). A named builder per rule is the same shape `Rule.extra`
already is, and it lets `continue` answer `accepted: a, b` for an Accept while keeping
`continued by the operator` for a checkpoint Continue, which one template string cannot.

**`prefilledBudget` — the brief's own `[ASSUMPTION]`.** "pre-filled with `spend + 10`
rounded". Resolved as `Math.ceil(spend + 10)` rendered with two decimals: a ceiling can never
land at or below the spend (a floor could, for a spend under $1), so the pre-filled value is
always one `validate` would admit. Stated here because the brief marks it open.

**The retry-path `error` resume — the brief's second `[ASSUMPTION]`.** "a retry-path error
under budget resumes as a retry when the budget is raised". Resolved by `resume_from`, whose
own docstring already says the parked row is the first candidate: it re-queues an `error` row
(`error → retry`) and steps over a `done` one. One line covers both rows the brief describes
separately, and it is the same call `_skip_story`/`_skip_epic`/`_terminal_resume` already
make.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain/application strict), import-linter (4
  contracts), env contract, test pairs, `gen:api --check`, eslint, prettier, `tsc --noEmit`,
  astro check all clean.
- `make test` -- expected: backend + web unit suites green; `domain/` + `application/` hold
  **100 %** branch coverage, including every new branch in `_budget_raise`, the accept
  refusal, `park_payload`/`hit_paths` and `diff_run_file`.
- `make openapi` -- expected: `contracts/openapi.json`/`schema.d.ts` regenerate with
  `AlertOut.payload` and `RunFileDiffOut`; `gen:api --check` clean afterward.
- `make e2e` -- expected: green on the disposable stack (`ORCH_TEST_MODE=1`), including
  `test_budget_raise.py`.
- `make e2e-ui` -- expected: green. The two Epic-5 PNGs under
  `_bmad-output/implementation-artifacts/epic-5-screens/` are regenerated by story 5.10's
  anchor spec; commit the new bytes.

## Auto Run Result

Status: blocked

**Blocking condition:** anchor conflict — `backend-api/tests/unit/application/
test_handle_signal.py::test_continue_on_protected_path_is_refused_not_available_yet`.

Planning is complete (see the Code Map above; it is the whole investigation, so a resumed
dispatch needs no re-survey). Implementation did not start: the story cannot be built without
invalidating one assertion in an existing test file that is not covered by any exception the
operator granted.

**The conflict.**

| | |
|---|---|
| File | `backend-api/tests/unit/application/test_handle_signal.py` |
| Test | `test_continue_on_protected_path_is_refused_not_available_yet` (lines 197-206) |
| Landed by | story 4-9 (`8ad015e`), Epic 4 — it predates this branch |
| Assertion | `with pytest.raises(Conflict, match="continue not available yet"): send(world, ports, "continue")` on `parked("protected_path", COMMIT_GUARD, "error")`, then `world.status_of(COMMIT_GUARD) == "error"` and `world.engine.calls == []` |

**Why it is unavoidable.** This story's own brief requires `continue` on a `protected_path`
park to reach its effect. The only gate is `use_cases/signals.py::_in_scope`, and admitting
that pair is what makes the test's `Conflict` stop being raised. Three alternatives were
swept and all rejected:

1. *Leave `_in_scope` alone.* Removes half the story (the brief's `continue`-on-
   `protected_path` scope, FR-31, and the entire Accept path).
2. *Admit it only when the payload carries `files`, so a payload-less `continue` still reads
   `continue not available yet`.* The refusal would then lie: the action **is** available and
   the caller sent no files. It is also the "route around it" the operator forbade, and it
   fails NFR-8 ("copy names the mechanism").
3. *Put the hit-list check in `rules/signals.py::validate` instead, so the refusal is AD-13's
   own `INVALID` text.* `match="continue not available yet"` still fails, and it would put
   gate-record state inside a table keyed on `(status, park_kind, row kind/status)`.

**The minimal edit requested.** Delete the whole test function (lines 197-206) — it is a
pending-gate assertion for a gate this story lands, structurally identical to the
`budget_raise` registry row eleven lines below it that the operator already pre-authorised;
its `world` builds no protected-path record, so there is nothing in it but the refusal.
Nothing else in the file changes beyond the authorised `budget_raise` row. Strictly-exceeding
coverage lands in the same commit in a new file,
`tests/unit/application/test_accept_protected_path_signal.py`: the Accept applying through
`handle_signal` on an agent-row park (accepted paths recorded, row `error → running`, the
record carrying `payload.files`), the same on a commit-guard-row park, the mismatched-list
409, the empty-list 409, and `world.engine.calls` in each case.

Nothing was written to the repository: the working tree is clean at `b44152e` and no gate was
run, because there is nothing yet to run one against.
