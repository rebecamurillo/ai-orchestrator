# Test Automation Summary — orchestrator-initiative-steps / epic-3-interactive-lane

Generated: 2026-11-23. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-3-interactive-lane/SPEC.md` (relative to the hub).
Stories: 1–4 (commits `d828c9a5`..`d3f67fab`).
Previous summary (epic-2-run-page-review): in git history at `7ab6f6a3`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The module follows the
patterns of `test_queue.py` and `test_run_creation.py`. This epic only regenerates `schema.d.ts` in the
web-client, so no Playwright test is added.

The stories' own tests are unit tests over fakes. The new module proves the same behaviour on the running
stack: real HTTP, Postgres, DBOS queues, git and a bare remote. No existing test file was touched, and no
shipped template is read. Every template is a fresh name the module owns, and every Run it starts is
cancelled when its test ends.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_interactive_templates.py` (16 tests)

- **CAP-1, the template type (story 1):**
  - A stored version with `type: interactive`, `type: auto` or no `type` reads that type back from the
    `201` save body and from `GET /templates/{name}/1` (`interactive` / `auto` / `auto`).
  - `type: manual` and `type: [auto]`:
    - `POST /versions` answers `422` with `line 4:`.
    - `POST /validate` answers `200` with exactly one error: line 4, code `template-invalid-value`.
- **CAP-2, the lane (story 2):**
  - Every `GET /queue` row has `lane` ∈ {`walk`, `interactive`}.
  - Positions are numbered 1..n within each lane.
  - A Run from an `interactive` template with no `conversation` row is parked at a checkpoint. It is listed
    in `GET /queue` with `lane: walk`, which is the gate item 5 rule.
- **CAP-3, frozen versions (story 3):** the template `e2e-frozen-*` is stored at versions 1 and 2. Version
  1 has a `link` row and version 2 does not.
  - A Run at version 1 reads `version: 1` and plans `touch` and `link`.
  - A Run at version 2 plans `touch` only.
  - Version 9:
    - `POST /runs` answers `422` with `errors[0].template` set to the name and `errors[0].version` set to
      `"9"`, and the Project lists no Run at that version.
    - `POST /runs/preflight` returns a `plan_error` naming the same template and version `9`.
- **CAP-4, `git.branch_delete` (story 4):**
  - `POST /validate` accepts a `git.branch_delete` step with `{branch}` and refuses an unknown `with` key
    (`force`).
  - The template graph has exactly one `git.branch_delete` node, `delete`. It is `deterministic` and not
    an agent node.
  - The real engine walks a Run on a fresh bare remote that holds `spec/demo`:
    - The Run ends `done`, and the row reason is `deleted origin/spec/demo`.
    - The remote no longer holds the branch.
    - The attempt's log has the line `git push origin --delete spec/demo` and the answer `deleted`.
  - A branch the remote never held: the Run ends `done · already gone`, and the log has the operation line
    and `already gone`.
  - `branch: main`, the default branch: the Run parks `needs_you` with `misconfigured` and the reason
    `refuses to delete the default branch main`. `main` is still on the remote.

## Coverage

- Capabilities of this epic: 4 of 4 are exercised on the running stack.
- Covered by unit tests only:
  - The `interactive` lane being chosen. No `conversation` kind exists until epic 4 story 3, so no real
    template can produce an interactive Run yet.
  - `MAX_ACTIVE_RUNS=1` with a parked walk Run.
  - The three registered queue widths.
  - The migration default `walk`.
  - A `GitError` → `push_rejected`.
  - An adapter without `RemoteBranches`.

## Verification

- `ruff check` and `ruff format --check` pass on the new module. The `mypy` gate covers only
  `src/orchestrator/{domain,application}`.
- The run used the gate's own disposable stack, project `aio-e2e`:
  - It was brought up with the `make e2e` compose command, `.env.e2e` and database `orchestrator_e2e`.
    `check_e2e_target.sh` passed.
  - It was destroyed with `down -v` afterwards. No other stack or container was touched.
- `pytest tests/e2e/test_interactive_templates.py`: **16 passed**, twice in a row against the same stack
  (the suite must be re-runnable).
- `test_queue.py`, `test_templates.py`, `test_run_creation.py` and `test_template_graph.py` against the
  same stack: 28 passed.

## Findings (not fixed: tests only)

1. **Story 1's refusal does not name the key or the value.** The story asked for "the validator's
   existing invalid-value error, naming the key `type`, the value and the line".
   - The wire carries `line: 4`, `reason: "invalid value"` and `code: template-invalid-value`. The words
     `type` and `manual` appear only through the line number.
   - The unit test `test_template_type.py` pins the same thing.
   - The new e2e test pins what ships (line and code). Whether the reason should name `type`/`manual` is
     for the Operator to decide.
2. **`.dockerignore` excludes only the root `.venv`.**
   - In a checkout where `backend-api/.venv` exists, that venv is copied into the backend image.
   - Its entry-point shebangs point at host paths, so the container exits 127 at
     `/app/backend-api/.venv/bin/alembic`, and `make e2e` cannot start.
   - Workaround used for this run: move `backend-api/.venv` aside during the build, then put it back.
   - Suggested fix (not applied): add `**/.venv` to `.dockerignore`.
3. **The `Fixtures` host route in `test_clone_check.py`.**
   - On a host where `WORK_DIR` (`/work`) exists and is writable but is not the container's `work`
     volume, `Fixtures` creates the bare repositories on the host. The containerised backend then cannot
     clone them.
   - For this run, a failing `git` shim on `PATH` forced the `docker compose exec` route.
   - On CI, the backend runs from source, so the two paths are the same and this does not arise.

## Next Steps

- The lead runs `make e2e` in the disposable `aio-e2e` stack before the pull request (after finding 2 is
  addressed or worked around).
- Epic 4 story 3 adds an e2e case where a real `conversation` row puts a Run on `lane: interactive`.
