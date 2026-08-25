---
title: AI Orchestrator — Experience
status: draft
created: 2026-08-25
updated: 2026-08-25
name: AI Orchestrator
sources:
  - _bmad-output/planning-artifacts/prds/prd-ai-orchestrator-2026-08-24/prd.md
  - .working/direction-instrument-dark.html
---

# AI Orchestrator — Experience Spine

> Scope: M1 only. Product content is inherited by reference from the PRD (status: final) and is not restated here. Visual identity lives in `DESIGN.md`; tokens are referenced by name as `{path.to.token}`. Where this spine and the PRD disagree, the disagreement is called out explicitly rather than silently resolved.

## Foundation

Web, desktop-first, single operator. Astro front-end over the orchestrator's API. **No inherited UI system** — no shadcn, no MUI, no Tailwind preset, no component library. Every component in `DESIGN.md.Components` is authored for this product, which is why the visual spine is unusually prescriptive: there are no library defaults to fall back on.

`DESIGN.md` is the visual reference and owns colour, type, spacing, shape, and per-component appearance. This document owns structure, behaviour, states, interaction, accessibility, the test-id contract, and the journeys.

Single login, one authenticated user, no roles (FR-4a). There is no multi-user surface anywhere in M1: no sharing, no assignment, no presence, no mentions. The "other party" in every interaction is an agent, not a person.

Dark-first, and dark-only in M1. No light theme, no theme toggle.

**One constraint shapes everything.** Under FR-47 the M1 engine serializes execution — exactly one run is active at a time, globally. The board therefore encodes *lifecycle position*, not concurrency, and the interface must never imply parallelism the engine cannot deliver. This is a settled decision (memlog), not an open question.

## Information Architecture

Six M1 surfaces plus the G3 gate page. This set is settled; nothing is added and nothing is removed.

| # | Surface | Route | Reached from | Purpose |
|---|---|---|---|---|
| 1 | Onboarding | `/onboarding` | First run · rail → Projects / Repositories | Register a project, its repositories, and four optional per-repo commands; validate on save |
| 2 | Board (home) | `/` | App open · rail → Board | Where is everything. Pipeline stages as columns, features/versions as cards |
| 3 | Feature detail | `/features/:featureId` | Board card click | One feature/version: alert at top, epic/story structure, artifact tree at feature scope |
| 4 | Task detail | `/features/:featureId/tasks/:taskId` | Feature detail — a step, or the alert | The blocked step: the question, its criteria, what the agent did, and how to reply |
| 5 | G2 review | `/features/:featureId/gates/g2` | Board card in Plan/G2 · feature detail · notification | Review and accept the execution plan **and** the generated Playwright specs, before workflow creation and setup |
| 6 | Notifications | `/notifications` | Rail → Notifications | Pending human actions and alerts, typed (FR-33) |
| 7 | G3 review | `/features/:featureId/epics/:epicId/gates/g3` | Board card in Review/G3 · feature detail · notification | Artifact tree, diff, E2E result, merge decision |

**[ASSUMPTION] Route strings are inferred.** The memlog settles the surfaces and their navigation edges but not their URLs. Because FR-24a requires every acceptance criterion to name the **routes** it touches, these strings become part of the contract the moment a criterion cites one — so they need confirming before any `epics.md` is authored against them, not after.

**Shell.** Fixed left rail on every surface (`{components.app-rail}`): Board, Notifications, then a Configure group (Projects, Repositories, Workflows), then an Evidence group (Metrics, Gate record). The rail never collapses. A persistent footer line states the serialization truth — how many runs are in flight and how many are queued — so that "only one thing is moving" is read as the design, not as a stall.

**Depth.** Board → feature → task is three levels and that is the maximum. Gate pages are siblings of feature detail, not children of a modal. **There are no modals in M1** except a single destructive-confirm. A gate decision is never taken in an overlay; it gets its own page and its own URL, because a gate decision has to be linkable, bookmarkable, and re-openable after two days away.

**Filtering** is by project and by repository, on the board and on notifications, and is reflected in the query string (`?project=&repo=`) so a filtered board survives a reload and can be linked.

## Voice and Tone

Microcopy only. Aesthetic posture lives in `DESIGN.md`.

The operator is the only human in the system and she already knows what she built. Copy is written for someone competent returning cold — it states facts, names things by their real identifiers, and never encourages, congratulates, or apologises.

| Do | Don't |
|---|---|
| "Nothing needs you." | "You're all caught up! 🎉" |
| "Parked 2d 04h" | "Waiting for a while now" |
| "Halted at $18.40 of $15.00 per-run budget" | "Budget exceeded — action required!" |
| "Rework cap 2/2 reached — spec `filters-restore-from-url` still red after both cycles" | "This task failed repeatedly." |
| "Answer in the session and the run resumes on its own — no action needed here." | "Don't forget to come back and click Resume!" |
| "AC-3 names `inbox-row-age` — no generated spec asserts it. Unmatched criterion blocks G2." | "Some criteria could not be verified." |
| "Skipped — no `e2e_command` declared" / "unvalidated" | "Passed" / "✓" for a check that did not run |
| Name the agent as `Agent · claude-opus-4 · 2026-08-23 09:52` | "Claude says…" / first-person agent voice / "I couldn't figure out…" |
| State the mechanism: "The orchestrator owns the session identity; the harness owns its content." | Hide the mechanism behind "we're working on it" |
| Print exact identifiers: run ids, session ids, branches, worktree paths, spec files and line numbers | Round, abbreviate, or humanise an identifier |

