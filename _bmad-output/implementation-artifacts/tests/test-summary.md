# Test Automation Summary — orchestrator-deploy-folder / epic-4-stack-proof

Generated: 2026-11-12 (dispatch, empty story id, covering the whole epic)
Spec: `initiatives/orchestrator-deploy-folder/epic-4-stack-proof/SPEC.md` (hub-relative)
Stories: 1–5 (committed `a5fdadb`..`f2dd7f9`)

---

## Generated Tests

### Unit gate (run by `make test`)

- [x] `backend-api/tests/unit/test_deploy_stack_surface.py` (22 tests). It checks that the product still offers what the deployment stack tests drive. The module reads `deploy-tests/stack/*.py` as source with `ast`; it never imports or runs them, so the epic's constraint holds.
  - **Every API path a stack test calls is a route.** All `/api/…` and `/healthz` string and f-string literals are checked against `contracts/openapi.json`, with placeholders matched to one segment. There is one case per module; 36 literals are checked across 5 modules.
  - **Every variable a stack test writes is declared.** Each env-style dict literal (spreads ignored) must name only keys declared in `deploy/.env.example` or `deploy/release.env`. That covers the 15 keys of `harness.py`'s `.env`, the gateway/tracing/`GITHUB_TOKEN` keys of `test_install.py` and `test_setup.py`, and `test_runs_survive_upgrade.py`'s `ORCH_TEST_MODE`, `MAX_ACTIVE_RUNS` and `DBOS_APPLICATION_VERSION`.
  - **The survival proofs' anchors.** `MAX_ACTIVE_RUNS`, `ORCH_TEST_MODE` and `COMPOSE_PROJECT_NAME` are declared, and `DBOS_APPLICATION_VERSION` lives in `release.env`, which is where AC-9a's derived release changes it.
  - **The readers are tested themselves** on sources the module owns: f-string pieces, query stripping, extra or missing segments, spreads, and commented-out declarations.
  - **Why this matters:** `harness._apply_release_env` replaces matching lines of the shipped `.env.example` and *appends* any key it does not find. Suppose a setting were renamed in the product. The stack would then start on that setting's default, with no error. AC-9's global queue (`MAX_ACTIVE_RUNS`) and AC-9a's engine-version refusal would no longer prove anything. A renamed route would surface only when `deploy.yml` runs. This test makes both kinds of drift fail in `make test`.

### Backend API E2E tests (`backend-api/tests/e2e`)

- None added. Epic 4 changes no product code: every commit touches only `deploy-tests/`.

### UI E2E tests

- None. Epic 4 does not touch the web client.

### Deployment tests (written by the stories, not run here)

- `deploy-tests/stack/`:
  - `conftest.py`, `harness.py` and `test_harness.py` (story 1), with the guard unit test `deploy-tests/unit/test_stack_harness.py`
  - `test_install.py` (story 2)
  - `test_upgrade.py` (story 3)
  - `test_runs_survive_upgrade.py` (story 4)
  - `test_setup.py` (story 5)
- These were read against each story's scope. The SPEC forbids the Run from executing them, so none was run. They run in `deploy.yml` (job `stack`).

## Coverage

| Story | CAP | Unit (`make test`) | Deployment (`deploy-tests/`) | Backend e2e | UI e2e |
|-------|-----|--------------------|------------------------------|-------------|--------|
| 1 — Throwaway-stack harness | CAP-1 | ✅ **new** `.env` keys and `/healthz` and `/runs/{id}` paths | ✅ existing | n/a | n/a |
| 2 — Install proofs | CAP-2 | ✅ **new** gateway and tracing keys, probe/version/templates/runs paths | ✅ existing | n/a | n/a |
| 3 — Upgrade proofs | CAP-3 | ✅ **new** templates, activity and version paths | ✅ existing | n/a | n/a |
| 4 — Runs survive an upgrade | CAP-4 | ✅ **new** `ORCH_TEST_MODE`, `MAX_ACTIVE_RUNS`, `DBOS_APPLICATION_VERSION`; signals/detail/activity paths | ✅ existing | n/a | n/a |
| 5 — Setup proofs | CAP-5 | ✅ **new** secret keys, preflight and harnesses paths | ✅ existing | n/a | n/a |

- Stack-test API literals that resolve to a contract route: 36/36. Stack-test `.env` keys that are declared: all.

## Run Results

- Targeted: `uv run pytest tests/unit/test_deploy_stack_surface.py` → 22 passed.
- `make lint`: exit 0. The first run caught one E501 in the new module's docstring; it was shortened and lint re-run.
- `make test`: exit 0. Backend: 10824 passed, 1 skipped, coverage thresholds held. Web client: 1868 passed.
- Deployment tests (`deploy-tests/`), `docker` and `install.sh` were not run, as the SPEC requires.

## Observations (not defects found by a run)

- Story 4 says `MAX_ACTIVE_RUNS=1`, but `test_runs_survive_upgrade.py` sets `2`. A comment in that file explains why: a parked Run holds a global slot (AD-12), so P, B and Q can coexist only as two parked and one queued. The deviation is reasoned, but it departs from the story's text, and the Operator may want to confirm it when the PR runs `deploy.yml`.
- Still open from earlier epics: the e2e harness envelope key set lacks `setup` (awaiting an Operator ruling), and `.dockerignore`'s root-only `.venv`.

## Next Steps

- Let `deploy.yml` run `make test-deploy-stack` on the pull request. Only a real stack proves AC-1..AC-18.
