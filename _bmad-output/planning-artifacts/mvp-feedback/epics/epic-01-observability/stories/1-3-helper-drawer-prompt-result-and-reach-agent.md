---
title: "Helper drawer — prompt-result and reach-agent"
type: 'feature'
created: '2026-09-16'
status: 'in-progress'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: 'b2a3f581ba98718e3b567dd0f86dc7d1b62d392b'
context: []
warnings: []
deferred:
  - "I/O matrix rows 4–7 (close, same-button toggle, tab switch, shell-step button exclusion) require click events or async hooks; deferred to tests/e2e/step-detail.spec.ts per story 1-2 pattern"
---

<intent-contract>

## Intent

**Problem:** On the step-run detail page, the dispatch prompt, result, and FR-21 terminal resume instructions for each past attempt are either scattered across the page (blocking the log) or absent entirely, making it hard to inspect agent output while watching a live tail.

**Approach:** Add a right-side helper drawer (side panel, never modal) to the `StepDetail` island with two swappable contents — "prompt · result" and "reach agent" — opened from per-attempt buttons. Extend `AttemptDetailOut` with `resume_command` and `session_lifetime_ends_at` so the backend computes the resumable-session data and the frontend renders it verbatim.

## Boundaries & Constraints

**Always:**
- TDD (AD-18): tests for every new module exist and fail before implementation; unit tests use shared fakes in `tests/unit/fakes/`; no new doubles for a port that already has one.
- The drawer is a side panel, never a modal; the page behind it stays live and the log keeps following under it (FR-34).
- Opening or closing the drawer changes nothing else on the page: `selectedN`, poll interval, and `LogViewer` follow state are all unaffected.
- Non-agent attempts (`attempt.command !== null`) show no drawer controls.
- "reach agent" button is absent when `attempt.resume_command` is null (harness not resumable or no session).
- `schema.d.ts` is never hand-edited; `make openapi` + `pnpm gen:api` regenerate it (AD-3).
- The resume command string is built server-side by `terminal.resume_command()` and rendered as text — never rebuilt or interpolated in the browser (AD-5).
- Reuse `TERMINAL_SESSION_LINE` and `sessionLifetimeLine()` from `web-client/src/lib/run/terminal.ts`; do not duplicate those constants.
- No status writes anywhere (AD-8); this epic reads state only.

**Block If:** Any pre-existing test fails after these changes — classify and report per AGENTS.md rule 1 before continuing.

**Never:** Modal for the drawer; signal actions (Answer, Continue, Retry, Skip, Release) on this page; `dangerouslySetInnerHTML` with `resume_command`; hand-edit `schema.d.ts`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| "prompt · result" button clicked on agent attempt | `attempt.command === null`; `dispatch_prompt` may be non-null | Drawer (`data-testid="step-drawer"`) opens right side; shows dispatch_prompt block + copy; retry_prompt block + copy if non-null; result block + copy if non-null | No error |
| "reach agent" button clicked, claude attempt | `resume_command` non-null | Drawer shows command block + copy, session lifetime line (if `session_lifetime_ends_at` non-null), TERMINAL_SESSION_LINE, past-session note | No error |
| "reach agent" button absent | `resume_command` null | No `data-testid="step-reach-{n}"` button rendered on that row | No error |
| Close drawer | close button clicked | Drawer unmounts; `selectedN`, log follow, polling unchanged | No error |
| Same button clicked again | drawer open, identical attempt+content | Drawer closes | No error |
| Switch tab inside drawer | drawer open, other tab button clicked | Content changes; page behind unaffected | No error |
| Shell step attempt | `attempt.command !== null` | No "prompt · result" or "reach agent" buttons on that row | No error |
| `ports.terminal = None` | backend `RunViewPorts.terminal` absent | `AttemptDetailOut.resume_command = null`; `session_lifetime_ends_at = null` | No error |
| Attempt without session_id | `session_id = None` in DB | `resume_command = null` (terminal.resume_command returns None) | No error |

</intent-contract>

## Code Map

