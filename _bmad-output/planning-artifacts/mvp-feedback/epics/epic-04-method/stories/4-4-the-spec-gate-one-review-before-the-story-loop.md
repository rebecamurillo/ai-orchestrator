---
title: The spec-gate — one review before the story loop
type: feature
created: '2026-09-17'
status: blocked
baseline_revision: 3276df1df7cd2e0108d82ded5fee200e9b191de0
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The shipped `epic` template runs the story loop immediately after baseline with no automated review of the spec folder; formatting defects and open questions in `SPEC.md` or `stories.yaml` are discovered mid-loop when an agent hits them, wasting agent attempts.

**Approach:** Insert a `spec-gate` agent step (operator skill `ia-agents-skills/spec-gate/`) between baseline and the story loop in `templates/epic.yaml`; the skill reviews the spec folder and writes a result file routed by the existing FR-16 logic (`route()` in `rules/routing.py`) — no new routing code; update the bmad-spec authoring guidance to record that `spec_checkpoint` is now the exception, not the routine validation path.

## Boundaries & Constraints

**Always:**
- The spec-gate step uses `uses: agent` with `skill: spec-gate`, `expect.files: ["{{spec_folder}}/spec-gate-result.md"]`, `status_in: [done, blocked]`; routing is entirely handled by the existing `route()` — no modification needed
- Skill writes `status: done` (clean or after formatting fixes) or `status: blocked` (open questions); for `blocked`: `blocking_condition: "open questions"` in frontmatter; `## Auto Run Result` body carries the consolidated question list across all source files
- Formatting fixes are committed with the exact message `spec: gate fixes (orchestrator)` before the skill writes the done result
- `ia-agents-skills/spec-gate/SKILL.md` is the skill's only entry point; directory name `spec-gate` must not collide with any BMAD stub (authoring contract, story 4-1)
- `backend-api/tests/unit/application/templates/fixtures/exemplars/epic.yaml` is updated in the same commit as `templates/epic.yaml` (existing exemplar-sync pattern)
- No test pins step ids, ordering, or any shipped template content (exemplar-freeze, AGENTS.md)

**Block If:** Any routing change is required to handle the three spec-gate outcomes — investigation confirms the existing FR-16 table covers `done` and `blocked` outputs without modification.

**Never:**
- Do not add `pause_when` to the spec-gate step — checkpoints are the operator's decision at story level
- Do not add `retry` to the spec-gate step — the skill's two-outcome contract (`done` / `blocked`) makes retry unnecessary
- Do not add a commit-guard step after spec-gate in the epic template — the skill commits inside its own execution, before writing the result file
- Do not change `rules/routing.py`, `agent_tail.py`, or any other routing/tail code
- Do not create per-story gates (one consolidated `blocked` output covers all questions in one pass)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Clean spec | SPEC.md and stories.yaml have no open questions or formatting problems | `spec-gate-result.md` written with `status: done`; story loop starts | — |
| Formatting problems only | SPEC.md or stories.yaml has fixable defects (malformed frontmatter, placeholder text) but no unresolved questions | Skill fixes files in place, commits `spec: gate fixes (orchestrator)`, writes `status: done`; story loop starts | — |
| Open questions present | stories.yaml or SPEC.md has unresolved ambiguities, TBD entries, or contradictions | `spec-gate-result.md` written with `status: blocked`, `blocking_condition: "open questions"`, `## Auto Run Result` listing every question grouped by file; Run enters `needs_you` | Operator resolves questions, signals Continue |
| spec-gate absent from catalog | `spec-gate` not in skills manifest at pre-flight time | Pre-flight `fail` line "not installed: spec-gate"; `start_allowed` false; Run never starts (story 4-2 guarantee) | Operator rebuilds image |

</intent-contract>

## Code Map

