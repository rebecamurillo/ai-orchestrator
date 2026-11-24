# Test Automation Summary — orchestrator-initiative-steps / epic-5-step-close

Generated: 2026-11-24. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-5-step-close/SPEC.md` (relative to the hub).
Stories: 1–3 (through commit `76a5cddb`).
Previous summary (epic-4-conversation-stop): in git history at `9005c1ae`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The new module follows
`test_conversation_stop.py` and reuses its helpers (`talking_origin`, `parked_on`, `signal`,
`turns_of`, `wait_for`). The epic changes no UI; its one contract change is `close_discarded` in
`MachineEvent`, so no Playwright test is added.

The stories' own tests are unit tests over fakes. The new module proves the same behaviour on the running
stack: real HTTP, Postgres, the DBOS walker and interactive queue, git, and the scripted `fake` harness.
No existing test file was touched and no shipped template is read. Every template is a fresh name the
module owns. Every repository is a fresh bare origin whose `.fake-harness/` scripts the turns. Every Run
is cancelled when its test ends.

The `fake` harness cannot write an attempt id it does not know. While the turn's process sleeps, the
test therefore writes the attestation `.orchestrator/session/close` into the Run's worktree itself
(`docker compose exec`, with a fallback to the host). The write happens after the turn's prompt file
exists, which is after the dispatcher's turn-start removal. A "nothing was sent" check uses a barrier:
one more message, whose turn must end. Session turns run one after another, so by then every earlier
turn's end, including its attestation check, has run.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_step_close.py` (11 tests)

- **CAP-1, the attestation (story 1):**
  - [x] Her own turn's id. The harness prompt holds `{first_turn}`, a blank line, then
    `Close product as {attempt id}.` The stored message is the first turn alone. After the turn ends,
    `step_close` is sent: one `step_close` record (`machine`, `step closed`) and no `close_discarded`.
    The row is `done`, the next row parks on a higher `park_seq`, and the file is gone.
  - [x] Another attempt's id. One `close_discarded` record reads `close discarded: attempt {id}`. No
    `step_close`, the row stays `checkpoint`, `park_seq` is unchanged, and the file is gone.
  - [x] Its own id while a later message is queued. One record reads `close deferred: later message`.
    Nothing is sent, and the next turn still runs.
  - [x] Its own id on a turn that exits 1. The turn is `error` and one record reads
    `close discarded: turn failed`. Nothing is sent.
  - [x] A step file reading `status: done` with no attestation. No `step_close` and no
    `close_discarded`; the row stays `checkpoint`.
  - [x] An attestation an earlier turn left behind (written after that turn ended) is removed when
    the next turn starts. Nothing is discarded or sent, and the file is gone.
- **CAP-3, the resumed execute routes the step file (story 3), via her `step_close`:**
  - [x] `status: draft`, `status: blocked` and a missing file (3 parametrised cases). The row parks
    `conversation` again with the exact EXPERIENCE § 5.3 sentence. The Run is `needs_you`,
    `senior_session` is true, the session is active, no new session turn is added, and the next row
    stays `planned`.
- **CAP-2 with CAP-3, the initiative folder (story 2):**
  - [x] Run inputs `initiative_folder: initiatives` and `slug: demo`, `writes: [docs/product.md,
    epics.yaml]`. A session that wrote `initiatives/demo/epics.yaml` and a done step file ends the row
    `done` on `step_close`, with no `protected_path` record, and the next row parks.
  - [x] The same session also writes `backend-api/AGENTS.md`. The row parks `protected_path` with
    `hits == [backend-api/AGENTS.md]`. The reason names that path and not the folder anchor. The row
    is `error`. `continue` with `files: [backend-api/AGENTS.md]` lets the close proceed: the row is
    `done` and the next row parks.

Not covered end to end (unit tests only):
- A `git.commit` row after a conversation row committing an in-folder anchor, or parking on an
  `AGENTS.md`. The session's own commit has already committed the tree, so that row finds nothing
  staged.
- The `auto`-Run and merge-shaped (`lane: walk`) anchor results.
- The member `AGENTS.md` R1 line.
- `after_turn` on a Run parked on another stop kind.
- The `step close not wired` and `step close refused` log lines.

## Results

Run against the disposable `aio-e2e` stack (`docker compose -p aio-e2e`, `.env.e2e`), which was
destroyed afterwards. Only the new module and the epic-4 module were run, not the full `make e2e`:

- `test_step_close.py`: **11 passed**, on 3 of 3 runs (about 2 min each).
- `test_conversation_stop.py` (epic 4, unchanged): **9 passed, 1 failed**. The failure is the known
  defect from the epic-4 summary,
  `test_a_forced_skip_mid_turn_closes_the_queued_turns_and_the_walk_waits_for_the_killed_one`
  (`ux[0].started_at` 3 ms before the killed turn's `ended_at`). The `open_turns` cause recorded at
  `9005c1ae` is still unfixed. Epic 5 did not introduce it.

### Environment notes (not test changes)

- The host `backend-api/.venv` was moved aside again during the image build and restored right
  after. `.dockerignore` still excludes only a root-level `.venv`.

## Coverage

- SPEC capabilities with an e2e test: CAP-1, CAP-2, CAP-3 (3 of 3).
- Endpoints the epic's behaviour runs through: `POST /runs/{id}/signals` (`step_close`, `continue`
  with `files`), `POST /runs/{id}/session/messages`, `GET /runs/{id}/session`,
  `GET /runs/{id}/detail` (gate records `step_close` and `close_discarded`, alert reason and hits).
- UI features: none in scope.

## Next Steps

- Run the full `make e2e` in CI.
- Fix `open_turns` (epic-4 summary), then rerun the epic-4 module.
- Exclude `**/.venv` in `.dockerignore`.
