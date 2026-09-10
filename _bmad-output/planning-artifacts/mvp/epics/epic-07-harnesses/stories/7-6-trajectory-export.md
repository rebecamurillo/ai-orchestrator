---
title: 'Trajectory export'
type: 'feature'
created: '2026-09-10'
baseline_revision: '8f4b545876291bcf5c0552dee3d93d8ce2fcd136'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      An attempt's `cost_usd` inside a trajectory's `attempts[]` JSON blob has no
      database-level numeric constraint, so a value outside `numeric(12,6)` bounds would
      raise validating `MoneyStr` partway through the streamed response, after headers and
      some lines are already sent.
    evidence: |-
      `infrastructure/db/models/trajectory.py`'s `attempts` column is JSON, not the
      `numeric(12,6)`-typed `cost_usd` column the top-level `trajectory.cost_usd` has — so
      only the row's own total is DB-constrained, never a per-attempt figure inside the
      blob. `api/schemas/trajectories.py::AttemptRecordOut.cost_usd: MoneyStr | None` is the
      first reader anywhere in this codebase to apply that validation to the blob's
      contents; every earlier consumer (5.9's own writer, the repository adapter) round
      -trips it as opaque JSON. The gap predates this story; this story is only what makes
      it reachable through a public response for the first time.
    location: >-
      backend-api/src/orchestrator/api/schemas/trajectories.py:AttemptRecordOut
    severity: low
  - summary: >-
      The e2e scan of every Project's export line count against its `trajectory_count` has a
      narrow race: a background Run could complete a Story and write a new trajectory row
      between the list read and the per-project export read in the same test.
    evidence: |-
      `tests/e2e/test_trajectory_export.py::test_every_line_any_project_answers_parses_as_
      json_with_the_sm_fields` reads `GET /projects` once, then `GET .../trajectories.jsonl`
      for each Project in turn; the shared e2e stack has no test isolation between Runs still
      finishing in the background and this scan. Both full `make e2e-api` runs performed for
      this story were green, and the window is one HTTP round trip per Project, but the test
      is not immune to it by construction.
    location: >-
      backend-api/tests/e2e/test_trajectory_export.py:test_every_line_any_project_answers_parses_as_json_with_the_sm_fields
    severity: low
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

## Spec Change Log

_None. No `bad_spec` finding was raised in review._

## Review Triage Log

### 2026-09-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2 (high 0, medium 1, low 1)
- defer: 2 (high 0, medium 0, low 2)
- reject: 6
- addressed_findings:
  - `[medium]` `[patch]` No router-level test proved `GET /projects` (the list operation,
    `api/routers/projects.py::list_projects`) assigns each row its *own* `trajectory_count`
    rather than leaking a value between loop iterations — the frozen `test_projects_router.py`
    predates the field and asserts nothing about it, and every test written so far exercised
    either the schema directly or a single-Project read. Fixed by adding
    `tests/unit/test_projects_router_trajectory_count.py` (3 tests: two Projects with
    different nonzero counts on the list read, a single Project's own count on `GET
    /projects/{id}`, and a zero-count Project beside a nonzero one to catch value bleed
    across the loop).
  - `[low]` `[patch]` The singular branch of the count text (`"1 trajectory"`, no `s`) was
    never exercised by any test — the one e2e scenario asserting the hint only ever used
    `EXPORT_TRAJECTORY_COUNT = 3`. Fixed by extracting the text logic out of `index.astro`'s
    frontmatter into `web-client/src/lib/projects/export.ts::trajectoryCountText`
    (`lib/projects/runs.ts`'s own established pattern for pulling pure logic out of a page so
    it unit-tests without rendering), with a new `tests/unit/projects-export-lib.test.ts`
    covering `0`, `1`, and `3`.

Two findings were deferred rather than patched, both low severity and both pre-existing
conditions this story's new code is the first to make reachable rather than causing outright:
`deferred` (frontmatter) records both. Six further candidates considered during the pass
(cosmetic field ordering, the harmlessness of an empty `repositories: []` fixture, no
explicit 405 test, a project-deleted-mid-request race that degrades to an empty list rather
than an error, router mount ordering, and UUID path-parameter safety) were rejected as
non-issues on inspection and are not itemized further.

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
(`trajectory_repository`, in a new sibling module `api/providers_trajectories.py` rather than
in `api/providers.py` itself — that module is *also* capped, at 391/400 — called directly
from `api/routers/projects.py`, which has room (171→188 lines) and already composes
`use_cases.embedded_repositories` and `project_runs.embedded_runs` from outside `ProjectPorts`
in exactly this way for the Runs list.

**`trajectory_repository` is read tolerantly, `None` rather than raising, when the
application has no database session factory** — `api/providers.py::git_adapter`'s own
precedent for an optional adapter. Discovered only once the router was actually wired: the
frozen `test_projects_router.py` builds its application with no `session_factory` at all and
overrides only `project_ports`, so a hard-required second dependency on the same four route
handlers would have 500'd every one of its 27 tests on a capability that predates it and that
file cannot be edited to know about. `trajectory_count(None, ...)` answers `0`, the same
precedent `embedded_repositories`/`embedded_runs` already set for their own optional ports.

**`trajectory_count` is nullable in the contract, not because it can be absent, but because**
`builtin` already established the pattern in this file: a defaulted *non-nullable* field is
still `required` in the generated TypeScript (`openapi-typescript`'s own behaviour, noted at
`builtin`'s definition), and two frozen web-client fixtures
(`newwf-state.test.ts`, `newwf-fields.test.ts`) construct `ProjectRead` object literals that
predate this field. `.of()` still always resolves a real `int`; nothing served is ever `null`.

## Verification

**Commands:**
- `make lint` -- exit 0
- `make test` -- exit 0
- `make openapi` -- exit 0, no drift beyond this story's own fields
- `make e2e-api` -- exit 0 (own disposable stack, `make e2e`)
- `make e2e-ui` -- exit 0; restore the Epic 5/6 deliverable PNGs `make e2e-ui` rewrites, commit none

## Auto Run Result

Status: done
Blocking condition: none

**Deviation from `bmad-build-auto`'s own step 3 and step 4, noted rather than halted on.**
This dispatch was first halted `blocked` (`no subagents`) because step 3 ("Implement")
instructs launching a fresh implementation subagent and step 4 ("Review") instructs launching
four reviewer subagents, and the operating rules said plainly "Do not spawn subagents." The
coordinator clarified in the same run that the rule targets process deadlock (a prior epic's
agent backgrounded a child and then blocked waiting on it after it had already finished), not
authorship, and that step 3 and step 4's instructions apply to this session directly. Both
steps were therefore executed inline, in this session, exactly as stories 7-1, 7-2, 7-3 and
7-5 record doing on this epic. No subagent was spawned at any point.

### Summary

`GET /api/v1/projects/{id}/trajectories.jsonl` (streamed `application/x-ndjson`, newest
first, paged 100 at a time, 404 for an unknown Project, 200 empty body for none) and the
*Export trajectories* bar action on the Project screen, with its hint and a `trajectory_count`
reading. No anchor conflict: both risks the dispatch flagged (a closed-set equality on the
Project read model; a placeholder on the Project screen) were checked and neither existed.

### Files changed — backend-api

- `src/orchestrator/application/use_cases/trajectory_export.py` (new) — `trajectory_count`,
  `export_filename`, `TrajectoryExportPorts`, `prepare_export`.
- `src/orchestrator/api/schemas/trajectories.py` (new) — `TrajectoryLineOut` and its four
  small nested `…Out` models, mirroring every `Trajectory` field with `MoneyStr`/`UtcTimestamp`.
- `src/orchestrator/api/routers/trajectories.py` (new) — the one `GET` operation, the
  `StreamingResponse`, the `Content-Disposition` header, paging the response in chunks of 100.
- `src/orchestrator/api/providers_trajectories.py` (new) — `trajectory_repository` (read
  tolerantly, `None` without a session factory — `git_adapter`'s own precedent) and
  `trajectory_export_ports` (required, like every other feature's ports). A sibling of
  `api/providers.py` rather than an addition to it: that module is 391/400 lines.
- `src/orchestrator/api/routers/projects.py` — threads a `Trajectories` dependency through
  all four handlers; `_read` gains a `trajectories` parameter.
- `src/orchestrator/api/schemas/projects.py` — `ProjectRead.trajectory_count: int | None`
  (nullable on `builtin`'s own precedent, for the frozen web-client fixtures); `.of()` gains
  a `trajectory_count: int = 0` parameter.
- `src/orchestrator/main.py` — mounts `trajectories.router` beside `history.router`.
- New tests: `tests/unit/application/test_trajectory_export.py` (8),
  `tests/unit/test_trajectories_schema.py` (7), `tests/unit/test_trajectories_router.py` (7),
  `tests/unit/test_api_providers_trajectories.py` (4),
  `tests/unit/test_project_schemas_trajectory_count.py` (4),
  `tests/unit/test_projects_router_trajectory_count.py` (3, added in review — see Review
  Triage Log), `tests/e2e/test_trajectory_export.py` (5).

### Files changed — web-client

- `src/pages/projects/index.astro` — *Export trajectories* button beside *Edit* in the bar
  (Project selected only); the hint + count line under the title/meta in the detail body.
- `src/lib/projects/export.ts` (new, added in review) — `trajectoryCountText`, extracted out
  of the page frontmatter so the singular/plural text is unit-tested without rendering.
- `tests/e2e/projects-fixtures.mjs` — `trajectory_count: 0` default on every fixture, and a
  new dedicated `EXPORT`/`EXPORT_ID` fixture (`trajectory_count: 3`) — never shared with
  `MIXED_ID`, `MIXED_RECHECK_REPO_ID`'s own precedent for why.
- `tests/e2e/stub-backend.mjs` — `GET /api/v1/projects/{id}/trajectories.jsonl`, answering
  `trajectory_count` sample lines with the two headers; deliberately *not* handled by
  `page.route()` in the new spec, so the download crosses the real Astro proxy.
- New tests: `tests/unit/projects-export-lib.test.ts` (3, added in review),
  `tests/e2e/trajectory-export.spec.ts` (3).

### Review findings (step 4, run inline — see `## Review Triage Log` for the full entry)

- **patch (2, both fixed in this pass):** a verification gap — no test proved `GET /projects`
  assigns each row its own `trajectory_count` rather than leaking one across the loop — closed
  by `test_projects_router_trajectory_count.py`; and an untested singular-text branch — closed
  by extracting `trajectoryCountText` into its own module with a dedicated unit test.
- **defer (2, both low, both pre-existing conditions this story's new code is the first to
  make reachable):** an attempt's `cost_usd` inside the JSON `attempts[]` blob has no
  database-level numeric bound, so an out-of-range value would raise `MoneyStr` validation
  mid-stream; and the e2e Project-scan test has a narrow, unhit-so-far race against a
  background Run completing between its list read and its per-project export read. Both
  recorded in frontmatter `deferred`.
- **reject (6):** cosmetic field ordering, an empty-`repositories` fixture, no explicit 405
  test, a project-deleted-mid-request race (degrades to an empty list, not an error), router
  mount ordering, and UUID path-parameter safety — each inspected and found to be a non-issue.
- **Follow-up review recommendation:** `false`. This pass's patched findings score
  `3 × 1 (medium) + 1 × 1 (low) = 4`, under the threshold of 5, and none was `high`.

### Verification — every gate run in the foreground, exit code observed directly, twice
(once before the review patches, once after)

- `make lint` — exit 0. ruff check/format, mypy --strict over `domain/` + `application/`
  (122 files), import-linter 4/4 contracts kept, env contract (37 settings / 43 vars),
  `check_test_pairs` 213 backend + 96 web-client modules paired, `gen:api --check` no drift,
  astro check 244 files/0 errors, eslint, prettier.
- `make test` — exit 0. Backend 5980 passed, 1 skipped; `domain/` + `application/` at 100%
  branch coverage (`--fail-under=100`, `trajectory_export.py` itself 100%); web-client 101
  files / 1289 tests passed.
- `make openapi` — exit 0; `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerated, `trajectory_count` and the new route present in both.
- `make e2e-api` — exit 0, via `make e2e` in its own disposable `aio-e2e` stack: 220 passed,
  11 deselected, 40 subtests, including this story's own `tests/e2e/test_trajectory_export.py`
  and schemathesis over the new route.
- `make e2e-ui` — exit 0: 180 passed, 1 skipped, including the 3 new
  `trajectory-export.spec.ts` scenarios (bar action + hint render, no-selection render, and a
  real browser download through the actual Astro proxy). The Epic 5/6 deliverable PNGs it
  rewrites were restored with `git checkout` both times it ran; none is committed.

### Residual risks

- The two deferred findings above (both low, both frontmatter `deferred`).
- `PAGE_SIZE = 100` chunks the *response*, not the database query (see Design Notes): a
  Project with an unusually large trajectory count still reads the whole list into memory in
  `prepare_export` before streaming. Acceptable at "one row per Story, per Project" volumes;
  would need the port widened (an Operator ruling, since the port is frozen at two methods)
  if that assumption stops holding.
