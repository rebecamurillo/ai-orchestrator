# Editable workflows for deployed instances — strategy and orchestration plan

Status: draft for the Operator · 2026-09-30 · built from `PM-CHALLENGE.md`, `ARCH-CHALLENGE.md`,
`DECISIONS.md`, `UX-SPEC.md` and `mockups/` in this folder.

## 1. What this delivers

A deployed instance where the Operator edits workflows in the UI, a saved edition applies
only to Runs planned after the save, a parent workflow follows its child's latest version
automatically, every version stays viewable and restorable, the shipped `templates/*.yaml`
are examples that image upgrades never overwrite once customised, harness and model are
chosen per declared agent input when a Run is started, and the editor offers helpers that
list exactly what the orchestrator accepts.

## 2. What is already true (no work)

- Templates are immutable versions; save = max+1; a Run copies the resolved
  `(name, version)` tree into `run.pinned_versions`; nothing FK-references a template.
  A save therefore cannot touch a planned, queued or running Run (AD-7, AD-15). Ask 1 is
  shipped behaviour that only needs to be stated on screen.
- The Templates screen already has a YAML editor with validate-before-save and a versions
  column. A new name is already creatable through `POST /templates/{name}/versions` at v1.
- Agent rows already read `harness`/`model` from the template's own inputs; the mechanism
  for a model per step exists, only the DSL types and the form are missing.

## 3. Decisions (see `DECISIONS.md` for the reasoning)

| Id | Decision |
| --- | --- |
| D-1 | `uses: template` without `version:` is unpinned: resolved to the callee's latest at validate and plan time, pinned on the Run as the resolved snapshot. Integer `version:` stays an explicit pin. Reverse check on save refuses stranding an unpinned caller. Cascade-republish rejected. |
| D-2 | `template_version.origin ∈ {shipped, operator, legacy}` + `restored_from`. Seed never inserts a shipped text under a name that has any operator version; the file stays readable in an Examples catalogue with Copy. Shipped names are editable in place. |
| D-3 | Restore = new version equal to version k, `restored_from = k`, full validation, refused with errors like a save. |
| D-4 | v1 per-agent harness/model = DSL input types `harness` and `model`, rendered by type on the New workflow form; pre-flight probes every distinct planned `(harness, model)` pair. Run-level override maps and mid-Run retarget deferred. Optional v1 add-on: `retry` carrying `{harness, model}` for the next attempt only (attempt-level, AD-7 untouched). |
| D-5 | One read-only `GET /capabilities` derived from the validator's own tables and the harness rows; no second list. |

## 4. Spine and anchor changes the Operator must ratify first

| Ref | Change | Gates |
| --- | --- | --- |
| R-1 | AD-15 rule: "non-literal `version`" → "a `version` that is neither an integer literal nor omitted"; add the unpinned-resolution paragraph; Prevents line: "a Run resolving a changed callee **after it was planned**". | Epic A |
| R-2 | AD-7: retire the `initiative@1 → epic@1 → story@1` sentence and version numbers in the shipped-roots sentence. | hygiene |
| R-3 | AD-10: "rejects a model outside the probed list" → every planned agent `(harness, model)` pair. | C-2 |
| R-4 | `AGENTS.md` root: shipped-template list line; a line "shipped callees are unpinned"; `backend-api/AGENTS.md` if the DSL table lives there. `DEPLOY.md` upgrade paragraph (not an anchor). | A-4, B-1 |
| R-5 | Migrations `0021_template_version_origin`, `0022_run_template_tree` (head today `0020`). | B-1, A-2 |
| R-6 | Test revisions under R-1 (ARCH §8 names them by path): non-literal-version rejection, `seed_shipped` cases, `test_shipped_smoke.py:149,173`, e2e `test_templates.py:96`, web-client `newwf-*` name-based tests → type-based. Each hand-back cites R-1/R-3 and the date. | per story |

