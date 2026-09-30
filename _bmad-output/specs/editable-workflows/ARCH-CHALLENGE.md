---
title: Architecture challenge — editable workflows for deployed instances
type: arch-challenge
status: draft — nothing here is ratified; §10 lists what the Operator decides
created: 2026-09-30
spine: ../../architecture/ARCHITECTURE-SPINE.md
companion: PM-CHALLENGE.md (PM agent, written in parallel; not read here)
---

# Architecture challenge — editable workflows

Every claim below was checked against `main` at `7727803`. Paths are relative to the repository root; `path:line` cites the line read.

## 0. What is already true (so the ask is smaller than it reads)

- **Ask 1 is already the storage model.** `TemplateVersionRow` has no update path (`backend-api/src/orchestrator/infrastructure/db/models/template.py:43-55`); `save_version` stores `max+1` (`backend-api/src/orchestrator/application/use_cases/templates.py:241-264`); a Run copies `(template_name, template_version)` and the whole resolved tree into `run.pinned_versions` (`application/use_cases/create_run.py:203-205`), and `plan_run` materialises every row before enqueue (AD-7). A new version therefore already reaches new Runs only. Nothing FK-references `template_version`; `pinned_by` is a JSONB containment count (`infrastructure/db/repositories/templates.py:152-161`).
- **"Add your own workflow" already works at the API**: `POST /templates/{name}/versions` with `version: 1` on a new name. What is missing is the affordance (`/templates` redirects to the first stored Template, `web-client/src/pages/templates/index.astro:3`), provenance, and a seed that does not collide with the Operator's edits.
- **Ask 2 is half there**: a harness/model per agent step is a template concern — every agent row's `with.harness` / `with.model` resolves from the template's own inputs at plan time (`application/templates/plan.py:143-160` `root_scope`; `application/steps/agent.py:203-215` reads `with_resolved["harness"]`). `templates/drafts/story-staged.yaml:27-30` already declares `plan_model`, `build_model`, `review_model`. What is missing is that `create_run` probes only the run-level pair (`create_run.py:164-176`) and the New Workflow form renders every input as free text (`web-client/src/components/NewWorkflowFields.tsx:146-158`).
- **Ask 4 is the one real collision** with the spine, and it is also the root of the known upgrade defect. Both are settled by one decision (§2).

## 1. Where the request collides with the spine

**AD-15** — *Prevents*: "a Run resolving a changed callee". *Rule*: "… non-literal `version`, `parallel`, `timeout_min`/`on_fail` on `template` are rejected"; "Saving creates version n+1; a version pinned by any Run, directly or as a callee, is frozen." Code: `keys.py:339-348` `_check_call_with` refuses a call without `version` (`missing key`) or with a non-integer one (`non-literal version`); `calls.py:93` fetches the callee at the literal pair; `domain/entities/template.py:9` "`calls` is the pinned callee list, recorded when the version was saved".

Ask 4 wants the parent to follow the child. Read literally, that is "a Run resolving a changed callee". But AD-15's *prevents* line names a **Run**, and a Run never resolves anything after `create_run`: the tree is resolved once (`use_cases/plan_run.py:47-61`), written to `run.pinned_versions`, and the walker "executes only existing rows in `seq` order" (AD-7). The thing that would change is the **Template's reference**, resolved at plan time. So: *resolve an unpinned callee to its latest stored version at plan time and pin the resolved snapshot on the Run* keeps every outcome AD-15 prevents (a planned Run still sees exactly the versions it pinned; those versions stay frozen) and gives the Operator ask 4. What has to move is the sentence that makes the reference literal.

Proposed amendment to AD-15 (Operator ratifies; I do not edit the spine):
> "… expressions beyond the grammar, cycles, depth > 3, callee input name/type mismatches, **a `version` that is neither a positive integer literal nor omitted**, `parallel`, … are rejected. **A call that omits `version` is unpinned: it resolves to the callee's highest stored version — at validate time for the binding, cycle and depth checks, and again at plan time — and the resolved `(name, version)` is what `run.pinned_versions` records; a call that writes an integer is pinned to exactly that version. A Run is planned from resolved versions only and never re-resolves.** … Saving creates version n+1; a version pinned by any Run, directly or as a callee, is frozen."

