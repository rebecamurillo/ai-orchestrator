---
title: 'DSL v1 parser and validator'
type: 'feature'
created: '2026-09-05'
status: 'done'
baseline_revision: '7cea1a3601ecc3aa1e254df56f00f02a2822e73b'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-03-templates/briefs/3-1-dsl-v1-parser-and-validator.md'
warnings: ['oversized']
deferred:
  - summary: >-
      A step kind's essential `with` key is not required, so an unrunnable step validates green.
    evidence: |-
      `KindMeta.with_keys` is accepted-only, never required. `uses: shell` with no `command`,
      `git.commit` with no `message` and `agent` with no `harness` all validate with zero
      errors and fail only at dispatch. The story's key table names accepted keys and says
      nothing about required ones, so this was out of scope here; `KindMeta` would carry it
      as a `required_keys` column.
    location: >-
      backend-api/src/orchestrator/application/steps/__init__.py
    severity: medium
  - summary: >-
      The loader has no input-size, alias-expansion or duplicate-key guard on operator YAML.
    evidence: |-
      `LineLoader` inherits `SafeLoader`'s alias and merge handling unbounded, so an
      alias-expansion payload is materialised before any checker runs; and a mapping that
      repeats a key silently keeps the last, so a second `steps:` or `version:` overrides the
      first with no error. Story 3.3 exposes `POST /templates/{name}/validate`, which is where
      the guard belongs.
    location: >-
      backend-api/src/orchestrator/application/templates/lines.py
    severity: medium
  - summary: >-
      A version literal that is an integer but not a valid one reports `non-literal version`.
    evidence: |-
      `version: 0`, `-1` and `true` all report `non-literal version`, which tells the Operator
      the value is not a literal when the real problem is that it is not a positive integer.
      The frozen 27-reason vocabulary has no "invalid version" phrase, so correcting this
      needs an operator ruling on the wording.
    location: >-
      backend-api/src/orchestrator/application/templates/keys.py
    severity: low
  - summary: >-
      A callee's gateless steps never reach the caller's `unvalidated` report.
    evidence: |-
      A `uses: template` step is deliberately not a row, so validating `initiative@1` reports
      no gateless steps even though the expanded plan contains the callee's. NFR-2 says a step
      with no declared gate is never silently green; under composition that currently holds
      per file, not per plan. Story 3.4 (graph) and Epic 4 (planner) are where the expanded
      view exists.
    location: >-
      backend-api/src/orchestrator/application/templates/keys.py
    severity: medium
  - summary: >-
      Depth and cycle detection trust `TemplateVersion.calls`, which nothing in this story verifies.
    evidence: |-
      The traversal below the root reads the pinned `calls` list rather than re-parsing the
      callee, and `hash` is carried but never compared with `yaml`. If story 3.3 writes a
      stale or wrong `calls` list, the validator reports the wrong depth and misses cycles.
      The port carries no documented invariant tying `calls` to `yaml`.
    location: >-
      backend-api/src/orchestrator/domain/ports/templates.py
    severity: medium
  - summary: >-
      `ParsedTemplate.steps` is an undiscriminated union, forcing isinstance narrowing downstream.
    evidence: |-
      `tuple[Step | ForEach, ...]` carries no tag, which already required a `type: ignore` in
      this story's own tests and will push isinstance narrowing through story 3.4's graph
      builder and the Epic 4 planner. A literal `kind` field or separate accessors would keep
      the union honest.
    location: >-
      backend-api/src/orchestrator/application/templates/model.py
    severity: low
  - summary: >-
      Enum bindings across a template call are checked by type only, not by value set.
    evidence: |-
      A caller `enum` input binds a callee `enum` input on type equality alone, so two enums
      with incompatible value sets pass, and a bare literal bound to a callee `enum` is not
      checked against that enum's `values`. The failure surfaces only when the callee runs.
    location: >-
      backend-api/src/orchestrator/application/templates/calls.py
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Nothing in the repository parses a Template. Every later epic — the planner, the graph builder, the versions API, the editor — needs one function that reads DSL v1 YAML and returns either a parsed tree or every problem in the file named by line and reason (FR-5, AD-15), and one registry that is the only enumeration of step kinds (AD-9).

