---
title: 'Board LIST view'
type: 'feature'
created: '2026-09-11'
status: 'done'
baseline_revision: 'cc75b57f8532211c8e7919634d84cadab4678cdc'
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Board's `LIST` toggle is a disabled stub (`aria-disabled`); the Operator has no record-row layout when there are too many cards to scan across five columns.

**Approach:** Activate the `BOARD · LIST` toggle inside the `Board` island (React state + `history.replaceState` URL sync); render `RunListRow` components grouped by column order from the already-fetched `BoardOut` data; no new API request on toggle.

## Boundaries & Constraints

**Always:**
- The `view` state lives inside `Board.tsx`; the Astro page passes `initialView` (from `?view=`) at SSR time; toggling does not navigate or re-mount.
- Toggle writes `?view=list` via `history.replaceState`, preserving any `?project=` param; restoring BOARD removes `?view=`.
- The list re-renders the same `$board` store data — no new `GET /runs` call on toggle.
- Row group order: Needs you → Running → Queued → Done → Failed; groups with zero cards are omitted.
- Rows sorted newest-first (ascending `age_seconds`) within each group.
- Signal rule identical to board: `isAgedNeedsYou(token, age_seconds)` sets `data-signal="needs-you"` on the token cell and age cell only; nothing else in the row carries a signal colour.
- Required test-ids: `board-toggle-list` (LIST button), `board-list` (list container), `board-list-row-{id}` (each row).
- Schema is generated, never hand-edited (AD-3); no backend changes, no `make openapi` needed.

**Block If:**
- `CardOut` in the running schema lacks any of the seven fields (`token`, `project_name`, `repository_slug`, `branch`, `current_step_label`, `progress`/`kind_label`, `age_seconds`) — confirmed present; not a blocker.

**Never:**
- A second `GET /runs` request caused by toggling.
- Sorting controls (rows follow column order then age only).
- Modify any existing test file.
- Cap list rows (list is for scanning many runs — done/failed cap is a card-layout constraint only).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|----------------|----------------|
| LIST selected | Board loaded, BOARD view active | `board-list` renders; rows grouped with column-head per non-empty group; URL carries `?view=list`; no additional request | — |
| BOARD re-selected | `board-list` visible | columns restore; URL loses `?view=`; no additional request | — |
| Reload with `?view=list` | `Astro.url.searchParams.get('view') === 'list'` | `Board` mounts with `initialView='list'`; `board-list` visible | — |
| BLK card ≥ 48 h in list | `token:'BLK'`, `age_seconds ≥ 172800`, listed | token cell and age cell carry `data-signal="needs-you"` (amber); no other cell in the row does | — |

</intent-contract>

## Code Map

- `web-client/src/pages/index.astro:87-91` — static `<div class="board-toggle" data-testid="board-toggle-view">` stub (both items `<span>`); **remove** this block; add `const view = Astro.url.searchParams.get('view') === 'list' ? 'list' : 'board'` alongside line 37's `selectedProjectId` read; pass `initialView={view}` to `<Board>` at line 120
- `web-client/src/pages/index.astro:125-150` — scoped `<style>` block; remove `.board-toggle span` and `.board-toggle-list[aria-disabled]` rules (now in `board.css`); keep `.board-filter a` rules unchanged
- `web-client/src/islands/Board.tsx:51-53` — `Props { initialProjectId }` interface; add `initialView?: 'board' | 'list'`
- `web-client/src/islands/Board.tsx:117` — `export default function Board({ initialProjectId })`: destructure `initialView` too; add `const [view, setView] = useState<'board' | 'list'>(initialView ?? 'board')` and `switchView(v)` using `new URLSearchParams(window.location.search)` + `history.replaceState` + `setView(v)`
- `web-client/src/islands/Board.tsx:208-229` — main return `<div data-testid="board">`; add toggle as first child (container `data-testid="board-toggle-view"`, BOARD button unmarked, LIST button `data-testid="board-toggle-list"`; each has `aria-current={view === x ? 'true' : undefined}` and calls `switchView`); replace `<div class="board-columns">` with a conditional: `view === 'list'` → `<div data-testid="board-list">` with groups; otherwise existing columns
- `web-client/src/components/RunCard.tsx:29-67` — pattern for token chip + aged amber: import `tokenSignal`, `isAgedNeedsYou`; `<span data-signal={signal}>` on token, `data-signal={aged?'needs-you':undefined}` on age; `RunListRow` follows the same pattern in row form
- `web-client/src/lib/board/format.ts:54` — `tokenSignal`, `isAgedNeedsYou`, `ageText`, `progressText` — all reused in `RunListRow`; `capColumn` NOT used (no cap in list view)
- `web-client/src/api/schema.d.ts` — `CardOut` fields consumed: `id`, `token`, `project_name`, `repository_slug`, `branch`, `current_step_label`, `progress` (`ProgressOut|null`), `kind_label`, `age_seconds`; shape unchanged by this story
- `web-client/src/styles/board.css` — add `.board-toggle` layout (flex, baseline, gap); `.board-toggle button` type reset + control-font sizing + tertiary colour; `[aria-current='true']` → primary colour; `.board-list` (flex column); `.board-list-group`; `.board-list-group-head` (column head label, same control-font + secondary colour); `.board-list-row` (grid/flex row, link, no decoration); `.board-list-token`, `.board-list-chip` (7 px chip matching `.run-card-chip`); `.board-list-age[data-signal='needs-you']` amber
- `web-client/tests/e2e/board.spec.ts` — DO NOT MODIFY; the `unexpectedSignals` helper scans the full page but none of its test cases render a BLK card aged > 48 h in list view; board.spec.ts opens `BOARD_URL` without `?view=list` so `view` defaults to `'board'`

