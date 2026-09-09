---
status: blocked
---

# Continue and Reject at checkpoints

## Auto Run Result

Status: blocked
Blocking condition: anchor conflict — a frozen assertion landed by story 6-1 forbids the
exact prompt behavior this story's brief requires for Reject at a spec checkpoint.

### The conflict

- **File:** `backend-api/tests/unit/application/steps/test_agent_answer_dispatch.py`
  (committed by 6-1 at `a48e13d`, clean on disk — a genuine anchor, not a scratch file).
- **Test:** `test_a_spec_checkpoint_answer_quotes_spec_rejected_and_does_not_halt_again`
  (lines 127-135).
- **Assertions (lines 134-135):**
  ```python
  assert prompt.endswith(f'blocking condition "spec rejected": {ANSWER}')
  assert "Halt after planning." not in prompt
  ```
  built over `an_answered_world(spec_checkpoint=True)`, whose `resume` is
  `a_gate_record(row, "answer", {ANSWER_KEY: ANSWER})` — i.e. exactly the scenario this
  story's brief calls Reject: an `answer` signal on an agent row with `spec_checkpoint`
  true. The `.endswith(...)` assertion pins the composed prompt to end at the Answer
  clause, with nothing after it; the second assertion says the same thing again by name.

- **What the brief requires (`briefs/6-2-continue-and-reject-at-checkpoints.md`), verbatim:**
  - Binding rule: *"Reject with a reason... the story is re-planned with the reason (and,
    because `spec_checkpoint` is still true, the re-plan halts again at the checkpoint)."*
  - Acceptance criterion:
    > **Given** the same Run
    > **When** `answer {text: "split the endpoint in two"}` is signalled
    > **Then** the file is archived with the reason, the prompt suffix reads `Answer from
    > the operator to the blocking condition "spec rejected": split the endpoint in two`
    > **followed by** ` Halt after planning.`, and the record has `answer`.

  `compose_prompt` (`backend-api/src/orchestrator/application/steps/agent.py:152-178`)
  is pure over `with_resolved`/`resume_signal`; today its `HALT` clause
  (line 173-174) is gated on `resume_signal is None` only, which already matches the
  frozen test (no halt on any resume). Making the brief's AC pass requires the halt
  clause to *also* fire when `resume_signal.event == ANSWER_EVENT` **and**
  `with_resolved.get(SPEC_CHECKPOINT_KEY)` — which appends `" Halt after planning."`
  after the Answer clause on exactly the case the frozen test builds, breaking both of
  its assertions. There is no accepted-equivalent phrasing that satisfies both: the
  brief pins the literal trailing string, and the frozen test asserts nothing may follow
  the Answer clause at all.

### Why no honest alternative was found

I swept for one before concluding this (per the epic's standing rules): there is no
additive design — every implementation of "append ` Halt after planning.` after the
Answer clause on a spec-checkpoint Reject" is, by construction, an implementation that
makes `prompt.endswith(f'blocking condition "spec rejected": {ANSWER}')` false. The two
requirements are the literal negation of each other over the identical scenario.

### The minimal edit, if the operator authorises it

In `test_agent_answer_dispatch.py`:
- Rename `test_a_spec_checkpoint_answer_quotes_spec_rejected_and_does_not_halt_again` to
  reflect the corrected behavior (e.g.
  `test_a_spec_checkpoint_answer_quotes_spec_rejected_and_halts_again`).
- Replace line 134's `.endswith(...)` with
  `.endswith(f'blocking condition "spec rejected": {ANSWER} Halt after planning.')`.
- Delete line 135's `assert "Halt after planning." not in prompt`.
- Update the docstring (currently "the clause is the one difference") to state the halt
  also differs.

This is not self-authorised here: two anchor edits were granted to story 6-1 for its own
named lines only, and the epic's standing rules are explicit that they do not extend to
this story. No code was changed; the working tree is otherwise exactly as this story's
dispatch found it (no scratch files).

### Everything else investigated, for whoever picks this back up

- **Continue on a `checkpoint`-status agent row** (re-dispatch without halt, new
  session): already fully implemented by 6-1/4.9 —
  `agent.py:173-174`'s existing gate, `_planned` (`agent.py:326-336`, new `session_id`
  whenever no Template `retry:` resumes one), `signal_effects.py:155-170 _continue`. Only
  a fresh unit test asserting the AC's specific "attempt 2, new session, gate record has
  `continue`" combination was outstanding — trivial once unblocked.
