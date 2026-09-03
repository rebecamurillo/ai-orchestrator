---
story: "3-4"
epic: 3
title: Graph builder and template graph endpoint
requirements: [FR-7, NFR-2, AR-20]
binds: [AD-2, AD-9, AD-15]
---

# Story 3.4 — Graph builder and template graph endpoint

As the Operator,
I want the backend to compute the shape of a Template version from the same parse the validator did,
So that the browser only draws, never interprets, and the diagram and the validator can never disagree.

## Scope

**In:** `application/graph.py` (`build_template_graph(parsed) -> Graph`), the `Graph` schema, `GET /api/v1/templates/{name}/{version}/graph`, tests on the four shipped Templates.
**Out:** the run graph with statuses and expanded rows (Epic 4 adds `build_run_graph` to the same module); drawing (3.6).

## Binding rules (inlined)

- **Shape.** `Graph{nodes: [Node], edges: [Edge], groups: [Group]}`; `Node{id, label, kind, gate: liveness | deterministic | human | unvalidated | null, agent: bool, human: bool, call: {name, version} | null}`; `Edge{from, to}`; `Group{id, label, kind: "for_each", members: [node id]}`.
- **Ids (AD-15).** Node id = template-relative path without indices, dot-separated step ids: top-level step `checkout` → `checkout`; a step inside a `for_each` with id `stories` → `stories.story`. A `template` call is one collapsed node (`call` set, `kind: template`, `gate: null`, `label: "{name}@{version}"`); its callee's steps are not expanded here. A `for_each` is a group whose members are its inner step nodes; the group id is the loop's id.
- **Edges.** Sequential order of steps: each step to the next at the same level; entering a loop connects the previous step to the loop's first inner node and the loop's last inner node to the next step; a loop with `pause_before_item_when` / `pause_after_item_when` adds a synthetic node `<loop>.before` / `<loop>.after` with `kind: checkpoint`, `gate: human`, `human: true`, placed at the start / end of the group. Escalation and retry edges are not drawn.
- **Flags (NFR-2).** `agent: true` for `uses: agent`; `human: true` for `gate: human` or `kind: checkpoint`; `gate: "unvalidated"` when the step declares none; `label` is the step id.
- **Endpoint.** `GET /api/v1/templates/{name}/{version}/graph` → 200 `Graph`; 404 for an unknown version; the stored YAML is re-parsed through `validate()` (stored versions are valid by construction, so errors here are a 500 with the reason).
- **Layering (AD-2):** `graph.py` is pure over the parsed tree; it reads kind metadata from `application/steps/__init__.py`.

## Acceptance criteria

**Given** `epic@1`
**When** its graph is built
**Then** nodes are `checkout`, `baseline`, `stories.story` (`call: {story, 1}`), `stories.after` (`kind: checkpoint`, `human: true`), `push`, `link`; the group `stories` has members `[stories.story, stories.after]`; edges are `checkout→baseline`, `baseline→stories.story`, `stories.story→stories.after`, `stories.after→push`, `push→link`.

**Given** `initiative@1`
**When** built
**Then** nodes are `epics.epic` (`call: {epic, 1}`) and `epics.after`; one group `epics`.

**Given** `story@1`
**When** built
**Then** `build` has `agent: true`, `gate: liveness`; `verify` and `commit_guard` are `deterministic`; `sync` precedes `build`.

**Given** `repo-init@1`
**When** built
**Then** five nodes in order with no group and no call.

**Given** a template whose step lacks `gate`
**When** built
**Then** that node has `gate: "unvalidated"`.

**Given** `GET /templates/epic/1/graph` with the bearer
**When** called
**Then** it returns the graph above; `GET /templates/epic/9/graph` returns 404.

## Implementation notes

- `application/graph.py` with `build_template_graph(parsed: ParsedTemplate) -> Graph` and a private walker over steps/loops; leave a clearly named seam (`_nodes_for_step`) that Epic 4's `build_run_graph` reuses.
- `api/schemas/graph.py` for the Pydantic schema (also used by the run graph later); router in `api/routers/templates.py`.
- Run `make openapi`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-7, FR-29 (shared builder), NFR-2. Spine AD-15 (graph rules, node ids), AD-7 (`before`/`after` checkpoint rows).
