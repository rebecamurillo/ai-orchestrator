---
title: 'New Workflow picker is driven by ROOT_TEMPLATES and the template’s own inputs'
type: 'refactor'
created: '2026-09-22'
status: 'done'
baseline_commit: '98181df2fca45cd660ce11edfeefea26f4f05cd6'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `web-client/src/lib/newwf/state.ts` hardcodes three rules that make the set of runnable workflows a code constant: `TEMPLATE_ORDER` (which five templates are startable), `TEMPLATE_INPUT_FIELDS` (which fields each one shows), and `usesHarness` (naming `repo-init`). A newly authored template — `epic-oss`, or anything the Operator writes — is seeded, listed, validated and runnable through the API, but cannot be selected in the UI. The backend is already generic: `create_run` enforces no startability rule, `RunIn.inputs` is `dict[str, Any]`, and `GET /templates/{name}/{version}` already serves each input's `{name, type, required, default, values}`.

**Approach:** One env variable, `ROOT_TEMPLATES`, is the source of truth for *which* templates the picker offers and in what order; its default value is the only place a template name is written in code. *What to ask* for each is derived from that template's own declared `inputs[]`, read server-side from the API. No backend change, no contract regeneration.

## Boundaries & Constraints

**Always:**
- `ROOT_TEMPLATES` is a comma-separated name list. Unset, empty, or whitespace-only falls back to `DEFAULT_ROOT_TEMPLATES` — the one hardcoded string in the change.
- The variable is a **filter over what is stored**, never a source of templates: a name it lists that the template store does not hold is dropped, so the picker never offers an option whose version `runBody` cannot pin.
- Order in the variable is display order; the first surviving entry is the default selection.
- A declared input becomes a form field unless its `type` is bound at run time (`project`, `repository`, `item`) or the form already owns a dedicated control for its `name` (`base_branch`, `harness`, `model`).
- Field labels derive from the input name (`spec_folder` → `SPEC FOLDER`). Tooltips come from a map keyed by **input name**, not template name, so every tooltip written today survives and applies to any template declaring the same input.
- `required: false` renders `(optional)`, matching the MODEL/BUDGET convention; a declared `default` prefills the field.
- Adding `ROOT_TEMPLATES` obeys AD-20: `.env.example`, `docker-compose.yml`, and the `COMPOSE_ONLY_VARIABLES` allowlist in `scripts/check_env_contract.py` change in this same commit.

**Ask First:**
- Any change to a backend module, `contracts/openapi.json`, or `src/api/schema.d.ts`.
- Any second env variable beyond `ROOT_TEMPLATES`.

**Never:**
- No template name survives anywhere in `web-client/src/**` except inside `DEFAULT_ROOT_TEMPLATES`.
- Do not make the planner apply declared input defaults (see Design Notes — deferred, not in scope).
- Do not add a startability rule to `create_run`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Variable unset | `ROOT_TEMPLATES` absent | Picker offers the five default names, in default order | N/A |
| Variable blank | `ROOT_TEMPLATES=""` or `"  "` | Same as unset — falls back to the default list | N/A |
| Reordered / extended | `"epic-oss,epic"` | Picker offers `epic-oss` then `epic`; `epic-oss` is the default selection | N/A |
| Names a template the store lacks | `"epic,ghost"` | `ghost` dropped; picker offers `epic` alone | No dead option; no 404 on submit |
| Every listed name is unstored | `"ghost"` | `NO TEMPLATE TO BIND` empty state | Distinct from the unreachable-backend state |
| Duplicates / stray whitespace | `"epic, epic , "` | De-duplicated, trimmed, empty segments dropped | N/A |
| Template with no bindable inputs | `repo-init` selected | Zero input text fields rendered | N/A |
| Optional input with a default | `epic-oss.skill_dir` | Field labelled `(optional)`, prefilled with the declared default | N/A |
| Template declaring no `harness` input | fixture catalog entry | Harness list hidden and `state.harness` cleared | N/A |
| Template declaring a `harness` input | `repo-init` | Harness list shown (behaviour change — see Design Notes) | N/A |

</frozen-after-approval>

## Code Map

