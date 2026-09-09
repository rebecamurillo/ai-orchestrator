---
title: 'UJ-3 proven end to end'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      `E2E_BACKEND=real make e2e-ui` fails 43 of the suite's 159 specs, none of them this
      story's: they mock `page.route()` for the browser's own fetches but read their Projects,
      Repositories and Templates from the stub backend server-side (SSR), and a real stack
      holds none of that fixture data.
    evidence: |-
      Run against a test-mode `aio-e2e` stack: 115 passed, 43 failed, 1 skipped, with
      `uj3.spec.ts` itself passing in 13.7 s. Every failure is an SSR read of stub fixture
      ids (`projects.spec.ts` `?id=<MIXED>`, `templates.spec.ts`, `new-workflow.spec.ts`,
      `shell.spec.ts`). Closing it means `test.skip(USE_REAL_BACKEND, ...)` in ten existing
      spec files, all anchors, so it needs an operator ruling rather than a patch here.
    location: >-
      web-client/tests/e2e/ (projects, templates, new-workflow, project-form, shell,
      smoke, repository-init, board, runs-queue, template-diagram)
    severity: medium
  - summary: >-
      `skip_epic` still has no compose-stack proof; UJ-3's journey could not add one, because
      the e2e saves `templates/epic.yaml` under a name of its own and `_has_epic_frame`'s
      literal `template_name == "epic"` branch can therefore never be true for a fixture Run.
    evidence: |-
      Recorded first by story 6-5 (its own frontmatter `deferred`). Confirmed unchanged here:
      `application/rules/signals_table.py::_has_epic_frame` is `template_name == EPIC_TEMPLATE
      or epic_frame(run.park_path) is not None`, and `epic@1` plans carry no `epics[n]`
      bracket, while `helpers/gates_fixture.py::epic_template_as` must rename the Template so
      `tests/e2e/test_templates.py`'s `pinned_by == 0` assertion for `epic@1` keeps holding.
    location: >-
      backend-api/tests/e2e/helpers/gates_fixture.py::epic_template_as
    severity: medium
  - summary: >-
      The ARTIFACTS panel can only edit a file the tree lists, so a spec-folder file the agent
      deleted cannot be put back from the screen; `PUT /runs/{id}/files` creates it happily.
    evidence: |-
      `ArtifactsPanel` fetches the tree and edits a selected row; there is no "new file"
      control. Found while building the browser journey, which therefore makes the repair
      through the API. Not a defect of anything 6-3's brief asked for.
    location: >-
      web-client/src/components/run/ArtifactsPanel.tsx
    severity: low
baseline_revision: '7ed91723198788c19cf7a6e4b24e778b47bcc467'
---

<intent-contract>

## Intent

**Problem:** Every gate this epic built is proven one at a time — 6.1's Answer, 6.2's two
checkpoints, 6.3's edit, 6.4's skip, 6.6's raise and Accept, 6.7's terminal — and nothing
drives them *together* through one Run on the real stack. UJ-3 ("come back cold and unblock")
is a sequence, and a sequence can be broken while every step of it passes on its own; the
recurring failure of this codebase (a signal effect that moves a row but enqueues nothing) is
exactly the class of defect only a sequence catches.

**Approach:** One API-driven journey Run on the `fake` harness that walks the gates fixture's
three stories through blocked → Answer → done, spec checkpoint → Continue, and verify failed
twice → operator edit → Skip story, ending `done` with `summary.skipped == ["3"]`; a second
Run parked `blocked` and cancelled, with the worktree and the never-pushed branch really gone;
and one Playwright journey over the same paths in a real browser against a real stack. The
`fake` scenario schema gains the one thing the verify-failure path needs — `delete: [paths]`.

## Boundaries & Constraints

**Always:**
- New coverage in new files. `tests/e2e/test_uj3.py`, `web-client/tests/e2e/uj3.spec.ts`, and
  new unit files for anything shipped code gains. No existing test file is edited.
- The scenarios drive the *product*: every state change is an HTTP call an Operator could
  make (`POST /runs/{id}/signals`, `PUT /runs/{id}/files`) or something the engine did. The
  suite never writes a row, never touches a worktree, and never patches a running process.