## Tasks & Acceptance

**Execution:**

1. `web-client/src/pages/index.astro` — add `const view = Astro.url.searchParams.get('view') === 'list' ? 'list' : 'board'` (line 37 area); remove the static `<div class="board-toggle">` block (lines 87-91); pass `initialView={view}` to `<Board>`; remove orphaned `.board-toggle span` and `.board-toggle-list[aria-disabled]` CSS rules from the scoped `<style>` block (keep `.board-filter` rules intact)
2. `web-client/src/islands/Board.tsx` — add `initialView?: 'board' | 'list'` to `Props`; add `view` state (default `initialView ?? 'board'`) and `switchView(v)` that preserves `?project=` via `URLSearchParams`; in the main return add toggle as first child of `<div data-testid="board">` with `data-testid="board-toggle-view"`, BOARD button, and LIST button `data-testid="board-toggle-list"`; replace `<div className="board-columns">` with conditional: list view renders `<div data-testid="board-list" className="board-list">` containing one group per non-empty column (order: needs_you → running → queued → done → failed), each group a `<div className="board-list-group">` with a `<div className="board-list-group-head">` head and sorted `RunListRow` per card
3. `web-client/src/components/RunListRow.tsx` — NEW; `Props { card: CardOut }`; `const signal = tokenSignal(card.token); const aged = isAgedNeedsYou(card.token, card.age_seconds)`; renders `<a className="board-list-row" data-testid={\`board-list-row-${card.id}\`} href={"/workflows/"+card.id}>` with seven cells: (1) `.board-list-token[data-signal={aged?'needs-you':signal}]` containing `.board-list-chip` + token word, (2) `.board-list-project` project_name, (3) `.board-list-repo` repository_slug, (4) `.board-list-branch` branch, (5) `.board-list-step` current_step_label, (6) `.board-list-progress` progressText(progress, kind_label), (7) `.board-list-age[data-signal={aged?'needs-you':undefined}]` ageText(age_seconds)
4. `web-client/src/styles/board.css` — add `.board-toggle { display:flex; align-items:baseline; gap:var(--space-5) }`; `.board-toggle button` type reset (background:none, border:none, padding:0, cursor:pointer) + control-font (same as `.board-filter a`: `font-size:var(--type-control)`, `letter-spacing:var(--type-control-tracking)`, `text-transform:var(--type-control-transform)`) + `color:var(--color-text-tertiary)`; `.board-toggle button[aria-current='true'] { color:var(--color-text); cursor:default }`; `.board-list { display:flex; flex-direction:column; gap:var(--space-8) }`; `.board-list-group { display:flex; flex-direction:column }`; `.board-list-group-head` (label, control-font, secondary colour, border-bottom or padding); `.board-list-row` (grid with 7 columns or flex row, `<a>` link, no underline, padding, gap, `border-bottom:1px solid var(--color-line)`); `.board-list-token`, `.board-list-chip` (7 px chip: `width:7px; height:7px; border-radius:50%; background:currentColor`; token carries `data-signal` colour via same `[data-signal='run']`/`[data-signal='needs-you']`/`[data-signal='failed']` rules as `.run-card-token`); `.board-list-age[data-signal='needs-you'] { color:var(--color-signal-needs-you) }`
5. `web-client/tests/unit/run-list-row.test.tsx` — NEW; using `renderToStaticMarkup` (same pattern as `RunCard` unit tests); assert: (a) `board-list-row-{id}` testid and `href=/workflows/{id}`; (b) all 7 text fields present in output; (c) non-aged RUN card: token cell `data-signal="run"`, no age `data-signal`; (d) BLK card `age_seconds=49*3600`: token cell `data-signal="needs-you"`, age cell `data-signal="needs-you"`; (e) CHK card `age_seconds<172800` (young): token `data-signal="needs-you"` (CHK maps to needs-you signal), no age amber
6. `web-client/tests/e2e/board-list.spec.ts` — NEW; uses same `mockBoard` / `card` patterns as `board.spec.ts`; three test cases: (a) LIST selected: mock board with cards in every column → goto BOARD_URL → wait for `board-card-*` → intercept next requests → click `board-toggle-list` → assert `board-list` visible, groups with heads in correct order, `board-list-row-{id}` contains 7 text fields for a known card, URL contains `?view=list`, no additional board request was intercepted → click BOARD toggle → assert `board-column-queued` visible, `board-list` gone, still no extra request; (b) reload with list: goto `BOARD_URL + &view=list` → wait for `board-list` → assert visible; (c) BLK ≥ 48 h amber: mock with BLK card `age_seconds=49*3600` in needs_you → goto with `?view=list` → assert token cell amber, age cell amber, row-level `unexpectedSignals` empty outside that row

