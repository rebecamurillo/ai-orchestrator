---
title: 'Changed-since-last-opened marks'
type: 'feature'
created: '2026-09-11'
status: 'in-review'
baseline_revision: '5aa4e769cd28f5304b422954c7fd7d768ae5741d'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** Returning to a Run after days away, the Operator cannot tell which artifact files changed since they last looked — the artifacts tree shows everything with equal visual weight.

**Approach:** Record `last_opened_before` (the prior visit timestamp) on the Run when the detail is first fetched per navigation (`?opened=1`); expose a `changed: bool` per file in `GET /runs/{run_id}/files` by comparing each file's mtime to that cutoff; render a 7 px accent chip and text promotion on changed file rows in `ArtifactsTree`.

## Boundaries & Constraints

**Always:**
- `last_opened_before` and `last_opened_at` are the only new Run fields written outside the two status writers (AD-8 exception: explicit use case, own endpoint side-effect).
- `?opened=1` lands on `GET /runs/{run_id}/detail` only (the frontend endpoint, not the bare `GET /runs/{run_id}` — frozen tests pin that route's shape).
- `changed: bool` lives on `RunFileEntryChangedOut`, a new subclass of `RunFileEntryOut`; `RunFileEntryOut` is not modified (frozen schema test asserts its exact `model_dump()` shape).
- `changed=true` only for files (`entry.kind == "file"`) modified after `last_opened_before`; directories are never marked.
- `changed=false` when `last_opened_before` is `None` (Run never previously opened).
- Schema is generated, never hand-written (AD-3): after adding Python schemas, run `make openapi && pnpm gen:api`.
- Migration slot: `0010` is taken by `terminal_clean_polls`; the new migration is `0011_last_opened_before.py`.

**Block If:**
- `Workspace.tree` does not return `mtime` on every `TreeEntry` (confirmed present since 6.3 — not a blocker).
- `RunFilesPorts.runs` does not expose `Run.last_opened_before` after migration (must confirm migration committed before running verification).

**Never:**
- Mark directories with the chip or text promotion.
- Compute `changed` from `last_opened_at` (use `last_opened_before`, the pre-visit snapshot).
- Send `?opened=1` on polling requests, only on the first navigation fetch.
- Modify `RunFileEntryOut`, `RunFilesTreeOut`, or their `.of()` factories (frozen tests).
- Modify any existing test file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|----------------|----------------|
| First-ever open | `last_opened_at=null`, `?opened=1` | `last_opened_at=now`, `last_opened_before=null`; all files `changed: false` | — |
| Second open, 2 files changed | `last_opened_before=T`, 2 files with `mtime > T` | those 2 entries `changed: true`, rest `false`; tree shows chip+promotion on 2 rows | — |
| Poll during visit | no `?opened=1` | `last_opened_before` unchanged; `changed` marks identical to opening response | — |
| Third open, no new changes | `last_opened_before=T2`, no file newer than T2 | all `changed: false` | — |
| Directory in tree | `entry.is_dir=True`, mtime > cutoff | `changed: false` regardless of mtime | — |
| Unknown run | any `run_id` not in DB | 404 | Problem JSON |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/entities/run.py:103` — `Run` entity; `last_opened_at: datetime | None = None` already at line 103; add `last_opened_before: datetime | None = None` after it
- `backend-api/src/orchestrator/infrastructure/db/models/run.py:100` — `RunRow`; `last_opened_at` column at line 100; add `last_opened_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)` after it; update `to_entity()` and `row_values()`
- `backend-api/alembic/versions/0010_terminal_clean_polls.py` — current head migration (chain terminus); new `0011_last_opened_before.py` must chain from its revision id
- `backend-api/src/orchestrator/application/use_cases/activity.py` — `ActivityPorts(runs, uow)` pattern; `open_run.py` follows exact same shape adding `clock: Clock`
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:35` — `RunViewPorts` has `clock: Clock` at line 45; `open_run.py`'s `OpenRunPorts` uses the same `Clock` port
- `backend-api/src/orchestrator/domain/ports/repositories.py:73` — `RunRepository.update(run)` at line 84; used by `open_run` to persist the updated entity
- `backend-api/src/orchestrator/application/use_cases/run_files.py:107` — `RunFilesPorts(runs, workspace)`; `RunFilesTree` dataclass: add `last_opened_before: datetime | None = None`; update `list_files_tree` to pass `run.last_opened_before` into the returned `RunFilesTree`
- `backend-api/src/orchestrator/api/schemas/run_files.py:29` — `RunFileEntryOut` (DO NOT MODIFY); add `RunFileEntryChangedOut(RunFileEntryOut)` with `changed: bool = False`; add `RunFilesTreeChangedOut` with `entries: list[RunFileEntryChangedOut]` and `of(tree)` factory computing `changed` from `last_opened_before`
- `backend-api/src/orchestrator/api/schemas/run_views.py:111` — `RunDetailSummaryOut`; add `last_opened_at: datetime | None = Field(default=None, json_schema_extra=_drop_default)` (same `_drop_default` guard as `terminal`); update `of_run()` to pass `last_opened_at=run.last_opened_at`
- `backend-api/src/orchestrator/api/routers/run_detail.py:51` — `detail()` handler; add `opened: Annotated[bool, Query()] = False`; add `OpenPorts = Annotated[OpenRunPorts, Depends(open_run_ports)]` dependency; call `open_run(open_ports, run_id)` before `build_detail` when `opened=True`
- `backend-api/src/orchestrator/api/routers/run_files.py:98` — `get_file()` handler; tree branch (`path is None`) returns `RunFilesTreeChangedOut.of(list_files_tree(...))` instead of `RunFilesTreeOut.of(...)`; update `response_model` to `RunFileOut | RunFilesTreeChangedOut | RunFileDiffOut`
- `backend-api/src/orchestrator/api/providers.py:347` — `activity_ports` provider pattern; add `open_run_ports` provider wiring `OpenRunPorts(runs=..., uow=..., clock=...)`
- `web-client/src/api/schema.d.ts` — DO NOT EDIT; regenerated by `make openapi && pnpm gen:api`
- `web-client/src/lib/run/artifacts.ts:16` — currently exports `RunFileEntryOut`, `RunFilesTreeOut`; add `RunFileEntryChangedOut`, `RunFilesTreeChangedOut` re-exports; update `FilesResponse = RunFileOut | RunFilesTreeChangedOut | RunFileDiffOut`; update `isTree` return type to `data is RunFilesTreeChangedOut`
- `web-client/src/components/run/ArtifactsPanel.tsx:25` — imports `RunFilesTreeOut`; change to `RunFilesTreeChangedOut`; update `tree` state type accordingly
- `web-client/src/components/run/ArtifactsTree.tsx:14` — `Props.entries: RunFileEntryOut[]`; change to `RunFileEntryChangedOut[]`; add chip span `<span className="wf-artifacts-chip" />` before `wf-artifacts-name` when `entry.changed`; add `data-changed="true"` on the `<button>` when `entry.changed` for CSS text promotion
- `web-client/src/styles/run-detail.css:566` — `.wf-artifacts-name` style; add `.wf-artifacts-chip` style (7px filled circle, accent color); add `.wf-artifacts-file[data-changed='true'] .wf-artifacts-name { color: var(--color-text); }` and `[data-changed='false'] .wf-artifacts-name` keeping `text-secondary`
- `web-client/src/islands/RunDetail.tsx:78` — `fetchDetail()` calls `api.GET('/runs/{run_id}/detail', ...)`; add `openedRef = useRef(false)`; on first mount call, append `{ query: { opened: true } }` and set `openedRef.current = true`; poll calls omit `opened`
- `backend-api/tests/unit/application/test_open_run.py` — NEW; tests `open_run` use case: sets `last_opened_before = prior last_opened_at`, `last_opened_at = now`; NotFound on unknown run_id
- `backend-api/tests/unit/test_run_detail_opened_router.py` — NEW; tests `GET /runs/{id}/detail?opened=1` sets fields and `GET /runs/{id}/detail?opened=0` does not
- `backend-api/tests/unit/test_run_files_tree_changed_schema.py` — NEW; tests `RunFileEntryChangedOut` and `RunFilesTreeChangedOut.of()`: `changed=true` for file with `mtime > cutoff`, `false` for dir, `false` when `last_opened_before=None`
- `web-client/tests/unit/artifacts-tree-changed.test.tsx` — NEW; unit tests for `ArtifactsTree`: chip renders for `changed=true` file, absent for `changed=false`, absent for dir with `changed=true`
- `web-client/tests/e2e/run-detail-last-opened.spec.ts` — NEW; Playwright e2e: first open (`?opened=1`) returns `last_opened_at` and all `changed: false`; second open with a changed file shows chip on that file's row; polling (no `?opened=1`) does not reset marks