- `ORCH_TEST_MODE=1` is required, not optional: `test_mode` fails by name when the `fake`
  harness is not seeded, the way every other Epic 6 e2e module already does. Nothing skips.
- Additive fixture changes only where an existing fixture file is touched, its existing
  consumers (`test_answer_signal.py`, `test_checkpoint_signals.py`, `test_skip_story.py`,
  `test_spec_edit.py`, `test_budget_raise.py`, `tests/unit/test_gates_fixture.py`) must stay
  green unchanged.
- `AD-13` stays the authority: a defect found in shipped behaviour is fixed at its rule or
  its writer, with unit coverage in a new file, never worked around in the scenario.
- Module cap 400 lines on `src/`; `scenario.py` (227) and `adapter.py` (291) have room.

**Block If:**
- A scenario cannot be built without editing or deleting an assertion in an existing test
  file, or any line of `SPEC.md` / `stories.yaml` / `epics.yaml` / an `AGENTS.md`.
- A defect the scenarios reveal needs a design decision nobody has made, or a fix large
  enough to be its own story. Record it precisely; do not invent a default.

**Never:**
- No new product feature. No `skip_epic` integration proof (6.5 recorded why it is
  unreachable through `epic_template_as`; not this story's scope).
- No `pgid` on a resumed dispatch and no `model`/`budget_usd_remaining` on `Harness.resume`
  — deferred to Epic 7 by the operator.
- `fake` never becomes reachable outside `ORCH_TEST_MODE`, and never enters a shipped
  Template's `harness` enum.
- No edit to `.env` and no `ORCH_TEST_MODE` in the dev stack: the browser journey runs
  against a test-mode stack of its own.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `delete:` names one file | scenario `delete: [a/b.txt]`, file present in the worktree | the file is gone before the process starts; `commit: true` commits its removal | none expected |
| `delete:` names a missing file | file already absent | no-op, the dispatch proceeds | never raises |
| `delete:` names a directory | `delete: [specs]` | ignored (files only) | never raises |
| `delete:` escapes the worktree | `delete: [../x]`, `delete: [/etc/passwd]` | ignored entirely | never raises |
| `delete:` malformed | not a list; entries not strings; blank strings | parsed as `()` | never raises |
| verify fails twice | story 3 deletes the spec-scoped gate file, redispatch fails again | park `verify_failed · verify failed 2/2`, `skip_story` admitted | n/a |
| operator repairs the gate file | `PUT /runs/{id}/files` inside the spec folder while parked | 200, one `spec: operator edit (orchestrator)` commit, one `spec_edit` gate record | 403 outside the folder, 409 on a list file |
| `skip_story` after the repair | park is on the frame's `verify` row; `build` already `done` | the frame's done-checkpoint row `skipped · skipped by operator` (the `done` build is left alone — `FINISHED` rows are never re-written), verify re-runs green, commit-guard commits under `story 3: skipped by operator` | n/a |
| `cancel {confirm: true}` on a `blocked` park | second Run, branch created and never pushed | Run `cancelled`, worktree gone, branch gone from the base clone | idempotent, a second signal is refused |

</intent-contract>

## Code Map

**The one shipped change: `delete: [paths]` in the `fake` scenario schema.**
- `backend-api/src/orchestrator/infrastructure/harness/fake/scenario.py` (227 lines) —
  `Scenario` gains `delete: tuple[str, ...] = ()`; `parse` reads `loaded.get("delete")`
  through a new `_deletes(value)` built exactly like `_files`: not a list → `()`, a
  non-string or blank entry → dropped, an entry that `_escapes` (absolute, or any `..`
  part) → dropped. Never raises (the module's own contract). The YAML example in the module
  docstring gains the key.
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` (291 lines) —
  `_apply` deletes first, then writes `files`, then the story file: a scenario that deletes
  and re-creates the same path is then the write, not the delete. `Path.unlink()` guarded
  with `missing_ok=True` and skipped for a directory. The module docstring gains a paragraph
  naming `delete:` and why it exists (a `verify` failure needs the gate file *gone*, and a
  scenario cannot express that with `files:` alone).
- New `backend-api/tests/unit/test_fake_harness_delete.py` — the matrix above over
  `scenario.parse` and `adapter._apply` on `tmp_path`. Existing
  `test_fake_harness_scenarios.py` / `test_fake_harness_adapter.py` are untouched.

**The fixture, additively (`fixtures/gates-repo/`).** Read-only evidence: `GATE_OK` sits at
the repository *root* and `PUT /runs/{id}/files` is scoped to the Run's own `spec_folder`
(`application/use_cases/run_files.py::_within_spec_folder`), so the brief's "restore
`GATE_OK` through an operator `PUT`" is only satisfiable against a gate file *inside* the
spec folder. Root `GATE_OK` and `check.sh` stay exactly as they are, for every existing
consumer.
- New `fixtures/gates-repo/specs/gates/GATE_OK` (`1`) and new
  `fixtures/gates-repo/check-spec.sh` — `check.sh`'s twin, reading the spec-folder copy. The
  UJ-3 Runs register their Repository with `quality_gate_command: "sh check-spec.sh"`; every
  other suite keeps `sh check.sh` and is untouched by the deletion below.
- `fixtures/gates-repo/.fake-harness/3/default.yaml` — one added key,
  `delete: ["specs/gates/GATE_OK"]`, plus the comment saying why. This is story 3's *first*
  dispatch in every suite; for `sh check.sh` consumers the deleted path is not their gate, so
  `test_checkpoint_signals.py` still walks story 3 to a green `verify`.
- New `fixtures/gates-repo/.fake-harness/3/attempt-2.yaml` — reachable only from a Run that
  dispatches story 3 twice, i.e. only from this story's own verify-failure path. Writes the
  same `3-ship.md` at `status: done` plus an uncommitted `SHIP_NOTES.md`, and **no**
  `commit:` — the leftover is what makes the post-skip commit-guard produce a real commit
  under the rewritten message rather than `no changes`.
- `fixtures/gates-repo/README.md` — documents `delete:` and the second quality gate.
- New `backend-api/tests/unit/test_gates_fixture_uj3.py` — pins the four facts the e2e
  depends on (the spec-scoped gate file and its script, story 3's deletion, attempt 2's
  no-commit leftover). `tests/unit/test_gates_fixture.py` is untouched and still passes:
  its `SCENARIOS` glob picks the new file up and it satisfies both parametrised assertions
  (non-empty scenario, `story_file` present, slug `ship`).

**The API scenarios: `backend-api/tests/e2e/test_uj3.py` (new).** Reuse, verbatim:
`tests/e2e/helpers/gates_fixture.py::GatesFixture`/`epic_template_as`;
`tests/e2e/test_answer_signal.py::poll_until`/`detail_of`/`step_status`;
`tests/e2e/test_run_creation.py::PROJECTS`/`RUNS`/`create_project`/`clone_check`;
`tests/e2e/test_signals.py::run_check` (the two-route "is the worktree gone, is the branch
gone" check) and `SQLAlchemyRunRepository` for the Run's own `worktrees`.
- New `backend-api/tests/e2e/helpers/uj3_reads.py` — `Uj3Reads(GatesFixture)`, additive
  subclass adding `subject(worktree, ref)` (`git log -1 --format=%s`) and
  `commit_matching(worktree, message)` (`git log --format=%H --grep=... -1`), through the
  inherited `_either` two-route runner. Needed because the redispatch's `## Verify Failure`
  file is read at the prepare commit `application/steps/agent.py::PREPARE_MESSAGE` wrote,
  and the post-skip commit-guard message is read off the branch.
- One journey Run covers A→B→C (one clone, one plan, the SPEC's own success signal in
  order); a second Run covers D and is started only after the journey Run is terminal, so
  the suite never holds more than one of `MAX_ACTIVE_RUNS=2` global slots at a time.
- Module marker `uj3` (registered in `backend-api/pyproject.toml` `markers`, beside
  `durability`); the default `E2E_MARKER = not durability` still selects it, and
  `E2E_MARKER=uj3 make e2e-api` runs the journey alone.
- Each Run's gate record is printed through the terminal reporter
  (`request.config.pluginmanager.get_plugin("terminalreporter")`), which writes past
  pytest's capture, so `make e2e-api` shows it on a pass as well as a failure.

**The browser journey: `web-client/tests/e2e/uj3.spec.ts` + `uj3-fixture.mjs` (both new).**
- `uj3-fixture.mjs` — the same bare-origin script the Python helper uses, run through
  `docker compose exec -T backend-api` (honouring `COMPOSE_PROJECT_NAME` / `COMPOSE_FILE` /
  `COMPOSE_ENV_FILE` when the caller exported them) or on this host, then `fetch` against
  `BACKEND_API_URL` with the bearer to create Project, Repository, clone-check, Template and
  Run, and poll to the `blocked` park.
- `uj3.spec.ts` — `test.skip(!USE_REAL_BACKEND, …)`, so the default `make e2e-ui` is
  unaffected. Test ids already on the surface: `board-column-needs_you`,
  `board-card-{id}` (`src/components/RunCard.tsx`), `wf-header`/`wf-token`
  (`components/run/Header.tsx`), `wf-question` (`QuestionBlock.tsx`), `wf-answer` +
  `wf-signal-answer` (`AnswerBox.tsx`), `wf-signal-continue` and the `ConfirmAction` trio
  `wf-signal-skip_story` / `wf-confirm-skip_story-yes` (`StopBody.tsx`, `ConfirmAction.tsx`),
  `wf-summary` (`Banner.tsx`, the `DON` branch, carrying `skipped: 3` via
  `lib/run/detail.ts::summaryLine`), and the `your active time` row rendering `—`
  (`CostBlock.tsx`).

**Read-only evidence gathered (do not re-derive):**
- `templates/story.yaml`: `verify.on_fail = {redispatch: build, max: 1}` → two failures park
  `verify_failed` with `apply_step_result.py::VERIFY_FAILED` = `verify failed 2/2`.
- `signal_effects.py::_skip_frame` skips `SKIPPABLE_KINDS` (`agent`, `checkpoint`) of the
  frame — `stories[2].after` is in frame `stories[2]`, so the done checkpoint goes with it —
  rewrites the commit-guard message to `story 3: skipped by operator`, and leaves the parked
  `verify` row for `resume_from` to re-queue.
- `run_views_summary.py::skipped_stories` lists a frame when any of its rows is
  `skipped · skipped by operator`, so story 3 is listed although its `build` reached `done`.
- `pr_link.py` writes no compare URL for a `file://` origin ("no compare link for this
  host"), so a fixture Run ends `done` with `compare_urls == []`; the skipped id is read off
  `wf-summary`, not off the compare line.
- `git_commit.py`: nothing staged → `done` with reason `no changes` (scenario A's
  commit-guard assertion); otherwise a commit under `with_resolved["message"]`.
- `record_trajectory.py::_human_actions` keeps `{event, at}` for every park or Operator
  signal about a row of the frame — the `answer` event scenario A asserts, read from the
  `trajectory` table (no API surface exposes it).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/infrastructure/harness/fake/scenario.py` -- add
  `Scenario.delete`, `_deletes`, `_escapes`, and the docstring key -- the schema the
  verify-failure scenario needs.
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` -- delete before
  writing in `_apply`; document `delete:` in the module docstring -- the brief's own
  implementation note.
- `backend-api/tests/unit/test_fake_harness_delete.py` -- new file covering every row of the
  I/O matrix's `delete:` half -- the schema is shipped code and must be unit-covered.
- `fixtures/gates-repo/specs/gates/GATE_OK`, `fixtures/gates-repo/check-spec.sh` -- new: a
  quality gate whose file lives inside the spec folder -- so the operator's repair is a real
  `PUT /runs/{id}/files`, not a shell command the product does not offer.
- `fixtures/gates-repo/.fake-harness/3/default.yaml` -- add the deletion -- makes story 3's
  first verify fail for a `check-spec.sh` Run and nothing else.
- `fixtures/gates-repo/.fake-harness/3/attempt-2.yaml` -- new: the redispatch's scenario,
  leaving an uncommitted file -- so the post-skip commit-guard really commits.
- `fixtures/gates-repo/README.md` -- document both -- the fixture explains itself.
- `backend-api/tests/unit/test_gates_fixture_uj3.py` -- new: pin the fixture facts the e2e
  depends on -- a fixture typo must fail here, not as a timeout in `make e2e`.
- `backend-api/tests/e2e/helpers/uj3_reads.py` -- new: `Uj3Reads(GatesFixture)` with
  `subject`/`commit_matching` -- reads the branch needs that `show`/`tree` cannot answer.
- `backend-api/pyproject.toml` -- register the `uj3` marker -- `--strict-markers` is on.
- `backend-api/tests/e2e/test_uj3.py` -- new: scenarios A, B, C on one journey Run and D on
  a second -- the story.
- `web-client/tests/e2e/uj3-fixture.mjs` -- new: origin + Run setup for the browser journey.
- `web-client/tests/e2e/uj3.spec.ts` -- new: the UX journey, skipped unless
  `E2E_BACKEND=real`.

**Acceptance Criteria:**
- Given the compose stack in test mode, when `make e2e-api` runs, then `test_uj3.py`'s
  scenarios A–D all pass and each Run's gate record is printed to the terminal.
- Given scenario A, when the Answer is posted, then the signal response says `running`, the
  next API read (within 5 s) still says `running`, the archived
  `specs/gates/stories/.answers/1-attempt-1.md` on the branch holds the question and
  `## Human Answer` with the operator's text, the rewritten `1-notify.md` carries the
  verbatim Answer clause, `stories[0].verify` is `done`, `stories[0].commit-guard` is `done`
  with reason `no changes`, and the `trajectory` row for story `1` carries an `answer`
  human action.
- Given scenario B, when the spec checkpoint parks, then `GET /runs/{id}/files?path=` reads
  the planned `2-plan.md` at `status: ready-for-dev`, and after `continue` the story file on
  the branch echoes a prompt that does not contain `Halt after planning.` and story 2's
  commit-guard is `done`.
- Given scenario C, when story 3's verify fails twice, then the redispatch's prepare commit
  holds `3-ship.md` at `status: in-progress` with `## Verify Failure`, the Run parks
  `verify_failed` with reason `verify failed 2/2`, `skip_story` is admitted; and when the
  Operator `PUT`s `specs/gates/GATE_OK` back and posts `skip_story`, then
  `stories[2].after` (the done checkpoint, in the same frame) is
  `skipped · skipped by operator`, `stories[2].verify` is `done`, the commit-guard's commit subject is
  `story 3: skipped by operator`, `push` and `link` are `done`, the Run is `done` and
  `summary.skipped == ["3"]`.
- Given scenario D, when `cancel {confirm: true}` is posted on a second Run parked
  `blocked`, then the Run is `cancelled`, its worktree path no longer exists and its created
  branch is gone from the base clone.
- Given `E2E_BACKEND=real` against a test-mode stack, when the Playwright journey runs, then
  it opens the `BLK` card from the Board, reads the question, types and submits the answer,
  sees the card running again, clicks *Continue* at the spec checkpoint, skips story 3 at
  the `verify_failed` stop, and ends on `DON` with `skipped: 3` in the summary line and the
  active-time row still showing `—`.
- Given every fix made along the way, when `make lint && make test && make openapi && make
  e2e && make e2e-ui && make durability` run, then all are green from a clean tree.

## Spec Change Log

## Review Triage Log

### 2026-09-09 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 1, medium 0, low 2)
- defer: 3: (high 0, medium 2, low 1)
- reject: 5: (high 0, medium 0, low 5)
- addressed_findings:
  - `[high]` `[patch]` `walk.py::_sent_back` resumed a Run the exhausted bound had already
    parked. The rows an exhausted redispatch leaves are identical to the ones mid-loop leaves
    (target `done`, gate `error`), and `next_row` is called on parked Runs
    (`test_walk_use_case.py::test_a_run_stopped_on_a_row_queues_nothing_ahead_of_it` pins
    that contract), so `verify failed 2/2` would have resumed itself and the Operator's stop
    would never have held. Guarded on `require_run(...).status == RUNNING`, with
    `test_a_run_the_exhausted_bound_parked_is_never_resumed_by_this_rule` and
    `test_a_queued_run_that_has_not_started_is_left_to_the_planner` covering both sides.
  - `[low]` `[patch]` `walk.py`'s module docstring listed `next_row`'s finders and did not
    name the new one; a sentence added beside `_resumed_in_place`'s own.
  - `[low]` `[patch]` scenario C asserted the *second* verify failure but never the first
    turn of the loop. Split into `test_c_the_bounded_redispatch_really_ran_the_story_a_second
    _time` (the `redispatch` gate record, `build.attempts == 2`) and the park assertion.

## Design Notes

**Why one Run carries scenarios A, B and C.** SPEC CAP-8's own success signal is a
*sequence*: "a Run parked BLK … at story 4-2 the Run pauses at the spec checkpoint … story
4-3's verify fails twice and she skips it; by evening the card reads DON … with 4-3 listed
as skipped." Three separate Runs would prove three gates again, which the epic already has;
one Run is the only shape that proves the journey. The brief's own words agree — scenario D
is "a **second** Run".

**Why a second quality gate rather than moving `GATE_OK`.** The brief has the Operator
restore the gate file through `PUT /runs/{id}/files`, and that endpoint is scoped to the
Run's own spec folder by design (6.3's own 403). Root `GATE_OK` can therefore never be
restored that way. Moving it would edit `check.sh`, `README.md` and the frozen
`tests/unit/test_gates_fixture.py::test_the_quality_gate_passes_on_an_untouched_clone`
(which asserts `"GATE_OK" in check.sh` and the root file's content). A second, spec-scoped
gate script is purely additive, leaves every existing consumer byte-identical, and is
selected per Repository — which is what `quality_gate_command` already is.

**Why `attempt-2.yaml` rather than a second `default.yaml` key.** Story 3's `default.yaml`
is read on the first dispatch by every suite; `attempt-2.yaml` is read only when a Run
dispatches story 3 twice, which only the verify-failure path does. Putting the *uncommitted*
leftover there keeps `test_checkpoint_signals.py`'s single-dispatch story 3 exactly as it
was, and gives the post-skip commit-guard something to commit so the rewritten message
`story 3: skipped by operator` is observable on the branch rather than only in `with_resolved`.

**Reading the redispatch's story file.** `agent.py::_prepare_writes` writes the
`in-progress` + `## Verify Failure` rewrite and commits it as
`orchestrator: prepare story 3 attempt 2` *before* the harness runs and overwrites the file.
The assertion therefore reads the file at that commit, found by its message — a fact on the
branch, not a database row.

## Verification

**Commands:**
- `make lint` -- expected: ruff, ruff format, mypy, import-linter (4 contracts), env
  contract, test pairs, `gen:api --check`, eslint, prettier, `tsc --noEmit`, astro check all
  clean.
- `make test` -- expected: backend + web unit suites green; `domain/` + `application/` hold
  100 % branch coverage (this story adds no `domain`/`application` code).
- `make openapi` -- expected: no drift; the contract and `schema.d.ts` unchanged (no wire
  shape changes).
- `make e2e` -- expected: green on the disposable `aio-e2e` stack, including the new
  `test_uj3.py` scenarios; the previously-passing count grows by the new tests only.
- `make e2e-ui` -- expected: green, with `uj3.spec.ts` skipped (no real backend).
- `make durability` -- expected: green.
- The browser journey against a test-mode stack of its own (`make down` first if the dev
  stack is up — the Astro preview binds 4321 too):

  ```bash
  docker compose -p aio-e2e --env-file .env.e2e \
    -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait backend-api
  set -a; . ./.env.e2e; set +a
  cd web-client && pnpm build && \
    E2E_BACKEND=real BACKEND_API_URL="http://127.0.0.1:${BACKEND_API_PORT}" \
    ORCHESTRATOR_TOKEN="$ORCHESTRATOR_TOKEN" COMPOSE_PROJECT_NAME=aio-e2e \
    COMPOSE_FILE=docker-compose.yml:docker-compose.e2e.yml COMPOSE_ENV_FILE=.env.e2e \
    pnpm exec playwright test tests/e2e/uj3.spec.ts
  docker compose -p aio-e2e --env-file .env.e2e \
    -f docker-compose.yml -f docker-compose.e2e.yml down -v
  ```

  Expected: `uj3.spec.ts` passes. `COMPOSE_ENV_FILE` is repository-root-relative, because the
  fixture helper runs `docker compose` with the repository root as its working directory.
  Running the *whole* suite with `E2E_BACKEND=real` is not a gate — see frontmatter
  `deferred` for the 43 pre-existing specs that read stub fixtures server-side.

## Auto Run Result

Status: done

**Summary.** UJ-3 is proven end to end. `tests/e2e/test_uj3.py` walks one Run on the `fake`
harness through blocked → *Answer* → done, spec checkpoint → *Continue*, and quality gate
failed twice → inline repair → *Skip story*, ending `done` with `summary.skipped == ["3"]`;
a second Run parks `blocked` and is cancelled, with the worktree gone and the never-pushed
branch deleted from the base clone. `web-client/tests/e2e/uj3.spec.ts` drives the same three
gates in a real browser against a real stack. The `fake` scenario schema gained
`delete: [paths]`, which is what makes a quality-gate failure expressible at all.

**The defect the journey found, and the reason it exists.** FR-10's redispatch loop had
never closed. `apply_step_result::_redispatch` queues the *target* (`build`) and leaves the
gate that sent the walk back at `error`, deliberately (`test_apply_step_result.py` pins it);
`_advance` will not touch a successor that is not `planned`; so once the re-dispatched Story
finished, nothing ran the quality gate again. `close_run` read the leftover `error` row as a
stall and parked `internal` — a stop admitting no signal but `cancel`. Every Run whose gate
failed once was unrecoverable, and AD-9's own `verify failed {n}/{n}` park was unreachable.
Fixed in `walk.py::_sent_back`, the exact twin of `_resumed_in_place` (added for the same
symptom one row earlier), guarded on the Run still being `running` so an exhausted bound's
park keeps holding. `queue_row` reaches AD-8's own `("error", "retry") -> "queued"` pair, so
no transition was invented and the bound stays `redispatch_count` on the target. No existing
test asserted the broken behaviour: the two that come closest build their worlds with an
empty `with_resolved`, so neither carries a redispatch and neither changed.

**Files changed** (backend): `application/use_cases/walk.py` (`_sent_back`, wired into
`next_row` after `_resumed_in_place`; 391/400 lines),
`infrastructure/harness/fake/scenario.py` (`Scenario.delete`, `_deletes`, `_escapes`, the
documented key), `infrastructure/harness/fake/adapter.py` (`_remove`, applied before every
write; the docstring paragraph), `pyproject.toml` (the `uj3` marker). Four new test files:
`tests/unit/application/test_walk_runs_the_verify_again.py` (9),
`tests/unit/test_fake_harness_delete.py` (16), `tests/unit/test_gates_fixture_uj3.py` (6),
`tests/e2e/test_uj3.py` (18 across scenarios A–D), plus the new helper
`tests/e2e/helpers/uj3_reads.py`. No existing test file was edited.

**Files changed** (fixture): new `fixtures/gates-repo/check-spec.sh` and
`fixtures/gates-repo/specs/gates/GATE_OK` — a second quality gate whose file lives inside the
spec folder, so the Operator's repair can be a real `PUT /runs/{id}/files` (the root
`GATE_OK` is outside every Run's scope by construction and could never be); new
`.fake-harness/3/attempt-2.yaml` (reached only by a Run that dispatches story 3 twice, and
deliberately without `commit:`, so the post-skip commit guard has something to commit under
the rewritten message); `.fake-harness/3/default.yaml` gained the deletion; `README.md`
documents both. Every existing suite keeps `sh check.sh` and is untouched by the deletion.

**Files changed** (frontend): new `tests/e2e/uj3.spec.ts` and `tests/e2e/uj3-fixture.ts`.
No `src/` change, and no wire change — `make openapi` is drift-free.

**Decisions the brief left open.**

- **One Run for A, B and C.** SPEC CAP-8's success signal is a sequence, and the brief's own
  scenario D is "a **second** Run". Three separate Runs would have re-proven three gates the
  epic already has; one Run is the only shape that proves the journey. D starts only once the
  journey Run is terminal, so the module never holds more than one of `MAX_ACTIVE_RUNS`.
- **A second quality gate rather than moving `GATE_OK`.** See above; moving it would have
  edited `check.sh`, the fixture README and the frozen
  `test_gates_fixture.py::test_the_quality_gate_passes_on_an_untouched_clone`.
- **The done-checkpoint's row, not the `build` row, is what the skip marks.** `_skip_frame`
  never re-writes a `FINISHED` row, and story 3's `build` had already reached `done` — what
  carries `skipped · skipped by operator` is `stories[2].after`, which is enough for
  `summary.skipped` to name the Story (`run_views_summary.py::_operator_skipped`).
- **The compare link the brief's UX journey names does not exist for this fixture.**
  `pr_link.py` records no compare URL for a `file://` origin ("no compare link for this
  host"), the same conclusion 6-2's e2e reached; the skipped id is read off `wf-summary`
  instead, and `compare_urls == []` is asserted as the correct outcome rather than glossed.
- **The browser does not assert the literal `RUN` token after the Answer.** The scripted
  harness can reach story 2's checkpoint before the poll that follows the click lands. The
  browser asserts what is stable (the blocked stop gone, the token no longer `BLK`); the
  timing itself — `running` on the very next API read, inside five seconds — is measured in
  `test_uj3.py::test_a_the_answer_puts_the_run_back_to_running_within_one_poll`.
- **The gate-file repair in the browser journey is a `PUT`, not a click.** The ARTIFACTS
  panel edits a file the tree lists, and the file being repaired was deleted; the panel has
  no control that creates one (recorded in `deferred`).

**Review findings breakdown:** 3 patch (1 high, 2 low) — all applied and re-verified; 3
deferred (2 medium, 1 low, in frontmatter `deferred`); 5 rejected as noise (a symlinked
directory in `delete:`, `PurePosixPath` on a platform this system does not run on, the extra
`list_for_run` per idle walk turn, an unasserted empty `summary.skipped_epics`, and a
Board-card "back in Running" assertion that would have raced the next park).

**Follow-up review recommendation:** `true` — one patched finding was `high` severity.

**Gates — all run from a clean tree, foreground, real output, and re-run in full after the
patches**

| Gate | Result |
| --- | --- |
| `make lint` | pass — ruff, ruff format, mypy (domain/application strict), import-linter (4 contracts kept), env contract (35 fields / 41 variables agree), test pairs (194 backend / 91 web modules), `gen:api --check`, eslint, prettier, `tsc --noEmit`, astro check (0 errors) |
| `make test` | pass — 5505 backend passed, 1 skipped; `domain/` + `application/` **100 %** branch coverage; web-client 1225 passed in 94 files |
| `make openapi` | pass — no drift; `contracts/openapi.json` and `schema.d.ts` unchanged (this story adds no wire shape) |
| `make e2e` | pass — 206 passed, 11 deselected, 38 subtests, on the disposable `aio-e2e` stack with `ORCH_TEST_MODE=1`; the UJ-3 journey Run finished in 5.4 s and both gate records printed |
| `make e2e-ui` | pass — 158 passed, 1 skipped (`uj3.spec.ts`, which needs a real backend) |
| `make durability` | pass — 11 passed, 206 deselected |
| the journey, real backend | pass — `E2E_BACKEND=real` against a test-mode `aio-e2e` stack: `uj3.spec.ts` green in 14.0 s |

The two Epic-5 PNGs under `_bmad-output/implementation-artifacts/epic-5-screens/` are
regenerated by story 5.10's own anchor spec on every `make e2e-ui`; the new bytes are
committed.

**Residual risks.** Three deferred items, none blocking an acceptance criterion. The largest
is that `E2E_BACKEND=real make e2e-ui` is not a whole-suite gate: 43 specs read stub-backend
fixtures server-side and fail against a real stack. That predates this story and closing it
means editing ten anchor spec files, so the journey is run on its own —
`pnpm --dir web-client exec playwright test tests/e2e/uj3.spec.ts` with the real-backend
environment — and the command is written out under `## Verification`.
