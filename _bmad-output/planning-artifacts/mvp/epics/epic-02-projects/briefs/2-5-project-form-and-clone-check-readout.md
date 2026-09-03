---
story: "2-5"
epic: 2
title: New project and edit form with the live Clone check readout
requirements: [FR-2, FR-3, FR-4, NFR-8, UX-DR13, UX-DR18, AR-25]
binds: [AD-1, AD-3, AD-5]
---

# Story 2.5 — New project and edit form with the live Clone check readout

As the Operator,
I want one form for a Project and its Repositories that keeps every value when something is wrong and shows the Clone check result per repository the moment I save,
So that configuring a project and finding out the token is wrong happen in the same minute (UJ-1).

## Scope

**In:** `src/pages/projects/new.astro` and `src/pages/projects/[id]/edit.astro`, the `ProjectForm` React island (dynamic rows for env vars and repositories), the `saveProject` Action (create or update, then read back with clone-check results), the **Clone check** readout column, Vitest for the island, Playwright for the flow.
**Out:** *Initialise repository* (Epic 4).

## Binding rules (inlined)

- **Form fields (UX-DR13).** Name; context (textarea); context file paths (one per line); env vars (rows `NAME` / value; existing vars show `••••1234` and a *replace* affordance that reveals an empty value input; leaving it untouched keeps the stored value); `log_prompt_content` switch with the secondary line `on: prompt and tool content, including source code, is sent to Langfuse for this project`; repositories (rows: URL, default branch, package manager select, `test_globs` pre-filled with `tests/**`, `**/*.test.*`, `**/*.spec.*` and editable, `install_command`, `quality_gate_command`, `unit_test_command`). No token field; one secondary line `credentials are instance settings (.env)`.
- **Errors (conventions "Form errors").** The Action returns an `ActionError` carrying the problem body; the page re-renders with every submitted value kept, `detail` printed verbatim above the form, and each `errors[]` entry printed beside the field named by its `path` (e.g. `repositories[1].default_branch`). No toast, no redirect on error.
- **Save flow.** Create: `POST /projects` then `POST /projects/{id}/repositories` per row; update: `PUT /projects/{id}`, `PUT /repositories/{id}` for existing rows, `POST` for new rows. Then `GET /projects/{id}` and render the readout; the browser navigates to `/projects/{id}/edit?saved=1` so a reload keeps the readout. The backend runs the clone checks as part of each save (2.3), so the readout is the stored result.
- **Readout (UX-DR13).** Right column titled **CLONE CHECK**, one block per repository: its slug, then the four lines `ls-remote`, `clone` (`{bytes} · {seconds}s`), `default branch`, `method version` each with `ok` / `failed` as words; a failed repository prints the git output verbatim in an inset command block and the `hint` line; the block ends with `failed · new runs blocked` or `ok`; a `missing` or `outdated` method adds the line `run Initialise repository after save`; a repository without a quality command adds `verify step will be skipped`. Before the first save the column reads `save to run the clone check`.
- **Signal rule.** Only a failed line's status word is red; nothing else is coloured.
- **Island rules (web-client AGENTS.md).** `client:load`, ≤ 5 props (`initial`, `errors`, `mode`), no `fetch` inside the island (submission is a form post to the Action), no inline styles, serialisable props.
- **Test-ids:** `project-form`, `project-form-name`, `project-form-context`, `project-form-env-add`, `project-form-env-<n>-name`, `project-form-repo-add`, `repo-form-<n>-url`, `repo-form-<n>-default-branch`, `repo-form-<n>-quality`, `project-form-save`, `project-form-error`, `projects-clone-check-<slug>`.

## Acceptance criteria

**Given** `/projects/new`
**When** I add two repositories, one env var, and save
**Then** the Project is created with both repositories, the page shows the **CLONE CHECK** readout for each with its four lines, and the URL is `/projects/{id}/edit?saved=1`.

**Given** a submission with an empty default branch on the second repository
**When** saved
**Then** the page re-renders with every value kept and the reason beside `repo-form-1-default-branch`; nothing is created.

**Given** a repository the token cannot reach
**When** saved
**Then** its readout block shows `ls-remote failed`, the verbatim git output in an inset block, the hint line, and `failed · new runs blocked`; the Project is saved anyway.

**Given** the edit page of a Project with a stored env var
**When** I save without touching it
**Then** the stored value is unchanged (the Action sends the entry without `value`); after *replace* and a new value it is updated and its mask changes.

**Given** a repository without `quality_gate_command`
**When** saved
**Then** its readout block ends with `verify step will be skipped`.

**Given** the form
**When** inspected
**Then** it has no token or gateway key field and shows the line `credentials are instance settings (.env)`.

## Implementation notes

- `src/islands/ProjectForm.tsx` with local state for rows; hidden inputs serialise rows as `repositories[n].field` and `env_vars[n].name|value`; the Action parses with `zod` `[ASSUMPTION: zod via Astro Actions' built-in input schema]`.
- `src/actions/projects.ts::save` orchestrates the API calls through `src/api/server.ts` and maps problem bodies to `ActionError` with the `path` list.
- `src/components/projects/CloneCheckReadout.astro` renders from the Project read model.
- Vitest: row add/remove, mask/replace behaviour, error placement; Playwright `tests/e2e/project-form.spec.ts` with stubbed API for the six criteria.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §3.1 New project, §Operator workflow step 2, §Voice. PRD FR-2..FR-4, UJ-1. Spine conventions "Form errors". `web-client/AGENTS.md`.
