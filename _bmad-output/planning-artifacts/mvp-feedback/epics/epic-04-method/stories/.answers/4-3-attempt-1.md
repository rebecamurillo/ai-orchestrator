---
title: DSL dispatch forms — skill or prompt/prompt_file
type: feature
created: '2026-09-17'
status: blocked
baseline_revision: d5db0d41b59cbaad41c739eeccb48e47be4a72ad
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Agent steps in the Template DSL can only dispatch via `skill`; there is no way to supply a custom prompt string or read one from a file, limiting how non-skill-based agents can be invoked. Additionally, all-digit step ids are not caught with a specific reason, even though AD-15's dot-index bijection requires them to be rejected explicitly.

**Approach:** Add `prompt` and `prompt_file` as two new alternative dispatch forms for agent `with` blocks; validate that exactly one of the three forms is present; extend `compose_prompt` with the new forms; add a dedicated `ALL_DIGIT_STEP_ID` check in `_check_ids()`; split `compose_prompt` and its constants into a new `agent_prompt.py` sibling (the `agent.py` module is at its 400-line cap).

## Boundaries & Constraints

**Always:**
- AD-9: `compose_prompt` (now in `steps/agent_prompt.py`, re-exported from `steps/agent.py`) remains the only prompt builder; it gains a `prompt_file_content: str | None = None` keyword parameter so it stays pure — no I/O inside it.
- AD-2: `domain/` and `application/` stay pure; `agent_prompt.py` imports no I/O libraries (`os`, `shutil`, `subprocess`, `pathlib`, `httpx`, etc.); the `prompt_file` read happens in `_planned()` via `require_workspace(ctx, ctx.cwd).read(filename)` before `compose_prompt` is called.
- Exactly one of `{skill, prompt, prompt_file}` must be present in an agent step's `with` map; zero or two-or-more → `INVALID_DISPATCH_FORM` error reported at `params.line`.
- All-digit step id (e.g. `"123"`) → `ALL_DIGIT_STEP_ID` at the id key's line, checked before `is_slug` so the specific reason fires instead of the generic `INVALID_SLUG`.
- No existing test file is modified (hard rule); backward-compatible re-exports keep existing test imports (`from steps.agent import DISPATCH, compose_prompt`) working.
- No test pins shipped template content.

**Block If:** `Workspace.read()` requires an absolute path rather than a relative string path — would need a different read strategy than the pattern at `agent.py:263`.

