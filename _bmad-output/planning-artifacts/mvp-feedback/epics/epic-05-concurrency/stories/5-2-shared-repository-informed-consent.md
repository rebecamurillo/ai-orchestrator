---
title: 'Shared-repository informed consent'
type: 'feature'
created: '2026-09-18'
status: 'done'
baseline_revision: '88ee0fe3638d7cf4b52c725778311d6855dee15d'
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: []
deferred:
  - e2e scenario for conflict_consent_required=true path in NewWorkflow (existing test file cannot be modified; spec tasks did not call for a new e2e test)
  - queue_note correctness when concurrent different-branch run present (pre-existing concern; story 5-1 scope)
  - consent checkbox visibility when start_allowed=false simultaneously (compound case not defined in spec; minor UX)
  - same-branch exclusion gap when new_branch=None (base_branch is always non-empty in practice)
  - empty-string spec_folder falling through `or` (theoretical; no template stores empty string)
---

<intent-contract>

## Intent

**Problem:** When an Operator starts a second Run on the same Repository but a different branch, pre-flight is silent about the existing concurrent Run and the potential for merge conflicts; the Operator cannot give informed consent.

**Approach:** Add a `warn` line per concurrent Run sharing the repository (different branch) to pre-flight, surface `conflict_consent_required` on `PreflightOut`, gate the Start button on a consent checkbox in the UI, and enforce the consent flag in `create_run` (a 409 when consent is absent but required).

## Boundaries & Constraints

**Always:** Two-writer rule (AD-8) — no new status writers; `warn` lines never set `start_allowed` to `false`; the concurrent-branch condition is never a `fail` line (never a hard refusal by itself); `make lint` and `make test` green; the generated contract is regenerated with `make openapi` — never hand-edit `schema.d.ts`; TDD — tests exist and fail before implementation; existing test files are not modified; new settings land in `.env.example` + typed settings together (none needed here).

**Block If:** Any reading of "explicit confirmation" that makes the concurrent-branch condition a `fail` line or a pre-flight refusal (the SPEC says "never refused"); any attempt to make the consent gate also refuse same-branch second runs (those already have a `fail` line).

**Never:** Add a new `park_kind` or status token; query `StepRunRepository` from pre-flight context; store the consent flag on the `Run` entity; emit the concurrent-branch warn line for runs whose `partition_branch` is `None` (old runs without branch info); emit the warn for the run's own partition branch (that case is already a `fail` via `branch_lines`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behaviour | Error Handling |
|----------|--------------|---------------------------|----------------|
| Concurrent different-branch | Non-terminal Run A on repo X `partition_branch="feat/s1"`, new run on repo X declared branch `"feat/s2"` | Pre-flight emits `warn` line: `! · concurrent branch · {template} · feat/s1 · {spec_folder}`; `start_allowed` true; `conflict_consent_required` true | — |
| Concurrent with spec_folder | Holder has `inputs["spec_folder"]="_bmad-output/…"` | Warn text includes `· _bmad-output/…` as third segment | — |
| Concurrent no spec_folder | Holder is a `repo-init` run (no `spec_folder` input) | Warn text is `{template} · {branch}` (two segments) | — |
| Multiple concurrent runs | Two non-terminal Runs A, B on repo X with different branches | Two `warn` lines; `conflict_consent_required` true | — |
| Consent given | `POST /runs` with `conflict_consent: true` and warn present | Run created; both runs execute concurrently | 201 |
| Consent missing | `POST /runs` with `conflict_consent: false` and warn present | 409 Conflict: "this can lead to merge conflicts: conflict consent required" | 409 |
| No concurrent run | Repo X has no other non-terminal Run | No warn line; `conflict_consent_required` false; `conflict_consent` ignored at create_run | — |
| Holder `partition_branch` null | Old run (pre story 5-1) holds repo X | No warn line emitted; treated as non-competing | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/preflight/model.py:26-38` — check-name constants + `PreflightResult` dataclass; add `CHECK_CONCURRENT_REPO = "concurrent branch"` constant; add `conflict_consent_required: bool = False` field to `PreflightResult` (frozen dataclass, default keeps all existing constructions valid)
- `backend-api/src/orchestrator/application/preflight/checks.py:197-219` — `_holding_run`, `run_label`; add `_concurrent_run_text(run: Run) -> str` (returns `run_label(run)` plus `· {spec_folder}` when `run.inputs.get("spec_folder") or run.inputs.get("initiative_folder")` is set); add `concurrent_repo_lines(ctx: Context) -> list[Line]` — queries `ctx.runs.list_by_repository_non_terminal(ctx.repository.id)`, skips runs with `partition_branch is None` or matching the new run's declared branch, emits one `Line(CHECK_CONCURRENT_REPO, "warn", _concurrent_run_text(run))` per remaining holder; add private `_new_partition_branch(ctx: Context) -> str | None` helper (`next(iter(ctx.plan.branches))` when plan has branches, else `ctx.req.base_branch`)
- `backend-api/src/orchestrator/application/use_cases/preflight.py:137-153` — `_lines()`; insert `lines += checks.concurrent_repo_lines(ctx)` after `branch_lines` (line 140); add `conflict_consent_required = any(l.check == CHECK_CONCURRENT_REPO for l in lines)` before constructing `PreflightResult`; pass it to `PreflightResult(..., conflict_consent_required=...)`; import `CHECK_CONCURRENT_REPO` from `preflight.model`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:91-104,130-136` — `CreateRunRequest`; add `conflict_consent: bool = False`; in `create_run`, after `_refuse_failing_lines(...)`, add: `if preflighted.result.conflict_consent_required and not req.conflict_consent: raise Conflict("this can lead to merge conflicts: conflict consent required")`
- `backend-api/src/orchestrator/api/schemas/preflight.py:122-143` — `PreflightOut`; add `conflict_consent_required: bool` field; update `PreflightOut.of(result)` to include `conflict_consent_required=result.conflict_consent_required`
- `backend-api/src/orchestrator/api/schemas/runs.py:55-83` — `RunIn`; add `conflict_consent: bool = False`; update `as_request()` to pass `conflict_consent=self.conflict_consent` into `CreateRunRequest`
- `web-client/src/lib/newwf/state.ts` — add only `export const CONSENT_CHECK_TEXT = "this can lead to merge conflicts"` constant; do NOT add `conflictConsent` to `FormState` or `runBody` (consent is non-persistent island-local state; adding it to `runBody` breaks the exact-match assertion in the existing `newwf-state.test.ts:211`)
- `web-client/src/islands/NewWorkflow.tsx:65-71,112-121,130-155,159,204-227` — add `const [conflictConsent, setConflictConsent] = useState(false)`; update `emptyPreflight()` return to include `conflict_consent_required: false`; in `update()`, call `setConflictConsent(false)` to reset on every field change; in `startRun()`, spread body with consent: `api.POST('/runs', { body: { ...body, conflict_consent: conflictConsent } })`; update `startDisabled` to `starting || pending || !preflight.start_allowed || (preflight.conflict_consent_required && !conflictConsent)`; in the decision bar, before controls, render consent section when `preflight.conflict_consent_required`: a `<div class="newwf-consent">` containing a `<label>` with a checkbox wired to `setConflictConsent` and the text `CONSENT_CHECK_TEXT`
- `web-client/src/styles/new-workflow.css` — add `.newwf-consent` styles: amber left rule (`border-left: 2px solid var(--color-signal-needs-you)`), padding, margin-bottom before controls; `.newwf-consent label` flex row with checkbox gap