**Backend — modified:**
- `backend-api/src/orchestrator/api/schemas/step_detail.py:37` — `AttemptDetailOut`; add `resume_command: str | None` (None for non-agent, no terminal ports, or non-resumable harness) and `session_lifetime_ends_at: datetime | None`; both Optional with default `None` so existing `AttemptDetailOut(...)` constructions in old tests keep compiling
- `backend-api/src/orchestrator/api/routers/step_detail.py:14` — import `resume_command as _terminal_resume` and `Terminal` from `orchestrator.application.use_cases.terminal`; in `get_step_detail`, resolve `project = ports.projects.get(run.project_id)` once before the loop; per attempt: `t = _terminal_resume(ports.terminal, run, step, attempt, project_slug=project.slug if project else "") if ports.terminal else None`; populate `resume_command=t.command if t else None` and `session_lifetime_ends_at=t.session_lifetime_ends_at if t else None` in `AttemptDetailOut`

**Backend — new:**
- `backend-api/tests/unit/test_step_detail_resume.py` — WRITE FIRST; covers: `resume_command` key present and null when `terminal=None`; `session_lifetime_ends_at` key present and null when `terminal=None`; both null for shell step; both null when `attempt.session_id=None`; `resume_command` non-null when attempt has session_id and `terminal` is wired with `build_harnesses(settings, FakeProcessRunner())` using `claude` harness; uses same ASGI transport pattern as `test_step_detail_router.py`

**Frontend — new:**
- `web-client/src/components/run/HelperDrawer.tsx` — right-side drawer; exports `DrawerContent = 'prompt-result' | 'reach-agent'` (used by StepDetail to type its state) and `HelperDrawerAttempt` interface (subset: `dispatch_prompt`, `retry_prompt`, `result`, `resume_command`, `session_lifetime_ends_at`, all `string | null`); props `{ attempt: HelperDrawerAttempt; initialContent: DrawerContent; onClose: () => void }`; manages tab state via `useState(initialContent)`; two tab buttons; "prompt · result" tab: blocks for dispatch_prompt + copy, retry_prompt + copy (if non-null), result + copy (if non-null); "reach agent" tab: command block + copy, `sessionLifetimeLine(attempt.session_lifetime_ends_at)`, `TERMINAL_SESSION_LINE`, past-session note; close button; `data-testid="step-drawer"`; panel-scope CSS classes `step-drawer-*`
- `web-client/src/styles/step-detail.css` — CSS for existing `wf-step-detail-*` classes (story 1-2) and new `step-drawer-*` classes; imported in `StepDetail.tsx`
- `web-client/tests/unit/helper-drawer.test.ts` — WRITE FIRST; imports `HelperDrawer` from `../../src/components/run/HelperDrawer`; asserts `typeof HelperDrawer === 'function'`

**Frontend — modified:**
- `web-client/src/islands/StepDetail.tsx` — (1) add `resume_command: string | null` and `session_lifetime_ends_at: string | null` to `AttemptDetail` interface; (2) `import '../styles/step-detail.css'`, `import HelperDrawer, { type DrawerContent } from '../components/run/HelperDrawer'`; (3) add state `drawerState: { n: number; content: DrawerContent } | null` initialised `null`; (4) on each agent attempt row (`attempt.command === null`), add button `data-testid={\`step-prompt-${attempt.n}\`}` calling `toggleDrawer(attempt.n, 'prompt-result')`; and when `attempt.resume_command !== null`, add button `data-testid={\`step-reach-${attempt.n}\`}` calling `toggleDrawer(attempt.n, 'reach-agent')`; (5) render `<HelperDrawer>` outside the attempts list when `drawerState !== null`, passing the attempt whose `n === drawerState.n`; close handler sets `drawerState` to null

