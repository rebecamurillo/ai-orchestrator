---
title: 'Run read models for the board, the detail, and the run graph'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      `run_detail` and the Board's `_card` each issue one repository call per row/Run
      (N+1), with no batch-fetch method on any repository port.
    evidence: |-
      `run_detail` builds `attempts_by_row` with one `ports.attempts.list_for_row(row.id)`
      call per planned row, on top of separate `runs.get`/`steps.list_for_run`/
      `projects.get`/`repositories.get`/`gate_records.list_for_run` calls; `_card` calls
      `ports.steps.list_for_run`, `ports.projects.get`, `ports.repositories.get`, and (when
      parked) `ports.gate_records.list_for_run` once per Run returned by `ports.runs.list`.
      This matches the codebase's existing pattern (`application/use_cases/project_runs.py
      ::embedded_runs` does the same per-Run `steps.list_for_run` fan-out) rather than
      introducing a new one, so it is not a regression this story caused alone, but it is
      real and worth a batch-fetch port method later if the Board or a Run's row count
      grows.
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_views.py (`run_detail`, `_card`)
    severity: medium
  - summary: >-
      The Board has no bound on how many `done`/`failed` Runs it returns — every stored Run
      for the (optionally project-scoped) query, forever.
    evidence: |-
      `board_view` calls `ports.runs.list(project_id=project_id)` with no limit, unlike
      `application/use_cases/project_runs.py::EMBED_LIMIT` (20) for the Project screen's own
      Runs list. SPEC CAP-14 says "five columns always rendered" but does not say the
      `done`/`failed` columns are bounded, so this is a genuine open question for whichever
      story renders the Board screen (4.14) rather than something this story's brief asked
      it to decide.
    location: 'backend-api/src/orchestrator/application/use_cases/run_views.py:board_view'
    severity: medium
  - summary: >-
      `run_read_ports` and `run_view_ports` (`api/providers.py`) each open their own
      `SQLAlchemyUnitOfWork` and independently instantiate the same three repository
      adapters (`Project`, `Repository`, `GateRecord`), rather than sharing one "read
      adapters" helper.
    evidence: |-
      Compare `run_read_ports` (lines ~181-191) and `run_view_ports` (lines ~195-208):
      both build `SQLAlchemyProjectRepository(uow.session)`,
      `SQLAlchemyRepositoryRepository(uow.session)`, `SQLAlchemyGateRecordRepository(
      uow.session)` from scratch. Structural duplication, not a correctness bug — flagged
      by the blind-hunter review pass, not trivially fixable without touching both existing
      provider functions and their dependent tests' override targets.
    location: 'backend-api/src/orchestrator/api/providers.py'
    severity: low
  - summary: >-
      `HeaderMetaOut.folder` cannot distinguish a legitimately empty `spec_folder` input
      from an absent one — both fall through the same `or`-chain to `initiative_folder`.
    evidence: |-
      `_header` in `run_views.py` computes `str(run.inputs.get("spec_folder") or
      run.inputs.get("initiative_folder") or "")`. `spec_folder`/`initiative_folder` are
      declared `required: true` on every shipped Template that binds one, so an empty
      string is not reachable through today's Templates — low-likelihood edge case, not
      worth added complexity for a display-only header field in this story.
    location: 'backend-api/src/orchestrator/application/use_cases/run_views.py:_header'
    severity: low
  - summary: >-
      A Template step literally named `root` would collide with the run graph's synthetic
      root node id, breaking the "node id is the join key" invariant (AD-15) for that one
      Run.
    evidence: |-
      `application/graph.py::ROOT_ID = "root"`; `_row_node` uses `row.path` verbatim as a
      node's id with no collision check against `ROOT_ID`. No shipped Template
      (`repo-init`, `epic`, `story`, `initiative`) has a step id `root`, so this is
      unreachable today; closing it properly means either a collision-proof id scheme or
      validator-level enforcement, a design decision beyond a read-model story's scope.
    location: 'backend-api/src/orchestrator/application/graph.py:ROOT_ID,_row_node'
    severity: low
baseline_revision: '9b6b7e751b1f7dd6d898776f6566330f3dc4234c'
---

<intent-contract>

## Intent

**Problem:** The Board, the Run detail screen, and the run diagram each need one endpoint shaped for them so the browser reads once per screen and never aggregates or re-derives status.

**Approach:** Add pure builders in a new `application/use_cases/run_views.py` (board + detail) and `build_run_graph` beside `build_template_graph` in `application/graph.py`; wire three GETs: `GET /runs?view=board&project_id=` (existing route, new query param), `GET /runs/{run_id}/detail` (new route — see Boundaries), `GET /runs/{run_id}/graph` (new route on the existing `graph.router`).

## Boundaries & Constraints

**Always:** Reuse `application/rules/frames.py::epic_frame/story_frame/rows_in_frame` for every frame/group computation — do not re-derive path parsing. Node id = `step_run.path`, byte for byte. `application/graph.py` stays the one module for both graph builders. The group-status rule is one function (`group_status`), unit-tested directly for all 7 branches, called by nothing else that restates it. Step tokens: `planned/queued`→QUE, `running`→RUN, `done`→DON, `blocked`→BLK, `checkpoint`→CHK, `error`→ERR, `skipped`→SKP. Run/root/Card tokens: `queued`→QUE, `running`→RUN, `done`→DON, `failed`→ERR, `cancelled`→CAN, `needs_you`→CHK if `park_kind=="checkpoint"` else BLK (same rule as `application/use_cases/project_runs.py::_token`, duplicated locally per that module's own precedent, not imported). `log_tail` goes through a new `LogReader` port (`domain/ports/logs.py`, adapter `infrastructure/process/logs.py::RealLogReader.tail`), never a direct file read from `application/`. New ports get a fake in `tests/unit/fakes/`.

**Block If:** none — every ambiguity below is resolved, not deferred.

**Never:** touch `SPEC.md`, `stories.yaml`, `epics.yaml`, any `AGENTS.md`, or an existing test file. Do not change `GET /runs/{run_id}`'s existing response shape (`RunSummaryOut`, in `api/routers/run.py`) or `POST /runs`'s `CreateRunOut.run` shape — see Design Notes, "the detail is a new route, not a bigger `/runs/{id}`". Do not add screens (4.13–4.16) or history/activity (Epic 7/8).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Board, mixed statuses | Runs in every status incl. one `cancelled` | each in its column once; cancelled under `failed` with `CAN`; `needs_you` on `checkpoint` park is `CHK` | n/a |
| Board progress | initiative Run, 2 epics, 8 stories, 3 stories done, 1 epic pushed | `progress == {epics_done:1, epics_total:2, stories_done:3, stories_total:8, links:1}` | n/a |
| Board progress, non-epic Run | `repo-init` Run | `progress is None` | n/a |
| Detail, retried row | a row with 3 attempts | `StepRow.attempts == 3`, `latest.n == 3`, `latest.log_tail` is the last 40 lines | n/a |
| Detail, done+skip | `done` Run, one skipped story | `summary.skipped == [story_id]`, `summary.links == list(compare_urls)` | n/a |
| Graph, mixed | epic Run, mixed row states | each group's `status` by `group_status`; `current` on the park row | n/a |
| Graph, cancelled | `cancelled` Run | every `Group.status is None`; root `Node.token == "CAN"` | n/a |
| Unknown run id | any of the three GETs, unknown `{run_id}` | 404 problem document | 404 |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/graph.py` — `build_template_graph` (L167), `Node`/`Group`/`Graph` (L94-145, frozen pydantic). Add: `status: str | None`, `token: str | None`, `current: bool = False` to `Node`; `status: str | None` to `Group`; `build_run_graph(rows: Sequence[StepRun], run: Run) -> Graph`; exported `group_status(statuses: Sequence[StepStatus]) -> str` (the one rule); a local `_run_token(run: Run) -> str` (root token, same shape as `project_runs.py::_token`). Root node: one synthetic node, id `"root"`, label `run.template_name`, `status=run.status`, `token=_run_token(run)`, `gate=None`, chained via reused `_chain()` to `rows[0].path` then through `rows` in `seq` order (edges "follow seq"). Groups: for every distinct `epic_frame`/`story_frame` prefix over `rows` (via `application/rules/frames.py`), one `Group(id=prefix, label=prefix, members=[r.path for r in rows_in_frame(rows, prefix)], status=None if run.status=="cancelled" else group_status([r.status for r in rows_in_frame(rows, prefix)]))`. `current = row.status=="running" or row.path==run.park_path`.
- `backend-api/src/orchestrator/application/rules/frames.py` — `epic_frame`, `story_frame`, `in_frame`, `rows_in_frame` (reuse verbatim, do not re-derive).
- `backend-api/src/orchestrator/application/steps/__init__.py` — `COMMIT_KIND="git.commit"`, `PUSH_KIND="git.push"`, `AGENT_KIND`, `CHECKPOINT_KIND` (reuse for progress + Node.agent/human).
- `backend-api/src/orchestrator/application/rules/signals.py::run_admitted_signals(run, park_row_kind)` — reuse for `admitted_signals` in the detail model (same as `RunSummaryOut`).
- `backend-api/src/orchestrator/application/use_cases/project_runs.py` — `_token`/`_TOKENS` pattern to replicate locally (not import — established local-duplication convention in this codebase).
- `backend-api/src/orchestrator/application/use_cases/queue.py` — the pattern to follow: a frozen `*Ports` dataclass, one pure builder, small private helpers.
- `backend-api/src/orchestrator/domain/entities/run.py` — every `Run` field (no changes).
- `backend-api/src/orchestrator/domain/entities/step_run.py` — `path, seq, label, kind, gate, status, frame, story_id` (no changes).
- `backend-api/src/orchestrator/domain/entities/attempt.py`, `gate_record.py` — no changes; read-only sources for `StepRow.latest`/`gate_record`.
- `backend-api/src/orchestrator/domain/ports/repositories.py` — `RunRepository.list(project_id=)`, `.get`; `StepRunRepository.list_for_run`; `AttemptRepository.list_for_row`; `GateRecordRepository.list_for_run` — all sufficient as-is.
- `backend-api/src/orchestrator/domain/ports/logs.py` — **new**: `LogReader` Protocol, `tail(path: str, n: int) -> list[str]`.
- `backend-api/src/orchestrator/infrastructure/process/logs.py` — **new**: `RealLogReader.tail` — open the file at `path`, return the last `n` lines (`[]` if `path` is `None`/missing).
- `backend-api/src/orchestrator/application/steps/context.py::log_path` (L166) — how a log file's path is derived; `Attempt.log_path` is the stored pointer this story reads back.
- `backend-api/src/orchestrator/api/routers/run.py` — `list_runs` (existing `GET /runs`, `response_model=Page[RunSummaryOut]`): add `view: Literal["board"] | None = None`, `project_id: UUID | None = None` query params; when `view=="board"` call `board_view` and return `BoardOut`; change `response_model` to `Page[RunSummaryOut] | BoardOut`. Frozen route-count test (`tests/unit/test_run_router.py::test_the_router_declares_exactly_the_three_operations`) is unaffected — no new route.
- `backend-api/src/orchestrator/api/routers/graph.py` — add `GET /runs/{run_id}/graph` (frozen test uses containment, not an exact list — safe; see its own docstring).
- `backend-api/src/orchestrator/api/routers/run_detail.py` — **new** router, `GET /runs/{run_id}/detail`, mounted like `queue.router`.
- `backend-api/src/orchestrator/api/schemas/graph.py` — add `RunNodeOut`/`RunGroupOut`/`RunGraphOut` (new classes; `NodeOut`/`GroupOut`/`GraphOut` stay untouched — see Design Notes on why).
- `backend-api/src/orchestrator/api/schemas/run_views.py` — **new**: `CardOut`, `BoardOut`, `StepRowOut`, `StoryCellOut`, `CostOut`, `GateRecordOut`, `HeaderOut`, `AlertOut`, `SummaryOut`, `RunDetailOut`.
- `backend-api/src/orchestrator/api/providers.py` — add `run_view_ports(request) -> Iterator[RunViewPorts]`, same shape as `queue_ports`.
- `backend-api/src/orchestrator/main.py` — add `run_detail` to the router import block; `_mount(app, run_detail.router)` beside `run.router, signals.router, harnesses.router, queue.router`.
- `backend-api/tests/unit/fakes/logs.py` — **new**: `FakeLogReader` (canned `{path: [lines]}`).
- `backend-api/tests/unit/fakes/runs.py`, `projects.py` — reuse as-is (`FakeRunRepository`, `FakeStepRunRepository`, `FakeAttemptRepository`, `FakeGateRecordRepository`, `FakeProjectRepository`, `FakeRepositoryRepository`).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/ports/logs.py` -- add `LogReader` Protocol -- ports-first rule.
- `backend-api/src/orchestrator/infrastructure/process/logs.py` -- add `RealLogReader` -- the adapter `LogReader` needs.
- `backend-api/tests/unit/fakes/logs.py` -- add `FakeLogReader` -- unit tests need a double.
- `backend-api/src/orchestrator/application/graph.py` -- add `build_run_graph`, `group_status`, extend `Node`/`Group` -- CAP-12 graph.
- `backend-api/tests/unit/application/test_run_graph.py` -- new: node ids/tokens, `current`, `group_status` all 7 branches directly, cancelled → null groups + root `CAN` -- TDD for the graph.
- `backend-api/src/orchestrator/application/use_cases/run_views.py` -- add `RunViewPorts`, `board_view`, `run_detail`, dataclasses -- CAP-12 board+detail.
- `backend-api/tests/unit/application/test_run_views.py` -- new: every I/O-matrix row above as a pure-builder test -- TDD for board+detail.
- `backend-api/src/orchestrator/api/schemas/graph.py` -- add `RunNodeOut`/`RunGroupOut`/`RunGraphOut` -- wire (AD-3), without touching the frozen `GroupOut`/`NodeOut`.
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- add the board/detail wire schemas -- wire (AD-3).
- `backend-api/src/orchestrator/api/providers.py` -- add `run_view_ports` -- DI for the three routes.
- `backend-api/src/orchestrator/api/routers/run.py` -- extend `list_runs` with `view`/`project_id` -- CAP-12 board route.
- `backend-api/src/orchestrator/api/routers/run_detail.py` -- new router, `GET /runs/{run_id}/detail` -- CAP-12 detail route.
- `backend-api/src/orchestrator/api/routers/graph.py` -- add `GET /runs/{run_id}/graph` -- CAP-12 graph route.
- `backend-api/src/orchestrator/main.py` -- mount `run_detail.router` -- wire the new router.
- `backend-api/tests/unit/test_run_board_view_router.py` -- new: ASGI tests for `GET /runs?view=board` -- TDD, does not touch `test_run_router.py`.
- `backend-api/tests/unit/test_run_detail_router.py` -- new: ASGI tests for `GET /runs/{id}/detail` -- TDD.
- `backend-api/tests/unit/test_run_graph_router.py` -- new: ASGI tests for `GET /runs/{id}/graph` -- TDD.
- `make openapi` -- regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts` -- AD-3.

