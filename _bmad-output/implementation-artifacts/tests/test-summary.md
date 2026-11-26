# Test Automation Summary — orchestrator-initiative-steps / epic-8-initiative-advance

Generated: 2026-11-26. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-8-initiative-advance/SPEC.md` (relative to the hub).
Stories: 1–4 (through commit `e2a7367e`).
Previous summary (epic-7-initiative-record): in git history at `ef593633`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The epic is backend
only and changes no UI, so no Playwright test is added.

The stories' own tests are unit tests over the shared fakes. The new module drives real initiatives
on the running stack:
- the real engine walks the spec Run to `done`;
- the real `advance_initiative` workflow runs after the commit;
- Postgres stores the gate's verdict;
- the real git adapter merges, pushes `main`, deletes `spec/{slug}` and creates `feat/{slug}` on a
  bare origin.

No existing test file was touched, and no shipped template or hub `package/` is read (hard rule 6).
Every package, slug and origin is fresh. The fake harness is scripted per dispatch:
- `.fake-harness/default.yaml` for the spec turns and the gate;
- `.fake-harness/merge/` for the merge agent;
- `.fake-harness/resolve/` for the merge-session turn (its message carries the sentence the fake
  harness keys a scenario by).

## Generated Tests

### API tests — `backend-api/tests/e2e/test_initiative_advance.py` (7 tests)

- **A failing gate (CAP-1, CAP-2, CAP-3):**
  - [x] Gate `status: fail`, `owners: [intake]`. Checked:
    - the spec Run ends `done`;
    - the gate attempt stores `verdict_word` `fail`, `verdict_fields.owners` and the body as
      `verdict_text`, without the frontmatter;
    - the advance creates the round-2 spec Run at `(2, 0)` with `round_steps` `intake`,
      `first_turn` = the body and `branch` `spec/{slug}`;
    - the initiative's `round` is 2 and no merge Run exists;
    - the round-2 intake turn reads `author` `gate`, `defects` 2, `owner` `intake`.
- **A pass whose build pre-flight fails (CAP-3):**
  - [x] Gate `pass`, and the build loops over a missing `{initiative_folder}/epics.yaml`. The result
    is round 2 for the tech step, with `first_turn` naming `epics.yaml`, and no merge Run.
- **A pass, then merge, then build (CAP-3, CAP-5):**
  - [x] The merge Run at `(1, 1)`:
    - `interactive`, `branch` `main`, with the bound `initiative_folder` `initiatives`;
    - the spec Run's budget;
    - ends `done`.
  - [x] On the origin, after the merge:
    - `main` holds the spec branch's work;
    - `spec/{slug}` is deleted;
    - `feat/{slug}` sits at `main`'s tip.
  - [x] The build Run at `(1, 2)`:
    - carries budget $5.00, `branch` `feat/{slug}` and `initiative_folder` `initiatives/{slug}`;
    - receives no null-default `plan_model`/`review_model`;
    - ends `done`, and no fourth Run is created.
- **No project budget (CAP-3):**
  - [x] With `default_budget_usd` null, the merge ends `done`. The initiative then reads
    `waiting for her` · `no project budget`, with no build and no `feat/{slug}`.
  - [x] `PUT …/run-defaults` with $5.00 retries the advance: the build is created and
    `feat/{slug}` appears at `main`'s tip.
- **A merge conflict (CAP-4):**
  - [x] `main` and `spec/{slug}` both change `CONFLICT.md`. The merge Run parks `merge_conflict`
    with `merge conflict: spec/{slug} into main`, and:
    - a `scope: step` session is open;
    - `continue`, `retry` and `cancel` are admitted;
    - the Run is held on the `walk` lane in `GET /queue`;
    - the initiative's merge step lists `CONFLICT.md` in `conflict_files`.
  - [x] A message dispatches a turn whose prompt opens with the merge agent's skill
    (`staged-review`, not `senior-session`).
  - [x] The turn concludes the merge. The machine then sends `continue` ("merge resumed after the
    agent's turn"), and the row ends `done · already merged`. The resolved file reaches `main`,
    `spec/{slug}` is deleted, and the build is created.
- **A conflict outside an initiative (CAP-4):**
  - [x] A plain Run's `merge_conflict` opens no session, does not admit `continue`, and refuses a
    `continue` with 409. `retry` and `cancel` stay admitted.
- **The `git.push` keys (CAP-3):**
  - [x] `POST /templates/{name}/validate`:
    - admits `allow_default_branch` and `retry {max, sync_first}` in an `interactive` template;
    - refuses `allow_default_branch` in an `auto` template (`git.push allow_default_branch needs
      type: interactive`);
    - refuses `retry` on `git.commit` (`unknown key`).

Not covered end to end (unit tests only):
- the start-up sweep re-enqueuing an unconsumed advance after a crash (`make durability` territory);
- a cancelled initiative's or a superseded round's advance being consumed with nothing created;
- `advance failed: …` on a raising read;
- `gate owner … is not a step of …`, `gate failed with no owner` and an undeclared gate word;
- `feat/{slug}` already on the origin (fast-forward, or `exists and is not from main`);
- a non-spec-file pre-flight block (`preflight: harness: …`);
- the `git.push` retry path (rejected push, then sync, then push) and `sync before retry failed`;
- `continue` while the worktree is still conflicted, and `default_autonomy` / `default_senior_model`
  forwarding;
- hard rule 7's text in `AGENTS.md` (`tests/unit/test_agents_hard_rule_7.py`).

## Results

**Not run against a stack in this session.** The Docker daemon is unreachable from this machine
(`Cannot connect to the Docker daemon at tcp://127.0.0.1:2375`), so `make e2e` could not build the
disposable `aio-e2e` stack. No running instance was touched (hard rule 9).

