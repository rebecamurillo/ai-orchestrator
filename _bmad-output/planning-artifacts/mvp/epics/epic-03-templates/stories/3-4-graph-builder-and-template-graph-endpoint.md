---
title: 'Graph builder and template graph endpoint'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      An edited shipped Template seeds as the next version, so a stack that already stored the
      pre-edit `initiative` keeps answering `initiative@1` without its item checkpoint.
    evidence: |-
      `seed_shipped`/`_seed_file` skip a file whose hash matches any stored version and
      otherwise insert at `max(existing) + 1`. `templates/initiative.yaml` changed in this
      story, so a database seeded before it gets `initiative@2` while `initiative@1` keeps the
      old text. Immutability is 3.3's rule and is correct; what is missing is any statement of
      what an operator should do about a shipped Template whose text moved on. `make e2e`
      always builds a disposable stack, so no gate can see it.
    location: >-
      backend-api/src/orchestrator/application/use_cases/templates.py (_seed_file)
    severity: medium
  - summary: >-
      The graph draws every item pause and no step pause: the condition a `pause_*_item_when`
      declares is not carried on the node, and a step-level `pause_when` is not `human`.
    evidence: |-
      `ForEach.pause_after_item_when` holds an expression (`story.done_checkpoint`) evaluated
      per item by Epic 4's planner; the synthetic node carries `human: true` with nothing
      saying the stop is conditional. `story@1`'s `build` declares `pause_when:
      "story.spec_checkpoint"` and reads `human: false`. Both follow the brief's own
      definition of `human` (gate `human`, or kind `checkpoint`) exactly, so changing either
      is a product decision for 3.6 and Epic 4, not a defect in this builder.
    location: >-
      backend-api/src/orchestrator/application/graph.py (_item_checkpoint, _is_human)
    severity: medium
  - summary: >-
      `_refusal()` and `HTTP_NOT_FOUND` are now copied verbatim into a third router module.
    evidence: |-
      Byte-identical in `api/routers/templates.py`, `api/routers/clone_check.py` and
      `api/routers/graph.py`. Three copies is where the helper should move up beside
      `PROBLEM_SCHEMA_REF` in `api/errors.py`; doing it here would edit two routers this
      story otherwise does not touch.
    location: >-
      backend-api/src/orchestrator/api/routers/graph.py
    severity: low
  - summary: >-
      A 500 rendered from a raised `Problem` writes no log line, unlike the two 500 paths
      `api/errors.py` handles itself.
    evidence: |-
      `_handle_problem` does not call `log.exception`; only `_handle_unexpected` and
      `_handle_response_validation_error` do. Whether a raised `Problem` at 5xx should log is
      a repo-wide policy for `api/errors.py`, and no router logs today.
    location: >-
      backend-api/src/orchestrator/api/errors.py (_handle_problem)
    severity: low
baseline_revision: '5fcc89b77e8966c02ae73c717a4216189f16266d'
---

<intent-contract>

## Intent

**Problem:** The Templates screen (3.5) and the diagram (3.6) need the *shape* of a Template version — its nodes, its edges, its loop groups — and nothing in the system computes it; if the browser derived that shape from YAML it would be a second parser, and the diagram and the validator could disagree (AD-15).

**Approach:** One pure function, `build_template_graph(parsed) -> Graph`, over the tree `validate()` already returned, plus `GET /api/v1/templates/{name}/{version}/graph` that re-parses the stored YAML through the same one validator and answers `{nodes, edges, groups}`. The node id is the template-relative dotted path without indices — byte-identical to the paths `validate()` already reports in `unvalidated`, so the two join without translation, and Epic 4's `build_run_graph` reuses the same module and the same `_nodes_for_step` seam.

## Boundaries & Constraints

**Always:**
- `application/graph.py` is **pure over `ParsedTemplate`**. It never reads YAML, never re-implements a validator rule, and never performs I/O (AD-2: no `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`).
- Kind facts come from `application/steps/__init__.py` (`KIND_META`, `AGENT_KIND`, `TEMPLATE_CALL_KIND`, and the `CHECKPOINT_KIND` this story adds beside them). No kind is spelled out as a bare string literal at a comparison (`backend-api/AGENTS.md`: "No `if kind == ...` anywhere else").
- **Node id rule (AD-15).** A top-level step is its own `id`; a step inside a `for_each` is `{loop_id}.{step_id}`; a synthetic item checkpoint is `{loop_id}.before` / `{loop_id}.after`. No index, no `[n]`, ever — this is what makes the id joinable to `ValidationResult.unvalidated` and stable across items.
- **Collapsed calls.** A `uses: template` step is exactly one node: `call: {name, version}`, `kind: template`, `gate: null`, `label: "{name}@{version}"`. Its callee is never expanded here.
- **Flags (NFR-2).** `agent: true` iff `uses: agent`; `human: true` iff the declared gate is `human` or the kind is `checkpoint`; `gate: "unvalidated"` for an executable step that declared none — never filled in from `KIND_META.gate_default`; `label` is the step id (except a call, above).
- `domain/` + `application/` stay at 100 % branch coverage with no `pragma: no cover`; every source module has a test module that imports it; every module is <= 400 lines.
- The endpoint answers 200 `Graph`, 404 for an unknown name or version, and — for a stored version that no longer validates, which cannot happen while storage only ever accepts validated text — a 500 naming the first `line` and `reason`.

**Block If:**
- Landing the endpoint would require editing a pre-existing test file. (It does not: see Design Notes, "Why the route is its own router".)
- The graph shape the brief's acceptance criteria assert cannot be produced without changing a rule the validator owns.

**Never:**
- No run graph (`build_run_graph`, statuses, expanded rows, `groups[].status`) — Epic 4.
- No layout, no SVG, no dagre — 3.6.
- No callee expansion, and **no attempt to surface a callee's gateless steps to the caller**: the `unvalidated` guarantee is per file, not per expanded plan. That is Epic 4's problem; note it, do not solve it.
- No escalation and no retry edges.
- No new parser, no re-reading of YAML inside `application/graph.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Flat template | `repo-init@1` | 5 nodes in file order, 4 edges chaining them, `groups == ()`, every `call is None` | No error expected |
| Agent + gates | `story@1` | `sync -> build -> verify -> commit-guard`; `build.agent is True` and `gate == "liveness"`; `verify` and `commit-guard` `gate == "deterministic"` | No error expected |
| Loop + call + after | `epic@1` | nodes `checkout, baseline, stories.story, stories.after, push, link`; group `stories` members `(stories.story, stories.after)`; edges `checkout->baseline, baseline->stories.story, stories.story->stories.after, stories.after->push, push->link` | No error expected |
| Loop only | `initiative@1` | nodes `epics.epic` (`call {epic,1}`), `epics.after`; one group `epics`; one edge `epics.epic->epics.after` | No error expected |
| Gateless step | a template whose step omits `gate` | that node's `gate == "unvalidated"`; the id equals the path `validate()` put in `unvalidated` | No error expected |
| `pause_before_item_when` | loop declaring it | `{loop}.before` first in the group, `kind checkpoint`, `gate human`, `human True`; the previous step's edge enters `.before`, not the first real step | No error expected |
| Neither pause key | loop declaring neither | no synthetic node; the group holds only the inner steps | No error expected |
| Explicit `checkpoint` step | `uses: checkpoint` with no `gate` | `human True` (kind), `gate "unvalidated"` (nothing declared) | No error expected |
| Endpoint, known version | `GET /api/v1/templates/epic/1/graph` + bearer | 200, the `epic@1` graph above, edges as `{from, to}` | No error expected |
| Endpoint, unknown version | `GET /api/v1/templates/epic/9/graph` | 404 `application/problem+json` | `NotFound` -> 404 |
| Endpoint, unknown name | `GET /api/v1/templates/nope/1/graph` | 404 `application/problem+json` | `NotFound` -> 404 |
| Endpoint, no bearer | any of the above without the header | 401 problem document | router mounted with `require_bearer` |
| Stored text that no longer validates | repository holds invalid YAML under a version | 500 problem document whose `detail` reads `line {n}: {reason}` | `StoredTemplateInvalid` -> `Problem(500)` |

