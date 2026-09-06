# Epic 3 handoff — what exists, and why it is shaped that way

Written 2026-09-06, after story 3.6. For whoever builds Epic 4 and after.

`epic-1-handoff.md` and `epic-2-handoff.md` still hold: nothing in either was undone here. Read
this once before your first Epic 4 story; you do not need it again.

The commits are `211d526..b9c3505` on `feat/epic-3-templates`: six stories, one operator-directed
copy correction, and one blocked-story record. 166 files, +19328/-106.

---

## 1. What you can rely on

**One parser, one graph builder, and nothing else reads a Template.**

```
application/templates/          validate() is the single public entry point
  validate.py  lines.py  model.py  table.py  keys.py  inputs.py  expressions.py  agent.py  calls.py
application/steps/__init__.py   KIND_META — the only enumeration of step kinds (AD-9)
application/graph.py            build_template_graph(parsed) -> Graph
```

`validate.py` is a *package*, not a file. AD-15's text says "`application/templates/validate.py` is
the single parser/validator"; the frozen 400-line module cap in `test_source_limits.py` makes one
file impossible for a language this size. The invariant AD-15 protects is **one entry function, no
second parser** — that holds. Operator ratified this on 2026-09-05. Do not add a parser anywhere,
in Python or TypeScript.

`/api/v1` now publishes:

```
GET  POST  /api/v1/templates                       (list; POST validate/versions below)
GET        /api/v1/templates/{name}/{version}
GET  POST  /api/v1/templates/{name}/versions
GET  POST  /api/v1/templates/{name}/validate
GET        /api/v1/templates/{name}/{version}/graph      api/routers/graph.py
GET  POST  /api/v1/templates/{name}/graph                api/routers/graph_text.py
```

**Three routers, not one, and the reason is frozen tests.** `test_templates_router.py` pins
`templates.py` to exactly six routes, and `graph.py` carries a "every route here includes GET"
assertion. So the graph endpoints live in their own modules, following Epic 2's `clone_check.py`
precedent — same paths, same prefix, same bearer dependency, invisible from outside.
`graph_text.py` **must stay mounted before `templates.router`**, or `GET /templates/story/graph`
resolves as `version="graph"` and 422s. Epic 4's `GET /runs/{id}/graph` belongs in `graph.py`.

**Every published path needs a GET.** `test_bearer_auth.py` indexes `paths[path]["get"]` for every
path in the contract. A POST-only path fails it. That is why `GET /templates/{name}/validate` and
`GET /templates/{name}/graph` exist at all.

**Tables and seeding.** `template{name pk, description, created_at}` and
`template_version{id, name fk, version, yaml, hash, calls, created_at}`, unique `(name, version)`.
Seeding runs at start-up inside `main.run_migrations` — *inside*, because `test_migrations.py`
replaces `main.run_migrations` wholesale, so anything you add to start-up must go in that same
function, not beside it. `seed_shipped` retries in rounds, so shipped files may name callees in any
order; do not assume alphabetical or dependency ordering.

