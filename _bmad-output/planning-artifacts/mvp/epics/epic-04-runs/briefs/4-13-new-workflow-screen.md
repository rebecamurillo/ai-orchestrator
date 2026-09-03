---
story: "4-13"
epic: 4
title: New workflow screen with pre-flight and What will run
requirements: [FR-8, FR-33 (harness list), NFR-6, NFR-8, UX-DR8, UX-DR17, UX-DR18, AR-25]
binds: [AD-1, AD-3, AD-7]
---

# Story 4.13 — New workflow screen with pre-flight and *What will run*

As the Operator,
I want one page where I bind a Template's inputs, watch pre-flight re-run on every change, read the whole plan, and start,
So that starting a Run is a decision made with everything in view (UJ-2).

## Scope

**In:** `src/pages/workflows/new.astro`, the `NewWorkflow` island, pre-flight calls through the proxy, the plan table, the harness list, *Start run* with the queue note, pre-fill from query parameters (`?template=&project=&repository=&branch=` for the `start a new run` links), Vitest and Playwright.
**Out:** readiness re-run action wiring beyond the link (Epic 5 provides the endpoint; here the link points to it and shows `not available yet` if 404).

## Binding rules (inlined)

- **Form (UX-DR8), 190px labels, in order:** template (`initiative` latest pre-selected; `epic`, `repo-init`; never `story`) → project → repository (of that project; a `failed` clone check shows `clone check failed · new runs blocked` beside it) → base branch (default: repository default branch) → template inputs: `initiative`: *initiative folder*; `epic`: *working branch*, *spec folder*; `repo-init`: none → harness list (hidden for `repo-init`): one line per harness `{name} · enabled | disabled: {failing_check or "no readiness run"} · last readiness {time or —} · re-run readiness` (link to `POST /harnesses/{name}/readiness`), a disabled harness is not selectable → model (text, placeholder `harness default`) → budget (USD, required) → *re-review done stories* (switch, off) → manual estimate (hours, optional). A page, not a modal; the URL carries the form state as query parameters so a reload restores it.
- **Pre-flight (right column).** Calls `POST /runs/preflight` on every field change (debounced 400 ms) and on load; renders `lines[]` as `{status word} · {check} · {text}` with words `ok / ! / x / —` in the first column (`warn` → `!`, `fail` → `x`, `skip` → `—`), never icons; a `fail` line adds its `fix` in secondary text; a `x` line disables *Start run*. Only the `x` word is red; `!` is plain.
- **What will run.** Dense table `path · kind · gate` from `rows[]`, the first row `plan · plan.check · deterministic`, skipped rows showing `skipped · {reason}` in the gate column's row text (never green); a `plan_error` replaces the table with `plan error · {template}@{version} · line {line} · {reason}` in red.
- **Decision bar.** *Start run* (primary, disabled while any `x`), *Cancel* (link to `/`), and the note from `queue_note` verbatim (`starts immediately if the repository is free`, `queues behind {label}`). On click: `POST /runs`; 201 → navigate to `/workflows/{id}`; 409/422 → the problem `detail` above the bar, form kept.
- **Island rules:** `client:load`; props `{templates, projects, harnesses, initial}` (≤ 5); calls `client.ts` only; serialisable props.
- **Test-ids:** `newwf-form`, `newwf-template`, `newwf-project`, `newwf-repository`, `newwf-base`, `newwf-input-<name>`, `newwf-harness-<name>`, `newwf-budget`, `newwf-estimate`, `newwf-rereview`, `newwf-preflight`, `newwf-preflight-<check>`, `newwf-plan`, `newwf-plan-row-<seq>`, `newwf-start`, `newwf-note`.

## Acceptance criteria

**Given** `/workflows/new` with stubbed templates, projects, and harnesses
**When** opened
**Then** `initiative` is pre-selected, the initiative-folder input is shown, and switching to `epic` swaps it for working branch and spec folder; `repo-init` hides the harness list.

**Given** the harness list with `claude` disabled
**When** rendered
**Then** its line reads `claude · disabled: no readiness run · last readiness — · re-run readiness` and it cannot be selected.

**Given** a pre-flight response with one `fail` line
**When** rendered
**Then** the line shows `x`, its text and fix, *Start run* is disabled, and only the `x` is coloured.

**Given** a pre-flight response with rows
**When** rendered
**Then** the plan table lists every row with `plan` first and `skipped · already done` rows as plain words.

**Given** every line `ok` or `warn`
**When** *Start run* is clicked and the stub answers 201
**Then** the browser navigates to `/workflows/{id}`; with a 409 the detail is shown and the form is kept.

**Given** a reload of the page with a filled form
**When** the page loads
**Then** the form is restored from the query string and pre-flight re-runs.

## Implementation notes

- `src/islands/NewWorkflow.tsx`; helpers `src/lib/newwf/{state.ts, query.ts}` unit-tested; `src/components/PreflightLines.tsx` and `PlanTable.tsx` inside the island (small components).
- Data loaded server-side in the page: `GET /templates`, `GET /projects`, `GET /harnesses`.
- Playwright `tests/e2e/new-workflow.spec.ts`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2.1 New workflow, §Operator workflow step 3, §Voice. PRD FR-8, FR-33. Spine AD-7 (same rows as persisted).
