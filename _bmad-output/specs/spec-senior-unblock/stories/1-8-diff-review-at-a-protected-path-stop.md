---
title: 'Diff review at a protected_path stop'
type: 'feature'
created: '2026-11-02'
status: 'ready-for-dev'
route: 'dispatch'
baseline_commit: 'a11b1dfa1a010d9ca1abc5d58022474c20651d7d'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** An agent edits a frozen test because the story requires it. AD-17 then parks `protected_path`, and the Run waits for the Operator's `continue`. In the baseline Run, test edits the story already implied cost 19h43 of waiting.

**Approach:** This is the second half of CAP-2, under hard rule 1 (amended 2026-11-02) and AD-17's amendment, built on story 1-5. A row that declares `consult {on: [blocked, protected_path]}` sends a hit on tests only to a senior. The senior reads the real diff, then accepts or escalates. An `accept` has the effect of the Operator's `continue`: the hits enter `accepted_paths` with a `senior_accept` record (1-5), and the row runs `re_check` over the stopped attempt with no dispatch.

## Boundaries & Constraints

**Always:**
- **When a consult is offered.** Only on `agent_tail.tail`'s hit, when the row declares the stop and has not used it, and only when no hit is a document (`rules/protected_paths.is_document`, from 1-5). No `_resumable` check is needed.
- **The offer.** It first records the stopped attempt's spend, so the consult's budget check counts it. Then it sweeps and snapshots as 1-4 does, and stores the hits payload on the entry.
- **The diff file.** After 1-5's `prepare`, the consult attempt writes `{seq:03d}-{n}.diff` beside the decision file. For each hit it holds a `### {path}` header and `Git.diff` from the stopped attempt's start SHA to the tree as it stands after the sweep, in that hit's tree: `start_sha` for the workdir, `root_start_sha` for the root.
- **What counts as an accept.** `status: accept` with `approved_files` equal, as a set, to the hit paths.
- **Every other outcome fails closed.** The row parks `protected_path` with status `error`. The reason is the original one plus ` · senior: R` or ` · consult failed: {why}`. The payload is the original hits payload, so the Operator's diff view and `continue` work unchanged.
- **Applying an accept.** `apply_consult` extends `accepted_paths` (without duplicates) and records `senior_accept` with `kind: protected_path`. It sets the entry to `{state: accept, answered_by}` and requeues through `retry`'s pair. Nothing is written when `result.park` is set.
- **Delivering an accept.** `rules/consult.delivers` returns the row's latest `senior_accept` of that kind only to the `agent` attempt numbered `answered_by + 1`, and checks this before the blocked answer. `re_check` admits `continue` or `senior_accept` when it carries files. An accept therefore applies once, with no dispatch and no new spend. A later attempt (retry, crash) dispatches.
- **The re-check attempt is today's.** It is an empty `agent` attempt with no session, which is deferred under AD-9. A `blocked` stop that it routes to is consulted as in 1-4, and the answer reaches a fresh dispatch.
- **Unchanged:** the 1-4 rules and the walker's sequence.

**Never:** No consult at a stall or timeout hit (`finish`), at a `git.commit` commit-guard hit, or on a hit list that holds a document. No `accept` at `blocked`. No new status token. No test pins shipped template content.

**Decided (lead review, 2026-11-02):** The event and the Run-wide scope are 1-5's.
- *Set equality:* the senior must name every file it accepts. That is what the Operator's `continue` must name (`use_cases/signals.py`).
- *Delivery to `answered_by + 1` only:* 1-4's rule keeps an answer owed until a later attempt has an `end_sha`. `re_check` writes none, so under that rule it would apply the accept again on every later attempt.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Accept | Test hits only; `accept`; files equal the hits | Records `consult`, then `senior_accept`. `accepted_paths` gains the hits. The next attempt runs `re_check` over attempt n, with no dispatch | N/A |
| Escalate | `escalate`, `reason: R` | Park `protected_path`, `{reason} · senior: R`, with the hits payload | N/A |
| No accept | Unreadable; `answer`; files differ from the hits; tree changed; crash | Park `protected_path`, `{reason} · consult failed: {why}` (`no readable decision`, `approved files differ from the hits`, as in 1-4), with the hits payload | Fail closed |
| Anchor among hits | Any document is hit | No consult; park as today | N/A |
| Stall or timeout hit | — | No consult | N/A |
| Over budget | The consult's spend exhausts the budget | Park `protected_path`, with the `budget` record on top. Nothing accepted | N/A |
| Later re-run | After an accept: a retry or a crash | Dispatches; the accept is not re-applied | N/A |
| Operator after escalation | `continue` with the hit files | Accepted as today | N/A |
| Validator | `on: [blocked, protected_path]` | Valid. `budget` and other tokens are still refused | N/A |