## Tasks & Acceptance

**Execution:**

1. `backend-api/src/orchestrator/domain/entities/run.py` — add `last_opened_before: datetime | None = None` after `last_opened_at` at line 103
2. `backend-api/src/orchestrator/infrastructure/db/models/run.py` — add `last_opened_before` column; update `to_entity()` and `row_values()` to map it
3. `backend-api/alembic/versions/0011_last_opened_before.py` — NEW migration: adds `last_opened_before` nullable TIMESTAMPTZ column to `run`; chains from `0010_terminal_clean_polls`'s revision id
4. `backend-api/src/orchestrator/application/use_cases/open_run.py` — NEW; `OpenRunPorts(runs, uow, clock)`; `open_run(ports, run_id)` swaps `last_opened_before ← last_opened_at`, sets `last_opened_at = clock.now()`, commits; raises `NotFound` for unknown id
5. `backend-api/src/orchestrator/application/use_cases/run_files.py` — add `last_opened_before: datetime | None = None` to `RunFilesTree`; update both `RunFilesTree(...)` calls in `list_files_tree` to pass `last_opened_before=run.last_opened_before`
6. `backend-api/src/orchestrator/api/schemas/run_files.py` — add `RunFileEntryChangedOut(RunFileEntryOut)` with `changed: bool = False`; add `RunFilesTreeChangedOut(root, entries: list[RunFileEntryChangedOut])` with `of(tree)` computing `changed` per entry (file-only, `mtime > cutoff` where cutoff = `tree.last_opened_before.timestamp()`, or `False` if `last_opened_before` is None)
7. `backend-api/src/orchestrator/api/schemas/run_views.py` — add `last_opened_at: datetime | None = Field(default=None, json_schema_extra=_drop_default)` to `RunDetailSummaryOut`; update `of_run()` to include `last_opened_at=run.last_opened_at`
8. `backend-api/src/orchestrator/api/providers.py` — add `open_run_ports` provider (clock from `SystemClock`, runs and uow from the request's DB session pool, same pattern as `activity_ports`)
9. `backend-api/src/orchestrator/api/routers/run_detail.py` — add `opened: Annotated[bool, Query()] = False` and `OpenPorts = Annotated[OpenRunPorts, Depends(open_run_ports)]` to `detail()`; call `open_run(open_ports, run_id)` before `build_detail` when `opened=True`
10. `backend-api/src/orchestrator/api/routers/run_files.py` — tree branch (`path is None`) returns `RunFilesTreeChangedOut.of(list_files_tree(...))` instead of `RunFilesTreeOut.of(...)`; update `response_model` union to include `RunFilesTreeChangedOut`
11. `backend-api/tests/unit/application/test_open_run.py` — NEW unit tests for the use case
12. `backend-api/tests/unit/test_run_detail_opened_router.py` — NEW router test: `?opened=1` calls `open_run`, `?opened=0` (default) skips it; 404 on unknown run; response includes `run.last_opened_at`
13. `backend-api/tests/unit/test_run_files_tree_changed_schema.py` — NEW schema unit tests for `RunFileEntryChangedOut`/`RunFilesTreeChangedOut.of()`
14. `make openapi` — regenerate `contracts/openapi.json` and run `pnpm gen:api` to update `web-client/src/api/schema.d.ts`
15. `web-client/src/lib/run/artifacts.ts` — add `RunFileEntryChangedOut` and `RunFilesTreeChangedOut` exports; update `FilesResponse` union and `isTree` guard return type to `RunFilesTreeChangedOut`
16. `web-client/src/components/run/ArtifactsPanel.tsx` — replace `RunFilesTreeOut` with `RunFilesTreeChangedOut` for `tree` state type and import
17. `web-client/src/components/run/ArtifactsTree.tsx` — change `entries: RunFileEntryOut[]` to `RunFileEntryChangedOut[]` in `Props`; add chip span before filename when `entry.changed`; add `data-changed={entry.changed ? 'true' : undefined}` to the file `<button>`
18. `web-client/src/styles/run-detail.css` — add `.wf-artifacts-chip { width: 7px; height: 7px; border-radius: 50%; background: var(--color-accent); flex-shrink: 0; }` near existing `.wf-artifacts-name`; add `.wf-artifacts-file[data-changed='true'] .wf-artifacts-name { color: var(--color-text); }` for text promotion
19. `web-client/src/islands/RunDetail.tsx` — add `openedRef = useRef(false)`; in `fetchDetail`, pass `query: { opened: openedRef.current ? undefined : true }` on the first call and set `openedRef.current = true`; poll calls omit the param
20. `web-client/tests/unit/artifacts-tree-changed.test.tsx` — NEW; render chip for changed file, no chip for unchanged file, no chip for changed dir
21. `web-client/tests/e2e/run-detail-last-opened.spec.ts` — NEW e2e covering the 3 ACs

**Acceptance Criteria:**
- Given a Run last opened at T and two files modified after T, when the detail is opened (`?opened=1`) and the tree is read, then those two entries have `changed: true`, the others `false`, `run.last_opened_at` is updated, and the artifacts tree shows the accent chip and promoted text on the two file rows
- Given subsequent polls during the same visit (no `?opened=1`), when the tree is re-read, then the `changed` marks are unchanged
- Given a second opening with no new changes, when the tree is read, then no entry is `changed: true`
- Given a directory entry with `mtime > last_opened_before`, when rendered, then `changed` is `false` and no chip appears

## Spec Change Log

## Review Triage Log

## Design Notes

**Why `RunFileEntryChangedOut` (not modifying `RunFileEntryOut`):** `test_run_files_tree_schema.py` asserts the exact `model_dump()` dict of `RunFileEntryOut.of()` and `RunFilesTreeOut.of()` entries. Adding `changed` to `RunFileEntryOut` would include `"changed": false` in that dict, breaking the frozen test. The subclass approach keeps `RunFileEntryOut` and `RunFilesTreeOut` untouched; only the router branch and `RunFilesTreeChangedOut.of()` use the new type. The OpenAPI schema gains `RunFileEntryChangedOut` as a distinct type; `pnpm gen:api` exposes it; `artifacts.ts` re-exports it.

**`last_opened_before` not `last_opened_at` as the mtime cutoff:** The brief's invariant: "the marks stay visible for the whole visit". `last_opened_before` captures the snapshot at the moment of the opening and is stable throughout the visit. If `last_opened_at` were used, the cutoff would advance on re-fetch and marks would disappear. `last_opened_before = null` (first visit) correctly yields all `changed: false`.

**`?opened=1` on the first navigation fetch only:** `RunDetail.tsx` uses `openedRef` (not `useState`) to avoid triggering a re-render. The flag is set after the first `fetchDetail` call resolves; subsequent polling calls omit the param so `last_opened_before` is not advanced mid-visit.

## Verification

**Commands:**
- `make lint` — expected: zero ruff/mypy/import-linter/eslint/tsc errors
- `make test` — expected: all unit tests pass including new `test_open_run.py`, `test_run_detail_opened_router.py`, `test_run_files_tree_changed_schema.py`, `artifacts-tree-changed.test.tsx`
- `make openapi` — expected: `contracts/openapi.json` updated with `RunFileEntryChangedOut` and `RunFilesTreeChangedOut`; no drift after `pnpm gen:api`
- `make e2e-ui` — expected: `run-detail-last-opened.spec.ts` passes; existing `run-detail-artifacts.spec.ts` unaffected
