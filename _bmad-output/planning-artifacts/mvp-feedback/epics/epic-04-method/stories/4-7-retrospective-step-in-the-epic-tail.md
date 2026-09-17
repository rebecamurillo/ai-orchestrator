---
title: Retrospective step in the epic tail
type: feature
created: '2026-09-17'
status: done
baseline_revision: 90efc6a3f2bf9c2790dcc9c25537c8b5997dd528
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** After e2e passes in the epic tail, there is no automated retrospective step — the operator must run bmad-retrospective manually, and the report is never committed to the branch.

**Approach:** Insert a `retro` agent step (skill: bmad-retrospective) and a `commit-retro` git.commit step between the `e2e` step and the `push` step in `templates/epic.yaml`, so every epic run produces a committed retrospective report before the branch is pushed. No application code changes — template YAML and one TDD test file only.

## Boundaries & Constraints

**Always:**
- Exemplar freeze (AGENTS.md rule 6): `tests/unit/application/templates/fixtures/exemplars/epic.yaml` is NOT updated; `test_graph_shipped.py`, `test_plan_shipped.py`, `test_shipped_templates.py` continue using the frozen snapshot unchanged.
- The TDD test file must FAIL before the template changes and PASS after; it tests the shipped template directly, following `test_e2e_generation_gate.py`'s precedent.
- Voice on commit message: `"retro: epic retrospective (orchestrator)"` verbatim.
- The `retro` step is placed between `e2e` and `push`; the retro report is committed before the branch is pushed so it appears in the compare link.
- No trajectory row (AD-19) for the retro: the retro is committed as a file in the working folder, not recorded as a second data-collection path. Do not add any database writes, API routes, or trajectory insertions for the retro.
- The session-interrogation retro is NOT built: it stays a recorded follow-up note. Do not add any code that reads harness session logs or builds a separate interrogation report.
- The TDD test documents the skill-name anchor ("bmad-retrospective") in its docstring per `test_e2e_generation_gate.py` precedent.

**Block If:** Any contradiction about where the retro step must be positioned (before vs. after push) that cannot be resolved from SPEC.md and the stories.yaml description alone.

**Never:**
- Do not modify `fixtures/exemplars/epic.yaml`.
- Do not modify any existing test file.
- Do not add Python source modules that require new test-pair entries.
- Do not add any trajectory or data-collection path for the retro.
- Do not build the session-interrogation retrospective.

</intent-contract>

## Code Map

- `templates/epic.yaml:73-87` — current tail after e2e: `push` (git.push, line ~79), `link` (pr.link), `done-checkpoint` (checkpoint, human); the new `retro` and `commit-retro` steps insert between the `e2e` step and the `push` step, maintaining 2-space indent
- `templates/epic.yaml:73-77` — the `e2e` step (shell, `on_fail: {redispatch: gen-e2e, max: 2}`); `retro` goes immediately after this block
- `templates/repo-init.yaml:34-35` — reference: `id: context-review, uses: checkpoint, gate: human` — the pattern for `gate: human`; retro uses `gate: liveness` (not deterministic: harness output)
- `backend-api/tests/unit/application/templates/test_e2e_generation_gate.py:1-93` — the exact `seeded()` helper pattern to replicate (imports, `SHIPPED_DIR`, `AT`, `seeded()` function body); the new test follows this file exactly
- `backend-api/tests/unit/application/templates/test_epic_tail_order.py` — read-only reference; confirms `seeded()` helper pattern and ruff-format exclusion in `pyproject.toml`
- `backend-api/src/orchestrator/application/steps/__init__.py` — `AGENT_KIND = "agent"` constant used in TDD test assertions
- `backend-api/src/orchestrator/application/templates/model.py` — `Step` class imported in TDD test
- `backend-api/pyproject.toml` — `[tool.ruff.format] exclude` already contains `test_epic_tail_order.py`; new test file follows same formatting so no exclusion needed

## Tasks & Acceptance

**Execution (TDD order — test first, then template):**

- `backend-api/tests/unit/application/templates/test_retro_step.py` -- CREATE first -- TDD test; replicate `seeded()` helper from `test_e2e_generation_gate.py` exactly (same imports: `AGENT_KIND`, `Step`, `validate`, `TemplatePorts`, `seed_shipped`, `load_shipped_templates`, `FakeClock`, `FakeUnitOfWork`, `FakeTemplateVersionRepository`; `SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"`; `AT = datetime(2026, 9, 10, tzinfo=UTC)`; same `seeded()` body); write one test function `test_epic_has_retro_step_committed_before_push` that: (a) calls `seeded()` and loads the latest shipped epic version via `max(templates.list_versions("epic"))`; (b) calls `validate(stored.yaml, templates=templates)` and asserts `result.template is not None`; (c) collects `top_level_steps = [s for s in result.template.steps if isinstance(s, Step)]`; (d) asserts there is at least one agent step with `("skill", "bmad-retrospective") in s.params` with a diagnostic message naming the found top-level step IDs; (e) captures `retro_id = retro_steps[0].id` and `retro_idx = top_level_steps.index(retro_steps[0])`; (f) finds the `push` step: asserts there is exactly one step with `s.id == "push"` and captures `push_idx = top_level_steps.index(push_step)`, asserting `retro_idx < push_idx` with a diagnostic message; (g) asserts there is a `git.commit` step in `top_level_steps[retro_idx + 1 : push_idx]` with a diagnostic message; docstring must say: "story 4-7 (2026-09-17): retrospective step in the epic tail — a retro agent step (skill: bmad-retrospective) and a commit-retro step precede push; the skill name 'bmad-retrospective' is an architectural anchor and must be updated if the skill is renamed"