- `web-client/src/lib/newwf/state.ts` — the three rules to remove: `TEMPLATE_ORDER`:25, `TemplateName`:26, `DEFAULT_TEMPLATE`:28, `TEMPLATE_INPUT_FIELDS`:37, `isTemplateName`:114, `defaultFormState`:133, `usesHarness`:152, `withTemplate`:161, `reconcileInitial`:388. `FormState.template` becomes `string`.
- `web-client/src/lib/newwf/query.ts` — imports `DEFAULT_TEMPLATE`, `TEMPLATE_INPUT_FIELDS`, `isTemplateName` at :11; uses them at :26, :30, :58. Both exported functions need the catalog.
- `web-client/src/components/NewWorkflowFields.tsx` — picker at :75 maps `TEMPLATE_ORDER`; fields at :146 map `TEMPLATE_INPUT_FIELDS[state.template]`; `isTemplateName` guard at :72.
- `web-client/src/islands/NewWorkflow.tsx` — `usesHarness(state.template)` at :282; passes props to `NewWorkflowFields`; `preflightBody`/`runBody` at :91,:172,:225 already take `templates` and need no change.
- `web-client/src/pages/workflows/new.astro` — `TEMPLATE_ORDER` at :88 drives per-name `GET /templates/{name}/versions` resolution (:91-108). This is where the catalog is built; the best-effort `read()` helper at :46 is the pattern to reuse, and the `unreachable` vs `hasTemplates` distinction at :120-122 must be preserved.
- `backend-api/src/orchestrator/api/schemas/templates.py:78` — `InputDeclOut` = `{name, type, required, default, values}`; served by `GET /templates/{name}/{version}` (`TemplateVersionOut.inputs`:117). Read-only reference — the form's whole data source.
- `web-client/astro.config.mjs:20-28` — typed env schema; `envField` declarations for the existing three server variables.
- `scripts/check_env_contract.py:31` — `COMPOSE_ONLY_VARIABLES`, the allowlist for web-client-only variables (`BACKEND_API_URL` precedent).
- `templates/*.yaml` — read-only. `initiative`/`epic`/`repo-init`/`story-run`/`task` inputs confirm the exclusion rule reproduces today's five field lists exactly.

**Tests that pin the old behaviour** (see Tasks for the authorisation):
- `web-client/tests/unit/newwf-state.test.ts:77,83,107,113` — pins the array, the per-template field counts, the name guard.
- `web-client/tests/unit/newwf-fields.test.ts:19-37` — `render()` builds the component with no catalog; asserts the three root names.
- `web-client/tests/unit/newwf-query.test.ts`, `newwf-save.test.ts`, `newwf-consent.test.ts`, `newwf-island.test.ts`, `newwf-model-select.test.ts` — call the changed signatures indirectly.
- `web-client/tests/e2e/new-workflow.spec.ts:96` — asserts the harness list is absent for `repo-init`.

## Tasks & Acceptance

