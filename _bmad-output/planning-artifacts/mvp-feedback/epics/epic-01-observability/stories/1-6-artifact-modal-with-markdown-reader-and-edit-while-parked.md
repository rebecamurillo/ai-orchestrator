---
title: "Artifact modal with markdown reader and edit-while-parked"
type: 'feature'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 1
followup_review_recommended: true
baseline_revision: 'e71f4bf292b1594c995896750f933ef8137012c1'
context: []
warnings: ['oversized']
deferred:
  - summary: revokeObjectURL called synchronously — may fail before browser fetch in some environments
    evidence: download() calls URL.revokeObjectURL(url) immediately after a.click(); the click is synchronous but the download is async in some browsers
    location: web-client/src/components/run/ArtifactModal.tsx download()
    severity: low
  - summary: isFile(data)=false on a successful fetch produces no error state — modal body stays empty silently
    evidence: useEffect load() returns early if !isFile(data) without setting any error; operator sees a blank modal body
    location: web-client/src/components/run/ArtifactModal.tsx useEffect[runId,path]
    severity: low
  - summary: Download button enabled while content is null — click is a silent no-op during load
    evidence: download() has a content===null guard but the button is not disabled and shows no loading indicator
    location: web-client/src/components/run/ArtifactModal.tsx
    severity: low
  - summary: save() can be invoked concurrently before the first setSaving(true) re-render — two PUTs in-flight
    evidence: rapid double-click before the saving state re-renders could trigger two simultaneous PUT /runs/{id}/files calls
    location: web-client/src/components/run/ArtifactModal.tsx save()
    severity: low
  - summary: Cancelled fetch flag stops state updates but does not abort the HTTP request — superseded fetches consume network
    evidence: cancelled=true prevents setContent but the GET continues; a new path loads while the old network request is still running
    location: web-client/src/components/run/ArtifactModal.tsx useEffect[runId,path]
    severity: low
  - summary: No Escape key handler — modal cannot be dismissed with keyboard
    evidence: No keydown handler in ArtifactModal or parent; CancelModal also lacks one (pre-existing gap, not introduced by this story)
    location: web-client/src/components/run/ArtifactModal.tsx
    severity: low
  - summary: No focus management on mount — focus stays on the artifact tree row that opened the modal
    evidence: useEffect does not move focus to the panel or Close button on mount; CancelModal also lacks this (pre-existing gap)
    location: web-client/src/components/run/ArtifactModal.tsx
    severity: low
  - summary: No :hover/:focus-visible CSS for interactive elements — keyboard and pointer focus states invisible
    evidence: .wf-artifact-modal-close, .wf-artifact-modal-tabs button, Edit button have no :hover/:focus-visible rules
    location: web-client/src/styles/run-detail.css
    severity: low
---

<intent-contract>

## Intent

**Problem:** Artifacts are displayed inline in the run-detail summary column with a flat viewer; the operator cannot read rendered markdown, see YAML syntax-highlighted, download a file, or receive verbatim feedback when a save is rejected.

**Approach:** Replace the inline file-view path in `ArtifactsPanel` with an `ArtifactModal` overlay (the second system modal, after `CancelModal`). The modal provides a `RENDERED · SOURCE · RAW` toggle, a download control, and — when the run is parked without a terminal session — an Edit + Save path through the existing `PUT /runs/{id}/files` with verbatim error display on rejection.

## Boundaries & Constraints

**Always:**
- TDD (AD-18): `artifact-modal.test.ts` exists and fails before `ArtifactModal.tsx` is created; unit tests use shared fakes; no new doubles for ports that already have fakes.
- No backend changes: `PUT /runs/{id}/files` is unchanged; all non-2xx responses are surfaced verbatim in the modal.
- The modal is a fixed-inset backdrop + centered panel following the `CancelModal` structure exactly; never a native `<dialog>`.
- `canEditFile(run, path)` and `isListFile(folder, path)` from `web-client/src/lib/run/artifacts.ts` gate Edit visibility and read-only rendering; `editHint(run.branch)` provides the hint text beneath Save.
- `parseQuestionMarkdown()` from `web-client/src/lib/run/markdown.ts` renders `.md` content in RENDERED mode; CodeMirror read-only (`EditorState.readOnly.of(true)` + `yaml()`) renders `.yaml`/`.yml` content; all other files fall back to `<pre>` in RENDERED mode — no new library installs.
- Download triggers a client-side Blob → object URL → `<a download>` from the fetched content string; no new backend endpoint.
- `run.plan_ref` provides the SHA in the list-file read-only line.
- `schema.d.ts` is never hand-edited (AD-3); no API contract change needed.
- No status writes anywhere (AD-8).
- Backdrop click closes the modal; unsaved editor state is discarded.

