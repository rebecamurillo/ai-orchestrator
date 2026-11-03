---
title: 'Test-edit approval at a blocked stop'
type: 'feature'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: '2460a484df02e3db8e88834fef9153551b3d3515'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In the baseline Run, 19h43 went to waiting for a person to approve test edits the story already implied. Since 1-4 a senior can answer at a `blocked` stop, but it cannot approve a test edit. So the resumed agent's edit still parks `protected_path`.

**Approach:** This is the first half of CAP-2, under hard rule 1 (amended 2026-11-02) and AD-17's amendment. At a `blocked` consult, an `answer` may name `approved_files`. Each file enters `run.accepted_paths` with one acceptance record naming the senior, before the answer is delivered. Preflight warns when the repository's `test_globs` is empty. The `protected_path` diff review is story 1-8.

## Boundaries & Constraints

**Always:**
- A file is approvable only if it is in the frame's anchor set (`require_env(ctx).anchors`) and is not a document. A document is any path whose basename is `SPEC.md`, `stories.yaml`, `epics.yaml` or `AGENTS.md`.
- Paths use AD-17's run-worktree spelling. On a `workdir` row, only paths under `{workdir}/` qualify.
- One bad path fails the whole consult, and nothing is accepted.
- The acceptance extends `run.accepted_paths`, without duplicates, through `set_run`. It writes one record, before `senior_answer` and in the same unit of work:
  - event `senior_accept`, actor `senior`;
  - text `accepted by the senior: {files} · {reason}`;
  - payload `{files, reason, kind}`, where `files` is `FILES_KEY`.
- Nothing is accepted when `result.park` is set.
- Before the senior is dispatched, the consult attempt:
  - removes any file already at its decision path, because an agent can write the self-ignored folder;
  - writes `{seq:03d}-{n}.story.md` beside the decision file. This is the story file as it stood at the root-tree start SHA of the row's lowest-`n` `agent` attempt. Nothing is written when no single file matched then.
- The 1-4 rules hold: one consult per row per kind, an untouched tree, and the decision read from the file. The walker's sequence is unchanged.

**Never:** No approval of a document, or of anything outside the decision file. `accept` at `blocked` stays `no readable decision`. No new status token. No test pins shipped template content. A preflight warning never refuses a start.

**Decided (lead review, 2026-11-02):**
- *Event:* `senior_accept` joins `MACHINE_EVENTS`. `test_gate_events.py::test_the_machine_events_are_ad_9s_two_bounded_re_executions` is revised under rule 1(b), citing story 1-5 and the 2026-11-01 amendments to AD-17 and AD-22. Reason: `continue` is the Operator's signal event, and `signal_run` writes it (AD-8). A machine-written `continue` would add a writer, and the stop records (AD-24) could not show who accepted.
- *Scope:* Run-wide, as the Operator's `continue` is today. Reason: CAP-2 says approved files "do not stop the Run again". Scoping to the frame changes the Operator's `continue` too, so it is deferred (`deferred-work.md`).
- *Story baseline:* the senior judges against `SPEC.md`, `stories.yaml` and the `.story.md` baseline, not the live story file. Reason: the agent asking for approval can write its own declaration into the live story file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Approve | `answer`, body, `approved_files: [tests/a.py]` (frozen) | Records `consult`, `senior_accept`, `senior_answer`. `accepted_paths` gains the file. The resumed agent edits it without parking | N/A |
| Bad path | A document; not frozen; or outside `{workdir}/` | Park `blocked`: `{question} · consult failed: approved file is an anchor: {p}` / `…not a frozen test file: {p}` | Fail closed |
| Bad list | `approved_files` is not a list of strings | `… · consult failed: no readable decision` | Fail closed |
| No answer | `escalate` with files; answer over budget | Parks as 1-4. Nothing accepted | N/A |
| Planted file | A decision file exists before the senior runs, and the senior writes none | Removed first; `no readable decision` | Fail closed |
| Edit outside approval | The resumed agent edits frozen `tests/b.py` | Park `protected_path` as today. The hits list `tests/b.py` only | N/A |
| Preflight | The repository's `test_globs` is `[]` | One `warn` line, `test globs`: `no test_globs: no existing test is frozen`. No line when globs are set or no repository is chosen | Start allowed |