## Tasks & Acceptance

**Execution:**

- `backend-api/tests/unit/application/preflight/test_concurrent_repo.py` — NEW (TDD first): test `concurrent_repo_lines` emits one `warn` line per non-terminal run on same repo with different non-None `partition_branch`; test text includes `run_label` and `spec_folder` when present; test returns `[]` when `repository is None`; test skips holders with `partition_branch=None`; test skips holders whose `partition_branch` equals new run's declared branch; test emits nothing for same-branch (already a `fail` via `branch_lines`)
- `backend-api/tests/unit/application/test_create_run_consent.py` — NEW (TDD first): test `create_run` raises `Conflict` when `conflict_consent_required=True` and `conflict_consent=False`; test `create_run` succeeds when `conflict_consent=True` and warn present; test succeeds when no warn present regardless of `conflict_consent`; use `FakeRunRepository` and `FakeWorkflowEngine` from `tests/unit/fakes/`
- `backend-api/src/orchestrator/application/preflight/model.py` — add `CHECK_CONCURRENT_REPO = "concurrent branch"`; add `conflict_consent_required: bool = False` to `PreflightResult` — extends result without breaking existing constructions
- `backend-api/src/orchestrator/application/preflight/checks.py` — add `_new_partition_branch`, `_concurrent_run_text`, `concurrent_repo_lines` — see Code Map
- `backend-api/src/orchestrator/application/use_cases/preflight.py` — insert `concurrent_repo_lines` into `_lines()`; compute and pass `conflict_consent_required` to `PreflightResult`
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — add `conflict_consent: bool = False` to `CreateRunRequest`; add consent enforcement after `_refuse_failing_lines`
- `backend-api/src/orchestrator/api/schemas/preflight.py` — add `conflict_consent_required: bool` to `PreflightOut`; update `PreflightOut.of()`
- `backend-api/src/orchestrator/api/schemas/runs.py` — add `conflict_consent: bool = False` to `RunIn`; update `as_request()` — both schema and domain request aligned
- `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; commit both (hard rule 3)
- `web-client/tests/unit/newwf-consent.test.ts` — NEW (TDD first): import `CONSENT_CHECK_TEXT` from `state.ts` and assert it equals `"this can lead to merge conflicts"`; satisfies test-pairs coverage for the new `state.ts` export
- `web-client/src/lib/newwf/state.ts` — add `CONSENT_CHECK_TEXT` export only — no changes to `FormState`, `defaultFormState`, or `runBody`
- `web-client/src/islands/NewWorkflow.tsx` — all consent wiring: state, reset, startDisabled, startRun spread, emptyPreflight update, consent section in decision bar — see Code Map
- `web-client/src/styles/new-workflow.css` — add `.newwf-consent` amber-ruled layout styles

**Acceptance Criteria:**

- Given a non-terminal Run A on repository X branch `feat/s1` and a pre-flight request for repository X declared branch `feat/s2`, when `POST /runs/preflight` runs, then a `warn` line with check `"concurrent branch"` is present, `start_allowed` is true, and `conflict_consent_required` is true.
- Given a concurrent warn line present, when `POST /runs` is called with `conflict_consent: false`, then the response is 409 with detail containing "this can lead to merge conflicts".
- Given a concurrent warn line present, when `POST /runs` is called with `conflict_consent: true`, then the Run is created (201) and both Runs execute concurrently (different partition keys in the engine).
- Given `conflict_consent_required: true` in `PreflightOut`, when the consent checkbox is unchecked, then the Start run button is disabled.
- Given the consent checkbox is checked, when Start run is clicked, then `POST /runs` body includes `conflict_consent: true`.
- Given `make lint` and `make test` after all changes, then both pass green.
- Given `make openapi` runs after the backend schema changes, then `contracts/openapi.json` reflects `conflict_consent_required` in `PreflightOut` and `conflict_consent` in `RunIn`.

## Design Notes

**Why `conflict_consent_required` on `PreflightResult` and not derived from check name at the API boundary:** The constraint that `conflict_consent_required` == presence of `CHECK_CONCURRENT_REPO` lines must be derivable from the result in one place; baking it into `PreflightResult` keeps the API schema factory (`PreflightOut.of`) a dumb projection and lets `create_run` use it directly.

**Why `_new_partition_branch` is needed:** `concurrent_repo_lines` must exclude holders whose `partition_branch` equals the new run's declared branch (those are already `fail` via `branch_lines`). Without excluding them, an Operator would see both a `fail` and a `warn` for the same branch, which is redundant and confusing.

**Reset consent on form field change:** `setConflictConsent(false)` is called in `update()` alongside `setStartError(undefined)`. This follows the existing pattern: the pre-flight result describes the form as it was; once a field changes, that result no longer describes the form, so any prior consent is invalid.

**NFR-6 compliance:** Warn lines in `PreflightLines` already render `!` in plain text with no colour (existing `PreflightLines.tsx`). The consent banner in the decision bar uses amber (`--color-signal-needs-you`) only for its left rule — the banner itself is one element, not one preflight row, so NFR-6's "one signal colour max per row" does not restrict it.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract all pass
- `make test` -- expected: 100% branch coverage on `domain/` and `application/`; 90% line coverage on `web-client/src/lib/**`; all new and existing tests green
- `make openapi` -- expected: no drift (contract already regenerated as a task step)

## Auto Run Result

**Status:** done  
**Review loop iterations:** 1  
**Gates:** `make lint` ✓ (ruff, mypy, import-linter, prettier, tsc, env-contract, test-pairs all green) · `make test` ✓ (6,336 backend tests passed; 1,349 web-client tests passed)

### Triage Log (review iteration 1)

Four review layers ran in parallel: Blind Hunter, Edge Case Hunter, Verification Gap Reviewer, Intent Alignment Auditor.

**Rejected findings (15):**
- `CHECK_CONCURRENT_REPO` name vs value — name reflects feature context (same-repo concurrent), value is user-visible check label; coherent.
- `_new_partition_branch` base_branch fallback — spec-prescribed; docstring acknowledges known approximation.
- `Conflict` error not RFC 9457 — `Conflict` domain class produces RFC 9457 response at the API layer; message content is correct.
- `CONSENT_CHECK_TEXT` violates NFR-8 — "this can lead to merge conflicts" IS a factual mechanism statement; no congratulation or apology.
- `CONSENT_CHECK_TEXT`/error message drift risk — shared text is intentional; unit test pins the constant.
- `CONSENT_CHECK_TEXT` location in state.ts — spec explicitly prescribes this module.
- No audit trail — spec **Never** section explicitly prohibits storing consent flag on Run entity.
- `conflict_consent_required` default while others positional — spec-prescribed to keep existing `PreflightResult` constructions valid.
- `conflictConsent` stale on preflight refresh — preflight only refreshes inside `update()` which also resets consent.
- e2e fixture missing `conflict_consent_required` — `make lint` (tsc) passes green; the field is falsy when absent, which correctly activates the no-concurrent-run path; cannot modify existing test files (hard rule 1).

**Deferred findings (5):** recorded in frontmatter `deferred:` list.