**Approach:** Add `application/templates/` (a line-recording YAML load, a frozen parsed tree, and four checkers assembled by `validate()`), `application/steps/__init__.py` holding `KIND_META`, and the read-only `TemplateVersionRepository` port with its entity and fake, so cross-template calls resolve without I/O in the application layer.

## Boundaries & Constraints

**Always:**
- `validate()` in `application/templates/validate.py` is the only public entry point; `POST /templates/.../validate`, `plan_run` and `graph.py` will call it and nothing else parses Template YAML (AD-15).
- Pure over ports: `yaml` is the only third-party import; callees are reached only through `TemplateVersionRepository`. No `os`, `subprocess`, `httpx`, `sqlalchemy`, `fastapi` (AD-2, import-linter).
- `application/steps/__init__.py` is the sole enumeration of kinds; the validator reads `KIND_META` and enumerates no kind itself (AD-9). No `if kind == ...` outside it.
- Every error is collected in one pass. `validate()` never raises on bad input — malformed YAML is an error record, not an exception.
- Errors are returned sorted by `line`; Python's stable sort preserves discovery order within a line, so the output is deterministic.
- `result.template` is `None` whenever `errors` is non-empty.
- Existing anchors are read-only: add new test modules, never edit `tests/unit/*` that already exist, any `AGENTS.md`, `SPEC.md`, or `stories.yaml`.
- Checkable limits hold: module <= 400 lines, function <= 50 statements, complexity <= 10, line length 100, no `print`, no `pragma: no cover`, `mypy --strict` clean.
- 100 % branch coverage over `domain/` and `application/` is a `make test` gate for the whole package, not just this story's files.

**Block If:**
- The reason-string table below cannot be satisfied because a rule in the brief's key table contradicts `ARCHITECTURE-SPINE.md` — report `blocked`, do not pick a side.
- Landing the story would require editing an existing test file, `AGENTS.md`, `SPEC.md`, or `stories.yaml`.

**Never:**
- No storage, no endpoints, no Pydantic API schemas, no Alembic revision (3.3). No graph (3.4). No planner, no expansion, no executors (Epic 4). No shipped YAML under `templates/` (3.2).
- No `StepExecutor` implementations — `KIND_META` is metadata only this story.
- No deep type checking inside `expect` / `retry` beyond sub-key membership and `status_in` tokens.
- No re-validation of a callee's own body: a stored version was validated when it was saved.
- No second fake for a port that already has one; no `pragma: no cover`; no new `exclude_lines`/`omit` in `pyproject.toml`.

## I/O & Edge-Case Matrix

`validate(yaml_text, *, templates) -> ValidationResult{template, errors, unvalidated}`.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Minimal valid | one `shell` step with `gate: deterministic` | `errors` empty, `unvalidated` empty, `template` is a `ParsedTemplate` with `KIND_META` resolved on the step | none |
| `run:` sugar | `run: "make test"` | step parses as `uses: shell`, `with.command == "make test"` | none |
| Missing gate | second step has no `gate` | `errors` empty, `unvalidated == ("<path>",)`, `template` is built | not an error (NFR-2) |
| Unknown top-level key | `schedule: nightly` | one error | `unknown key` at that key's line |
| Non-literal version | `version: "1"` or `version: "{{v}}"` | one error | `non-literal version` |
| `uses` and `run` | both on one step | one error | `uses and run on the same step` |
| Unknown kind | `uses: rocket`; also `uses: plan.check` (planner-only) | one error | `unknown kind` |
| Unbound name | `{{missing}}` inside `with` | one error | `unbound variable` |
| Entity field | `{{repository.secret}}` | one error | `unknown field` |
| Expression grammar | `{{story.title \| upper}}` | one error | `expression syntax` |
| Second / nested `for_each` | two at top level; one inside another's `steps` | one error each | `second for_each`; `nested for_each` |
| Reserved key | `parallel: 2` | one error | `parallel is reserved` |
| Call carries timing | `uses: template` with `timeout_min` (or `on_fail`) | one error | `timeout_min or on_fail on a template call` |
| Callee absent | `templates.get(name, version)` returns `None` | one error | `callee not found` |
| Callee inputs | wrong input name; caller `number` bound to callee `path` | one error each | `callee input mismatch` |
| Depth | chain `a -> b -> c -> d` | one error | `call depth over 3` |
| Cycle | `a -> b -> a` | one error | `call cycle` |
| Duplicate id | two steps share an `id` | one error | `duplicate step id` |
| Bad redispatch | `on_fail: {redispatch: verify, max: 1}`, `verify` not an earlier `agent` step | one error | `redispatch target not an earlier agent step` |
| Bad gate | `gate: green` | one error | `invalid gate` |
| Three independent errors | on three different lines | all three returned, sorted by line | as each reason |
| Malformed YAML | unparseable text, empty text, or a root that is not a mapping | exactly one error, `template is None` | `invalid yaml` at the mark's line, or line 1 |