**Execution:**
- [x] `web-client/src/lib/newwf/catalog.ts` -- new module: `DEFAULT_ROOT_TEMPLATES` (the one hardcoded name string), `parseRootTemplates(raw)` (trim, split, drop empties, de-duplicate, fall back when blank), `TemplateCatalog` type (`names: string[]`, `fieldsFor(name)`, `usesHarness(name)`), `buildCatalog(names, details)` applying the type/name exclusion rule and the by-input-name tooltip map -- keeps `state.ts` under the component/module size rule and gives the parsing and derivation rules a direct unit-test target.
- [x] `web-client/src/lib/newwf/state.ts` -- delete `TEMPLATE_ORDER`, `TemplateName`, `DEFAULT_TEMPLATE`, `TEMPLATE_INPUT_FIELDS`; `FormState.template` becomes `string`; `defaultFormState`, `isTemplateName`, `usesHarness`, `withTemplate`, `reconcileInitial` take the catalog -- removes the hardcoded rules while keeping every pure function testable without a DOM.
- [x] `web-client/src/lib/newwf/query.ts` -- `parseFormStateFromQuery` and `formStateToQuery` take the catalog; an unknown `?template=` falls back to the catalog's first name -- a prefill link must not be able to select a template the instance does not offer.
- [x] `web-client/src/components/NewWorkflowFields.tsx` -- accept a `catalog` prop; render the picker from `catalog.names` and the fields from `catalog.fieldsFor(state.template)`, with `*` / `(optional)` from `required` and `title=` from the derived tooltip -- the component keeps deciding nothing.
- [x] `web-client/src/islands/NewWorkflow.tsx` -- accept and thread `catalog`; `usesHarness(state.template, catalog)` at the harness-list guard.
- [x] `web-client/src/pages/workflows/new.astro` -- read `ROOT_TEMPLATES` from `astro:env/server`, `parseRootTemplates` it, resolve each name's latest version (list read first, `GET /templates/{name}/versions` as fallback) and then `GET /templates/{name}/{version}` for its `inputs[]`, all best effort and in parallel; drop names that resolve to nothing; build the catalog and pass it to the island -- one place owns the reads, so the island and the pure functions stay I/O-free.
- [x] `web-client/astro.config.mjs` -- declare `ROOT_TEMPLATES` as `envField.string({ context: 'server', access: 'public', optional: true, default: '' })`; the module owns the real fallback so that a *blank* value behaves as unset, which `envField`'s own default does not cover.
- [x] `.env.example` + `docker-compose.yml` (web-client `environment:` block) + `deploy/.env.example` + `deploy/docker-compose.yml` if present -- add `ROOT_TEMPLATES` with the default list as its documented value -- AD-20.
- [x] `scripts/check_env_contract.py` -- add `ROOT_TEMPLATES` to `COMPOSE_ONLY_VARIABLES` -- it is read by the web-client and by no backend module, exactly like `BACKEND_API_URL`.
- [x] `web-client/tests/unit/newwf-catalog.test.ts` -- new: every row of the I/O matrix — blank/unset fallback, order, de-duplication, unstored-name drop, the exclusion rule reproducing each shipped template's field list, `(optional)` + default prefill, and both branches of the derived `usesHarness`.
- [x] `web-client/tests/unit/newwf-state.test.ts` + `newwf-fields.test.ts` + the other `newwf-*` unit tests -- revise to build a fixture catalog the test owns and pass it in. **Authorised behaviour change, Operator instruction 2026-09-22: "remove all hardcoded templates names, all must be dynamic, from source of truth env variable."** Each revised test names that instruction and its date. Replace each removed assertion with a stronger one: "the five names are exactly these" becomes "the picker renders exactly the catalog's names, in its order, and never one outside it".
- [x] `web-client/tests/e2e/new-workflow.spec.ts:96` -- same authorisation. `repo-init` declares a `harness` input and has an `agent` step, so the hide was wrong; assert the harness list is now **shown** for it, and let `newwf-catalog.test.ts` own the hidden branch against a fixture template that declares no `harness` input. Coverage strictly exceeds what it replaces: one name-based assertion becomes one behavioural assertion plus two rule assertions.

- [x] `web-client/tests/e2e/templates-fixtures.mjs` -- completed the `inputs` of the three root-Template fixtures (they carried a partial list, unread until now) and added `story-run` and `task`, so the stub answers `GET /templates/{name}/{version}` for every name the default `ROOT_TEMPLATES` offers -- **not anticipated at planning time**: the page now reads declarations the fixtures did not carry, and a name with no fixture is silently dropped from the dropdown.
- [x] `backend-api/tests/unit/test_compose_fails_closed.py`, `test_compose_services.py`, `test_deploy_compose.py`, `test_env_contract.py` -- revised under the same 2026-09-22 authorisation. **Not anticipated at planning time**: `ROOT_TEMPLATES` is the one compose reference that cannot be `${VAR:?}`, because that form refuses an *empty* value too and empty is this variable's documented "use the default". Each revision names the instruction and its date, and each is strengthened rather than relaxed — the bare reference is a named single-member set instead of a dropped invariant, a new test proves every unguarded variable still ships a contract default, and the web-client's four credentials keep their fail-closed parametrisation with a new test proving the exception can never be one.

