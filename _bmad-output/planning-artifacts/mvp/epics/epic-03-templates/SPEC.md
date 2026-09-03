---
id: SPEC-mvp-epic-03-templates
companions: []
sources:
  - ../../prd.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../template-dsl-draft.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 3.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 3 — Templates: validated DSL, versions, and the rendered diagram

## Why

An opportunity to make the dev loop legible and editable without a visual editor: a Template is YAML written like a CI workflow, validated by one function, stored as immutable versions, and drawn from a graph the backend computes. This epic delivers that single validator and graph builder, the four shipped Templates (`repo-init`, `story`, `epic`, `initiative`), the versions API, and the Templates screen with its editor and diagram. Every later epic reads the validator and the graph; nothing else ever parses a Template.

## Capabilities

- **CAP-1** DSL v1 validator
  - **intent:** One function parses and validates a Template against the DSL v1 key table and returns every error with template, version, line, and reason, plus the steps that lack a gate.
  - **success:** each rejection listed in FR-5 has a unit test that produces the expected error; valid Templates return no errors; a step without `gate` is reported `unvalidated`.
- **CAP-2** Shipped Templates
  - **intent:** The four Templates exist as YAML files in the repository, expressed in DSL v1, composing `initiative → epic → story`, and `repo-init` standing alone.
  - **success:** all four validate with no errors and no `unvalidated` step; `initiative@1` resolves `epic@1` and `story@1` at depth 3; the planner of Epic 4 can expand them.
- **CAP-3** Template versions API and seeding
  - **intent:** Templates and their versions are stored, listed, read, validated, and saved as version n+1; the shipped YAML is seeded as version 1 at container start.
  - **success:** `POST /templates/{name}/versions` creates n+1 and never changes an existing version's YAML; the read model shows `pinned_by` (0 until Epic 4) and `called_by`.
- **CAP-4** Graph builder and template graph endpoint
  - **intent:** The backend computes the graph of a Template version from the validator's result: one node per step, `for_each` as a group, `template` calls collapsed, agent steps and human gates flagged, `unvalidated` flagged.
  - **success:** `GET /templates/{name}/{v}/graph` returns `{nodes, edges, groups}` with index-free node ids; the shipped Templates produce the expected shapes.
- **CAP-5** Templates screen: versions, editor, validate, save
  - **intent:** The Operator opens a Template version, reads and edits its YAML in the browser, validates it, sees errors by line, and saves as the next version.
  - **success:** the screen matches the experience spec's Templates surface; validation errors list `line · reason`; saving creates n+1 and selects it.
- **CAP-6** Template diagram
  - **intent:** The browser lays out and draws the backend graph left to right, read-only, and keeps the last valid diagram when the editor content is invalid.
  - **success:** nodes show kind and gate word, `for_each` draws as a dashed group, calls draw collapsed with callee name and version, human gates read `human` with a hairline, ungated nodes read `unvalidated`; the diagram refreshes on every successful validation.

## Constraints

- `application/templates/validate.py` is the single parser and validator (AD-15); the browser never parses YAML.
- The DSL accepts exactly the key table of the spine's Structural Seed: `{{name}}` / `{{name.field}}` substitution only; one `for_each` per file, not nested; no conditionals, no string functions; `parallel` reserved and rejected; `timeout_min` and `on_fail` rejected on `template` calls; a callee sees only its declared inputs.
- Versions are immutable once saved; a version pinned by a Run (Epic 4) is frozen, callees included (AD-15).
- Kinds are enumerated once, in `application/steps/__init__.py` (AD-9); this epic creates that registry with kind metadata (default gate, default `timeout_min`, accepted `with` keys) and no executors yet.
- API and UI conventions of Epics 1 and 2 apply (bearer, problem+json, generated types, tokens, signal rule, voice).
- Tests first; every module has a test module; the validator has 100 % branch coverage (AD-18).

## Non-goals

- No planning, no expansion of loops into rows, no Runs (Epic 4).
- No enforcement of freeze-on-pin beyond the schema (`pinned_by` is 0 until Runs exist).
- No visual editing of the diagram; no drag, add, or edit of nodes.

## Success signal

The Operator opens `epic@1`, breaks it by adding `parallel: 2` to the loop and removing a `gate`, and reads `1 error · line 23 · parallel is reserved` plus an `unvalidated` node in the diagram from the last valid version; she reverts, validates, and saves `epic@2`, while `epic@1` stays byte-identical.