</intent-contract>

## Code Map

Read-only anchors that decide whether this lands (do not edit any of them):

- `backend-api/tests/unit/test_source_limits.py` — module <= 400 lines, no `print`, no `datetime.now` in `domain`/`application`. This is why `validate.py` is split into sibling modules.
- `backend-api/tests/unit/test_coverage_gates.py` — asserts `make test` holds `src/orchestrator/{domain,application}/*` to `--fail-under=100`, that no source module contains `pragma: no cover`, and that `pyproject.toml` gains no `omit`/`exclude_lines`.
- `backend-api/tests/unit/test_layering.py` + `pyproject.toml` `[tool.importlinter]` — contracts `AD-2 layers: ...` and `AD-2 forbidden: application imports no framework, no I/O`; forbidden list is `fastapi sqlalchemy dbos subprocess os shutil httpx langfuse git cryptography`. `yaml` is not forbidden.
- `scripts/check_test_pairs.py` (+ `backend-api/tests/unit/test_check_test_pairs.py`) — every source module except `__init__.py` and the top `main.py` must be imported by some module under `tests/unit/`. `application/steps/__init__.py` is exempt from pairing but not from coverage.
- `Makefile:39` — `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100`.

Patterns to copy:

- `backend-api/src/orchestrator/domain/ports/clock.py` — port style: module docstring naming the AD rule, adapter and fake; `from __future__ import annotations`; `@runtime_checkable class X(Protocol)`; sync methods with a docstring and a bare `...`.
- `backend-api/src/orchestrator/domain/ports/repositories.py` — a repository Protocol whose reads return `Entity | None`; "deciding that a missing X is `NotFound` is a rule, and rules live in `application/`".
- `backend-api/src/orchestrator/domain/entities/project.py` — entity style: pydantic v2 `BaseModel`, `model_config = ConfigDict(frozen=True)`, `tuple[X, ...]` collections, `Literal` aliases, `#:` comments on module constants, no `Field` validators.
- `backend-api/src/orchestrator/application/use_cases/projects.py` — application style: module-level functions, long rule-enumerating module docstring, `_leading_underscore` helpers under a `# --- ... ---` banner.
- `backend-api/tests/unit/fakes/projects.py:48` `FakeRepositoryRepository` — the shape to copy for the new fake (dict store, `add()`, `get()` returning `None`).
- `backend-api/tests/unit/test_repository_ports.py` — the `isinstance(fake, Port)` check and the "the frozen module cannot be extended, so this is its own test module" precedent.
- `backend-api/src/orchestrator/api/errors.py` `ProblemError{template, version, line, path, reason}` — the API shape 3.3 will map `ValidationError` onto. Note `version` is `str | None` there and `int | None` here; 3.3 owns the conversion.

Requirements sources already distilled into this spec (no need to re-read): the brief (binding key table, reason list, ACs), `ARCHITECTURE-SPINE.md` AD-2/AD-9/AD-15/AD-18 and its "Shipped kinds" table (the `KIND_META` values), `template-dsl-draft.md` sections 2-3 (step vocabulary; `expect`/`retry`/`escalate_when`/`pause_when` are step-level siblings of `with`, not `with` keys).

## Tasks & Acceptance