**The screens.** `/templates` (redirects to the first Template's latest version) and
`/templates/{name}/{version}`. `TemplateEditor.tsx` is CodeMirror 6; `Diagram.tsx` is dagre + SVG.
Logic lives in `src/lib/{editor,templates,diagram}/` so it unit-tests without rendering, following
`ProjectForm.tsx`.

**Gates.** All pass from a clean tree: `make lint`, `make test` (2160 backend / 722 web-client,
`domain/` + `application/` **100 % branch, 0 partial, no pragmas**), `make e2e-ui` (72),
`make e2e` (90 + 21 subtests), `make openapi` (no drift).

---

## 2. Decisions that are load-bearing — do not undo these by accident

**`TemplateVersion.calls` is stored, and depth and cycle detection read it.** For any template
below the root, the validator resolves calls from the stored `calls` list, not by re-parsing the
callee's YAML. Nothing ties `calls` to the row's `yaml` or `hash`. A stale or wrong `calls` means
wrong depth results and missed cycles — silently. It is filled from the validator's parsed tree at
both save time and seed time by one shared helper.

**Node ids are the join key, byte for byte.** Template-relative, dotted, index-free:
`checkout`, `stories.story`, `stories.after`. The set of paths `validate()` reports in
`unvalidated[]` is a *subset of the graph's node ids*, asserted directly rather than restated as a
format rule. Do not normalise, translate, or prettify an id anywhere. AD-15's example
`stories.story.build` is three segments, which only exists once a callee is expanded — that is the
**run** graph's `step_run.path`; the template graph collapses calls, so its deepest id is two.

**`gate: null` means "not a stop", and only a collapsed call has it.** Every other node carries a
gate word, including the literal `"unvalidated"`. A `template` call is a path segment, never a
stop, even if the file declares a gate on it.

**The `unvalidated` guarantee is per file, not per expanded plan.** A callee's gateless steps do
not surface to the caller, because calls are collapsed and never expanded. This is pinned by a test
rather than fixed. **Epic 4's planner is where this bites** — a plan expanded from `initiative@1`
can contain ungated rows that no Template's own validation reported. Decide there whether NFR-2
means per file or per plan.

**The graph does not carry the pause condition.** An item checkpoint draws as an unconditional
human stop, and a step-level `pause_when` is not `human`. Both follow the brief exactly; both are
recorded as deferred.

**The validated-OK signal is a nanostore, not an event.** `src/stores/template-validation.ts`
carries `{seq, yaml, ok}`. The editor publishes text and validity at its single outcome site; the
diagram column subscribes and fetches its own graph. Chosen because `web-client/AGENTS.md` already
names nanostores as the cross-island mechanism and a store is testable under vitest's `node`
environment, where there is no DOM. `seq` is monotonic so re-validating identical text still clears
the stale line.

**The last-valid-diagram rule keeps the whole previous `Graph` value**, in a pure reducer
(`src/lib/diagram/diagram-state.ts`). Retaining the whole value is what makes "the node ids are
unchanged" a property of the function rather than of array positions.

**The node eyebrow renders a kind's LAST SEGMENT** — `git.worktree` draws as `worktree`. This is a
deviation from brief 3.6, forced by `templates.spec.ts:155`, which resolves
`page.getByText('git.worktree')` unscoped; drawing the full kind puts a second match on the page and
fails Playwright strict mode. That assertion is not a placeholder and could not be revised. A test
asserts all eleven registry kinds have distinct last segments. **If you ever want the full kind
back, the fix is to scope that locator — which needs operator authorisation.**

---

## 3. The rules that will bite you

**Three anchor revisions happened in this epic. All three were operator decisions, in the shape of
a conversation, and NONE is a standing rule.** Cite them as precedent for *asking*, never for
*editing*.

1. `test_env_contract.py` — the hardcoded `"25"` / `"31"` literals. Story 3-2 could not add
   `Settings.TEMPLATES_DIR` without breaking them. Operator authorised the edit in advance, on the
   condition that the counts become *derived* and coverage strictly exceed the literals.
2. `test_settings.py` — `BACKEND_VARIABLES`, a hand-maintained 25-name frozenset, broke on the same
   change. Story 3-2 reported `blocked` (commit `649f5bf`) rather than touching it; the operator
   then extended authorisation. **The derivation matters:** it reads `.env.example` minus the
   compose-only allowlist, *not* `Settings.model_fields` — deriving from the model would make the
   assertion `fields == fields` and silently gut the only thing the test checks.
3. `templates.spec.ts` — the placeholder assertion `'diagram arrives with the next story'`. Story
   3-6 revised it under hard rule 1's **second standing exception** (a test naming a later story as
   its replacement, revised by exactly that story, with strictly greater coverage). Note that
   `AGENTS.md` also says *do not write* an assertion that needs this exception — story 3-5 wrote
   one, asserting the placeholder's copy rather than that the slot is served. Do not repeat that.

