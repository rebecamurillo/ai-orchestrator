# Test Automation Summary — orchestrator-deploy-folder / run-2 / epic-5-catalog-and-gate

Generated: 2026-11-12 (dispatch, empty story id, covering the whole epic)
Spec: `initiatives/orchestrator-deploy-folder/run-2/epic-5-catalog-and-gate/SPEC.md` (hub-relative)
Stories: 1–3 (committed `2ccf3af`..`c9031cc`)

---

## Generated Tests

### Unit gate (run by `make test`)

- [x] `backend-api/tests/unit/test_setup_catalog_flow.py` (15 tests). It covers the chain the epic builds, from a setup run to the catalog pre-flight reads. The stories tested each link on its own. This module runs the links in sequence on one temporary agent home.
  - **The chain** (real scripts, real reader). `scripts/setup/prepare.sh` runs first. Skill folders are then added and removed, the way `bmad install|remove` does it, and `<h>.sh catalog` runs after each change. `FsSkillCatalog` (the adapter pre-flight uses) then reads the result.
    - A fresh home gives an *empty* catalog, not an *unavailable* one.
    - Installed skills reach the reader. A removed skill drops out on the same reader instance, so no restart is needed (CAP-2).
    - Stray files are not listed.
    - The opencode catalog is the one the `local` harness reads.
    - `catalog` for one harness does not write another harness's manifest.
  - **The names the chain depends on agree** (static reads; `install.sh` is read as text, never run).
    - Each harness's declared `skills` asset folder sits beside the manifest `MANIFESTS` reads.
    - `prepare.sh`, `run.sh` and `setup_service_run` name the same three harnesses.
    - The paths `install.sh` calls (`/app/scripts/harness/${h}.sh catalog`, `--entrypoint /app/scripts/setup/prepare.sh`) are shipped by the Dockerfile's `COPY` lines, and each harness script has a `catalog)` case.
    - In `setup_service_run`, prepare.sh comes before the setup service, which comes before `catalog`. The function contains no `restart`, `stop` or `down`.
    - `run.sh` phase 4 counts folders and makes no `write_skills_manifest` call.
  - **Why this matters:** suppose one harness's skills folder were renamed in its script, or a harness were added to the reader but not to the `install.sh` loop. Every per-link test would still pass. Pre-flight would refuse installed skills, which is the B1 failure this epic fixes, and only the `deploy.yml` stack job would notice.

### Backend API E2E tests (`backend-api/tests/e2e`)

- None added. Epic 5 changes no API route, schema or contract.

### UI E2E tests

- None. Epic 5 does not touch the web client.

### Deployment tests (written by the stories, not run here)

- `deploy-tests/unit/test_setup_commands.py`, `test_install_folder.py`, `test_upgrade.py`, `test_setup_runner.py`, `test_bmad_script.py` and the other edits in `deploy-tests/unit/` (stories 1–3).
- The SPEC forbids the Run from executing them, so none was run. They run in `deploy.yml` (`unit` job). `make lint` now runs `ruff` over `deploy-tests/`, and it is clean.

## Coverage

| Story | CAP | Unit (`make test`) | Deployment (`deploy-tests/`) | Backend e2e | UI e2e |
|-------|-----|--------------------|------------------------------|-------------|--------|
| 1 — Mounts exist, log folder writable | CAP-1 | ✅ existing `test_setup_prepare_script.py`; **new** prepare → catalog chain, prepare entrypoint shipped in the image | ✅ existing | n/a | n/a |
| 2 — Catalog written by backend-api only | CAP-2 | ✅ existing `catalog` tests in `test_harness_scripts.py`; **new** catalog → `FsSkillCatalog` install/remove, folder/manifest agreement, harness lists, call order, no restart | ✅ existing | n/a | n/a |
| 3 — Deployment gate lint + unit lane | CAP-3 | ✅ `make lint` lints `deploy-tests/` (exit 0) | ✅ existing (read, not run) | n/a | n/a |

## Run Results

- Targeted: `uv run pytest tests/unit/test_setup_catalog_flow.py` → 15 passed.
- `make lint`: exit 0 (this includes ruff over `deploy-tests/`).
- `make test`: exit 0. Backend: 10855 passed, 1 skipped, and the coverage thresholds held. Web client: 1868 passed.
- Deployment tests, `install.sh`, `docker` and any stack were not run, as the SPEC requires.

## Next Steps

- Let `deploy.yml` run on the pull request. The `unit` job is expected green. The `stack` job's catalog assertions (epic 4 A6: AC-11, AC-12, AC-14, AC-18) are expected to pass.