**Never:**
- Do not add I/O imports to `agent_prompt.py`.
- Do not report both `ALL_DIGIT_STEP_ID` and `INVALID_SLUG` for the same id (the new check `continue`s past the slug check).
- Do not change the `AgentExtras` model or the `expect` / `retry` parsing — both forms already carry `expect {files, status_in}` through the existing `AgentExtras` path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| `skill` only (existing) | `with: {skill: bmad-build-auto, ...}` | DISPATCH sentence unchanged | No error |
| `prompt` only | `with: {prompt: "Do X.", ...}` | `"Do X."` as prompt base | No error |
| `prompt_file` only | `with: {prompt_file: "plan.md", ...}` + file exists in cwd | File content as prompt base | File absent: `ws.read()` returns None → base is `""` |
| Zero dispatch forms | `with: {harness: claude}` only | `INVALID_DISPATCH_FORM` at `with` map line | — |
| `skill` + `prompt` | both in `with` | `INVALID_DISPATCH_FORM` at `with` map line | — |
| `prompt` + `prompt_file` | both in `with` | `INVALID_DISPATCH_FORM` at `with` map line | — |
| All-digit step id | `id: "123"` | `ALL_DIGIT_STEP_ID` at id's line; no `INVALID_SLUG` for same line | — |
| Integer step id | `id: 123` (no quotes, YAML int) | `INVALID_SLUG` (existing path; not a string, fails `is_slug`) | — |
| `prompt_extra` + `prompt` | both in `with`; only one dispatch form | `prompt_extra` still appended after base | No error |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/model.py:87` — `INVALID_VALUE` constant; ADD `INVALID_DISPATCH_FORM = "invalid dispatch form"` and `ALL_DIGIT_STEP_ID = "all-digit step id"` immediately after it (lines 88-89)
- `backend-api/src/orchestrator/application/steps/__init__.py:70` — `KIND_META["agent"].with_keys` frozenset; ADD `"prompt"` and `"prompt_file"` to it
- `backend-api/src/orchestrator/application/templates/agent.py:42-56` — module for agent-extras checking; ADD `check_agent_dispatch_form(params: LinedMap) -> list[ValidationError]` after the existing functions; import `INVALID_DISPATCH_FORM` from model; counts `{"skill", "prompt", "prompt_file"}` ∩ set(params); if count != 1 appends `problem(params.line, INVALID_DISPATCH_FORM)`
- `backend-api/src/orchestrator/application/templates/keys.py:276-288` — `_check_with()`; ADD `if kind == AGENT_KIND: errors += check_agent_dispatch_form(params)` after the `unknown_keys` call; import `check_agent_dispatch_form` from `orchestrator.application.templates.agent` (already imported for `check_agent_extras`; extend that import)
- `backend-api/src/orchestrator/application/templates/keys.py:168-183` — `_check_ids()`; between the "id" presence check and the `is_slug` check, ADD: `if isinstance(node["id"], str) and node["id"].isdigit(): errors.append(problem(line, ALL_DIGIT_STEP_ID)); continue`; import `ALL_DIGIT_STEP_ID` from model (extend the existing model import in keys.py)
- `backend-api/src/orchestrator/application/steps/agent_prompt.py` — NEW module (no I/O imports); holds `DISPATCH`, `HALT`, `ANSWER`, `RETRY_PROMPT` constants (moved from `agent.py:90-98`); ADD `PROMPT_KEY = "prompt"` and `PROMPT_FILE_KEY = "prompt_file"`; extended `compose_prompt(with_resolved, resume_signal, previous_attempt, *, prompt_file_content: str | None = None) -> str` — base selected by: `PROMPT_KEY in with_resolved` → use value; `prompt_file_content is not None` → use content; else → DISPATCH sentence; `prompt_extra`, HALT, ANSWER clauses unchanged
- `backend-api/src/orchestrator/application/steps/agent.py:87-177` — REMOVE `DISPATCH`, `HALT`, `ANSWER`, `RETRY_PROMPT` constants and `compose_prompt` function body (moved to `agent_prompt.py`); ADD `from orchestrator.application.steps.agent_prompt import DISPATCH, PROMPT_FILE_KEY, compose_prompt` (re-exports `DISPATCH` and `compose_prompt` for backward compatibility with three existing test files that import them from `steps.agent`); EXTEND `_planned()` at line 340: before the `compose_prompt` call, read `prompt_file` when `PROMPT_FILE_KEY in ctx.with_resolved` using `require_workspace(ctx, ctx.cwd).read(str(ctx.with_resolved[PROMPT_FILE_KEY]))`, pass result as `prompt_file_content=` kwarg
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-zero.yaml` — NEW; valid agent step with no skill/prompt/prompt_file in `with` (only `harness` and `model`); `INVALID_DISPATCH_FORM` at the `with:` key line
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-multiple.yaml` — NEW; agent step with both `skill` and `prompt` in `with`; `INVALID_DISPATCH_FORM` at the `with:` key line
- `backend-api/tests/unit/application/templates/fixtures/all-digit-step-id.yaml` — NEW; template with a step carrying `id: "1"`; `ALL_DIGIT_STEP_ID` at line 4
- `backend-api/tests/unit/application/templates/test_template_validate_dispatch_form.py` — NEW test file; tests `INVALID_DISPATCH_FORM` (zero form, `skill`+`prompt`, `prompt`+`prompt_file`) and `ALL_DIGIT_STEP_ID`; follows the `read(fixture_name, templates) → assert errors == (ValidationError(...),)` pattern; imports `INVALID_DISPATCH_FORM`, `ALL_DIGIT_STEP_ID` from model
- `backend-api/tests/unit/application/steps/test_agent_prompt_forms.py` — NEW test file; tests `compose_prompt` with `prompt` base, `prompt_file_content` base, `prompt_extra` appended to each, and HALT clause applied to each; uses `resolved()` from `agent_fixtures.py` with `skill` key removed and `prompt`/`prompt_file` key added
- `backend-api/tests/unit/application/steps/test_agent_prompt_file_dispatch.py` — NEW test file; tests `AgentExecutor.execute()` with `prompt_file` in `with_resolved`; verifies the `Workspace.read(filename)` call and that the file content reaches the harness prompt — covers the new `_planned()` branch for 100% application coverage; uses existing `FakeWorkspace` and `FakeHarness` patterns from `agent_dispatch` tests

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/application/templates/model.py` -- ADD after `INVALID_VALUE` (line 87) -- `INVALID_DISPATCH_FORM = "invalid dispatch form"` and `ALL_DIGIT_STEP_ID = "all-digit step id"`
- `backend-api/src/orchestrator/application/steps/__init__.py` -- EXTEND `KIND_META["agent"].with_keys` at line 70 -- add `"prompt"` and `"prompt_file"` to the frozenset
- `backend-api/src/orchestrator/application/templates/agent.py` -- ADD `check_agent_dispatch_form` function -- counts how many of `{"skill", "prompt", "prompt_file"}` appear in params; appends `problem(params.line, INVALID_DISPATCH_FORM)` if count is not 1; import `INVALID_DISPATCH_FORM` from model
- `backend-api/src/orchestrator/application/templates/keys.py` -- EXTEND `_check_with()` when `kind == AGENT_KIND` and `_check_ids()` with all-digit pre-check -- import `check_agent_dispatch_form` (extend existing agent import), import `ALL_DIGIT_STEP_ID` (extend existing model import)
- `backend-api/src/orchestrator/application/steps/agent_prompt.py` -- CREATE -- pure module; `DISPATCH`, `HALT`, `ANSWER`, `RETRY_PROMPT` (moved); `PROMPT_KEY`, `PROMPT_FILE_KEY`; extended `compose_prompt` with `prompt_file_content` kwarg and three-branch base selection
- `backend-api/src/orchestrator/application/steps/agent.py` -- REMOVE moved constants and function body; ADD re-export import from `agent_prompt`; EXTEND `_planned()` with `prompt_file` workspace read passed as `prompt_file_content` kwarg
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-zero.yaml` -- CREATE -- fixture producing exactly one `INVALID_DISPATCH_FORM` error
- `backend-api/tests/unit/application/templates/fixtures/invalid-dispatch-form-multiple.yaml` -- CREATE -- fixture producing exactly one `INVALID_DISPATCH_FORM` error
- `backend-api/tests/unit/application/templates/fixtures/all-digit-step-id.yaml` -- CREATE -- fixture producing exactly one `ALL_DIGIT_STEP_ID` error at line 4
- `backend-api/tests/unit/application/templates/test_template_validate_dispatch_form.py` -- CREATE -- tests: zero dispatch form → one `INVALID_DISPATCH_FORM`; skill+prompt → one `INVALID_DISPATCH_FORM`; prompt+prompt_file → one `INVALID_DISPATCH_FORM`; `id: "1"` → one `ALL_DIGIT_STEP_ID` and no `INVALID_SLUG` at same line; integer `id: 1` → `INVALID_SLUG` (existing path, no new error)
- `backend-api/tests/unit/application/steps/test_agent_prompt_forms.py` -- CREATE -- tests: `prompt` form returns value directly; `prompt_file_content` form returns content; `prompt_extra` still appended for both; HALT clause appended for both when `spec_checkpoint` is true
- `backend-api/tests/unit/application/steps/test_agent_prompt_file_dispatch.py` -- CREATE -- tests `AgentExecutor.execute()` with `prompt_file` in `with_resolved`; verifies workspace read is called with the declared filename and the read content reaches the harness as the prompt; uses `FakeWorkspace` with read returning test content and existing agent dispatch fixture helpers

**Acceptance Criteria:**
- Given an agent step `with` containing exactly `skill: bmad-build-auto` (no `prompt`/`prompt_file`), when `validate()` runs, then `errors` is empty of `INVALID_DISPATCH_FORM`
- Given an agent step `with` containing `prompt: "Do X."` with no `skill` or `prompt_file`, when `validate()` runs, then `errors` is empty of `INVALID_DISPATCH_FORM`
- Given an agent step `with` containing no dispatch form keys, when `validate()` runs, then exactly one `ValidationError(reason=INVALID_DISPATCH_FORM)` is returned
- Given an agent step `with` containing both `skill: x` and `prompt: "y"`, when `validate()` runs, then exactly one `ValidationError(reason=INVALID_DISPATCH_FORM)` is returned
- Given a step with `id: "123"`, when `validate()` runs, then exactly one `ValidationError(reason=ALL_DIGIT_STEP_ID)` is returned at the id's line and no `INVALID_SLUG` error appears for that same line
- Given `compose_prompt` called with `with_resolved = {..., "prompt": "Custom."}` (no `skill`), then the return value starts with `"Custom."` and never contains the DISPATCH sentence
- Given `compose_prompt` called with `prompt_file_content="File content."` and `with_resolved` containing `"prompt_file": "plan.md"`, then the return value starts with `"File content."`
- Given `make lint`, then ruff, mypy, and import-linter all pass; no AD-2 violations; `agent_prompt.py` has a paired test module (`test_agent_prompt.py` already exists and names it)
- Given `make test`, then domain and application branch coverage stays at 100%

## Design Notes

`compose_prompt` gains `prompt_file_content: str | None = None` (the pre-read content) rather than `cwd: Path` because the function must stay pure — no I/O — so tests can exercise all dispatch paths without a filesystem. The `_planned()` call site already has a workspace handle (`require_workspace(ctx, ctx.cwd)`) and reads the file there, passing the content in. The same `ws.read(path) or ""` fallback used elsewhere in `agent.py` handles missing files.

`check_agent_dispatch_form` reports at `params.line` (the `with` map's opening line) regardless of how many forms are present, because for the zero-form case there is no key to point at, and for the multiple-form case no single key is more "wrong" than the others.

The `ALL_DIGIT_STEP_ID` check runs before `is_slug` so an id like `"123"` gets the specific, actionable reason rather than the generic `INVALID_SLUG`. The `continue` prevents both errors from firing for the same id.

## Verification

**Commands:**
- `make lint` -- expected: ruff format+lint, mypy, import-linter all green; `agent_prompt.py` satisfies test-pair rule (paired with existing `test_agent_prompt.py`)
- `make test` -- expected: all new tests green; domain + application 100% branch coverage maintained

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 1: (high 1, medium 0, low 0)
- bad_spec: 0
- patch: 0
- defer: 0
- reject: 0
- addressed_findings:
  - none

**Patch reference:** `_bmad-output/implementation-artifacts/4-3-zero-dispatch-intent-gap-patch.md`

## Auto Run Result

Status: blocked  
Blocking condition: intent gap — zero dispatch forms rule  

The `<intent-contract>` requires zero dispatch forms → `INVALID_DISPATCH_FORM`, but ~20 existing unmodifiable test fixtures contain agent steps with zero dispatch forms. Implementing zero→error would cause all of those tests to fail (hard rule: never modify existing tests). The two-or-more check is implemented and working; only the zero case conflicts.

**Unresolved questions for Operator:**

1. Should zero dispatch forms be allowed or forbidden in an agent step's `with` block?
   - If **allowed**: amend the `<intent-contract>` to read "two or more → error; zero is valid." The current implementation (`count > 1`) is correct and all tests pass.
   - If **forbidden**: authorize modification of the existing test fixtures that use agent steps with no dispatch form key (Operator exception four, with date and decision logged in each revised test).

All other parts of the story are complete and verified (make lint + make test green, 6357 passed). New source and test files are preserved as untracked files. Tracked source files reverted to baseline. Patch details: `_bmad-output/implementation-artifacts/4-3-zero-dispatch-intent-gap-patch.md`.

## Human Answer

2026-09-17T17:03:07.815713Z · operator

AUTHORIZE modifications of teixsint fixture, aligning to new requirements