**Acceptance Criteria:**
- Given Runs in every status incl. one `cancelled`, when `GET /runs?view=board` is read, then each appears once in its column, the cancelled one under `failed` with `token: CAN`, `counts` are right, and a `needs_you` Run parked on `checkpoint` reads `CHK`.
- Given an initiative Run (2 epics, 8 stories, 3 stories done, 1 epic pushed), when the board card is read, then `progress == {epics_done:1, epics_total:2, stories_done:3, stories_total:8, links:1}` and `current_step_label` names the running row.
- Given a Run with a row at 3 attempts, when `GET /runs/{id}/detail` is read, then `StepRow.attempts == 3`, `latest.n == 3` with the last 40 log lines, and `admitted_signals` matches the park.
- Given a `done` Run with one skipped story, when read, then `summary.skipped` lists its `story_id` and `summary.links` is `list(compare_urls)`.
- Given an epic Run with rows in mixed states, when `GET /runs/{id}/graph` is read, then every group's `status` matches `group_status` for each of its 7 branches (tested directly), `current` marks the park row, and — for a `cancelled` Run — every `Group.status is None` and the root `Node.token == "CAN"`.
- Given the contract, when `make openapi` runs, then the three read models are generated into `schema.d.ts` with no drift.

## Spec Change Log

