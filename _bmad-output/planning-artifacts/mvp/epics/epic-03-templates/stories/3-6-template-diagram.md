---
title: 'Template diagram rendered from the backend graph'
type: 'feature'
created: '2026-09-06'
status: 'done'
baseline_revision: '7381326457e81dcda9a00b4f37f355e8664f7f44'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      `Diagram.tsx` is documented as the reusable island Epic 8 mounts, but it emits the
      Templates-specific `data-testid="templates-diagram"` unconditionally.
    evidence: |-
      The brief pins the island's props to `{graph, ariaLabel}`, so a `testId` prop was not
      added here. Epic 8's run diagram mounting this same island would carry the Templates
      screen's test id, and a spec that then queried `templates-diagram` on a Run page would
      resolve. The fix is one optional prop, and it belongs to the story that needs a second
      caller.
    location: >-
      web-client/src/islands/Diagram.tsx
    severity: medium
  - summary: >-
      A group rectangle is a post-hoc bounding box of its members, so a non-member that ranks
      between two members would be drawn inside the dashed `for_each` box.
    evidence: |-
      `layout.ts` never calls dagre with `compound: true` / `setParent`; `enclose()` takes the
      min/max of the members that exist. A Template graph is a chain and its loop members are
      consecutive, so the case is unreachable in this release — `build_template_graph` emits a
      loop frame as one contiguous run. Epic 4's expanded plan and Epic 8's run diagram draw a
      group per callee frame beside these, which is where interleaving becomes reachable.
    location: >-
      web-client/src/lib/diagram/layout.ts (enclose, placeNodes)
    severity: medium
  - summary: >-
      A failed server-side read of the stored version's graph draws an empty diagram with
      nothing on screen saying the read failed.
    evidence: |-
      `[version].astro` falls back to `EMPTY_GRAPH`, which renders an SVG labelled `· 0 steps`
      inside the bordered slot. A Template with no steps cannot exist (the key table rejects an
      empty `steps:`), so the state is unambiguous to a reader who knows that and silent to one
      who does not. The repository already has `EmptyState.astro` for exactly this; the brief
      states no copy for the case, so inventing one here would be this story writing product
      voice it was not given.
    location: >-
      web-client/src/pages/templates/[name]/[version].astro
    severity: low
  - summary: >-
      The stale line carries no `aria-live` / `role="status"`, so a screen-reader user who
      clicks Validate is not told the picture stopped matching the text.
    evidence: |-
      Story 3.5 deferred the identical finding for its own async readout ("no `aria-live` on
      async state"). Both belong to one pass over the screen's live regions rather than to two
      half-measures, and the brief fixes the diagram's accessibility contract at `role="img"`
      plus the one `aria-label`.
    location: >-
      web-client/src/islands/TemplateDiagram.tsx
    severity: low
  - summary: >-
      `save()`'s failure branches do not publish a validation outcome, so a Save that is
      refused leaves the diagram unmarked while the readout lists the errors.
    evidence: |-
      `validate()` now publishes on every path it takes, including its two failure paths. A
      refused Save means the text on screen did not validate, which is the same state, but
      `save()` belongs to 3.5 and its own contract (it navigates away on success); widening it
      would change a control flow this story has no acceptance criterion over.
    location: >-
      web-client/src/islands/TemplateEditor.tsx (save)
    severity: low
---

<intent-contract>

## Intent

**Problem:** The Templates screen's third column is a literal placeholder (`diagram arrives with the next story`). The Operator can read a Template's YAML and its validation errors but cannot see its shape, and the backend graph endpoint only serves a *stored* version, so unsaved editor text has no graph at all.

**Approach:** Add `POST /api/v1/templates/{name}/graph` (`{yaml}` -> `Graph`, or 422 with the validator's errors) beside a read-only `GET /api/v1/templates/{name}/graph` (the latest stored version, the required `get` sibling), both on a router of their own; in the browser, lay the graph out with dagre (`rankdir: LR`) and draw it as read-only SVG in a reusable `Diagram` island, refreshed from a nanostore that `TemplateEditor` publishes each validation outcome to, and holding the last valid picture when validation fails.

## Boundaries & Constraints

**Always:**
- The browser never parses YAML (AD-15). Every node, edge and group comes from the API.
- Node ids are the join key, byte for byte, with no translation: React keys, `diagram-node-<id>` test-ids and the last-valid rule are all keyed on `Node.id`, never on array position.
- No signal colour anywhere in this diagram: only `--color-line`, `--color-line-strong`, `--color-surface`, `--color-text*`, `--color-accent`. `unvalidated` and `human` are plain words.
- Layout: `@dagrejs/dagre` 3.1.1 pinned exactly, `rankdir: LR`, orthogonal hairline connectors, square nodes, `border-radius: 0`, no shadow, dashed group rectangles drawn from `Group.members` alone.
- `role="img"` and `aria-label` exactly `template {name} v{n} · {nodes} steps`.
- Test-ids exactly `templates-diagram`, `diagram-node-<id>`, `diagram-group-<id>`, `templates-diagram-stale`. Stale copy exactly `diagram from last valid version`.
- New backend routes carry no route-level dependency (the bearer is on the mount, AD-4), declare every refusal as `ProblemDetail`, and publish a `get` on their path (`test_bearer_auth.py` indexes it).
- `domain/` + `application/` stay at 100 % branch coverage with no pragmas; `import-linter` layers hold.
- API types come only from `pnpm gen:api`; `contracts/openapi.json` and `src/api/schema.d.ts` are regenerated by `make openapi` and committed.
- No inline `style` attributes; every colour and type role read from `src/styles/tokens.css` via `var(--…)`.

**Block If:**
- The exact `@dagrejs/dagre@3.1.1` pin cannot be installed (offline registry, pnpm cooldown) — the version is fixed by the architecture Stack table and the brief.
- Any anchor other than the one placeholder assertion named in the Spec Change Log has to change.

**Never:**
- No run statuses, tokens, `now`, click-to-row, drag, add or edit (Epic 8 extends the same island).
- No second parser: the diagram never derives a gate, a kind or a group from text.
- No expansion of a `template` call; no pause *condition* on a node (recorded by 3.4 as deliberate).
- No `GET /api/v1/templates` answering non-empty in the e2e stub (frozen `shell.spec.ts`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Posted YAML is valid | `POST /templates/{name}/graph` `{yaml: story@1 text}` | 200 `{nodes, edges, groups}`, identical to the stored version's graph | No error expected |
| Posted YAML is invalid | same route, `uses: no.such.kind` | 422 `application/problem+json`, `detail` = `line {n}: {reason}`, every validator error in `errors[]` | Refusal, not data: there is no graph to draw |
| Posted YAML names an unknown callee | `uses: template` naming a name nothing stored | 422 with the validator's own error | Same path as above |
| Latest stored version read by name | `GET /templates/{name}/graph` with v1 and v2 stored | 200, the graph of v2 | — |
| Unknown name | `GET /templates/leaf/graph` | 404 problem document | `NotFound` |
| Stored latest no longer validates | repository holds text `validate()` rejects | 500 problem document naming the first line and reason | `StoredTemplateInvalid`, carried not assumed away |
| Route ordering | `GET /api/v1/templates/story/graph` on the whole app | the graph, not a 422 from `{version}` parsing `graph` | mount order asserted by a test |
| Page open | `/templates/demo/1` | `templates-diagram` holds an SVG with one `diagram-node-<id>` per node, no `templates-diagram-stale` | initial graph read server-side, best effort |
| Validation succeeds after an edit | editor text valid, adds a step | diagram redraws with the new node id; stale line absent | — |
| Validation fails after an edit | editor text has `parallel: 2` | node ids unchanged from the last valid graph; `templates-diagram-stale` reads `diagram from last valid version` | last-valid rule |
| Graph POST itself fails | validation succeeded, graph request errors | previous graph kept, stale line shown | never a blank diagram |
| Empty graph | `{nodes: [], edges: [], groups: []}` | an SVG with `aria-label … · 0 steps` and no node | no crash, no NaN in the viewBox |
| Group whose member id is absent | a `Group` naming an id no `Node` has | group box drawn around the members that exist; unknown ids ignored | no crash |

</intent-contract>

## Code Map

**Read-only anchors that decide whether this lands (do not edit):**

- `backend-api/tests/unit/test_graph_router.py:259` `test_the_router_publishes_the_template_graph_as_a_get_and_carries_no_dependency` — `for methods, path in routes: assert "GET" in methods`. **Every route on `api/routers/graph.py` must include GET**, so a POST-only route cannot land there. This is why the new pair gets a module of its own.
- `backend-api/tests/unit/test_templates_router.py:293` — `sorted(routes) == [six exact entries]` on `api/routers/templates.py`. A seventh route there fails it; the brief's "in `api/routers/templates.py`" is therefore not available (3.4 hit and documented the same wall).
- `backend-api/tests/unit/test_bearer_auth.py:271` `test_the_contract_declares_the_401_and_its_media_type` — indexes `document["paths"][path]["get"]` for **every** published `/api/v1` path. `/templates/{name}/graph` must publish a `get`; that is what makes the read-only sibling mandatory, not decorative.
- `backend-api/tests/unit/test_bearer_auth.py:255` — ast-scans `main.py`: every `include_router` call passes `prefix=API_PREFIX` and `dependencies=[Depends(require_bearer)]`. No order or count assertion, so a new mount may be inserted.
- `backend-api/tests/unit/test_projects_router.py:394` — repo-wide: `"HTTPValidationError" not in components.schemas`. Every new operation declares its own 422 as `ProblemDetail`.
- `backend-api/tests/unit/test_source_limits.py` — <= 400 lines per backend module. `application/use_cases/templates.py` is at 306.
- `backend-api/tests/unit/test_coverage_gates.py` + `Makefile` — `domain/`+`application/` at `--fail-under=100`, no pragma, no omit.
- `web-client/tests/unit/stylesheets.test.ts` — auto-discovers every `.css` under `src/`: radius 0 only, no shadow, `font-weight: 400` only, **no hex/`rgb()`/`hsl()`/`color-mix()` outside `tokens.css`**, every `var(--x)` must exist, no `outline: none`.
- `web-client/tests/unit/tokens.test.ts` — the type ramp is an exact table; do not add a `--type-*` token.
- `web-client/tests/e2e/shell.spec.ts:27` — bare `/templates` renders `NO TEMPLATES`; the stub's `GET /api/v1/templates` stays unconditionally `{items: []}`.
- `web-client/scripts/check-test-pairs.mjs` — every new `src/**/*.ts|tsx` must be *named* by a string in some `tests/unit/**` file. `src/pages/**/*.astro` is exempt.
- `scripts/check_test_pairs.py` — every new backend module must be imported by a `backend-api/tests/unit` module.

**Patterns to copy:**

- `backend-api/src/orchestrator/api/routers/graph.py` — the whole module is the template for the new one: `_refusal()`, a `REFUSALS` dict, `Ports = Annotated[TemplatePorts, Depends(template_ports)]`, `INTERNAL_TITLE`, the `StoredTemplateInvalid` -> 500 mapping.
- `backend-api/src/orchestrator/api/routers/templates.py` `save_version` — the `TemplateValidationFailed` -> 422 `Problem(..., errors=as_problem_errors(...))` mapping the POST reuses verbatim.
- `backend-api/src/orchestrator/application/use_cases/templates.py` — `template_graph` (read, `validate()`, `build_template_graph`) and `validate_latest` (`list_versions` -> `max`) are the two halves the new use cases compose.
- `backend-api/src/orchestrator/api/schemas/templates.py` `SaveVersionIn(ValidateIn)` — "same one field, a distinct name for a distinct route".
- `backend-api/tests/unit/test_graph_router.py` `Harness` — ASGI + `dependency_overrides[template_ports]` + `FakeTemplateVersionRepository`; copy wholesale.
- `backend-api/tests/e2e/test_template_graph.py` — the e2e client/bearer style and the `epic@1` golden shape.
- `web-client/src/islands/ProjectForm.tsx` + `project-form-logic.ts` — logic as pure functions in a sibling module because `vitest.config.ts` runs `environment: 'node'` with **no DOM library**; islands are never mounted in unit tests.
- `web-client/tests/unit/template-editor-island.test.ts` — the island unit-test header and shape.
- `web-client/tests/e2e/stub-backend.mjs:271` — the `/** 3.5's own routes below … added without touching any branch above. */` marker; add a `3.6` block the same way, and insert the new `if` between the last `/templates` branch and the fallback 404 (every existing regex is `$`-anchored, so nothing is shadowed).
- `web-client/tests/e2e/templates.spec.ts` `replaceEditorContent(page, text)` — how a spec retypes the CodeMirror document.

**Facts already distilled (no need to re-read):**

- Contract shapes already generated (3.4): `GraphOut {nodes, edges, groups}`, `NodeOut {id, kind, label, gate, agent, human, call}` with `gate: "liveness"|"deterministic"|"human"|"unvalidated"|null`, `EdgeOut {from, to}`, `GroupOut {id, label, kind:"for_each", members}`, `NodeCallOut {name, version}`. Import them as `components['schemas']['GraphOut']` etc.
- Browser paths are the generated `paths` with `/api/v1` stripped: `api.POST('/templates/{name}/graph', { params: { path: { name } }, body: { yaml } })`.
- `templates.router` is mounted **before** `graph.router` and registers `GET /templates/{name}/{version}` last, so a 3-segment `GET /templates/{name}/graph` mounted after it would be swallowed as `version="graph"` -> 422. The new router mounts **before** `templates.router`.
- `epic@1`'s golden graph (3.4, pinned by its e2e test): nodes `checkout · baseline · stories.story (label "story@1", gate null, call {story,1}) · stories.after (kind checkpoint, gate human, human true, label "after") · push · link`; group `stories` = `(stories.story, stories.after)`; edges chain them in that order.
- `story@1`'s `build` step is `uses: agent`, `gate: liveness` -> `agent: true`.
- Tokens available: `--color-{bg,surface,surface-raised,surface-rail,surface-inset,line,line-strong,text,text-secondary,text-tertiary,accent}`, `--type-{eyebrow,row-title,meta,column-head,micro}` (+ their `-line`/`-tracking`/`-transform` siblings), `--space-1..16`, `--font-mono`. The diagram column is 300 px wide (`grid-template-columns: 260px 1fr 300px`).
- `TemplateEditor.validate()` has exactly one place a fresh outcome lands: the `setResult({...})` call after the `seq` and `error || !data` guards. `data.errors.length === 0` there is the "valid" condition and `textRef.current` is the validated text.
- `nanostores@1.5.2` and `@nanostores/react@1.1.0` are already dependencies; `src/stores/` does not exist yet but `vitest.config.ts` already carries a `src/stores/**` 90 %-lines threshold (and the same for `src/lib/**`).
- Unit tests are `.test.ts` only (`include: ['tests/unit/**/*.test.ts']`) — **JSX cannot appear in a test**. Render React through `createElement` + `renderToStaticMarkup` from `react-dom/server`.

## Tasks & Acceptance

**Execution:**

1. `backend-api/tests/unit/test_graph_text_use_case.py` -- new: `graph_text` (valid -> graph, invalid -> `TemplateValidationFailed` carrying every error, callee resolved through the same repository, nothing written) and `graph_latest` (latest of several versions, unknown name -> `NotFound`, stored-invalid -> `StoredTemplateInvalid`) -- TDD, fails first.
2. `backend-api/tests/unit/test_graph_text_router.py` -- new: both routes over ASGI through `create_app` (which proves the mount order), 200 shapes, 422 with `errors[]` and `detail`, 404, 500 title/detail, 401 without the bearer, and the published contract (both operations have a summary; every refusal is `ProblemDetail`; the path publishes a `get`).
3. `backend-api/src/orchestrator/application/use_cases/templates.py` -- add `graph_text(ports, yaml_text)` and `graph_latest(ports, name)`; extend the module docstring's operation list -- one validator, one shaping (AD-15); reuses `TemplateValidationFailed`/`StoredTemplateInvalid` rather than inventing a third failure.
4. `backend-api/src/orchestrator/api/schemas/graph.py` -- add `GraphTextIn(ValidateIn)` -- the posted body, same one `yaml` field with the same length cap, a distinct name for a distinct route.
5. `backend-api/src/orchestrator/api/routers/graph_text.py` -- new router: `POST /templates/{name}/graph` and its mandatory read-only sibling `GET /templates/{name}/graph`; docstring states why it is not on `graph.py` (the frozen all-GET assertion) and not on `templates.py` (the frozen six-route assertion).
6. `backend-api/src/orchestrator/main.py` -- mount it, copied verbatim from the existing six, **before** `templates.router`, with a comment naming the shadowing it avoids.
7. `backend-api/tests/e2e/test_template_text_graph.py` -- new: both routes against the running stack over the really-seeded `story@1`/`epic@1`, plus the 422 for broken text.
8. `make openapi` -- regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; commit both (AD-3, never hand-edited).
9. `web-client/package.json` + `pnpm-lock.yaml` -- add `"@dagrejs/dagre": "3.1.1"` (exact, alphabetical) and install.
10. `web-client/tests/unit/diagram-layout.test.ts`, `diagram-svg.test.ts`, `diagram-state.test.ts`, `diagram-island.test.ts`, `template-diagram-island.test.ts`, `template-validation-store.test.ts` -- new, written first: the whole I/O matrix's browser half, including the `epic@1` and `story@1` golden shapes rendered through `renderToStaticMarkup`.
11. `web-client/src/lib/diagram/layout.ts` -- new, pure: `layoutGraph(graph)` -> `{width, height, nodes, edges, groups}` via dagre `rankdir: LR`; orthogonal 4-point connectors computed here, not taken from dagre's splines; group boxes are the bounding box of the members that exist, padded.
12. `web-client/src/lib/diagram/svg.tsx` -- new: `DiagramNode`, `DiagramGroup`, `DiagramEdge` renderers plus `gateWord()`; `DiagramNode` accepts optional `status` and `current` props, unused now, so Epic 8 adds tokens without restructuring.
13. `web-client/src/lib/diagram/diagram-state.ts` -- new, pure: `reduceDiagram(state, event)` implementing the last-valid rule (`validated-ok` swaps the graph and clears stale; `validated-failed` and `graph-failed` keep the graph and set stale).
14. `web-client/src/stores/template-validation.ts` -- new: the nanostore `TemplateEditor` publishes each validation outcome to and the diagram island subscribes to.
15. `web-client/src/islands/Diagram.tsx` -- new, reusable, props `{graph, ariaLabel}`: `role="img"`, the SVG, the three renderers, `data-testid="templates-diagram"` on its own scroll container.
16. `web-client/src/islands/TemplateDiagram.tsx` -- new: the Templates screen's stateful wrapper — initial graph as a prop, subscribes to the store, POSTs `/templates/{name}/graph`, owns the stale line.
17. `web-client/src/islands/TemplateEditor.tsx` -- publish `{yaml, ok}` at the one `setResult` site in `validate()` -- the validated-OK hand-off 3.5 deliberately left out.
18. `web-client/src/styles/diagram.css` -- new, tokens only, no signal colour, radius 0, no shadow.
19. `web-client/src/pages/templates/[name]/[version].astro` -- read the stored graph server-side (best effort) and replace the placeholder slot with `<TemplateDiagram client:load … />`.
20. `web-client/tests/e2e/templates-fixtures.mjs` + `stub-backend.mjs` -- purely additive: a lexical `graphFromYaml()` and the two `/graph` routes, inserted before the fallback 404, touching no existing branch.
21. `web-client/tests/e2e/template-diagram.spec.ts` -- new: open, redraw-on-valid, hold-on-invalid, `unvalidated` word, agent accent, group box, no signal colour, `aria-label`.
22. `web-client/tests/e2e/templates.spec.ts` -- the one anchor revision permitted by hard rule 1's placeholder exception; see the Spec Change Log.

**Acceptance Criteria:**

- Given a running stack, when `POST /api/v1/templates/story/graph` is called with `story@1`'s YAML, then it answers 200 with the same `{nodes, edges, groups}` as `GET /api/v1/templates/story/1/graph`.
- Given `GET /api/v1/templates/story/graph` on the whole application, when the request is routed, then it reaches the new operation and answers the latest version's graph — not a 422 from `{version}` parsing `graph`.
- Given `epic@1`'s graph, when `Diagram` renders it, then `diagram-node-checkout`, `diagram-node-baseline`, `diagram-node-stories.story`, `diagram-node-stories.after`, `diagram-node-push`, `diagram-node-link` and `diagram-group-stories` are present, `stories.story` reads `story@1` with eyebrow `template`, `stories.after` reads `human`, and the markup carries no signal token or amber/red value.
- Given `story@1`'s graph, when drawn, then the `build` node carries the agent accent border and the eyebrow `agent`.
- Given a node whose `gate` is `unvalidated`, when drawn, then its footer reads the plain word `unvalidated`.
- Given `/templates/demo/1` in a browser, when the page loads, then `templates-diagram` holds an SVG with `role="img"` and `aria-label` `template demo v1 · 2 steps`, and `templates-diagram-stale` is absent.
- Given the editor content is replaced with valid YAML declaring a new step, when Validate succeeds, then the diagram gains that node id and no stale line is shown.
- Given the editor content is replaced with invalid YAML, when Validate reports errors, then the rendered node ids are exactly the previous graph's and `templates-diagram-stale` reads `diagram from last valid version`.
- Given the whole gate set, when `make lint && make test && make openapi && make e2e-ui` run, then all pass and `make openapi` leaves no drift.

## Spec Change Log

- 2026-09-06 — **The brief's unfinished sentence, resolved.** "the island calls `POST /templates/{name}/validate` and, when there are no errors, `GET`s the graph for…" ends mid-clause; its own parenthesis supplies the resolution, and this story implements it: `POST /api/v1/templates/{name}/graph` with `{yaml}` -> `Graph` or 422, **backend included**. No other mechanism is invented.
- 2026-09-06 — **The route does not land where the brief says.** The brief's implementation note puts the POST "in `api/routers/templates.py`". `tests/unit/test_templates_router.py:293` freezes that module at six routes, and `tests/unit/test_graph_router.py:265` freezes every route on `api/routers/graph.py` to include `GET`, so a POST cannot land on either. It lands on a new `api/routers/graph_text.py`, same prefix, same bearer, invisible from outside — the precedent `api/routers/clone_check.py` set and 3.4 followed. Nothing is relaxed: both frozen properties stay literally true.
- 2026-09-06 — **A read-only `GET` sibling is added that the brief does not mention.** `tests/unit/test_bearer_auth.py:271` indexes `document["paths"][path]["get"]` for every published `/api/v1` path, so a POST-only path fails a frozen test. `GET /templates/{name}/graph` answers the latest stored version's graph — the exact mirror of `GET /templates/{name}/validate`, which `api/routers/templates.py`'s docstring already justifies in the same words.
- 2026-09-06 — **One anchor assertion revised, under hard rule 1's second exception.** `web-client/tests/e2e/templates.spec.ts:88-90` asserts `getByTestId('templates-diagram')` contains the placeholder copy `diagram arrives with the next story` — a string that names the replacing story as "the next story", which by `stories.yaml` order is 3-6, this one. Root `AGENTS.md` hard rule 1 permits exactly that story to revise exactly that assertion, and only when the same commit adds coverage that strictly exceeds it. The revision is the three lines of that one call and nothing else in the file; it becomes an assertion that the slot is served **and** that the real diagram's nodes are in it, and the same commit adds `tests/e2e/template-diagram.spec.ts` plus six unit test modules. `AGENTS.md`'s own guidance ("a test covering a placeholder asserts that the route is served, not the placeholder's copy") is what the revised line does. This is reported explicitly in the run result rather than absorbed silently.

## Design Notes

**Which signal channel, and why.** `TemplateEditor` and the diagram are two islands in two different grid cells; they cannot share React state, and `textRef` is a ref so a keystroke does not re-render. The channel is a nanostore, `src/stores/template-validation.ts` — not a DOM `CustomEvent` and not a callback prop, because `web-client/AGENTS.md` already names nanostores as this component's cross-island state mechanism, `nanostores` + `@nanostores/react` are already dependencies, and a store is unit-testable in `environment: 'node'` while a DOM event is not. `TemplateEditor` publishes `{seq, yaml, ok}` at the single `setResult` site in `validate()`; `TemplateDiagram` subscribes with `useStore`. The monotonic `seq` is what makes two identical validations distinguishable, so re-validating unchanged text still clears a stale line.

**Who fetches the graph.** The editor publishes *text and validity*, never a graph: fetching the graph in the diagram column keeps the editor's job unchanged (it validates) and the diagram's job whole (it draws). Cost: one extra round trip after each successful validation, which is what the brief's own sentence describes.

**The last-valid rule, keyed on ids.** `reduceDiagram` is a pure reducer over `{graph, stale}`. `validated-ok` replaces `graph` and clears `stale`; `validated-failed` and `graph-failed` leave `graph` untouched and set `stale`. Because the whole previous `Graph` value is retained, every node keeps its id; the test asserts the rendered `diagram-node-<id>` set is byte-identical to the previous graph's ids after an invalid edit that describes entirely different steps. Nothing is keyed on array position, and no node state is merged by index.

**Orthogonal connectors are computed, not taken from dagre.** dagre returns spline control points. The brief requires orthogonal hairlines, so `layout.ts` emits a 4-point polyline `(x1,y1) -> (mx,y1) -> (mx,y2) -> (x2,y2)` with `mx` the midpoint between the source's right edge and the target's left edge, collapsing to a straight line when the two ranks share a row. Deterministic, and unit-testable without a DOM.

**A call node has no gate.** `gate` is `null` only on a collapsed `template` call, which is a path segment and never a stop, so the footer line is omitted rather than filled with a word. The eyebrow reads `template` and the title reads `{name}@{version}`.

**Golden render (`epic@1`, 300 px column):**

```text
[checkout]->[baseline]->+-- stories (dashed) ----------+ ->[push]->[link]
                        | [story@1] -> [after: human]  |
                        +------------------------------+
```

## Verification

**Commands:**
- `make lint` -- expected: exit 0 (ruff, mypy, import-linter, env contract, both test-pair gates, `gen:api --check` with no drift, astro check, tsc, eslint, prettier).
- `make test` -- expected: exit 0; backend `domain`+`application` at 100 % branch with 0 partial branches; web-client vitest green with `src/lib/**` and `src/stores/**` above 90 % lines.
- `make openapi` -- expected: exit 0; `/api/v1/templates/{name}/graph` publishes `get` and `post`, both with a summary and `ProblemDetail` refusals; regenerated `schema.d.ts` committed.
- `make e2e-ui` -- expected: exit 0; every Playwright spec including the frozen `shell.spec.ts` and the revised `templates.spec.ts`. Port 4321 must be free (stop the compose `web-client` container first, restart it after).
- `make e2e-api` -- expected: exit 0 against a disposable stack, including the new `POST /templates/{name}/graph` operation under schemathesis with no 5xx.

## Auto Run Result

Status: done

**Summary of implemented change.** Story 3.6 (SPEC CAP-6, FR-7): the Templates screen's third
column is now the Template's shape, drawn from the backend's graph. The brief's unfinished
Refresh-rule sentence is resolved as its own parenthesis directs — `POST /api/v1/templates/{name}/graph`
with `{yaml}` answers a `Graph` or refuses 422 with the validator's errors, backend included —
and the browser lays that graph out with `@dagrejs/dagre@3.1.1` (`rankdir: LR`) and renders
read-only SVG: square nodes on `surface` with a `line` border, orthogonal `line-strong`
connectors, dashed `line-strong` loop rectangles, gate words as plain words, an `accent` border
on the one step that dispatches a harness, a `line-strong` hairline under `human`, and no signal
colour anywhere. Every successful validation replaces the picture; anything else keeps the last
valid one and says `diagram from last valid version` above it.

**Files changed** (new unless marked *modified*):

*Backend*
- `backend-api/src/orchestrator/api/routers/graph_text.py` — `POST` and `GET /templates/{name}/graph`.
- `backend-api/src/orchestrator/application/use_cases/templates.py` *(modified)* — `graph_text`,
  `graph_latest`, and the docstring's rule list.
- `backend-api/src/orchestrator/api/schemas/graph.py` *(modified)* — `GraphTextIn(ValidateIn)`.
- `backend-api/src/orchestrator/main.py` *(modified)* — the seventh mount, placed **before**
  `templates.router` so the three-segment `GET` is not swallowed as `version="graph"`.
- `backend-api/tests/unit/test_graph_text_use_case.py`, `test_graph_text_router.py`,
  `backend-api/tests/e2e/test_template_text_graph.py` — the tests, written and failing first.

*Web client*
- `web-client/src/lib/diagram/layout.ts` — pure `layoutGraph`; dagre placement, orthogonal
  connectors computed here, group boxes from `Group.members` alone.
- `web-client/src/lib/diagram/svg.tsx` — `DiagramNode` / `DiagramGroup` / `DiagramEdge`,
  `gateWord`, `kindWord`; `status` and `current` accepted and unused, for Epic 8.
- `web-client/src/lib/diagram/diagram-state.ts` — `reduceDiagram`, the last-valid rule.
- `web-client/src/stores/template-validation.ts` — the nanostore the editor publishes to.
- `web-client/src/islands/Diagram.tsx` — the reusable island: `role="img"`, the SVG, its own
  scroll container under `templates-diagram`.
- `web-client/src/islands/TemplateDiagram.tsx` — the Templates wrapper: subscribes, POSTs, owns
  the stale line and the `aria-label`.
- `web-client/src/islands/TemplateEditor.tsx` *(modified)* — publishes `{yaml, ok}` on every path
  `validate()` can take.
- `web-client/src/styles/diagram.css` — tokens only.
- `web-client/src/pages/templates/[name]/[version].astro` *(modified)* — reads the stored
  version's graph server-side and mounts the island where the placeholder was.
- `web-client/tests/unit/diagram-{fixtures,layout,svg,state,island}.test.ts`,
  `template-diagram-island.test.ts`, `template-validation-store.test.ts`,
  `web-client/tests/e2e/template-diagram.spec.ts` — the tests.
- `web-client/tests/e2e/stub-backend.mjs`, `templates-fixtures.mjs` *(modified, additive only —
  `git diff --numstat` reports 145/0 and 143/0)* — the two `/graph` routes, a lexical
  `graphFromYaml`, and the shipped `epic@1` fixture.
- `web-client/tests/e2e/templates.spec.ts` *(modified — the one anchor revision, 3 lines)* — see
  the Spec Change Log.
- `web-client/package.json`, `pnpm-lock.yaml` *(modified)* — `@dagrejs/dagre` pinned at `3.1.1`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` *(modified, generated)* —
  `make openapi`; never hand-edited (AD-3).

**Review findings breakdown:** 12 patches applied (0 high, 6 medium, 6 low — see the Review
Triage Log); 5 deferred (0 high, 2 medium, 3 low — see frontmatter `deferred`); 16 rejected.
The rejections, by reason: eight defensive guards for shapes a validated Template cannot produce
(self-loop and back edges, duplicate node ids, duplicate edges, an empty `points` array, an empty
kind segment, `Math.min` spread overflow, a `for_each` with no members) — each would add a branch
no test can reach, against the coverage gates and against 3.4's own precedent; a `graph` prop
changing after mount (the island is recreated wholesale by a full page navigation, the reasoning
`TemplateEditor` already documents); an `aria-label` that would say "editing" for unsaved text
(the brief fixes that string exactly); `resetTemplateValidation` living in `src/` (the idiomatic
nanostore test reset); `GATE_CHAR_WIDTH` as a hardcoded mono advance (the alternative,
`text-decoration` on SVG text, is less portable than an explicit `<line>`); three sequential
server-side reads on page load and the second validation each refresh cycle costs (both
localhost, both documented); the frontend test's restatement of the kind table (test-only, and
asserted over all eleven rows); and "the SVG scales to the column width" (implemented as scroll
only — scaling a 132px box into a 300px column would put the type below the one size this
product sets it in, which `Diagram.tsx` states).

**Follow-up review recommendation:** `true`. Patched findings score `3 × 6 (medium) + 1 × 6
(low) = 24`, at or above the threshold of 5; no patched finding was `high`.

**Verification performed (on the current tree, by the orchestrating session — not taken on a
subagent's word), after the patches above:**
- `make lint` — exit 0: ruff, `ruff format --check`, `mypy --strict` on `domain/`+`application/`,
  `lint-imports` (3 contracts kept, 0 broken), env contract (26 fields / 32 variables), both
  test-pair gates (59 backend modules, 42 web-client), `gen:api --check` with no drift, astro
  check (106 files, 0 errors), tsc, eslint, prettier.
- `make test` — exit 0: 2160 backend tests passed, 1 skipped; `coverage report --include=
  'src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` reported 100 %
  over 1668 statements and 474 branches with 0 missed and 0 partial; web-client 719 tests passed
  across 35 files, `src/lib/diagram/**` at 100 % lines.
- `make openapi` — exit 0, and `make lint` afterwards showed no drift.
  `/api/v1/templates/{name}/graph` publishes `get` (200/401/404/422/500) and `post`
  (200/401/422), both with a summary and `ProblemDetail` on every refusal;
  `HTTPValidationError` is still absent from the document.
- `make e2e-ui` — exit 0: 72 Playwright tests passed, including the frozen `shell.spec.ts`, the
  revised `templates.spec.ts`, and all 12 diagram scenarios. (The host's
  `ai-orchestrator-web-client-1` container was stopped to free port 4321 and restarted after.)
- `make e2e` (which builds a disposable stack and runs `e2e-api` inside it) — exit 0: 90 tests
  and 21 schemathesis subtests passed, including both new operations against real seeding, a real
  PostgreSQL and the real validator, with no 5xx from any generated request.
- Matrix Test Audit: every one of the thirteen I/O & Edge-Case Matrix rows has at least one test
  that ran and passed in the runs above; the two rows the first pass covered only at the reducer
  or only in backend JSON (a failing graph request, and `epic@1` drawn) are now covered in a
  real browser as well.

**Residual risks:**
- The five items in frontmatter `deferred`, of which two matter to Epic 8: `Diagram.tsx`'s
  hardcoded `templates-diagram` test id, and group rectangles being post-hoc bounding boxes
  rather than dagre compound nodes.
- Every browser-surface assertion runs against `stub-backend.mjs`'s `graphFromYaml`, a lexical
  restatement of `application/graph.py`. It is pinned to the real answer at both ends — the
  backend e2e asserts `epic@1`'s ids, kinds, labels, gates, flags, groups and edges against the
  running stack, and the browser fixture is byte-identical to that — but the two are separate
  statements of one shape and a future change to the builder must update both.
- The eyebrow reads a kind's last segment rather than the whole kind, for the reason recorded in
  the Spec Change Log. The eleven registry kinds have eleven distinct last segments today; a
  twelfth kind colliding on one (`github.link` beside `pr.link`) would conflate two eyebrows,
  and the test that would catch it is a frontend restatement of the table, not the table itself.