**Contract:**
- `contracts/openapi.json` — regenerated by `make openapi`
- `web-client/src/api/schema.d.ts` — regenerated by `pnpm gen:api`

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_step_detail_resume.py` -- WRITE FIRST (TDD): all scenarios from I/O matrix (resume null/non-null paths); every test must fail before the implementation tasks below are touched
- `web-client/tests/unit/helper-drawer.test.ts` -- WRITE FIRST (TDD): import HelperDrawer and assert function; must fail (import error) before the component file exists
- `backend-api/src/orchestrator/api/schemas/step_detail.py` -- add `resume_command: str | None = None` and `session_lifetime_ends_at: datetime | None = None` to `AttemptDetailOut`
- `backend-api/src/orchestrator/api/routers/step_detail.py` -- import terminal helpers; compute `_terminal_resume()` per attempt; populate new fields
- `contracts/openapi.json` -- run `make openapi`
- `web-client/src/api/schema.d.ts` -- run `pnpm gen:api` in `web-client/`
- `web-client/src/components/run/HelperDrawer.tsx` -- implement drawer component
- `web-client/src/styles/step-detail.css` -- create CSS file imported by StepDetail.tsx
- `web-client/src/islands/StepDetail.tsx` -- update interface, add imports, drawer state, buttons, and HelperDrawer render

**Acceptance Criteria:**
- Given an agent attempt row on the step-run detail page, when rendered, then a `data-testid="step-prompt-{n}"` button appears on the row; a `data-testid="step-reach-{n}"` button appears only when that attempt's `resume_command` is non-null
- Given the "prompt · result" button is clicked, when the drawer opens, then `data-testid="step-drawer"` is present in the DOM and shows the attempt's dispatch_prompt, retry_prompt (if non-null), and result (if non-null), each with a copy control; the log viewer's follow state is unchanged
- Given the "reach agent" button is clicked, when the drawer opens, then the panel shows the `resume_command` text block with a copy control, the session lifetime line (if `session_lifetime_ends_at` non-null), and the `TERMINAL_SESSION_LINE` text followed by the past-session note
- Given the close button inside the drawer is clicked, when the drawer closes, then `data-testid="step-drawer"` is absent from the DOM and `selectedN`, log follow, and polling are unchanged
- Given the same button is clicked while the drawer is already open for that attempt and content type, when clicked, then the drawer closes
- Given a shell step attempt row (`attempt.command !== null`), when rendered, then no `step-prompt-*` or `step-reach-*` buttons appear on that row
- Given an agent attempt with `RunViewPorts.terminal = None`, when `GET /api/v1/runs/{run_id}/steps/{path}` is called, then `AttemptDetailOut.resume_command` is null and `session_lifetime_ends_at` is null
- Given an agent attempt with claude harness, `session_id` set, and `ports.terminal` wired with `build_harnesses`, when the endpoint is called, then `AttemptDetailOut.resume_command` is a non-empty string containing that session_id
- Given `make openapi` then `pnpm gen:api`, when run after all changes land, then both exit 0 with no schema drift (AD-3)

## Design Notes

**Drawer state toggle:** `toggleDrawer(n, content)` sets `drawerState` to `{ n, content }` when the drawer is closed or showing a different `(n, content)` combination, and to `null` when the drawer is already showing that exact combination — close-on-same-click.

**HelperDrawer tab management:** The drawer receives `initialContent` and manages its active tab via local `useState`. Switching tabs inside the drawer does not propagate state upward — it is entirely drawer-local.

**Drawer renders outside the attempts list:** `<HelperDrawer>` is rendered as a sibling of the attempts section (not nested inside a `<li>`), positioned fixed to the right edge via CSS. This ensures no layout interference with the log viewer or attempt selection.

**resume_command per attempt in the router:** The router already has `run`, `step` (the StepRun), and `attempt` in scope. It calls `_terminal_resume(ports.terminal, run, step, attempt, project_slug=...)` exactly as `run_views.py` calls `resume_command` for the park row — the same function, the same mechanism, but bound to each individual historical attempt rather than only the current park row.

**session_lifetime_ends_at as datetime in schema:** `AttemptDetailOut.session_lifetime_ends_at: datetime | None` serialises to an ISO 8601 string in the JSON response; the frontend receives it as `string | null` and passes it directly to `sessionLifetimeLine()`.

**Past-session note in reach-agent content:** After `TERMINAL_SESSION_LINE`, the reach-agent tab adds: "A past session opens for interrogation; only the current stop's session moves the run." This is a static string defined in `HelperDrawer.tsx`.

**Non-agent attempt detection:** Agent attempts have `attempt.command === null`; shell/git steps have `attempt.command !== null`. This field is already in `AttemptDetail` from story 1-2.

## Verification

**Commands:**
- `make lint` -- expected: exit 0 (ruff, mypy, import-linter, eslint, prettier, tsc, check-test-pairs)
- `make test` -- expected: all tests green including `test_step_detail_resume.py` and `helper-drawer.test.ts`
- `make openapi` -- expected: exit 0, `resume_command` and `session_lifetime_ends_at` visible in `AttemptDetailOut` in `contracts/openapi.json`
- `cd web-client && pnpm gen:api` -- expected: exit 0, no schema drift