</frozen-after-approval>

## Code Map

Paths are under `backend-api/src/orchestrator/application/` unless stated.

- `domain/statuses.py`: add `senior_accept` to `MachineEvent`. `domain/values.py`: add `Consult.approved_files: tuple[str, ...] = ()`.
- `rules/consult.py`:
  - `Decision.approved_files`. An absent key reads as `()`. A non-list, or a list with an entry that is not a string, makes `parse` return `None`.
  - `STORY_FILE`, and `ACCEPT_EVENT = "senior_accept"`.
- `rules/protected_paths.py`: `is_document(path)`.
- `steps/context.py` `RunEnvironment.story_baseline_sha`, set by `use_cases/walk_context.py` from the row's lowest-`n` `agent` attempt that has a start SHA. Use `root_start_sha` on a `workdir` row, otherwise `start_sha`.
- `steps/agent_consult_review.py` (new, because `agent_consult.py` is over 320 lines):
  - `prepare(ctx, decision)` removes the decision file and writes the baseline through `Git.list_files` and `Git.read_file`.
  - `approval_error(ctx, files) -> str | None`.
- `steps/agent_consult.py`: `run` calls `prepare` after writing the `.gitignore`. `_outcome` checks an answer's files and returns `_parked(…, FAILED, why)` on an error, or else a `Consult` that carries them.
- `use_cases/apply_consult.py`: when an answer carries files, extend `accepted_paths` and record `senior_accept`, then `senior_answer` as today. Return the updated Run so later writes keep the list.
- `preflight/model.py::CHECK_TEST_GLOBS = "test globs"` and `preflight/lists.py::test_globs_line`, appended after `clone_check_line` in `use_cases/preflight.py::_lines`.
- `ia-agents-skills/senior-consult/SKILL.md` gains "Approving test edits":
  - Add `approved_files: [...]` to an answer's frontmatter only for existing test files that the story requires changing.
  - "Required" means `SPEC.md`, `stories.yaml` or the `.story.md` baseline states the new behaviour (acceptance criteria, `## Do not touch`). The revision touches only the assertions that pinned the old behaviour, asserts the new behaviour as thoroughly, and names the story and the date.
  - A declaration that only the live story file carries counts as the agent's own claim, so escalate.
  - On a hub row, spell paths `{workdir}/…`. Never name an anchor.
  - Escalate a deletion, a skip, a relaxed assertion, an unrelated test, or anything unsure.
  - Name the files in the answer body too.

## Tasks & Acceptance

**Execution:**
- [x] Rebase on story 1-6, which edits the same consult modules.
- [x] `backend-api/tests/unit/application/test_consult_approval_*.py` (new): one test per matrix row, through the shared fakes and fixture YAML, each seen failing first.
- [x] `backend-api/tests/unit/test_gate_events.py`: revise the named assertion as decided. No other existing test is edited.
- [x] `backend-api/tests/unit/test_senior_consult_approval_skill.py` (new): asserts each addition to the skill.
- [x] Every module in the Code Map, at 400 lines or fewer, each new module with a test module.

**Acceptance Criteria:**
- Given a fixture Run whose agent blocks on a question about frozen `tests/a.py`, whose senior answers with `approved_files: [tests/a.py]`, and whose resumed agent edits that file and ends `done`, when the walk finishes the row, then:
  - the Run never left `running`;
  - no `protected_path` record exists;
  - `GET /runs/{id}` lists the `senior_accept` record, with actor `senior`, naming `tests/a.py`;
  - `accepted_paths` holds `tests/a.py`.
- Given a fixture hub row, when its senior approves `{workdir}/tests/a.py`, then that exact spelling enters `accepted_paths`. When it approves `tests/a.py`, the consult fails closed.
- Given an agent that wrote `approved_files` into the consult's decision path before blocking, when the senior writes no file, then the stop parks `no readable decision` and nothing is accepted.

## Verification

**Commands:**
- `make lint`: passes.
- `make test`: passes, with domain and application at 100% branch coverage.
- `make openapi`: no drift after generation.
- `make e2e`: passes.

## Implementation Notes

