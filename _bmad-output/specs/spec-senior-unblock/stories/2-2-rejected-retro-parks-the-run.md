---
title: 'Rejected retro parks the Run'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: '985fb785301aea442ec6123e68bac7fc5578683a'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `retro` row of both staged epic templates declares no `expect`, so a retrospective that ended `rejected` is a `done` row and the Run carries on to `commit-retro`, `merge`, `push` and the next epic. Three of five retros in the evidence ended `rejected`, once past a live cross-association write (CAP-9).

**Approach:** Route the retro through the row's existing `expect` contract (AD-9, 2026-11-01 amendment), with no new kind, no `consult`, and no code. The row declares one marker, `{spec_folder}/stories/.auto/retro.md`, with `expect.success: [accepted, accepted-with-open-items]` and `expect.blocked: [rejected]`. `route` already turns a blocked marker into a `blocked` park whose reason is the marker's whole `## Auto Run Result` section. The row's `prompt_extra` tells the agent to write that marker last, from the verdict it recorded in `RETROSPECTIVE.md`.

## Boundaries & Constraints

**Always:**
- The marker is `retro.md` under `stories/.auto/`, never `RETROSPECTIVE.md`. An `answer` archives the row's first matched file to `.auto/.answers/retro-attempt-{n}.md`, and that must never be the retrospective itself.
- The marker's frontmatter `status` is exactly `accepted`, `accepted-with-open-items` or `rejected`: the spellings `bmad-retrospective` already names for a machine reader. A `rejected` marker carries a `## Auto Run Result` section whose `Blocking condition:` line names the standing findings, each with its source, and the full list beneath it. That section is the park reason the human reads.
- Both shipped staged epic templates (`staged-epic.yaml`, `staged-hub-epic.yaml`) get the same `retro` change. The `auto` family and every other row are unchanged.
- A retro that leaves no marker parks `misconfigured: no story file`, and one that leaves a status outside the three takes the row's declared `retry` (max 1, resume the session) before parking, as every other marker row does.

**Never:** No edit under `_bmad/` or to `bmad-retrospective`. No new step kind, no `consult` on the row, no change to any status table, signal table or `DBOS_APPLICATION_VERSION`. No new skill.

**Decided, 2026-11-02:**
- **Marker mechanism: the row's `prompt_extra`, not an operator skill.** A thin `ia-agents-skills/staged-retro` would run `bmad-retrospective` and then write the marker. It adds a skill that ships only by image rebuild, a second dispatch contract to keep in step with BMAD's, and a skill-name entry for pre-flight to check, to carry two sentences. `bmad-retrospective` already fixes the verdict spelling and `RETROSPECTIVE.md` as the document; the only missing fact is where to copy the verdict to. That is template prose, which AGENTS.md makes the template's own (`prompts` are the template's words), changes with the template and needs no rebuild. The `retry` clause covers a marker written with a status outside the three; one never written parks for the Operator.
- **`continue` is not admitted at this stop.** AD-13 admits `answer`, `skip_step`, `skip_story`, `skip_epic` and `cancel` on a `blocked` agent row; `continue` is for `checkpoint`, `protected_path`, `plan_stale` and `dependency`. `answer` re-dispatches the row with the human's decision, which the retrospective skill says always overrides the machine verdict, and the agent rewrites the marker. `skip_step` accepts the rejection and carries on. The table is not changed.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Rejected | marker `status: rejected`, `Blocking condition:` naming findings | Row `blocked`, Run `needs_you` parked `blocked` on the retro row, reason is the marker's section; later rows stay `planned` | N/A |
| Accepted | marker `accepted` | Row `done`, Run carries on | N/A |
| Accepted with items | marker `accepted-with-open-items` | Row `done`, Run carries on | N/A |
| No marker | `RETROSPECTIVE.md` only | Parks `misconfigured: no story file`; the document is never read as a verdict | Operator `retry` |
| Other token | marker `status: done` | `unexpected status: done` through the row's `retry`, then `misconfigured` | Bounded by `retry.max` |
| Answer | `answer` at the park | `retro.md` archived to `.auto/.answers/retro-attempt-{n}.md` with `## Human Answer`; `RETROSPECTIVE.md` untouched; the agent re-dispatches and rewrites the marker | N/A |
| Signals at the stop | Run parked `blocked` on the retro | `answer`, `skip_step`, `skip_epic`, `cancel`; not `continue` | 409 |

</frozen-after-approval>

## Code Map

- `templates/staged-epic.yaml`, `templates/staged-hub-epic.yaml` -- the `retro` row gains `prompt_extra`, `expect` and `retry`. Nothing under `backend-api/src/`: `routing.route`, `agent_tail.story_files`, `agent_answer.archive_path` (stem `retro`, from the row path) and the AD-13 table already do the rest.
- `templates/README.md` -- one paragraph on the retro marker.
- `backend-api/tests/unit/application/steps/test_rejected_retro.py` (new) -- a fixture template owned by the test, planned and executed through the shared fakes.

## Tasks & Acceptance

**Execution:**
- [x] `test_rejected_retro.py` -- every matrix row, on a fixture template, through `plan_run`, `AgentExecutor`, `apply_step_result` and `admitted_signals`. No test reads `templates/*.yaml` (hard rule 6).
- [x] The two shipped `retro` rows, then `templates/README.md`.

**Acceptance Criteria:**
- Given a retro whose marker says `rejected`, when the row finishes, then the Run is parked `blocked` on that row and the reason names the findings.
- Given `accepted` or `accepted-with-open-items`, then the row is `done` and the Run carries on.
- Given an `answer` at that stop, then `retro.md` is the file archived and `RETROSPECTIVE.md` is left where it is.

## Implementation Notes

Tests first; they pass against the unchanged source, because the contract machinery already routes a blocked marker. The template edit is the only behaviour change, and no test may read a shipped template, so the two shipped rows were checked once by validating and planning them (`staged-epic` through `staged-initiative-repo`, `staged-hub-epic` through `staged-initiative-hub`) and reading the planned `retro` row's `expect`.

**Risks.** A marker committed by an earlier Run of the same epic stays on the branch; an agent that skips the write is read as that old verdict, the same exposure the plan, implement and review markers have. Epics with an unfinished story are `rejected` by the retrospective skill's own rule, so a Run that skipped a story parks here by design. The agent's compliance with the marker sentence is the one thing no unit test can prove; the `retry` clause guards a wrong status only, and an unwritten marker parks `misconfigured` for the Operator.

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `make lint` -- expected: passes.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