_None yet._

## Review Triage Log

### 2026-09-07 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9 (high 0, medium 2, low 7)
- defer: 5 (medium 2, low 3)
- reject: 6
- addressed_findings:
  - `[low]` `[patch]` `group_status([])` returned `skipped` (vacuous `all()` over an empty
    sequence) instead of `queued` — guarded with an explicit empty check and a direct unit
    test (edge-case-hunter).
  - `[medium]` `[patch]` `RealLogReader.tail` could raise an unhandled `OSError` if the log
    file is removed between its `is_file()` check and the read (e.g. a `worktree_gc` race)
    — wrapped in `try/except OSError`, with a test that races the read (edge-case-hunter).
  - `[low]` `[patch]` `api/providers.py::run_view_ports`'s docstring wrongly said it served
    the Board too; the Board reads through `run_read_ports` — corrected (verification-gap).
  - `[medium]` `[patch]` `GET /runs?project_id=` (no `view=board`) filtered runs but had no
    test, and neither branch had a test for a malformed `project_id` returning 422 —
    added both, plus end-to-end tests proving `project_name`/`repository_slug`/
    `needs_you_since` actually come through the real `run_read_ports` wiring, not only the
    pure-function tests (verification-gap, blind-hunter).
  - `[low]` `[patch]` The Board-progress test used 4 stories where the story's own
    acceptance criterion names 8 — rewritten to match the AC verbatim (intent-alignment).
  - `[low]` `[patch]` `RunDetailSummaryOut.of_run` hand-duplicated `RunSummaryOut.of`'s
    nine-field mapping — refactored to build on `RunSummaryOut.of(...).model_dump()` so the
    two cannot drift (blind-hunter).
  - `[low]` `[patch]` `Cost.trace_url` was typed as the narrower `None` rather than
    `str | None`, foreclosing a later story setting it without a type change — widened
    (blind-hunter).
  - `[low]` `[patch]` `_frame_is_current` relied on the implicit fact that `row.path` is
    never `None` where `application/graph.py::_is_current` states the same "current" rule
    with an explicit `park_path is not None` guard — made explicit for consistency
    (blind-hunter).
  - `[low]` `[patch]` `api/routers/graph.py::run_graph` did its own `runs.get`/`None` check
    inline, unlike `run_detail`'s and `create_run.py::get_run`'s established pattern of
    raising `NotFound` at the application layer — extracted `run_views.py::run_graph_for`
    so the router stays a thin parse-call-map (blind-hunter).