And to the *Prevents* line: "a Run resolving a changed callee **after it was planned**".

**AD-7** — "expands the pinned tree into rows" stays true (the tree is pinned by resolution). Two stale sentences should go in the same ratification: "PRD `dev-loop` is `initiative@1 → epic@1 → story@1`" and "`story@1` has no checkout and is a callee only; every other shipped template is a root … (`initiative`, `initiative-hub`, `epic`, `repo-init`…)" — `initiative` is retired (`62a37eb`) and version numbers in the spine are exactly what ask 4 removes. Proposed: "the shipped roots are whatever `templates/*.yaml` declares no required `item` input for (`web-client/src/lib/newwf/catalog.ts::rootStartable`); shipped callees are unpinned."

**AD-10** — "`create_run` rejects a model outside the probed list with 422 naming the list, on every create". With a model per agent step the run-level pair is no longer the only one. Proposed: "… rejects, for **every distinct `(harness, model)` pair the planned `agent` rows carry**, a model outside that harness's probed list …". Also "The form probes on harness selection" → "on each harness selection the form carries".

**AD-8 / AD-7** — mid-Run edits of a `planned` row's `with_resolved.harness/model` (ask 2 read maximally). AD-7 prevents "plans that change on recovery or with a later repository edit"; AD-8 gives `step_run` writes to use cases only. An override is not a status write, so AD-8 admits it as a `signal_run` operator transition; AD-7 does not. §5 defers it and names the amendment it would need.

**AD-3, AD-20, AD-2, AD-6** — no collision: every new endpoint goes through `make openapi` → `pnpm gen:api`; no new setting is needed (§7); the capabilities endpoint reads `application/` tables from `api/` (allowed direction); the walker's step sequence does not change, so `DBOS_APPLICATION_VERSION` is not bumped.

**Entity docstring, not spine but load-bearing**: `domain/entities/template.py:9-11` and `calls.py:18-21` ("Below the root, the traversal reads `TemplateVersion.calls` — the callee list pinned when that version was saved") must be rewritten by the story that lands §2, or they become the copy that drifts.

## 2. Callee resolution design

| Option | Validate on save (callee unstored) | `calls` semantics | Cycle/depth | Seed order | Verdict |
| --- | --- | --- | --- | --- | --- |
| (a) `version: latest` keyword | keyword is a string → today's `is_count` path refuses it; needs a third branch | `{name, version: "latest"}` — a string in an int column | must resolve | fine | Second spelling of "absent"; every reader gains a sentinel. **Reject.** |
| (b) omit = latest, integer = pin | `callee not found` when `list_versions(name)` is empty; bindings checked against latest's `inputs:` | `TemplateRef.version: int \| None`; `None` = "resolved at use" | resolve `None` → `latest_version` on the current store, then walk exactly as today | unchanged: an unpinned callee not yet stored is `callee not found` → retried next round (`templates.py:267-298`) | **Recommend.** |
| (c) always latest, drop the key | same as (b) | `TemplateRef.name` only | same | same | Loses the only escape hatch the reverse-check below needs; kills the readiness/fixture ability to freeze a caller. **Reject.** |

**Why (b) needs the pin to survive.** A child that gains a *required* input breaks every unpinned caller; a caller cannot bind the input first (`callee input mismatch`, `calls.py:157-160`). The way out is: pin the parent to `child@k`, save `child@k+1`, then re-save the parent unpinned with the binding. Under (c) the Operator is deadlocked into "add it optional with a default".