</intent-contract>

## Code Map

Read-only anchors that decide whether this lands (do not edit any of them):

- `backend-api/tests/unit/test_templates_router.py:...::test_the_router_declares_every_path_with_a_get_beside_any_post` — asserts `sorted(routes) == [six exact entries]` on `api/routers/templates.py`. **A seventh route on that module fails this frozen test.** The route therefore lands in a router of its own; see Design Notes.
- `backend-api/tests/unit/test_bearer_auth.py:271` `test_the_contract_declares_the_401_and_its_media_type` — every published `/api/v1` path must have a `get`; `:228` calls every published operation unauthenticated and requires a 401. The new path is a `GET` under the bearer-mounted prefix, so both hold.
- `backend-api/tests/unit/test_bearer_auth.py:255` `test_the_versioned_router_is_mounted_with_the_dependency` — ast-scans `main.py`: *every* `include_router` call must pass `prefix=API_PREFIX` and `dependencies=[Depends(require_bearer)]`. Copy the existing five verbatim.
- `backend-api/tests/unit/test_source_limits.py` — <= 400 lines per module, no `print`, no wall clock outside `infrastructure/`.
- `backend-api/tests/unit/test_coverage_gates.py` + `Makefile:39` — `domain/` + `application/` at `--fail-under=100`, no `pragma: no cover`, no `omit` in `pyproject.toml`.
- `backend-api/tests/unit/test_layering.py` + `pyproject.toml [tool.importlinter]` — AD-2 layers and the forbidden-import list.
- `scripts/check_test_pairs.py` — every new source module needs a unit-test module importing it.
- `backend-api/tests/unit/application/templates/test_step_kind_registry.py` — frozen; adding a third named kind constant is purely additive and touches no assertion in it.
- `backend-api/tests/unit/application/templates/test_shipped_templates.py` — frozen; it asserts `epic@1`'s pause key but makes **no** assertion about `initiative@1`'s loop options, so the one-line fix below does not reach it.