- `templates/epic.yaml:22-26` — baseline step (lines 22–25) is the last step before the stories for_each (line 27); the spec-gate agent step is inserted between them as a new line 26 block; `{{harness}}`, `{{model}}`, and `{{spec_folder}}` are already declared inputs on the epic template
- `backend-api/tests/unit/application/templates/fixtures/exemplars/epic.yaml` — verbatim copy of `templates/epic.yaml` consumed by shipped-template smoke tests (`test_shipped_templates.py`, `test_shipped_smoke.py`); must be updated in the same commit to keep those tests passing
- `ia-agents-skills/spec-gate/SKILL.md` — new operator skill; reads `folder` from args (`folder=<path>`); loads `{folder}/SPEC.md` and `{folder}/stories.yaml`; identifies open questions and formatting problems; writes `{folder}/spec-gate-result.md` with frontmatter `status` and `## Auto Run Result` body
- `backend-api/src/orchestrator/application/rules/routing.py:67-105` — `route()` covers `done`→proceed and `blocked`→park unchanged; `blocking_condition: "open questions"` is not in `CONFIGURATION_CONDITIONS` so the blocked path routes correctly; no modification needed
- `backend-api/src/orchestrator/application/steps/agent_tail.py:273-286` — `story_files()` runs `_globs()` over `expect.files`; a literal path (no wildcard) is a valid glob that matches exactly one file when it exists; no modification needed
- `.agents/skills/bmad-spec/SKILL.md:136` — Story Breakdown section; the sentence "For each story, ask the user for `spec_checkpoint`…" needs a follow-on note that spec-gate now handles routine validation

## Tasks & Acceptance

**Execution:**

- `ia-agents-skills/spec-gate/SKILL.md` -- CREATE -- spec-gate operator skill; reads `folder` from args (`folder=<absolute-path>`); loads `{folder}/SPEC.md` and `{folder}/stories.yaml`; identifies: (a) open questions — unresolved ambiguities, TBD/open-question markers, story descriptions that admit multiple incompatible implementations, SPEC.md claims that contradict a story's scope — and (b) formatting problems — YAML parse errors, missing required frontmatter fields, broken markdown tables or code fences, placeholder text not filled in; if any open questions: writes `{folder}/spec-gate-result.md` with frontmatter `status: blocked` and `blocking_condition: "open questions"`, body `# Spec Gate Result\n## Auto Run Result\nStatus: blocked\n` followed by every question grouped under its source file heading; if only formatting problems and no open questions: fixes defects in the affected files, runs `git commit --message "spec: gate fixes (orchestrator)"`, then writes `{folder}/spec-gate-result.md` with `status: done` and `## Auto Run Result` summarising what was fixed; if clean: writes `{folder}/spec-gate-result.md` with `status: done` and `## Auto Run Result\nStatus: done\nOutcome: clean`

- `templates/epic.yaml` -- INSERT spec-gate agent step after line 25 (after baseline `gate: deterministic`), before the stories for_each (currently line 27) -- YAML block: `  - id: spec-gate\n    uses: agent\n    with:\n      harness: "{{harness}}"\n      model: "{{model}}"\n      skill: spec-gate\n      args: { folder: "{{spec_folder}}" }\n    expect:\n      files: ["{{spec_folder}}/spec-gate-result.md"]\n      status_in: [done, blocked]\n    timeout_min: 30\n    gate: liveness`

- `backend-api/tests/unit/application/templates/fixtures/exemplars/epic.yaml` -- UPDATE -- insert the identical spec-gate step in the same position as in `templates/epic.yaml`; keeps the shipped-templates smoke tests exercising the current template structure (without this update `test_shipped_smoke.py` would diverge from the shipped template)

- `.agents/skills/bmad-spec/SKILL.md` -- UPDATE Story Breakdown section (line 136) -- after the sentence ending "capturing that human judgment is what the fields are for.", append the sentence: `Note: the shipped \`epic\` template includes a \`spec-gate\` step that reviews the spec folder automatically before the story loop — set \`spec_checkpoint: true\` only for stories where human review between planning and implementation is genuinely warranted; the gate handles routine spec validation.`

**Acceptance Criteria:**