**Hard rule on validation language.** `passed`, `failed`, `skipped`, and `unvalidated` are four distinct words with four distinct meanings (FR-3a, FR-28). A step with no oracle says `unvalidated`. A step bound to an undeclared command says `skipped`. Neither is ever rendered green, and neither is ever collapsed into "OK."

## Component Patterns

Behavioural only. Visual specs live in `DESIGN.md.Components`.

| Component | Where | Behavioural rules |
|---|---|---|
| Record row | Notifications | Whole row is one link target. No hover-revealed actions — everything actionable is on the destination. Two lines: title, then a one-line hint that states *why this row exists*. Single-line truncation with `title` attribute carrying the full string. |
| Board card | Board | Whole card is one link target → feature detail. Cards are **not draggable** — stage is computed from run state, never set by hand. Fixed content order: chip + token, title, project · repo, current step, age. |
| Status chip + token | Board, notifications, detail headers | Always paired, never separated. The token is authoritative; the chip is redundant reinforcement. A row with an unknown state renders the token `---` in `{colors.text-tertiary}` rather than omitting the column. |
| Filter group | Board, notifications | Segmented, single-select, immediate — no Apply button. Writes to the query string. `ALL` is always present and always first. |
| Alert banner | Feature detail | Appears only when the feature has a pending human action. Click target is the whole banner → task detail (or the relevant gate page). At most one banner; if several actions are pending, the banner names the oldest and states the count. |
| Detail header | Feature, task, G2, G3 | Carries the full cold-reload meta line (project · repo · epic · branch · worktree · run id · workflow version) unabridged and never behind a disclosure. Back link returns to the referring surface, defaulting to the board. |
| Question block | Task detail | Read-only. The reply path is the terminal, not this page (FR-23a/FR-35 in M1). No text input is offered, because offering one would imply the answer is delivered here. |
| Criterion block | Task detail, G2 | Renders Given/When/Then plus, for each criterion, its named routes and test-ids (FR-24a) and the generated spec file, line, and status (FR-28b). A criterion with no matching spec renders in the unmatched state and is the thing that blocks G2. |
| Activity timeline | Task detail | Append-only, oldest first, current step last and marked. Never collapsed, never paginated within a task — the whole point is reading the run's history in one pass. |
| Command block | Task detail | Copy button writes the exact string to the clipboard and confirms in place by swapping its label to `COPIED` for ~1.2s. No toast. The command text is selectable and the block never soft-wraps mid-token. Carries the session-content expiry countdown (NFR-5). |
| Artifact tree | Feature detail, G2, G3, task detail | One component, three scopes — see below. Nodes expand/collapse in place; state is per-surface and not persisted across sessions in M1. Clicking a file opens it in an inline viewer pane, not a modal or a new tab. |
| Gate decision bar | G2, G3 | Approve is a primary action; Reject requires a reason before it is enabled. Both are disabled while a blocking condition exists (an unmatched criterion at G2). Neither is placed above the content it decides on — the operator scrolls past the evidence to reach the decision, on purpose. |
| Validation panel | Onboarding | Runs on save (FR-5), reports per-check results as a list, and never blocks the form on a failure it can describe. A repository with no `e2e_command` saves successfully but is marked pipeline-ineligible (FR-3b) rather than rejected outright. |
| Empty state | Every list surface | States what is happening *instead*. Never a bare "no items." |

### The hierarchical artifact view

One component, scoped three ways to the level under review (settled in the memlog). It is the **default detail view** wherever it appears.

| Scope | Host surface | Shows |
|---|---|---|
| Story | Task detail | The files generated in that story's working folder |
| Epic | G3 review | Epic files plus its related stories' folders |
| Feature / version | Feature detail, G2 review | The complete spec folder — all epics and all stories |

Behaviour is identical at all three scopes; only the root and the grouping differ. The component always states its own scope and the absolute worktree folder path it is reading, because the operator needs to be able to `cd` there.

