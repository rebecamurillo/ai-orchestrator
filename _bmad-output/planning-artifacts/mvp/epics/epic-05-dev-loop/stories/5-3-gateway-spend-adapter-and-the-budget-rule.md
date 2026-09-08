---
title: 'Gateway spend adapter and the budget rule'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      LiteLLMSpend._rows has no upper bound on how many pages it will fetch if
      /spend/logs/v2 keeps reporting an increasing total_pages.
    evidence: |-
      A single attempt realistically has a handful of Gateway calls, and the server itself
      caps total matching rows at 10000 (SPEND_LOGS_PAGINATION_COUNT_CAP), so this is a
      defensive gap rather than an observed failure. Neither the brief nor AD-11 states a
      page or row cap; adding one unasked would be a scope decision, not a patch.
    location: >-
      backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py:_rows
    severity: low
  - summary: >-
      StepRowOut.cost_usd / StoryCellOut.cost_usd are permanently schema-optional
      (Field(default=..., json_schema_extra=_drop_default)) so an existing, frozen
      web-client fixture (predates cost_usd) keeps compiling without it.
    evidence: |-
      `.of()` always sets the real value at runtime, so the optionality is a wire-schema
      artifact, not a data gap. Tightening it to required needs the frozen web-client
      fixtures in run-detail-lib.test.ts / run-steps-table.test.ts / run-stop-body.test.ts /
      run-stories-strip.test.ts updated first, which this story's anchor rule forbids.
    location: >-
      backend-api/src/orchestrator/api/schemas/run_views.py:StepRowOut,StoryCellOut
    severity: low
  - summary: >-
      record_attempt_spend's _run_spend recomputes run.spend_usd by re-reading every
      attempt of every row of the Run on every single settle call.
    evidence: |-
      O(rows x attempts) per write; matches the pre-existing read-path pattern
      application/use_cases/run_views.py::_cost already uses once per read, so this is not a
      new class of cost, just a new call site of the same shape at write time. Worth a look
      if Runs grow very large, not blocking today.
    location: >-
      backend-api/src/orchestrator/application/use_cases/spend.py:_run_spend
    severity: low
baseline_revision: 'b70c49b5df5385fe9d5a4bbe9ff64c5cda9d172f'
---

<intent-contract>

## Intent

**Problem:** Nothing reads an attempt's real cost from the Gateway. `attempt.cost_usd`/
`tokens_in`/`tokens_out`/`cost_provisional` exist (4.1) but nothing fills them, `run.spend_usd`
is always `0`, and there is no rule that says a Run has spent past its budget.

**Approach:** Add `domain/ports/gateway.py` (`Gateway`, `AttemptSpend`, `ModelSpend`),
`infrastructure/gateway/litellm_spend.py` (`LiteLLMSpend`, real adapter over `GET
/spend/logs/v2`), `application/rules/budget.py::check`, and `application/use_cases/
spend.py::record_attempt_spend`, which fills one attempt and recomputes `run.spend_usd`. The
read models (`StepRowView.cost_usd`, `StoryCell.cost_usd`) sum already-stored attempt figures
— no Gateway call at read time. No call site is wired (5.7); this story is the parts and their
own tests only.

## Boundaries & Constraints

**Always:**
- AD-11: bearer is `LITELLM_SPEND_KEY`, read only in `infrastructure/gateway/`; never
  `LITELLM_API_KEY`. Query by `end_user={run_id}`, `session_id={attempt_id}` — exactly the
  ids `env_for`'s headers already send (5.1's `HEADER_SOURCES`: `x-litellm-end-user-id` =
  `ORCH_RUN_ID`, `x-litellm-session-id` = `ORCH_ATTEMPT_ID`).
- The adapter never raises to `spend_for_attempt`'s caller: empty rows, an HTTP error, a bad
  body — all log and answer `provisional=True` with zeros.
- AD-2: `httpx` only under `infrastructure/gateway/`; `domain/` and `application/` hold no
  import of it.
