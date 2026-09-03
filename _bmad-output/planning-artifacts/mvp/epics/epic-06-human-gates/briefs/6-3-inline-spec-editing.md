---
story: "6-3"
epic: 6
title: Inline spec editing while parked
requirements: [FR-19 (inline edit), FR-23 (artifacts tree), FR-31 (never attributed), NFR-8, UX-DR9, UX-DR17, UX-DR18, AR-18]
binds: [AD-13, AD-14, AD-17]
---

# Story 6.3 — Inline spec editing while parked

As the Operator,
I want to fix `SPEC.md` or a story file from the Run detail while the Run waits for me, with every save committed and named in the record,
So that a gap in the spec is closed where I read it, and the next attempt starts from my edit without it ever counting as the agent's.

## Scope

**In:** `GET /runs/{id}/files` (tree) and `PUT /runs/{id}/files`, the artifacts tree with viewer and editor in `RunDetail`, the read-only rule for list files, the gate record entry, tests.
**Out:** changed-since-last-opened chips (Epic 8).

## Binding rules (inlined)

- **Endpoints (AD-13).** `GET /runs/{id}/files` → `{root: spec_folder (or initiative folder), entries: [{path, kind: file | dir, size, mtime}]}` recursive over the spec folder (and, for an initiative Run, the initiative folder); `GET /runs/{id}/files?path=` (6.2) returns content; `PUT /runs/{id}/files {path, content}` → allowed only when `run.status == needs_you` and `not terminal_session` (else 409 `editing requires a parked run without a terminal session`), path inside the spec or initiative folder (else 403), never `stories.yaml` or `epics.yaml` (409 `planned at {plan_ref} — start a new run to change the list`), traversal rejected (422). Effect: `Workspace.write` then `Git.commit(cwd, "spec: operator edit (orchestrator)", [path])` (author `operator <operator@local>`), gate record `spec_edit` (actor `operator`, text `edited {path}`, `path` = the park row); 200 with the new entry. These are the only worktree writes outside an engine step besides cancel.
- **Never attributed (AD-17).** The commit lands between attempts, outside any agent range, so the protected-path check never sees it (already guaranteed by 5.6; add a test).
- **Artifacts (UX-DR9).** Right column **ARTIFACTS**: the tree at spec-folder scope (`DESIGN.md` artifact tree: 14px indent, guide rules, filename + right-aligned mtime); clicking a file opens the viewer (Markdown rendered minimally, YAML as text); while the Run is parked and no terminal session is in progress an *Edit* control turns the viewer into a plain textarea editor (Markdown, YAML) with *Save* and the hint `saved as commit "spec: operator edit (orchestrator)" on {branch}`; `stories.yaml` and `epics.yaml` open read-only with the line `planned at {sha} — start a new run to change the list`; other statuses show the tree and viewer only.
- **Signal rule:** nothing coloured in the tree except (Epic 8) the accent chip.
- **Test-ids:** `artifacts-tree`, `artifacts-file-<path>`, `wf-editor`, `wf-editor-save`, `wf-editor-hint`, `artifacts-readonly`.

## Acceptance criteria

**Given** a parked Run
**When** `PUT /runs/{id}/files {path: "specs/x/SPEC.md", content}` is called
**Then** the worktree file is written, a commit `spec: operator edit (orchestrator)` with only that path exists on the branch, the gate record has `spec_edit · edited specs/x/SPEC.md`, and the response carries the new mtime.

**Given** `path: "specs/x/stories.yaml"`
**When** put
**Then** 409 with `planned at {sha} — start a new run to change the list` and no write.

**Given** a `running` Run, or a parked Run with `terminal_session`
**When** put
**Then** 409 and no write.

**Given** an operator edit followed by the next agent attempt
**When** the protected-path check runs on that attempt
**Then** the operator's change to `SPEC.md` is not a hit (unit test over the fakes with the SHAs).

**Given** the artifacts tree on a parked detail
**When** a Markdown file is opened and edited
**Then** *Save* posts the PUT, the hint shows the commit line, and the tree's mtime updates; `stories.yaml` opens read-only with the planned line.

## Implementation notes

- `application/use_cases/files.py` (`list_files`, `read_file`, `write_file`) over `Workspace` and `Git`; router in `runs.py`.
- `src/components/run/ArtifactsTree.tsx`, `FileViewer.tsx`, `FileEditor.tsx`; Markdown renderer from 5.10.
- Gate record event `spec_edit` added to the event list (4.5 constant).

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-19 (inline edit paragraph), FR-23. Spine AD-13 (`PUT /runs/{id}/files` rules), AD-17. `EXPERIENCE-v1.md` §2.2 (artifacts). `DESIGN.md` artifact tree.