**Last-viewed is tracked from day one.** Every open of the tree records a last-viewed timestamp for the operator against that scope. In M1 this surfaces only as a per-node "changed since you last looked" mark and a header line stating when she last opened it. **The diff-since-last-viewed tab is deferred** pending evidence from the first real run — but the tree header reserves a tab strip position for it (`artifacts-tab-full` / `artifacts-tab-changes`, rendered as a single inert `FULL` tab in M1). Nothing about the M1 layout may make that second tab impossible to add later, and no backfill may ever be required.

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| First run, nothing registered | Board | `NOTHING REGISTERED` + one line naming the next step, linking to `/onboarding`. The rail's Configure group is the only lit path. |
| Board with no features started | Board | All five stage columns render, all empty, each with a `—` placeholder. The footer states `0 runs in flight · 0 queued`. Columns never collapse. |
| Column empty, board non-empty | Board | The column keeps its full width and header count `0`, with a hairline placeholder. Under FR-47 this is the normal case and must read as normal. |
| Loading | Any list | Column heads, grid, and hairlines render immediately; rows render as `{colors.text-tertiary}` placeholder rows of the same height. Layout never shifts on data arrival. |
| Nothing pending | Notifications | `NOTHING NEEDS YOU`, followed by a readout of what is running, what is queued, and when the next return is expected. |
| Run in flight, no human action | Feature detail | No alert banner. The current step is marked in the timeline; the header states the run id and elapsed time. |
| Blocked | Feature detail, board card | `BLK` token + amber chip. On the board, the card keeps its lifecycle column — blocked is a state *on* a card, never a column. On feature detail, an alert banner at the top and the blocked story highlighted in the structure. |
| Stale | Notifications, board | An age past the staleness threshold renders in `{colors.signal-blocked}` with a trailing `·` marker. [ASSUMPTION] The threshold is inferred at 48h; the memlog does not settle it. |
| Unmatched criterion | G2 | A blocker banner naming the criterion and the test-id it cites. Approve is disabled with the reason stated in the button's adjacent note, not in a tooltip (FR-28b). |
| Unvalidated / skipped step | G2, G3, task detail | Rendered as the literal words `unvalidated` / `skipped` in `{colors.text-tertiary}`, never green, never a tick (FR-28, FR-3a). |
| Budget breach | Board card, notifications, task detail | `BGT` token. Task detail's cost table states the breach as a ratio (`$18.40 / $15.00`) and the run shows as halted, not failed (FR-45). |
| Rework cap reached | Notifications, task detail | `RWK` token, with the cycle count as `2/2` and the specific spec still red (FR-19). |
| Infrastructure failure | Notifications, task detail | `INF` token, with the retry count exhausted stated literally (`3/3 retries exhausted`) (FR-16). |
| Session expiring | Task detail | The command block states remaining session-content lifetime (`27d 20h left`). Past expiry the block is replaced by the reconstruction path (FR-22) with an explicit note that resume is no longer possible (NFR-5, C-4). |
| Repo missing `e2e_command` | Onboarding, board | Saved, listed, and marked `PIPELINE INELIGIBLE — no e2e_command` (FR-3b). It cannot be selected as a run target; the reason is stated at the point of selection, not discovered later. |
| Validation failure on save | Onboarding | Per-check failure lines with the actual command output. The form retains every entered value. Nothing is silently corrected. |
| Copy unavailable | Task detail | If the clipboard API is unavailable, the command block stays selectable and the button label becomes `SELECT`. The command is never rendered unusable. |
| Terminal state | Feature detail, board | `MERGED` / `CANCELLED` stated in words in the header; the card moves to the Merged column or leaves the board with its reason recorded in the gate record. |
| Error fetching a surface | Any | A full-surface readout stating the failed request and a retry control. Never a blank page, never an illustration. |

## Interaction Primitives

**Mouse-first, keyboard-adequate.** This is a deliberate M1 restraint (memlog): keyboard affordances stay minimal beyond copying the resume command, because inventing a shortcut vocabulary for one operator before the loop is proven is speculative work.

