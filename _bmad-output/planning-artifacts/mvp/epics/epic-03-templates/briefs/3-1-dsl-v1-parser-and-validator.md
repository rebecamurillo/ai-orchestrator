---
story: "3-1"
epic: 3
title: DSL v1 parser and validator
requirements: [FR-5, NFR-2, AR-12 (registry), AR-20]
binds: [AD-2, AD-9, AD-15, AD-18]
---

# Story 3.1 — DSL v1 parser and validator

As the Operator,
I want every Template I write checked against one small, explicit language before it can be saved or run, with each problem named by line and reason,
So that a Run can never start from YAML that means something other than what it says.

## Scope

**In:** `application/templates/validate.py` (parse + validate), `application/templates/model.py` (the parsed tree), `application/steps/__init__.py` registry with kind metadata, `domain/ports/templates.py` `TemplateVersionRepository` protocol (read-only: `get(name, version) -> TemplateVersion | None`) and its fake, exhaustive unit tests.
**Out:** the shipped YAML files (3.2), storage and endpoints (3.3), the graph (3.4), planning and expansion (Epic 4), executors (Epic 4).

## Binding rules (inlined)

### Key table (the only accepted keys)

| Level | Keys | Rules |
| --- | --- | --- |
| template | `name`, `version`, `description`, `inputs`, `steps` | `name` slug `^[a-z][a-z0-9-]*$`; `version` an int literal (a string or expression is `non-literal version`); `inputs` map; `steps` non-empty list |
| input | `type`, `required`, `default`, `values` | `type ∈ project, repository, string, path, enum, number, item`; `values` only with `enum`; `default` type-consistent |
| step | `id`, `uses` xor `run`, `with`, `gate`, `timeout_min`, `on_fail` | `id` slug unique in the file; exactly one of `uses` / `run` (`run: <command>` is sugar for `uses: shell`, `with: {command}`); `gate ∈ liveness, deterministic, human`; missing `gate` → reported in `unvalidated`, not an error; `timeout_min` positive int; `on_fail ∈ escalate, fail, continue` or `{redispatch: <step id>, max: <int ≥ 1>}` where the target is an earlier `agent` step in the same file |
| step `uses: agent` | `with {harness, model?, skill, args{}, prompt_extra?}`, `expect {files: [glob], status_in: [token]}`, `retry {max, prompt, resume_session?}`, `escalate_when`, `pause_when` | `status_in` tokens ∈ `draft, ready-for-dev, in-progress, in-review, blocked, done` |
| step `uses: template` | `with {name, version, inputs{}}` | `version` int literal; `timeout_min` or `on_fail` present → error; callee must exist through the repository port; every required callee input bound; input names and types match the callee's declaration (an `item` binds only to an `as` variable; `project`/`repository` bind only to inputs of the same type); call depth over 3 → error; a cycle → error |
| for_each | `id`, `for_each`, `as`, `steps`, `pause_before_item_when`, `pause_after_item_when`, `parallel` | `for_each` is a `{{…}}`-bearing path expression; `as` slug; at most one `for_each` per file; a `for_each` inside `steps` of another → `nested for_each`; `parallel` present → `parallel is reserved`; `pause_*_when` are a single item field `<as>.<field>` |
| kinds accepted in YAML | `git.worktree`, `git.sync`, `shell`, `agent`, `git.commit`, `git.push`, `pr.link`, `checkpoint`, `template`, `bmad.install` | `plan.check` is planner-only and rejected in YAML; unknown kind → error; `with` keys per kind: `git.worktree {base, branch}`, `git.sync {}`, `shell {command}`, `git.commit {message}`, `git.push {branch}`, `pr.link {branch}`, `checkpoint {}`, `bmad.install {}` — an unknown `with` key is `unknown key` |