- deferred: N+1 reads in `run_detail`/the Board (medium, pre-existing codebase pattern); no
  bound on the Board's `done`/`failed` columns (medium, a Board-screen-story decision, not
  this one's); duplicated adapter wiring between `run_read_ports`/`run_view_ports` (low);
  `HeaderMetaOut.folder`'s empty-vs-absent ambiguity (low, unreachable via any shipped
  Template); a Template step literally named `root` colliding with the run graph's
  synthetic root id (low, unreachable via any shipped Template). Full detail in frontmatter
  `deferred`.
- rejected: a fourth small local copy of the Run→token mapping (deliberate, precedented,
  already documented in three places' own docstrings); silently blanking
  `project_name`/`repository_slug` to `""` for a missing Project/Repository (matches
  `project_runs.py::embedded_runs`'s own established "graceful, never a stale placeholder"
  convention); `summary` excluded for `failed`/`cancelled` Runs (the brief states "when
  done" explicitly — not a gap); the wider field surface the intent-alignment auditor
  flagged as absent from the condensed intent-contract (`Header`/`Alert`/`Cost`/`StoryCell`/
  `GateRecord`) — the auditor saw only the intent-contract, not this story's full brief,
  which names these fields explicitly (FR-22/23/28, SPEC CAP-12/15); the file-layout split
  wider than the Approach section's literal two modules (already justified in Design Notes:
  the 400-line module limit); `_bracket_index`'s local regex (operates on `epic_frame`'s own
  output, not a second path-parsing pass).