**Acceptance Criteria:**
- Given a stubbed board with Runs in every column, when LIST is selected, then the rows appear grouped with heads in the order Needs you · Running · Queued · Done · Failed, each row has the seven fields (token, project, repository, branch, step label, progress, age), URL carries `?view=list`, and selecting BOARD restores the columns without a new request
- Given a reload with `?view=list`, when the page loads, then the list view is active (`board-list` is present)
- Given a `BLK` Run with `age_seconds ≥ 172800` when listed, then its token cell and age cell carry amber signal and nothing else in the row does

## Spec Change Log

## Review Triage Log

### Iteration 1 — 2026-09-11

**Reviewers:** Blind Hunter · Edge Case Hunter · Verification Gap · Intent Alignment Auditor

| Finding | Classification | Action |
|---------|---------------|--------|
| `.board-list-token` had duplicate `min-width: 3.5rem` in CSS | patch | Already absent in actual file — diff artifact; no action |
| Decorative `.board-list-chip` `<span>` lacks `aria-hidden="true"` | patch | Added `aria-hidden="true"` to `RunListRow.tsx` |
| Stale comment in `index.astro`: "(LIST stays disabled — Epic 8)" | patch | Removed stale reference from module-doc comment |
| URL `?view=` not asserted absent after BOARD restore | patch | Added `expect(page).not.toHaveURL(/view=list/)` to e2e test |
| Sort-order invariant unverified (only one card per group in fixtures) | patch | Added 4th e2e test with two-card running group asserting DOM order |
| `popstate` listener missing (browser back/forward desync) | defer | Not in spec scope; toggle is primary interaction path |
| Group order differs from BoardColumn visual order | reject | Spec explicitly mandates Needs you → Running → Queued → Done → Failed |
| Sort direction debate ("Needs you oldest first") | reject | Spec states ascending `age_seconds` = youngest first; correct |
| BOARD button has no `data-testid` | reject | Spec only requires `board-toggle-list`; role query is stable |
| `listGroups` computed unconditionally on every render | reject | Micro-opt; no observable correctness issue |
| Empty board-list when all groups filter to zero | reject | Impossible: `total === 0` early-return fires before list render |
| `tokenSignal` 'neutral' has no explicit CSS rule | reject | Base `.board-list-token` tertiary fallback is correct and intentional |
| Test fixture IDs are not valid UUIDv7 | reject | Existing codebase pattern (`board.spec.ts` uses same style); acceptable in fixtures |

## Auto Run Result

**Gates:** `make lint` 0 errors · `make test` 7374 passed (6041 backend + 1333 web-client) · `make e2e-ui` board-list.spec.ts 4/4 + board.spec.ts 8/8 (pre-existing run-detail failures unrelated to this story)

**Patches applied:** 4 (aria-hidden on chip, stale comment, URL cleanup assertion, sort-order e2e test)

## Design Notes

**Why the toggle moves into the Board island:** `history.replaceState` (no page reload) is required to satisfy "no second request" on toggle — a plain `<a href>` would remount the island and re-call `fetchBoard`. The static stub in `index.astro` is removed; its scoped CSS rules are replaced by global classes in `board.css` so they reach the React-rendered elements.

**Token chip on row vs card:** `RunCard` uses `.run-card-chip` (7×7 square). `RunListRow` uses `.board-list-chip` (7×7 circle, `border-radius:50%`). The brief does not specify shape; a circle differentiates the list token from the card token at a glance while reusing the same colour mapping.

**No cap in list view:** The `cap={20}` on Done and Failed board columns is a card-layout constraint (a stack of 20+ cards exceeds the viewport). List rows are compact; capping would defeat the purpose of the list view ("twenty or more Runs still read top to bottom like a log").

## Verification

**Commands:**
- `make lint` — expected: zero eslint/tsc errors
- `make test` — expected: all unit tests pass including new `run-list-row.test.tsx`
- `make e2e-ui` — expected: `board-list.spec.ts` passes; `board.spec.ts` unaffected
