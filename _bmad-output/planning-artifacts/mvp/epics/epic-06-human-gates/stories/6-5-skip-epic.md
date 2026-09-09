---
title: 'Skip epic'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      `blockedSignals`/`checkpointSignals` can still advertise `skip_epic` in
      `admitted_signals` on a Template that carries no epic frame at all (e.g. a plain
      `story` Run's own `blocked` park), so a *Skip epic* button posted there answers 409
      rather than not being offered at all.
    evidence: |-
      `admitted_signals(park_kind, row_kind)` answers from the park kind and the parked
      row's kind alone and cannot run `validate`'s own `extra=_has_epic_frame` check — its
      own docstring says so. `blockedSignals`/`checkpointSignals` are both frozen (5.10/6.2)
      and render every kind `admitted_signals` names regardless of `run.template`; this
      story's own `offersSkipEpic` is more precise (it reads `run.template` and the parked
      row's own `epics[n]` bracket) but only governs the five stops those two frozen filters
      do not reach. This is the exact same shape of gap 6.4 already deferred for
      `skip_story` on a park outside every Story frame — this story declined to extend that
      one either, for the same reason: the three bodies 5.10/6.2 landed are pinned by
      frozen tests.
    location: >-
      web-client/src/lib/run/detail.ts::blockedSignals,
      web-client/src/lib/run/checkpoint.ts::checkpointSignals
    severity: low
  - summary: >-
      `skip_epic` has no proof at the compose-stack (e2e-api) integration level: only unit
      and router-level (in-process ASGI) coverage exists for it. The scope gate, the read
      model, and the frontend confirm are all proven end to end against the real HTTP/DB
      layer at the unit-test level, but never against a running backend-api + postgres stack
      the way `test_skip_story.py` proves `skip_story`.
    evidence: |-
      The only e2e fixture path this repository has (`tests/e2e/helpers/gates_fixture.py::
      epic_template_as`) saves `templates/epic.yaml` under a fresh registered name so it
      does not pin `epic@1` (`test_templates.py` asserts `pinned_by == 0` for it) — but that
      rename makes `rules/signals.py::_has_epic_frame`'s own `run.template_name ==
      "epic"` branch permanently false for any Run started on it, and the `epic` Template's
      own plan has no `epics[n]` frame in any path either, so `_has_epic_frame`'s other
      branch can never be satisfied that way. Every `skip_epic` signal posted against a Run
      started through this fixture would 409. Proving it for real would need a second,
      initiative-shaped fixture (an `epics.yaml` plus a nested epic sub-template registered
      under its own name) that does not exist; building one is fixture engineering outside
      this story's own surface (see the spec's own `Never` clause), not authorised here, and
      not attempted. This is stated explicitly rather than left implied by a green `make
      e2e` run, which proves nothing about `skip_epic` — it only proves the suite this
      story did not touch is still green.
    location: >-
      backend-api/tests/e2e/helpers/gates_fixture.py::epic_template_as
    severity: medium
baseline_revision: 'd75fae66d5335b08e52e1440d7a6142c076399a5'
---

<intent-contract>

## Intent

**Problem:** `skip_epic` is the one remaining AD-13 action with no reach: 4.5 built its
writer whole (`signal_effects.py::_skip_epic`, 100% branch covered by `test_signal_run.py`
since story 4-5), but `handle_signal`'s scope gate still refuses it `not available yet`, the
read model has no `summary.skipped_epics`, and the button renders as a plain (non-confirm)
`<button>` on only two of the eight stop bodies AD-13 admits it on.

**Approach:** Join `skip_epic` to `use_cases/signals.py::_in_scope`'s tuple (same
unconditional join `skip_story` made in 6.4), widen the `Summary`/`SummaryOut` read model
with `skipped_epics: list[int]` (1-based epic numbers, matching the brief's own AC wording),
and give every stop body FR-20 lists a `ConfirmAction`-based *Skip epic* control via a sibling
filter, reusing 6.4's component verbatim with its own predicate (not `offersSkipStory`'s: no
per-current-Story id is needed, only the Run's own `template`, and the epic number comes from
the parked row's own path, not from a story cell).

## Boundaries & Constraints

**Always:**
- AD-13 stays the authority on validity: `rules/signals.py::validate`/`admitted_signals` are
  **not** changed — `VALID["skip_epic"]` already exists (4.5) and is correct.
- AD-8's two writers are untouched: `signal_effects.py::_skip_epic` already implements every
  effect the brief lists (current frame as `skip_story`, every later Story frame of the epic
  `skipped`, push/link left `planned` — or, on `push_rejected`, both `skipped` and the next
  epic's first row `queued`). No writer code changes.
- `Summary.skipped_epics` widens the read model without breaking `Summary.skipped`'s own
  contract (unchanged, per 6.4). Both `Summary.skipped_epics` (dataclass) and
  `SummaryOut.skipped_epics` (wire) carry a default (`field(default_factory=list)` /
  `Field(default_factory=list, json_schema_extra=_drop_default)`) so `Summary(progress=None,
  links=[...], skipped=["4-2"])` in `test_run_view_schemas.py` (an existing test file, not
  editable) keeps compiling and the wire field is schema-optional for the same reason
  `cost_provisional`/`row_kind` are (`_drop_default`'s own precedent, 5.10/6.2).
- The confirm is `ConfirmAction` (6.4), reused verbatim with `kind="skip_epic"`; no modal, no
  `dangerouslySetInnerHTML`, `wf-signal-skip_epic` stays the trigger's test id (every existing
  spec already asserts only its presence, not whether it is a confirm — 6.4's own precedent:
  the closed render is indistinguishable from the plain button it replaces).
- `offersSkipEpic`'s frame check is the Run's own `template` (`'epic' | 'initiative'`), not a
  per-current-Story id: `rules/signals.py::_has_epic_frame` is true whenever
  `run.template_name == "epic"` (the whole Run is one epic) or the parked row sits under an
  `epics[n]` frame — and every row of an `initiative` Run's plan is nested under `epics[i]`
  (`templates/initiative.yaml`'s only `for_each`), so the client-side twin needs no path
  inspection to decide *whether* to offer the control.
- The epic number `{n}` in the confirm line, where a path IS available (`currentStepPath`,
  already read for `logTail`), is `1 + ` the parked row's own `epics[N]` bracket, or `1` when
  the path carries none (`epic` template, or the row precedes any bracket) — the same
  1-based convention the brief's own ACs use (`epics[0].push` → `summary.skipped_epics ==
  [1]`), distinct from `StoryCell.epic_index`'s pre-existing 0-based convention (untouched,
  out of scope — that mismatch predates this story and is not this story's to fix).
- Module cap 400 lines: check `run_views_summary.py`/`run_view_types.py`/`signals.py` (use
  case)/`StopBody.tsx`/`detail.ts` after edits; split along a real seam if any is pushed over.
- New coverage goes in new test files. Two pending-gate registry rows may be removed under
  the operator's standing exception: `test_handle_signal.py`'s `skip_epic` row (and its `ids`
  entry) and `test_answer_signal_scope.py`'s `skip_epic` row (and its `ids` entry) — both
  files name this story explicitly in their own docstrings/comments.

**Block If:**
- Any assertion in an existing test file, other than the two pending-gate rows above, would
  have to change to make this story's own scope-gate widening true. In particular:
  `backend-api/tests/unit/test_signals_router.py::
  test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet` uses `skip_epic` as its
  illustrative "not yet built" kind against `push_rejected_world()` (default `template_name=
  "epic"`, per `writer_fixtures.a_world`) — once `_in_scope` admits `skip_epic`, `validate()`
  already accepts that exact world (`push_rejected` is in `VALID["skip_epic"].park_kinds`,
  and `_has_epic_frame` is true via the `template_name == "epic"` branch), so the request
  this test posts would return 200, not 409. This file predates the branch (story 4-9, Epic
  4) and is not one of the two operator-named registries, so HALT and report rather than
  self-authorise: minimal edit would be swapping this one test's illustrative kind to one
  still out of scope after 6.5 (`budget_raise` or `terminal_start`), unchanged otherwise, with
  strictly-exceeding coverage (a new router-level test proving `skip_epic` now succeeds) in
  the same commit — an operator ruling is required first.

**Never:**
- Do not implement, test, or shape `budget_raise`, `continue` on `protected_path`, the
  terminal path (6.6, 6.7), or the UJ-3 journey scenarios (6.8).
- Do not widen `stopSignals`/`hasEffect`/`EFFECTIVE_KINDS`, `blockedSignals`/
  `BLOCKED_EXTRA_KINDS`, or `checkpointSignals`/`CHECKPOINT_EXTRA_KINDS` — all pinned by
  frozen tests and already include `skip_epic` in their own filtered output (5.10/6.2); only
  `StopBody.tsx`'s *rendering* of that kind (plain button → `ConfirmAction`) and the sibling
  filter for the four/five stop kinds those three miss are this story's to touch.
- Do not add a new end-to-end (compose-stack) scenario for `skip_epic`: the only e2e fixture
  path available (`tests/e2e/helpers/gates_fixture.py::epic_template_as`, which renames the
  root template) can never satisfy `_has_epic_frame`'s literal `template_name == "epic"`
  branch once renamed, and no `epics.yaml`/nested-template fixture exists to exercise the
  frame-based branch instead; building one is fixture engineering, not this story's own
  surface, and 6.8's own UJ-3 scenario list does not include a skip-epic case either. The
  writer is already 100% branch covered end-to-end at the unit level (4.5); this story adds
  unit + router-level coverage for its own new code (the scope gate, the read model).
- Do not touch the Epic-7 gaps (`pgid` on a resumed dispatch, `Harness.resume`'s arguments).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Skip mid-epic | `needs_you`, `blocked` on `epics[0].stories[1].build`, stories 2-4 remain | current frame as `skip_story`, later frames `skipped`, `push`/`link` stay `planned`, Run `running` | — |
| Push rejected | `needs_you`, `push_rejected` on `epics[0].push` | `push`/`link` → `skipped · skipped by operator`, `epics[1].checkout` → `queued`, `summary.skipped_epics == [1]` once `done` | — |
| Re-baseline failed after skip | `verify_failed`, reason `re-baseline failed after skip` | that `error` verify row → `skipped`, `git.commit` → `queued`, epic proceeds to push | — |
| Budget park | `needs_you`, `park_kind == "budget"` | `skip_epic` refused | 409, AD-13's own text (`validate` refuses before the scope gate) |
| Button click | stop body admits `skip_epic` | inline confirm renders the right sentence per park kind, *Skip epic* posts, *Keep* posts nothing | — |

</intent-contract>

## Code Map

**Backend — the scope gate.**
- `application/use_cases/signals.py::_in_scope` (~line 72) — add `"skip_epic"` to the tuple
  `("cancel", "retry", "answer", "skip_story")`. `handle_signal` needs nothing else: `EFFECTS
  ["skip_epic"]` is already wired (4.5) and `VALID["skip_epic"]` already correct.
- `tests/unit/application/test_handle_signal.py` (~line 222-251) — remove the `_skip_epic_world`
  helper, its parametrize row `(_skip_epic_world, "skip_epic", {})`, and the `"skip_epic"`
  entry of `ids` — nothing else in the file changes.
- `tests/unit/application/test_answer_signal_scope.py` (~line 93-99) — remove the
  `("push_rejected", "push", "error", "skip_epic", {})` row and the `"skip_epic"` entry of
  `ids`, leaving the `budget_raise` row alone.

**Backend — the read model.**
- `application/use_cases/run_view_types.py::Summary` — add `skipped_epics: list[int] =
  field(default_factory=list)` (import `field`); keeps `Summary(progress=None, links=[...],
  skipped=["4-2"])` in `test_run_view_schemas.py` compiling unedited.
- `application/use_cases/run_views_summary.py` — new `skipped_epics(rows) -> list[int]`:
  every `PUSH_KIND` row whose `epic_frame(row.path)` is not `None` and whose
  `(status, reason) == ("skipped", SKIPPED_BY_OPERATOR)`, numbered `bracket_index(epic) + 1`
  (1-based — matches the brief's own AC, distinct from `StoryCell.epic_index`'s 0-based
  convention, untouched). A plain `epic`-template Run's own `push` row has no `epics[n]`
  bracket (`epic_frame` returns `None`), so it is never numbered — consistent with `progress
  ()`'s existing `epics_total=None` treatment of that template. `summary()` passes
  `skipped_epics=skipped_epics(rows)`.
- `api/schemas/run_views.py::SummaryOut` — add `skipped_epics: list[int] =
  Field(default_factory=list, json_schema_extra=_drop_default)`; `.of()` sets
  `skipped_epics=list(summary.skipped_epics)`.
- New test file `tests/unit/application/test_run_views_summary_skipped_epics.py`:
  `skipped_epics()` over a rejected-push world (epic 1 listed), an ordinary `done` epic
  (nothing listed), a second epic's push skipped (numbered 2), a plain `epic`-template Run's
  own skipped push (not numbered — no bracket). New test file
  `tests/unit/test_run_view_schemas_skipped_epics.py`: `SummaryOut.of()` projects
  `skipped_epics`.

**Backend — scope-gate + router coverage (this story's own new code).**
- New test file `tests/unit/application/test_skip_epic_signal.py`: `handle_signal` now
  applies `skip_epic` for the three brief scenarios (parametrised, mirroring the writer's
  own `test_signal_run.py` shapes but through the scope gate this story opens), plus the
  `budget` park's 409 (AD-13's own refusal, unchanged).
- New test file `tests/unit/test_skip_epic_signal_router.py`: `POST .../signals {"kind":
  "skip_epic"}` now 200s over the router (the scenario the frozen `test_signals_router.py`
  test cannot be widened to cover per the Block-If above), and `GET .../signals` renders
  `skip_epic` in `admitted_signals` for a fresh `blocked` park.

**Frontend — the predicate and the confirm line, not symmetric with 6.4's `skip.ts`.**
- `src/lib/run/skip.ts` — add `SKIP_EPIC_STOP_KINDS` (the eight park kinds
  `VALID["skip_epic"].park_kinds` admits: `blocked, checkpoint, verify_failed, timeout,
  push_rejected, protected_path, misconfigured, internal`), `SKIP_EPIC_LABEL = 'Skip epic'`,
  `offersSkipEpic(kind, admitted, template)` (kind in the list, `admitted.includes
  ('skip_epic')`, `template === 'epic' || template === 'initiative'` — the client twin of
  `_has_epic_frame`, keyed on the Run's own `template` rather than a story id, see Boundaries),
  `currentEpicNumber(detail)` (regex `epics\[(\d+)\]` over `currentStepPath(detail)`, `+1`,
  else `1`), `skipEpicConfirmLine(epicNumber, pushRejected)` (verbatim, the two tails the
  brief states).
- `src/components/run/StopBody.tsx` — alongside the existing `skip_story` append, compute
  `offersSkipEpic(...)` and append `skip_epic` when offered and not already present (it
  already is, via `blockedSignals`/`checkpointSignals`, on `blocked`/`misconfigured`/
  `checkpoint`); in the button-row map, render `ConfirmAction` for `s === 'skip_epic'` too
  (label/confirmLabel `SKIP_EPIC_LABEL`, line `skipEpicConfirmLine(currentEpicNumber(detail),
  kind === 'push_rejected')`), replacing the current plain-button branch for that kind.
- `src/lib/run/detail.ts::summaryLine` — after the existing `skipped: {ids}` clause, append
  ` · epics skipped: {ns}` when `summary.skipped_epics` (`?? []`, optional on the wire) is
  non-empty. The existing frozen `summaryLine` tests in `run-detail-lib.test.ts` build
  `summary` literals without `skipped_epics`, so the field must stay optional on the wire
  (see Boundaries) for those to keep compiling and passing unedited.
- New test files: `tests/unit/run-skip-epic-lib.test.ts` (`offersSkipEpic`,
  `currentEpicNumber`, `skipEpicConfirmLine`), `tests/unit/run-stop-body-skip-epic.test.ts`
  (the confirm renders on the four/five bodies `blockedSignals`/`checkpointSignals`/
  `stopSignals` alone cannot reach — `verify_failed`, `timeout`, `protected_path`,
  `internal`, `push_rejected` — and the push-rejected sentence differs),
  `tests/unit/run-detail-lib-skipped-epics.test.ts` (`summaryLine`'s new clause),
  `tests/e2e/run-detail-skip-epic.spec.ts` (the confirm's open/confirm/keep interaction over
  a mocked `/api/runs/{id}/detail`, the same mocking pattern `run-detail-skip-story.spec.ts`
  uses — no compose stack needed for this, unlike the backend e2e decision above).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/application/use_cases/signals.py` -- `skip_epic` joins
  `_in_scope` -- the kind AD-13 and 4.5 already admit and implement finally has a reachable
  entry point.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` -- `Summary.
  skipped_epics` -- the epic half of the read model the brief names.
- `backend-api/src/orchestrator/application/use_cases/run_views_summary.py` -- `skipped_epics
  ()`, wired into `summary()` -- computes it from the frame rows already read.
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- `SummaryOut.skipped_epics`,
  `_drop_default`-guarded -- publishes it without breaking an existing fixture.
- `backend-api/tests/unit/application/test_handle_signal.py` -- remove the `skip_epic`
  registry row and helper -- the gate has landed.
- `backend-api/tests/unit/application/test_answer_signal_scope.py` -- remove the `skip_epic`
  registry row -- ditto.
- New backend test files per the Code Map above (five).
- `web-client/src/lib/run/skip.ts`, `src/components/run/StopBody.tsx`, `src/lib/run/
  detail.ts` -- the predicate, the confirm rendering, the banner clause.
- New frontend test files per the Code Map above (four).
- `make openapi` -- regenerate: `SummaryOut.skipped_epics` is a new wire field.

**Acceptance Criteria:** the brief's own five (verbatim, `briefs/6-5-skip-epic.md`) govern;
implemented exactly as written there.

## Spec Change Log

## Review Triage Log

### 2026-09-09 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 2, low 1)
- defer: 1: (low 1)
- reject: 1: (low 1)
- addressed_findings:
  - `[medium]` `[patch]` `use_cases/signals.py`'s own module docstring said "this module
    refuses **five** of AD-13's ten kinds" and named only `answer`/`skip_story` as landed —
    both stale the moment `skip_epic` joined `_in_scope`. Corrected to "four", and
    `skip_epic`/SPEC CAP-5 (6.5) added to the landed list.
  - `[medium]` `[patch]` `run_views_summary.py::offersSkipEpic`'s original Code Map design
    (a `template === 'initiative'` name check for `_has_epic_frame`'s second branch) is a
    false negative against a custom-named copy of an initiative-shaped Template — the system
    supports registering any Template under any name, and only the parked row's own path,
    not the Run's `template_name`, is symmetric with the server's actual `epic_frame(park_
    path) is not None` check. `offersSkipEpic` now reads the parked row's own `epics[n]`
    bracket (via `currentStepPath`, already resolved for `currentEpicNumber`) instead of
    approximating with the Template name a second time; signature widened from
    `(kind, admitted, template)` to `(detail, kind, admitted)`, and the affected unit tests
    rewritten to match (`run-skip-epic-lib.test.ts`).
  - `[low]` `[patch]` `skipped_epics()`'s own multi-epic accumulation (two epics skipped in
    the same `done` Run, over two separate `skip_epic` signals) had no test exercising the
    loop past its first match — added `test_both_epics_of_an_initiative_skipped_in_turn_are_
    both_listed_in_order` to `test_run_views_summary_skipped_epics.py`.

Deferred (pre-existing, not caused by this story, recorded in frontmatter `deferred`):
`blockedSignals`/`checkpointSignals` can still advertise `skip_epic` where `_has_epic_frame`
would refuse it (a Template with no epic frame at all) — the same shape of gap 6.4 already
declined to close for `skip_story`, for the same reason (those two filters are frozen).

Rejected as noise: the frontend's unanchored `epics\[(\d+)\]` regex versus the backend's
end-anchored `bracket_index` — different jobs (extracting a bracket from the *middle* of a
full path versus from an already-isolated frame prefix), not a discrepancy.

### 2026-09-09 — Review pass (operator ruling applied)
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 1, low 0)
- defer: 1: (medium 1)
- reject: 0
- addressed_findings:
  - `[medium]` `[patch]` the operator's ruling authorised retargeting `test_signals_router.
    py::test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet` from `skip_epic` to
    `budget_raise`; checked against the file's own `push_rejected_world()` fixture before
    applying anything and found `budget_raise` is not AD-13-admitted on a `push_rejected`
    park at all (`VALID["budget_raise"].park_kinds == {"budget"}`), so that literal retarget
    would fail with the wrong 409 body. Retargeted to `terminal_start` instead — admitted on
    every park kind, still out of `_in_scope` through 6.6 — two literal string swaps, nothing
    else in the file changed. `make test` now exits 0 (5230 passed, 1 skipped, 0 failed).

Deferred (this pass): the compose-stack/e2e-api integration gap for `skip_epic` is now
stated explicitly in frontmatter `deferred` (medium), per the operator's second note — not a
new finding, a plainer restatement of what the `Never` clause above already said.

## Design Notes

**Why `offersSkipEpic` reads the parked row's own path, not only `template`.** 6.4's
`offersSkipStory` needed a per-current-Story id because `_has_story_frame` can be false at a
stop with no Story frame at all (e.g. `push_rejected` on the epic's own `push` row) — the
same stop kind `skip_epic` *must* work on. The Code Map originally planned `_has_epic_frame`'s
second branch as a `template === 'initiative'` name check, reasoning that every row of an
`initiative` Run's plan is nested under the single `epics` loop `templates/initiative.yaml`
declares. Implementation found a sharper fact already at hand: `_has_epic_frame`'s own second
branch is `epic_frame(run.park_path) is not None` — a path check, not a name check — and a
custom-named copy of an initiative-shaped Template (the system supports registering any
Template under any name) would defeat the name check while the path still carries its
`epics[n]` bracket. `offersSkipEpic` therefore takes the whole `detail` and asks the same two
questions `_has_epic_frame` does: `run.template === 'epic'` (byte-identical to the server's
`template_name == EPIC_TEMPLATE` branch, since `RunSummaryOut.template` is `run.template_name`
verbatim), or `currentStepPath(detail)` carries an `epics[n]` bracket — the exact fact
`currentEpicNumber` below already reads for the confirm line's own number, so no second
proxy is introduced.

**Why the epic number still needs `currentStepPath`, even though the offer predicate does
not.** The confirm *line* names `{n}`, which the predicate does not need to compute. `Alert`
carries no epic index of its own (unlike `checkpoint_story`, 6.2, added because no other field
carried that fact); `currentStepPath(detail)` already resolves the parked row's own `path`
from `gate_record[]` for `logTail`, and that path's own `epics[N]` bracket is the same fact
`bracket_index` reads server-side for `summary.skipped_epics` — reusing it needs no wire
change.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain/application strict), import-linter (4
  contracts), env contract, test pairs, `gen:api --check`, eslint, prettier, `tsc --noEmit`,
  astro check all clean.
- `make test` -- expected: backend + web unit suites green; `domain/`+`application/` **100%**
  branch coverage held, including every new branch in `skipped_epics`/`offersSkipEpic`.
- `make openapi` -- expected: `contracts/openapi.json`/`schema.d.ts` regenerate with
  `SummaryOut.skipped_epics`; `gen:api --check` clean afterward.
- `make e2e` -- expected: green on the disposable stack (existing suite; no new scenario,
  see Never).
- `make e2e-ui` -- expected: green, including the new mocked-response Playwright spec.

## Auto Run Result

Status: done

**Summary.** `skip_epic` reaches its effect: `handle_signal`'s scope gate now admits the
kind (the 4.5 writer needed no change — every one of the brief's three writer scenarios was
already built and unit-tested since story 4-5), `summary.skipped_epics` names the 1-based
epic numbers a rejected push gave up on, and every stop body FR-20 lists carries a *Skip
epic* control behind the reusable inline confirm, including the `push_rejected` sentence
variant. The anchor conflict this story's own scope-gate widening produced was
resolved by an operator ruling (see below); every gate is green.

**Files changed** (backend): `application/use_cases/signals.py` (`skip_epic` joins
`_in_scope`; module docstring corrected to say "four" refused kinds and name 6.5),
`application/use_cases/run_view_types.py` (`Summary.skipped_epics`, defaulted),
`application/use_cases/run_views_summary.py` (`skipped_epics()`, wired into `summary()`),
`api/schemas/run_views.py` (`SummaryOut.skipped_epics`, `_drop_default`-guarded). Five new
test files: `test_skip_epic_signal.py`, `test_skip_epic_signal_router.py`,
`test_run_views_summary_skipped_epics.py`, `test_run_view_schemas_skipped_epics.py`. Two
pending-gate registry rows removed (`test_handle_signal.py`, `test_answer_signal_scope.py`
— both operator-named exceptions). `test_signals_router.py`'s own scope-gate illustration
retargeted from `skip_epic` to `terminal_start` under the operator's ruling (see below) —
the only other change to that file.

**Files changed** (frontend): `lib/run/skip.ts` (`offersSkipEpic`, `currentEpicNumber`,
`skipEpicConfirmLine`, `SKIP_EPIC_STOP_KINDS`, `SKIP_EPIC_LABEL`), `components/run/
StopBody.tsx` (appends the control on the five stops `blockedSignals`/`checkpointSignals`/
`stopSignals` cannot reach, renders every `skip_epic` as a confirm), `lib/run/detail.ts`
(`summaryLine`'s new `epics skipped: {ns}` clause). Four new test files: `run-skip-epic-lib.
test.ts`, `run-stop-body-skip-epic.test.ts`, `run-detail-lib-skipped-epics.test.ts`,
`tests/e2e/run-detail-skip-epic.spec.ts`. `contracts/openapi.json`/`src/api/schema.d.ts`
regenerated with `SummaryOut.skipped_epics` (optional on the wire).

**Review findings breakdown:** 3 patch (0 high, 2 medium, 1 low) — all applied and
re-verified (see Review Triage Log). 1 deferred (low, frontmatter `deferred`). 1 rejected as
noise.

**Follow-up review recommendation:** `true` — patched severities were 0 high, 2 medium and 1
low, so the score is 3 × 2 + 1 × 1 = 7, which reaches the threshold of 5.

A second pass followed, once the operator ruled on the anchor conflict below: one
`[medium]` `[patch]` (the anchor retarget itself, `skip_epic` → `terminal_start`, since
`budget_raise` — the operator's own suggested kind — is not valid on
`push_rejected_world()` per AD-13's own table and would have asserted the wrong refusal
text; see the Review Triage Log's second entry for the full reasoning) and one
`[medium]` `[defer]` (no compose-stack proof exists for `skip_epic`, now stated plainly
in frontmatter `deferred` per the operator's second note). That pass's own score is 3 ×
1 = 3, under the threshold on its own, but `followup_review_recommended` stays `true`
from the first pass's own 7.

**Verification performed** (foreground, real output, from a clean tree, re-run in full
after every patch and again after the anchor retarget below):
- `make lint` — pass: ruff, ruff format, mypy (domain/application strict), import-linter (4
  contracts kept), env contract (34/40 agree), test pairs (189 backend modules / 85 web
  modules), `gen:api --check` clean, eslint, prettier, `tsc --noEmit`, astro check (0 errors).
- `make test` — **pass: 5230 passed, 1 skipped, 0 failed**; `domain/`+`application/` still
  **100%** branch coverage; web-client 1135 passed across 86 files (`make test` exits 0).
- `make openapi` — pass: `contracts/openapi.json`/`src/api/schema.d.ts` regenerate with
  `SummaryOut.skipped_epics`; stable across repeated runs (no drift).
- `make e2e` — pass: 175 passed, 11 deselected, 38 subtests, on the disposable `aio-e2e`
  stack with `ORCH_TEST_MODE=1` (same count as before this story — no new e2e-api scenario
  was added for `skip_epic`; see the spec's own `Never` clause and the frontmatter `deferred`
  item for why, stated plainly rather than implied by this green count).
- `make e2e-ui` — pass: 140 passed, including the 5 new `run-detail-skip-epic.spec.ts` tests.
  The two Epic-5 screenshot deliverables (`_bmad-output/implementation-artifacts/
  epic-5-screens/{01,02}-*.png`) changed on this run (story 5.10's own anchor spec, expected
  per the epic's own environment notes) and the new bytes are committed.

**Anchor conflict — halted, then resolved by an operator ruling covering the whole arc.**

File: `backend-api/tests/unit/test_signals_router.py`
Test: `test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet`
Assertion: posting `{"kind": "skip_epic"}` against `push_rejected_world()` (park_kind
`push_rejected`, default `template_name="epic"` per `writer_fixtures.build_run`) answers
`409` with `detail == "skip_epic not available yet"`.

Why unavoidable: this story's entire surface is `use_cases/signals.py::_in_scope` admitting
`skip_epic` unconditionally (the same unconditional join `skip_story` made in 6.4, and the
only way any of the brief's three writer scenarios — already fully built and unit-tested
since 4.5 — becomes reachable). `push_rejected_world()`'s exact world already satisfies
`validate()` (AD-13 admits `skip_epic` on `push_rejected`, and `_has_epic_frame`'s
`template_name == "epic"` branch is true for this fixture's default template), so once
`_in_scope` admits the kind, this specific request genuinely returns `200` (the writer
applies: `push`/`link` → `skipped`, the Run — the last epic — ends `done`), not `409`. There
is no narrower scoping that satisfies the brief's own push-rejected acceptance criterion
while keeping this one world refused: both use the identical code path, and the writer's own
support for exactly this scenario (a plain `epic`-template Run's rejected push, ending
`done`) is pre-existing, passing coverage from story 4-5
(`test_signal_run.py::test_skip_epic_on_a_rejected_push_of_the_last_epic_ends_the_run`).

This file predates the branch (introduced in story 4-9, Epic 4, confirmed via `git log
--diff-filter=A`) and is not one of the two registries the operator pre-authorised
(`test_handle_signal.py`, `test_answer_signal_scope.py`); the standing rule states plainly
that anything predating the branch "still require[s] an operator ruling every time." No
earlier story in this epic hit this specific collision: 6.4's own `skip_story` never reaches
this test's world, because AD-13 excludes `push_rejected` from `skip_story`'s own valid park
kinds (`VALID["skip_story"].park_kinds = ANY_PARK - {budget, plan_stale, push_rejected}`), so
`validate()` refuses it there with its own text before this file's scope-gate example is
ever exercised. This story is the first (and only) one whose own kind is the file's
illustrative "not yet built" example.

**The operator's ruling** (covering the whole arc, not just this story): the test names the
*mechanism* ("a kind this epic does not build yet is refused with this exact sentence"); the
kind it happens to illustrate with is only the vehicle, replaceable by whichever story next
invalidates it, under the same discipline — swap only the kind in the request body and the
expected `detail` string (plus the docstring/name, if either names the old kind); nothing
else in the file changes. When the last such kind lands, that story may retire the test and
the `_refuse_out_of_scope` branch it proves, given coverage of the endpoint's real behaviour.

**Applied, with one deviation from the operator's own suggested kind, reported rather than
silently substituted.** The ruling suggested retargeting to `budget_raise`. Checked against
`push_rejected_world()` (the fixture the shared `api` pytest fixture in that file actually
uses) before applying anything: `rules/signals.py::VALID["budget_raise"].park_kinds ==
frozenset({"budget"})` — `budget_raise` is **not** admitted by AD-13's own table on a
`push_rejected` park at all. Retargeting to it literally, as instructed, would make
`validate()` refuse the request *before* `_in_scope` is ever reached, with a different 409
body (`"signal budget_raise invalid for status needs_you / park push_rejected"`, AD-13's own
refusal text) instead of the scope gate's `"budget_raise not available yet"` — the retargeted
assertion would still fail, just with a different, wrong message, defeating the point of
getting `make test` green. Confirmed empirically (`validate(...)` raised for `budget_raise`
on this exact world, before touching the file) rather than assumed. `terminal_start` is the
kind that actually satisfies the ruling's own intent on this fixture unchanged: AD-13 admits
it on every park kind (`park_kinds=ANY_PARK`) with only `extra=_no_terminal_session`, which
`push_rejected_world()` — no `terminal_session` override — satisfies by the `Run` entity's
own default (`terminal_session: bool = False`); it is still outside `_in_scope` (lands in
6.7, the terminal path) and stays that way through 6.6. Applied: the request body's `"kind"`
and the expected `detail` string both changed from `skip_epic`/`"skip_epic not available
yet"` to `terminal_start`/`"terminal_start not available yet"` — two literal string swaps,
nothing else in the file touched (no docstring named `skip_epic`, so nothing else to
correct). Strictly-exceeding coverage already existed in this story's own new file,
`test_skip_epic_signal_router.py` (`test_skip_epic_on_a_rejected_push_now_succeeds_over_the_
router`, `test_get_renders_skip_epic_in_admitted_signals_for_a_fresh_blocked_park`), kept in
the same commit as the retarget per the ruling.

**Residual risks.** One low item deferred (`blockedSignals`/`checkpointSignals` can still
advertise `skip_epic` where `_has_epic_frame` would refuse it — the same pre-existing shape
of gap 6.4 already declined to close for `skip_story`) and one medium item deferred (no
compose-stack/e2e-api proof exists for `skip_epic`; see frontmatter `deferred` for the full
account) — neither blocks any acceptance criterion. `make test` is green with 0 failures.