- **Click to navigate.** Whole rows and whole cards are single link targets. No hover-revealed actions anywhere — an affordance that only exists on hover is invisible to someone scanning a two-day-old board.
- **`Ctrl/Cmd + C` on the command block**, and a Copy button, both produce the identical string. The copy affordance confirms in place.
- **`Esc`** dismisses the one destructive-confirm dialog. There is nothing else to dismiss.
- **`Tab`** traverses in reading order on every surface; the focus ring is `{components.focus-ring}` and is never suppressed.
- **Browser back** always works and always returns to the referring surface with its filter state intact — which is why filters live in the query string and gates are pages rather than overlays.
- **Refresh model.** [ASSUMPTION] Polling on an interval with a visible "last updated" timestamp in the footer, plus a manual refresh control. The PRD specifies no live-update mechanism (this is flagged as a gap in the PRD's own scope review), so the interface must not depend on push. A surface must never appear live when it is not.

**Banned everywhere:** modals for anything but destructive confirmation; drag-and-drop (stage is computed, not set); infinite scroll; toasts as the only record of an event; hover-only affordances; auto-refresh that moves content under the cursor; optimistic UI on anything that costs money or touches a branch; animation beyond an instantaneous state swap; sound.

## Accessibility Floor

Behavioural. Contrast and colour live in `DESIGN.md`.

- **WCAG 2.2 AA** across the surface. `{colors.text}` on `{colors.bg}` and `{colors.text-secondary}` on `{colors.bg}` both clear AA for body text; `{colors.text-tertiary}` is used only for non-essential meta and is verified against AA large-text at its rendered sizes. Any text carrying information a task depends on uses `{colors.text}` or `{colors.text-secondary}`.
- **Colour is never the sole carrier of state.** Every status is a three-letter word token in a fixed column position; the chip is redundant. This satisfies the requirement structurally rather than by remediation, and it is the reason the token exists.
- **Semantic structure.** One `h1` per surface (the detail title or surface name). Lists are lists; the board's columns are labelled regions; the record grid is a `table` with real column headers on notifications and a labelled list on the board.
- **The board is announced by stage.** Landing on `/` announces the surface, the active filter, and the per-stage counts, so an operator who cannot scan five columns visually gets the same one-glance summary.
- **Live regions.** Filter changes and refreshed counts announce via `aria-live="polite"`. The copy confirmation announces. Nothing else interrupts.
- **The command block is reachable and readable by keyboard alone** — focusable, selectable, with the copy control in tab order and an accessible name that includes the word "resume command."
- **Focus is never trapped**, because there is nothing to trap it in. The single destructive-confirm dialog returns focus to its trigger on close.
- **Truncated cells carry their full value** as an accessible name, so the visual ellipsis never loses information.
- **Motion.** There is effectively none; nothing in the product animates beyond an instantaneous state swap, so `prefers-reduced-motion` has nothing to disable. This is a property of the design, not a setting.
- **Zoom to 200%** must not lose content. The fixed grid scrolls horizontally rather than reflowing.

## Test-ID Contract

**This section is the interface contract.** PRD FR-24a requires every acceptance criterion to name the test-ids and routes it touches, validated on ingest and enforced at G2. FR-28b generates Playwright specs from those signed criteria, targeting these ids. FR-3b makes the existence of that suite the precondition for `ai-orchestrator` running its own pipeline. So this table is not documentation of a build — it is the artifact the build is generated from, and the artifact `epics.md` is written against.

Consequence: **a test-id here is an API.** Renaming one breaks generated specs and invalidates signed criteria. Ids change only through the same review that changes a route.

### The rule

Every interactive element, every element whose text an assertion would read, and every container an assertion would scope to, carries a `data-testid`. If a Playwright assertion could plausibly need it, it has one. Nothing is selected by CSS class, tag structure, or visible text.

**Grammar:** `<surface>-<component>[-<instance>][-<field>]`, lowercase kebab-case throughout.

| Segment | Rule |
|---|---|
| `<surface>` | The surface's own prefix, fixed: `nav` (global shell), `onboarding`/`project-form`/`repo-form`/`repo-validation`/`repo-list`, `board`, `feature`, `task`, `g2`, `g3`, `notifications`, `artifacts` (the shared tree component). |
| `<component>` | The component's name in the component table — `row`, `card`, `filter`, `criterion`, `activity`, `resume`, `column`, `node`. |
| `<instance>` | The domain identity of the item: a story slug (`blocked-3-2`), an epic slug, a stage name (`spec`), a criterion number (`ac-2`), a repository slug, a file slug. **Never an array index**, never a position, never a database id that changes between environments. |
| `<field>` | The specific value being asserted on: `-title`, `-status`, `-project`, `-repo`, `-step`, `-age`, `-hint`, `-type`, `-count`, `-route`, `-testids`. |

**Ordinals** are permitted in exactly one case: a collection that is inherently ordered and has no stable domain identity — the activity timeline (`task-activity-step-3`) and plan steps (`g2-plan-step-4`). Everywhere else an ordinal is a bug waiting for the list to reorder.

**States are attributes, not ids.** A blocked row is `notifications-row-blocked-3-2` with its state readable from `notifications-row-blocked-3-2-type`; it does not become `notifications-row-blocked-3-2-is-blocked`. Assertions read text and attributes, they do not select on state.

**Container + field, always.** Every collection item has a container id and separately-addressable field ids beneath it. This lets a spec scope to one row and assert several fields without positional selectors, which is what makes the generated specs stable when the list reorders.

**One id per element, one element per id.** A `data-testid` is unique within its surface. Repeated instances differ by their `<instance>` segment.

**Two renames carried over from the direction file, and why.** The direction file `direction-instrument-dark.html` used `inbox-*` and `detail-*`. The IA was revised *after* those directions were rendered: the inbox was demoted to a notifications surface and "detail" split into two distinct surfaces (feature and task). `inbox-*` therefore becomes `notifications-*` and `detail-*` becomes `task-*`. The grammar, field vocabulary, and structure are unchanged. Also: the direction file contains `nav-inbox-empty` / `nav-inbox-detail` variants — these are an artifact of three mock screens sharing one HTML document and **must not** survive into the product; the shell's ids are identical on every surface.

### Global shell — present on every surface

| Test-ID | Element |
|---|---|
| `app-shell` | Root layout container |
| `nav-rail` | Navigation rail |
| `nav-brand` | Brand block |
| `nav-board` | Board link |
| `nav-notifications` | Notifications link |
| `nav-notifications-count` | Pending-action count beside it |
| `nav-projects` | Projects link |
| `nav-repositories` | Repositories link |
| `nav-workflows` | Workflows link (read-only viewing, FR-12) |
| `nav-metrics` | Metrics link |
| `nav-gate-record` | Gate record link (FR-32) |
| `global-run-status` | Footer: runs in flight / queued / last updated |

### Surface 1 — Onboarding · `/onboarding`, `/projects/new`, `/projects/:projectId/repositories/new`

| Test-ID | Element |
|---|---|
| `onboarding-root` | Surface root |
| `onboarding-step-project` | Step: project |
| `onboarding-step-repositories` | Step: repositories |
| `onboarding-step-commands` | Step: per-repo commands |
| `onboarding-empty-state` | Nothing registered yet |
| `onboarding-complete` | Completion readout |
| `project-form` | Project form container |
| `project-form-name` | Project name (FR-1) |
| `project-form-strategy` | Strategy / business context (FR-1) |
| `project-form-context` | Context artifacts: architecture notes, glossary (FR-2) |
| `project-form-github-token` | GitHub token (FR-4) |
| `project-form-env-vars` | Agent environment variables (FR-4) |
| `project-form-submit` | Save project |
| `project-form-error` | Project-level validation error |
| `repo-form` | Repository form container |
| `repo-form-url` | Repository URL |
| `repo-form-default-branch` | Default branch (FR-3) |
| `repo-form-package-manager` | Package manager (FR-3) |
| `repo-form-cmd-unit-test` | `unit_test_command` |
| `repo-form-cmd-code-quality` | `code_quality_command` |
| `repo-form-cmd-e2e` | `e2e_command` |
| `repo-form-cmd-quality-gate` | `quality_gate_command` |
| `repo-form-save` | Save repository (triggers validation, FR-5) |
| `repo-form-cancel` | Cancel |
| `repo-validation-panel` | Validation results container |
| `repo-validation-clone` | Clone check result |
| `repo-validation-cmd-unit-test` | Unit-test command check |
| `repo-validation-cmd-code-quality` | Code-quality command check |
| `repo-validation-cmd-e2e` | E2E command check |
| `repo-validation-cmd-quality-gate` | Quality-gate command check |
| `repo-validation-e2e-missing-warning` | Pipeline-ineligible notice (FR-3b) |
| `repo-validation-error` | Validation failure detail with command output |
| `repo-list` | Registered repositories list |
| `repo-list-add` | Add repository |
| `repo-list-row-{repoSlug}` | One registered repository |
| `repo-list-row-{repoSlug}-name` | Its name |
| `repo-list-row-{repoSlug}-status` | Eligible / pipeline-ineligible |
| `repo-list-row-{repoSlug}-edit` | Edit it |

### Surface 2 — Board (home) · `/`

| Test-ID | Element |
|---|---|
| `board-root` | Surface root |
| `board-count` | Feature count + oldest age |
| `board-search` | Free-text filter |
| `board-filters` | Filter group container |
| `board-filter-project` | Filter by project |
| `board-filter-repository` | Filter by repository |
| `board-filter-clear` | Clear filters |
| `board-column-spec` | Stage column: Spec |
| `board-column-plan` | Stage column: Plan / G2 |
| `board-column-build` | Stage column: Build |
| `board-column-review` | Stage column: Review / G3 |
| `board-column-merged` | Stage column: Merged |
| `board-column-{stage}-count` | Per-column count (5 instances) |
| `board-column-{stage}-empty` | Per-column empty placeholder (5 instances) |
| `board-card-{featureSlug}` | One feature/version card |
| `board-card-{featureSlug}-status` | Its chip + three-letter token |
| `board-card-{featureSlug}-title` | Its title |
| `board-card-{featureSlug}-project` | Its project |
| `board-card-{featureSlug}-repo` | Its repository |
| `board-card-{featureSlug}-step` | Current step, e.g. "epic 1, story 3" |
| `board-card-{featureSlug}-age` | Age in current stage |
| `board-empty-state` | No features match the filter |
| `board-first-run-state` | Nothing registered at all |

### Surface 3 — Feature detail · `/features/:featureId`

| Test-ID | Element |
|---|---|
| `feature-root` | Surface root |
| `feature-back` | Back to board |
| `feature-title` | Feature / version title |
| `feature-meta` | Cold-reload meta line |
| `feature-status` | Chip + token for the feature |
| `feature-alert` | Pending-action banner (whole banner is the link) |
| `feature-alert-type` | Its chip + token |
| `feature-alert-message` | Its one-line statement |
| `feature-alert-open-task` | Its target link → task detail |
| `feature-progress` | Stage strip |
| `feature-progress-stage-{stage}` | One stage in the strip (5 instances) |
| `feature-epic-{epicSlug}` | One epic in the structure |
| `feature-epic-{epicSlug}-title` | Its title |
| `feature-epic-{epicSlug}-status` | Its chip + token |
| `feature-story-{storySlug}` | One story |
| `feature-story-{storySlug}-status` | Its chip + token |
| `feature-story-{storySlug}-step` | Its current step |
| `feature-story-{storySlug}-open` | Open its task detail |
| `feature-gate-g2-link` | Go to the G2 page |
| `feature-gate-g3-link` | Go to the G3 page |
| `feature-cost` | Cost / budget key-value table (FR-44, FR-45) |
| `feature-open-pr` | Open the PR (FR-40) |
| `feature-open-trace` | Open the trace (FR-43) |
| `feature-cancel-run` | Cancel run and roll back branch (FR-18) — destructive confirm |
| `feature-empty-state` | Feature registered, nothing started |

### Shared component — hierarchical artifact tree

Host surfaces: task detail (story scope), feature detail and G2 (feature scope), G3 (epic scope). The component appears at most once per surface, so its ids are stable regardless of host.

| Test-ID | Element |
|---|---|
| `artifacts-root` | Tree container |
| `artifacts-scope` | Declared scope: story / epic / feature |
| `artifacts-folder-path` | Absolute worktree folder path |
| `artifacts-last-viewed` | "You last opened this …" |
| `artifacts-refresh` | Re-read the folder |
| `artifacts-tab-full` | `FULL` tab — the only tab in M1 |
| `artifacts-tab-changes` | **Reserved**, not rendered in M1 (deferred diff-since-last-viewed) |
| `artifacts-group-{groupSlug}` | An epic or story grouping node |
| `artifacts-node-{fileSlug}` | One file node |
| `artifacts-node-{fileSlug}-name` | Its filename |
| `artifacts-node-{fileSlug}-updated` | Its modified timestamp |
| `artifacts-node-{fileSlug}-new-badge` | Changed-since-last-viewed mark |
| `artifacts-file-viewer` | Inline file pane |
| `artifacts-file-viewer-title` | Its path heading |
| `artifacts-file-viewer-body` | Its content |
| `artifacts-file-viewer-close` | Close the pane |
| `artifacts-empty-state` | Folder exists but is empty |

### Surface 4 — Task detail · `/features/:featureId/tasks/:taskId`

| Test-ID | Element |
|---|---|
| `task-root` | Surface root |
| `task-back` | Back to feature detail |
| `task-type-badge` | Chip + token + full type name |
| `task-title` | Story title |
| `task-meta` | Cold-reload meta line: project · repo · epic · branch · worktree · run · workflow version |
| `task-question` | The question that parked the run (FR-30) |
| `task-question-author` | Agent · model · timestamp |
| `task-criterion-ac-{n}` | One acceptance criterion |
| `task-criterion-ac-{n}-spec` | Its generated spec file, line, and status (FR-28b) |
| `task-criterion-ac-{n}-route` | The route it names (FR-24a) |
| `task-criterion-ac-{n}-testids` | The test-ids it names (FR-24a) |
| `task-activity` | Activity timeline container |
| `task-activity-step-{n}` | One timeline entry (ordinal permitted) |
| `task-resume-block` | Resume-command block |
| `task-resume-command` | The exact `claude --resume <session-id>` string (FR-23a) |
| `task-resume-copy` | Copy it |
| `task-resume-expiry` | Session-content lifetime remaining (NFR-5) |
| `task-structured-output` | Structured output table (FR-24) |
| `task-cost` | Cost and trace table (FR-26, FR-44) |
| `task-artifacts` | Artifact tree at story scope |
| `task-open-diff` | Open the diff |
| `task-open-trace` | Open the trace |
| `task-open-logs` | Agent logs |
| `task-dismiss` | Dismiss escalation (FR-30a) |
| `task-cancel-run` | Cancel run and roll back branch — destructive confirm |

### Surface 5 — G2 review · `/features/:featureId/gates/g2`

| Test-ID | Element |
|---|---|
| `g2-root` | Surface root |
| `g2-title` | Gate title |
| `g2-meta` | Cold-reload meta line |
| `g2-blocker-banner` | Unmatched criterion blocks approval (FR-28b) |
| `g2-plan` | Generated plan container (FR-12a) |
| `g2-plan-workflow-name` | Template name |
| `g2-plan-version` | Pinned document version (FR-9) |
| `g2-plan-step-{n}` | One plan step (ordinal permitted) |
| `g2-plan-epic-{epicSlug}` | One planned epic |
| `g2-plan-story-{storySlug}` | One planned story |
| `g2-specs` | Generated Playwright specs container (FR-28b) |
| `g2-spec-{specSlug}` | One generated spec |
| `g2-spec-{specSlug}-criterion` | The criterion it was generated from |
| `g2-spec-{specSlug}-route` | The route it targets |
| `g2-spec-{specSlug}-testids` | The test-ids it asserts |
| `g2-coverage` | Coverage summary |
| `g2-coverage-matched` | Matched criteria count |
| `g2-coverage-unmatched-criteria` | Criteria with no spec — blocking |
| `g2-coverage-unmatched-specs` | Specs with no criterion — reported |
| `g2-manual-estimate` | Pre-registered manual estimate (FR-50) |
| `g2-artifacts` | Artifact tree at feature scope |
| `g2-approve` | Approve and start (FR-12a) |
| `g2-reject` | Reject |
| `g2-reject-reason` | Rejection reason (required before Reject enables) |
| `g2-decision-record` | Recorded decision: who, when, against which version (FR-32) |
| `g2-empty-state` | Nothing to review yet |

### Surface 6 — G3 review · `/features/:featureId/epics/:epicId/gates/g3`

| Test-ID | Element |
|---|---|
| `g3-root` | Surface root |
| `g3-title` | Gate title |
| `g3-meta` | Cold-reload meta line |
| `g3-artifacts` | Artifact tree at epic scope |
| `g3-diff` | Diff container |
| `g3-diff-stats` | Files changed / insertions / deletions |
| `g3-diff-file-{fileSlug}` | One changed file |
| `g3-e2e-result` | Playwright run result (FR-29) |
| `g3-e2e-spec-{specSlug}` | One spec result |
| `g3-e2e-spec-{specSlug}-status` | Its pass / fail |
| `g3-quality-gate-result` | Quality-gate command result |
| `g3-unvalidated-notice` | Steps with no oracle, rendered `unvalidated` (FR-28) |
| `g3-assumptions` | Routine assumptions recorded, shown here not escalated (FR-30) |
| `g3-assumption-{n}` | One assumption (ordinal permitted) |
| `g3-pr-link` | The open PR (FR-40) |
| `g3-cost` | Epic cost roll-up (FR-44) |
| `g3-active-time` | Active human minutes in this gate (FR-51) |
| `g3-approve-merge` | Approve — a human performs the merge (FR-42) |
| `g3-reject` | Reject |
| `g3-reject-reason` | Rejection reason (required) |
| `g3-reject-confirm` | Confirm rejection — destructive confirm |
| `g3-respec-notice` | States what rejection triggers: an epic-level re-spec, not a per-story retry |
| `g3-decision-record` | Recorded decision (FR-32) |

### Surface 7 — Notifications · `/notifications`

| Test-ID | Element |
|---|---|
| `notifications-root` | Surface root |
| `notifications-count` | Item count + oldest age |
| `notifications-search` | Free-text filter |
| `notifications-filters` | Filter group container |
| `notifications-filter-all` | `ALL` |
| `notifications-filter-blocked` | `BLK` — blocked story |
| `notifications-filter-qa` | `QA` — epic ready for QA |
| `notifications-filter-budget` | `BGT` — budget breach |
| `notifications-filter-rework` | `RWK` — rework cap reached |
| `notifications-filter-infra` | `INF` — infrastructure failure |
| `notifications-filter-criterion` | `CRT` — unmatched criterion |
| `notifications-table` | Record table |
| `notifications-row-{typeSlug}-{itemSlug}` | One notification row |
| `notifications-row-{typeSlug}-{itemSlug}-type` | Its chip + token |
| `notifications-row-{typeSlug}-{itemSlug}-project` | Its project |
| `notifications-row-{typeSlug}-{itemSlug}-repo` | Its repository |
| `notifications-row-{typeSlug}-{itemSlug}-title` | Epic / story |
| `notifications-row-{typeSlug}-{itemSlug}-hint` | Why it is here |
| `notifications-row-{typeSlug}-{itemSlug}-age` | Its age |
| `notifications-mark-seen` | Mark seen (does not resolve the underlying action) |
| `notifications-footer-status` | Serialization readout |
| `notifications-empty-state` | Nothing needs you |

### Contract total

**211 ids**, counting each `{instance}` pattern once. Three of them are per-stage patterns (`board-column-{stage}-count`, `board-column-{stage}-empty`, `feature-progress-stage-{stage}`) that resolve to five concrete ids each.

**Verification-queue note.** The memlog records this run as verification item #1 from the PRD addendum: assign test-ids at design time for three real features and confirm it is tolerable. The finding: it is tolerable, and it is cheap — but only because the grammar was fixed *first*. Assigning ids surface-by-surface without the `<surface>-<component>-<instance>-<field>` rule would have produced 211 arbitrary strings. The rule is the reusable output here; the table is its application.

## Key Flows

Protagonist: **Rebeca**, sole operator, the only human in the system.

### Flow A — Onboarding a repository (Monday, setting up the fullstack app)

1. Rebeca opens the app cold. The board shows `board-first-run-state`: nothing registered, one line pointing at Configure.
2. She goes to `/onboarding`. `project-form` asks for a name, strategy and business context, architecture notes, a GitHub token, and agent environment variables. She saves.
3. `repo-form` opens. She pastes the repository URL, sets the default branch and package manager, then fills three of the four command fields — unit test, code quality, quality gate — and leaves `repo-form-cmd-e2e` for last, pasting in the Playwright invocation.
4. She hits `repo-form-save`. `repo-validation-panel` runs the checks live: clone succeeds; each declared command is executed and its exit status reported (FR-5).
5. `repo-validation-cmd-code-quality` comes back red — the lint command references a config path that only exists in CI. The form keeps every value she typed and prints the actual command output.
6. She fixes the command in place and saves again. All four checks come back clean.
7. **Climax:** `repo-list-row-{repoSlug}-status` reads `ELIGIBLE`. She scrolls down and sees the second repository she registered earlier — the `ai-orchestrator` repo itself — sitting there marked `PIPELINE INELIGIBLE — no e2e_command`, with the reason stated on the row rather than buried in a settings page. The system has told her, at setup time and in one glance, exactly which of her repositories can be trusted to the pipeline and why the other cannot. That is FR-3b enforced at the moment it costs nothing, instead of six hours into a run.

Failure: clone fails on a bad token → `repo-validation-clone` reports the auth error verbatim and links back to `project-form-github-token`. The repository is not saved half-configured.

### Flow B — The cold return (Thursday 09:10, after two days on another project)

1. Rebeca opens the board. `nav-notifications-count` reads `3`. The Build column holds one card: `board-card-{featureSlug}-status` shows an amber chip and `BLK`, `board-card-{featureSlug}-step` reads "epic 3, story 3.2", `board-card-{featureSlug}-age` reads `2d 04h` in amber. Every other column is quiet — which, under serialization, is the truth and reads as the truth.
2. She clicks the card. Feature detail opens. `feature-alert` sits at the top: `BLK · S3.2 parked 2d 04h · agent asked a question`. Below it the epic structure, with story 3.2 marked and everything above it green.
3. She clicks the alert. Task detail opens on `/features/:featureId/tasks/:taskId`.
4. `task-question` carries the whole thing at 14px: AC-2 says a returning user sees their last filters, but does not say what a signed-out visitor sees — persist in `localStorage`, or clear at logout? The agent implemented the signed-in path and stopped rather than guess at a privacy decision.
5. She reads `task-criterion-ac-2` — Given/When/Then, the route it names, the test-ids it names, and `saved-views.spec.ts:31 · red`. Then `task-activity`: six entries, 08:12 to 09:52, ending with the run parking. Two days of machine work, reconstructed in about ninety seconds of reading.
6. She still isn't sure what the epic decided about anonymous sessions. She opens `task-artifacts` — the story-scoped tree — and `artifacts-node-{fileSlug}-new-badge` marks two files written since she last looked. The architecture note settles it: anonymous state is never persisted server-side.
7. She hits `task-resume-copy`. The label swaps to `COPIED`.
8. **Climax:** She pastes into her terminal. `cd /work/fullstack-app/feat-saved-views-3-2 && claude --resume 6f2a1c94-…` drops her straight back into the session that asked the question — same working directory, same context, no reconstruction. She types the answer and closes the terminal. She does not return to the browser, because `task-resume-block` already told her not to: *answer in the session and the run resumes on its own*. Twenty minutes later the board's card has moved on by itself. The cold-reload cost that the whole async premise depends on came in under five minutes of her actual attention (FR-34, FR-51).

Failure: the session content has expired past the 30-day window (NFR-5) → `task-resume-expiry` reads `EXPIRED` and `task-resume-block` is replaced by the reconstruction path (FR-22), stating plainly that resume is no longer possible and what will be rebuilt instead.

### Flow C — G2 approval (Tuesday, before a run starts)

1. A feature sits in the Plan/G2 column. Rebeca opens `/features/:featureId/gates/g2`.
2. `g2-plan` shows the bound workflow instance — template name, pinned document version, the epic and story list, and every step. Structure she recognises, because workflow structure is never model-generated (FR-11c).
3. She scrolls to `g2-specs`. Each generated Playwright spec is listed against the criterion it came from, with the route and test-ids it asserts.
4. `g2-blocker-banner` is lit: `g2-coverage-unmatched-criteria` reads `1`. AC-3 names the test-id `inbox-row-age`, and no generated spec asserts it. `g2-approve` is disabled, with the reason stated beside it, not in a tooltip.
5. She reads the criterion. The test-id is stale — it was renamed to `notifications-row-age` when the inbox became the notifications surface, and `epics.md` was never updated.
6. She rejects with that as the reason, fixes the criterion in `epics.md`, and re-ingests. The specs regenerate; coverage comes back clean.
7. **Climax:** She scrolls past the plan, past sixteen generated specs, past the coverage summary, and only then reaches `g2-approve` — the layout made her walk the evidence to get to the button. Before approving she fills `g2-manual-estimate`: *writing this myself, four hours*. That number is captured before a single token is spent, which is the one-way door (FR-50) — retrofit it afterwards and the entire verdict metric is permanently unanswerable. She approves. `g2-decision-record` stamps who, when, and against which artifact version. The branch and worktree are created behind her.

Failure: she approves and *then* notices a wrong story in the plan → she cancels the run from feature detail (`feature-cancel-run`), which rolls back the branch. No half-state; the gate record keeps both decisions.

### Flow D — G3 rejection (Friday afternoon, epic ready for QA)

1. `notifications-row-qa-epic-2` reads: PR #418 open, quality gate green, 14/14 Playwright specs green against a seeded database. She opens the G3 page.
2. `g3-artifacts` gives her the epic-scoped tree — epic files plus all three stories' folders. `g3-diff` gives her the change. `g3-e2e-result` gives her fourteen green specs. `g3-quality-gate-result` is clean.
3. Everything the machine can check is green. She reads the diff anyway, which is the entire point of a human gate.
4. The code is correct against the criteria — and the criteria are wrong. The epic assumed one saved view per user; the product needs several, and story 2.1's data model has a unique constraint that forecloses it. No spec catches this, because no spec could: the oracle was fixed before the implementation, and it was fixed against a bad premise.
5. She hits `g3-reject` and writes the reason: the epic's data model assumption is wrong, not the implementation of it.
6. `g3-respec-notice` states exactly what happens next, before she confirms: **this is not a per-story retry.** The PM/architect rewrites the spec for the whole epic, because a wrong premise in one story almost always implies impacts beyond it. A new adjusted workflow is generated and re-runs on the same working branch; stories whose specs are unchanged are skipped; the change is recorded as a git commit.
7. **Climax:** She confirms at `g3-reject-confirm`. The board's card slides from Review/G3 back to Spec — not to Build, and not to a retry of story 2.1. The interface just told her the truth about the machine's shape: this pipeline does not patch a bad answer, it re-asks the question at the level the question was actually wrong at. `g3-decision-record` stamps the rejection against the artifact version, and FR-52's rejection-rate counter ticks — the metric that exists to catch a gate that never says no. This one just did.

Failure / contradiction to resolve: the memlog flags this flow as a **PRD change required**. FR-19a in the finalized PRD says a G3 rejection opens a *new session* bounded by the FR-19 per-story rework cap. This flow implements the user's later decision — an epic-level re-spec — which is a larger mechanism, and the per-story cap may no longer be the right bound. `g3-respec-notice` is written against the memlog decision, not against FR-19a. **This must be resolved by a `bmad-prd` update pass before build**; it must not drift as a UX-only decision.

## Open Gaps

Surfaced rather than decided. Each needs the user's call.

1. **FR-19a contradiction (blocking, already flagged in the memlog).** G3 rejection: new session bounded by the per-story cap (PRD) vs. epic-level re-spec (memlog decision, implemented above). Needs a PRD update pass, including whether the FR-19 cap still applies and at what level.
2. **Routes are unconfirmed.** All seven route strings are `[ASSUMPTION]`. FR-24a makes routes part of the signed criteria, so these must be confirmed before `epics.md` cites any of them.
3. **Where FR-50's manual estimate is captured.** Placed on the G2 page here as the last moment before a run begins. The PRD says "at ingest in M1," which may mean the `epics.md` ingest step rather than G2. One-way door — worth being certain.
4. **G2 scope.** Modelled as feature/version-scoped (`/features/:featureId/gates/g2`). If G2 is in fact per-epic, the route and the artifact-tree scope both change.
5. **No live-update mechanism exists in the PRD.** Polling with a visible last-updated timestamp is assumed. The PRD's own scope review flags the Astro front-end as having zero requirements covering the API contract, auth, session handling, or how status streams. This spine cannot close that gap.
6. **Staleness threshold** for amber ageing is assumed at 48h.
7. **Responsive behaviour** is assumed out of scope (desktop-only, horizontal scroll below ~1024px).
8. **"Unchanged story" determination** on re-spec (memlog open mechanism) has no UI answer here because it has no decided mechanism. The recommendation stands: the orchestrator computes it deterministically from a content hash of each story's spec section. If it is ever decided by agent judgment, G3 and feature detail both need a surface showing what was skipped and why — which does not exist in this spec.
