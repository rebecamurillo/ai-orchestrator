# Test Automation Summary — orchestrator-client-kit / epic-01-template-folder

Generated: 2026-11-06 (dispatch, story id `.` — the whole epic)
Spec: `initiatives/orchestrator-client-kit/epic-01-template-folder/SPEC.md` (hub-relative)
Stories: 1–8 (committed `99fe66c`..`3f42e1c`)

---

## Generated Tests

### Backend API E2E Tests

- [x] `backend-api/tests/e2e/test_template_folder_epic.py`. 10 httpx scenarios over the suite's own templates. Every name is unique per run, and nothing reads `templates/*.yaml` (hard rule 6):
  - CAP-5: `POST /templates/reload` without the bearer gets 401 problem+json. With the bearer it gets either the D3 report (`folder`, `stored`, `unchanged`, `refused`, `not_in_folder`, and a second reload stores nothing) or a 409 problem whose detail is `template folder not configured` / `template folder not found: …`. The test never skips.
  - CAP-4/5: a saved name that has no file keeps exactly its saved versions after a reload, so nothing is deleted or added.
  - CAP-3: an input `description` comes back through the real repository, an absent one comes back as `null`, and a non-string one gets `invalid value`.
  - CAP-6: a fresh name has `in_folder: false` on save, on a version read and in the list.
  - CAP-2: a depth-2 file with `bind:` saves, validates clean and graphs `epics.stories.build` with nested groups, where the outer group lists the inner node. The rejections `nested for_each`, `second for_each` and `loop name already bound` (bind name = input) each have a test.

### Playwright (UI) E2E Tests

- None added. CAP-6's notice is the only UI change. `web-client/tests/unit/template-folder-notice.test.ts` already covers it rendering and not rendering. The e2e stack runs with the folder off, so a Playwright spec could only show the notice absent.

---

## Coverage

| Story | CAP | Backend unit | Backend e2e | Frontend unit | Frontend e2e |
|-------|-----|--------------|-------------|---------------|--------------|
| 1 — Row number is the version | CAP-1 | ✅ existing | n/a (only folder files can disagree; the save API refuses a mismatched `version:`) | n/a | n/a |
| 2 — Loops within loops, bind | CAP-2 | ✅ existing | ✅ new (4) | n/a | n/a |
| 3 — Input description | CAP-3 | ✅ existing | ✅ new (2) | n/a | n/a |
| 4 — Folder loaded at start-up | CAP-4 | ✅ existing | ✅ new (1, nothing deleted) | n/a | n/a |
| 5 — Reload without restart | CAP-5 | ✅ existing | ✅ new (2) | n/a | n/a |
| 6 — Folder notice | CAP-6 | ✅ existing | ✅ new (1) | ✅ existing | n/a (folder off in e2e) |
| 7 — Five shipped templates | CAP-7 | ✅ existing | n/a (no e2e may pin shipped content) | n/a | n/a |
| 8 — Documentation | CAP-8 | ✅ existing | n/a | n/a | n/a |

API endpoints touched by the epic that this file covers: 4/4 (`POST /templates/reload`, plus `in_folder` and `description` on `GET /templates`, `GET /templates/{name}/{version}` and `POST /templates/{name}/versions`).

---

## Verification

- **Not run against a stack.** The epic SPEC forbids `make e2e*` and `docker compose` (Constraints: production is untouched). So `make e2e-api` was not run.
- **In-process run instead.** A throwaway runner outside the repo (`/tmp/e2echeck/run_check.py`) ran all 10 test functions through `fastapi.testclient.TestClient` on `create_app`, with `template_ports` overridden onto the shared unit fakes. It ran them twice, once with the folder off and once with an empty ready folder. Result: **20/20 PASS**. This checks the routes, schemas, validator rules and graph shape. It does not check the real Postgres repository.
- `ruff check`, `ruff format --check` and `pytest --collect-only` (10 collected) pass on the new file. `make lint` passes.

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) once the Operator allows it, to run this file against real Postgres.