**Execution** — tests first (AD-18): write each test module and watch it fail before the module it names exists.

1. `backend-api/pyproject.toml` — move `pyyaml==6.0.3` from `[dependency-groups] dev` into `[project] dependencies`; add `types-pyyaml` to the dev group (mypy strict has no stubs otherwise). Then `uv lock` and commit `uv.lock` — every gate runs `uv run --locked`.
2. `backend-api/src/orchestrator/domain/entities/template.py` — `TemplateRef{name, version}` and `TemplateVersion{name, version, yaml, hash, calls: tuple[TemplateRef, ...]}`, frozen pydantic. Placed with the other entities because `backend-api/AGENTS.md` lists `TemplateVersion` under `domain/ entities`.
3. `backend-api/src/orchestrator/domain/ports/templates.py` — `@runtime_checkable class TemplateVersionRepository(Protocol)` with the single read `get(self, name: str, version: int) -> TemplateVersion | None`. Read-only this story; 3.3 adds the writes.
4. `backend-api/tests/unit/fakes/templates.py` — `FakeTemplateVersionRepository` over `dict[tuple[str, int], TemplateVersion]` with `add()` / `get()`; docstring states it is the one fake for that port.
5. `backend-api/src/orchestrator/application/steps/__init__.py` — `Gate = Literal["liveness", "deterministic", "human"]`, frozen dataclass `KindMeta{gate_default: Gate | None, timeout_default_min: int | None, with_keys: frozenset[str], planner_only: bool}`, and `KIND_META` for the eleven kinds with the spine's values (below). Docstring says executors register here in Epic 4.
6. `backend-api/src/orchestrator/application/templates/__init__.py` — docstring only.
7. `backend-api/src/orchestrator/application/templates/model.py` — the frozen pydantic tree `ParsedTemplate`, `InputDecl`, `Step`, `ForEach`, `TemplateCall`, `AgentExtras`, each carrying `line`; plus the result vocabulary `ValidationError{template: str | None, version: int | None, line: int, reason: str}` and `ValidationResult{template: ParsedTemplate | None, errors: tuple[ValidationError, ...], unvalidated: tuple[str, ...]}`. `ValidationError` is a value, never an `Exception` — `domain/errors.py` is the only exception vocabulary.
8. `backend-api/src/orchestrator/application/templates/lines.py` — the `yaml.SafeLoader` subclass and `load_with_lines(text)`. The only module importing `yaml`.
9. `backend-api/src/orchestrator/application/templates/keys.py` — `check_keys()`: the key table at template, input, step, agent-extras, call and `for_each` levels; kind lookup through `KIND_META`; `uses`/`run` xor and the `run:` desugaring; duplicate ids; gate, `timeout_min`, `on_fail` and redispatch-target rules; `parallel`; one `for_each` per file and no nesting.
10. `backend-api/src/orchestrator/application/templates/expressions.py` — `check_expressions()`: the `{{name}}` / `{{name.field}}` grammar, the bound-name scope, the entity field whitelist, and the bare condition forms.
11. `backend-api/src/orchestrator/application/templates/calls.py` — `check_calls()`: resolve each callee through the port, walk `TemplateVersion.calls` with a path stack for cycles and a depth counter, and check the input bindings.
12. `backend-api/src/orchestrator/application/templates/validate.py` — `parse()` and `validate()`: run the checkers over the lined tree, concatenate, sort by line, and build `ParsedTemplate` only when `errors` is empty. The only public entry point.
13. `backend-api/tests/unit/application/__init__.py`, `.../templates/__init__.py`, and `.../templates/fixtures/*.yaml` — one fixture file per rejection, named by its reason; plus `test_template_model.py`, `test_template_lines.py`, `test_template_keys.py`, `test_template_expressions.py`, `test_template_calls.py`, `test_template_validate.py`, `test_step_kind_registry.py`, `test_template_ports.py`, `test_template_fake.py`. Every new source module must be imported by at least one of them.

**Acceptance Criteria** (beyond the I/O matrix, which is the rejection suite):