</frozen-after-approval>

## Code Map

Paths are under `backend-api/src/orchestrator/application/` unless stated.

- `domain/values.py`: `ConsultOutcome` gains `accept`, and `Consult` gains `hits: dict[str, Any] = {}`.
- `rules/consult.py`:
  - `verdict(decision, kind="blocked")`. At `protected_path` it returns `accept` or `escalate`, and anything else fails.
  - `delivers`, as decided.
  - `DIFF_FILE`.
- `steps/agent_consult_review.py` (1-5's): `qualifies(hits)`, `write_diff(ctx, entry)`, `same_files(approved, hits)`.
- `steps/agent_consult.py`:
  - `offer` handles `protected_path`; `_resumable` applies to `blocked` only.
  - `_parked` writes `error` and the stored hits payload for `protected_path`.
  - `run` writes the diff for `protected_path` and reads the verdict with the entry's kind.
- `steps/agent_tail.py` is at 400 lines:
  - `tail` passes a hit through `agent_consult.offer`.
  - `_record_spend` becomes public for the offer.
  - `re_check` admits `senior_accept`.
  - If this does not fit, move `re_check` and `_reported` whole to `steps/agent_recheck.py`, with a test pair.
- `use_cases/apply_consult.py`: handles `accept`.
- `templates/table.py`: `CONSULT_ON = {blocked, protected_path}`.
- `ia-agents-skills/senior-consult/SKILL.md` gains "Reviewing a protected-path diff":
  - When the condition starts with `protected path modified:`, read the `.diff` beside the decision file and the `.story.md` baseline.
  - Write `status: accept` with `approved_files` equal to every listed path only when 1-5's "required by the story" holds for each hunk.
  - Otherwise, or when unsure, escalate.
- `templates/staged-story.yaml` and `templates/staged-hub-story.yaml`: the three consulting rows declare `on: [blocked, protected_path]`, and `dispatch` says "condition", not "blocking condition".

## Tasks & Acceptance

**Execution:**
- [ ] Rebase on stories 1-6 and 1-5.
- [ ] `backend-api/tests/unit/application/test_consult_review_*.py` (new): one test per matrix row, through the shared fakes and fixture YAML, each seen failing first.
- [ ] `backend-api/tests/unit/test_senior_consult_review_skill.py` (new): asserts each addition to the skill.
- [ ] Every module in the Code Map, at 400 lines or fewer, each new module with a test module. No existing test needs revising: in `test_consult_rules.py`, the `accept until 1-5` case still holds, because `accept` at `blocked` stays unreadable.

**Acceptance Criteria:**
- Given a fixture Run whose implementer edits a frozen test and whose senior accepts, when the walk ends, then:
  - the Run never left `running`;
  - no `protected_path` record exists;
  - the row's harness was started once for the agent and once for the senior;
  - `GET /runs/{id}` lists the `senior_accept` record naming the senior and the file.
- Given a fixture hub row whose hit is `{workdir}/tests/a.py`, when its senior accepts, then the diff file holds the workdir tree's diff, and that exact spelling enters `accepted_paths`.
- Given an escalated review, when the Operator sends `continue` with the hit files, then the row resumes through `re_check` as it does today.

## Verification

**Commands:**
- `make lint`: passes.
- `make test`: passes, with domain and application at 100% branch coverage.
- `make openapi`: no drift after generation.
- `make e2e`: passes.

## Implementation Notes

## Spec Change Log

- 2026-11-02, lead review: split out of 1-5. Added the spend recorded before the offer, the `answered_by + 1` delivery and the `error`-status park. Known-bad states avoided: an accept applied again on every later attempt; a consult budget check that misses the stopped attempt's spend; a fail-closed park that the Operator's `continue` cannot accept. KEEP: the hits-only gate, and the hits payload on every fail-closed park.

## Review Triage Log