What was verified:
- `pytest tests/e2e/test_initiative_advance.py --collect-only`: 7 tests collected.
- `ruff check` and `ruff format --check` on the new file: clean.
- `make lint` (whole repository): exit 0.

The fixture's assumptions that only a run can confirm:
- the fake harness's `commit: true` concludes the in-progress merge in the merge worktree;
- `staged-review` and `spec-gate` are in the e2e image's skills manifest (the installed-skill
  pre-flight line);
- a bare `run: "true"` row is accepted in a `for_each` body.

If one of them is wrong, the failing assertion names it.

### Defect still open from epic 6: `0046` revision id overflows `alembic_version`

`backend-api/alembic/versions/0046_repository_initiative_folder.py` still declares a 33-character
revision id, and `alembic_version.version_num` is `varchar(32)`. Start-up therefore fails at the
migrate step on Postgres, and `make e2e` cannot boot until the id is shortened (in `0046`, and in
`0047`'s `down_revision`). Epic 8's own `0049_attempt_verdict` is 20 characters.

## Coverage

- SPEC capabilities with an e2e test:
  - CAP-1: the advance after a real terminal transition, consumed once per `(round, position)`;
  - CAP-2: the verdict stored on the gate row;
  - CAP-3: fail round, pre-flight fail, merge, build, budget block and retry, the push keys;
  - CAP-4: conflict session, skill, machine `continue`, non-initiative refusal;
  - CAP-5: every Run created `queued` through `create_run` and walked by the engine.
- Transitions of story 3's acceptance list with an e2e test: 7 of 15. The other 8 are listed above.
- Endpoints exercised through the changed behaviour:
  - `POST /initiatives`, `GET /initiatives/{id}`, `PUT /projects/{id}/run-defaults`;
  - `POST /runs/{id}/signals` (`step_close`, `continue`), `GET /runs/{id}/session`,
    `POST /runs/{id}/session/messages`;
  - `GET /runs/{id}/detail`, `GET /queue`, `POST /templates/{name}/validate`.
- UI features: none in scope.

## Next Steps

- Shorten the `0046` revision id, then run `make e2e` on a machine with Docker. That runs this module
  and epic 7's `test_initiatives.py`, neither of which has run yet.
- Once epic 9 lands `reopen_initiative` and `initiative_pr_check`, extend this module with reopen
  rounds and the PR-merged end state.
