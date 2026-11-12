# Test Automation Summary — orchestrator-deploy-folder / epic-3-deploy-folder

Generated: 2026-11-12 (dispatch, empty story id, covering the whole epic)
Spec: `initiatives/orchestrator-deploy-folder/epic-3-deploy-folder/SPEC.md` (hub-relative)
Stories: 1–5 (committed `98b9503`..`f1f033d`)

---

## Generated Tests

### API tests (unit gate, ASGI transport, run by `make test`)

- [x] `backend-api/tests/unit/test_install_sh_wire_order.py` (3 tests). This pins the **key order** of the C5 responses that `deploy/install.sh` parses with sed and awk:
  - `GET /instance/activity`: `working[]` rows are `run_id, run_label, path, kind, started_at`. `in_engine[]` rows are `run_id, run_label, status, park_kind, queue_reason`.
  - `POST /instance/hold` 409: `errors[]` rows begin with `run_id`, in the same order as the `working[]` rows.
  - `GET /harnesses`: an item begins with `name` and ends with `setup`, after `lines[]`. The setup object carries one `ok`. A failure row is `script, reason`.
  - **Why this matters:** `install.sh` splits arrays on each row's first key (`json_array_items … run_id`, `json_items … name`). It reads a harness's setup record as everything after `"setup":`, then takes the last `"ok"` match. Suppose a schema field is reordered — for example, `setup` placed before `lines`. The upgrade's exit-3/4 refusals and the setup report would then misread, and no test would fail, because every deployment-test fixture is hand-written JSON. Epic 1's e2e and unit tests check these keys only as sets.
  - Built on the shared fakes (`a_world`, `an_attempt`, `FakeInstanceHoldRepository`, `FakeSetupRecord`, and the `Api` of `test_harnesses_router.py`). No new doubles.

### Backend API E2E tests (`backend-api/tests/e2e`)

- None added. Epic 3 changes no route, schema or contract: `git diff 8cd22ac HEAD -- backend-api/src web-client/src contracts` is empty. Epic 1's `tests/e2e/test_instance.py` already drives the C5 calls (hold, 409, activity, the `setup` field) against the running stack. Key order is deterministic in the response models, so the unit gate covers it without a stack.

### UI E2E tests

- None. Epic 3 does not touch the web client.

### Deployment tests (written by the stories, not run here)

- `deploy-tests/unit/`: `test_folder_layout.py` (story 1), `test_install_folder.py` (2), `test_upgrade.py` (3), `test_setup_commands.py` (4), `test_readme_roles.py` (5), and the revised `test_deploy_install.py`, `test_install_admin.py` and `test_install_verify_docker.py`.
- These were checked against each story's acceptance criteria. The SPEC forbids the Run from executing deployment tests or `install.sh`, so neither was run. They run in `deploy.yml` on the pull request.

## Coverage

| Story | CAP | Unit (`make test`) | Deployment (`deploy-tests/`) | Backend e2e | UI e2e |
|-------|-----|--------------------|------------------------------|-------------|--------|
| 1 — Folder layout, product manifest | CAP-1 | ✅ existing (Dockerfile/entrypoint pins) | ✅ existing | n/a (no route) | n/a |
| 2 — install, no platform | CAP-2 | ✅ **new** wire order of hold, 409 and harness `setup` | ✅ existing | ✅ epic 1 `test_instance.py` | n/a |
| 3 — upgrade under the hold | CAP-3 | ✅ **new** wire order of `working[]`, `in_engine[]` and 409 `errors[]` | ✅ existing | ✅ epic 1 `test_instance.py` | n/a |
| 4 — setup and bmad commands | CAP-4 | ✅ **new** (same C5 calls) | ✅ existing | ✅ epic 1 | n/a |
| 5 — Docs, kit skill, spine | CAP-5 | ✅ existing (`test_spine_deploy_folder.py`, docs tests) | ✅ existing (`test_readme_roles.py`) | n/a | n/a |

- API endpoints added or changed by the epic: 0/0. API endpoints `install.sh` consumes whose wire order is now pinned: 3/3 (activity, hold, harnesses). `/version` is read only through `json_string` on top-level keys, which does not depend on order.

## Run Results

- `make lint`: exit 0.
- `make test`: exit 0. Backend: 10802 passed, 1 skipped, coverage thresholds held. Web client: 1868 passed.
- `make e2e` was not run. The epic adds no e2e scenario. As the epic 1 and epic 2 summaries record, Repository-backed e2e modules cannot pass in this sandbox (`/work` is not shared with the docker daemon).

## Defects found

- None new. The schemas emit the keys in the order `install.sh` expects. The new tests guard that order going forward.
- Still open from earlier epics: the e2e harness envelope key set lacks `setup` (awaiting an Operator ruling), and `.dockerignore`'s root-only `.venv`.

## Next Steps

- Let `deploy.yml` run the epic's deployment tests on the pull request.
- Epic 4 (`deploy-tests/stack/`): drive `install.sh upgrade` and `setup` against a real throwaway stack. That proves the parsing end to end, not just the key order.