- **`GET /runs/{id}/files`**: does not exist yet. The brief places it in
  `api/routers/runs.py`, but that router carries its own frozen route-count test
  (`tests/unit/test_runs_router.py::test_the_router_declares_exactly_the_two_operations`,
  pinned to `GET`/`POST /runs/preflight` only) — adding a third operation there breaks
  it. The honest alternative, precedented twice already (`run_detail.py`, `signals.py`,
  both split from `run.py`/`runs.py` for the identical reason, with the reasoning spelled
  out in their own docstrings): a new sibling router module, e.g.
  `api/routers/run_files.py`, mounted in `main.py:293`'s tuple. `Workspace.read` already
  exists on the port (`domain/ports/workspace.py:34-36`); `FsWorkspace._reject_escape`
  (`infrastructure/workspace/fs.py:96-100`) already refuses `..`/absolute paths — the
  natural 422. A 403 for "well-formed but outside `{spec_folder}`" has no existing
  vocabulary (`domain/errors.py` has `NotFound`/`Conflict`/`Invalid` only); the idiomatic
  fix is a new `Forbidden(DomainError)` plus a `DOMAIN_STATUS` row in `api/errors.py`
  (`Invalid` already maps to 422, so the malformed-path case is free).
- **`Alert.row_kind`** (spec- vs done-checkpoint body dispatch): missing from
  `application/use_cases/run_view_types.py:138-143` (`Alert`) and
  `api/schemas/run_views.py:164-179` (`AlertOut`); `run_detail()`
  (`application/use_cases/run_views.py:213-235`) already computes `park_row.kind` for
  `admitted_signals` and just needs to thread it into `_alert(...)` too. **Blocker for
  that specific edit:** `application/use_cases/run_views.py` is at exactly 400/400 lines
  (the repo's hard cap, `tests/unit/test_source_limits.py`) with zero headroom, so the
  field cannot land without a split. The clean seam (mirrors 6-1's
  `agent.py → agent_answer.py`, and `run_views.py`'s own precedent of splitting
  `board_view` schemas into `api/schemas/board_view.py`): pull `_run_token`,
  `_attribution`, `_alert` into a new `application/use_cases/run_views_alert.py`
  (no test imports these private helpers directly — confirmed by grep — so this is a
  safe, non-anchor move) and re-export/call from `run_views.py`, freeing ~35 lines.
- **Web-client** `StopBody.tsx` (173/300-line convention cap, plenty of room): the
  existing frozen `tests/unit/run-stop-body.test.ts` `StopBody · checkpoint` case (uses
  no `alert.row_kind`, expects `wf-stop-checkpoint` + literal `'story checkpoint'` text +
  `wf-signal-continue`) is **not** in conflict — it can stay satisfied by keeping the
  existing generic banner/reason paragraph unconditionally and adding the spec-/done-
  checkpoint-specific bodies as additional, `row_kind`-gated content, same pattern 6.1
  used for the Answer box (additive, no edit to that test). `continue` itself is already
  fully wired client-side (`src/lib/run/detail.ts::EFFECTIVE_KINDS`/`stopSignals`,
  `RunDetail.tsx`'s `sendSignal`) — only the Reject textarea (model on
  `AnswerBox.tsx`, needs a new reveal-toggle state it doesn't have) and the two new
  checkpoint bodies are net-new. `GET /runs/{id}/files` has no existing inline viewer to
  reuse cleanly; closest precedent is `QuestionBlock.tsx`'s markdown block renderer (no
  `dangerouslySetInnerHTML`).

No code was written or modified for this story. `git status` is clean except this one
new planning artifact.
