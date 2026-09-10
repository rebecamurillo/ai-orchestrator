---
title: 'Trajectory export'
type: 'feature'
created: '2026-09-10'
baseline_revision: '8f4b545876291bcf5c0552dee3d93d8ce2fcd136'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Trajectory table (5.9, AD-19) has no reader. There is no way to pull a
Project's stories out for SM-1/SM-3 comparison or a fine-tuning set (SPEC CAP-6, FR-32).

**Approach:** A new streamed `GET /projects/{id}/trajectories.jsonl` (ndjson, newest first,
paged 100 at a time), an *Export trajectories* bar action on the Project detail with its hint
and a `trajectory_count` reading, and a proxy passthrough that keeps the download headers intact.

## Boundaries & Constraints

**Always:** the port stays `add` + `list_for_project` only — `SQLAlchemyTrajectoryRepository`'s
public set is pinned to exactly `{"add", "list_for_project"}`
(`test_trajectory_repository_adapter.py::test_the_adapter_has_no_way_to_change_or_delete_a_trajectory`);
the count is computed as `len(list_for_project(...))`, never a new port method. The new route
lives in its own router (`api/routers/projects.py` is pinned at four operations by
`test_projects_router.py::test_the_router_declares_four_operations_and_repeats_no_dependency`).
`trajectory_count` on `ProjectRead` is `int | None = None` (mirrors `builtin`'s own precedent
in `api/schemas/projects.py`) so the frozen `web-client/tests/unit/newwf-state.test.ts` and
`newwf-fields.test.ts` `ProjectRead` object-literal fixtures keep compiling unchanged; it always
resolves to a real `int` in `.of()`. `application/use_cases/projects.py` is 395/400 lines — do
not add to it; thread the count through a second, separate FastAPI dependency instead.

**Block If:** none identified — no further anchor conflict surfaced during investigation.

**Never:** no aggregation/dashboard (Scope: Out). No new method on `TrajectoryRepository`. No
hand-edit of `web-client/src/api/schema.d.ts` (AD-3) — `make openapi` regenerates it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Three trajectories | known Project, 3 rows | 200, `application/x-ndjson`, `Content-Disposition: attachment; filename="trajectories-{slug}-{date}.jsonl"`, 3 lines newest first, each valid JSON | none |
| No trajectories | known Project, 0 rows | 200, empty body | none |
| Unknown Project | random UUID | 404 problem document | `NotFound` → global handler |
| Project detail render | Project selected, 3 trajectories | *Export trajectories* linking to the proxy path, hint text shown, `3 trajectories` shown | none |
| Browser download (Playwright) | click *Export trajectories* | file arrives with its filename and ndjson content | none |

</intent-contract>

## Code Map

**backend-api — a new router/use-case/schema trio (the `history.py` pattern, 7.5):**

- `src/orchestrator/domain/ports/trajectories.py`, `domain/entities/trajectory.py` — read-only.
  `Trajectory` already carries every field the brief lists, `story_file` included.
- `tests/unit/fakes/trajectories.py` — `FakeTrajectoryRepository`, the one fake for the port.
  Reuse; do not add a second one.
- `src/orchestrator/application/use_cases/trajectory_export.py` (new) — `PAGE_SIZE = 100`,
  `export_filename(slug, today) -> str`, `trajectory_count(trajectories, project_id) -> int`
  (`len(list_for_project(...))`), `TrajectoryExportPorts` (`projects: ProjectRepository`,
  `trajectories: TrajectoryRepository`, `clock: Clock`), `build_export(ports, project_id) ->
  tuple[str, Iterator[str]]` — raises `domain.errors.NotFound` for an unknown Project, else
  returns the filename and a generator that yields the rows in chunks of 100, newest first
  (`list_for_project` already sorts newest first; there is no third port method to page the
  query itself, so paging is the response generator batching the one in-memory list — see
  Design Notes).
