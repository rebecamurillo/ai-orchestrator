---
title: DSL dispatch forms — skill or prompt/prompt_file
type: feature
created: '2026-09-17'
status: in-progress
baseline_revision: 9cb40a30d3e17b7aec1e192cdda3e0fe53115def
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The agent step DSL has no `prompt` or `prompt_file` dispatch form; an author who writes one gets `unknown key`, and the executor's `_planned()` always calls the skill-only local `compose_prompt`, so custom-prompt dispatch never reaches the harness. All-digit step ids (e.g. `"1"`) are also accepted by `validate.py`, which would break AD-15's dot-index bijection.

**Approach:** Add `prompt` and `prompt_file` to agent's `with_keys`; wire `INVALID_DISPATCH_FORM` (more than one dispatch key present) and `ALL_DIGIT_STEP_ID` into `validate.py`; update `_planned()` to call `agent_prompt.compose_prompt`, which already handles all three forms, reading `prompt_file` content from the workspace first.

## Boundaries & Constraints

**Always:**
- AD-9: `agent_prompt.compose_prompt` remains the only prompt builder; `_planned()` calls it for all three forms.
- AD-2: `domain/` and `application/` stay pure — workspace read (via port) stays in `_planned()`, which is already the I/O-permitted application layer.
- AD-15: `ALL_DIGIT_STEP_ID` fires before `INVALID_SLUG` for the same id; the `continue` in `_check_ids()` prevents both from firing for the same line.
- Zero dispatch forms (no `skill`, `prompt`, or `prompt_file` key in `with`) is valid — the check fires only when more than one is present.
- The local `compose_prompt` in `agent.py` stays (two existing tests import it by name); simplify its body to delegate to `agent_prompt.compose_prompt` rather than removing it.
- Exemplar freeze: no unit or e2e test pins shipped template content.
- `agent.py` must stay ≤ 400 lines after all changes; simplifying the local `compose_prompt` creates room.

**Block If:** Any contradiction between the test assertions in the pre-written test files and the validation logic cannot be resolved from the story description and SPEC.md alone.