Patterns to copy:

- `backend-api/src/orchestrator/api/routers/clone_check.py` (docstring lines 1-8) — the precedent for this exact situation: "A router of its own rather than two more routes on `api/routers/repositories.py`, for the reason that module's own contract test states". Same prefix, same bearer dependency, invisible from outside.
- `backend-api/src/orchestrator/application/templates/model.py` — frozen pydantic v2 models (`model_config = ConfigDict(frozen=True)`, `tuple[X, ...]`, `#:` comments) — the shape `Graph` copies.
- `backend-api/src/orchestrator/api/schemas/templates.py` — `*Out` model with a `.of()` classmethod mapping an application value onto the wire.
- `backend-api/src/orchestrator/application/use_cases/templates.py` — `get_version` is the read-then-`validate()` shape `template_graph` follows; `TemplateValidationFailed` is the "carries the validator's errors so the router can render them" precedent.
- `backend-api/tests/unit/test_templates_router.py` `Harness` — the ASGI + `dependency_overrides[template_ports]` + `FakeTemplateVersionRepository` harness to copy into the new router test.
- `backend-api/tests/unit/application/templates/test_shipped_templates.py` — reads `templates/*.yaml` off disk against `FakeTemplateVersionRepository` with `calls` pinned; the shipped-graph test copies that fixture wholesale.
- `backend-api/tests/e2e/test_templates.py` — the e2e client/bearer style for the new e2e module.

Facts already distilled (no need to re-read): `application/templates/keys.py:111` `_path()` builds `unvalidated` entries as `{loop}.{step}` / `{step}`, index-free, and its docstring says these "are the node ids 3.4 joins a graph to"; a `uses: template` step and a `for_each` construct are never reported `unvalidated`; both `steps:` lists (root and loop) are rejected empty, so a validated tree never holds an empty loop; `ForEach` appears only at the root and holds only `Step`s.

