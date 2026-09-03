---
story: "2-4"
epic: 2
title: Projects list and detail screens
requirements: [FR-2, FR-3, FR-4, NFR-6, NFR-8, UX-DR12, UX-DR5, UX-DR17, UX-DR18]
binds: [AD-1, AD-3]
---

# Story 2.4 — Projects list and detail screens

As the Operator,
I want to open Projects and see, for each Project, its context, its repositories with their method version and clone-check state, and its settings,
So that I can tell at a glance which repository is ready for a Run and which needs my attention.

## Scope

**In:** `src/pages/projects/index.astro` (two panes: list + detail of the selected Project via `?id=`), `src/pages/projects/[id].astro` (redirects to the two-pane route with the id) `[ASSUMPTION: one two-pane page rather than two routes]`, static Astro components for the repositories table and settings kv, the *re-run check* action (Astro Action calling `POST /repositories/{id}/clone-check`), Playwright tests with stubbed API.
**Out:** the form (2.5); *Initialise repository* (Epic 4), *Export trajectories* (Epic 7), monthly spend (Epic 8) — render their places as absent, not disabled.

## Binding rules (inlined)

- **Data (AD-1, AD-3).** Pages fetch server-side through `src/api/server.ts` using the generated types: `GET /api/v1/projects` and `GET /api/v1/projects/{id}`; the UI aggregates nothing across endpoints.
- **Layout (UX-DR12).** Left pane: record rows (name · repositories count · runs count `0` · one amber or red count only if any, none for now). Right pane, in order: title + meta line (`created {date}` · `log_prompt_content on|off`); section **CONTEXT** (context text, then the hint line `written to project-context.md in the spec folder before every story`); section **REPOSITORIES**: dense table `repository · default · method · quality_gate_command · test_globs · clone check · status`; section **SETTINGS** kv (`env vars` → `{n} · {NAME ••••1234, …}`; `GitHub token and gateway key` → `instance settings`); section **RUNS ON THIS PROJECT** with the readout `no runs yet` (Epic 4 fills it). Bar: surface title `PROJECTS`, count, *+ New project* linking to `/projects/new`, and on the detail *Edit* linking to `/projects/{id}/edit`.
- **Cells (UX-DR12, UX-DR17).** `method`: the version string, `missing`, or `outdated`; `quality_gate_command`: the command or `— none declared`; `clone check`: `ok · {seconds}s` or `failed · new runs blocked`; `status`: `verify step will be skipped` when `verify_skipped`, else `ready`; a `failed` row shows the *re-run check* control and, on hover or below the row, the verbatim output in an inset command block with the `hint` line. `pending` reads `pending · save to check`.
- **Signal rule (UX-DR2).** The only coloured element in a repository row is the clone-check cell when `failed` (red text, no fill). When no row is failed, the screen has no amber or red pixel.
- **Empty states.** No Projects: `NO PROJECTS` + `register a project to start` + link. A Project without repositories: the table shows `no repositories · edit the project to add one`.
- **Voice (NFR-8):** the strings above, verbatim.
- **Test-ids (UX-DR18):** `projects-list`, `projects-row-<slug>`, `projects-detail`, `projects-repo-<slug>`, `projects-recheck-<slug>`, `projects-new`, `projects-edit`.

## Acceptance criteria

**Given** two Projects, one selected by `?id=`
**When** `/projects` renders
**Then** the list shows both rows, the selected row is marked, and the detail shows title, meta line, context, repositories table, settings kv, and the runs readout, in that order.

**Given** a Repository with `clone_check.status: failed`
**When** rendered
**Then** its clone-check cell reads `failed · new runs blocked` in the red token colour, the verbatim output and the hint are shown in an inset block, and *re-run check* is present; clicking it calls the API and re-renders the row with the new result.

**Given** a Repository without `quality_gate_command`
**When** rendered
**Then** the command cell reads `— none declared` and the status cell reads `verify step will be skipped`.

**Given** a Repository with `bmad_version: missing`
**When** rendered
**Then** the method cell reads `missing` (no action yet).

**Given** no Projects
**When** `/projects` renders
**Then** it shows `NO PROJECTS` with the link to `/projects/new`.

**Given** a page with every repository `ok`
**When** the Playwright colour scan runs
**Then** no element uses the amber or red token.

## Implementation notes

- Components: `src/components/projects/RepositoriesTable.astro`, `ProjectSettings.astro`, `ProjectListRow.astro`; reuse `DenseTable`, `KvTable`, `SectionHead`, `EmptyState`, `CommandBlock` from Epic 1.
- Action `src/actions/repositories.ts::recheck` returns the updated Repository; the page re-renders (no island needed).
- Playwright `tests/e2e/projects.spec.ts` with route stubs for the two endpoints and the action.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §3 Projects, §Voice, §Test-ids. PRD FR-2..FR-4, FR-30 (method cell), NFR-6, NFR-8. `DESIGN.md` components (record row, dense table, kv table, command block).
