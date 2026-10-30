---
title: 'Model selector for every model-named workflow input'
type: 'feature'
created: '2026-10-30'
status: 'done'
baseline_commit: '94ee2b2dd394074dee51dc41e96770a4dc889e6a'
route: 'dispatch'
review_loop_iteration: 1
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The New Workflow form offers a select of probed models only on the dedicated MODEL field. A Template's other model inputs (`model_planning`, `model_x`, `plan_model`, ...) are always free text, so an Operator can type a name the harness does not serve and only find out when the Run fails at that step's first model call.

**Approach:** Every Template input whose name starts or ends with `model` renders the same control as MODEL: a select over the selected harness's probed models when that list is non-empty, a free-text input when it is empty or could not be retrieved.

## Boundaries & Constraints

**Always:** The list comes from the existing `GET /harnesses/{name}/probe` for the selected harness, the same source as MODEL. A retrieval error (non-2xx or network throw) means free text, including when an earlier probe of that harness succeeded. A select always offers a blank `—` option. A value the select cannot show is cleared, never submitted invisibly. An input qualifies when its `type` is `string` and its name starts or ends with `model` (Operator decision 2026-10-30: `model*` and `*model`, so `model1`, `model_1`, `plan_model` and `review_model` all qualify, and so does any other name with that shape, such as `modeling_notes` or `data_model`).

**Never:** No backend or contract change. No template edits. No per-input model lists. No test pins shipped template content (hard rule 6); tests use fixture catalogs. Existing frozen tests stay unmodified. `withHarness` and `modelsFor` are left as they are. No probe on page load: a form reloaded from its URL shows free text with values kept until a harness is clicked, exactly as MODEL behaves today.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| List available | Template declares `model_x`; probe ok, models non-empty | `newwf-input-model_x` is a select over those models | N/A |
| Empty list | Probe ok, `models: []` | Free-text input; typed value kept | N/A |
| Retrieval error | Probe 5xx or network throw, earlier probe of that harness ok | Stale list dropped, free-text input | Harness stays selected; no unhandled rejection |
| Probe not ok | `ok: false` | Harness cleared (existing), model inputs back to declared defaults, free text | Existing failing-reason readout |
| No harness | Template has no `harness` input, or none selected | Free-text input | N/A |
| Harness changed | `model_x` holds a value | Reset to declared default, then cleared if the new list excludes it | N/A |
| Default not in list | `model_x` default `foo`, list excludes `foo` | Select's blank option reads `— (template default: foo)`; value `''`. The backend binds `foo` for a blank value, so the Run uses it (Operator decision 2026-10-30: label it, Start stays allowed) | Required input with no default: pre-flight refuses as for any blank required input |
| Template switched with list loaded | New Template's `model_y` default not in list | Cleared, same rule | N/A |
| Not a model input | `model_count: number`; `model_name_notes_v2: path`; `remodeled: string` | Plain text input | N/A |

</frozen-after-approval>

## Code Map

- `web-client/src/lib/newwf/catalog.ts` -- `deriveFields` builds `TemplateInputField`; `FORM_OWNED_NAMES` keeps `model` out of the fields. Add the name rule and a `modelChoice` flag here; the catalog is plain data crossing the island boundary.
- `web-client/src/lib/newwf/state.ts` -- pure form transitions. Add the reset and the reconcile here. `withTemplate` opens new fields at defaults and cannot see the list, hence the reconcile in the island.
- `web-client/src/components/NewWorkflowFields.tsx` -- lines 165-189 hold the select/input pair; lines 152-160 hold the template input map. Reuse the shape, keep `data-testid="newwf-model"` and `newwf-input-{key}`.
- `web-client/src/islands/NewWorkflow.tsx` -- `runProbe` (132-152) has no catch and keeps stale results on error; `onSelect` (290-293) resets `model`; `models` prop at 281.
- `web-client/tests/unit/newwf-catalog-fixture.ts` -- `decl` helper and fixture pattern to copy; do not edit it.
- `web-client/tests/e2e/new-workflow-probe.spec.ts` -- `probeOkBody` and route-stub pattern to copy into a new spec.
- `backend-api/.../create_run.py:175` -- validates only `req.model` against the probe. Left alone: the select already limits the choice, and free text is what the Operator asked for when no list exists.

## Tasks & Acceptance

