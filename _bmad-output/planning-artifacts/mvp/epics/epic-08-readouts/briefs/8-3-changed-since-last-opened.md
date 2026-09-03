---
story: "8-3"
epic: 8
title: Changed-since-last-opened marks
requirements: [FR-23 (changed marks), UX-DR5 (artifact tree), UX-DR9]
binds: [AD-1, AD-14]
---

# Story 8.3 — Changed-since-last-opened marks

As the Operator,
I want the artifacts tree to show which files changed since I last opened this Run,
So that coming back after two days I go straight to what moved.

## Scope

**In:** `run.last_opened_at` updated on `GET /runs/{id}` reads from the UI (not from polling — see rule), `changed: bool` per entry in `GET /runs/{id}/files`, the accent chip and promotion in the artifacts tree, tests.
**Out:** diffs (6.6 has per-file diffs).

## Binding rules (inlined)

- **Opening vs polling.** The detail's first request after navigation sends `?opened=1`; the server records `run.last_opened_before = run.last_opened_at` and sets `last_opened_at = now`; poll requests omit it and change nothing. The tree compares file mtimes (from `Workspace.tree`) with `last_opened_before`, so the marks stay visible for the whole visit and reset on the next opening.
- **Tree (UX-DR5, `DESIGN.md`).** A changed file is promoted from `text-secondary` to `text` and carries a single 7px accent chip before its name; nothing else is coloured; a changed directory is not marked (only files).
- **Read model.** `GET /runs/{id}/files` entries gain `changed`; the detail's `run.last_opened_at` is exposed.

## Acceptance criteria

**Given** a Run last opened at T and two files modified after T
**When** the detail is opened (`?opened=1`) and the tree is read
**Then** those two entries have `changed: true`, the others `false`, `last_opened_at` is now, and the tree shows the accent chip and promotion on the two files.

**Given** subsequent polls during the same visit
**When** the tree is re-read
**Then** the marks are unchanged.

**Given** a second opening later with no new changes
**When** the tree is read
**Then** no entry is `changed`.

## Implementation notes

- Migration `0010_last_opened_before.py`; `Workspace.tree` returns mtimes (from 4.7).
- `ArtifactsTree` (6.3) renders the chip from `changed`.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-23 (file tree marks). `DESIGN.md` artifact tree. `EXPERIENCE-v1.md` §2.2 (artifacts chips).