**Block If:** Any pre-existing test fails after changes — classify per AGENTS.md rule 1 before touching anything.

**Never:** Native `<dialog>` element. New tab for download. New backend endpoint. New syntax-highlighting library not already in `web-client/package.json`. `dangerouslySetInnerHTML` for markdown rendering.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Non-list file, needs_you, no terminal | run.status='needs_you', run.terminal_session=false, non-list path | Modal opens; RENDERED tab active; Edit button present (`data-testid="wf-artifacts-edit"`) | No error |
| Non-list file, run not parked or terminal active | run.status != 'needs_you' OR run.terminal_session=true | Modal opens; RENDERED tab active; no Edit button | No error |
| Markdown file, RENDERED tab | path ends `.md` | Blocks rendered via parseQuestionMarkdown() (headings, lists, code, paragraphs) | No error |
| YAML file, RENDERED tab | path ends `.yaml` or `.yml` | CodeMirror read-only view with yaml() extension mounted in ref div | No error |
| Other file, RENDERED tab | any other extension | `<pre>{content}</pre>` | No error |
| SOURCE tab clicked | any file | `<pre>{content}</pre>` | No error |
| RAW tab clicked | any file | `<pre>{content}</pre>` | No error |
| Download clicked | content fetched | Blob(content, text/plain) → objectURL → `<a download="{basename}">` click → revokeObjectURL | No error |
| List file (stories.yaml/epics.yaml) | isListFile(folder, path)=true | Modal opens; read-only line "planned at {sha} — start a new run to change the list" visible; no Edit button | No error |
| Edit mode, save succeeds | PUT /runs/{id}/files returns 2xx | editing=false (returns to reader); onSaved() callback invoked (triggers tree re-fetch in ArtifactsPanel) | No error |
| Edit mode, save rejected | PUT returns non-2xx | error detail displayed verbatim in `.wf-artifact-modal-error`; editor buffer unchanged; Save stays available | No silent failure |
| Backdrop clicked | any modal state | Modal unmounts; ArtifactsPanel.selectedPath → null; unsaved buffer discarded | No error |

</intent-contract>

## Code Map

