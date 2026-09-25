---
date: 2026-09-25
verdict: accepted-with-open-items
criteria: declared
headless: false
---

# Retrospective — Step handling: skip, resume, cancel

**Spec folder:** `_bmad-output/specs/spec-step-handling`  
**Stories:** 1 – 5 (all done)  
**Range:** `f8b99093..18418b52`  
**Date:** 2026-09-25

---

## Epic summary

**Spec:** `SPEC.md` — 6 declared capabilities (CAP-1 through CAP-6), each with explicit success criteria. AD-13 ratified same day (2026-09-25) for `skip_step`; AD-10 amended same day for local resume.

**Stories completed:** 5 of 5

| # | Title | Status | Baseline commit | Final commit |
|---|-------|--------|-----------------|--------------|
| 1 | Skip one step | done | `f8b99093` | `4729fa74` |
| 2 | Cancel a Run while it is running | done | `4729fa74` | `6b130348` |
| 3 | The local harness resumes an OpenCode session | done | `6b130348` | `876a1f63` |
| 4 | Retry carries the operator's instruction and resumes by default | done | `876a1f63` | `2726e3ef` |
| 5 | The step-run page shows attempts as a table | done | `2726e3ef` | `18418b52` |

**Diff range:** `f8b99093..18418b52` — 8 commits (0 merges), 50 files changed. Note: one commit (`7695c1ee wip: story 1 attempt 2 (interrupted)`) is an aborted session within story 1's range; it matched both `"1"` and `"2"` in `git_evidence.py`'s word-boundary scan (false positive for story 2 attribution). Evidence from the story 2 artifact and commit subjects confirms it belongs to story 1 only.

**Evidence inventory:**

| Item | Available | Notes |
|------|-----------|-------|
| SPEC.md | ✓ | Declared success criteria per CAP |
| stories.yaml | ✓ | 5 stories in list order, all done |
| Story artifacts 1–5 | ✓ | All `status: done`, review triage logs present |
| Git diff range | ✓ | Established from story baseline revisions |
| Sprint status | — | Stories mode; no sprint-status.yaml |
| Previous retro | — | No prior retro for this epic |
| Session logs | partial | One wip commit (`7695c1ee`) evidences a retried story 1; no conversation logs |
| E2E test summary | ✓ | `_bmad-output/implementation-artifacts/tests/test-summary.md` (generated 2026-09-25, re-verified same day) |

**Missing evidence:** Session logs absent; process-lesson analysis (why story 1 needed a retry) is based on the wip commit alone, not a session record.

---

## Findings

### Aggregate views

#### Architecture delta

All six capabilities respected the declared architectural constraints throughout the epic.

- **AD-2 (layering):** `domain/` and `application/` acquired no new infrastructure imports. `import-linter` passed at every story's `make lint`. Evidence: story 1–5 verification sections.
- **AD-8 (status writers):** `signal_run` is the sole status writer across all three new signal kinds. No executor, router, or island acquired a status derivation.
- **AD-13 ratification:** The `skip_step` row was written into the spine and dated `2026-09-25` in the same change as the domain code — per the constraint. No silent addition.
- **AD-10 amendment:** `LocalHarness` docstring updated from `**There is no resume**` to `**Resume** (AD-10 amended 2026-09-25)`. The invocation lives only in `adapter.py` — AD-10 holds.

New structural elements introduced:
- `web-client/src/components/run/AttemptsTable.tsx` — new stateless component; `AttemptDetail` type ownership moved here from `StepDetail.tsx`. Clean extraction, consistent with `StepsTable.tsx` pattern.
- `web-client/src/lib/run/skip.ts` additions (`SKIP_STEP_LABEL`, `skipStepConfirmLine`, `offersSkipStep`) — follows existing `offersSkipStory`/`offersSkipEpic` pattern exactly.
- `run_view_types.py` new field `resume_unavailable_reason: str | None = None` — proper addition in the application view-type dataclass, mapped through the full serialization stack.

**Source:** `git_evidence.py` file listing; story artifact Code Map sections.

#### Duplication map

One documented duplication introduced across the epic:

- **`reply_available` computed in two places:** `_check_mode` (signal_run.py, story 4) and `_reply_status` (run_views.py, story 4) each compute the same three-part condition (attempt, session_id, harness). Acknowledged in story 4 Design Notes as intentional minimal change; a shared helper was deferred (story 4 deferred item #2, low). No duplication visible between other stories.

**Source:** story 4 deferred item #2; `backend-api/src/orchestrator/application/use_cases/signal_run.py:172-194`, `run_views.py`.

#### God-class / size growth

Files with highest net churn ranked (non-merge commits only):

| File | Added | Deleted | Net | Commits |
|------|-------|---------|-----|---------|
| `stories/4-retry-…md` | 255 | 0 | +255 | 1 |
| `stories/1-skip-…md` | 197 | 2 | +195 | 2 |
| `web-client/tests/unit/run-stop-body-skip-step.test.ts` | 150 | 3 | +147 | 2 |
| `web-client/tests/unit/run-stop-body-cancel.test.ts` | 103 | 0 | +103 | 1 |
| `web-client/tests/unit/attempt-table.test.ts` | 119 | 0 | +119 | 1 |
| `web-client/src/components/run/AttemptsTable.tsx` | 127 | 0 | +127 | 1 |
| `backend-api/tests/unit/test_local_adapter.py` | 109 | 28 | +81 | 2 |
| `web-client/src/components/run/StopBody.tsx` | 52 | 9 | +43 | 3 |

The spec artifacts' churn is expected (new documents). Production-code candidates: `AttemptsTable.tsx` (+127 net, new component — 127 lines is healthy for a table component). `StopBody.tsx` is the only production file touched by three separate stories; it grew by +43 lines but remains well within a healthy size. No god-class growth.

**Source:** `git_evidence.py` files output.

#### Pattern divergence

No meaningful divergence found. Specific confirmations:

- `signalLabel('skip_step')` placed after `skip_epic` in signals.ts — semantic grouping with other `skip_*` kinds. Story 1 review corrected an initial ordering that broke the grouping. Source: story 1 Review Triage Log, low patch.
- `AttemptsTable.tsx` follows `StepsTable.tsx` house pattern: `data-selected` on `<tr>`, signal-colour on token span only, CSS scoped under a hand-scoped class. Source: story 5 intent-contract Constraints.
- `RetryBox` receives `resumeUnavailableReason` as a prop (not computed internally) — consistent with other server-knowledge props in the component tree. Source: story 4 Design Notes.
- React key uses `attempt.id` (UUIDv7) not `attempt.n`. Story 5 review caught a `key={attempt.n}` and corrected it to `key={attempt.id}`. Source: story 5 Review Triage Log, low patch.

One minor inconsistency: `StopBody.tsx` comment style uses mixed tenses across the stories' additions, reflecting three separate authoring sessions. No functional impact.

#### Spec-to-implementation reconciliation

All six CAPs were implemented and their declared success criteria met:

| CAP | Success criterion met | Evidence |
|-----|-----------------------|----------|
| CAP-1 | `POST skip_step` marks row skipped, returns run to running, writes gate_record with `actor: operator` | story 1 acceptance tests, `make test` passed |
| CAP-2 | Retry carries `text` into resumed session or restart prompt | story 4 acceptance tests, `_session_message` fix |
| CAP-3 | Absent mode defaults to session when `reply_available`; control states reason when it cannot | story 4 acceptance tests, `_check_mode` fix |
| CAP-4 | `LocalHarness.capabilities.resume is True`; `resume()` passes `--session {id}` | story 3 acceptance tests, adapter tests |
| CAP-5 | Running Run renders Cancel; confirming posts cancel | story 2 acceptance tests |
| CAP-6 | Attempt history renders as aligned table; no run-on text | story 5 acceptance tests |

Three SPEC constraints that deserved explicit verification:

1. **`skip_step` excluded from dependency parks (SPEC constraint 1):** `run_admitted_signals` returns early for dependency before reaching `admitted_signals`, so `skip_step` is never offered there. Tested via story 1's `test_a_skip_step_on_a_dependency_park_is_refused`. The coarse `admitted_signals` function *would* include `skip_step` for dependency (it's in `ANY_PARK`), but `run_admitted_signals` short-circuits first. This is correct but the coarse path is untested — carried forward as deferred (story 1 deferred item #1, low).

2. **Resume flag is `--session` only, never `--continue` or `--fork` (SPEC constraint):** Story 3 added exact argv equality assertion after review; `_resume_argv` is pinned with `==` list check. Source: story 3 Review Triage Log, low patch.

3. **`signal.payload` mutation in `_check_mode` (story 4 design):** The gate record captures the computed default because `_planned` reads `ctx.resume_signal.payload.get("mode")` after the mutation. This is intentional and documented in Design Notes. The test `test_absent_mode_defaults_to_session_when_reply_available` pins it.

**One divergence noted:** The SPEC Assumptions section says "Retry's park kinds exclude `blocked`" — this is still the current constraint (the code has not changed this). The epic did not touch `blocked`'s retry admission. Confirmed correct: CAP-2 and CAP-3 apply to all parks where `retry` is admitted; the spec does not extend retry to `blocked` stops.

### Diff-scope review

Reviewing boundaries between stories — where no single session saw both sides:

**Story 1 → Story 2 boundary (StopBody.tsx):**
Story 1 added skip_step to the signals chain via `withSkipEpic`. Story 2 changed the `if (kind === null) return null` early return. The two changes don't interact: story 2's new null-kind cancel path returns before reaching the signals chain. No conflict at the boundary. The `const signals` naming was correctly chained through `withSkipEpic` by story 1 before story 2 touched the file.

**Story 3 → Story 4 boundary (reply_available):**
Story 3 flipped `LocalHarness.capabilities.resume = True`. Story 4 changed `_check_mode` to default to `"session"` when `reply_available=True`. This is an intended composed effect: after story 3, local Runs *are* reply_available when a session is recorded, so story 4's default correctly applies to them. The composition works and is covered by `test_absent_mode_defaults_to_session_when_reply_available`.

**Story 4 → Story 5 boundary:** No interaction — story 5 is purely frontend (AttemptsTable), story 4 is application+frontend (RetryBox, signal logic). Clean.

**Cross-story: `contracts/openapi.json` and `schema.d.ts` touched by stories 1 and 4:**
Story 1 added `skip_step` to `SignalIn.kind` enum; story 4 added `resume_unavailable_reason` to `RunDetailOut`. Both ran `make openapi` after their respective backend changes. The generated file was not hand-edited (AGENTS.md hard rule 3). Confirmed: each story's `make openapi` round-trip is its own self-consistent commit. Source: stories 1 and 4 verification sections.

**Serialization layer gap (patched, story 4):**
The story 4 review found that `_omit_false_reply_available` had no `model_dump()` test, so a mutant unconditionally popping `resume_unavailable_reason` would pass all application-layer tests. Three serialization tests were added. This was the high-severity patch that triggered `followup_review_recommended: true`. Source: story 4 Review Triage Log, high patch.

**React key correctness (patched, story 5):**
Story 5 review corrected `key={attempt.n}` to `key={attempt.id}`. Using a sequence number as a React key causes unnecessary re-renders when the list changes order (newest-first re-renders on retry). The fix is committed. Source: story 5 Review Triage Log, low patch.

### Session log gaps

One wip commit exists (`7695c1ee wip: story 1 attempt 2 (interrupted)`) indicating story 1 needed an aborted attempt before the final commit. No session log is available to reconstruct what was tried and abandoned. Process-lesson analysis for story 1 is therefore limited to what the artifact records: the spec was sound (spec-gate passed before dispatch), so the retry most likely reflects a tooling or environment issue rather than a spec defect.

---

## Behavior verification

Runtime behavior was **not** exercised end to end during this retrospective. The following gate results were reported in story artifacts:

- `make lint` — passed at stories 1, 2, 3, 4, 5
- `make test` — passed at all stories; 7295 (baseline) → 7309 backend tests, 1723 → 1740 frontend tests; 100% branch coverage on `domain/` and `application/` maintained throughout
- `make openapi` — ran at stories 1 and 4; regenerated `contracts/openapi.json` and `schema.d.ts` without drift

The test-summary.md (`_bmad-output/implementation-artifacts/tests/test-summary.md`, generated and re-verified 2026-09-25) generated e2e tests for CAP-1, CAP-2/3, CAP-5, and CAP-6 and cross-checked all testid/selector values against the current source. The generated tests have not yet been run via `make e2e` or `make e2e-ui`.

**Untested at runtime:** the composed effect of CAP-3 + CAP-4 (local Run stops showing resume as default); workspace state after skip_step on push_rejected/merge_conflict; the actual `opencode run --session` process path.

---

## Previous-retro follow-through

No prior retrospective exists for this project. Nothing to follow through on.

---

## Action items

| # | Finding | Action | Owner | Priority |
|---|---------|--------|-------|----------|
| 1 | Keyboard accessibility regression on attempt rows (story 5, medium deferred) | Add `tabIndex={0}` and `onKeyDown` (Enter/Space) to `<tr>` rows in `AttemptsTable.tsx`; add unit assertions | Rebecam | medium |
| 2 | Workspace state after skip_step on push_rejected/merge_conflict is untested (story 1, medium deferred) | Write integration test or document the expected walker behavior for each bad-park skip scenario; determine whether cleanup is needed | Rebecam | medium |
| 3 | Run the generated e2e tests (test-summary.md) | Execute `make e2e-api` (for `test_skip_step.py`) and `make e2e-ui` (for the four Playwright specs) against the running stack | Operator | high (verification) |
| 4 | Unquoted `cwd` in `resume_command` output (story 3, low deferred) | Replace `f"cd {cwd} && …"` with `f"cd {shlex.quote(str(cwd))} && …"` in `adapter.py`; update the test assertion | Rebecam | low |
| 5 | Duplicate `reply_available` logic in `_check_mode` and `_reply_status` (story 4, low deferred) | Extract a shared `_compute_reply_available(ports, run) -> bool` helper in `signal_run.py`; import in `run_views.py` | Rebecam | low |
| 6 | `StopBody.tsx` is a three-story hotspot (composite finding) | No immediate action. Monitor: if story 6+ touches it again, consider extracting the skip-button group and the cancel-path into focused sub-components before the file degrades | Rebecam | watch |

Process lessons:

- **Review found a critical serialization gap (story 4).** The `resume_unavailable_reason` field was added with application-layer tests but no `model_dump()` assertion. A concrete mutant (unconditionally pop the field) passed all tests until the review added three serialization tests. Lesson: when a new field is added to a Pydantic schema with a custom serializer that pops it conditionally, add a `model_dump()` test that checks *both* the present and absent cases, in the same commit as the field.

- **One story retry (story 1).** The wip commit suggests the first dispatch did not complete cleanly. No session log survives, so the cause is unknown. No spec change was required. Lesson: session log retention would make this diagnosable in future retros.

---

## Acceptance verdict

**Verdict: accepted-with-open-items**  
**Criteria: declared** (SPEC.md states explicit success criteria per CAP; all 6 met)

**Evidence:**

All five stories reached `done`. All six capability success criteria are met per their story acceptance test results and `make test`/`make lint` gate passes at each story. Branch coverage was maintained at 100% on `domain/` and `application/` throughout. The three hard architectural constraints that this epic most directly tested (AD-2, AD-8, AD-13) hold in the committed code.

**Open items that do not block acceptance:**

- Medium: keyboard accessibility on attempt rows (story 5, action item #1)
- Medium: workspace state after skip on push_rejected/merge_conflict (story 1, action item #2)
- High-verification: e2e tests written and cross-checked but not yet run (action item #3)

None of these block the capability deliverables. The two medium deferred items are usability gaps in delivered functionality, not broken functionality. Action item #3 is a verification gap, not an implementation gap.

---

## Open questions

1. **Should workspace cleanup be added to `_skip_step` for push_rejected/merge_conflict parks?** The current code does no git operations on skip; the walker is responsible for its own setup. Whether the walker's setup handles these cases is untested. Answer determines whether action item #2 is a documentation task or a code change.

2. **Was the story 1 retry caused by a harness/environment issue or a spec issue?** Without session logs the cause is unknown. The spec was sound (gate passed). If environment-caused, worth checking whether the environment is more stable now.

3. **Should `StopBody.tsx` be refactored before the next epic touches it?** It has been modified by 3 of 5 stories in this epic. Action item #6 flags this for monitoring.
