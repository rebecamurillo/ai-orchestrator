# Test Automation Summary — orchestrator-deploy-folder / epic-2-setup-runner

Generated: 2026-11-11 (dispatch, empty story id, covering the whole epic)
Spec: `initiatives/orchestrator-deploy-folder/epic-2-setup-runner/SPEC.md` (hub-relative)
Stories: 1–5 (committed `042e704`..`97cbb3d`; story 5 is the `wip … (consult)` commit)

---

## Generated Tests

### Backend API E2E Tests

- None added. The epic changes no route, schema or contract: `git diff e5de22a HEAD -- backend-api/src web-client/src contracts` touches only `application/steps/bmad_install.py`, `application/steps/context.py` and `infrastructure/db/environment.py`, which together select `/opt/bmad/bin/bmad-method` over `npx`. Nothing new is reachable over HTTP.
- `bmad.install` is already driven end to end by `tests/e2e/test_repo_init.py` and `test_repo_init_commit_scope.py`. A scenario asserting *which* installer ran cannot hold across both e2e topologies. In `make e2e` the backend runs from the image, which has `/opt/bmad`. In `ci.yml`'s e2e-api job it runs on the runner, which has no `/opt/bmad` and falls back to `npx`. `tests/unit/test_bmad_install_prefix.py` and `test_run_environment_bmad_bin.py` cover both branches.
- What the image carries (`/opt/bmad`, no BMAD stub in a harness home, the `setup` service) is a deployment check. Under member AD-31 it belongs to `deploy-tests/stack/`, which is epic 4's work and a non-goal here. No such check was added to `tests/e2e`, because that would put a deployment test in a development gate.

### UI E2E Tests

- None. The SPEC's non-goals exclude any web-client change.

### Deployment tests (written by the stories, not run here)

- `deploy-tests/unit/`: `test_guard.py` (10), `test_bmad_collision.py` (1), `test_setup_runner.py` (10), `test_bmad_script.py` (6), `test_release_files.py` (13), plus the three moved `install.sh` tests. `deploy-tests/stack/test_stack_guard.py` (1).
- Checked against each story's acceptance criteria: every listed case has a test. The SPEC forbids the Run from executing them, so they were not run. They run in `deploy.yml` on the pull request.

## Coverage

| Story | CAP | Unit (`make test`) | Deployment (`deploy-tests/`) | Backend e2e | UI e2e |
|-------|-----|--------------------|------------------------------|-------------|--------|
| 1 — Deployment gate, production guard | CAP-1 | ✅ existing | ✅ existing (guard + 3 moved) | n/a (no route) | n/a |
| 2 — BMAD leaves the image | CAP-2 | ✅ existing | ✅ existing (collision) | ✅ existing `test_repo_init` (image built and booted from the new Dockerfile) | n/a |
| 3 — Setup runner | CAP-3 | n/a (script) | ✅ existing (10) | n/a (no route; setup never runs at boot) | n/a |
| 4 — BMAD sample script | CAP-4 | n/a (script) | ✅ existing (6) | n/a | n/a |
| 5 — Release pins, setup service | CAP-5 | ✅ existing (`test_env_contract_release_pins.py`, revised compose/env tests) | ✅ existing (13) | n/a (deploy compose is not the e2e stack) | n/a |

- API endpoints added or changed by the epic: 0/0.

## Run Results

The regression run was `make e2e`, against the disposable `aio-e2e` stack. A second pass ran without `--maxfail=3` to see the whole suite. Both stacks were torn down afterwards, and no other stack was touched.

- **The image builds and boots** from the epic's Dockerfile (`/opt/bmad` install, `ASSET_DIRS`), and the backend reports healthy. To build it, `backend-api/.venv` was moved aside for the run and then restored (defect 2 below).
- **152 passed, 13 failed, 117 errors** (11 deselected for durability).
- **129 of the 130 failures and errors** come from the sandbox limit recorded in epic 1's summary. Clone-check fails with `fatal: '/work/e2e-fixtures/…' does not appear to be a git repository` because the pytest process writes fixture repositories to a `/work` that the docker daemon's backend container does not share. Every Repository-backed module fails this way, including `test_repo_init.py`. Whether those scenarios pass is not known from this run.
- **1 failure is a real defect, already open:** `tests/e2e/test_harnesses.py::test_the_response_is_the_one_list_envelope`. Its closed key set lacks `setup` (epic 1, story 2). It is still waiting on the Operator's ruling, so the test was left untouched.
- No failure points at an epic 2 change.

## Defects found (not fixed, reported to the Operator)

1. **Still open from epic 1:** the e2e harness envelope test needs `"setup"` added to its key set. It needs an Operator ruling under hard rule 1.
2. **Still open from epic 1:** `.dockerignore`'s `.venv` matches only the root. A host `backend-api/.venv` gets copied into the image and breaks start-up. Epic 2 edited the image but not `.dockerignore`, so the defect stands. `**/.venv` fixes it.

## Next Steps

- Run `make e2e` on CI or on a host that shares `/work` with the stack. This settles the Repository-backed scenarios, including `test_repo_init.py` on the image's `/opt/bmad` path.
- Let `deploy.yml` run the epic's deployment tests on the pull request.
- Epic 4: in `deploy-tests/stack/`, assert the image's `/opt/bmad` installer and the `setup` service against a real throwaway stack.