- `web-client/src/components/run/ArtifactsPanel.tsx` — currently owns inline FileViewer/FileEditor state (`fileContent`, `editing`, `saveError`); add `selectedPath: string | null` state (initially null); on tree-row click set `selectedPath`; render `<ArtifactModal path={selectedPath} run={run} folder={folder} runId={runId} onClose={() => setSelectedPath(null)} onSaved={() => { setSelectedPath(null); /* then re-fetch tree */ }} />` when selectedPath non-null; remove inline FileViewer/FileEditor and their associated state
- `web-client/src/components/run/ArtifactModal.tsx` — new; props `{ runId: string; path: string; run: RunDetailSummaryOut; folder: string; onClose: () => void; onSaved?: () => void }`; fetches content via `GET /api/v1/runs/{runId}/files?path={encodeURIComponent(path)}` on mount; internal state: `tab: 'rendered'|'source'|'raw'` (default `'rendered'`), `editing: boolean`, `saveError: string | null`, `editorContent: string`; modal structure: outer div `.wf-artifact-modal` (fixed inset flex center), backdrop div `.wf-artifact-modal-backdrop` (onClick=onClose), panel div `.wf-artifact-modal-panel` (`data-testid="wf-artifact-modal"`); close ×; toggle row `RENDERED · SOURCE · RAW` (`data-testid="wf-artifact-modal-tab-rendered"` etc.); download button; RENDERED view per file type; SOURCE/RAW view as `<pre>`; Edit button (`data-testid="wf-artifacts-edit"`) when `canEditFile(run, path)`; FileEditor in edit mode with Save + hint + error zone; read-only line when `isListFile(folder, path)`
- `web-client/src/lib/run/artifacts.ts` — read-only; confirmed: `canEditFile(run, path): boolean` at line 87-89, `editHint(branch: string): string` at line 52; also check for `isListFile(folder, path)` and the read-only line string (`planned at {run.plan_ref} — start a new run to change the list`) — if not exported from here, they live in `FileViewer.tsx` and must be extracted or inlined (do not duplicate logic); import/reuse rather than re-derive
- `web-client/src/lib/run/markdown.ts` — read-only; `parseQuestionMarkdown(content: string): MdBlock[]`; used in ArtifactModal RENDERED view for `.md` files
- `web-client/src/components/run/FileEditor.tsx` — read-only; CodeMirror-backed editor component; reuse in ArtifactModal edit mode; inspect props to confirm `value`/`onChange`/`language` interface
- `web-client/src/styles/run-detail.css:501` — existing cancel modal pattern (`.wf-cancel-backdrop`, `.wf-cancel-modal`, `.wf-cancel-modal-panel`); new artifact modal classes follow same structure; add: `.wf-artifact-modal` (position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; z-index: above cancel modal), `.wf-artifact-modal-backdrop` (position: fixed; inset: 0; background: var(--color-bg); opacity: 0.8), `.wf-artifact-modal-panel` (position: relative; max-width: 800px; width: calc(100% - 2 × var(--space-10)); max-height: 80vh; overflow-y: auto; background: var(--color-surface-raised); border: 1px solid var(--color-line-strong)), `.wf-artifact-modal-tabs` (toggle row), `.wf-artifact-modal-body` (scrollable content area), `.wf-artifact-modal-error` (white-space: pre-wrap; color: var(--color-signal-failed))
- `web-client/src/islands/RunDetail.tsx:250` — read-only reference; passes `runId`, `run={detail.run}`, `folder={detail.header.meta.folder}` to ArtifactsPanel; unchanged
- `backend-api/src/orchestrator/api/routers/run_files.py` — read-only; `PUT /runs/{run_id}/files` body: `RunFileIn {path, content}`; success: `RunFileEntryOut`; 409 for list files or not-parked-without-terminal; 403/422 for path violations; error body is problem+json with `detail` field containing git output on commit failure
- `web-client/src/api/schema.d.ts` — read-only; no contract change needed

## Tasks & Acceptance

**Execution:**
- `web-client/tests/unit/artifact-modal.test.ts` -- WRITE FIRST (TDD): `import ArtifactModal from '../../src/components/run/ArtifactModal'`; assert `typeof ArtifactModal === 'function'`; must fail (import error) before ArtifactModal.tsx exists
- `web-client/src/components/run/ArtifactModal.tsx` -- implement modal: RENDERED/SOURCE/RAW toggle, download (Blob → objectURL), Edit+Save path reusing FileEditor, read-only list-file line, save-error verbatim display; import canEditFile/isListFile/editHint/readOnlyLine from artifacts.ts; import parseQuestionMarkdown from markdown.ts
- `web-client/src/components/run/ArtifactsPanel.tsx` -- replace inline FileViewer/FileEditor with `selectedPath` state and `<ArtifactModal>` overlay; wire `onSaved` to re-fetch tree
- `web-client/src/styles/run-detail.css` -- add `.wf-artifact-modal`, `.wf-artifact-modal-backdrop`, `.wf-artifact-modal-panel`, `.wf-artifact-modal-tabs`, `.wf-artifact-modal-body`, `.wf-artifact-modal-error` classes