- `src/orchestrator/api/schemas/trajectories.py` (new) — `TrajectoryLineOut` (+ small nested
  `AttemptRecordOut`, `GateResultsOut`, `ProtectedPathsResultOut`, `HumanActionOut`), mirroring
  every `Trajectory` field with `MoneyStr`/`UtcTimestamp` (`api/schemas/common.py`) for
  `cost_usd`/timestamps, `.of(Trajectory) -> TrajectoryLineOut`.
- `src/orchestrator/api/routers/trajectories.py` (new) — `GET /projects/{project_id}/trajectories.jsonl`,
  `StreamingResponse(media_type="application/x-ndjson")`, `Content-Disposition` header, no
  `response_model` (the body is not one JSON document).
- `src/orchestrator/api/providers.py` — `trajectory_repository(request) -> Iterator[TrajectoryRepository]`
  (lightweight, feeds the count dependency) and `trajectory_export_ports(request) ->
  Iterator[TrajectoryExportPorts]` (feeds the export route), both opening their own
  `SQLAlchemyUnitOfWork` the way `history_ports` does.
- `src/orchestrator/api/routers/projects.py` — add a `Trajectories` dependency
  (`Depends(trajectory_repository)`) to all four handlers; `_read` gains a `trajectories`
  parameter and calls `trajectory_export.trajectory_count(trajectories, view.id)`. This file
  stays at 171 lines +~10; it is not the capped module.
- `src/orchestrator/api/schemas/projects.py` — `ProjectRead.trajectory_count: int | None = None`
  (see Boundaries), `.of()` gains a `trajectory_count: int = 0` parameter.
- `src/orchestrator/main.py` — mount `trajectories.router` beside `history.router`.
- New tests: `tests/unit/application/test_trajectory_export.py`,
  `tests/unit/test_trajectories_schema.py`, `tests/unit/test_trajectories_router.py`,
  `tests/unit/test_project_schemas_trajectory_count.py` (new file — `test_project_schemas.py`
  is existing and not edited), `tests/e2e/test_trajectory_export.py`.

**web-client:**

- `src/pages/projects/index.astro` — 254 lines, cap 300. Add `Button` "Export trajectories"
  (`testId="projects-export"`, `href="/api/projects/{id}/trajectories.jsonl"`) beside `Edit` in
  the `filters` slot (project selected only); in the detail body, under the title/meta line, a
  `<p data-testid="projects-export-hint" class="hint">` holding the hint text and the count
  together: `one line per done story · newest first · JSON lines · {n} trajectories`.
- `src/pages/api/[...path].ts`, `src/api/server.ts` — read only; `forward` already streams
  `upstream.body` unbuffered and copies every response header except `NOT_RETURNED`
  (hop-by-hop + `content-length`/`content-encoding`) and a credential-bearing one —
  `content-disposition` already survives untouched. No code change expected; confirmed by a new
  test rather than assumed.
- `tests/e2e/stub-backend.mjs` — add a stub for `GET /api/v1/projects/{id}/trajectories.jsonl`
  answering fixed ndjson bytes with the two headers, for the download scenario.