**Reverse check on save (new rule, `save_version`)**: after validating the posted text, for every latest version of a name whose `calls` names this name unpinned (`callers_of(name, None)`), re-run `validate()` on that caller's YAML against a store view where this name's latest is the candidate. Any error → 422 with `errors[]` carrying `template = <caller>`, `reason = callee input mismatch`. The save is refused, never silently allowed to strand a parent at plan time. (Today a stranded parent surfaces as `PlanError(CALLEE_NOT_RESOLVED)` naming the caller and a line — the misleading message the 2026-09-29 note records.)

**Data shape.** `TemplateRef.version: int | None`; `TemplateVersion.calls` records what the file *declares* (None = unpinned) — it is still what `_calls_of` derives from the validated tree (`templates.py:336-355`), so the "cannot disagree with the file" property holds. `callers_of(name, version)` matches `calls[*].version == version OR calls[*].version IS NULL` (the JSONB containment in `repositories/templates.py:143-150` becomes two containments). `pinned_by` is untouched: `run.pinned_versions` always holds resolved integers. `GET /templates/{name}/{version}` `calls[]` gains `resolved_version` (current latest, computed at read time) beside `version: int | null`. The template graph's `NodeCall` (`application/graph.py:205-209`) carries `{name, version: null, resolved_version}` and labels `name@{resolved}`.

**Plan time.** `resolve_tree` (`use_cases/plan_run.py:47-61`) resolves `None` through `latest_version` *once per name* per plan (a diamond must not resolve two versions of one callee inside one Run) and re-runs the cycle/depth guard over the *resolved* refs — validate-time results are stale by definition once the store has moved — raising `PlanError` with new reasons `call cycle` / `call depth over 3` in `plan_model.py`.

**The upgrade defect disappears** without bumping pins: shipped files drop `version:` from every call; whatever number seeding assigns, the parent resolves the current content. `test_shipped_smoke.py:173` (a caller pinned to `epic@1` keeps the old content) stays true for an *explicit* pin, which is exactly what it fixtures.

**How a Run records the tree.** Keep `run.pinned_versions` (flat, root-first — the containment query depends on it). Add `run.template_tree` (JSONB, NOT NULL, `server_default '{}'` — the nullable-column set of `run` is frozen by `tests/unit/test_run_repository_adapter.py`, see the reasoning at `domain/entities/run.py:83-89`), shape `{"name","version","calls":[{"step":"epics.epic","name","version","calls":[…]}]}`, built by `resolve_tree` in walk order. Old Runs read `{}` and the detail falls back to the flat list. One migration (`0022_run_template_tree`). A `run_template` table is the wrong trade: never queried into, always read with its Run — the same reasoning `models/run.py:3-7` gives for every other list on that table.

## 3. Seed and examples model for deployments

Today `_seed_file` (`templates.py:301-319`) inserts any new hash as `max+1` under the shipped name. After the Operator edits `initiative-hub` (v2, theirs), the next image seeds the shipped text as v3 and every name-resolution (`INIT_TEMPLATE`, `READINESS_TEMPLATE`, `ROOT_TEMPLATES`, unpinned callers) silently switches to the shipped content. That is "an upgrade changed my workflow" and it is the collision to design out.

| Option | Verdict |
| --- | --- |
| `origin` column only, seed still inserts | Provenance without protection. Not enough. |
| Separate `example-*` names | Every shipped callee name changes; `INIT_TEMPLATE=repo-init` and friends must be re-pointed; the readiness fixture flow (`epic`→`story`) gets renamed too. Churn with no benefit. |
| Read-only Examples catalogue from disk, no seeding at all | Fresh installs would have no Templates until the Operator copies; readiness (`READINESS_TEMPLATE`) and init would fail on first boot. |
| **`origin` column + seed-never-overrides-operator + disk catalogue with "Copy"** | **Recommend.** Fresh installs unchanged; edited names are owned by the Operator from then on; the shipped text stays reachable as reference. |

