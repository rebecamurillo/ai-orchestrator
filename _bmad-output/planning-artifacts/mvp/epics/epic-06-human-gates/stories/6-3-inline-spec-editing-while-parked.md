---
title: 'Inline spec editing while parked'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      Binary or non-UTF-8 content under the scope folder raises an unhandled
      UnicodeDecodeError/UnicodeEncodeError instead of a clean 4xx on read or write.
    evidence: |-
      FsWorkspace.read/write call read_text()/write_text() unconditionally; this predates
      6-3 in read_run_file (story 6-2) and 6-3 only extends the same gap to write_run_file.
    location: >-
      backend-api/src/orchestrator/infrastructure/workspace/fs.py
    severity: low
  - summary: >-
      No optimistic-concurrency check between loading a file for edit and saving it, so a
      second tab or a concurrent edit is silently clobbered.
    evidence: |-
      write_run_file has no ETag/mtime comparison; the brief does not ask for one and no AC
      covers concurrent editors of the same Run.
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_files.py::write_run_file
    severity: low
  - summary: >-
      GateRecord.payload is left unused by the spec_edit record; the edited path lives only
      in the free-text `text` field rather than a structured payload key.
    evidence: |-
      GateRecord's own docstring says payload "carries whatever the event needs kept"; not
      required by the brief's AC, which only names the text sentence.
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_files.py::write_run_file
    severity: low
  - summary: >-
      No "unsaved changes" warning when switching the tree selection while the editor is
      open; the draft is silently discarded.
    evidence: |-
      ArtifactsPanel.fetchFile unconditionally calls setEditing(false) on selection; not
      covered by the brief's ACs.
    location: >-
      web-client/src/components/run/ArtifactsPanel.tsx
    severity: low
  - summary: >-
      No loading state between mount/selection and data arriving, and no empty-state
      message for a zero-entry tree.
    evidence: |-
      ArtifactsPanel only renders a treeError state or the populated tree; UX polish not
      covered by the brief's ACs.
    location: >-
      web-client/src/components/run/ArtifactsPanel.tsx
    severity: low
  - summary: >-
      No size or pagination bound on the tree read or the PUT body.
    evidence: |-
      Mirrors an accepted-risk pattern already present elsewhere in the codebase — no
      existing Workspace-backed read endpoint paginates either.
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_files.py
    severity: low
  - summary: >-
      A DB failure after a successful git commit (gate-record insert or uow.commit)
      leaves an unrecorded commit on the branch, with no compensating rollback.
    evidence: |-
      Mirrors an existing architectural pattern elsewhere (git writes are not two-phase
      committed with the DB anywhere in this codebase, e.g. git_commit.py's own step).
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_files.py::write_run_file
    severity: low
baseline_revision: '0e4b7907c5cafab99ed267cf0533d5f85cf88989'
---

<intent-contract>

## Intent

**Problem:** A parked Run gives the Operator no way to fix a gap in `SPEC.md` or a story
file from the Run detail screen; every edit today means leaving the app.

**Approach:** Widen `GET /runs/{id}/files` (6-2) with a tree mode, add `PUT /runs/{id}/files`
that writes the worktree file, commits it as `spec: operator edit (orchestrator)` with only
that path, and appends a `spec_edit` gate record — then an ARTIFACTS column on `RunDetail`
with a tree, a read-only viewer, and a textarea editor.

## Boundaries & Constraints

**Always:**
- `PUT` succeeds only when `run.status == "needs_you"` and `not run.terminal_session`; else
  409 `editing requires a parked run without a terminal session`.
- `path` must resolve inside the Run's own `spec_folder`/`initiative_folder` (else 403) and
  never escape the workspace (else 422) — reuse `run_files.py::_within_spec_folder`/
  `_escapes` verbatim, do not fork the traversal rule.
- `path` naming a list file the plan read (`path in run.plan_refs`) is refused 409
  `planned at {sha} — start a new run to change the list`, `{sha}` = `run.plan_refs[path]`.
- The write is `Workspace.write` then `Git.stage(worktree, pathspec=path)` +
  `Git.commit(worktree, "spec: operator edit (orchestrator)")` — staging only `path` is what
  keeps the commit to "only that path" (the worktree is otherwise clean while parked).
- One `gate_record` per save: `event="spec_edit"`, `actor="operator"`,
  `text="edited {path}"`, `path=run.park_path` (the row the record is about, AD-8's own
  rule — not the edited file).
- No `dangerouslySetInnerHTML` anywhere in the new components (repo-wide invariant).

**Block If:** none identified — the brief and 6-1/6-2's code map cover every branch.

**Never:**
- Touch changed-since-last-opened chips (Epic 8, explicitly out).
- Add a `plan-diff` or any endpoint beyond `GET`/`PUT /runs/{id}/files` — 6-2's own
  `detail.ts` docstring already refused a `plan-diff` endpoint for the same reason.
- Grow `api/routers/runs.py` — the new `PUT` and the tree branch both live in the existing
  sibling `api/routers/run_files.py` (6-2's own precedent, and its own "Notes for next
  story" said so explicitly).
- Write a test about Skip story, Skip epic, Raise budget, Accept, or the terminal path —
  those belong to 6-4 through 6-7.

</intent-contract>

## Code Map

**Backend — extend, do not replace, 6-2's `run_files` trio:**
- `application/use_cases/run_files.py` (111 lines, room to grow) — has `RunFilesPorts`
  (`runs`, `workspace` factory), `read_run_file`, and the two reusable free functions
  `_escapes`/`_within_spec_folder`. Add: `_scope_folder(run) -> str` (the folder computation
  `_within_spec_folder` already does inline — pull it out, have `_within_spec_folder` call
  it, no behaviour change); `RunFilesTree(root: str, entries: tuple[TreeEntry, ...])` +
  `list_files_tree(ports: RunFilesPorts, run_id) -> RunFilesTree` (reuses `RunFilesPorts`,
  no write capability needed); a new `RunFilesWritePorts(runs, workspace, git: Git,
  records: GateRecordRepository, clock: Clock, uow: UnitOfWork)` dataclass; `write_run_file
  (ports: RunFilesWritePorts, run_id, path, content) -> TreeEntry` implementing the five
  checks above in that order (404 → 422 → 403 → 409 plan-anchor → 409 parked), then write +
  stage + commit + `GateRecord` + `ports.uow.commit()`, returning
  `TreeEntry(path=path, is_dir=False, size=len(content), mtime=workspace.mtime(path))` — the
  write's result is the same shape a tree row is, so one schema (`RunFileEntryOut`) covers
  both the tree's rows and the PUT response ("the response carries the new mtime").
- `domain/ports/workspace.py` — `TreeEntry(path, is_dir)` (unused until now) gains
  `size: int = 0`, `mtime: float = 0.0` (defaulted, so `test_fs_workspace.py`'s dict-comprehension
  assertions over `.path`/`.is_dir` stay unaffected). `infrastructure/workspace/fs.py::
  FsWorkspace.tree` computes both from the same `entry.stat()` `rglob` already walks, `0`/`0.0`
  for a directory. `tests/unit/fakes/workspace.py::FakeWorkspace.tree` (the sole fakes
  exception, additive only) gains matching `size=len(text)`/`mtime=self.mtimes.get(path, 0.0)`
  for files and synthesizes the ancestor directory entries under `prefix` (`is_dir=True`) so
  a test can assert `kind: "dir"` rows without a real filesystem.
- `api/schemas/run_files.py` (22 lines) — add `RunFileEntryOut` (`of(entry: TreeEntry)`:
  `path`, `kind: Literal["file","dir"]` from `is_dir`, `size`, `mtime`), `RunFilesTreeOut`
  (`of(tree: RunFilesTree)`: `root`, `entries: list[RunFileEntryOut]`), `RunFileIn`
  (`path: str`, `content: str`, the PUT body).
- `api/routers/run_files.py` (61 lines) — `path` becomes `Annotated[str | None, Query()] =
  None`; `None` → `RunFilesTreeOut.of(list_files_tree(ports, run_id))`, given → today's
  `read_run_file` path unchanged. `response_model=RunFileOut | RunFilesTreeOut`. New
  `PUT /runs/{run_id}/files` route: body `RunFileIn`, ports
  `Annotated[RunFilesWritePorts, Depends(run_files_write_ports)]`, returns
  `RunFileEntryOut.of(write_run_file(...))`, refusals 403/404/409/422 documented the same way
  `GET_REFUSALS` already is.
- `api/providers.py` — new `run_files_write_ports(request) -> Iterator[RunFilesWritePorts]`,
  same `with SQLAlchemyUnitOfWork(...) as uow:` shape `run_files_ports` already uses, plus
  `git=_required_git(request, "run_files")` (existing helper, `signal_effect_ports`'s own
  precedent), `records=SQLAlchemyGateRecordRepository(uow.session)`, `clock=SystemClock()`,
  `uow=uow`. `run_files_ports` itself is untouched.
- `domain/statuses.py` — `GateEvent`'s alphabet gains a `spec_edit` member for a THIRD
  reason beside AD-8's transitions and AD-9's bounded re-executions: a direct worktree write
  outside `signal_run` (the brief's own words: "the only worktree writes outside an engine
  step besides cancel"). **`ALL_GATE_EVENTS`'s stored value is not touched** — see Design
  Notes for why, and why this is not an anchor conflict.
- Domain errors/status mapping (`domain/errors.py::Conflict`, `api/errors.py::DOMAIN_STATUS`)
  already give 409 for `Conflict` — no change needed there.

**Backend — the AD-17 proof.** `application/rules/protected_paths.py::FrameAnchors.check`
only diffs `self.ranges` (one `(start_sha, end_sha)` per attempt); a commit made between
attempts is never a range endpoint, so it is invisible to the check by construction. New
unit test constructs a `FrameAnchors` with one attempt range and a `FakeGit.diff_changes`
scripted to answer only for that range, then asserts a `Change` carrying the operator's own
commit sha (outside the range) is absent from `check()`'s result — AC4's own words ("unit
test over the fakes with the SHAs").

**Frontend — new `ArtifactsPanel`, not a graft onto `AnswerBox`/`RejectBox`/`StoryFileBlock`**
(6-2's own "Notes for next story": those three are read-only/single-field; this is multi-line
with a real Save). `src/islands/RunDetail.tsx` (194 lines) — one new import, one new block in
the existing `wf-right` div (`StoriesStrip`/`CostBlock`/`GateRecord` already live there),
passing `runId`, `run={detail.run}`, `folder={detail.header.meta.folder}` (`lib/run/
checkpoint.ts::plannedFilePath` already reads this same field for its own glob). No new
`RunDetail` state — the panel owns its own tree/selection/edit state, keeping the island's
growth to a handful of lines.
- `src/lib/run/artifacts.ts` (new, pure): `treeRequestPath`/`fileRequestPath` builders,
  `isListFile(folder, path)` (`path === `${folder}/stories.yaml`` or `.../epics.yaml`,
  server-side is the real gate — this is only what hides the Edit control), `isMarkdown(path)`,
  `editHint(branch)` = `` `saved as commit "spec: operator edit (orchestrator)" on ${branch}` ``
  (verbatim), `readOnlyLine(planRef)` = `` `planned at ${planRef} — start a new run to change
  the list` `` (uses `run.plan_ref`, already on the wire — see Design Notes on why this reuses
  the singular field rather than exposing `plan_refs`), `treeDepth(path, root)` for the 14px
  indent multiplier, `canEditFile(run, path, folder)` = `run.status === 'needs_you' &&
  !run.terminal_session && !isListFile(folder, path)`.
- `src/components/run/ArtifactsTree.tsx` (new): `entries: RunFileEntryOut[]`, `selectedPath`,
  `onSelect`. `data-testid="artifacts-tree"` on the root, `data-testid="artifacts-file-{path}"`
  per row, 14px indent per depth + a guide rule (border-left), filename left / mtime
  right-aligned (`DESIGN.md`'s own shape, quoted in the brief).
- `src/components/run/FileViewer.tsx` (new): `path`, `content`, `readOnlyLine: string | null`,
  `canEdit`, `editing`, `onEditToggle`. Markdown → `parseQuestionMarkdown` +
  local `renderBlock`/`renderInline` (the `StoryFileBlock.tsx` precedent for local
  duplication, not an import of it); anything else (YAML included) → `<pre>{content}</pre>`,
  verbatim text. `readOnlyLine` renders as `data-testid="artifacts-readonly"` in place of the
  Edit control.
- `src/components/run/FileEditor.tsx` (new): `path`, `initialContent`, `branch`, `saving`,
  `error`, `onSave(content)`, `onCancel()`. `<textarea data-testid="wf-editor">`, Save button
  `data-testid="wf-editor-save"`, hint paragraph `data-testid="wf-editor-hint"` showing
  `editHint(branch)` — shown alongside the textarea the way `AnswerBox`'s own hint is, not
  only after a successful save.
- `src/components/run/ArtifactsPanel.tsx` (new, ≤ 3 props): fetches the tree on mount and
  after every successful save (`GET /runs/{id}/files`, no `path`); fetches one file's content
  on selection (`GET ...?path=`); PUTs on Save, then re-fetches the tree so the row's mtime
  updates ("the tree's mtime updates", AC5). Computes `canEdit`/`readOnlyLine` from
  `lib/run/artifacts.ts`.
- `src/styles/run-detail.css` (497 lines) — additive rules for `.wf-artifacts*` at the end of
  the file, the same token variables the existing `.wf-right`/`.wf-answer-box` rules already
  use.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/ports/workspace.py` -- widen `TreeEntry` with
  `size`/`mtime` -- the tree response and the write result both need them.
- `backend-api/src/orchestrator/infrastructure/workspace/fs.py` -- compute them in `tree()`
  -- keeps the real adapter and the fake in step.
- `backend-api/src/orchestrator/domain/statuses.py` -- add `spec_edit` to `GateEvent` --
  the gate record this story's own AC pins needs a validating type.
- `backend-api/src/orchestrator/application/use_cases/run_files.py` -- add
  `list_files_tree`/`write_run_file`/`RunFilesWritePorts`/`RunFilesTree`, extract
  `_scope_folder` -- the use-case layer for both new endpoints.
- `backend-api/src/orchestrator/api/schemas/run_files.py` -- add `RunFileEntryOut`/
  `RunFilesTreeOut`/`RunFileIn` -- the wire shapes.
- `backend-api/src/orchestrator/api/routers/run_files.py` -- optional `path`, tree branch,
  new `PUT` route -- the two endpoints the brief asks for.
- `backend-api/src/orchestrator/api/providers.py` -- `run_files_write_ports` -- wires `Git`/
  `GateRecordRepository`/`Clock`/`UnitOfWork` for the write path only.
- `backend-api/tests/unit/fakes/workspace.py` -- `tree()` gains size/mtime/dir entries
  (additive) -- lets unit tests assert the tree shape without a real filesystem.
- New backend test files (one concern each, per the epic's "new coverage → new file" rule):
  `tests/unit/application/test_run_files_tree.py`, `tests/unit/application/
  test_run_files_write.py`, `tests/unit/test_run_files_tree_schema.py`, `tests/unit/
  test_run_files_write_router.py`, `tests/unit/test_run_files_tree_router.py`, `tests/unit/
  test_spec_edit_gate_event.py`, `tests/unit/application/
  test_protected_paths_operator_edit.py`, `tests/e2e/test_spec_edit.py`.
- `web-client/src/lib/run/artifacts.ts`, `src/components/run/{ArtifactsTree,FileViewer,
  FileEditor,ArtifactsPanel}.tsx`, `src/islands/RunDetail.tsx`, `src/styles/run-detail.css`
  -- the UI, per the Code Map above.
- New frontend test files: `web-client/tests/unit/lib/run-artifacts.test.ts`, `web-client/
  tests/unit/components/run-artifacts.test.tsx`, `web-client/tests/e2e/
  run-detail-artifacts.spec.ts`.
- `make openapi` -- regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  -- never hand-write either (AD-3).

**I/O & Edge-Case Matrix**

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Save on a parked Run | `PUT {path: "specs/x/SPEC.md", content}`, `needs_you`, no terminal session | write, commit (only that path), `spec_edit` record, 200 with new mtime | — |
| List-file write | `path: "specs/x/stories.yaml"` | no write | 409 `planned at {sha} — start a new run to change the list` |
| Not parked | `run.status == "running"` | no write | 409 `editing requires a parked run without a terminal session` |
| Terminal session | `needs_you`, `terminal_session == true` | no write | 409, same text |
| Escaping path | `path: "../x"` | no write | 422, checked before scope (6-2's own order) |
| Outside scope | well-formed path outside `spec_folder`/`initiative_folder` | no write | 403 |
| Tree read | `GET /runs/{id}/files` (no `path`) | `{root, entries[]}` recursive over the scope folder | — |
| Next attempt's protected-path check | operator's `SPEC.md` commit lands between attempts | not flagged (outside every recorded range) | — |

**Acceptance Criteria:** (the brief's own five ACs — verbatim, not restated here — govern;
implemented exactly as written in `briefs/6-3-inline-spec-editing.md`.)

## Spec Change Log

## Review Triage Log

### 2026-09-09 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 1, medium 4, low 4)
- defer: 7: (high 0, medium 0, low 7)
- reject: 5: (high 0, medium 0, low 5)
- addressed_findings:
  - `[high]` `[patch]` a Save with content identical to what is already on disk crashed
    (`git commit` fails on nothing staged) — `write_run_file` now short-circuits to a no-op
    200 when the new content equals the current content, skipping stage/commit/gate-record.
  - `[medium]` `[patch]` `PUT` to a path that is an existing directory crashed with an
    unhandled `IsADirectoryError` — `FsWorkspace.write` now raises `WorkspaceError` for a
    directory target, caught by `write_run_file`'s existing handler into a 422.
  - `[medium]` `[patch]` `write_run_file`'s reported `size` (`len(content)`, characters)
    disagreed with the tree's own `size` (`stat.st_size`, bytes) for non-ASCII content —
    both `_read`/`write_run_file` now report `len(content.encode("utf-8"))`, matching the
    tree's byte count; a multi-byte test added.
  - `[medium]` `[patch]` `list_files_tree` exposed the whole worktree for a Run with no
    `spec_folder`/`initiative_folder`, contradicting the module's own scope-folder claim
    and disagreeing with read/write's "empty folder → refuse everything" rule — now answers
    an empty tree instead; the new (uncommitted) test asserting the old behavior corrected.
  - `[medium]` `[patch]` `ArtifactsPanel`'s tree/file fetch effects lacked the cancellation
    guard `RunDetail.tsx`'s own `plannedFile` effect already uses — a stale response could
    overwrite a fresher one; the same `cancelled` flag pattern added to both.
  - `[low]` `[patch]` `workspace.mtime(path)` after a successful write was unguarded —
    wrapped in the same `WorkspaceError → Invalid` pattern `read_run_file` already uses.
  - `[low]` `[patch]` `FsWorkspace.tree()`'s per-entry `is_dir()`/`stat()` could raise on a
    TOCTOU race (a file removed between listing and stat) — now skips that entry instead of
    crashing the whole tree read.
  - `[low]` `[patch]` a failed tree re-fetch left the previous tree rendered under the error
    line — `ArtifactsPanel` now clears the tree on a failed fetch.
  - `[low]` `[patch]` a `PUT` resolving with no error but falsy `data` (a contract
    violation) left the operator with no feedback — `save()` now falls back to a
    synthesized problem-detail instead of `null`.

Deferred (pre-existing or genuinely out of this story's scope, not fixed in this pass): see
frontmatter `deferred` — binary/non-UTF-8 content handling (predates 6-3, in 6-2's own
`read_run_file`), no optimistic-concurrency check between load and save, `GateRecord.payload`
left unused, no unsaved-changes warning on selection switch, no loading/empty states, no
size/pagination bound, and a DB-write-after-git-commit failure ordering that mirrors an
existing pattern elsewhere in the codebase.

Rejected as noise (not real, already covered, or unreachable): a `spec_edit`
gate record's `path` going `None` (protected by the existing `Run.park_path` invariant for
every `needs_you` Run); `fetchFile` receiving tree-shaped data (unreachable — `fetchFile`
always supplies a concrete `path`, which the router only ever answers with file content);
`mtimeText` crashing on a non-finite `mtime` (server `mtime` is always a real `stat()` float
or `0.0`, never non-finite, and a directory row never reaches `Date` at all); `PUT` being
able to create a brand-new file at a path that does not exist yet (reuses `Workspace.write`'s
own pre-existing, documented behavior verbatim, and the tree/viewer UI has no "new file"
affordance to reach it from).

### Investigated separately — the two Epic-5 screenshot deliverables

`_bmad-output/implementation-artifacts/epic-5-screens/{01,02}-*.png` come back modified by
every `make e2e-ui` run, including the required final one. Root cause, confirmed by reading
`web-client/tests/e2e/run-detail-story-additions.spec.ts` (an existing anchor test predating
this branch, story 5.10): it unconditionally calls `page.screenshot({ path: SCREENS/..., fullPage:
true })` at the end of its two tests, on every run, by design (its own module doc: "this
epic's own screenshot deliverable ... gets one PNG per state below, captured while this spec
runs"). `ArtifactsPanel` now mounts unconditionally on every Run status (the brief's own
words: "other statuses show the tree and viewer only"), so it is part of the full-page
capture for both of that spec's states. There is no way to make the two files stop changing
without either (a) editing that anchor test — forbidden outright, no hard-rule-1 exception
applies (no assertion is at stake, so this is not itself a hard-rule-1 case, but the file is
still an existing test file no story may touch) — or (b) suppressing the brief's own
required, permanent UI element on those two specific screens, which would contradict FR-23.
Both are outside this story's authority to choose between. The new bytes are the correct,
expected output of a required feature and are committed as part of this story; this is
flagged for the operator rather than silently resolved, since the underlying tension (any
future story that adds persistent `RunDetail` chrome will hit the same conflict) is a
process question about that anchor test's own design, not one story's bug.

## Design Notes

**Why `ALL_GATE_EVENTS`'s value is not touched.** `tests/unit/test_gate_events.py`
(predates this branch, story 4-5) pins `ALL_GATE_EVENTS == (*GATE_EVENTS, *MACHINE_EVENTS)`
exactly — hard rule 1's anchor. The honest alternative, not an edit: `spec_edit` is added to
the `GateEvent` **type** union so `GateRecord(event="spec_edit", ...)` validates, but
`ALL_GATE_EVENTS`'s own **value** stays the exact two-alphabet concatenation the test pins.
This mirrors the codebase's own layering precedent exactly: `GATE_EVENTS` (AD-8's three,
pinned by the older `test_run_statuses.py`) is already a *strict subset* the newer
`ALL_GATE_EVENTS` (AD-8 + AD-9, story 4-5) was added beside without editing the older test —
`test_gate_events.py`'s own `test_the_transition_alphabet_is_a_strict_subset_of_the_whole_one`
says so in as many words. `spec_edit` (and `cancel`'s own kind, already inside `SignalKind`)
are the direct-write class the brief itself names ("the only worktree writes outside an
engine step besides cancel") — a third, even-outer layer, proven by its own new test file
(`test_spec_edit_gate_event.py`) rather than by widening a frozen constant. No existing test
file is edited for this.

**`plan_ref` vs `plan_refs` for the read-only line's `{sha}`.** The backend 409 uses
`run.plan_refs[path]` — "the commit each list file was read at" (`Plan.plan_refs`'s own
docstring), the precise per-file fact. The frontend's proactive read-only line (shown before
any PUT is attempted, so there is no 409 body to read the sha from) uses `run.plan_ref`
(singular) instead — already on the wire (`RunDetailSummaryOut.plan_ref`) since 4.4, and
`plan_refs` is not published to the client. Widening the read model to publish `plan_refs`
would be a wire change the brief does not ask for; reusing the field 6-2 and earlier stories
already expose keeps this story to the two endpoints the brief names.

**`TreeEntry` reused for the PUT response.** Rather than a fourth dataclass, `write_run_file`
returns the same `TreeEntry` `list_files_tree` already emits per row — the write's own
result *is* a tree row (`path`, `kind`, `size`, `mtime`), so one schema (`RunFileEntryOut`)
serves both "the response carries the new mtime" (AC1) and the tree's own rows.

**Anchor corrections made under the epic's standing rule (b).**
`backend-api/tests/unit/test_run_files_router.py` was written in story 6-2, on this branch,
and pins two things this story's own brief now governs differently:
1. `test_the_router_declares_exactly_one_operation` (routes == one `GET`) — this story adds
   `PUT` to the same router by design (6-2's own "Notes for next story" said so). Renamed to
   `test_the_router_declares_exactly_the_two_operations`, assertion widened to both routes.
2. `test_a_missing_path_query_param_is_a_422` — this story's brief redefines "no `path`" as
   the tree response, not a refusal. Renamed to `test_a_missing_path_query_param_answers_the_tree`,
   assertion changed to 200 + tree shape.

Both are single-assertion edits, nothing else in the file changes, and strictly-exceeding
coverage lands in two new files (`test_run_files_write_router.py`,
`test_run_files_tree_router.py`) in the same commit.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy, import-linter, env-contract, eslint, prettier, tsc,
  astro check all clean.
- `make test` -- expected: backend + web-client unit suites green, `domain/`+`application/`
  100% branch coverage held.
- `make openapi` -- expected: `contracts/openapi.json` and `schema.d.ts` regenerate with
  `RunFileEntryOut`/`RunFilesTreeOut`/`RunFileIn` and the new `PUT` operation; `gen:api
  --check` clean afterward.
- `make e2e` -- expected: green on the disposable stack (`ORCH_TEST_MODE=1`), including the
  new `test_spec_edit.py`.
- `make e2e-ui` -- expected: green, including the new artifacts Playwright spec.

## Auto Run Result

Status: done

**Summary.** `GET`/`PUT /runs/{id}/files` widened per the brief: `GET` with no `path` answers
a recursive tree (`{root, entries}`) over the Run's own spec/initiative folder; `PUT` writes
the worktree file, commits it alone as `spec: operator edit (orchestrator)`, appends a
`spec_edit` gate record, and is refused 422/403/409/409 in that order (escape / scope / plan
anchor / not-parked). `RunDetail`'s new ARTIFACTS column (`ArtifactsPanel`, `ArtifactsTree`,
`FileViewer`, `FileEditor`) renders the tree, a read-only Markdown/plain-text viewer, and a
textarea editor with the exact save hint, gated by the same rules server-side.

**Files changed** (backend): `application/use_cases/run_files.py` (`list_files_tree`,
`write_run_file`, `RunFilesWritePorts`), `api/schemas/run_files.py` (`RunFileEntryOut`,
`RunFilesTreeOut`, `RunFileIn`), `api/routers/run_files.py` (tree branch + `PUT`),
`api/providers.py` (`run_files_write_ports`), `domain/statuses.py` (`spec_edit` widens
`GateEvent`, `ALL_GATE_EVENTS`'s pinned value untouched), `domain/ports/workspace.py`
(`TreeEntry` gains `size`/`mtime`), `infrastructure/workspace/fs.py` (`tree()` computes them,
a directory-target write refuses cleanly, a TOCTOU'd entry is skipped not crashed),
`tests/unit/fakes/workspace.py` (additive: matching `tree()` shape). Eight new backend test
files (tree/write use cases, tree/write routers, tree schema, the `spec_edit` alphabet proof,
the AD-17 never-attributed proof, one e2e). One corrected existing test file
(`test_run_files_router.py`, two renamed/widened assertions under the epic's standing rule
(b), both from story 6-2 on this branch; see Design Notes).

**Files changed** (frontend): `lib/run/artifacts.ts`, `components/run/{ArtifactsPanel,
ArtifactsTree,FileViewer,FileEditor}.tsx` (new), `islands/RunDetail.tsx` (wires the panel into
`wf-right`), `styles/run-detail.css` (additive `.wf-artifacts*`/`.wf-editor*`). Three new test
files (lib, component, e2e). `contracts/openapi.json` / `src/api/schema.d.ts` regenerated.

**Review findings breakdown:** 9 patch (1 high, 4 medium, 4 low) — all applied and verified;
see Review Triage Log for each. 7 deferred (all low) — recorded in frontmatter `deferred`. 4
rejected as noise or unreachable. The two Epic-5 screenshot deliverables investigated
separately (see Review Triage Log) — not a review finding in the patch/defer/reject sense,
but a structural conflict flagged for the operator.

**Follow-up review recommendation:** `true` (one `high`-severity patch was applied — the
no-op-save crash).

**Verification performed** (all five gates, foreground, real output, after every patch was
applied):
- `make lint` — pass: ruff, ruff format, mypy (domain/application strict), import-linter (4
  contracts kept), env-contract (34/40 agree), test-pairs (188 backend modules), `gen:api
  --check` clean, eslint/prettier/`tsc --noEmit`/astro check (0 errors), web test-pairs (83
  modules).
- `make test` — pass: 5195 backend passed, 1 skipped; `domain/`+`application/` **100%**
  branch coverage (`run_files.py` itself 100%); web-client 1083 passed across 79 files.
- `make openapi` — pass: `contracts/openapi.json`/`schema.d.ts` regenerate with
  `RunFileEntryOut`/`RunFilesTreeOut`/`RunFileIn` and the new `PUT` operation; stable across
  repeated runs (no drift).
- `make e2e` — pass: 168 passed, 11 deselected, 38 subtests, on the disposable `aio-e2e`
  stack. (Two earlier attempts hit transient Docker network/compose races on this machine,
  unrelated to the code — confirmed by a fully clean teardown + single uninterrupted rerun
  passing outright; see hand-back for detail.)
- `make e2e-ui` — pass: 130 passed (129 pre-existing/updated + 1 new: the ARTIFACTS staleness
  guard), including `run-detail-artifacts.spec.ts` in full.

**Residual risks.** Seven low-severity items deferred (frontmatter `deferred`), none blocking
any acceptance criterion. The Epic-5 screenshot deliverable conflict (see Review Triage Log)
recurs on every future `make e2e-ui` run for as long as `ArtifactsPanel` renders on every Run
status and `run-detail-story-additions.spec.ts` keeps its unconditional full-page capture —
both are correct as they stand; only a future, operator-authorized change to that anchor test
(e.g. an opt-in capture flag) would end the recurrence.
