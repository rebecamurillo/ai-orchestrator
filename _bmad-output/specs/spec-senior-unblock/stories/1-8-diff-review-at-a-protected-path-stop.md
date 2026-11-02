---
title: 'Diff review at a protected_path stop'
type: 'feature'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: 'f1883b473af9e0800dd7088e1b9bcf2a655a6b64'
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
- [x] Rebase on stories 1-6 and 1-5.
- [x] `backend-api/tests/unit/application/test_consult_review_*.py` (new): one test per matrix row, through the shared fakes and fixture YAML, each seen failing first.
- [x] `backend-api/tests/unit/test_senior_consult_review_skill.py` (new): asserts each addition to the skill.
- [x] Every module in the Code Map, at 400 lines or fewer, each new module with a test module. No existing test needs revising: in `test_consult_rules.py`, the `accept until 1-5` case still holds, because `accept` at `blocked` stays unreadable.

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

- **Gates.** `make lint` passes. `make test` passes: 8779 backend tests (1 skipped) and 1711 web-client tests, with `domain` and `application` at 100% branch coverage. No API schema changed (`Consult` is not in the contract), so `make openapi` had nothing to regenerate; `gen:api --check` in `make lint` reports no drift.
- **Not run.** `make e2e` and `make e2e-ui` were out of scope by instruction.
- **Built on HEAD.** The Code Map held, with line references adapted. 1-5's `prepare`, `read_decision`, `is_document`, `Workspace.is_link` and the `senior_accept` writer are reused unchanged.
- **Module splits (400-line cap).** `agent_tail.py` was at 400: `re_check` and `_reported` moved whole to `steps/agent_recheck.py` (test pair `test_agent_recheck.py`), and `agent.py` calls it there. `agent_consult.py` was at 397: the senior's own dispatch (`_Senior`, `_dispatch`, `_senior`, `_stall_min`) moved whole to `steps/agent_consult_senior.py` (test pair `test_agent_consult_senior.py`). The protected-path helpers (`qualifies`, `same_files`, `write_diff`, `accepted`) are in `agent_consult_review.py`.
- **Decided: the hits on the entry.** The offer's `Consult.hits` is the hit's own payload (`{hits: [...]}`), stored on the entry under `hits` only when non-empty, so `blocked` entries are unchanged. Every fail-closed `protected_path` park returns that payload, status `error`.
- **Decided: the spend.** `offer` takes the stopped dispatch's `HarnessResult` and, at a `protected_path` offer only, records its spend through `agent_tail.record_spend` (made public) before the sweep. The re-check later prices the same attempt with no usage, which recomputes rather than adds (`record_attempt_spend`).
- **Decided: an accept over budget (Review Triage 2).** It parks `{reason} · consult failed: senior accepted ({senior's reason}); no remaining budget` with the `budget` record on top and outcome `accept`, still in the `consult failed:` form the boundaries allow. Nothing is accepted.
- **Decided: an accept with no reason.** It fails closed (`approval names no reason`, 1-5's wording), and `apply_consult` writes no `senior_accept` without files and a reason.
- **Message spelling.** Files that differ read `approved files differ from the hits`. The row's reason after an accept is `senior accepted: {files}`. `approved_files` is stored in the hits' order.
- **The diff file.** Each section is `### {path}\n{Git.diff}`, joined by a newline. A hit under `{workdir}/` is diffed in the member tree from `start_sha` with the prefix stripped. Any other hit on a `workdir` row is diffed in the root from `root_start_sha`. The file is removed first. A diff path under a link, or a hit whose tree has no start SHA, parks before the senior is dispatched (Review Triage 4).
- **Templates.** `staged-story.yaml` and `staged-hub-story.yaml`: the three consulting rows in each now declare `on: [blocked, protected_path]`, and `dispatch` says "this condition". The `answer` clauses are unchanged.
- **Skill.** "Reviewing a protected-path diff" was added, and the frontmatter description names the protected-path stop.
- **Loop fixture.** AD-17 freezes the frame's first started attempt's test set. So `test_consult_review_loop.py` gives the frame an earlier, finished row whose attempt recorded `tests/a.py`, and the implementer's first dispatch can hit it.
- **Tests revised.** No test that predates this story was changed. Every one passes, including `test_consult_rules.py`'s `accept until 1-5` case. The review revised three of this story's own tests in `test_consult_review_run.py`, as the triage rows declare: the planted diff, the diff under a link, and the stopped attempt with no start now park before dispatch. The over-budget accept now asserts the new reason.

## Spec Change Log

- 2026-11-02, lead review: split out of 1-5. Added the spend recorded before the offer, the `answered_by + 1` delivery and the `error`-status park. Known-bad states avoided: an accept applied again on every later attempt; a consult budget check that misses the stopped attempt's spend; a fail-closed park that the Operator's `continue` cannot accept. KEEP: the hits-only gate, and the hits payload on every fail-closed park.

## Review Triage Log

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| 1 | Deleting `workspace.remove(path)` in `write_diff` survived every test. Under that mutation a link the agent planted at the `.diff` path survived, and the senior read a diff the agent chose | fix | `test_a_planted_diff_is_removed_and_the_senior_reads_the_real_one` plants a regular file and a link at the diff path and asserts the senior reads the real diff. The mutation now fails it |
| 2 | An accept that ran out of budget parked as `consult failed: no remaining budget`, the same text as the refusal before any senior ran, so the accept and its reason were lost | fix | It now parks `· consult failed: senior accepted ({reason}); no remaining budget`, outcome `accept`, with the `budget` record on top |
| 3 | The offer discarded the Run returned after recording the stopped attempt's spend, so a hit whose own dispatch overspent was still offered, then parked without the `budget` record | fix | `offer` runs `budget.check` on that Run. When it parks, there is no offer and the hit keeps `budget_park`, as the blocked path does |
| 4 | A diff path under a link, or a stopped attempt with no start SHA, sent the senior nothing to read | fix | `write_diff` returns why, and the consult parks before dispatch: `diff file is under a link`, `no start commit to diff {path} from` (also on a hub root hit with no `root_start_sha`) |