**Migration `0021_template_version_origin`**: `template_version.origin TEXT NOT NULL DEFAULT 'legacy'` (`shipped | operator | legacy`), `template_version.restored_from INTEGER NULL`. `legacy` is the only honest backfill (a migration may not read disk), and the seed rule treats `legacy` as `shipped`: an upgraded install behaves exactly as today for names it never touched, and the first save after the upgrade makes the name the Operator's.

**Seeding rule (pin this paragraph in a test):** For each shipped `(name, text)`, in retry rounds as today: (1) if any stored version of `name` has `hash == sha256(text)` → nothing (`inserted_as = None`); (2) else if no stored version of `name` has `origin = 'operator'` → insert as `max+1` with `origin = 'shipped'`; (3) else → insert nothing, `SeedResult(name, inserted_as=None, withheld=True)`, logged at `info`; the text remains readable through `GET /examples/{name}` with `stored_as = null`. A name is Operator-owned by *any* operator version, not by its latest, so a restore (an operator version) also claims the name.

`ROOT_TEMPLATES`, `INIT_TEMPLATE`, `READINESS_TEMPLATE` keep resolving name → latest (`templates.py:173-183`), which is now the Operator's version whenever one exists — the intended behaviour. `templates/drafts/` stays unseeded and unlisted (they are retired files, `AGENTS.md`), unless the Operator decides drafts belong in the catalogue (§10). Examples are served through a new port `ShippedTemplateSource.list() -> [(name, text)]` with `infrastructure/templates_loader.py` as its adapter (it already reads `Settings.templates_dir`), so `application/` still does no I/O (AD-2).

## 4. Restore

`POST /templates/{name}/{version}/restore`, empty body → `201 TemplateVersionOut` of the new version; `404` unknown pair; `422 errors[]` exactly as save. Semantics: take version k's `yaml`, rewrite only its `version:` line to `max+1` (the editor already does this client-side, `web-client/src/islands/TemplateEditor.tsx:151` `rewriteVersionLine`; the server needs the same pure function in `application/templates/`), run `validate()` in full — including the reverse check of §2 — and store with `origin = 'operator'`, `restored_from = k`. A version saved before a validator tightening (the `prompts` clauses, 2026-09-27) may no longer validate: refuse with the validator's own errors, no exception — the Operator opens k in the editor, fixes, saves. `hash` differs from k's because the version line differs; `restored_from` is the provenance, not the hash. Old versions are already viewable at `/templates/{name}/{version}` and never deletable; nothing else is needed for "history only".

## 5. Per-agent harness and model

**(a) Template-level typed inputs** — add `harness` and `model` to `InputType` (`application/templates/model.py:28`). A `harness` input's default must be a harness name; a `model` input is free text. The form renders a `harness` input as a select over `GET /harnesses` (enabled ones first, disabled greyed with `failing_check`) and a `model` input as the select/text the island already builds from the probe (`NewWorkflowFields.tsx:160-190`), keyed to the `harness` input the template names beside it. Today the form owns the fields by *name* (`catalog.ts` `FORM_OWNED_NAMES`); by type is the rule that survives a template author calling them `plan_model` / `review_harness`. Shipped files change `harness: { type: enum, values: [claude, codex, local] }` to `{ type: harness }` — which also removes the harness list from YAML. Zero orchestrator change beyond the type and the check below.

**(b) Run-level override map** `overrides: {"epics.epic.stories.story.build": {harness, model}}` applied at plan time — feasible (index-free row path is well defined, `keys.py:119-132` + the call segment), but it is a second mechanism that fights the template author's declared inputs, needs its own validation against the resolved tree, and answers a question (a) already answers. **Defer to v2**, to be revisited if the Operator wants overrides on templates they did not author.

**Recommend v1 = (a).** Mid-Run edits of not-yet-dispatched rows: **out of v1.** The v2 path is a `retarget` signal (`domain/statuses.py:61-74` `SignalKind`) admitted only while the Run is `needs_you`, payload `{path, harness, model}`, on a `planned` row only, written by `signal_run` in its unit of work (AD-8 admits it), validated against the same probe rule. DBOS is not the obstacle: the walker reads the row inside the engine step that runs it, so a value changed before the row is `queued` is the value used, and replay re-reads the same committed row; no application-version bump. The obstacle is AD-7's "plans that change" — it needs a ratified carve-out ("`with_resolved.harness` and `.model` of a `planned` row may be re-targeted by the `retarget` signal; every other field of a plan is fixed").