Open items for the Operator with the working default: drafts stay out of Examples (default
no); reverse check refuses rather than flags (default refuse); `legacy` as the migration
backfill (default yes); promote `story-staged` as the first per-step-model example (default
yes, as C-4's second half); do not run the owed dev template-store reset before A-4 lands on
an instance holding operator edits.

## 5. Backlog, in execution order, with the coding-subagent model tier

Tiers: **opus** = spine-touching or rule-interacting; **sonnet** = mechanical against a
precise spec. Every story: own worktree branch commit, `make lint && make test` green,
`make openapi` when a schema moves, e2e target when named, hand-back cites any ratification
used. No story pins shipped template content in a test (fixture copies only).

### Epic A — Unpinned callees (needs R-1)
| Story | Scope | Gate | Tier |
| --- | --- | --- | --- |
| A-1 | `TemplateRef.version: int \| None`; validator accepts omitted call version, resolves latest for binding/cycle/depth; `_calls_of`, null-aware `callers_of`; graph `NodeCall.resolved_version`; `GET /templates/{n}/{v}` `calls[].resolved_version`. | lint, test, openapi | opus |
| A-2 | `resolve_tree` resolves once per name per plan, re-guards cycle/depth as `PlanError`; `run.template_tree` JSONB + migration 0022; `RunOut`/detail carry it. | lint, test, e2e-api | opus |
| A-3 | Reverse check in `save_version`: re-validate unpinned callers against the candidate; 422 `errors[]` with `template = caller`. | lint, test | sonnet |
| A-4 | Shipped files drop every call `version:`; cited test revisions; `DEPLOY.md` note that the 2026-09-29 upgrade defect is closed. | lint, test, e2e-api | sonnet |

### Epic B — Provenance, examples, restore (A-1 first; A-4 before any deploy)
| Story | Scope | Gate | Tier |
| --- | --- | --- | --- |
| B-1 | Migration 0021 (`origin`, `restored_from`); seeding rule (same hash → nothing; no operator version → insert shipped; else withheld + info log); `TemplateSummaryOut.latest_origin/operator_owned`. | lint, test, openapi | opus |
| B-2 | `ShippedTemplateSource` port + loader adapter; `GET /examples`, `GET /examples/{name}` (`stored_as`, `withheld`); Copy = existing save with server-side `name:` rewrite (new name) or next version (same name). | lint, test, e2e-api | sonnet |
| B-3 | `POST /templates/{name}/{version}/restore`: version line rewritten, full validate, `origin=operator`, `restored_from`. | lint, test, e2e-api | sonnet |
| B-4 | web-client: library page (My workflows + Examples, New template, Copy), versions column (origin, Restore with pre-validation), history diff, save impact preview, Run detail "planned from" line. | lint, test, e2e-ui | sonnet (split in 2–3 PR-sized stories if >300-line components) |

### Epic C — Harness and model per agent (R-3 before C-2)
| Story | Scope | Gate | Tier |
| --- | --- | --- | --- |
| C-1 | DSL input types `harness` and `model` (validator has no harness port; defaults checked at create). | lint, test | sonnet |
| C-2 | `create_run` + pre-flight probe every distinct planned `(harness, model)` pair; refusal names the pair and the row. | lint, test, e2e-api | opus |
| C-3 | New workflow form renders inputs by type: harness select (enabled + readiness), model select from the per-harness probe with labelled free-text fallback; WILL PLAN FROM line; per-pair pre-flight lines. | lint, test, e2e-ui | sonnet |
| C-4 | Shipped files declare `type: harness`/`type: model`; promote `story-staged` (Operator decision) with a caller passing three models. | lint, test | sonnet |
| C-5 (optional) | `retry` signal accepts `{harness, model}` applied to the next attempt only; recorded on the attempt. | lint, test, e2e-api | opus |

### Epic D — Capabilities catalogue and editor helpers (independent, can start day 1)
| Story | Scope | Gate | Tier |
| --- | --- | --- | --- |
| D-1 | `GET /capabilities` use case + schema + router; `_DISPATCH_KEYS`/`_INTENT_KEYS` public in `table.py`; skills from `SkillCatalog`; `?probe=true` opt-in. | lint, test, e2e-api | sonnet |
| D-2 | Editor helper panel (STEPS, INPUTS, HARNESSES & MODELS, SKILLS, EXPRESSIONS) inserting snippets at the cursor; no YAML parsing in the browser. | lint, test, e2e-ui | sonnet |

Dependency graph: R-1 → A-1 → A-2 → A-3 → A-4 → B-1 → {B-2, B-3} → B-4; D-1 → D-2 in
parallel from the start; C-1 → (R-3) C-2 → C-3 → C-4 (→ C-5). Production readiness = A + B
+ C-1..C-3 + D. Critical path ≈ 11 sequential stories; D and C-1 run beside A.

## 6. How the build will be orchestrated

1. One feature worktree off `main` (`feat/editable-workflows`), one branch per epic stacked
   in the order above so each epic can be reviewed and merged on its own.
2. One coding subagent per story with the tier in §5, given: the story row, the relevant
   ARCH section, the mockup for UI stories, the ratification text to cite, and the gate
   commands. The subagent hands back the diff summary, gate output, and any test it revised
   with its citation.
3. After each story: I run the gates myself, review the diff against the spine, commit
   (`story {id}: {title}`), and only then dispatch the next one.
4. Checkpoints for the Operator: after R-1..R-6 ratification (before A-1); after Epic A
   (the spine-touching part); after B-4 and C-3 (the two UI deliveries, checked against
   the mockups); before merging to `main`.
5. Deploy note: the first upgraded instance runs 0021/0022 on boot; names never edited
   behave as before; edited names stop receiving shipped versions and show them under
   Examples.

## 7. UX

`UX-SPEC.md` (per screen: states, controls and their endpoints, exact copy, keyboard,
accessibility) and seven static mockups under `mockups/`, all on the instrument-dark
tokens and consistent on one data set (`initiative-hub@3 → initiative-hub-epic@5 →
initiative-hub-story@4`):

| File | Screen |
| --- | --- |
| 01-templates-library | `/templates`: MY WORKFLOWS + EXAMPLES, New template, empty and unavailable states |
| 02-template-editor | editor with VERSIONS (origin, restored-from, Restore), HELPERS panel from `/capabilities`, validation readout gating Save; valid and refused states |
| 03-save-impact-preview | confirm listing unpinned callers (direct and through a hop) and the post-save readout |
| 04-version-history-restore | history, unified diff, Restore that pre-validates (enabled / refused) |
| 05-examples-copy | read-only example, diff vs my latest, Copy as next version or new name |
| 06-new-workflow-typed-inputs | typed harness/model controls, WILL PLAN FROM, per-pair pre-flight, refused state |
| 07-run-detail-planned-from | PLANNED FROM tree line, frozen note, greyed v2 retarget note |

UX decisions for the Operator to look at first (defaults in `UX-SPEC.md`): HELPERS sits under
VERSIONS in the left column rather than a fourth column; the library uses its own row grid
(a stated DESIGN.md exception); the impact preview labels transitive callers with the hop;
Copy offers "as version n of the same name" first; `legacy` origin is shown verbatim; a
free-text model input keeps START enabled with the label "cannot be checked before the run
starts". Acceptance criteria that lost their screen under D-1 (PM's D2/D4 cascade) are
flagged in the spec preamble rather than designed around.
