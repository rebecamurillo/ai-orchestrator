# Test Automation Summary — orchestrator-initiative-steps / epic-7-initiative-record

Generated: 2026-11-25. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-7-initiative-record/SPEC.md` (relative to the hub).
Stories: 1–6 (through commit `8f89a177`).
Previous summary (epic-6-package): in git history at `69f3dfed`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The epic changes no UI
(web pages are epics 10 and 11; its only web change is the regenerated `schema.d.ts`), so no
Playwright test is added.

The stories' own tests are unit tests over the shared fakes. The new module covers the same
operations on the running stack: real HTTP, Postgres and its partial unique indexes, the real git
adapter pushing and deleting `spec/{slug}` on a bare origin, and the real engine walking the spec
Run to a `conversation` stop on the scripted `fake` harness. No existing test file was touched, and
no shipped template or hub `package/` is read. Every package (`e2e-init-<hex>`), slug and origin is
fresh. Origins are written through the container first (as `talking_origin` does). Every initiative
a test creates is cancelled when the test ends.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_initiatives.py` (14 tests)

- **Create (CAP-3, CAP-5):**
  - [x] `POST /initiatives` answers 201 with the detail.
    - `spec/{slug}` exists on the origin at `main`'s sha.
    - `round` is 1. `project`, `hub`, `folder` (`initiatives/{slug}`) and `package` are set, and the
      status is `running`.
    - There is one shown workflow (the merge entry is `shown_as: step`). Its steps are
      `intake, product, gate, merge` at the frozen `{package}.spec` v1.
    - The spec Run has keys `(round 1, position 0)` and the inputs `slug`, `branch`, `first_turn`
      and the bound `initiative_folder`.
  - [x] A held slug is refused 409 naming `{holder name} ({holder id})`. After a cancel (no cleanup
    error), the same name creates a new initiative.
  - [x] A `spec/{slug}` already on the origin is refused 409 with the exact text. The branch is left
    untouched and no initiative is stored.
  - [x] Other refusals:
    - an unknown project is 404;
    - a project with no package is 409 `no package installed on project …`;
    - a blank name is 422;
    - an unknown body key is 422.

    Nothing is stored.
- **Reads over a walked Run (CAP-2, CAP-4, CAP-6):**
  - [x] At its first conversation stop the spec Run reads `running` with attention `your_turn`.
    - `step` and `current_step` are `intake`. `park_seq` is the Run's, and `repo_tag` is the hub's
      slug.
    - The `intake` step is `running`, `park_kind` `conversation`, and holds one operator turn, done,
      with the first message. `product` is `planned`. `owners` is `[]`, and `sessions` starts with
      the Run.
    - `GET /runs/{id}/detail` carries the `initiative` tag (`position` 1, `workflow_count` 1) and
      `template_type` `interactive`.
    - On the board, the Run is in `running`, not in Needs-you, and its card carries `attention`,
      `template_type` and the tag.
  - [x] The lists:
    - `?project_id=` narrows to the project;
    - `ongoing` keeps the open initiative;
    - `needs_you` is empty for a `your_turn` initiative;
    - `all` adds the cancelled one;
    - `GET /projects/{id}/initiatives` equals the narrowed list;
    - `columns`, `counts.cancelled` and the row's `workflows` foot are correct, and `next_cursor` is
      null.
  - [x] Unknown initiative or project: 404. A bad `filter` or a malformed id: 422.
  - [x] `?opened=true` sets `last_opened_at`. A plain read writes nothing, and a second open does
    not move it backwards.
- **start-next (CAP-5):**
  - [x] A stale `park_seq` is 409, and the stop is unchanged.
  - [x] With the current one it answers 200. The real walk skips `intake` (detail token `SKP`) and
    parks on `product`.
  - [x] From `product` (next is the gate) it is 409 with the exact "never forced" text.
  - [x] An unknown body key or a missing `park_seq` is 422. An unknown initiative is 404. A
    cancelled one is 409 `no conversation step is open`.
- **Cancel (CAP-3, CAP-5):**
  - [x] Cancelling a parked initiative answers 200 `cancelled` with no cleanup error. The spec Run
    reads `cancelled`, and `spec/{slug}` is gone from the origin.
  - [x] A second cancel is 409 `already cancelled`. An unknown initiative is 404.
- **Package delete (CAP-1):**
  - [x] `DELETE …/package` is 409 `refused: 1 open initiatives use this package — {slug}` while the
    initiative is open, and the record stays. After the cancel, the delete answers 204.
- **Surface (B10):**
  - [x] All six initiative operations need the bearer (401).
  - [x] `tools/list` has no initiative tool. `set_initiative_folder`, which comes from epic 6, is
    the only tool with "initiative" in its name.

Not covered end to end (unit tests only):
- `waiting for her` from a real `blocked` attention (failed turn, `step not closed`, a blocked step
  word), and the unmapped-word `failed`.
- Turns across rounds, `owners` from `round_steps`, files per step and their `changed` mark (no
  reopen or gate-fail round exists before epics 8 and 9).
- A merge `merge_conflict` stop and `conflict_files`. The build workflow line with a PR link.
- A cancel whose branch delete fails (`branch_cleanup_error`) and its retry.
- Rollback of a create when `create_run` refuses after the branch was pushed.
- The migration's downgrade.

## Results

**Not run against a stack in this session.** The Docker daemon is unreachable from this machine
(`Cannot connect to the Docker daemon at tcp://127.0.0.1:2375`), so `make e2e` could not build the
disposable `aio-e2e` stack. No running instance was touched (hard rule 9).

What was verified:
- `pytest tests/e2e/test_initiatives.py --collect-only`: 14 tests collected.
- `ruff check` and `ruff format --check` on the new file: clean.
- `make lint` (whole repository): exit 0.

### Defect still open from epic 6: `0046` revision id overflows `alembic_version`

`backend-api/alembic/versions/0046_repository_initiative_folder.py` still declares a 33-character
revision id. `alembic_version.version_num` is `varchar(32)`, so start-up fails at the migrate step on
Postgres. Unless it is shortened (in `0046`, and in `0047`'s `down_revision`), `make e2e` cannot boot
and this module cannot run. Epic 7's own `0048_initiative` is 15 characters.

## Coverage

- SPEC capabilities with an e2e test: CAP-1 (package delete refusal, slug index), CAP-2 (status and
  attention read through the API), CAP-3, CAP-4, CAP-5, CAP-6 (header fields, step park fields,
  turns, sessions, `?opened=true`). Each has at least one test; CAP-6 only in part (see above).
- Endpoints, all 6 new operations:
  - `GET /initiatives`, `GET /projects/{id}/initiatives`, `GET /initiatives/{id}`;
  - `POST /initiatives`, `POST /initiatives/{id}/cancel`, `POST /initiatives/{id}/start-next`.

  Also exercised through the changed behaviour: `GET /runs?view=board`, `GET /runs/{id}/detail`,
  `DELETE /projects/{id}/package` and `POST /mcp`.
- UI features: none in scope.

## Next Steps

- Shorten the `0046` revision id, then run `make e2e` with this module on a machine that has Docker.
- Extend the module when epic 8 lands the advance (gate-fail rounds, merge and build Runs), so that
  turns across rounds, `owners`, files and the merge/build lines get covered end to end.