## Design Notes

**Why the full detail is `GET /runs/{run_id}/detail`, not a bigger `GET /runs/{run_id}`.** The brief names the endpoint `GET /runs/{id}` (full). `api/routers/run.py`'s existing `GET /runs/{run_id}` is pinned by two frozen tests in `tests/unit/test_run_router.py`: `test_get_reads_the_run_just_created` asserts `response.json() == created["run"]` (byte-for-byte equality with `POST /runs`'s embedded `RunSummaryOut`), and `test_post_creates_and_enqueues_a_repo_init_run` asserts `body["run"]["status"|"template"|"version"|"budget_usd"|"id"]` as direct keys of that same minimal object. Any top-level enrichment of `GET /runs/{run_id}` — nested `run`/`header`/`steps`/`cost`/... siblings, as the brief's own shape requires — makes it stop being byte-equal to `created["run"]`, breaking the first test; nesting `RunSummaryOut`'s fields one level deeper to compensate breaks the second. No query-parameter variant threads this either: the equality test carries no query string, so any *default* change to that route's response still breaks it, and a `?view=full`-style opt-in makes the contract's default behavior invisible at the one path the brief names, while equally deviating from the brief's literal text. `api/schemas/runs.py`'s own docstring already anticipated this by name — "`RunSummaryOut` is the 'minimal' read model the brief asks for; the full one is 4.12's" — without claiming the full model reuses the same route. Per hard rule 1, no exception applies (the test names no later story), so the spine wins: `GET /runs/{run_id}` keeps its current minimal shape verbatim, and the full detail model is served at a new sibling path, `GET /runs/{run_id}/detail`, on a new router module (the same "new routes go in a new module" resolution 4-4/4-9/4-10/4-11 already used for their own frozen route-count tests). Story 4-15 (Run detail core) must call `GET /runs/{run_id}/detail`, not `GET /runs/{run_id}`.

