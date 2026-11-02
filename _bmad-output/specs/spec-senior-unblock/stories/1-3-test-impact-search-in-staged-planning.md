---
title: 'Test-impact search in staged planning'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'ff879624f57c3c7c31cabf28214f82b751e6d916'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In a real Run, a story's existing tests surfaced at different stages by luck: planning for some, implementation for one, review for another. Each one stopped the Run for approval because the plan had not declared it under `## Do not touch`. `staged-plan` told the planner to name changed tests there but never told it to look for them. A label pinned by a `test.fixme` e2e spec was caught only at review; a test asserting a menu entry is hidden was caught only when the agent reached it.

**Approach:** `staged-plan` gains a test-impact search in step 2, before the spec is written. It searches every test lane, `test.fixme` and skipped specs included, for the labels, identifiers, routes, exports, enum values and hidden or visible states the story changes. Contradicted tests go under `## Do not touch` with the behaviour change behind them. The search is recorded in that section whether or not it found anything.

## Boundaries & Constraints

**Always:** The search names all four lanes: `backend-api/tests/unit`, `backend-api/tests/e2e`, `web-client/tests/unit`, `web-client/tests/e2e`. Each contradicted test names its file, its assertion and the declared behaviour change.

**Never:** No new marker status. `staged-implement` and `staged-review` are untouched. No existing test file is edited; the new test is a new file. No test pins shipped template content (hard rule 6). `AGENTS.md` is not touched.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Label pinned by a `test.fixme` spec | Story changes a label that a skipped e2e spec asserts | The spec file is listed under `## Do not touch` with the assertion and the label change | N/A |
| Nothing found | No existing test contradicts the story | `## Do not touch` ends with `Test-impact search: <lanes> for <terms>; none found` | N/A |
| Skipped lanes | Story touches a `skip`ped pytest or `describe.skip` vitest test | Searched; listed if contradicted | N/A |

</frozen-after-approval>

## Code Map

- `ia-agents-skills/staged-plan/SKILL.md` -- step 2 gains the test-impact search: the four lanes and the skipped-spec markers, the terms to search, the contradicted-test rule, and the closing search line under `## Do not touch`. Nothing else in the file changes.
- `backend-api/tests/unit/test_staged_plan_test_impact.py` -- new; reads the skill the way `test_operator_skills_contract.py` does. Asserts the search sits before step 3, names every lane, `test.fixme` and `test.skip`, the change kinds, the `## Do not touch` record and `none found`, and that no marker status was added.
- `ia-agents-skills/README.md`, `staged-implement/SKILL.md`, `staged-review/SKILL.md` -- not touched.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/test_staged_plan_test_impact.py` -- new; seen failing first (six of seven fail against the unchanged skill) -- TDD.
- [x] `ia-agents-skills/staged-plan/SKILL.md` -- step 2 test-impact search, per Code Map.

**Acceptance Criteria:**
- Given a fixture story that changes a label pinned by a `test.fixme` spec, when `staged-plan` plans it, then the plan names that spec file under `## Do not touch` with the assertion and the label change.
- Given a story that no existing test contradicts, when `staged-plan` plans it, then the plan's `## Do not touch` section still records the search, its lanes and its terms, ending in `none found`.

## Implementation Notes

The skill is an instruction, so the test asserts the instruction's content, not a run of the planner. The `status:` guard asserts the marker set is still `done`, `blocked` and `ready-for-dev`; it passes before and after the change, as intended.

The search is written as `grep -rn` over the lanes, and labelled "not a survey", because step 2 says "Do not survey the codebase".

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `make lint` -- passes (ruff, mypy, import-linter, test pairs, env contract, eslint, prettier, tsc, gen:api drift).
- `make test` -- passes: backend-api 8198 passed, 1 skipped (the pytest run includes the seven new tests); web-client vitest 142 files, 1706 tests passed.