- **Gates.** `make lint` passes. `make test` passes: 8676 backend tests (1 skipped) and 1711 web-client tests, with `domain` and `application` at 100% branch coverage. `make openapi` regenerated `contracts/openapi.json` and `schema.d.ts`, because `GateEvent` widened by `senior_accept`. Neither file has drift.
- **Not run.** `make e2e` and `make e2e-ui` were out of scope by instruction.
- **Rebased on 1-6.** The Code Map holds at HEAD. `agent_consult.py` was at 389 lines and is now 396. So the answer is built in `agent_consult_review.answered`, which returns the `Consult` or the refusal, next to `prepare` and `approval_error`. `_outcome` parses once and passes the `Decision` on.
- **Decided: `Consult.reason`.** The acceptance record carries the decision's `reason`, so `Consult` gains `reason: str = ""` beside `approved_files`. An approval with a blank reason fails closed (`approval names no reason`), and the writer accepts nothing without one (Review Triage 2).
- **Decided: only a `blocked` answer approves.** A `verify_failed` answer (1-6) carries no files, and nothing is accepted. The diagnosis is still delivered.
- **Decided: the planted baseline.** `prepare` removes any file at the `.story.md` path as well as at the decision path, so an agent cannot plant a baseline either.
- **Message spelling.** The matrix's `…not a frozen test file: {p}` is written `approved file is not a frozen test file: {p}`. A path outside `{workdir}/` on a hub row reads the same.
- **Known limits (Review Triage 3).** The kill reaches only the blocked agent's own process group. A child it started with `setsid` escapes it, though the decision is still read only from a regular file. A recorded `pgid` the kernel has since reused would be signalled too. The 1-4 orphan kill shares this hazard.
- **Port widened (Review Triage 1).** `Workspace.is_link` is new. `FsWorkspace` implements it, and the shared `FakeWorkspace` gains `is_link` and a public `links` set, which its `remove` clears. No existing assertion changed.
- **Tests revised (rule 1(b)).** `test_gate_events.py::test_the_machine_events_are_ad_9s_two_bounded_re_executions` now pins `senior_accept`, citing story 1-5, 2026-11-02 and the AD-17/AD-22 amendments. The shared fixture `consult_fixtures.a_consult_world` now writes the decision in `FakeHarness.on_wait`, while the senior runs, instead of seeding it before `run`. The coordinator approved this on 2026-11-02, because the planted-file rule removes a file that is already there. No assertion was changed, and all 36 callers in `test_consult_run.py` and `test_verify_consult_run.py` pass unchanged. The old shape is now pinned as the planted case in `test_consult_approval_run.py`. No other existing test was edited.

## Spec Change Log

- 2026-11-02, lead review: split. The `protected_path` diff review and `accept` moved to story 1-8. Added the decided event, scope and story baseline; the removal of a planted decision file; and the workdir prefix rule. Known-bad states avoided: an agent pre-approving its own edits through the self-ignored folder or the live story file, and a hub approval landing in the wrong tree. KEEP: the acceptance record's shape, and failing the whole consult on one bad path.

## Review Triage Log

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| 1 | A dangling symlink planted at the decision path survived `FsWorkspace.remove`, because `is_dir` and `exists` follow links. Once its target was written, `read` returned the agent's `approved_files` (verified on a real tree) | fix | `remove` now deletes a link itself first. A new `Workspace.is_link` names a path that is a link or lies under a linked folder. The consult reads the decision through `agent_consult_review.read_decision`, which refuses such a path (`no readable decision`), and it writes no baseline through a link. Covered on a real `tmp_path` tree by `test_consult_decision_links.py`, and on the fake by `test_consult_approval_hardening.py` |
| 2 | An approval with an empty `reason` was accepted, and the record then named no reason | fix | `answered` refuses non-empty `approved_files` with a blank reason (`approval names no reason`). `apply_consult` accepts nothing without one, and its text is always `{files} · {reason}`. My own `test_an_acceptance_with_no_reason_names_the_files_only` became the refusal case, and the hub approval test gained a reason. Both are new tests of this story |
| 3 | A process the blocked agent left running could rewrite the decision after it was cleared, because `runner.wait` does not kill the group on a normal exit | fix | `prepare` first kills the blocked agent attempt's recorded `pgid` through `ProcessRunner.kill_group`, before it clears anything. The `setsid` escape and `pgid` reuse are noted as known limits |
