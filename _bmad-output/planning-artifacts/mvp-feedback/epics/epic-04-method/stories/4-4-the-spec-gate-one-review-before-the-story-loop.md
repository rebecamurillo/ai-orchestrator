---
title: The spec-gate — one review before the story loop
type: feature
created: '2026-09-17'
status: done
baseline_revision: 5634acaee3c11aaf03f198387455158888482882
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The shipped `epic` template ran the story loop immediately after baseline with no automated review of the spec folder; the implementation (spec-gate skill + template step + exemplar update + bmad-spec guidance note) is already in place from attempt 1, but four tests fail because they pin the old epic template shape in violation of AGENTS.md hard rule 6. The Operator has authorized revision of these tests (exception 4, 2026-09-17).

**Approach:** Update exactly the four failing tests to reflect the new `spec-gate` node in the epic template — adding it to golden-shape assertions, row-list constants, and frame-building helpers — while preserving the behaviour each test was covering. No shipping code changes are needed.

## Boundaries & Constraints

**Always:**
- Each revised test must name the decision and its date per AGENTS.md exception 4: "story 4-4 (2026-09-17): spec-gate agent step inserted after baseline"
- The implementation artifacts already in place must remain unchanged: `templates/epic.yaml`, `tests/unit/application/templates/fixtures/exemplars/epic.yaml`, `ia-agents-skills/spec-gate/SKILL.md`, `.agents/skills/bmad-spec/SKILL.md` (all already correct — do not re-edit)
- The revisions are the minimum change to make the 4 tests pass: do not change unrelated assertions in those files

**Block If:** Running `make test` reveals failing tests beyond the 4 identified ones — report which additional tests fail before making further changes.

**Never:**
- Do not modify any test file other than the three listed in the Code Map
- Do not change `plan_fixtures.py` — the exemplar files (not the plan_fixtures constants) are the source of truth for the plan tests
- Do not resync the exemplar to the shipped template beyond what was already done in the wip commit

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| spec-gate step in exemplar | `fixtures/exemplars/epic.yaml` has spec-gate between baseline and stories | `test_epic_is_the_golden_shape` passes with updated node + edge assertions | — |
| EPIC_ROWS without spec-gate | `test_epic_expands_one_frame_per_story_*` asserts rows list against `EPIC_ROWS` | `EPIC_ROWS` updated; test passes | — |
| epic_frame without spec-gate | `test_an_initiative_expands_one_frame_per_epic_and_one_per_story` builds frame via `epic_frame()` helper | `epic_frame()` helper updated; test passes | — |
| agent_rows[0] is now spec-gate | `test_the_readiness_run_reaches_its_agent_row` finds first story agent row | assertion changed to filter by `story_id == READINESS_STORY_ID` | — |

</intent-contract>

## Code Map

- `backend-api/tests/unit/application/test_graph_shipped.py:175` — `test_epic_is_the_golden_shape`; asserts exact node IDs tuple and edge pairs; must add `"spec-gate"` between `"baseline"` and `"stories.story"` in node IDs, and replace `("baseline", "stories.story")` edge with `("baseline", "spec-gate"), ("spec-gate", "stories.story")` in edge pairs
- `backend-api/tests/unit/application/templates/test_plan_shipped.py:150-172` — `EPIC_ROWS` constant; insert `"spec-gate"` after `"baseline"` (before `"stories[0].sync"`); `THIRD_STORY` derives from `EPIC_ROWS` and needs no change
- `backend-api/tests/unit/application/templates/test_plan_shipped.py:376-392` — `epic_frame(index, *, after)` helper function; rows list starts with `[checkout, setup, baseline]`; add `f"{prefix}.spec-gate"` as the fourth element immediately after `f"{prefix}.baseline"`
- `backend-api/tests/unit/application/test_readiness_declares_no_quality_gate.py:187-199` — `test_the_readiness_run_reaches_its_agent_row`; currently uses `agent_rows[0]` and asserts `first.story_id == READINESS_STORY_ID`; spec-gate is now `agent_rows[0]` (story_id=None), so the story's build step is `agent_rows[1]`; fix: filter `agent_rows` by `story_id == READINESS_STORY_ID` before taking `first`

## Tasks & Acceptance

**Execution:**

- `backend-api/tests/unit/application/test_graph_shipped.py` -- UPDATE `test_epic_is_the_golden_shape` -- add `"spec-gate"` after `"baseline"` in the `node_ids` assertion tuple; replace single edge `("baseline", "stories.story")` with two edges `("baseline", "spec-gate")` and `("spec-gate", "stories.story")`; update the docstring to name the decision and date: "Updated 2026-09-17 (story 4-4): spec-gate agent step inserted after baseline."

- `backend-api/tests/unit/application/templates/test_plan_shipped.py` -- UPDATE `EPIC_ROWS` -- insert `"spec-gate"` after `"baseline"` and before `"stories[0].sync"`; add inline comment `# story 4-4 (2026-09-17): spec-gate agent step inserted after baseline`

- `backend-api/tests/unit/application/templates/test_plan_shipped.py` -- UPDATE `epic_frame()` helper -- change the opening `rows` assignment from `[f"{prefix}.checkout", f"{prefix}.setup", f"{prefix}.baseline"]` to `[f"{prefix}.checkout", f"{prefix}.setup", f"{prefix}.baseline", f"{prefix}.spec-gate"]`; add inline comment `# story 4-4 (2026-09-17): spec-gate after baseline`

