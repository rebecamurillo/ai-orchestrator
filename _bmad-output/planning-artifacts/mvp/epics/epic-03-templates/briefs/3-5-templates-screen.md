---
story: "3-5"
epic: 3
title: Templates screen with versions list, editor, validate, and save
requirements: [FR-5, FR-6, NFR-6, NFR-8, UX-DR15, UX-DR18, AR-25]
binds: [AD-1, AD-3, AD-15]
---

# Story 3.5 — Templates screen with versions list, editor, validate, and save

As the Operator,
I want to open any Template version, read and edit its YAML in the browser, see every validation error by line, and save my edit as the next version,
So that the dev loop is something I can read and change without touching the repository, and never something I can corrupt in place.

## Scope

**In:** `src/pages/templates/index.astro` (redirects to the latest version of the first Template), `src/pages/templates/[name]/[version].astro`, the `TemplateEditor` island (CodeMirror 6 with `lang-yaml`), the versions list, the inputs table, the validation readout, Validate and Save actions, tests.
**Out:** the diagram (3.6; this story leaves a `templates-diagram` slot rendering `diagram arrives with the next story`), freeze-on-pin hints beyond the copy line.

## Binding rules (inlined)

- **Layout (UX-DR15).** Three columns: **VERSIONS** list (record rows: `{name} v{n}` · `pinned by {pinned_by} runs` · `called by {name}@{v}, …` when any · the marker `read-only` on every version, since versions are immutable); **YAML** editor with line numbers; **DIAGRAM** slot + **INPUTS BOUND AT START** table (`input · type · required · default`). Bar: surface title `TEMPLATES`, the validation readout (`valid · {hh:mm:ss}` or `{n} errors`), *Validate*, *Save as v{n+1}* (primary). Under the editor: the error list `line {n} · {reason}` and, for ungated steps, `unvalidated · {path}` lines. The hint under the versions list: `a saved version never changes; a version pinned by a run, directly or as a callee, is frozen`.
- **Editor.** CodeMirror 6 (`@codemirror/state` 6.7.2, `@codemirror/view` 6.43.10, `@codemirror/lang-yaml` 6.1.3) on the instrument-dark tokens: keys in `text-secondary`, values in `text`, `uses:` kinds and `run:` commands in `accent`; the selected step (cursor inside its mapping) is highlighted with `surface-raised`; no soft wrap; the editor only edits text.
- **Validate.** Calls `POST /templates/{name}/validate` through the proxy; renders errors; on zero errors updates the readout with the time and emits the parsed OK state to the diagram slot (3.6 consumes it). Runs on *Validate* and 800 ms after the last keystroke `[ASSUMPTION: debounced auto-validate]`.
- **Save.** `POST /templates/{name}/versions` with the editor text; on 201 navigate to `/templates/{name}/{n+1}`; on 422 print the errors under the editor and keep the text; the YAML's `version` field must already read `n+1` — the screen pre-fills it when the Operator opens a version by replacing `version: n` with `version: n+1` in a banner line `editing as v{n+1}` `[ASSUMPTION: the editor shows the stored YAML unchanged and the Save action rewrites the version line before posting]`.
- **Signal rule.** The only coloured element is the red error count in the bar when errors exist; `unvalidated` and `read-only` are plain words.
- **Voice (NFR-8):** strings above verbatim; no "successfully saved".
- **Island rules:** `client:load` for the editor only; props `{name, version, yaml, inputs, errorsInitial}`; no `fetch` in the island — it calls `src/api/client.ts` (allowed: it is the browser client), never `server.ts`.
- **Test-ids:** `templates-versions`, `templates-version-<name>-<v>`, `templates-editor`, `templates-validate`, `templates-save`, `templates-errors`, `templates-error-<n>`, `templates-readout`, `templates-inputs`, `templates-diagram`.

## Acceptance criteria

**Given** `/templates`
**When** opened
**Then** it redirects to the latest version of the first Template by name, the versions list shows every version of every Template with `pinned by 0 runs` and the callers of callees (`story v1 · called by epic@1`), and the editor shows the YAML with line numbers.

**Given** the editor content with `parallel: 2` added and a `gate` removed
**When** *Validate* is clicked
**Then** the bar reads `1 errors` in red, the list shows `line {n} · parallel is reserved` and `unvalidated · {path}`, and the text is untouched.

**Given** valid edited content
**When** *Save as v2* is clicked
**Then** the browser navigates to `/templates/{name}/2`, the versions list shows v1 and v2, and v1's YAML is unchanged.

**Given** the version page
**When** rendered
**Then** the inputs table lists every input with type, required, and default.

**Given** the editor
**When** the cursor is inside a step mapping
**Then** that step's lines are highlighted; `uses:` values render in the accent colour.

## Implementation notes

- `src/islands/TemplateEditor.tsx` (CodeMirror setup in `src/lib/editor/yamlEditor.ts`, unit-tested for the highlight and version-rewrite helpers); `src/components/templates/VersionsList.astro`, `InputsTable.astro`, `ValidationReadout` inside the island.
- Actions: none needed; the island posts through `client.ts`; the page loads data server-side with `server.ts`.
- Playwright `tests/e2e/templates.spec.ts` with stubbed endpoints for the five criteria; Vitest for helpers and the island's error rendering.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §5 Templates, §Voice. PRD FR-5, FR-6, NFR-6, NFR-8. `DESIGN.md` (record row, command block colours for the editor palette). `web-client/AGENTS.md`.