**Acceptance Criteria:**
- Given `ROOT_TEMPLATES` is unset, when `/workflows/new` is opened, then the picker offers exactly the five default names in their current order and the form behaves as it does today.
- Given `ROOT_TEMPLATES=epic-oss,epic` and both are stored, when the page is opened, then the picker offers those two in that order, `epic-oss` is selected, and its `branch`, `spec_folder` and `skill_dir` fields render — `skill_dir` marked `(optional)` and prefilled with its declared default.
- Given a template is authored, seeded and named in `ROOT_TEMPLATES`, when a Run is started from it, then `POST /runs` receives its declared inputs and the Run plans — with no change to any file under `backend-api/` or `web-client/src/api/`.
- Given `grep -rn` over `web-client/src/lib/newwf` and `web-client/src/components/NewWorkflowFields.tsx` — the New Workflow form's own modules — for any shipped template name, then the only match is inside `DEFAULT_ROOT_TEMPLATES`. (Corrected 2026-09-22 during review; see the Spec Change Log.)

## Spec Change Log

### 2026-09-22 — Review pass 1

- **Finding:** the acceptance criterion and verification command asserted that no shipped template name survives anywhere in `web-client/src/**`. It does not hold and never could: `src/lib/run/detail.ts:235` branches on `detail.run.template !== 'initiative'` to word a Run's progress line, and `src/lib/projects/runs.ts:46` matches `run.template.startsWith('repo-init@')` to find a Repository's last initialisation Run. Both belong to other features, predate this change, and were not touched by it — so the stated check failed while the change itself was complete.
- **Amended:** the criterion and the `grep` now scope to the New Workflow form's own modules, which is what the intent was ever about — the picker's hardcoded rules.
- **Known-bad state avoided:** a green implementation reported as failing its own definition of done, or — worse — the two unrelated modules edited to satisfy a grep, changing two other features to make a string check pass.
- **Not re-derived:** the root cause was a verification step written too broadly, not code. Reverting reviewed, passing code to correct a grep pattern would have destroyed the work without changing a line of what ships. The two surviving branches are recorded in `deferred-work.md` instead.
- **KEEP:** the by-input-name tooltip map (every existing line of copy survives, and a new Template declaring a known input inherits it); the exclusion rule reproducing all five field lists from declarations alone; `ROOT_TEMPLATES` read as `access: 'secret'` so it is a *runtime* read.

## Design Notes

**Why the exclusion rule and not a DSL change.** Filtering declared inputs by `type in {project, repository, item}` or `name in {base_branch, harness, model}` reproduces all five current field lists byte for byte — `initiative`→`initiative_folder`; `epic`→`branch, spec_folder`; `repo-init`→none; `story-run`→`branch, spec_folder, story_id`; `task`→`branch, task_id, title, intent, artifacts_dir`. So the hardcoded table was already a hand-maintained copy of what the templates declare, and deriving it loses nothing.

**The `repo-init` harness flip is a correction, not a regression.** `state.ts:150` claims "`repo-init` runs no agent step". `templates/repo-init.yaml:22` is `- id: context / uses: agent`, and its `inputs` declare `harness`. The form therefore hides a control for a template that genuinely dispatches a harness, and submits an empty harness for it. No derivable rule reproduces the hide; the honest rule is "declares a `harness` input", and that is what lands.

**Declared input defaults are not applied at plan time.** `plan.py::root_scope` builds the scope from `RunInputs.values` — what the Operator submitted — plus the five named inputs. Nothing reads `InputDecl.default`, so `{{skill_dir}}` on a Run that submitted nothing for it resolves to `""`. Prefilling the field closes this for the UI path, which is the path in scope. Closing it for API-created runs is a backend change and is deferred, not silently fixed here.

**Per-template detail reads.** `TemplateSummaryOut` carries no `inputs`, so the page issues one `GET /templates/{name}/{version}` per offered name. With a handful of templates, server-side and in parallel, that is cheaper than widening the contract — and it keeps this change entirely inside the web-client, which is the point.

## Verification