**Never:**
- Do not modify or delete any existing test file.
- Do not create new test files — all tests are pre-written on this branch.
- Do not pin shipped template content in tests.
- Do not change the API error response shape or the `{line, reason}` format.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Zero dispatch forms | Agent `with` has none of `skill`, `prompt`, `prompt_file` | No `INVALID_DISPATCH_FORM` error | — |
| Single form — skill | `with.skill: bmad-build-auto` only | No `INVALID_DISPATCH_FORM` | — |
| Single form — prompt | `with.prompt: Do X.` only | No `INVALID_DISPATCH_FORM` | — |
| Single form — prompt_file | `with.prompt_file: plan.md` only | No `INVALID_DISPATCH_FORM` | — |
| Two dispatch forms | `skill` + `prompt` (or any two) | Exactly one `INVALID_DISPATCH_FORM` at the `with` line | — |
| Three dispatch forms | `skill` + `prompt` + `prompt_file` | Exactly one `INVALID_DISPATCH_FORM` at the `with` line | — |
| All-digit quoted id `"1"` | Step `id: "1"` (YAML str) | `ALL_DIGIT_STEP_ID` at id line; no `INVALID_SLUG` for same line | — |
| Unquoted integer id `1` | Step `id: 1` (YAML int, not a str) | `INVALID_SLUG` only; no `ALL_DIGIT_STEP_ID` | — |
| `prompt_file` present, file exists | `with.prompt_file: plan.md`; workspace has the file | File content used as prompt base by harness | — |
| `prompt_file` present, file absent | `with.prompt_file: plan.md`; workspace lacks file | Empty string used as prompt base (`ws.read()` returns None → `or ""`) | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/model.py:87` — `INVALID_VALUE` constant (last reason); add `ALL_DIGIT_STEP_ID` and `INVALID_DISPATCH_FORM` immediately after
- `backend-api/src/orchestrator/application/steps/__init__.py:67-71` — agent `KindMeta` row; `with_keys` frozenset at line 70 needs `"prompt"` and `"prompt_file"` added
- `backend-api/src/orchestrator/application/templates/keys.py:46-61` — model imports; add `ALL_DIGIT_STEP_ID` and `INVALID_DISPATCH_FORM`
- `backend-api/src/orchestrator/application/templates/keys.py:168-183` — `_check_ids()`: insert all-digit str check (`isinstance(node["id"], str) and node["id"].isdigit()`) before the `is_slug` check (line 177); use `continue` to suppress `INVALID_SLUG` on the same line
- `backend-api/src/orchestrator/application/templates/keys.py:276-288` — `_check_with()`: add `if kind == AGENT_KIND: errors += _check_dispatch_form(params, line)` after the `unknown_keys` call; add `_DISPATCH_KEYS` module constant and `_check_dispatch_form(params, with_line)` helper near the bottom (or adjacent to `_check_with`)
- `backend-api/src/orchestrator/application/steps/agent.py:44-71` — imports; add `from orchestrator.application.steps import agent_prompt`; remove named imports `ANSWER_EVENT`, `ANSWER_KEY`, `CONDITION_KEY` (from agent_answer) and `PROMPT_EXTRA_KEY` (from agent_row) — all only used in the old `compose_prompt` body
- `backend-api/src/orchestrator/application/steps/agent.py:87` — `SKILL_KEY = "skill"` — unused after body simplification; remove
- `backend-api/src/orchestrator/application/steps/agent.py:94-95` — `HALT` and `ANSWER` constants — unused after body simplification; remove both lines
- `backend-api/src/orchestrator/application/steps/agent.py:151-177` — local `compose_prompt`; keep signature and shorten docstring; replace body (lines 161-177) with `return agent_prompt.compose_prompt(with_resolved, resume_signal, previous_attempt)`
- `backend-api/src/orchestrator/application/steps/agent.py:329-343` — `_planned()`; replace the single `prompt = compose_prompt(...)` call with: (1) compute `prompt_file_content = require_workspace(ctx, ctx.cwd).read(str(ctx.with_resolved[agent_prompt.PROMPT_FILE_KEY])) or ""` when `agent_prompt.PROMPT_FILE_KEY in ctx.with_resolved` else `None`; (2) call `agent_prompt.compose_prompt(ctx.with_resolved, agent_answer.resolved_signal(ctx), previous, prompt_file_content=prompt_file_content)`
- `backend-api/src/orchestrator/application/steps/agent_prompt.py:39-44` — `PROMPT_FILE_KEY = "prompt_file"` (line 41), `compose_prompt` (lines 47-84) — **already implemented; read-only reference for implementer**
- `backend-api/tests/unit/application/templates/test_template_validate_dispatch_form.py` — **pre-written; must not be modified**; all assertions drive the implementation above
- `backend-api/tests/unit/application/steps/test_agent_prompt_forms.py` — **pre-written; must not be modified**
- `backend-api/tests/unit/application/steps/test_agent_prompt_file_dispatch.py` — **pre-written; must not be modified**
- `backend-api/tests/unit/application/steps/test_agent_prompt.py` — **existing anchor; must not be modified**; imports `compose_prompt` from `agent` — the delegating body must satisfy its assertions
- `backend-api/tests/unit/application/templates/fixtures/all-digit-step-id.yaml` — id `"1"` at line 4; `ALL_DIGIT_STEP_LINE = 4` in the test file confirms the expected line
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-zero.yaml` — all three dispatch forms (`skill` + `prompt` + `prompt_file`)
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-multiple.yaml` — two forms (`skill` + `prompt`)

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/application/templates/model.py` -- ADD two constants after line 87 (`INVALID_VALUE`) -- `ALL_DIGIT_STEP_ID = "all-digit step id"` and `INVALID_DISPATCH_FORM = "invalid dispatch form"`
- `backend-api/src/orchestrator/application/templates/keys.py` -- ADD imports `ALL_DIGIT_STEP_ID` and `INVALID_DISPATCH_FORM` from `orchestrator.application.templates.model`; in `_check_ids()` insert `if isinstance(node["id"], str) and node["id"].isdigit(): errors.append(problem(line, ALL_DIGIT_STEP_ID)); continue` before the `is_slug` check (after `line = key_line(node, "id", node.line)`); add module-level `_DISPATCH_KEYS = frozenset({"skill", "prompt", "prompt_file"})` and function `_check_dispatch_form(params: LinedMap, with_line: int) -> list[ValidationError]` that returns `[problem(with_line, INVALID_DISPATCH_FORM)]` when `sum(1 for k in params if k in _DISPATCH_KEYS) > 1`, else `[]`; in `_check_with()` for agent kind compute `allowed = KIND_META[kind].with_keys | _DISPATCH_KEYS` (so `prompt`/`prompt_file` don't generate `UNKNOWN_KEY`) and call `errors += _check_dispatch_form(params, line)` — do NOT modify `KIND_META["agent"].with_keys` directly (see Design Notes)
- `backend-api/src/orchestrator/application/steps/agent.py` -- SIMPLIFY AND EXTEND -- add `from orchestrator.application.steps import agent_prompt` to imports; remove named imports `ANSWER_EVENT`, `ANSWER_KEY`, `CONDITION_KEY` from the `agent_answer` import group; remove `PROMPT_EXTRA_KEY` from the `agent_row` import group; remove constants `SKILL_KEY`, `HALT`, `ANSWER` (all unused after body simplification); replace `compose_prompt` body with a single-line delegate `return agent_prompt.compose_prompt(with_resolved, resume_signal, previous_attempt)`; in `_planned()` replace `prompt = compose_prompt(ctx.with_resolved, agent_answer.resolved_signal(ctx), previous)` with the three-line prompt_file read + `agent_prompt.compose_prompt` call described in the Code Map

**Acceptance Criteria:**
- Given an agent step `with` block containing `skill: bmad-build-auto` and `prompt: Do X.`, when `validate()` runs on the template, then exactly one `INVALID_DISPATCH_FORM` error is returned
- Given an agent step `with` block containing only `harness: claude` and `model: claude-opus-5` (zero dispatch forms), when `validate()` runs, then no `INVALID_DISPATCH_FORM` error appears in the result
- Given a template step with `id: "1"` (quoted digit string), when `validate()` runs, then exactly one `ALL_DIGIT_STEP_ID` error appears at line 4, and no `INVALID_SLUG` error appears for that same line
- Given `AgentExecutor.execute()` called with `with_resolved` containing `prompt_file: plan.md` and a workspace holding `plan.md`, when the executor runs, then the file content reaches the harness as the prompt base
- Given `AgentExecutor.execute()` called with `prompt_file: plan.md` and a workspace that lacks the file, when the executor runs, then the harness prompt does not contain the DISPATCH sentence (`"Run the skill"`)
- Given `make lint`, then ruff, mypy, and import-linter all pass; `agent.py` is ≤ 400 lines
- Given `make test`, then domain and application branch coverage remains at 100%

## Design Notes

`_check_dispatch_form` fires after `unknown_keys` within `_check_with`, so a step with two dispatch forms and an additional unknown key reports both error types — consistent with the "every problem found in one pass" invariant.

`KIND_META["agent"].with_keys` is NOT modified to include `"prompt"` or `"prompt_file"`. `test_step_kind_registry.py` pins the exact spine table values; modifying `with_keys` would break it, and modifying that test requires Operator authorization (AGENTS.md exception 4). Instead, `_check_with()` computes `allowed = KIND_META[kind].with_keys | _DISPATCH_KEYS` for agent steps, so `prompt`/`prompt_file` are accepted without appearing in the metadata table. The `_DISPATCH_KEYS` constant (`{"skill","prompt","prompt_file"}`) serves double duty: extending the allowed set and counting for the dispatch-form check.

The local `compose_prompt` in `agent.py` becomes a one-line delegate. Its signature is unchanged so `test_agent_prompt.py` and `test_agent_reject_halts_again.py` continue to pass without modification. `DISPATCH` and `RETRY_PROMPT` stay in `agent.py` because tests import `DISPATCH` directly.

`_planned()` sets `prompt_file_content = ws.read(filename) or ""` when the `prompt_file` key is present. The `or ""` converts a missing-file `None` to an empty string — `agent_prompt.compose_prompt` fires the `prompt_file_content is not None` branch with an empty base, matching `test_absent_file_gives_empty_prompt_base`.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter, env-contract, test-pairs all green; `agent.py` ≤ 400 lines
- `make test` -- expected: all new pre-written tests green; domain + application 100% branch coverage maintained