**Acceptance Criteria:**
- Given an artifact file row is clicked in the artifacts tree, when clicked, then `data-testid="wf-artifact-modal"` appears as a fixed-position overlay (not inline in the column) and RENDERED tab is active by default
- Given the modal opens for a `.md` file in RENDERED mode, when the content has headings and lists, then rendered HTML-equivalent blocks appear (not raw source markdown)
- Given the modal opens for a `.yaml` file in RENDERED mode, when the content is shown, then a CodeMirror read-only view with YAML syntax is rendered
- Given the download button is clicked, when clicked, then a file download is triggered with filename equal to the last path segment and content equal to the raw fetched file text
- Given run.status='needs_you' and run.terminal_session=false and path is not stories.yaml or epics.yaml, when the modal opens, then `data-testid="wf-artifacts-edit"` is present
- Given run.status != 'needs_you' or run.terminal_session=true, when the modal opens, then `data-testid="wf-artifacts-edit"` is absent
- Given Edit is clicked and Save is submitted with valid content, when PUT /runs/{id}/files returns 2xx, then the modal returns to reader view and the artifact tree in ArtifactsPanel is re-fetched
- Given Edit is clicked and Save is submitted, when PUT /runs/{id}/files returns non-2xx, then the response detail is displayed verbatim in the modal error zone and the editor content is unchanged
- Given the path is stories.yaml or epics.yaml, when the modal opens, then "planned at {sha} — start a new run to change the list" is visible and `data-testid="wf-artifacts-edit"` is absent
- Given the modal backdrop is clicked, when clicked, then the modal unmounts and no `data-testid="wf-artifact-modal"` is present in the DOM

## Design Notes

**Modal structure mirrors CancelModal exactly:** outer div (fixed inset, flex center), backdrop div (fixed inset, opacity 0.8, onClick=onClose), panel div (relative, raised surface, border). The panel is wider (max-width 800px vs 420px) to accommodate file content. z-index must sit above the standard layer; check `tokens.css` for the z-index token.

**RENDERED tab for YAML/code:** In a `useEffect`, mount an `EditorView` with `EditorState.create({ doc: content, extensions: [yaml(), EditorState.readOnly.of(true), EditorView.lineWrapping] })` into a `divRef`. Unmount on tab change or component unmount. This reuses the same `@codemirror/state`, `@codemirror/view`, and `@codemirror/lang-yaml` packages already used by `FileEditor.tsx`; no new installs.

**Save error extraction:** `const body = await response.json().catch(() => null); setSaveError(body?.detail ?? await response.text());` — covers both problem+json `detail` strings and plain text error bodies. Render with `white-space: pre-wrap` so git output line breaks are preserved.

**Download pattern:** `const blob = new Blob([content], { type: 'text/plain' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = path.split('/').at(-1) ?? 'file'; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);`

**ArtifactsPanel onSaved wiring:** ArtifactsPanel already has internal state to control re-fetch (e.g., a `refreshKey` counter that triggers the tree-fetch effect). Increment it in the `onSaved` handler. The modal also calls `onSaved` to signal a successful write; ArtifactsPanel does not close the modal on save — the modal returns to reader view internally.

## Verification

**Commands:**
- `make lint` -- expected: exit 0 (eslint, prettier, tsc, check-test-pairs all pass)
- `make test` -- expected: all tests green including `artifact-modal.test.ts`
- `make e2e-ui` -- expected: exit 0 (Playwright; requires running compose stack — not run in this session; existing `run-detail-artifacts.spec.ts` tests that reference `wf-file-viewer`, `wf-artifacts-edit`, and `artifacts-readonly` are maintained by backwards-compatible testids added to ArtifactModal)

## Spec Change Log

- 2026-09-16: Renamed `data-testid="wf-artifact-modal-edit"` → `data-testid="wf-artifacts-edit"` throughout I/O matrix, Acceptance Criteria, and Code Map to maintain backwards compatibility with existing e2e tests in `run-detail-artifacts.spec.ts` that use the old testid.

## Review Triage Log

### 2026-09-16 — Review pass (iteration 1)

