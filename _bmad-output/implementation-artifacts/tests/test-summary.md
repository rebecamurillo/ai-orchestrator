# Test Automation Summary — orchestrator-initiative-steps / epic-4-conversation-stop

Generated: 2026-11-23. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-4-conversation-stop/SPEC.md` (relative to the hub).
Stories: 1–6 (through commit `9bb0f055`).
Previous summary (epic-3-interactive-lane): in git history at `2fc80729`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The module follows
`test_interactive_templates.py` and `test_skip_step.py`. The web-client change in this epic is the
regenerated `schema.d.ts` and one scope label, so no Playwright test is added.

The stories' own tests are unit tests over fakes. The new module proves the same behaviour on the running
stack: real HTTP, Postgres, the DBOS walker and interactive queue, git, and the scripted `fake` harness.
No existing test file was touched and no shipped template is read. Every template is a fresh name the
module owns. Every repository is a fresh bare origin whose `.fake-harness/attempt-1.yaml` and
`default.yaml` script the turns (a conversation prompt names no story). Every Run is cancelled when its
test ends.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_conversation_stop.py` (10 tests)

- **CAP-3, the kind (story 3):**
  - [x] A `conversation` row validates in an `interactive` template. It is refused with no `type` (auto)
    and when `prompts.close` is missing.
  - [x] `GET /templates/{name}/1/graph` draws one `conversation` node per row.
  - [x] With `round_steps: ux`, the `product` row ends `skipped · not in this round`. `ux` parks and its
    first turn is the Run's `first_turn`.
- **CAP-1 and CAP-4, the stop and its session (stories 1 and 4):**
  - [x] The row parks `checkpoint`, with the Run at `needs_you` and park kind `conversation`.
    `senior_session` is true and the session reads `scope: step` and `scopes: [step]`. There is one
    `session_start` record and one session turn, carrying `first_turn`.
  - [x] Each of these answers `409` and the row stays `checkpoint`: a plain `skip_step`; a forced
    `skip_step` without its stop; `skip_story`; `continue`; `step_close` without a stop; `step_close`
    for a stale stop.
  - [x] `step_close` with the current stop answers `200`. The row parks again on a higher `park_seq`
    with no second first turn. The gate record holds one `step_close` (`machine`, `step closed`), and the
    old stop is then refused `409`.
- **CAP-5, messages, forced skip and cancel mid-turn (story 5):**
  - [ ] **Fails: product defect, see below.** Two messages posted during a running turn each answer
    `202 queued`. A forced skip with the stop answers `200` and the row reads `skipped, forced`. The
    killed turn ends. The two queued turns close `error · step skipped` with their text kept. `ux` opens
    with `Open ux.`, and that turn must start after the killed turn's `ended_at`.
  - [x] Cancel during a running turn, with one queued message: the Run ends `cancelled`, and the queued
    turn closes `error · Run cancelled` with its text kept.
- **CAP-6, restart (story 6):**
  - [x] After a failed first turn, `POST /session/retry` answers `201` with the failed turn's message. A
    second retry while that turn runs answers `409`. The restarted turn ends `done`, after which retry
    answers `409`. The restarted attempt carries the failed turn's harness `session_id`.
  - [x] Retry answers `409` once the Run is cancelled and no session is open.

Not covered end to end (unit tests only): `spec-gate` skip refusal on an interactive Run (parking an
agent `spec-gate` row needs a blocked agent scenario); the announcer and chat poster sending nothing;
the unlisted-bare-skill turn failure (the `fake` harness has no skill catalog); the CAP-2 walker
discard on the DBOS fake.

## Results

Run against the disposable `aio-e2e` stack (`docker compose -p aio-e2e`, `.env.e2e`), which was
destroyed afterwards: **9 passed, 1 failed.** The failure reproduced on 4 of 4 runs.

### Defect found (CAP-5, AD-23 amended "Signals"; gate item 4)

`test_a_forced_skip_mid_turn_closes_the_queued_turns_and_the_walk_waits_for_the_killed_one` fails at
`ux[0].started_at >= killed.ended_at`. The next row's turn is stamped 3–4 ms before the killed turn's
`ended_at`.

**Cause.** `application/use_cases/walk.py::open_turns` counts only attempts with `status == "running"`
and `ended_at is None`. `session_dispatch._run` commits the killed turn's final `status` (`error`) with
`ended_at` still `None`. `session_turn` sets `ended_at` later, in a separate commit (line 232). In that
gap `open_turns` returns 0, and the walk executes the next row before the attempt has ended. The SPEC
says the walk waits "until that attempt has `ended_at`". The likely fix is to drop the `status ==
"running"` condition, so that any session attempt with `ended_at is None` counts as open. That is a code
change for a story, so it was not made here.

### Environment notes (not test changes)

- `.dockerignore` excludes only a root-level `.venv`. A host `backend-api/.venv` is copied into the
  image and overwrites the image's own venv, and the container then exits with code 127 at
  `alembic`. The stack was built with the host venv moved aside temporarily.
- On a host where `WORK_DIR` (`/work`) exists and is writable, the shared `Fixtures` helper writes
  fixture repositories on the host, where the containerised backend cannot see them. The new module
  therefore tries `docker compose exec` first and falls back to the host.
- A signal that kills a running turn answers after the process runner's 10 s SIGTERM grace, so the
  module gives signals a 60 s client timeout.

## Coverage

- SPEC capabilities with an e2e test: CAP-1, CAP-3, CAP-4, CAP-5, CAP-6 (5 of 6). CAP-2 is walker-internal
  and covered by unit tests on the DBOS fake.
- Endpoints touched by the epic: 5 of 5 (`POST /templates/{name}/validate`, `POST /runs/{id}/signals`
  with `step_close` and forced `skip_step`, `GET /runs/{id}/session`, `POST /runs/{id}/session/messages`,
  `POST /runs/{id}/session/retry`).
- UI features: none in scope.

## Next Steps

- Fix `open_turns` (above), then rerun `make e2e`. The failing test is the regression check.
- Exclude `**/.venv` in `.dockerignore` so `make e2e` works on a machine with a host venv.