**The spine gained a variable.** `TEMPLATES_DIR` was added to `ARCHITECTURE-SPINE.md`'s variable
table (one line) because that table is the source `test_settings.py` encodes; leaving it out would
put code, contract, and spine permanently out of agreement. Operator authorised.

**Adding a setting is now cheap.** Both count checks derive from `.env.example`. The next story
that adds one changes both sides automatically instead of breaking a frozen literal. This trap is
retired.

**`make e2e` is the only gate that catches packaging.** Story 3-3 shipped a Dockerfile that never
copied root `templates/` into the image, so seeding would have failed in the container while every
local gate passed. `make e2e` builds and runs the real image; `make test` cannot see this class of
bug. Run it before you believe you are done.

**Port 4321 is single-tenant.** `make e2e-ui` runs `pnpm preview` on it, and so does the compose
`web-client` container. Stop the container, run the gate, start it again. Stories cannot run in
parallel for this reason, among others.

**A story agent that spawns an implementation subagent must wait for it.** Story 3-5 ended its turn
while its subagent was still writing, leaving 19 uncommitted paths and no commit. Nothing was lost,
but the run stalled until resumed. Finish synchronously or HALT.

**An edited shipped Template seeds as version n+1.** A long-lived stack that already stored the
pre-edit `initiative` keeps answering `initiative@1` with the old shape and gains an
`initiative@2`. Fresh stacks, including `make e2e`, get the new text as v1.

---

## 4. Known gaps, honestly

- **`calls` can go stale.** Nothing recomputes it if a row's `yaml` were ever changed. Immutability
  is what protects it today; freeze-on-pin (Epic 4) must not weaken that.
- **`pinned_by` is always 0.** Nothing counts Runs yet; the schema is there, the enforcement is not.
- **A concurrent write race on `(name, version)`** is a 500, not a 409 — the same unmapped
  `IntegrityError` pattern Epic 2 recorded. Deferred on 3-3.
- **Group rectangles are post-hoc bounding boxes.** dagre is never given `compound: true` or
  `setParent`. Unreachable for a Template (a chain with contiguous loop members); **reachable the
  moment Epic 8's run graph draws a group per callee frame** with anything ranking between two
  members. Fix it there, before drawing.
- **`Diagram.tsx` hardcodes `data-testid="templates-diagram"`.** The brief pinned its props to
  `{graph, ariaLabel}`. Epic 8 needs one optional `testId` prop. `DiagramNode` already accepts
  unused `status` / `current` props and emits them as data attributes, so run tokens arrive as a
  stylesheet rule, not a restructure.
- **No `aria-live` on the stale line**, and no copy when the initial graph read fails. Both
  deferred, on 3-5 and 3-6.
- **`followup_review_recommended: true`** on 3-1, 3-3, 3-5 and 3-6. Roughly twenty deferred items
  sit across the six specs' frontmatter.

---

## 5. What Epic 4 specifically inherits

Epic 4 plans and runs. Four things are already decided for you:

- **`validate()` is your parser and `build_template_graph` is your shape.** `plan_run` calls
  `validate()`; it does not read YAML. `application/graph.py` is where `build_run_graph` goes, in
  the same module, so the two graphs cannot drift.
- **Expansion is yours alone.** The template graph is index-free with loops unexpanded and calls
  collapsed. The run graph is the expanded rows, keyed on `step_run.path`. Nothing in Epic 3
  expands anything — that is deliberate, and the ungated-callee gap above is the first consequence
  you must rule on.
- **Freeze-on-pin is unenforced.** `template_version` is immutable by construction (no update path
  in the repository, no endpoint), but "a version pinned by a Run, callees included, is frozen" is
  schema-only until you count pins.
- **The shipped Templates are real and they validate.** `story@1`, `epic@1`, `initiative@1`,
  `repo-init@1` compose at depth 3 with zero errors and zero `unvalidated` steps. They are the
  planner's first input, and `test_shipped_templates.py` pins their structure.
