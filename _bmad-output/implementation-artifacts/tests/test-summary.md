# Test Automation Summary — orchestrator-initiative-steps / epic-9-initiative-reopen

Generated: 2026-11-26. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-9-initiative-reopen/SPEC.md` (relative to the hub).
Stories: 1–4 (through commit `07420f7c`).
Previous summary (epic-8-initiative-advance): in git history at `310278de`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The epic is backend
and guide only (the web-client change is the regenerated `schema.d.ts`), so no Playwright test is
added.

The stories' own tests are unit tests over the shared fakes, a `MockTransport` for the GitHub
adapter, and structure tests for the guide. The new module drives the two new REST operations on
the running stack:
- the real `signal_run` cancels a real parked spec Run;
- the real git adapter re-pushes a deleted `spec/{slug}` to a bare origin;
- the real engine walks the next round to the reopened step, skipping rows outside `round_steps`.

No existing test file was touched. No shipped template or hub `package/` is read (hard rule 6):
the hub, package and origin are `test_initiatives.Hub`'s fixture, fresh per test.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_initiative_reopen.py` (10 tests)

- **Reopen a parked step (CAP-2):**
  - [x] The spec Run is parked on `intake`, then `reopen(intake, reason)`. Checked:
    - the answer is 201 `{run_id, round: 2}`;
    - the old Run is `cancelled`, with a `cancel` gate record;
    - `spec/{slug}` keeps its sha (attached);
    - the new Run is at the frozen version, with `round_steps` `intake,product`, `first_turn` = the
      reason and `branch` `spec/{slug}`;
    - it walks to `intake` at `(2, 0)` and is the initiative's only live Run;
    - the intake turns hold both the round-1 first message and the reason;
    - `reopened_after` is null.
  - [x] `reopen(product, …)` gives `round_steps` `product`, and the walk skips `intake` and parks on
    `product`.
  - [x] With `spec/{slug}` deleted on the origin, the reopen re-creates it at `main`'s tip before the
    new Run walks.
  - [x] Two reopens in a row give rounds 2 then 3. Round 2's Run is cancelled, and exactly one Run
    is live.
- **The refusals write nothing (CAP-2):**
  - [x] `gate`, `merge` and `deploy` each get 422 problem+json naming the step. A blank reason, an
    unknown key and a missing reason also get 422. Afterwards the round is still 1, and the one Run
    is still `needs_you`.
  - [x] An unknown id gets 404. A cancelled initiative gets 409 naming its slug and `cancelled`,
    and no Run is added.
- **The upgrade preparation (CAP-3):**
  - [x] With no hold, the answer is 409 `no instance hold…` and the parked Run stays `needs_you`.
  - [x] Under a hold, the parked conversation is listed as `{run_id, initiative_id, step: intake}`.
    It is `cancelled` with a `cancel` gate record, and the initiative stays open at round 1.
    - The operation is instance-wide, so a live non-conversation interactive Run left by another
      module answers 409 instead. That branch is checked too: the refusal does not name this Run,
      and this Run still waits. The hold is released in `finally`.
- **The surface (CAP-5, B10):**
  - [x] Both operations answer 401 without the bearer.
  - [x] No MCP tool name contains `reopen` or `upgrade`.

Not covered end to end (unit tests only, by design):
- the `initiative_pr_check` job: it would call GitHub, which CAP-5 and hard rule 5 forbid;
- the start-up `reopen_after_upgrade` pass: it needs a backend restart (hard rule 9; `make
  durability` territory);
- `reopened_after` and the build's `BLK · stopped on the spec · {step} reopens` line: they need a
  done gate, a merge and a parked build (epic 8's long fixture); unit tested in
  `test_initiative_detail_reopen.py`;
- `consumed_at` on a blocked advance during a reopen;
- the done-initiative 409;
- the guide pages (`check_guide.py` and the unit structure tests).

## Results

**Not run against a stack in this session.** The Docker daemon is unreachable from this machine
(`docker info` fails), so `make e2e` could not build the disposable `aio-e2e` stack. No running
instance was touched (hard rule 9; SPEC constraint "never start, stop, upgrade or call a running
instance").

What was verified:
- `pytest tests/e2e/test_initiative_reopen.py --collect-only`: 10 tests collected.
- `ruff check` and `ruff format` on the new file: clean.
- `scripts/check_test_pairs.py`: passes. mypy in `make lint` covers only `domain/` and
  `application/`, as for every e2e module.

The assumptions that only a run can confirm:
- the cancel through `signal_run` is synchronous, so the new Run is created on the first call and
  not refused with `Run … is still live`;
- a parked conversation with no turn running is not a working step, so the hold can be placed.

If either is wrong, the failing assertion names it.

### Defect still open from epic 6: `0046` revision id overflows `alembic_version`

`backend-api/alembic/versions/0046_repository_initiative_folder.py` still declares the 33-character
revision `0046_repository_initiative_folder`, and `alembic_version.version_num` is `varchar(32)`.
The migrate step at start-up fails on Postgres, so `make e2e` cannot boot until the id is shortened
(in `0046`, and in `0047`'s `down_revision`).

## Coverage

- SPEC capabilities with an e2e test:
  - CAP-2: reopen, its round, branch attach and re-create, refusals;
  - CAP-3: `upgrade-prepare` with no hold and under a hold;
  - CAP-5: the cancels go through `signal_run`, the Run through `create_run`, and there is no MCP
    tool.
- CAP-1 and CAP-4 are unit- and lint-tested only (GitHub; guide prose).
- Story 2 acceptance criteria with an e2e test: 6 of 10 (the parked reopen, `round_steps`
  narrowing, a deleted branch, two reopens, the 422s, the 409 on a cancelled initiative).
- Story 3 acceptance criteria with an e2e test: 2 of 8 (no hold, and a cancel under a hold).
- Endpoints exercised:
  - `POST /initiatives/{id}/reopen`, `POST /instance/upgrade-prepare`;
  - `POST`/`DELETE /instance/hold`, `GET /instance/activity`;
  - `GET /initiatives/{id}`, `GET /runs/{id}/detail`, MCP `tools/list`.
- UI features: none in scope.

## Next Steps

- Shorten the `0046` revision id, then run `make e2e` on a machine with Docker. That runs this
  module and epics 7–8's `test_initiatives.py` and `test_initiative_advance.py`, none of which has
  run yet.
- Once epic 11 story 6 lands the "reopen step …" action, add a Playwright test for it.
