# Test Automation Summary — orchestrator-deploy-folder / epic-1-hold-catalog

Generated: 2026-11-11 (dispatch, story id `.`, covering the whole epic)
Spec: `initiatives/orchestrator-deploy-folder/epic-1-hold-catalog/SPEC.md` (hub-relative)
Stories: 1–4 (committed `1615aca`..`b298b27`)

---

## Generated Tests

### Backend API E2E Tests

- [x] `backend-api/tests/e2e/test_instance.py` is a new file with 14 httpx scenarios. Every Run it starts uses its own template name and its own Repository. Every hold it places is released in a `finally` fixture and has a 120 s TTL as backstop. It reads no `templates/*.yaml` (hard rule 6).
  - Auth: `GET /instance/activity`, `POST /instance/hold` and `DELETE /instance/hold` all return 401 without the bearer.
  - CAP-3: the activity read has exactly `working`, `in_engine`, `hold` and `dbos_application_version`, and the version equals the exported `DBOS_APPLICATION_VERSION`.
  - CAP-3: a real running `shell` step (`sleep 30`) is listed under `working` with kind, path, label and `started_at`, and its Run is listed under `in_engine` as `running`. Once the Run is cancelled it is absent from both lists.
  - CAP-4: `ttl_seconds` 0 and 3601 return 422 problem+json and nothing is held. A `reason` of 201 characters returns 422. `DELETE` returns 204 twice in a row with nothing held.
  - CAP-4: a hold is placed (201, `expires_at = held_at + ttl` within 2 s), read back through the activity read, and replaced by a second POST (the expiry moves and the reason changes). After `DELETE` the hold is `null`.
  - CAP-4: with a step working, `POST /instance/hold` returns 409 problem+json whose `errors[]` names the step (`run_id`, `run_label`, `path`, `kind`, `started_at`), and the activity read shows no hold.
  - CAP-4 / D-4: a Run started under a hold keeps its step `queued` past several 5 s walker polls. The Run stays `running`, is not listed as working, and `GET /queue` gives it the reason `held for upgrade`. After `DELETE` the Run reaches `done`.
  - CAP-2: every `GET /harnesses` item carries `setup: null` and `GET /version` carries `bmad_installed: null`, because no setup record exists in a fresh stack. `bmad_version` still equals the pinned setting.

### UI E2E Tests

- None. The SPEC's non-goals exclude any web-client screen in this epic; only the regenerated types changed.

## Coverage (new endpoints and fields, e2e)

- `GET /api/v1/instance/activity`: covered (auth, shape, working, in_engine, terminal Run absent).
- `POST /api/v1/instance/hold`: covered (auth, 201, replace, 409, 422 ×3).
- `DELETE /api/v1/instance/hold`: covered (auth, 204 with and without a hold).
- `GET /api/v1/queue` `held for upgrade`: covered.
- `GET /api/v1/harnesses` `setup`, `GET /api/v1/version` `bmad_installed`: covered for the no-record case only. A record cannot be planted through the API, and the backend never writes it. The unit suite covers the failed-script, corrupt and installed cases.
- CAP-1 (the per-harness catalog in pre-flight) has no e2e scenario: a manifest cannot be varied per harness through the API. It stays covered by the unit suite.
- 5/5 new routes or fields reached; 3/4 capabilities exercised end to end.

## Run Results

The gate was `make e2e`, against the disposable `aio-e2e` stack, which was torn down after each run.

- `make lint`: exit 0 with the new file.
- **11 of the 14 new scenarios pass**: the three 401s, the activity shape, both TTL 422s, the reason 422, DELETE, place/replace/release, harness `setup`, and version `bmad_installed`.
- **3 have not been run to a result here**: the shell-step activity, the 409, and the hold-then-release Run. Their `repository_id` fixture fails at clone-check with `fatal: '/work/e2e-fixtures/…' does not appear to be a git repository`. In this sandbox the pytest process writes fixture repositories to the host's `/work`, and the backend runs in a docker-in-docker daemon that cannot see that path. The existing `test_answer_signal.py`, `test_run_creation.py` and every other Repository-backed module fail the same way here. They need a run on a host or CI runner where the stack shares `/work` with the test process.

## Defects found (not fixed, reported to the Operator)

1. **`tests/e2e/test_harnesses.py::test_the_response_is_the_one_list_envelope` fails after story 2.** Its closed key set has 8 names and the response now also carries `setup`. `api/schemas/harnesses.py`'s own docstring says story 2 took both equalities to nine, but only the unit one changed. The e2e file is not in story 2's list of tests it may change, so under hard rule 1 this needs the Operator's ruling before the assertion gains `"setup"`. The test was left untouched.
2. **`.dockerignore` lists `.venv`, which matches only a root-level `.venv`.** When `backend-api/.venv` exists on the build host (it does after `make test` or `make lint`), `COPY backend-api/ ./` copies it into the image. The resulting image's backend exits 127 at start-up with `.venv/bin/alembic: cannot execute: required file not found`, because the shebang points to the host path. `**/.venv` (or `backend-api/.venv`) would fix it. That is an image change, which is outside this epic. For this run the host venv was moved aside during the build and then restored.

## Next Steps

- Run `make e2e` on CI or a host that shares `/work` with the stack, to settle the 3 Repository-backed scenarios.
- Operator ruling on defect 1, then a one-name revision of the e2e envelope test.
- Fix `.dockerignore` (defect 2) in the epic that owns the image.