- Given the whole suite, when `make lint` runs, then `ruff`, `mypy --strict`, `lint-imports` and `scripts/check_test_pairs.py` all pass — in particular no new source module is unpaired and no forbidden import appears.
- Given `make test`, when the coverage step runs, then `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` passes, so `model.py`, `validate.py` and every sibling checker show 100 % branch coverage.
- Given `KIND_META`, when a test enumerates it, then it holds exactly the eleven kinds with the spine's gate and timeout defaults, `plan.check` is the only `planner_only` entry, and the validator's accepted-kind set is derived from `KIND_META` rather than restated.
- Given `FakeTemplateVersionRepository`, when a test asserts `isinstance(fake, TemplateVersionRepository)`, then it holds.
- Given a valid `initiative -> epic -> story` chain in fixtures, when validated, then depth 3 produces no error and each callee is fetched through the port exactly as a stored `TemplateVersion`.

## Spec Change Log

## Review Triage Log

### 2026-09-05 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 2, medium 7, low 1)
- defer: 7: (high 0, medium 5, low 2)
- reject: 1: (high 0, medium 0, low 1)
- addressed_findings:
  - `[high]` `[patch]` `validate()` raised `pydantic.ValidationError` on YAML the key table accepted (`for_each: [a, b]`, `expect.files: [3]`, `retry.max: two`, `enum values: [1, 2]`, `run: [make, test]`), breaking the "never raises" invariant and turning 3.3's validate endpoint into a 500. Every value `parse()` feeds a model is now type-checked first, reported as `expression syntax` (`for_each`) or `missing key` (the rest); a hostile-input table test pins the property.
  - `[high]` `[patch]` Direct self-recursion was not a cycle: a root `a@1` calling `a@1` validated clean because only descendants were tested against the call path. The call target is now tested against the root ref; `call cycle` is reported.
  - `[medium]` `[patch]` A non-mapping entry in `steps:` was silently dropped, so a typo'd step vanished from the plan with no error. Reported as `missing key` at that entry's line.
  - `[medium]` `[patch]` Unmemoised call traversal emitted duplicate identical records (two `callee not found` at one line) against the matrix's "one error" promise. Records are deduplicated on `(line, reason)`, first-seen order preserved.
  - `[medium]` `[patch]` `unvalidated` carried junk AD-15 node ids (`('', 'dup', 'dup')`) that story 3.4 joins on. Steps whose id is not a slug are skipped and paths are no longer repeated.
  - `[medium]` `[patch]` The `run:` sugar path skipped `_plain`, leaking `LinedSeq`/`LinedMap` loader types into the frozen tree where the `with` path yielded plain types.
  - `[medium]` `[patch]` An unterminated interpolation (`command: '{{b'`) was accepted and would reach the harness as literal text; an unbalanced `{{` or `}}` is now `expression syntax`.
  - `[medium]` `[patch]` Input `default` values were never scanned, so `default: '{{missing}}'` survived into every Run taking the default. Defaults are scanned with the same grammar and scope rules as step values.
  - `[medium]` `[patch]` Verification gap: dropping `unvalidated` from `validate()`'s error return left all 314 tests green, because no rejection fixture held a gateless executable step. A fixture with one keyed error and one gateless step now pins both.
  - `[low]` `[patch]` `_kind_of` re-derived the planner-only rule instead of reading the registry — the second enumeration AD-9 exists to prevent — and `line_of` was production code called only from tests.


## Design Notes

**Why `validate.py` is a package, not a file.** The brief names `application/templates/validate.py` as "parse + validate". The key table alone is several hundred lines and `backend-api/AGENTS.md` caps a module at 400 lines and a function at 50 statements, enforced by the frozen `test_source_limits.py`. AD-15's rule is "one parser", not "one file": `validate.py` stays the single public entry point and the only module anything outside `application/templates/` imports; `lines.py`, `keys.py`, `expressions.py` and `calls.py` are its private siblings. If a checker still exceeds 400 lines, split it again inside the package rather than relaxing a gate.