**Commands:**
- `pnpm -C web-client test` -- expected: green, including the new `newwf-catalog.test.ts`
- `make lint` -- expected: green; `check_env_contract.py` accepts `ROOT_TEMPLATES`, `tsc` accepts `FormState.template: string`
- `grep -rnE "['\"](initiative|epic|repo-init|story-run|task)['\"]" web-client/src/lib/newwf web-client/src/components/NewWorkflowFields.tsx web-client/src/pages/workflows` -- expected: no match. Quoted whole names, because the loose pattern also matches `initiative_folder`, an *input* name in `INPUT_COPY` — copy keyed by input, inherited by any Template declaring the same input, and not a rule that names a Template. `DEFAULT_ROOT_TEMPLATES` itself is the unquoted comma list and is the one place the names are written.
- `make e2e-ui` -- expected: green (binds 4321; ask the Operator before freeing the port — hard rule 9)

## Suggested Review Order

**The source of truth, and the one name left**

- Start here: the whole change in one declaration — the default list, and why it is allowed to exist.
  [`catalog.ts:36`](../../web-client/src/lib/newwf/catalog.ts#L36)

- `secret`, not `public` — the one line that decides whether the variable is read at run time or baked in at build time.
  [`astro.config.mjs:42`](../../web-client/astro.config.mjs#L42)

- Blank reads as unset, which `envField`'s own default cannot express.
  [`catalog.ts:131`](../../web-client/src/lib/newwf/catalog.ts#L131)

**The two derivation rules that replaced the hardcoded tables**

- Which declared inputs become fields — reproduces all five old lists from declarations alone.
  [`catalog.ts:149`](../../web-client/src/lib/newwf/catalog.ts#L149)

- Declares a `harness` input, therefore shows the list — the rule that replaced a Template name.
  [`catalog.ts:184`](../../web-client/src/lib/newwf/catalog.ts#L184)

- Copy keyed by input name, not Template name, so every existing tooltip survives and is inherited.
  [`catalog.ts:69`](../../web-client/src/lib/newwf/catalog.ts#L69)

- Operator text becomes object keys here; prototype names are dropped, not thrown on.
  [`catalog.ts:192`](../../web-client/src/lib/newwf/catalog.ts#L192)

**Where it is assembled — the only I/O**

- The variable is read once, server-side, and filtered against what the store holds.
  [`new.astro:48`](../../web-client/src/pages/workflows/new.astro#L48)

- Failures counted, not just dropped: "unread" and "not stored" are two different sentences.
  [`new.astro:131`](../../web-client/src/pages/workflows/new.astro#L131)

- So a failing backend is never reported as an empty instance.
  [`new.astro:170`](../../web-client/src/pages/workflows/new.astro#L170)

**What the form now renders**

- The picker's options are the catalog's names, in the variable's order.
  [`NewWorkflowFields.tsx:77`](../../web-client/src/components/NewWorkflowFields.tsx#L77)

- Fields, mandatory marks and prefilled defaults all come from the Template's declarations.
  [`NewWorkflowFields.tsx:148`](../../web-client/src/components/NewWorkflowFields.tsx#L148)

- The union type is gone, so an unoffered name is refused at run time instead.
  [`state.ts:100`](../../web-client/src/lib/newwf/state.ts#L100)

**The compose exception, and the tests that bound it**

- The one bare reference in the file, with the reason it is not a gate failing open.
  [`docker-compose.yml:101`](../../docker-compose.yml#L101)

- The invariant kept, with a single named exception rather than dropped.
  [`test_compose_fails_closed.py:76`](../../backend-api/tests/unit/test_compose_fails_closed.py#L76)

- Bounded by enumeration, not by how the variable is spelled.
  [`test_compose_services.py:134`](../../backend-api/tests/unit/test_compose_services.py#L134)

**Tests (read last)**

- The rules, and every row of the I/O matrix.
  [`newwf-catalog.test.ts:44`](../../web-client/tests/unit/newwf-catalog.test.ts#L44)

- The Template shapes the tests own — including the optional, defaulted input no shipped Template has.
  [`newwf-catalog-fixture.ts:72`](../../web-client/tests/unit/newwf-catalog-fixture.ts#L72)

- The only assertion that would have caught the build-time inlining bug.
  [`new-workflow.spec.ts:102`](../../web-client/tests/e2e/new-workflow.spec.ts#L102)

- The preview server runs with a deliberately non-default order so that assertion can mean something.
  [`playwright.config.ts:44`](../../web-client/playwright.config.ts#L44)