## Tasks & Acceptance

**Execution:**

1. `backend-api/tests/unit/application/test_graph.py` — **write first, watch it fail**: the `Graph`/`Node`/`Edge`/`Group` shape, the id rule (including an assertion that no id contains `[`, `]` or a digit-only segment), collapsed calls, the flags, both pause keys and neither, an explicit `checkpoint` step, and the `unvalidated`-joins-to-node-ids proof. Drives every row of the I/O matrix above the endpoint rows.
2. `backend-api/tests/unit/application/test_graph_shipped.py` — **write first**: the four shipped Templates' expected shapes, asserted as exact ordered tuples of node ids, edges and group members.
3. `backend-api/src/orchestrator/application/steps/__init__.py` — add `CHECKPOINT_KIND` beside `TEMPLATE_CALL_KIND` and `AGENT_KIND` — the graph needs the kind by name, and AD-9 says kinds are named here or nowhere.
4. `backend-api/src/orchestrator/application/graph.py` — `Node`, `Edge`, `Group`, `Graph` (frozen), `build_template_graph(parsed) -> Graph`, and the `_nodes_for_step` seam Epic 4 reuses. Pure; no I/O; <= 400 lines.
5. `templates/initiative.yaml` — add `pause_after_item_when: "epic.done_checkpoint"` to the `epics` loop. Brief 3.2 specified it and the file shipped without it; brief 3.4's `initiative@1` acceptance criterion (`epics.after`) cannot hold without it, and AD-7 gives `epics.yaml` entries a `done_checkpoint` field for exactly this.
6. `backend-api/tests/unit/test_graph_schemas.py` + `backend-api/src/orchestrator/api/schemas/graph.py` — `GraphOut` with `from`/`to` aliases on the edge, `.of(graph)`; the schema Epic 4's run graph extends.
7. `backend-api/tests/unit/test_graph_use_case.py` + `backend-api/src/orchestrator/application/use_cases/templates.py` — add `template_graph(ports, name, version) -> Graph` and `StoredTemplateInvalid`; amend the module docstring's operation count.
8. `backend-api/tests/unit/test_graph_router.py` + `backend-api/src/orchestrator/api/routers/graph.py` + `backend-api/src/orchestrator/main.py` — the `GET /templates/{name}/{version}/graph` route, its declared refusals, and the mount (copied verbatim from the existing five).
9. `backend-api/tests/e2e/test_template_graph.py` — the endpoint against the real stack and the real seeded Templates.
10. `contracts/openapi.json`, `web-client/src/api/schema.d.ts` — regenerate with `make openapi`; both are generated, never hand-edited (AD-3).

**Acceptance Criteria:**

- Given `epic@1`, when its graph is built, then the nodes, the group and the edges are exactly the "Loop + call + after" row of the matrix, in that order.
- Given `initiative@1`, when built, then nodes are `epics.epic` (`call {epic,1}`, `kind template`, `gate None`, `label "epic@1"`) and `epics.after`, with one group `epics`.
- Given `story@1`, when built, then `build.agent` is true with `gate "liveness"`, `verify` and `commit-guard` are `"deterministic"`, and `sync` precedes `build` in both nodes and edges.
- Given `repo-init@1`, when built, then there are five nodes in file order, no group, and no node carries a `call`.
- Given any of the four shipped Templates, when built, then no node id and no group id contains `[`, `]`, or a segment that is only digits.
- Given a Template whose step declares no `gate`, when built, then that node's `gate` is `"unvalidated"` and its id is exactly the string `validate()` reported in `ValidationResult.unvalidated`.
- Given `GET /api/v1/templates/epic/1/graph` with the bearer against the running stack, when called, then it returns 200 with that graph and edges keyed `from`/`to`; `GET /api/v1/templates/epic/9/graph` returns 404 `application/problem+json`.
- Given the whole change, when `make lint`, `make test` and `make openapi` run, then all three exit 0, `domain/` + `application/` report 100 % branch coverage, and the re-exported contract shows no drift.

## Spec Change Log