- `templates/epic.yaml` -- INSERT two steps between `e2e` and `push` -- immediately after the `- id: e2e` block (after `gate: deterministic` on that block, before `- id: push`), add `retro` and `commit-retro` maintaining 2-space indent:
  ```yaml
    - id: retro
      uses: agent
      with:
        harness: "{{harness}}"
        model: "{{model}}"
        skill: bmad-retrospective
        args: { folder: "{{spec_folder}}" }
      timeout_min: 30
      gate: liveness

    - id: commit-retro
      uses: git.commit
      with: { message: "retro: epic retrospective (orchestrator)" }
      gate: deterministic
  ```

**Acceptance Criteria:**
- Given the shipped `templates/epic.yaml` with `retro` and `commit-retro` added, when `seed_shipped` runs and `validate()` is called on the result, then no errors and no unvalidated steps are returned
- Given the shipped epic template, when the parsed template's top-level steps are inspected, then there exists an agent step with `("skill", "bmad-retrospective") in step.params`, followed by a `git.commit` step, both with indices lower than the `push` step's index
- Given `test_retro_step.py` run BEFORE the template changes, then `test_epic_has_retro_step_committed_before_push` fails with an assertion error (no agent step with bmad-retrospective skill)
- Given `make test` run after the template changes, then `test_retro_step.py` passes and all existing tests including `test_shipped_smoke.py`, `test_epic_tail_order.py`, and `test_e2e_generation_gate.py` continue to pass; domain + application branch coverage stays at 100%
- Given `make lint`, then all checks pass; no new Python source modules are introduced, so no new test-pair entries are required
- Given a committed `retro` and `commit-retro` in the epic tail, when a full epic run completes, then the retrospective report is committed to the branch before `push` runs

## Design Notes

`retro` uses `gate: liveness` (same as gen-e2e and spec-gate): the orchestrator monitors the harness for activity rather than verifying a deterministic output. The `commit-retro` step that follows provides the structural guarantee that something was written before the branch is pushed.

No `expect.files` is declared on `retro` — the report filename in the target repo's working directory is not known at template-design time (consistent with gen-e2e's design rationale). The `commit-retro` step is the quality gate.

The `retro` step is positioned after `e2e` and before `push` so that the retrospective report is included in the pushed branch and visible in the compare link that `link` records. This matches SPEC.md's epic-tail ordering.

The frozen exemplar (`fixtures/exemplars/epic.yaml`) intentionally does NOT get `retro` or `commit-retro`. The exemplar is a snapshot decoupled from the shipped file; the graph tests assert properties of that snapshot, and the snapshot is only updated under deliberate Operator authorization.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter, env-contract, test-pairs all green; no new Python source modules introduced, so no new test-pair entries needed
- `make test` -- expected: new `test_retro_step.py` green; all 6359+ existing tests pass; domain + application branch coverage stays at 100%

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 0, low 1)
- defer: 0
- reject: 14
- addressed_findings:
  - `[low]` `[patch]` Test only asserted that the retro step precedes push, not that it follows e2e — the intent says "between e2e and push" (two-sided constraint); added `e2e_idx < retro_idx` assertion in `test_retro_step.py`, finding the e2e step by `s.id == "e2e"` with documented anchor caveat

## Auto Run Result

**Summary:** Inserted `retro` (agent step, skill: bmad-retrospective, gate: liveness) and `commit-retro` (git.commit, gate: deterministic) steps between `e2e` and `push` in `templates/epic.yaml`, so every epic run produces a committed retrospective report before the branch is pushed. Created `test_retro_step.py` to verify the behavioral invariant (TDD order: test first, template second). One low patch applied during review: added the missing `e2e_idx < retro_idx` assertion to pin the two-sided "between e2e and push" constraint.

**Files changed:**
- `templates/epic.yaml` — inserted `retro` and `commit-retro` before `push`; exemplar frozen copy unchanged
- `backend-api/tests/unit/application/templates/test_retro_step.py` — new TDD test; verifies retro agent step with skill bmad-retrospective exists, follows e2e (patched), is followed by a git.commit step, and both precede push

**Review findings breakdown:** 1 patch applied (0 high, 0 medium, 1 low); 0 deferred; 14 rejected.

**Follow-up review recommended:** false — score 3×0 medium + 1×1 low = 1 < 5.

**Verification performed:**
- `make lint`: PASS — ruff format+lint, mypy, import-linter, env-contract, test-pairs all green
- `make test`: PASS — 6360 backend tests passed (23 skipped); 1348 web-client tests passed; domain+application at 100% branch coverage

**Residual risks:**
- The frozen exemplar (`fixtures/exemplars/epic.yaml`) does not include `retro` or `commit-retro`; graph-shape tests assert the frozen exemplar's shape and will not catch changes to the shipped template. Covered structurally by `test_shipped_smoke.py` and behaviorally by `test_retro_step.py`.
- The test locates the e2e step by `s.id == "e2e"` — a documented architectural anchor that must be updated if the e2e step is renamed.
- The `commit-retro` step will fail on an empty git index if the retro skill writes nothing; this matches the `commit-e2e` precedent and is expected to be caught by the skill's own output guarantee.
