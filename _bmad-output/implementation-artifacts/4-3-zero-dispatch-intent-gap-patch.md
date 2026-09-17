# Story 4-3 — Intent Gap Patch

**Story:** DSL dispatch forms — skill or prompt/prompt_file  
**Blocked on:** zero-dispatch-forms rule conflict  
**Date saved:** 2026-09-17

## The conflict

The `<intent-contract>` states: "Exactly one of `{skill, prompt, prompt_file}` must be present in an agent step's `with` map; zero or two-or-more → `INVALID_DISPATCH_FORM`."

The implementation uses `count > 1` (only two-or-more is an error; zero is valid) because approximately 20+ existing unmodifiable test fixtures contain agent steps with zero dispatch forms (only `harness`/`model` in `with`). Making zero → error would cause all of those tests to fail. Hard rule: never modify existing test files.

## Unresolved questions for Operator

1. **Product decision required:** Should zero dispatch forms be allowed or forbidden in an agent step's `with` block?
   - If **allowed**: amend the `<intent-contract>` to read "two or more → `INVALID_DISPATCH_FORM`; zero is valid (non-story dispatch use case)". The existing implementation (`count > 1`) is correct.
   - If **forbidden**: authorize modification of the approximately 20+ existing test fixtures that have agent steps with no dispatch form key, under exception four of the anchor rule (Operator-level change with date and decision logged in each revised test).

2. **Fixtures that use zero dispatch forms (examples):** Any agent step fixture in `tests/unit/application/templates/` or `tests/unit/application/steps/` that has `uses: agent` with only `harness` and/or `model` in `with:` (no `skill`, `prompt`, or `prompt_file`).

## What was implemented

All other parts of the story are complete and passing:
- `agent_prompt.py` module created (pure, no I/O)
- `compose_prompt` extended with `prompt` and `prompt_file_content` bases
- `ALL_DIGIT_STEP_ID` check added before `is_slug` in `_check_ids()`
- `INVALID_DISPATCH_FORM` and `ALL_DIGIT_STEP_ID` constants added to `model.py`
- `check_agent_dispatch_form` implemented (two-or-more → error)
- `AGENT_DISPATCH_KEYS` extends allowed set in `_check_with()` without touching `with_keys`
- `_planned()` extended with `prompt_file` workspace read
- All new test files pass; make lint and make test green (6357 passed)

## New files created (remain untracked)

- `backend-api/src/orchestrator/application/steps/agent_prompt.py`
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-zero.yaml`
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-multiple.yaml`
- `backend-api/tests/unit/application/templates/fixtures/all-digit-step-id.yaml`
- `backend-api/tests/unit/application/templates/test_template_validate_dispatch_form.py`
- `backend-api/tests/unit/application/steps/test_agent_prompt_forms.py`
- `backend-api/tests/unit/application/steps/test_agent_prompt_file_dispatch.py`

The tracked source files (`agent.py`, `templates/agent.py`, `keys.py`, `model.py`) have been reverted to baseline.