- 2026-09-05 — `templates/initiative.yaml` gains `pause_after_item_when: "epic.done_checkpoint"`. Brief 3.2 §"`initiative@1`" specified it; the file shipped in story 3-2 without it, so brief 3.4's `initiative@1` acceptance criterion (`epics.after` exists) was unsatisfiable. Fixing the shipped file is the only reading that leaves both briefs, AD-7 and the graph rule mutually consistent; inventing an `.after` node for a loop that declares no pause key would contradict this story's own binding rule. No pre-existing test asserts the absence of that key.

## Review Triage Log

### 2026-09-06 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 4, low 7)
- defer: 4: (high 0, medium 2, low 2)
- reject: 9: (high 0, medium 3, low 6)
- addressed_findings:
  - `[medium]` `[patch]` A synthetic item checkpoint could collide with a real inner step named `before`/`after`: two nodes at one path, a self-edge, and an `unvalidated` path joining to the wrong node. The validator now reserves the word a declared pause key plans a row at, reported with its existing `duplicate step id` reason (no new reason string); three tests cover the reservation and its absence.
  - `[medium]` `[patch]` A `uses: template` step that declared a `gate` carried it onto the call node, contradicting the brief's `gate: null` and the published schema's own description. `_gate_of` and `_is_human` now test the call first; two tests pin both.
  - `[medium]` `[patch]` `initiative@1` — the one shipped file this story edited — was asserted only against the text on disk, never through storage. Two e2e tests now read its graph from the running stack, and the e2e id sweep covers all four shipped Templates.
  - `[medium]` `[patch]` `test_the_router_declares_only_the_template_graph_route` froze an exact route list that Epic 4's `GET /runs/{id}/graph` would have to break — the same trap that made this route need its own module. It now asserts containment plus "every route here is a GET".
  - `[low]` `[patch]` The 500 discarded every validator error but the first; it now carries them all in `errors[]` through `as_problem_errors`, the way the sibling save 422 does.
  - `[low]` `[patch]` The 500's title was `stored template invalid` where every other 500 this API sends reads `internal server error`. One status, one title; `detail` and `errors[]` say which 500 it is.
  - `[low]` `[patch]` `tests/unit/application/test_graph.py` was 466 lines against this spec's own 400-line ceiling. Split into `test_graph.py` (shape, flags, gates, ids) and `test_graph_loops.py` (the loop construct and the collapsed call) over a shared `graph_cases.py`.
  - `[low]` `[patch]` Two tests did not assert what their names claimed: `test_story_has_no_human_node_and_no_group` never checked the groups, and `test_the_callee_is_read_through_the_same_repository` never removed the callee. Both now do.
  - `[low]` `[patch]` `initiative@1`'s new pause key was observed only through the node it produces; the expression `epic.done_checkpoint` is now pinned directly.
  - `[low]` `[patch]` AD-15 illustrates the node id with the three-segment `stories.story.build`, which is the run graph's expanded id. `graph.py`'s docstring now says so rather than silently picking the brief's two-segment form (root `AGENTS.md`: "when code and spine disagree, stop and say so").
  - `[low]` `[patch]` `MAX_VERSION` was imported router-to-router. It is a storage fact, so it moved to `api/schemas/common.py` beside the other column limits and both routers read it there.

## Design Notes

**Why the route is its own router.** `tests/unit/test_templates_router.py::test_the_router_declares_every_path_with_a_get_beside_any_post` asserts an exact six-entry route list on `api/routers/templates.py`; a seventh route there fails a frozen test, and that test may not be edited. `api/routers/clone_check.py` already set the precedent for this exact shape — `/repositories/{id}/clone-check` lives in its own module "for the reason that module's own contract test states" — with the same prefix and the same bearer dependency, so the split is invisible from outside. `api/routers/graph.py` is also where Epic 4's `GET /runs/{id}/graph` belongs, which makes the split the destination rather than a detour. Nothing is relaxed: the property the frozen test protects (that router publishes exactly its six operations) stays true, and the repo-wide "every published path has a `GET`" check in `test_bearer_auth.py` covers the new path.