**Board view stays on `GET /runs`.** `?view=board` is the same path Starlette already routes to `run.py::list_runs`, so unlike the detail model there is no way to put it elsewhere — it is implemented as new optional query parameters on the existing handler, with `response_model=Page[RunSummaryOut] | BoardOut` (a union) so the plain, no-`view` request keeps its exact existing shape (`test_list_answers_every_stored_run` is untouched) and `?view=board` returns the new shape. No new route, so `test_the_router_declares_exactly_the_three_operations` is unaffected.

**`needs_you_since`** has no dedicated stored column. It is read as the `.at` of the most recent `gate_record` whose `event == run.park_kind` for this run (`GateRecordRepository.list_for_run`, oldest-first, take the last match) — the only place this timestamp is durably recorded (AD-8's append-only gate record).

**The group landmine (per the operator's brief).** Run-graph groups nest two deep (`epics[i]` contains `epics[i].stories[j]`), which Epic 3's post-hoc-bounding-box diagram approach cannot render correctly once one group's members interleave with another's on rank — this is `application/graph.py`'s `Group` staying a flat list either way (same shape 3.4 already returns), so this story's read model does not make that harder than it already is; the fix (dagre `compound`/`setParent`) is Epic 8's, per the hand-off.

**The run graph gets its own wire schema; `NodeOut`/`GroupOut` are untouched.** The brief's implementation note says to "add optional `status`, `token`, `current` fields to `Node` and `status` to `Group`" — done, but only on the `application/graph.py` dataclasses. `api/schemas/graph.py::GroupOut` is pinned by two existing tests with exact-dict equality on the *whole* serialized group — `tests/unit/test_graph_schemas.py::test_a_group_carries_its_label_and_its_construct_onto_the_wire` (`body["groups"] == [{"id", "label", "kind", "members"}]`, four keys, nothing else) and `tests/unit/test_graph_router.py`'s own `body["groups"] == [...]` assertion for `caller/1/graph`. FastAPI serializes a `response_model` with every field, `None` included (`response_model_exclude_none` is not set on that route), so any new `GroupOut` field — populated or not — appears as an extra key and breaks both, and neither test names 4.12 as what replaces it, so no hard-rule-1 exception applies. The resolution: `NodeOut`/`GroupOut`/`GraphOut` for the *template* graph stay exactly as they are; the run graph gets its own `RunNodeOut`/`RunGroupOut`/`RunGraphOut` in the same file, each built from the *same* `application/graph.py` `Node`/`Group`/`Graph` the template graph uses — "reuse the Graph schema" is kept at the application layer, where the brief's own hand-off note lives, not forced onto a wire type an existing test already pins shut.

**`Node.status`/`Node.token` share one field pair across two alphabets.** Per-row nodes use `StepStatus`/step tokens (QUE/RUN/DON/BLK/CHK/ERR/SKP); the one synthetic root node uses `RunStatus`/run tokens (QUE/RUN/DON/ERR/CAN/BLK/CHK) — both fields stay plain `str | None` on `Node`, documented in its docstring, since a cancelled Run's root token `CAN` has no equivalent in `StepStatus` at all (this is the textual proof the root is Run-scoped, not row-scoped).

## Verification

**Commands:**
- `make lint` -- expect: clean (ruff, mypy strict on domain/application, import-linter, env-contract, eslint/prettier/tsc, contract drift check)
- `make test` -- expect: green, 100% branch on domain/application
- `make openapi` -- expect: no drift in `contracts/openapi.json` / `web-client/src/api/schema.d.ts`
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- expect: green
- `make e2e-ui` -- expect: green (no assertions on this story's endpoints yet — screens land in 4.13-4.16 — but the build/preview must still succeed)

## Auto Run Result

Status: done

**Summary.** Three new/extended read-only surfaces on `GET /api/v1/runs`: `?view=board` (existing route, new query param) for the Board, `GET /runs/{run_id}/detail` (new route) for the full Run detail, `GET /runs/{run_id}/graph` (new route on the existing `graph.router`) for the run graph. `build_run_graph` and its one rule, `group_status`, live beside `build_template_graph` in `application/graph.py`. `GET /runs/{run_id}` (minimal `RunSummaryOut`) is untouched — see Design Notes for why the full model could not land on that literal route.

**Files changed** (backend-api, all paths relative to `backend-api/`):
- `src/orchestrator/application/graph.py` — `build_run_graph`, `group_status`, `_run_token`, `_run_node`/`_row_node`/`_group`/`_group_prefixes`; `Node`/`Group` moved to `graph_schema.py` (line-count split).
- `src/orchestrator/application/graph_schema.py` — new: `Node`, `Edge`, `Group`, `Graph`, `NodeCall` and their constants (re-exported from `graph.py`).
- `src/orchestrator/application/use_cases/run_views.py` — new: `board_view`, `run_detail`, `run_graph_for`, every private builder helper.
- `src/orchestrator/application/use_cases/run_view_types.py` — new: `RunViewPorts`, `Card`, `BoardView`, `Header`, `Alert`, `StepRowView`, `StoryCell`, `Cost`, `Summary`, `RunDetailView`, `Progress` (line-count split from `run_views.py`).
- `src/orchestrator/application/use_cases/create_run.py` — `RunReadPorts` gains optional `projects`/`repositories`/`gate_records` fields for the Board.
- `src/orchestrator/domain/ports/logs.py` — new: `LogReader` port.
- `src/orchestrator/infrastructure/process/logs.py` — new: `RealLogReader` adapter (race-safe on a concurrent `worktree_gc`).
- `src/orchestrator/api/schemas/graph.py` — new `RunNodeOut`/`RunGroupOut`/`RunGraphOut` (template graph's `NodeOut`/`GroupOut`/`GraphOut` untouched).
- `src/orchestrator/api/schemas/run_views.py` — new: every Board/detail wire schema.
- `src/orchestrator/api/schemas/runs.py` — unchanged (referenced by `RunDetailSummaryOut`, which subclasses `RunSummaryOut`).
- `src/orchestrator/api/routers/run.py` — `list_runs` gains `view`/`project_id` query params and a union response model.
- `src/orchestrator/api/routers/run_detail.py` — new router, `GET /runs/{run_id}/detail`.
- `src/orchestrator/api/routers/graph.py` — new route `GET /runs/{run_id}/graph`, delegating to `run_graph_for`.
- `src/orchestrator/api/providers.py` — new `run_view_ports`; `run_read_ports` wired with the Board's extra ports.
- `src/orchestrator/main.py` — mounts `run_detail.router`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` — regenerated (`make openapi`), three new operations, no drift.
- 10 new test files (unit: `test_run_graph.py`, `test_graph_schema.py`, `test_run_views.py`, `test_real_log_reader.py`, `test_run_view_schemas.py`, `test_run_board_view_router.py`, `test_run_detail_router.py`, `test_run_graph_router.py`) plus `tests/unit/fakes/logs.py`.

**Review findings:** 9 patched (0 high, 2 medium, 7 low — see Review Triage Log), 5 deferred (2 medium, 3 low — recorded in frontmatter `deferred`), 6 rejected (deliberate precedent, matches an established codebase convention, explicitly covered by the brief, already justified in Design Notes, or reviewer lacked the full brief).

**Follow-up review recommended:** true (`3 × 2 medium + 1 × 7 low = 13 ≥ 5`).

**Verification performed:** `make lint` (ruff, ruff format, mypy strict on domain/application, import-linter, env-contract, test-pairs both components, `pnpm gen:api --check`, `pnpm lint`) — clean. `make test` — 4056 backend tests + 738 web-client tests passed, 100% branch coverage on `domain`/`application` maintained. `make openapi` — regenerated with no drift on the second run. `PATH="$HOME/.docker/bin:$PATH" make e2e` — 144 passed, 34 subtests passed, against a disposable `aio-e2e` stack, cleaned up after. `make e2e-ui` — 75 passed against the built preview on port 4321; port left clean afterward.

**Residual risks:** the five deferred items (N+1 reads on the Board and Run detail; the Board's unbounded `done`/`failed` columns; duplicated DI wiring; two low-likelihood edge cases unreachable via any shipped Template). None block this story; the two `medium` ones are candidates for the story that first renders the Board at scale (4.14) to revisit.