- Given `make lint`, when run after all file changes, then all checks pass (ruff, mypy, import-linter, env-contract, test-pairs, tsc, eslint, prettier — no new Python modules added, so no new test-pair requirement)
- Given `make test`, when run with both `templates/epic.yaml` and `fixtures/exemplars/epic.yaml` updated, then all tests pass and domain + application remain at 100% branch coverage
- Given a `spec-gate-result.md` with `status: done` at the path named in `expect.files`, when `route()` processes the spec-gate agent step result with exit code 0, then `StepResult.status == "done"` and the walker advances to the stories for_each (no park, no retry)
- Given a `spec-gate-result.md` with `status: blocked` and `blocking_condition: "open questions"`, when `route()` processes the result, then `StepResult.status == "blocked"` and the Run transitions to `needs_you` with the `## Auto Run Result` body as the park reason
- Given the `spec-gate` skill is absent from the installed skills catalog, when pre-flight runs against a plan containing the spec-gate step, then the installed-skill check emits a `fail` line whose text contains `"spec-gate"` and `start_allowed` is false

## Design Notes

The spec-gate result file uses a literal path in `expect.files` (no glob wildcard) because the skill always writes to the same known location. `story_files()` in `agent_tail.py` runs each entry in `expect.files` through the workspace glob; a literal path (no `*`) is a valid glob that returns the file if it exists, or an empty list if not. An empty list routes to `misconfigured` park via `route()`'s liveness check — the correct failure mode if the skill crashes before writing.

Formatting fixes are committed inside the skill's execution, before the result file is written. This places the fix commit earlier in history than the story-loop commits, giving the git log a clean ordering: repo baseline → spec fixes (if any) → story 4-1 → story 4-2 → … The epic template does not need a commit-guard step after spec-gate because the fix commit is the skill's own responsibility, not the template's orchestration concern.

The "one human gate" constraint means the skill reads ALL source files in `{folder}` (SPEC.md and stories.yaml) before deciding; it writes one single `spec-gate-result.md` with all questions consolidated, so the operator sees the full picture in one park, addresses it, and signals Continue.

## Verification

**Commands:**
- `make lint` -- expected: all checks green; no new Python modules means no new test-pair entries required; updated YAML passes the template validation that `test_shipped_smoke.py` exercises under `make test`
- `make test` -- expected: shipped-templates smoke tests pass for the updated epic.yaml and story.yaml; domain + application branch coverage at 100%

## Auto Run Result

Status: blocked
Blocking condition: failing tests pin shipped template content (AGENTS.md hard rule 6 violation)

Four tests fail after adding the `spec-gate` step to `templates/epic.yaml`. All four pin shipped template content in ways that make them incompatible with any edit to the epic template's steps:

1. `backend-api/tests/unit/application/test_graph_shipped.py::test_epic_is_the_golden_shape` — asserts the exact graph node IDs of the shipped epic template. Adding `spec-gate` inserts a new node.
2. `backend-api/tests/unit/application/templates/test_plan_shipped.py::test_epic_expands_one_frame_per_story_with_the_checkpoint_story_two_declared` — asserts `paths(epic) == EPIC_ROWS`, pinning exact row-path ordering.
3. `backend-api/tests/unit/application/templates/test_plan_shipped.py::test_an_initiative_expands_one_frame_per_epic_and_one_per_story` — same row-path pin via initiative expansion.
4. `backend-api/tests/unit/application/test_readiness_declares_no_quality_gate.py::test_the_readiness_run_reaches_its_agent_row` — asserts `agent_rows[0].story_id == '1'`, assuming no epic-level agent step precedes the story loop; `spec-gate` is now `agent_rows[0]` with `story_id=None`.

Hard rule 6: "No test may pin shipped template content (step ids, ordering, counts, graph shapes, YAML text of templates/*.yaml): shipped templates are exemplars that evolve freely, and a test that would fail on a template edit is testing the wrong thing." These tests violate that rule. As a dispatched agent I cannot revise them — that requires the Operator's ruling.

Implementation is complete; `make lint` passes; 6353 of 6357 tests pass. The four tests above must be revised (removing template-content pins, testing the same behaviour on fixture copies the tests own) before `make test` will pass.