**Why the walker builds edges in this order.** Each top-level entry is reduced to a *frame*: its nodes, its internal edges, its entry id and its exit id. The connecting edge from the previous frame's exit is appended **before** the frame's own internal edges, which is what makes `epic@1` read `baseline->stories.story` then `stories.story->stories.after` rather than the reverse — the order the acceptance criterion states, and the order a left-to-right reader expects.

**Loop entry and exit.** A `for_each` frame's ordered members are `[before?] + inner steps + [after?]`. Entry id is the first member and exit id is the last, so `pause_before_item_when` moves the incoming edge onto `.before` and `pause_after_item_when` moves the outgoing edge off `.after` with no special case at the call site. Consecutive members are chained. The group's `members` is that same ordered list, so the synthetic checkpoints are inside the dashed box 3.6 draws, which is where an item-level pause belongs.

**Why `_nodes_for_step` returns a tuple.** In this release a step is exactly one node. Epic 4's `build_run_graph` expands one planned step into one row per item, and the brief names this seam as the reuse point; returning a tuple is what lets that arrive without changing the walker.

**The known limitation, recorded not fixed.** A callee's gateless steps do not surface to the caller: `epic@1`'s graph collapses `story@1` to a single node, so an `unvalidated` step inside `story@1` is invisible in `epic@1`'s graph, exactly as it is invisible in `epic@1`'s `ValidationResult`. The guarantee is per file, not per expanded plan. Epic 4's planner owns the expanded view; this story must not try to close it.

**Golden shape** (`epic@1`):

```text
nodes  checkout · baseline · stories.story (call epic->story@1) · stories.after (checkpoint) · push · link
groups stories = (stories.story, stories.after)
edges  checkout->baseline · baseline->stories.story · stories.story->stories.after · stories.after->push · push->link
```

## Verification

**Commands:**
- `make lint` — expected: exit 0 (ruff, ruff format, `mypy --strict` on `domain/`+`application/`, `lint-imports` with 3 contracts kept, env contract, test pairs, contract-drift check, web-client half).
- `make test` — expected: exit 0; every new test passes; `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` reports 100 % with 0 missed branches.
- `make openapi` — expected: exit 0; `contracts/openapi.json` gains the new path and `web-client/src/api/schema.d.ts` regenerates; re-running `make lint` after it shows no drift.
- `make e2e` — expected: exit 0 against a disposable stack, including the new `tests/e2e/test_template_graph.py` and schemathesis finding no 5xx on the new operation.

## Auto Run Result

Status: done

**Summary of implemented change.** Story 3.4 (SPEC CAP-4, FR-7): `application/graph.py` computes
`Graph{nodes, edges, groups}` from the tree `validate()` returns — pure, no I/O, no second parse
— and `GET /api/v1/templates/{name}/{version}/graph` serves it. Node ids are template-relative
dotted paths with no index, byte-identical to the paths `validate()` reports in `unvalidated`;
a `uses: template` step is one collapsed node; a `for_each` is a group whose members are its
inner nodes plus the synthetic `{loop}.before` / `{loop}.after` checkpoints its pause keys
declare. `_nodes_for_step` is the named seam Epic 4's `build_run_graph` reuses.