- New tests: `tests/unit/projects-export-action.test.ts` (if the button/hint text is factored
  into a small pure helper — otherwise covered by the e2e spec alone, since `index.astro` itself
  is not unit-tested per `web-client/AGENTS.md`'s "every page has one Playwright smoke test"),
  `tests/e2e/trajectory-export.spec.ts` (new — renders, downloads, asserts filename + content).

## Tasks & Acceptance

**Execution:**
- `application/use_cases/trajectory_export.py` -- new module -- filename, count, streamed export.
- `api/schemas/trajectories.py` -- new -- the ndjson line shape.
- `api/routers/trajectories.py` -- new -- the streaming route, 404 on unknown Project.
- `api/providers.py` -- two new provider functions -- wiring, no new transaction shared with `project_ports`.
- `api/routers/projects.py` -- thread the count dependency through all four handlers.
- `api/schemas/projects.py` -- `trajectory_count` field, optional/nullable for the frozen web fixtures.
- `main.py` -- mount the new router beside `history.router`.
- `src/pages/projects/index.astro` -- the button, the hint+count line.
- `tests/e2e/stub-backend.mjs` -- the download stub.

**Acceptance Criteria:**
- Given a Project with three trajectories, when the endpoint is read, then three lines arrive
  newest first, each parses as JSON with `harness`, `model`, `attempts[]`, `human_actions[]`,
  `cost_usd`, `wall_clock_seconds`, `gate_results`, `story_file`, and the headers carry
  `application/x-ndjson` and the attachment filename.
- Given a Project with none, when read, then 200 with an empty body.
- Given an unknown Project id, when read, then a 404 problem document.
- Given the Project detail, when rendered, then *Export trajectories* links to
  `/api/projects/{id}/trajectories.jsonl`, the hint is shown, and the count reads `3 trajectories`.
- Given the proxy, when the download is requested from the browser (Playwright), then the file
  arrives with the filename and content.

## Design Notes

**"Streamed in pages of 100" without a third port method.** The port is frozen at `add` +
`list_for_project` (both the domain docstring and a pinned adapter test say so). `list_for_project`
already returns the whole Project's trajectories, newest first, in one call. `build_export`
reads that list once, then its generator yields it back to the `StreamingResponse` in
chunks of 100 rows joined as one write each — genuine paging of the *response*, not of the
query. For the volumes this endpoint serves (one row per Story, per Project), this is the
honest reading of the brief's implementation note ("over a generator paging the repository")
that does not require widening a port two other stories already relied on staying closed.

**`trajectory_count` avoids `application/use_cases/projects.py` entirely.** That module is
395/400 lines (`test_source_limits.py`). Rather than grow it to add a `trajectories` field to
`ProjectPorts`, the count is read through a second, independent FastAPI dependency
(`trajectory_repository`, `api/providers.py`) called directly from `api/routers/projects.py` —
which has room (171 lines) and already composes `use_cases.embedded_repositories` and
`project_runs.embedded_runs` from outside `ProjectPorts` in exactly this way for the Runs list.

**`trajectory_count` is nullable in the contract, not because it can be absent, but because**
`builtin` already established the pattern in this file: a defaulted *non-nullable* field is
still `required` in the generated TypeScript (`openapi-typescript`'s own behaviour, noted at
`builtin`'s definition), and two frozen web-client fixtures
(`newwf-state.test.ts`, `newwf-fields.test.ts`) construct `ProjectRead` object literals that
predate this field. `.of()` still always resolves a real `int`; nothing served is ever `null`.

</intent-contract>

## Verification

**Commands:**
- `make lint` -- exit 0
- `make test` -- exit 0
- `make openapi` -- exit 0, no drift beyond this story's own fields
- `make e2e-api` -- exit 0 (own disposable stack, `make e2e`)
- `make e2e-ui` -- exit 0; restore the Epic 5/6 deliverable PNGs `make e2e-ui` rewrites, commit none

## Auto Run Result

Status: blocked
Blocking condition: no subagents

Planning (step 2) completed: this spec is Ready for Development — Code Map, Tasks &
Acceptance and Design Notes are filled in, no anchor conflict was found (see Boundaries &
Constraints: the two risks the dispatch flagged — a closed-set equality on the Project read
model, and a placeholder on the Project screen — were both checked and neither exists here;
`test_project_schemas.py` and `test_projects_router.py` have no closed-set assertion over
`ProjectRead`'s full field set, and no "Export trajectories" placeholder was ever landed on
the Project screen). Nothing in `_bmad-output/planning-artifacts` or any anchor file was
edited.

`bmad-build-auto`'s own step 3 ("Implement") requires launching an implementation subagent —
"Using subagents when instructed is mandatory. If you cannot, HALT with status `blocked` and
blocking condition `no subagents`" (`workflow.md`, Subagents section) — and this dispatch's
operating rules state plainly, with no carve-out: "Do not spawn subagents. No background
commands, no polling loops, no Monitor, no `&`. Foreground only." No implementation code was
written; no test was written or run. `baseline_revision` above is the repository `HEAD` this
plan was drafted against, unchanged since.

**To resume:** re-dispatch with subagent use permitted, and this spec is Ready for
Development as written — step 2 does not need to be repeated.