- Every new module is paired with a unit test that imports it (AD-18, `check_test_pairs`);
  every module stays ≤ 400 lines; `domain/` + `application/` stay at 100% branch coverage.
- No new `Settings` field: `litellm_base_url`/`litellm_spend_key` already exist (4.x).

**Block If:**
- Landing this story would require editing `SPEC.md`, `stories.yaml`, an `AGENTS.md`, or any
  existing test file.

**Never:**
- No call site: nothing calls `record_attempt_spend` from the walker or an executor (5.7 —
  Scope's own "Out").
- No budget-park routing, no re-check scheduling, no raising the budget (5.7, Epic 6).
- No `StepPorts`/`WalkPorts`/`RunViewPorts` field for `Gateway` — the read models need none;
  a write-time call site is 5.7's to wire.
- No wire/UI exposure beyond `StepRowOut.cost_usd`/`StoryCellOut.cost_usd` (the same-story
  precedent 5.2 set for `cost.trace_url`) — Question block, Stories-strip rendering, harness/
  cost *columns* are 5.10.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Three rows, two models | stubbed `/spend/logs/v2` returns 3 rows (2 for model A, 1 for model B) | `usd`/`tokens_in`/`tokens_out` are the sum; `by_model` has both models' own sums; `provisional=False`, `calls=3` | No error expected |
| Empty result | stubbed endpoint returns `{"data": [], "total": 0, ...}` | `provisional=True`, every number `0`, a log line | No error expected |
| Connection error | the transport raises | same as empty: `provisional=True`, zeros, a log line | No exception reaches the caller |
| Bearer header | any request | `Authorization: Bearer {LITELLM_SPEND_KEY}` — never `LITELLM_API_KEY` | No error expected |
| Paged response | `total_pages=2` on page 1 | a second request at `page=2`; rows from both pages summed | No error expected |
| Provisional + harness usage present | `spend_for_attempt` returns provisional; `harness_usage` given | attempt gets the harness's `cost_usd`/`tokens_in`/`tokens_out`, `cost_provisional=True` | No error expected |
| Later call settles it | same attempt, a later `record_attempt_spend` call now gets Gateway rows | attempt's figures replaced, `cost_provisional=False`; `run.spend_usd` is the sum both times | No error expected |
| Provisional, no harness usage | `spend_for_attempt` provisional; `harness_usage=None` | attempt's existing cost fields untouched, `cost_provisional=True` | No error expected |
| Budget exceeded | `run.spend_usd=41.20`, `run.budget_usd=40.00` | `budget.check` returns `Park(kind="budget", reason="budget $41.20 / $40.00")` | No error expected |
| Budget exactly met | `41.20 / 41.20`, `40.00 / 40.00` | `None` | No error expected |
| Read-model sums | a Run with two story frames of two attempts each | each `StepRowView.cost_usd` sums its own row's attempts; each `StoryCell.cost_usd` sums its frame's rows; `cost.spent_usd`/`provisional` already correct (pre-existing) | No error expected |

</intent-contract>

## Code Map

- `research/spend.md` (already loaded) pins the query shape but not the response envelope.
  Verified live against LiteLLM `v1.99.1`'s own source
  (`litellm/proxy/spend_tracking/spend_management_endpoints.py`, `ui_view_spend_logs`,
  shared by `/spend/logs/v2`):
  - **`start_date`/`end_date` are required**, not optional as the brief's example call
    implies — omitted, the route raises 400. Both `"%Y-%m-%d"` and `"%Y-%m-%d %H:%M:%S"` are
    accepted for `is_v2`. The adapter supplies a fixed, wide window (`2020-01-01` ..
    `2099-12-31`) rather than a real one — a query already scoped exactly to one
    `(end_user, session_id)` pair needs no narrower window, and a fixed window needs no
    `Clock` port.
  - **`session_id` is `LIKE %value%`** (partial match), not equality; `end_user` is exact
    equality. A UUIDv7 attempt id colliding as a substring of another attempt id's is not a
    realistic risk — noted, not defended against, since the route offers no exact filter.
  - **Response envelope:** `{"data": [...], "total", "page", "page_size", "total_pages",
    "total_is_capped"}`. Each row carries (among others) `spend` (float), `prompt_tokens`,
    `completion_tokens`, `model`, `session_id`, `end_user`.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:59-66` —
  `HEADER_SOURCES`: confirms `x-litellm-end-user-id`/`x-litellm-session-id` carry
  `ORCH_RUN_ID`/`ORCH_ATTEMPT_ID` — what the adapter's query filters match.
  `infrastructure/harness/env.py` needs no change.
- `backend-api/src/orchestrator/domain/entities/attempt.py` — `cost_usd: Decimal | None`,
  `tokens_in`/`tokens_out: int | None`, `cost_provisional: bool` (4.1). No migration.
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py` — `update()`
  already writes every mutable column including these four plus `model`; reuse, no change.
- `backend-api/src/orchestrator/domain/ports/repositories.py` — `AttemptRepository`,
  `RunRepository`, `StepRunRepository`: `list_for_row`, `list_for_run`, `update` — the whole
  read/write surface `record_attempt_spend` needs. No new repository method.
- `backend-api/src/orchestrator/domain/values.py:24-32` — `Park(kind, reason, path=None)`
  already exists; `"budget"` is already a valid `ParkKind`
  (`backend-api/src/orchestrator/domain/statuses.py:42-54`). `budget.py` builds this type,
  invents nothing.
- `backend-api/src/orchestrator/application/rules/frames.py::rows_in_frame` — reused for
  `StoryCell.cost_usd`'s per-frame sum, in preference to a literal `LIKE prefix%`: it is the
  boundary-safe version (`stories[1]` vs `stories[10]`) the module's own docstring states,
  and it is already loaded for `_story_cells`' commit-row walk.
- `backend-api/src/orchestrator/application/use_cases/writers.py::WriterPorts` — the pattern
  a ports bundle + `with ports.uow:` follows (`start_attempt.py` is the closest existing
  use case: ports first argument, entity-typed inputs, one unit of work). Not reused
  directly: `WriterPorts` is AD-8's own bundle for the three *status* writers; spend is a
  different write, so `spend.py` gets its own `SpendPorts`.
- `backend-api/src/orchestrator/application/use_cases/run_views.py:255-311` — `_step_row`,
  `_story_cells`, `_story_cell`: exact insertion points, at **385/400 lines already** (the
  tightest file this story touches). Every helper added here needs to be a one-purpose,
  no-docstring private function; `_frame_cost` is computed inline inside `_story_cells`'
  existing loop rather than as its own top-level function, to keep the net addition small
  (a new top-level function costs its body *and* the two blank lines PEP8 spacing between
  top-level functions adds around it).
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — `StepRowView`,
  `StoryCell` (both `@dataclass(frozen=True)`, 197/400 lines, plenty of room): `cost_usd:
  Decimal = Decimal("0")` on both, **with a default** — `tests/unit/
  test_run_view_schemas.py:140` (frozen) constructs a bare `StepRowView(...)` with no
  `cost_usd` and must keep working unmodified.
- `backend-api/src/orchestrator/api/schemas/run_views.py` (382/400 lines) — `StepRowOut`,
  `StoryCellOut`: add `cost_usd: MoneyStr` to both and their `.of()`, the same "expose in
  the story that adds the read-model field" precedent 5.2 set for `Cost.trace_url` in
  `CostOut`. Verified safe against the two frozen router tests
  (`test_run_detail_router.py`, `test_run_board_view_router.py`): both assert only top-level
  JSON key sets, never a nested dict's exact keys, and `tests/unit/test_run_view_schemas.py`
  never constructs `StepRowOut`/`StoryCellOut` directly (only through `.of()`), so a new
  required field there is safe.
- `backend-api/tests/unit/fakes/runs.py` — `FakeRunRepository`, `FakeAttemptRepository`,
  `FakeStepRunRepository`: all three already have `update`; reuse, no new fake needed for
  them (AD-18).
- `backend-api/tests/unit/fakes/db.py::FakeUnitOfWork` — reuse.
- `httpx.MockTransport` (stdlib-adjacent, part of the already-pinned `httpx==0.28.1`) is the
  test seam for `LiteLLMSpend` — no new test dependency.

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_gateway_port.py` -- new: `Gateway` protocol shape,
  `AttemptSpend`/`ModelSpend` construction and frozen-ness, `FakeGateway` satisfies
  `Gateway` -- TDD first (AD-18).
- `backend-api/src/orchestrator/domain/ports/gateway.py` -- new: `ModelSpend`,
  `AttemptSpend`, `Gateway` protocol.
- `backend-api/tests/unit/fakes/gateway.py` -- new `FakeGateway`: scripted `AttemptSpend`
  per `(run_id, attempt_id)`, a call log, unscripted pair answers provisional zero -- the
  one fake for the port (AD-18).
- `backend-api/tests/unit/test_litellm_spend_adapter.py` -- new: every I/O matrix row for
  the adapter, against `httpx.MockTransport` -- sum + per-model breakdown, empty list,
  connection error, bearer header, pagination, the required date window.
- `backend-api/src/orchestrator/infrastructure/gateway/__init__.py` -- new package marker
  re-exporting `LiteLLMSpend`.
- `backend-api/src/orchestrator/infrastructure/gateway/litellm_spend.py` -- new:
  `LiteLLMSpend(settings, http)`, `_query`, aggregation -- the real adapter.
- `backend-api/tests/unit/application/test_budget_rule.py` -- new: `check` over/at/under
  budget -- TDD first.
- `backend-api/src/orchestrator/application/rules/budget.py` -- new: `check(run) -> Park |
  None`.
- `backend-api/tests/unit/application/test_record_attempt_spend.py` -- new: settled figures,
  provisional + harness usage, provisional + no harness usage, a later call replacing
  provisional figures, `run.spend_usd` recomputed both times, dominant-model pick when
  `attempt.model` was unset.
- `backend-api/src/orchestrator/application/use_cases/spend.py` -- new: `SpendPorts`,
  `record_attempt_spend`, `_priced_attempt`, `_dominant_model`, `_run_spend`.
- `backend-api/tests/unit/application/test_run_views_cost.py` -- new (does not touch the
  frozen `test_run_views.py`): a Run with two story frames of two attempts each ->
  `StepRowView.cost_usd`/`StoryCell.cost_usd` sums, matching the AC's own scenario.
- `backend-api/src/orchestrator/application/use_cases/run_views.py` -- edit per Code Map:
  `_step_row` gets `cost_usd`; `_story_cells`/`_story_cell` thread an inline per-frame sum.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` -- edit: `cost_usd:
  Decimal = Decimal("0")` on `StepRowView` and `StoryCell`.
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- edit: `cost_usd: MoneyStr` on
  `StepRowOut`/`StoryCellOut` and their `.of()`.

**Acceptance Criteria:**
- Given a stubbed spend endpoint returning three rows for the attempt (two models), when
  `spend_for_attempt` is called, then the sum and the per-model breakdown are right and
  `provisional` is false; and with an empty list or a connection error, `provisional` is
  true with zeros and a log line.
- Given a provisional Gateway answer and `harness_usage` present, when
  `record_attempt_spend` runs, then the attempt carries the harness figures with
  `cost_provisional = true`; a later call with Gateway rows replaces them and clears the
  flag; `run.spend_usd` is the sum over attempts both times.
- Given `spend_usd 41.20` and `budget_usd 40.00`, when `budget.check` runs, then it returns
  the park with reason `budget $41.20 / $40.00`; with `40.00 / 40.00` -> `None`.
- Given a Run with two story frames of two attempts each, when the Run detail read model is
  built, then each story's `cost_usd` is its attempts' sum, `cost.spent_usd` the total, and
  `cost.provisional` reflects any provisional attempt.
- Given the adapter's HTTP client, when any request is made, then the bearer is
  `LITELLM_SPEND_KEY`, never `LITELLM_API_KEY`.
- Given `make lint`, then `check_test_pairs`, ruff, mypy --strict, lint-imports, the
  env-contract check and every module's 400-line cap all pass, with no change to any frozen
  file.
- Given `make test`, then every unit test passes and `domain/` + `application/` stay at
  100% branch coverage.
- Given `make openapi`, then `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerate with the two new `cost_usd` fields and no other drift.

## Spec Change Log

## Review Triage Log

### 2026-09-08 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 3: (high 0, medium 0, low 3)
- reject: 10: (high 1, medium 1, low 8)
- addressed_findings:
  - `[medium]` `[patch]` No test drove a non-zero `cost_usd` through `StepRowOut.of()`/
    `StoryCellOut.of()` and asserted the emitted value — a reverted or typo'd
    `cost_usd=row.cost_usd`/`cost_usd=cell.cost_usd` line would ship every Run's per-step
    and per-story cost as `"0"` over the wire while every other test in the diff kept
    passing (verification-gap). New file `test_run_view_schemas_cost.py` closes it.
  - `[low]` `[patch]` `LiteLLMSpend._aggregate`'s per-model accumulator was `dict[str,
    list[Decimal | int]]`, needing four `# type: ignore` comments under `mypy --strict`
    (blind-hunter). Replaced with a local mutable `_Bucket` dataclass; no suppressions
    remain.
  - `[low]` `[patch]` `_dominant_model`'s tie-break on equal `usd` was accidental dict-
    iteration order, undocumented (blind-hunter, edge-case-hunter). Now an explicit
    `(usd, model)` key — alphabetically-last on a tie — with a doc-comment and a new test.
  - `[low]` `[patch]` `/spend/logs/v2`'s `session_id` filter is `LIKE %value%`, not exact
    equality (verified live against LiteLLM 1.99.1's source); nothing defended a row whose
    `session_id` merely contained the requested attempt id as a substring before it reached
    a money/budget figure (blind-hunter, intent-alignment). Added `_matches` — an exact
    client-side post-filter on both `session_id` and `end_user` — plus two new tests.
  - `[low]` `[patch]` The brief's own named scenario ("local models cost 0 with tokens...
    keep it") had no test asserting it by name (intent-alignment). Added
    `test_a_local_model_with_zero_spend_is_settled_not_empty`.
  - `[reject]` Four independent reviewers (blind-hunter, edge-case-hunter, intent-alignment,
    verification-gap) flagged `except InvalidOperation, ValueError:` /
    `except TypeError, ValueError:` in `litellm_spend.py` as Python-2-only syntax that would
    make the module fail to import. Verified empirically against this repository's actual
    pinned interpreter (`uv run python --version` → `3.14.7`; `ast.parse` on the file
    succeeds) that PEP 758 (accepted for Python 3.14) makes an unparenthesized multi-
    exception `except` clause valid syntax — every reviewer's tooling ran under an older
    Python. `make lint`/`make test` were independently re-run end to end (not just trusted
    from the implementer's own report) and both pass, 4321 backend + 973 web-client tests,
    domain/application at 100% branch coverage. No change made; false positive, not noise
    dropped for being unimportant — recorded here in detail because four separate reviewers
    converged on it.
  - `[reject]` `[medium]` Edge-case-hunter suggested the budget park reason append
    "(over by $X)" so a sub-cent overage does not show identical rounded figures on both
    sides. Rejected: the brief's own AC pins the exact literal string `budget $41.20 /
    $40.00`; changing the format would violate that AC, not satisfy it.
  - `[reject]` Spec Change Log left empty despite a real discovery (start_date/end_date
    required, not optional) (blind-hunter). That section is for step-04's own bad_spec
    repair loopbacks (spec-template.md's own docstring); this is the first review pass, no
    loopback fired, and the discovery is already recorded in this spec's own Code Map and
    the adapter's module docstring — the right place for a planning-time finding.
  - `[reject]` No test for `budget.check` with a negative `spend_usd` (blind-hunter).
    Speculative: nothing in this domain ever produces a negative `cost_usd`.
  - `[reject]` `infrastructure/gateway/__init__.py`'s re-export is never imported via the
    package path in a test (blind-hunter). Matches the existing, accepted convention
    (`infrastructure/harness/__init__.py` is the same shape); `check_test_pairs.py` exempts
    `__init__.py` by design.
  - `[reject]` `budget.py`'s docstring names `litellm_spend.py::_decimal` by symbol
    (blind-hunter). Cosmetic; matches this codebase's pervasive cross-file documentation
    style throughout every prior story's own modules.
  - `[reject]` No test for `record_attempt_spend`'s unit-of-work rolling back on a partial
    write failure (blind-hunter). Same, untested pattern across every existing AD-8 writer
    (`start_attempt`, `apply_step_result`, `signal_run`); not specific to this story.
  - `[reject]` Fixed date window format not validated against a live LiteLLM (edge-case-
    hunter). Already verified by reading LiteLLM 1.99.1's own source at plan time
    (`is_v2`'s accepted format list includes `%Y-%m-%d`); a live check is out of this
    story's stated scope (no live Gateway access).
  - `[reject]` A non-integer float token count (e.g. `10.7`) truncates silently via `int()`
    rather than being treated as unusable (edge-case-hunter). `prompt_tokens`/
    `completion_tokens` are integer-typed in LiteLLM's own schema; speculative, not an
    observed shape.
  - `[reject]` Intent-alignment's observation that `cost.spent_usd`/`cost.provisional`
    coverage for the AC's fourth scenario lives in pre-existing frozen tests rather than
    this diff's own new test. Correct as stated, not a defect — those two fields were
    already implemented and tested before this story; only the two new sums
    (`StepRowView.cost_usd`, `StoryCell.cost_usd`) needed new coverage, which
    `test_run_views_cost.py` provides.

## Design Notes

**Why `record_attempt_spend(ports, run, attempt, harness_usage)`, not the brief's literal
three-argument form.** Every use case in this codebase takes its ports bundle first
(`start_attempt(ports, run_id, seq, ...)`, `run_detail(ports, run_id)`) — the brief's
`record_attempt_spend(run, attempt, harness_usage)` line names the *facts*, the same way
5.1's `env_for` and 5.2's `create_run_trace` brief lines did, not a literal call signature.
`ports` is added as the leading argument, the same precedent.

**`SpendPorts` is its own bundle, not `WriterPorts`.** AD-8 names `WriterPorts` for exactly
the three status writers (`start_attempt`, `apply_step_result`, `signal_run`); spend is a
different write with a different, smaller dependency set (`gateway`, `runs`, `steps`,
`attempts`, `uow` — no `records`/`clock`). Reusing `WriterPorts` would force every caller
that does not have a `GateRecordRepository`/`Clock` handy to supply one anyway.

**Provisional with no `harness_usage`.** The brief's own AC only states "provisional +
harness usage present"; the empty case (`provisional=True`, `harness_usage=None` — the
Gateway has nothing yet and the harness printed no usable JSON either) is not named. This
leaves the attempt's existing cost fields untouched and `cost_provisional=True`: there is
nothing new to write, and inventing zeros would misrepresent "unknown" as "free".

**`run.spend_usd`'s write does not go through the two AD-8 status writers.** AD-8 gives that
rule to `run.status` specifically ("Status has two writers"); `spend_usd` is a different
field, written the same way 5.2's `create_run` sets `trace_id` — a plain
`ports.runs.update(run.model_copy(update={"spend_usd": ...}))` inside the use case's own
unit of work.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; every module (including the two already-tight files this
  story edits) stays ≤ 400 lines.
- `make test` -- expected: exit 0; `domain/` + `application/` at 100% branch coverage.
- `make openapi` -- expected: exit 0; the two new `cost_usd` fields appear in
  `contracts/openapi.json` and `web-client/src/api/schema.d.ts`, nothing else drifts.
- `git status --porcelain` -- expected: only the files this spec's Execution list names.

## Auto Run Result

Status: done

**What was implemented.** The `Gateway` port (`spend_for_attempt`) and its real adapter,
`LiteLLMSpend`, over LiteLLM's `GET /spend/logs/v2` — paginated, bearer `LITELLM_SPEND_KEY`
only, a fixed wide date window (the route requires one; the brief's own example call
omitted it), and an exact client-side `session_id`/`end_user` post-filter (the route's own
`session_id` match is `LIKE %value%`, verified live against LiteLLM 1.99.1's source). The
adapter never raises: empty rows, an HTTP error, or a bad body all degrade to a logged
provisional zero. `application/rules/budget.py::check` returns a `Park("budget", ...)` when
`run.spend_usd > run.budget_usd`, reason always rendered to two decimal places regardless of
how much precision a real Gateway sum carries. `application/use_cases/spend.py::
record_attempt_spend` prices one attempt (settled Gateway figures beat a provisional
harness-usage fallback, which beats leaving the attempt untouched), attributes the dominant
model by spend when the attempt's model was unset, and recomputes `run.spend_usd` by summing
every attempt of every row of the Run (never incremented, so a later settling call replays
safely). The Run-detail read model gained `StepRowView.cost_usd` (sum over a row's own
attempts) and `StoryCell.cost_usd` (sum over a story frame's rows, via the existing
boundary-safe `rows_in_frame`), exposed over the wire as `StepRowOut.cost_usd`/
`StoryCellOut.cost_usd` (schema-optional only so four frozen, pre-existing web-client
fixtures keep compiling — `.of()` always sets the real value). No call site was wired
(5.7's own scope): nothing in the walker or an executor calls `record_attempt_spend` or
`budget.check` yet.

**Files changed (13 added, 5 modified):**
- `backend-api/src/orchestrator/domain/ports/gateway.py` — added: `ModelSpend`,
  `AttemptSpend`, the `Gateway` protocol.
- `backend-api/src/orchestrator/infrastructure/gateway/__init__.py`,
  `infrastructure/gateway/litellm_spend.py` — added: `LiteLLMSpend`, the real adapter
  (`_rows`, `_page`, `_matches`, `_aggregate`, `_Bucket`, `_decimal`, `_int`).
- `backend-api/src/orchestrator/application/rules/budget.py` — added: `check`.
- `backend-api/src/orchestrator/application/use_cases/spend.py` — added: `SpendPorts`,
  `record_attempt_spend`, `_priced_attempt`, `_dominant_model`, `_run_spend`.
- `backend-api/tests/unit/fakes/gateway.py` — added: `FakeGateway`, the one fake for the
  port.
- `backend-api/tests/unit/test_gateway_port.py`, `test_litellm_spend_adapter.py`,
  `test_run_view_schemas_cost.py`, `application/test_budget_rule.py`,
  `application/test_record_attempt_spend.py`, `application/test_run_views_cost.py` —
  added: the port's own tests, the real adapter's tests (13 cases including the review
  pass's substring-match, local-model-zero-spend, and dominant-model-tie additions), the
  rule's tests, the use case's tests, the wire-mapping regression test, and the read-model
  sum test.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — modified: added
  `cost_usd: Decimal = Decimal("0")` to `StepRowView`/`StoryCell`.
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — modified: `_step_row`
  sums its row's attempts; `_story_cells`/`_story_cell` thread an inline per-frame sum via
  `rows_in_frame`.
- `backend-api/src/orchestrator/api/schemas/run_views.py` — modified: `cost_usd` on
  `StepRowOut`/`StoryCellOut` and their `.of()`, schema-optional via `_drop_default`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` — modified: regenerated, the
  two new `cost_usd` fields, no other drift.

**Review findings:** 5 patched (0 high, 1 medium, 4 low), 3 deferred (frontmatter
`deferred`, all low), 10 rejected (1 would-be-high, 1 medium, 8 low — see the Review Triage
Log for why each was rejected, including the four-reviewer syntax false positive verified
against this repository's actual pinned Python 3.14 interpreter). No `intent_gap` and no
`bad_spec` — the intent-alignment auditor independently confirmed the implementation's
reading (ports-first convention, matching every other use case in this codebase) is what
the brief's own explicit scope ("Out: the call site in the agent tail (5.7)") requires.

**Follow-up review recommended:** true. Patch score `3 × 1 medium + 1 × 4 low = 7`, over the
threshold (no high-severity patch on its own).

**Verification performed (re-run independently by the coordinator, not only trusted from
the implementation subagent's own report):**
- `make lint` — exit 0, twice (once before the review patches, once after): ruff check,
  ruff format --check, mypy --strict over `domain/` + `application/`, all four
  import-linter contracts KEPT, env-contract check (31 settings fields / 37 `.env.example`
  variables agree, unchanged — no new setting needed), `check_test_pairs` 166/166 paired,
  `gen:api --check` no drift, web-client lint/tsc/astro-check/eslint/prettier/test-pairs
  all clean.
- `make test` — exit 0, twice: 4321 backend unit tests passed, 1 skipped (up from 4195
  before this story); `domain/` + `application/` at 100% branch coverage under
  `--fail-under=100`; web-client 973 passed.
- `make openapi` — exit 0, re-run independently after the review patches: idempotent, no
  further drift; the two `cost_usd` fields present in both `contracts/openapi.json` and
  `web-client/src/api/schema.d.ts`.
- Anchor check (the literal command from the dispatch instructions) — run twice, printed
  nothing both times: no existing test file was touched, only new test files and the two
  files (`run_views.py`, `run_view_types.py`, `api/schemas/run_views.py`) this spec's own
  Execution list names.
- Matrix audit: all 11 I/O matrix rows are covered by named tests that ran and passed,
  including the three the review pass added (substring `session_id`, `end_user` mismatch,
  local-model zero-spend).
- Line-count audit: `litellm_spend.py` 193, `spend.py` 119, `budget.py` 30, `run_views.py`
  398/400, `api/schemas/run_views.py` 399/400, `run_view_types.py` 201/400, `main.py`
  unchanged at 394/400 (untouched — this story needed no composition-root wiring).
- Independently re-read the implementation and every patch line by line (not only the
  subagent's own summary) before accepting it, including verifying the Python 3.14
  `except X, Y:` syntax claim empirically (`uv run python --version`, `ast.parse`) rather
  than taking either the reviewers' or the implementer's word for it.

**Residual risks (frontmatter `deferred`):**
- `LiteLLMSpend._rows` has no upper bound on pages fetched if `total_pages` keeps growing;
  bounded in practice by the Gateway's own 10000-row cap and by one attempt's realistically
  small call count.
- `cost_usd` is permanently wire-schema-optional so four frozen, pre-existing web-client
  fixtures keep compiling; tightening it needs those fixtures updated first, which this
  story's own anchor rule forbids.
- `record_attempt_spend`'s `run.spend_usd` recompute is O(rows × attempts) per settle call
  — matches the pre-existing read-path pattern `run_views.py::_cost` already uses, just at
  a new write-time call site; worth a look only if Runs grow very large.
- `run_views.py` (398/400) and `api/schemas/run_views.py` (399/400) are now extremely
  tight; a later story touching either has essentially no line budget left without moving
  something out first.