- **Expressions.** Only `{{name}}` and `{{name.field}}`; anything else inside `{{ }}` is `expression syntax`. Bound names: declared inputs, the `for_each` `as` name (inside its `steps` only), and for `escalate_when` the form `output.status == <token>`. Entity inputs expose a fixed whitelist: `project.name`; `repository.url`, `repository.default_branch`, `repository.install_command`, `repository.quality_gate_command`, `repository.unit_test_command`. An unlisted entity field → `unknown field`. Fields of an `item` variable are not checked (dynamic). An unbound name → `unbound variable`.
- **Errors.** `ValidationError{template, version, line, reason}`; `line` from the YAML node (use a `yaml.SafeLoader` subclass that records `start_mark.line + 1` on every mapping and sequence node); the reason strings are the exact phrases listed in FR-5: `unknown key`, `unbound variable`, `unknown kind`, `uses and run on the same step`, `nested for_each`, `second for_each`, `expression syntax`, `non-literal version`, `call cycle`, `call depth over 3`, `callee input mismatch`, `parallel is reserved`, `timeout_min or on_fail on a template call`, plus `unknown field`, `duplicate step id`, `redispatch target not an earlier agent step`, `invalid on_fail`, `invalid gate`. Validation collects every error in one pass and returns them ordered by line.
- **Result.** `validate(yaml_text, *, templates: TemplateVersionRepository) -> ValidationResult{template: ParsedTemplate | None, errors: [ValidationError], unvalidated: [step path]}`; `template` is `None` when any error exists.
- **Registry (AD-9).** `application/steps/__init__.py` defines `KIND_META: dict[str, KindMeta{gate_default, timeout_default_min, with_keys, planner_only}]` for all eleven kinds (`plan.check` marked `planner_only`); the validator imports it and enumerates nothing itself. Executors come in Epic 4 and register in the same module.
- **Layering (AD-2):** no I/O; PyYAML 6.0.3 only.

## Acceptance criteria

**Given** a minimal valid template (one `shell` step with a gate)
**When** validated
**Then** `errors` is empty, `unvalidated` is empty, and `template` holds the parsed tree with resolved kind metadata.

**Given** each of these inputs in its own test: an unknown top-level key; `version: "1"`; `version: "{{v}}"`; a step with both `uses` and `run`; `uses: rocket`; a `{{missing}}` in `with`; `{{repository.secret}}`; `{{story.title | upper}}`; two `for_each` at top level; a `for_each` nested in another; `parallel: 2`; a `template` call with `timeout_min`; a `template` call to a callee that does not exist; a callee input named wrongly; a callee `path` input bound to a `number`; a chain `a → b → c → d` (depth 4); `a → b → a`; a duplicate step id; `on_fail: {redispatch: verify, max: 1}` where `verify` is not an agent step; `gate: green`
**When** validated
**Then** exactly the expected reason appears, with the line of the offending node.

**Given** a template whose second step has no `gate`
**When** validated
**Then** `errors` is empty and `unvalidated` contains that step's path.

**Given** a template with three independent errors on different lines
**When** validated
**Then** all three are returned, sorted by line.

**Given** `run: "make test"` on a step
**When** parsed
**Then** the step is `uses: shell` with `with.command = "make test"`.

**Given** the coverage report
**When** `make test` runs
**Then** `validate.py` and `model.py` show 100 % branch coverage.

## Implementation notes

- `application/templates/model.py`: pydantic models `ParsedTemplate`, `InputDecl`, `Step`, `ForEach`, `TemplateCall`, `AgentExtras`; every node keeps `line`.
- `application/templates/validate.py`: `parse()` (YAML → raw tree with lines), `check_keys()`, `check_expressions()`, `check_calls()` (loads callees through the port, recursion with a visited set for cycles and a depth counter), `validate()` assembling the result. Keep each function under 50 lines.
- `domain/ports/templates.py`: `TemplateVersion{name, version, yaml, hash, calls}` entity and the repository protocol; `tests/unit/fakes/templates.py` holds versions in a dict keyed `(name, version)`.
- Test fixtures under `tests/unit/application/templates/fixtures/*.yaml`, one file per rejection, named by reason.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-5, NFR-2. Spine AD-9, AD-15, Structural Seed "Template DSL v1 keys" and "Shipped kinds", conventions "Template variables". `template-dsl-draft.md` §2 (older `run:` spelling of kinds is superseded by `uses:`).