**Validation, where it lives.** Replace `create_run.py:164-176` (run-level pair only) with a check over `plan.rows`: for every row of `kind == AGENT_KIND`, collect distinct `(with_resolved.harness, with_resolved.model)`; each harness must have an adapter in `harness_registry` (else 409 `harness not available`) and a passing probe (409 with `failing_reason`); a model outside a **non-empty** probed list is 422 naming the list (empty list = gateway-disabled, free text, `domain/ports/harness.py:74-75`). Probe each harness once per create. Mirror it as a pre-flight line (`application/preflight/checks.py:306-330` `harness_probe_line` today reads `req.harness` only) so the form's *What will run* shows the same refusal before *Start run*. Readiness (`enabled`) stays informational per AD-10; the probe is the gate.

## 6. The helpers — a capabilities catalogue

`GET /api/v1/capabilities` (read-only; `?probe=true` opts into shelling each harness's `probe` verb, off by default because the form already probes on selection and a probe is a subprocess per harness). Derived, never restated:

```
{ dsl: { template_keys, input_keys, input_types, step_keys, agent_keys, for_each_keys,
         run_sugar_key, dispatch_keys, intent_keys, call_timing_keys, gates, on_fail_actions,
         status_tokens, max_call_depth,
         kinds: { <kind>: { with_keys, gate_default, timeout_default_min, stall_default_min } },
         expression: { forms: ["{{name}}", "{{name.field}}"], entity_fields: {project:[…], repository:[…]},
                       conditions: "<name>.<field>", escalate_when: "output.status == <token>" },
         reasons: [ …every validator reason string… ] },
  harnesses: [ { name, enabled, failing_check, version_pin, configured_models: […], probe: null | {ok, failing_reason, version, models} } ],
  skills: { available: [ … ] | null } }
```

Sources (one each, the ones the validator reads): `application/steps/__init__.py` `KIND_META`, `TEMPLATE_KINDS`, `GATES`; `application/templates/table.py` `TEMPLATE_KEYS INPUT_KEYS STEP_KEYS AGENT_KEYS FOR_EACH_KEYS CALL_TIMING_KEYS RUN_KEY`; `application/templates/model.py` `INPUT_TYPES ON_FAIL_ACTIONS STATUS_TOKENS` and the reason constants; `application/templates/keys.py:289-292` `_DISPATCH_KEYS`, `_INTENT_KEYS` (move to `table.py` and make public — the underscore is the only reason a second list could appear); `application/templates/expressions.py:60` `ENTITY_FIELDS`; `application/templates/calls.py:49` `MAX_DEPTH`. Harnesses: `use_cases/harnesses.list_harnesses` + `infrastructure/harness/models.py::model_table` (already joined in `api/routers/harnesses.py:34-37`) + `use_cases/harness_probe.probe` when asked. Skills: the `SkillCatalog` port (`domain/ports/skill_catalog.py`) over `{agent_home}/.claude/skills-manifest.json` written by `scripts/harness/_common.sh::write_skills_manifest` — the same source pre-flight's skill line uses (`api/providers.py:166`); `null` when the manifest is unavailable, which is a broken instance and is reported as such, not as "no skills". Modules: `application/use_cases/capabilities.py` (pure assembly), `api/schemas/capabilities.py`, `api/routers/capabilities.py`. The one test that matters asserts `kinds.keys() == TEMPLATE_KINDS` and each list equals its source frozenset — derivation, not a copy.

## 7. API, contract, migrations, settings, web-client

| Method, path | Change | Errors |
| --- | --- | --- |
| `GET /templates` | `TemplateSummaryOut` + `latest_origin`, `operator_owned: bool` | — |
| `GET /templates/{name}/{version}` | `TemplateVersionOut` + `origin`, `restored_from`, `calls[].version: int\|null`, `calls[].resolved_version` | — |
| `GET /templates/{name}/{version}/graph` | `NodeCall.version: int\|null`, `+resolved_version` | — |
| `POST /templates/{name}/versions` | unchanged body; new 422 case: reverse check, `errors[].template` = the caller | 422 |
| **`POST /templates/{name}/{version}/restore`** | new, empty body → 201 `TemplateVersionOut` | 404, 422 |
| **`GET /examples`, `GET /examples/{name}`** | new feature router (a literal `examples` segment under `/templates` would fight `/templates/{name}/{version}`, registered last — `routers/templates.py:142-144`); `ExampleOut{name, description, yaml, hash, stored_as: int\|null, withheld: bool}` | 404 |
| **`GET /capabilities`** | new, §6 | — |
| `GET /runs/{id}`, `GET /runs` | `+template_tree` | — |
| `POST /runs` | unchanged in v1 (per-agent via typed inputs); the agent-pair probe check tightens refusals | 409, 422 |

Migrations: `0021_template_version_origin` (`origin`, `restored_from`), `0022_run_template_tree`. Head today is `0020_drop_run_initiative`. **Settings: none** — `TEMPLATES_DIR`, `INIT_TEMPLATE`, `READINESS_TEMPLATE`, `ROOT_TEMPLATES` already exist; AD-20 is satisfied by adding nothing. Every story that touches `api/schemas/` runs `make openapi` (exports `contracts/openapi.json`, then `pnpm gen:api`; `pnpm gen:api --check` in `make lint` refuses drift).

Web-client surfaces: `pages/templates/index.astro` (list with origin badge, *New template* → editor seeded with a minimal skeleton at `version: 1`, *Examples* panel with *Copy to my workflows*); `pages/templates/[name]/[version].astro` + `components/templates/VersionsList.astro` (*Restore* per row, `origin`/`restored_from` shown); `islands/TemplateEditor.tsx` (helper panel from `/capabilities`, callee `name@resolved` shown from the graph); `pages/workflows/new.astro` + `NewWorkflowFields.tsx` + `lib/newwf/catalog.ts` (typed `harness`/`model` rendering, by type not by name); `islands/RunDetail.tsx` (template tree line "planned from a@3 → b@5 → c@7"). `DEPLOY.md` gains one paragraph: an upgrade never replaces an Operator-owned name; withheld shipped files are listed under *Examples*.

## 8. Test strategy (hard rule 6)

New test files carry the bulk; each new source module gets its pair. Fixtures are the test's own copies, never `templates/*.yaml` text (Operator ruling 2026-09-10). Existing tests whose assertions pin behaviour a declared change revises — the hand-back cites "editable-workflows §2/§3/§5, Operator ratification of the AD-15/AD-7/AD-10 amendments, date":

- `backend-api/tests/unit/application/templates/test_template_keys.py::test_a_call_with_no_version_is_missing_a_key` (:719) — an omitted version becomes accepted (§2). `::test_a_call_whose_version_is_not_a_literal_is_refused` (:725) stays as is (`'{{v}}'` is still refused).
- `…/test_template_calls.py::test_a_call_whose_name_or_version_is_not_a_literal_is_left_to_the_key_table` (:73) — a missing version is now resolved, not left; `::test_a_call_to_a_version_that_is_not_stored_is_not_found` (:47) unchanged for pinned calls.
- `…/test_shipped_smoke.py::test_every_pinned_call_of_every_shipped_version_is_found_by_the_resolver` (:149) — walks `stored.calls` and calls `tree.callee(ref.name, ref.version)`; with unpinned shipped calls `ref.version` is `None` → resolve first. `::test_a_shipped_files_content_change_lands_as_a_new_version_and_old_callers_still_resolve` (:173) — unchanged (explicit pin fixture) **but** the seeding rule of §3 must keep inserting for a name with no operator version; the fixture's `prior_epic` needs `origin='legacy'`, the default.
- `…/test_use_cases_templates.py::test_seed_shipped_*` (:302-374) — the seeding rule gains case (3); `::test_seed_shipped_reseeds_a_file_whose_hash_changed` (:333) must state which origin the existing version has. `::test_save_version_pins_a_root_level_call_into_calls` (:266) / `_nested_in_a_for_each` (:274) unchanged (their fixtures pin); new tests cover `version: None`.
- `tests/unit/test_templates_router.py::test_get_version_answers_the_stored_text_and_zero_calls` (:107) and `tests/unit/test_templates_schemas.py` — if either holds an exact-dict equality on `TemplateVersionOut`, the added fields revise it (same pattern as the `HarnessOut` closed-set rulings recorded at `api/schemas/harnesses.py:3-14`).
- `tests/e2e/test_templates.py::test_epic_1_shows_its_call_and_its_inputs` (:96) asserts `body["calls"] == [{"name": "story", "version": 1}]` — this already pins shipped content against the 2026-09-10 ruling and breaks when `epic.yaml` drops the pin; revise to structural (`version` is `int | None`, `resolved_version` is an int the store holds).
- `tests/unit/application/test_create_run_use_case.py` (:134, :178) — fixtures pin explicitly; unchanged. The probe-check generalisation (§5) revises whatever test pins "only the run-level model is probed" — `grep -n probe tests/unit/application/test_create_run_use_case.py` at story time; if none, it is new coverage only.
- `tests/unit/test_run_repository_adapter.py` — closed nullable-column set: untouched by design (`template_tree` is NOT NULL with a default).
- `tests/unit/test_harnesses_router.py::test_harness_out_of_renders_every_field`, `tests/e2e/test_harnesses.py::test_the_response_is_the_one_list_envelope` — untouched: the catalogue is its own schema, `HarnessOut` does not change.
- web-client: `tests/unit/newwf-catalog.test.ts`, `newwf-fields.test.ts`, `newwf-model-select.test.ts` — the name-based `FORM_OWNED_NAMES` rule becomes type-based (§5a); `template-editor-island.test.ts` unchanged (save still rewrites the version line); every new island/page gets its unit test and Playwright smoke per `web-client/AGENTS.md`.

Unit tests of the new rules use `tests/unit/fakes/templates.py` (`FakeTemplateVersionRepository` — extend it for `origin`/`callers_of(name, None)`; do not create a second double), `tmp_path` template directories for seeding, and `FakeHarness` adapters for the probe rule. Coverage floors (100 % branch on `domain`/`application`) apply to every new module.

## 9. Sequenced plan

Ratification first: **R-1** AD-15 wording + *Prevents* line; **R-2** AD-7 stale shipped-list/version sentences; **R-3** AD-10 "every planned agent pair". R-1 gates Epic A; R-3 gates story C-2; R-2 is documentation hygiene and can ride with either.

**Epic A — Unpinned callees (needs R-1)**
- A-1 `TemplateRef.version: int | None`; validator accepts an omitted call `version`, resolves it to latest for binding/cycle/depth; `_calls_of`, `callers_of` (null-aware), graph `NodeCall.resolved_version`; entity and `calls.py` docstrings rewritten. Gate: `make lint && make test`. **opus**
- A-2 `resolve_tree` resolves once per name, re-guards cycle/depth as `PlanError`; `run.template_tree` + migration 0022 + `RunOut`/detail; `make openapi`. Gate: lint, test, `make e2e-api`. **opus**
- A-3 Reverse check on save (callers of an unpinned callee re-validated; 422 naming the caller). Gate: lint, test. **sonnet**
- A-4 Shipped files drop every `version:` pin; `test_shipped_smoke.py`/e2e revisions cited to R-1; `DEPLOY.md` note that the upgrade defect is closed. Gate: lint, test, e2e-api. **sonnet**

**Epic B — Provenance, examples, restore (A-1 first; A-4 before any deploy)**
- B-1 Migration 0021 `origin`/`restored_from`; seeding rule (1)-(3) with `withheld`; `main.py` log line. Gate: lint, test. **opus** (the rule interacts with `legacy` and restore)
- B-2 `ShippedTemplateSource` port + loader adapter; `GET /examples`, `GET /examples/{name}`; `make openapi`. Gate: lint, test, e2e-api. **sonnet**
- B-3 `POST /templates/{name}/{version}/restore` with server-side version-line rewrite; `make openapi`. Gate: lint, test, e2e-api. **sonnet**
- B-4 web-client: templates index (*New template*, origin badge, *Examples* + copy), versions list (*Restore*), Run detail tree line. Gate: lint, test, `make e2e-ui`. **sonnet**

**Epic C — Per-agent harness and model (needs R-3 for C-2)**
- C-1 DSL input types `harness` and `model`; default of a `harness` input checked against harness rows at create, not at validate (the validator has no harness port — keep it that way). Gate: lint, test. **sonnet**
- C-2 `create_run` and pre-flight probe every distinct planned `(harness, model)` pair; run-level fallback unchanged. Gate: lint, test, e2e-api. **opus**
- C-3 New Workflow renders `harness`/`model` inputs by type (select from `/harnesses`, models from the per-harness probe); `catalog.ts` type-based ownership. Gate: lint, test, e2e-ui. **sonnet**
- C-4 Shipped files declare `harness: { type: harness }`; optional: promote `templates/drafts/story-staged.yaml` (Operator decision, §10). Gate: lint, test. **sonnet**

**Epic D — Capabilities catalogue (independent)**
- D-1 `GET /capabilities` use case, schema, router; `_DISPATCH_KEYS`/`_INTENT_KEYS` made public in `table.py`; `make openapi`. Gate: lint, test, e2e-api. **sonnet**
- D-2 Editor helper panel (kinds, `with` keys, inputs, expression forms, harnesses + models, skills) fed by D-1; no YAML parsing in the browser (AD-15). Gate: lint, test, e2e-ui. **sonnet**

Order: R-1 → A-1 → A-2 → A-3 → A-4 → B-1 → B-2/B-3 (parallel) → B-4; D-1 → D-2 any time; C-1 → (R-3) C-2 → C-3 → C-4. Each story: one conventional commit, gates green, hand-back cites the ratification for any revised test.

## 10. Decisions only the Operator can make

1. Ratify the AD-15 amendment (§1) — the literal-version sentence and the *Prevents* line. Without it Epic A is blocked (hard rule 1).
2. Ratify the AD-7 cleanup (retired `initiative`, no version numbers in the shipped-roots sentence).
3. Ratify the AD-10 amendment (probe every planned agent pair) before C-2.
4. Option (b) for callee resolution (omit = latest, integer = pin) versus (c) always-latest.
5. The seeding rule of §3, in particular "a name with any operator version is never re-seeded" (versus "latest is operator-authored"), and `legacy` as the backfill value.
6. Whether `templates/drafts/*.yaml` appear in the Examples catalogue (flagged `draft`) or stay invisible.
7. Whether the reverse check refuses a callee save that breaks unpinned callers (recommended) or allows it and flags the caller.
8. v1 scope of ask 2 = template-level typed inputs only; run-level overrides and mid-Run `retarget` deferred (the latter needs an AD-7 carve-out).
9. `AGENTS.md` (anchor) edits that follow: the shipped-template list line, the `Kinds:` line if a kind is added (none proposed), and a line stating "shipped callees are unpinned".
10. Whether `story-staged` is promoted from `templates/drafts/` as the first shipped example of a per-step model (it is the motivating case for ask 2).
11. The reset the 2026-09-29 note records as owed (dev template store) becomes unnecessary once A-4 ships; confirm it is not run beforehand on any instance that holds operator edits.