**Files changed** (new unless marked *modified*):
- `backend-api/src/orchestrator/application/graph.py` — the frozen `Graph`/`Node`/`Edge`/`Group`/`NodeCall` values and `build_template_graph`.
- `backend-api/src/orchestrator/application/steps/__init__.py` *(modified)* — `CHECKPOINT_KIND`, the third named kind constant.
- `backend-api/src/orchestrator/application/templates/keys.py` *(modified)* — a declared pause key reserves the id it plans a row at; an inner step taking it is `duplicate step id`.
- `backend-api/src/orchestrator/application/use_cases/templates.py` *(modified)* — `template_graph()` and `StoredTemplateInvalid`; the docstring now describes seven operations.
- `backend-api/src/orchestrator/api/schemas/graph.py` — `GraphOut`, with the edge aliased back to `{from, to}` on the wire.
- `backend-api/src/orchestrator/api/schemas/common.py` *(modified)* — `MAX_VERSION` moved here, where both routers that bound a version read it.
- `backend-api/src/orchestrator/api/routers/graph.py` — the route, its declared 404/422/500, and the module Epic 4's run graph lands on.
- `backend-api/src/orchestrator/api/routers/templates.py` *(modified)* — reads `MAX_VERSION` from the shared module.
- `backend-api/src/orchestrator/main.py` *(modified)* — the sixth `include_router`, copied verbatim from the existing five.
- `templates/initiative.yaml` *(modified)* — `pause_after_item_when: "epic.done_checkpoint"` (see the Spec Change Log).
- `backend-api/tests/unit/application/{graph_cases,test_graph,test_graph_loops,test_graph_shipped}.py`, `backend-api/tests/unit/test_graph_{schemas,use_case,router}.py`, `backend-api/tests/e2e/test_template_graph.py` — the tests, written and failing first.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` *(modified, generated)* — `make openapi`; never hand-edited (AD-3).

**Review findings breakdown:** 11 patches applied (0 high, 4 medium, 7 low — see the Review
Triage Log); 4 deferred (0 high, 2 medium, 2 low — see frontmatter `deferred`); 9 rejected.
The rejections, each with its reason: the spine/brief node-id "contradiction" (resolved by
saying so, patched as documentation, not a code change); declaring the 500 on one operation
only (it is the only operation with a *described* 500 outcome); `Group` discarding `ForEach.source`
and `as_name`, and `Graph` carrying no name/version (the shape is pinned by the brief and reused
by Epic 8); `NodeOut.kind` as a bare string rather than a Literal (a static enum would duplicate
`KIND_META`, which AD-9 forbids); `step.uses == AGENT_KIND` style comparisons (named constants
from the registry, the precedent `validate.py` already sets); and four defensive guards for
states a validated tree cannot reach (an empty frame, empty `steps:`, `StoredTemplateInvalid`
with no errors, `gate_default` being `None`) — each would add a branch no test can reach, against
the 100 % branch gate.

**Follow-up review recommendation:** `true`. Patched findings score `3 x 4 (medium) + 1 x 7
(low) = 19`, at or above the threshold of 5; no patched finding was `high`.

**Verification performed:**
- `make lint` — exit 0: ruff, `ruff format --check`, `mypy --strict` on `domain/`+`application/`, `lint-imports` (3 contracts kept, 0 broken), env contract (26 fields / 32 variables), test pairs (58 backend modules, 29 web-client), contract-drift check, and the web-client half.
- `make test` — exit 0: 2127 backend tests passed, 1 skipped; 586 web-client tests passed; `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` reported 100 % with 0 missed lines and 0 partial branches.
- `make openapi` — exit 0; the new path publishes 200/401/404/422/500, `EdgeOut` publishes `from`/`to`, and `make lint`'s `gen:api --check` afterwards showed no drift.
- `make e2e` — exit 0 against a disposable stack: 78 tests + 19 subtests passed, including the graph of `epic@1`, `story@1`, `repo-init@1` and `initiative@1` read through real seeding and a real Postgres, and schemathesis finding no 5xx on the new operation.
- Every row of the I/O & Edge-Case Matrix has at least one test that ran and passed in those runs; the endpoint rows are covered twice, at the ASGI surface and against the real stack.

**Residual risks:**
- The four items in frontmatter `deferred`, of which two matter for the next stories: an already-seeded stack answers `initiative@1` with the pre-edit shape (the e2e test above proves the fresh-stack case only), and the graph draws an item pause as an unconditional human stop because `Node` has no field for the condition.
- The callee limitation is by design and pinned by a test, not fixed: a gateless step inside `story@1` is invisible in `epic@1`'s graph, exactly as it is invisible in `epic@1`'s `ValidationResult`. The `unvalidated` guarantee is per file, not per expanded plan (Epic 4).
- The 500 is declared in the published contract but is unreachable against a real stack by construction, so only the unit surfaces exercise it.