**Line numbers.** `LineLoader(yaml.SafeLoader)` overrides `construct_mapping` and `construct_sequence` to return `LinedMap(dict)` / `LinedSeq(list)` subclasses. Each carries `line = node.start_mark.line + 1`; `LinedMap` additionally carries `key_lines: dict[str, int]` from each key node's own mark. The reporting rule: an offence about a key or its scalar value uses `key_lines[key]`; an offence about a nested mapping or sequence uses that child's `line`. Without `key_lines`, `version: "1"` on line 2 would be reported at the line of the enclosing document, which the acceptance criteria forbid.

**Depth and cycles.** Depth counts templates, root inclusive: root is 1, so `a -> b -> c -> d` reaches 4 and is `call depth over 3`, while `initiative -> epic -> story` is 3 and passes. Cycle detection keys on `(name, version)` and uses the **current call path** as the visited set, pushed and popped around each descent — a global visited set would report a diamond (two steps calling the same callee) as a cycle. Traversal below the root reads `TemplateVersion.calls`, which is exactly why that field exists; the callee's YAML is loaded only to read its `inputs:` block for the binding check. A callee's own body is never re-validated, and an unreachable callee is `callee not found` at the call's line.

**Binding types.** A `{{name}}` that is the entire value binds by exact type equality against the callee's declared input type — this is what makes a `number` bound to a `path` a `callee input mismatch`. A scalar literal, or a string with interpolation inside it (`"{{initiative_folder}}/{{epic.spec_folder}}"`), binds `string`, `path` or `enum` when it is text and `number` when it is an int or float literal; `project`, `repository` and `item` accept only an exactly-typed variable. Every `required: true` callee input must be bound; an input name the callee does not declare is a mismatch.

**`unvalidated` paths.** A step's path is its `id`s joined by `.`, index-free, with the enclosing `for_each` id as a segment — `stories.story.build`, matching AD-15's node ids so 3.4 joins to it without translation. A missing `gate` is reported for every executable step; a `for_each` construct and a `uses: template` step are not rows and are never reported. `KIND_META.gate_default` is metadata the Epic 4 planner reads; it never suppresses an `unvalidated` report (NFR-2: a step with no declared gate is never silently green).

**`KIND_META` values** (spine "Shipped kinds"): `plan.check` deterministic/5/`{}`/planner-only; `git.worktree` deterministic/5/`{base, branch}`; `git.sync` deterministic/5/`{}`; `shell` deterministic/30/`{command}`; `agent` liveness/90/`{harness, model, skill, args, prompt_extra}`; `git.commit` deterministic/5/`{message}`; `git.push` deterministic/5/`{branch}`; `pr.link` liveness/5/`{branch}`; `checkpoint` human/none/`{}`; `template` none/none/`{name, version, inputs}`; `bmad.install` deterministic/30/`{}`. `expect`, `retry`, `escalate_when` and `pause_when` are step-level keys accepted only when `uses: agent`; elsewhere they are `unknown key`.

**Reason strings.** FR-5 fixes thirteen and the brief adds five: `unknown key`, `unbound variable`, `unknown kind`, `uses and run on the same step`, `nested for_each`, `second for_each`, `expression syntax`, `non-literal version`, `call cycle`, `call depth over 3`, `callee input mismatch`, `parallel is reserved`, `timeout_min or on_fail on a template call`, `unknown field`, `duplicate step id`, `redispatch target not an earlier agent step`, `invalid on_fail`, `invalid gate`. The key table states rules those eighteen cannot name, so this spec fixes these rather than leave the implementer to invent them: `invalid yaml` (unparseable, empty, or a non-mapping root), `callee not found`, `missing key` (an absent required key; a step with neither `uses` nor `run`; an `enum` input with no `values`), `invalid slug` (a `name`, step `id` or `as` failing `^[a-z][a-z0-9-]*$`), `invalid input type`, `default does not match type`, `empty steps`, `invalid timeout_min`, `invalid status_in token`. A key accepted only in another context — `values` on a non-`enum` input, `expect` on a `shell` step — is `unknown key`, not a new reason.

**Degrading gracefully.** Each checker skips a subtree it cannot read rather than raising, so a file with a malformed `inputs:` block still reports every step-level problem it can name in the same pass. The one exception is a YAML load failure, which returns a single `invalid yaml` and nothing else.