- intent_gap: 0
- bad_spec: 0
- patch: 6 (high 1, medium 1, low 4)
- defer: 8 (high 0, medium 0, low 8)
- reject: 11
- addressed_findings:
  - `[high]` `[patch]` FileViewer e2e testid regression — `run-detail-artifacts.spec.ts` references `wf-file-viewer`, `wf-artifacts-edit`, and `artifacts-readonly` testids from the old inline FileViewer; these were missing from ArtifactModal. Fix: added `data-testid="wf-file-viewer"` wrapper div inside the modal panel, renamed Edit button testid from `wf-artifact-modal-edit` to `wf-artifacts-edit`, added `data-testid="artifacts-readonly"` to the read-only `<p>`. Unit test and spec AC updated to match.
  - `[medium]` `[patch]` Hint text (`editHint(branch)`) not rendered in edit mode — the intent explicitly states "with the hint saying so" and `editHint()` is cited in Boundaries, but the implementation never imported or called it. Fix: imported `editHint` from `artifacts.ts` and rendered `<p className="wf-artifact-modal-hint">{editHint(run.branch)}</p>` below `<FileEditor>` in the editing block; added `.wf-artifact-modal-hint` CSS rule.
  - `[low]` `[patch]` `saveError` not cleared when Edit mode re-entered — a stale error from a prior failed save reappeared on the second Edit click. Fix: added `setSaveError(null)` before `setEditing(true)` in the Edit button's onClick handler.
  - `[low]` `[patch]` CSS Download button inherited tab toggle styling — `.wf-artifact-modal-tabs button` matched the Download button, giving it secondary color and meta font-size. Fix: added `.wf-artifact-modal-tabs .wf-artifact-modal-download` override rule with `color: var(--color-text)` and `font-size: var(--type-body)`.
  - `[low]` `[patch]` `font-family: var(--font-mono)` applied to the markdown rendered view div — prose content (headings, paragraphs) rendered in monospace. Fix: added `div.wf-artifact-modal-body { font-family: inherit; }` override rule.
  - `[low]` `[patch]` `aria-labelledby` missing on the dialog panel — screen readers cannot derive an accessible name from the path span. Fix: added `aria-labelledby="wf-artifact-modal-title"` on the panel div and `id="wf-artifact-modal-title"` on the path span.

## Auto Run Result

**Status:** done

**Summary:** Implemented `ArtifactModal` (FR-19, UX-DR9) as the second system modal — a fixed-inset, backdrop+panel overlay replacing the inline FileViewer/FileEditor in `ArtifactsPanel`. The modal provides RENDERED/SOURCE/RAW toggle, download (Blob→objectURL), CodeMirror read-only for YAML, `parseQuestionMarkdown` for .md files, Edit+Save through `PUT /runs/{id}/files`, verbatim error display with `white-space: pre-wrap`, hint text via `editHint(branch)` below the Save button, and read-only lines for list files. Six review patches applied; eight items deferred.

**Files changed:**
- `web-client/tests/unit/artifact-modal.test.ts` — new; TDD pair (14 tests, all green)
- `web-client/src/components/run/ArtifactModal.tsx` — new; the modal component with all required functionality
- `web-client/src/components/run/ArtifactsPanel.tsx` — `selectedPath: string | null` state replaces inline FileViewer/FileEditor; `<ArtifactModal>` overlay rendered when non-null; `onSaved` triggers tree re-fetch
- `web-client/src/styles/run-detail.css` — artifact modal CSS classes added; review patches applied (download override, div.body font-family, hint rule)
- `_bmad-output/.../stories/1-6-artifact-modal-with-markdown-reader-and-edit-while-parked.md` — this spec file

**Review findings:** 6 patches applied (high 1, medium 1, low 4), 8 deferred (all low), 11 rejected.

**Follow-up review recommended:** `true` — patch score = 3×1 + 2×1 + 1×4 = 9 ≥ 5.

**Verification:**
- `make lint`: exit 0 (0 TS errors, 0 eslint errors, prettier clean, check-test-pairs clean)
- `make test`: 6372 backend + 1419 frontend passed, 0 failures
- `make e2e-ui`: not run (compose stack unavailable); backwards-compatible testids (`wf-file-viewer`, `wf-artifacts-edit`, `artifacts-readonly`) added to ArtifactModal to maintain existing e2e test coverage

**Residual risks:** 8 low-severity deferred items (revokeObjectURL timing, silent empty modal on isFile=false, silent download no-op during load, save() concurrent race, fetch no-abort, Escape key, focus management, hover/focus-visible CSS).