**Execution:**
- [x] `web-client/tests/unit/newwf-model-inputs.test.ts` -- new; failing tests first (hard rule 6) for name matching, `resetModelInputs`, `reconcileModelInputs`, and select vs input rendering, on a fixture catalog -- covers the matrix.
- [x] `web-client/tests/unit/model-field.test.ts` -- new; select/input shape, blank option, placeholder -- satisfies the test-pair gate.
- [x] `web-client/tests/e2e/new-workflow-model-inputs.spec.ts` -- new; stubbed probe: ok list, empty list, 500 after a prior ok, harness switch -- interaction needs a browser.
- [x] `web-client/src/lib/newwf/catalog.ts` -- add `isModelInput(input)` (`type === 'string'` and `name.startsWith('model') || name.endsWith('model')`) and `TemplateInputField.modelChoice` -- single statement of the rule.
- [x] `web-client/src/lib/newwf/state.ts` -- add `resetModelInputs(state, catalog)` (each model field back to `initial`) and `reconcileModelInputs(state, models, catalog)` (non-empty list: clear values not in it; empty list: unchanged) -- pure and unit-testable.
- [x] `web-client/src/components/ModelField.tsx` -- new stateless select/input pair taking `testId`, `value`, `models`, `placeholder`, `onChange` -- one control, two call sites.
- [x] `web-client/src/components/NewWorkflowFields.tsx` -- render `ModelField` for MODEL and for `field.modelChoice` fields; update the header comment -- same control everywhere.
- [x] `web-client/src/islands/NewWorkflow.tsx` -- `onSelect` applies `resetModelInputs`; `runProbe` applies `reconcileModelInputs` on ok and `resetModelInputs` on not-ok, and on error or throw deletes `probeResults[name]`; form `onChange` reconciles against the current list -- covers template switch and retrieval error.

**Acceptance Criteria:**
- Given a Template declaring `model_x` and a harness whose probe returns models, when the harness is selected, then `model_x` and MODEL both offer exactly those models, and the chosen `model_x` reaches `POST /runs` in `inputs.model_x`.
- Given the form URL after choosing a value, when `formStateToQuery` runs, then `in_model_x` carries it, as for any other input.
- Given a Template with no `model*` or `*model` inputs beyond `model`, when the form renders, then its markup is unchanged.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Evidence | Route |
|---------|---------|----------|-------|
| Clearing an unserved literal default still runs that default | high | Confirmed: `with_defaults` (`templates/defaults.py`) rebinds a literal default when the input is absent or `""`, so `—` displays while the default is used | intent_gap |
| `—` on a Template model input has no stated meaning, no placeholder | medium | Same root: blank means the declared default if any, otherwise the harness default | intent_gap (grouped) |
| Probe-driven clears skip URL, pending and pre-flight | medium | Confirmed: `runProbe` calls `setState` directly, so a probe slower than the 400 ms debounce leaves `start_allowed` and the URL describing the old value | patch |
| Cached list blanks a default before the re-probe returns | medium | Confirmed: `update` reconciles against the cached `probeResults` on harness select | patch (move reconcile out of `update` to the form's `onChange`, as the spec's task says) |
| E2e "cleared" assertions read the select's DOM value, not the state | medium | Gap filed pre-verified: React falls back to the blank option whatever the state holds | patch |
| Harness-switch reset not observed by its test | medium | Gap filed pre-verified | patch |
| `ok: false` reset untested at the island | medium | Gap filed pre-verified | patch |
| Template switch with a list loaded untested at the island | medium | Gap filed pre-verified | patch |
| Network throw path untested | medium | Gap filed pre-verified; the e2e only stubs a 500 | patch |
| "Empty list" e2e does not wait for the probe | medium | Confirmed: `newwf-note` is non-empty from load, so the wait passes before the probe answers | patch |
| `NewWorkflowFields` header comment names `modelsFor` and `local` only | low | Confirmed: the island passes `probeResults`; a direct correction | patch |
| No probe on load; a checked radio cannot re-probe, so a reload gets the list only by switching away and back, which resets values | medium | Confirmed: `HarnessList.tsx:80` uses the radio's `onChange`. Same for MODEL before this change; the approved spec excludes a load probe | defer |
| Failed list retrieval gives the Operator no explanation | medium | Confirmed; a failed probe response was already silent before this change | defer |
| `NewWorkflow.tsx` over the 300-line component limit | low | Already 365 lines at baseline; 384 now | defer |
| Reload restores a cleared default | false | The default is what the backend binds anyway, so the restored display is accurate | rejected |
| Save during an in-flight probe keeps a value | low | Rare, and Save is documented as independent of harness state | rejected |
| Same-named input carries to a no-harness Template | low | The value stays visible and editable in the text input | rejected |
| Expression default restored literally by reset | low | The form already opens with it literally at baseline; no shipped root `model*` input has one | rejected |
| Clearing a value gives no notice | low | The fix adds new surface; rare outside defaults, which the intent_gap covers | rejected |
| `withTemplate` keeps `''` over a new Template's served default | low | Backend binds that default anyway, so the Run gets the right model | rejected |

## Verification

**Commands:**
- `make lint` -- expected: pass, including the test-pair check
- `make test` -- expected: pass with coverage thresholds held
- `make coverage` -- expected: changed lines at least 90 %
- `make e2e-ui` -- expected: pass; binds 4321, and if held, ask the Operator before any `make down` (hard rule 9)