## Verification

**Commands:**
- `cd backend-api && uv run pytest tests/unit -q` — expected: the whole unit suite green, including every new rejection fixture.
- `make lint` — expected: ruff, mypy strict, import-linter and the test-pair gate all pass.
- `make test` — expected: unit suite green **and** the 100 % branch-coverage report over `domain/` + `application/` passes.

## Auto Run Result

Status: done

**Implemented change.** `validate()` in `application/templates/validate.py` is now the single parser and validator for DSL v1 (AD-15), returning `ValidationResult{template, errors, unvalidated}` with every problem carrying template, version, line and reason. `application/steps/__init__.py` holds `KIND_META` for the eleven spine kinds and is the only enumeration of kinds (AD-9). Callees resolve through the read-only `TemplateVersionRepository` port, so the application layer performs no I/O.

**Files changed.**
- `backend-api/pyproject.toml`, `uv.lock` — `pyyaml` promoted to a runtime dependency (kept in the dev group too, because the frozen `test_coverage_gates.py` pins it there); `types-pyyaml` added for `mypy --strict`.
- `domain/entities/template.py` — `TemplateRef`, `TemplateVersion{name, version, yaml, hash, calls}`.
- `domain/ports/templates.py` — `TemplateVersionRepository` Protocol, read-only `get`.
- `application/steps/__init__.py` — `Gate`, `KindMeta`, `KIND_META`, `TEMPLATE_KINDS`.
- `application/templates/` — `validate.py` (public entry), `lines.py` (line-recording loader, the only `yaml` importer), `model.py` (frozen tree, result vocabulary, 27 reason constants), `table.py`, `inputs.py`, `keys.py`, `expressions.py`, `agent.py`, `calls.py`.
- `tests/unit/fakes/templates.py` — the one fake for the new port.
- `tests/unit/application/templates/` — 9 test modules, a conftest and 44 YAML fixtures; 361 tests.

**Review findings.** 10 patches applied (2 high, 7 medium, 1 low), 7 items deferred, 1 rejected. The rejected finding claimed `uv.lock` was missing from the change; it was excluded from the review diff by the reviewer's own construction, and the `--locked` gates prove the lock matches the manifest.

**Follow-up review recommended: true.** Patched counts: high 2, medium 7, low 1. Two high-severity patches were applied, which sets the flag regardless of score; the score itself is 3 x 7 + 1 x 1 = 22, also over the threshold of 5.

**Verification performed.**
- `make lint` — exit 0: ruff, ruff format, `mypy --strict` on `domain/` and `application/`, `lint-imports` (3 contracts kept, 0 broken), env-contract, `check_test_pairs` (48 modules, each paired), plus the web-client half.
- `make test` — exit 0: 1854 backend tests passed, 1 skipped; 586 web-client tests passed; `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` reported 100% with 0 missed lines and 0 partial branches.
- The new modules measured on their own: 872 statements, 326 branches, 0 missed, 0 partial — 100% branch coverage, no `pragma: no cover`.
- Every I/O-matrix row is covered by a test that ran: the 31-row `REJECTIONS` table drives `validate()` per fixture asserting exact reason and exact line, and the accepted rows (minimal, `run:` sugar, missing gate, depth-3 chain, three sorted errors, malformed YAML) each have a named test.
- The two high-severity fixes were confirmed by executing the validator directly before and after, not by test output alone.

**Residual risks.**
- The reason vocabulary now covers malformed scalars inside `expect`, `retry` and enum `values` by reusing `missing key`. The story's "Never" clause said those blocks get no deep type checking, but leaving them untyped made `validate()` raise, which its "Always" clause forbids. Upholding the invariant without minting a 28th reason string is the reading taken; the operator should ratify the wording before 3.3 surfaces it and 3.5 renders it.
- Story 3.2 must spell shipped step ids as slugs (`commit-guard`, not `commit_guard`): the DSL draft's underscore spelling is now `invalid slug`.
- Depth and cycle detection below the root read `TemplateVersion.calls`; story 3.3 owns populating that field correctly, and nothing yet ties it to the stored `yaml`.