- `backend-api/tests/unit/application/test_readiness_declares_no_quality_gate.py` -- UPDATE `test_the_readiness_run_reaches_its_agent_row` -- replace `first = agent_rows[0]` and `assert first.story_id == READINESS_STORY_ID` with: filter `agent_rows` to `story_rows = [e for e in agent_rows if e.story_id == READINESS_STORY_ID]`; assert `story_rows` is non-empty; `first = story_rows[0]`; keep `assert first.status == "planned"` and the `before` check unchanged; update the docstring to name the decision and date

**Acceptance Criteria:**

- Given `make test`, when run after the four test changes, then all 6357 tests pass and domain + application remain at 100% branch coverage
- Given `make lint`, when run after the changes, then all checks pass (no new Python modules are introduced, so no new test-pair entries are needed)
- Given `test_epic_is_the_golden_shape`, then `node_ids(graph)` equals `("checkout", "setup", "baseline", "spec-gate", "stories.story", "stories.after", "e2e", "push", "link")` and edge pairs include `("baseline", "spec-gate")` and `("spec-gate", "stories.story")`
- Given `test_epic_expands_one_frame_per_story_with_the_checkpoint_story_two_declared`, then `paths(epic)` equals `EPIC_ROWS` (which now includes `"spec-gate"` after `"baseline"`)
- Given `test_an_initiative_expands_one_frame_per_epic_and_one_per_story`, then each epic frame includes `{prefix}.spec-gate` after `{prefix}.baseline`
- Given `test_the_readiness_run_reaches_its_agent_row`, then the test passes by finding the first agent row whose `story_id == READINESS_STORY_ID` rather than using `agent_rows[0]`

## Design Notes

The `test_readiness_declares_no_quality_gate.py` test's docstring says "nothing here names a step, counts a row or pins a reason to a path: every assertion is a property that must hold for *any* epic Template." The `agent_rows[0]` assumption violated that principle once a pre-loop agent step was added. Filtering by `story_id` restores the intended invariant: the test asserts that the readiness story's agent dispatch is reachable and planned, regardless of what epic-level steps precede it.

The `test_graph_shipped.py` exemplar fixture (`fixtures/exemplars/epic.yaml`) already contains the spec-gate step. The golden-shape test pins the exemplar's structure — updating it to match the new exemplar is the correct fix, not removing the exemplar or the assertion.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter, env-contract, test-pairs all green; no new modules
- `make test` -- expected: all 6357 tests pass; domain + application at 100% branch coverage

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 0, low 1)
- defer: 0
- reject: 11
- addressed_findings:
  - `[low]` `[patch]` `spec-gate`'s `story_id=None` was not pinned anywhere; extended `test_an_epic_row_belongs_to_the_epic_frame_and_to_no_story` in `test_plan_shipped.py` to assert `(spec_gate.frame, spec_gate.story_id) == ("epics[1]", None)`, matching the existing assertion for `push` and closing the gap that the readiness test's `story_id` filter implicitly depends on

## Auto Run Result

**Summary:** Fixed four tests that pinned the old epic template shape (pre-spec-gate) after the `spec-gate` agent step was added to the shipped `epic` template and its exemplar fixture in the prior wip commit. All revisions name the Operator-authorized decision and date per AGENTS.md exception 4. One additional low-severity patch applied during review: `spec-gate`'s `story_id=None` property pinned alongside the existing `push` pin in the initiative plan test.

**Files changed:**
- `backend-api/tests/unit/application/test_graph_shipped.py` — `test_epic_is_the_golden_shape`: added `"spec-gate"` to node IDs tuple; replaced `("baseline","stories.story")` edge with two edges; updated docstring with decision date
- `backend-api/tests/unit/application/templates/test_plan_shipped.py` — `EPIC_ROWS` constant: inserted `"spec-gate"` after `"baseline"` with dated comment; `epic_frame()` helper: added `f"{prefix}.spec-gate"` as fourth prefix element with dated comment; `test_an_epic_row_belongs_to_the_epic_frame_and_to_no_story`: extended to also assert `spec-gate` row carries `story_id=None` (review patch)
- `backend-api/tests/unit/application/test_readiness_declares_no_quality_gate.py` — `test_the_readiness_run_reaches_its_agent_row`: replaced positional `agent_rows[0]` assertion with `story_id`-filtered lookup; updated docstring with decision date

**Review findings breakdown:** 1 patch applied (0 high, 0 medium, 1 low); 0 deferred; 11 rejected.

**Follow-up review recommendation:** false — score 3×0 medium + 1×1 low = 1 < 5.

**Verification performed:**
- `make lint`: PASS — ruff, mypy, import-linter, env-contract, test-pairs, gen:api, tsc, eslint, prettier all green
- `make test`: PASS — 6357 backend tests passed (23 skipped); domain + application at 100% branch coverage

**Residual risks:**
- The `test_the_readiness_run_reaches_its_agent_row` no longer asserts that the readiness story's dispatch is the *first* agent row overall (spec-gate now precedes it). This positional property is intentionally unpinned per the test module's own design rule ("nothing here names a step, counts a row or pins a reason to a path"). The spec-gate step's `story_id=None` is now pinned via the initiative plan test, removing the gap the verification-gap reviewer identified.
