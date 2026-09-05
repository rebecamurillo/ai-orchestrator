---
title: 'Git port, base clone layout, and the Clone check'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      A clone check reads a Repository, spends minutes in git, then writes back every mutable
      field from that stale snapshot, and concurrent checks race into the same base directory.
    evidence: |-
      run_clone_check reads the entity, runs up to four 120 s commands, then calls
      repositories.update(checked), which persists url, default_branch and the commands from
      the pre-check snapshot. An Operator edit landing in that window is lost. Two POST
      /clone-check calls, or a POST racing the loop a PUT /projects/{id} runs, clone or fetch
      into the same {work_dir}/{project.slug}/{repository.slug}/base concurrently. There is no
      lock, no version column and no SELECT ... FOR UPDATE.
    location: >-
      backend-api/src/orchestrator/application/use_cases/clone_check.py:77
    severity: medium
  - summary: >-
      The save-time check has no time budget: it runs inside the request, holding the database
      session, for as long as every repository's commands take.
    evidence: |-
      _check_repositories runs N repositories x up to four commands x 120 s inside the
      project_ports unit of work, so one PUT can occupy a database connection and a threadpool
      worker for many minutes with no request-level deadline and no way to opt out. The e2e
      client makes it visible: tests/e2e/conftest.py uses timeout=10.0, and every new clone
      check and project PUT now runs real git under that read timeout.
    location: >-
      backend-api/src/orchestrator/api/routers/projects.py:130
    severity: medium
  - summary: >-
      The e2e suite now needs the whole environment contract exported, contradicting the
      two-variable invocation its own conftest documents.
    evidence: |-
      tests/e2e/test_clone_check.py constructs Settings() in the test process, and every
      Settings field is required with no default, so the documented
      "BACKEND_API_URL=... ORCHESTRATOR_TOKEN=... make e2e-api" errors the module with a
      pydantic validation list instead of conftest's deliberate one-variable message. This
      predates the story - tests/e2e/test_projects.py already instantiates Settings the same
      way - and was reproduced during this run's verification.
    location: >-
      backend-api/tests/e2e/test_clone_check.py
    severity: low
  - summary: >-
      The e2e fixture picks its topology by testing whether WORK_DIR is writable here, which
      is a heuristic rather than a fact about where the backend runs.
    evidence: |-
      Fixtures.make writes the bare repository directly when settings.work_dir is writable by
      the test process and otherwise shells out to docker compose exec. On a host that both
      has a writable /work and runs the containerised stack it would take the local branch
      while the backend reads a different volume. It never skips, so this surfaces as a
      failure naming both routes rather than a false pass. The spec's Design Notes prescribe
      this heuristic.
    location: >-
      backend-api/tests/e2e/test_clone_check.py
    severity: low
  - summary: >-
      Nothing removes a base clone or an e2e fixture repository under WORK_DIR.
    evidence: |-
      E2E fixture repositories and the base clones made under random project slugs accumulate
      on the work volume across runs, and no code path deletes a base clone when a Repository
      or a Project is deleted. This matches the existing e2e suites' style, so it is a gap in
      the layout rather than a regression this story introduced.
    location: >-
      backend-api/src/orchestrator/application/use_cases/clone_check.py:153
    severity: low
  - summary: >-
      clone_base leaves HEAD wherever the remote's HEAD points, so the detached-at-origin
      invariant is established only on the second check.
    evidence: |-
      fetch_base moves HEAD to origin/{default_branch} with update-ref and is tested, but a
      fresh clone_base does not, so a repository whose remote HEAD is not the configured
      default branch has a base whose HEAD disagrees until something fetches. It does not
      affect this story - read_file addresses origin/{branch} explicitly - but a later
      worktree story would rely on it.
    location: >-
      backend-api/src/orchestrator/infrastructure/git/subprocess_git.py:112
    severity: low
baseline_revision: '2b3604d0886910ba873aef9723104e359492bdba'
---

<intent-contract>

## Intent

**Problem:** Nothing in the orchestrator has ever run `git`. A Repository's `clone_check` has read
`pending` since 2.2, so a wrong URL, a token without access, or a default branch that does not exist
on origin stays invisible until a Run is hours in (SM-5), and nothing reads the BMAD method version a
repository carries (FR-30).

**Approach:** Add the `Git` port with a subprocess adapter that supplies `GITHUB_TOKEN` per command
through `GIT_ASKPASS`, the `/work/{project.slug}/{repository.slug}/base` blobless base clone, and a
`run_clone_check` use case that records four lines — `ls-remote`, `clone`, `default branch`, `method
version` — onto the Repository. It runs for every Repository when a Project is saved and on demand
from `POST /api/v1/repositories/{id}/clone-check`.

## Boundaries & Constraints

**Always:**
- AD-2 layering: `Git` protocol + `RemoteRef`/`CloneResult`/`GitError` in `domain/ports/git.py`;
  `CloneCheckLine` and the `hint` rule in `domain/entities/repository.py`; `run_clone_check` in the
  **new** `application/use_cases/clone_check.py`; every `subprocess`/`os`/`shutil` call inside
  `infrastructure/git/`. `import-linter` forbids `subprocess`, `os`, `shutil` in `domain/` and
  `application/` — the use case receives `Git`, `Clock`, `work_dir: Path` and `bmad_version: str` as
  arguments and does no I/O.
- AD-5, token per command: the adapter builds each subprocess environment itself (it never inherits
  the parent environment wholesale), sets `GIT_ASKPASS` at a 0700 copy of `infrastructure/git/askpass.sh`,
  `GIT_TERMINAL_PROMPT=0`, `GIT_CONFIG_NOSYSTEM=1`, passes `-c credential.helper=` on every `git`
  invocation, and puts the token only in the private variable the script echoes. The token never
  reaches the URL, a git config, a file under `WORK_DIR`, or a log line; every `GitError.output` and
  every stored `output` runs through `redact()` first.
- Checks run in order and stop at the first failure among lines 1–3; line 4 (`method version`) is
  informational and never sets `status: failed`. `status` is `failed` when any of lines 1–3 failed,
  else `ok`.
- `repository.clone_check` is written by `run_clone_check` and by nothing else (AD-14). A failing
  check never blocks a Project save: the save use case commits first, then the checks, then commits
  the results. `updated_at` is not bumped by a check — `clone_check.at` is when it ran.
- Each git command carries a 120 s timeout; expiry is a failed line whose output is
  `timeout after 120 s`.
- No new `Settings` field: `work_dir`, `bmad_version` and `github_token` already exist.
  `scripts/check_env_contract.py` and the frozen counts in `tests/unit/test_env_contract.py`
  (`"25"` fields / `"31"` contract variables) must stay exactly as they are.
- Every new `src/orchestrator/**` module is imported by a **new** `tests/unit/` module
  (`scripts/check_test_pairs.py`); `domain/` + `application/` stay at 100 % branch coverage with no
  `pragma: no cover`; `make openapi` regenerates `contracts/openapi.json` and
  `web-client/src/api/schema.d.ts`, both committed.
- Every published `/api/v1` path must declare a `get` operation
  (`tests/unit/test_bearer_auth.py::test_the_contract_declares_the_401_and_its_media_type` indexes
  `paths[path]["get"]`), so `POST /repositories/{id}/clone-check` ships beside
  `GET /repositories/{id}/clone-check`, which reads the stored result and runs nothing.
- Each `include_router` call in `main.py` keeps `prefix=API_PREFIX` and
  `dependencies=[Depends(require_bearer)]` verbatim; `api/deps.py` is not touched.
- `ruff PLR0913` caps a function at 5 arguments; `test_source_limits.py` caps a module at 400 lines
  (`application/use_cases/projects.py` is already at 374).

**Block If:**
- A frozen anchor (`SPEC.md`, `stories.yaml`, any `AGENTS.md`, any pre-existing test file) would have
  to change for a gate to pass, beyond the read-model placement resolved in Design Notes.
- The architecture spine and this spec disagree on a field, a route, or a port signature.
- `git` is unavailable in the environment `make test` runs in (the adapter's real-git unit tests
  need the binary; they never need a network).

**Never:**
- No worktrees, sync, commit, push, and no daily re-check job (Epic 4). No UI (2.4, 2.5).
- Never add a key to the `clone_check` object of `RepositoryOut`, and never add a column to the
  `repository` table: `tests/unit/test_repositories_router.py:130`,
  `tests/unit/test_repository_repository_adapter.py:232/305/358/367` and
  `test_the_table_carries_exactly_the_columns_the_entity_has` are frozen against exactly the four
  keys and the thirteen columns 2.2 shipped.
- Never let a harness process, a log line, or a response body carry `GITHUB_TOKEN`.
- Never make the check network-dependent in `tests/unit/` — the fake `Git` covers the use case and
  local `file://` bare repositories cover the adapter.
- Never skip an e2e test when the stack or the fixture is missing; fail with what is missing.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reachable repository, manifest matches | `POST /repositories/{id}/clone-check`, `BMAD_VERSION=6.11.0`, manifest `installation.version: 6.11.0` | 200; `status: ok`; four lines each `ok` with `seconds`; `bmad_version: "6.11.0"`; `hint: ""` | No error expected |
| Manifest states another version | same, manifest `6.12.0` | `bmad_version: "outdated"`, `status: ok` | No error expected |
| No manifest in the repository | `read_file` returns `None` | `bmad_version: "missing"`, `status: ok`, line 4 `ok` | No error expected |
| Manifest present but unparseable / no `installation.version` | file exists, bad YAML or missing key | `bmad_version: "missing"`, `status: ok`, line 4 `ok` with the reason in its `output` | Parse failure is not a check failure |
| Unreachable URL | `ls_remote` raises `GitError` | `status: failed`; line 1 `failed` with the verbatim redacted output; lines 2–4 absent; `hint: "repository not found: check the URL"` when the output names `Repository not found` | `GitError` becomes a failed line, never a 500 |
| Token has no access | output contains `Authentication failed` or `could not read Username` | `status: failed`, `hint: "the instance's GitHub token has no access to this repository"` | as above |
| Default branch missing on origin | `ls_remote(url, branch)` returns `None` | lines 1 and 2 `ok`, line 3 `failed`, line 4 absent, `status: failed`, `hint: "branch {default_branch} does not exist on origin"` | as above |
| Failure with no matching pattern | output is some other git error | `status: failed`, `hint: ""` | as above |
| `base` already exists | second check on the same Repository | `fetch_base` is called, `clone_base` is not; line 2 `ok` with output naming `fetched` and the seconds | No error expected |
| Command exceeds 120 s | adapter timeout | that line is `failed` with output `timeout after 120 s` | `GitError` from the timeout |
| Project save | `PUT /api/v1/projects/{id}` for a Project with two Repositories, one reachable and one not | 200; the Project and both Repositories are stored; the reachable one reads `ok` with four lines and a `bmad_version`, the other `failed` with line 1 failed, verbatim output and a non-empty `hint` | The failing check never fails the save |
| Read the stored result | `GET /repositories/{id}/clone-check` | 200 with the last stored result; `pending` with no lines before any check has run | No error expected |
| Unknown Repository id | `POST`/`GET /repositories/{uuid}/clone-check` not stored | 404 problem+json | `NotFound` |
| Non-UUID id | `POST /repositories/not-a-uuid/clone-check` | 422 problem+json | FastAPI path validation |
| Unauthenticated | either operation without the bearer | 401 problem+json with `WWW-Authenticate` | inherited router dependency |
| Token in command output | a git failure whose output contains the token value | the stored `output` carries `***` in its place, and no response body, log line, or file under `WORK_DIR` holds it | `redact()` on every path out of the adapter |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/entities/repository.py` (111 lines) -- `CloneCheck{status, at,
  output, bmad_version}` (frozen pydantic), `CloneCheckStatus = pending | ok | failed`,
  `Repository.clone_check`. **Gains** `CloneCheckLine`, `CloneCheck.lines: tuple[CloneCheckLine, ...] = ()`
  (defaulted, so every frozen construction in `test_repository_entity.py`, `test_repository_ports.py`,
  `test_repository_schemas.py`, `test_repository_repository_adapter.py` keeps compiling) and the pure
  `hint` rule. `CloneCheck.pending()` keeps returning no lines.
- `backend-api/src/orchestrator/domain/ports/{clock,crypto,repositories}.py` -- the
  `Protocol` + `runtime_checkable` shape to copy for `git.py`. `RepositoryRepository.update` is what
  persists a finished check.
- `backend-api/src/orchestrator/application/use_cases/projects.py` (374 / 400 lines) -- `ProjectPorts`
  (L66) with `repositories: RepositoryRepository | None = None` and the `_repos()` narrowing helper
  (L330) — the precedent for the `git: Git | None = None` field this story adds, and the reason
  `run_clone_check` cannot live here: the module has 26 lines of headroom.
- `backend-api/src/orchestrator/api/providers.py` -- `project_ports()` (L61) builds the uow, both
  repositories, the crypto and the clock. `from_state` raises when an adapter is missing;
  `tests/unit/test_api_providers.py` builds `app.state` with **only** `session_factory` and `crypto`
  (L71-72), so the new `git` adapter must be read tolerantly (`getattr(..., None)`), not through
  `from_state`.
- `backend-api/src/orchestrator/api/routers/repositories.py` (115 lines) -- `_refusal`,
  `READ_REFUSALS`, `Ports = Annotated[ProjectPorts, Depends(project_ports)]`; the two clone-check
  operations belong here, beside the four that already address a Repository by id.
- `backend-api/src/orchestrator/api/routers/projects.py` (145 lines) -- `_read()` (L81) is the single
  helper every Project response goes through; `create_project` (L108) and `update_project` (L136) are
  where the save-time checks hook in, after the use case has committed.
- `backend-api/src/orchestrator/api/schemas/projects.py` (307 / 400 lines) -- `CloneCheckOut` (L125,
  four fields — **frozen in shape** by the router test), `RepositoryOut` (L134) and its `.of()` (L153).
  New clone-check schemas go in a new module to stay clear of the line cap.
- `backend-api/src/orchestrator/infrastructure/db/repositories/repository.py` -- `clone_check_json`
  (L44) and `clone_check_from_entity` (L55). `test_repository_repository_adapter.py:358/367` asserts
  `clone_check_json` of a check **without lines** equals exactly the four keys, and `:232/:305` assert
  the same of `row.clone_check`; `test_the_table_carries_exactly_the_columns_the_entity_has` (L120)
  forbids a new column. Lines therefore live inside the same JSONB value under a key emitted only
  when non-empty, and read back with a default — which also makes every row 2.2 wrote readable.
- `backend-api/src/orchestrator/infrastructure/settings.py` -- `work_dir: Path` (absolute, validated),
  `bmad_version: str`, `github_token: SecretStr` all already exist. **No new setting.**
- `backend-api/src/orchestrator/main.py` -- `create_app(settings, *, lifespan, session_factory,
  crypto)` (L104) is at 4 parameters; `git` makes 5, which is exactly `PLR0913`'s limit. `main()`
  (L161) is the only place an adapter is named. The three `include_router` calls (L138-156) are
  ast-checked for `prefix=API_PREFIX` and `require_bearer`.
- `backend-api/tests/unit/fakes/{clock,projects}.py` -- `FakeClock` only moves when a test moves it
  (so a fake `Git` that advances it is how line `seconds` become assertable); `FakeRepositoryRepository`
  and `FakeProjectRepository` are the stores the use-case tests run on.
- `backend-api/tests/unit/test_bearer_auth.py` -- frozen: every `/api/v1` path needs a `get`, every
  operation must 401 unauthenticated, every mount keeps its two keywords.
- `backend-api/tests/unit/test_source_limits.py`, `test_layering.py`, `test_coverage_gates.py`,
  `test_check_test_pairs.py`, `test_env_contract.py` -- the frozen gates listed under **Always**.
- `backend-api/tests/e2e/conftest.py` -- `stack`, `client`, `authenticated`, `require()`; nothing ever
  skips. The suite runs **on the host**: in CI the backend runs from source on the same runner (so a
  host path is a backend path), under `make up` it runs in a container (so it is not).
- `backend-api/tests/e2e/test_repositories.py` -- `project_id`, `unique_url`, `create_repository`,
  `repositories_url` are the fixtures/helpers to copy; `Settings()` is already instantiated inside
  e2e tests (`test_projects.py`'s `project_indexes`), so `settings.work_dir` and
  `settings.bmad_version` are available to a test.
- `backend-api/Dockerfile` -- `git` and `gh` are installed; the process runs as uid 1000 `agent`,
  which owns `${WORK_DIR}`; the package is installed non-editable but the source tree is copied, so a
  `.sh` beside the adapter is present at runtime (hatchling's `packages = ["src/orchestrator"]` has no
  `*.py` filter — `py.typed` ships the same way). The executable bit is **not** guaranteed.
- `docker-compose.yml` -- named volume `work` mounted at `${WORK_DIR}`; the backend reads the whole
  contract through `env_file`. No change needed.
- `.github/workflows/ci.yml` (job `e2e-api`, L104-142) -- copies `.env.example` to `.env` and runs the
  backend **from source on the runner**, where `WORK_DIR=/work` does not exist and cannot be created
  without root. Both the "Start backend-api from source" and "Gate" steps need a writable `WORK_DIR`.
  `tests/unit/test_ci_workflow.py` requires the job to keep `docker compose up … postgres`,
  `orchestrator.main`, `/healthz` and `make e2e-api`, and forbids naming a credential.

## Tasks & Acceptance

**Execution:**

1. `backend-api/tests/unit/test_git_port.py` -- failing tests for `RemoteRef`, `CloneResult`,
   `GitError{command, exit_code, output}` and the fake's conformance to the `Git` Protocol -- TDD;
   pairs task 2 and task 3.
2. `backend-api/src/orchestrator/domain/ports/git.py` -- `Git` `runtime_checkable` Protocol with
   `ls_remote(url, ref) -> RemoteRef | None`, `base_exists(dest) -> bool`,
   `clone_base(url, dest) -> CloneResult`, `fetch_base(dest, branch) -> None`,
   `branch_exists(dest, branch) -> bool`, `read_file(dest, ref, path) -> str | None`, plus the three
   frozen dataclasses; every method raises `GitError` on failure -- the port later stories extend.
   `base_exists` is the one addition to the brief's list: without it the use case cannot choose
   between clone and fetch without importing `os`, which AD-2 forbids.
3. `backend-api/tests/unit/fakes/git.py` -- `FakeGit`: scripted per-method responses (value or
   `GitError`), a recorded call log, an optional `FakeClock` it advances per call so line `seconds`
   are assertable -- the only double for this port (AD-18).
4. `backend-api/tests/unit/test_clone_check_entity.py` -- failing tests for `CloneCheckLine`, the
   defaulted `lines`, and every branch of the `hint` rule (auth, not-found, missing branch, none) --
   TDD; drives task 5.
5. `backend-api/src/orchestrator/domain/entities/repository.py` -- add frozen
   `CloneCheckLine{name, status, seconds, output}`, `CloneCheck.lines: tuple[...] = ()`, the line-name
   constants, and `hint` as a pure derivation from `status`, `output` and `lines` -- one place names
   the rules the API and the UI restate; nothing existing changes shape.
6. `backend-api/tests/unit/test_clone_check_use_cases.py` -- failing tests for every I/O-matrix row
   that is a use-case rule: the ok path, each failing line, each `bmad_version` value, the unparseable
   manifest, the existing-base fetch, the timeout output, ordering and short-circuiting, that only
   this use case writes `clone_check`, and that `updated_at` is untouched -- TDD; drives task 7 to
   100 % branch coverage on the fake `Git`, with no network.
7. `backend-api/src/orchestrator/application/use_cases/clone_check.py` (new module) --
   `run_clone_check(ports, repository_id, *, work_dir, bmad_version) -> Repository` and
   `run_clone_checks_for_project(ports, project_id, *, work_dir, bmad_version) -> list[Repository]`;
   the four lines, the stop-at-first-failure rule, the `/work/{project.slug}/{repository.slug}/base`
   path, `installation.version` parsing, and the commit of the results. Four arguments keeps `PLR0913`
   satisfied; a new module keeps `projects.py` under 400 lines.
8. `backend-api/src/orchestrator/application/use_cases/projects.py` -- add `git: Git | None = None` to
   `ProjectPorts`, mirroring the `repositories` field and its comment -- one ports object per feature,
   one transaction per request (2.2's Design Notes).
9. `backend-api/tests/unit/test_git_redact.py` -- failing tests for `redact()`: the token replaced
   everywhere it appears, an empty token left alone, non-token text untouched -- TDD; drives task 10.
10. `backend-api/src/orchestrator/infrastructure/git/redact.py` (new package) -- `redact(text, token)`
    replacing the token value with `***` -- the one function every path out of the adapter goes through.
11. `backend-api/src/orchestrator/infrastructure/git/askpass.sh` -- three lines: print the token from
    the private environment variable the adapter sets, and nothing else -- the token reaches `git`
    through the interface git already has for it.
12. `backend-api/tests/unit/test_subprocess_git.py` -- failing tests driving the adapter against
    **local `file://` bare repositories created in `tmp_path`** (real `git`, no network): clone,
    re-check fetch, `ls_remote` hit and miss, `branch_exists`, `read_file` present and absent, a
    failing command's `GitError` fields, the 120 s timeout wiring, that the subprocess environment
    carries `GIT_ASKPASS`/`GIT_TERMINAL_PROMPT=0` and not the inherited parent environment, that
    `askpass.sh` prints the token when run with that variable, that a token appearing in output comes
    back as `***`, and that after a check no file under the work dir, no git config and no remote URL
    contains the token -- TDD; drives task 13.
13. `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py` -- `SubprocessGit(token,
    timeout_seconds=120)` implementing `Git`: one `_run` that builds the command
    (`git -c credential.helper= …`), the minimal environment, the 0700 copy of `askpass.sh` made once
    per adapter, the timeout, and the redacted `GitError`; `clone_base` uses
    `clone --no-checkout --filter=blob:none`, records elapsed seconds and the size of the created
    tree, `fetch_base` fetches every head and then points HEAD at `origin/{branch}` when it exists
    without checking out a blob -- the only module in this story that touches a process or a file.
14. `backend-api/tests/unit/test_clone_check_schemas.py` -- failing tests for the new read models,
    including that `RepositoryOut.clone_check` still serialises exactly the four keys 2.2 published --
    TDD; drives tasks 15 and 16.
15. `backend-api/src/orchestrator/api/schemas/clone_check.py` (new module) -- `CloneCheckLineOut` and
    `CloneCheckResultOut{status, at, output, bmad_version, lines, hint}` -- the shape both clone-check
    operations answer with; a new module because `api/schemas/projects.py` is at 307 of 400 lines.
16. `backend-api/src/orchestrator/api/schemas/projects.py` -- `RepositoryOut` gains
    `clone_check_lines: list[CloneCheckLineOut]` and `clone_check_hint: str`, filled by `.of()` --
    siblings of `clone_check`, never keys inside it (see Design Notes).
17. `backend-api/tests/unit/test_clone_check_router.py` -- router tests over httpx ASGI with the fakes
    injected through `dependency_overrides`: both operations, the 404 and 422, that `GET` runs no git
    command, that a save runs one check per Repository, and that a failing check still returns 200 for
    the save -- TDD; drives tasks 18 to 21.
18. `backend-api/src/orchestrator/api/providers.py` -- read the git adapter off `app.state` with
    `getattr(..., None)` and pass it as `ProjectPorts(..., git=...)` -- a strict read would break the
    frozen provider tests, which build `app.state` with two adapters only.
19. `backend-api/src/orchestrator/api/routers/repositories.py` -- `POST /repositories/{id}/clone-check`
    (runs the check, 200 with `CloneCheckResultOut`) and `GET /repositories/{id}/clone-check` (the
    stored result, runs nothing) -- the `GET` is also what keeps the path from publishing a `POST`
    with no `GET` (`test_bearer_auth.py`).
20. `backend-api/src/orchestrator/api/routers/projects.py` -- `create_project` and `update_project`
    call `run_clone_checks_for_project` after the use case has committed, then render through `_read`
    -- the save-time check of FR-4, with the failure never reaching the Operator as a failed save.
21. `backend-api/src/orchestrator/main.py` -- build `SubprocessGit` in `main()` from
    `settings.github_token`, accept it as the fifth `create_app` keyword, store it on `app.state.git`
    -- `main.py` stays the only place an adapter is named.
22. `.github/workflows/ci.yml` -- in the `e2e-api` job's two script steps, export a writable
    `WORK_DIR` (under `${RUNNER_TEMP}`) and create it before starting the backend and before
    `make e2e-api` -- the contract's `/work` is a container volume that does not exist on the runner,
    and the clone check writes there. Nothing else in the workflow changes.
23. `backend-api/tests/e2e/test_clone_check.py` -- against the running stack: a helper that creates a
    bare repository with `_bmad/_config/manifest.yaml` on `main` under `settings.work_dir/e2e-fixtures`
    — directly when that directory is writable by this process (CI, where the backend runs on the same
    machine), otherwise through `docker compose exec -T backend-api` (a containerised stack) — and
    registers it by `file://` URL; then the ok path with the version, `outdated`, `missing`, a URL that
    exists nowhere (`failed`, line 1, verbatim output, non-empty hint), a missing default branch (line
    3, its hint), a second run reporting `fetched`, `GET` returning the stored result, the 404, and a
    `PUT /projects/{id}` that leaves one Repository `ok` and one `failed` with both still stored. It
    never skips: if neither fixture route works it fails naming both.
24. `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- regenerate with `make openapi` and
    commit -- AD-3; `make lint` fails on drift.

**Acceptance Criteria:**
- Given a Project with two Repositories, one reachable and one whose URL exists nowhere, when
  `PUT /api/v1/projects/{id}` completes, then it answers 200, both Repositories are still stored, the
  first reads `clone_check.status: "ok"` with four lines and a `bmad_version`, and the second reads
  `failed` with line 1 failed, the verbatim git output and a non-empty hint.
- Given any git command the adapter runs, when the subprocess environment, the clone under
  `WORK_DIR`, its git config and its remote URL are inspected during and after a check, then
  `GITHUB_TOKEN`'s value appears in none of them, and a failing command's stored output carries `***`
  wherever the value would have been.
- Given the unit suite, when `make test` runs, then `run_clone_check` is covered on the fake `Git` for
  the ok path, each failing line, each `bmad_version` value and an existing base, with no network, and
  `domain/` + `application/` report 100 % branch coverage.
- Given the whole suite, when `make lint && make test && make openapi && make e2e-api` run, then
  `import-linter`, `check_test_pairs`, the env-contract check, the contract-drift check and
  Schemathesis (no 5xx on either new operation) all pass, and no pre-existing test file, `AGENTS.md`,
  `SPEC.md` or `stories.yaml` was modified.
- Given `GET /api/v1/openapi.json`, when every published path is checked, then
  `/api/v1/repositories/{repository_id}/clone-check` declares both a `get` and a `post`, each with a
  401 in `application/problem+json`.

## Spec Change Log

### 2026-09-05 — Two forced deviations from **Tasks & Acceptance**, recorded so the spec does not disagree with the code

Neither of these changes the published contract, the intent contract, or an acceptance
criterion. Both were forced by a frozen anchor or by a correctness defect found in review, and
both are in the shipped code.

**1. Task 19's module placement: `api/routers/clone_check.py`, not `api/routers/repositories.py`.**
Task 19 directed the two clone-check operations into `api/routers/repositories.py`. That module
is pinned by the pre-existing
`test_repositories_router.py::test_the_router_declares_four_operations_and_repeats_no_dependency`
to exactly four routes, and that test names no later story, so hard rule 1's placeholder
exception does not apply and the file could not be edited. The operations therefore live in a
new `api/routers/clone_check.py`, mounted in `main.py` with `prefix=API_PREFIX` and
`dependencies=[Depends(require_bearer)]` verbatim. The paths, the operations, their responses
and the 401 sweep are exactly what task 19 specified — only the module differs. No anchor was
modified.

**2. Task 13's clone cleanup is conditional: `discard_partial_clone(dest, *, existed)`.**
Review found that a clone killed by the 120 s timeout leaves a partial `dest` that
`base_exists` then reports as a clone, with no recovery path. The obvious repair — an
unconditional `rmtree(dest)` when `clone_base` fails — would delete a pre-existing non-empty
directory that the clone never created and that this system did not own. The adapter therefore
records whether `dest` existed before the clone was attempted and discards it only when the
clone itself created it.

**3. Task 2's `ls_remote` grew an exact-branch mode (line 3 was wrong without it).**
Review found that `git ls-remote <url> <branch>` matches a ref by its tail on slash boundaries,
so `refs/tags/main` and `refs/heads/release/main` both answered a check for `main` — line 3
passed for a repository that has no such branch, which is the precise failure the check exists
to catch (SM-5). `--heads` alone does not fix it: it still answers `refs/heads/release/main`.
A branch query is now `--heads` plus an equality test against `refs/heads/{branch}`, verified
against an origin holding `refs/tags/main`, `refs/heads/release/main` and `refs/heads/develop`.
`ls_remote(url)` for line 1 still asks for `HEAD` unchanged.


## Review Triage Log

### 2026-09-05 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 1, medium 5, low 6)
- defer: 6: (high 0, medium 2, low 4)
- reject: 17: (high 0, medium 3, low 14)
- addressed_findings:
  - `[high]` `[patch]` Only `GitError` was caught by the four check steps, so an `OSError` from
    `mkdir` under an unwritable `WORK_DIR`, from `tree_bytes`, or a `FileNotFoundError` from a
    missing `git` binary escaped the post-commit check and answered 500 on a save that had
    already committed — breaking the story's own "a failing check never fails the save"
    invariant. `OSError` is now handled exactly as `GitError` is, the shared fake was extended
    to raise any scripted exception, and use-case and router tests cover it.
  - `[medium]` `[patch]` `tests/unit/test_subprocess_git.py` skipped itself when `git` was
    absent, disabling every AD-5 credential assertion while `make test` stayed green. The spec
    lists a missing binary as a Block If, not a skip; the module now fails loudly.
  - `[medium]` `[patch]` Line 3 asked `git ls-remote <url> <branch>`, which matches a ref by
    its tail, so a tag named `main` or a `release/main` branch satisfied a check for `main`.
    The branch query is now exact.
  - `[medium]` `[patch]` No gate asserted that the backend runtime image installs `git`;
    removing it from the Dockerfile left every gate green. A new unit test module asserts it.
  - `[medium]` `[patch]` Operator-supplied `url` and `default_branch` reached git as unguarded
    argv, so a value beginning with `-` parsed as an option. `--` now precedes the operands.
  - `[medium]` `[patch]` `status` was published as bare `string` rather than the domain's
    literal unions, so the generated client could not switch exhaustively on the status tokens.
  - `[low]` `[patch]` `CloneCheckResultOut`'s description shipped a grammatically broken
    sentence and `CloneCheckOut`'s cited story "2.2" — both published verbatim in
    `contracts/openapi.json` and `schema.d.ts`.
  - `[low]` `[patch]` `os.environ.get("PATH", FALLBACK_PATH)` returned `""` for a set-but-empty
    `PATH`, so the fallback never applied.
  - `[low]` `[patch]` A clone killed by the timeout left a partial `dest` that `base_exists`
    then reported as a clone, with no recovery path; a failed clone now removes it.
  - `[low]` `[patch]` `SubprocessGit.__init__`'s `mkdtemp` directory was never removed.
  - `[low]` `[patch]` `installed_version` did not strip an inline comment, so
    `version: 6.11.0  # pinned` read as `outdated`.
  - `[low]` `[patch]` `.github/workflows/ci.yml` used `$RUNNER_TEMP` unguarded, collapsing
    `WORK_DIR` to `/work` where it is unset.

## Design Notes

**Where the lines and the hint live, and why not inside `clone_check`.** The brief puts them at
`repository.clone_check = {status, at, output, bmad_version, lines[]}`. Three frozen assertions
written by 2.2 forbid that placement in two of the three layers, and none of them names a later story,
so hard rule 1's placeholder exception does not apply:

- `tests/unit/test_repositories_router.py:130` asserts a created Repository's response
  `body["clone_check"] == {"status", "at", "output", "bmad_version"}` — exact dict equality. FastAPI
  serialises every field of a response model, so a fifth field on `CloneCheckOut` fails it for every
  Repository, checked or not.
- `tests/unit/test_repository_repository_adapter.py:232/305/358/367` assert the same four keys of the
  stored JSON for checks that carry **no** lines.
- `test_the_table_carries_exactly_the_columns_the_entity_has` forbids a `clone_check_lines` column.

The resolution keeps every requirement and touches no anchor:

- **Domain and storage keep one object.** `CloneCheck.lines` defaults to `()`, and `clone_check_json`
  emits the `lines` key only when it is non-empty. Every frozen assertion passes because each one
  serialises a check without lines; and every row 2.2 already wrote — which has no `lines` key — reads
  back through a defaulting `clone_check_from_entity`, so no data migration is needed.
- **The API publishes them as siblings.** `RepositoryOut` gains `clone_check_lines` and
  `clone_check_hint` beside the untouched four-key `clone_check`; no frozen test asserts
  `RepositoryOut`'s key set, and `tests/e2e/test_repositories.py:78`'s `read.json() == body`
  compares two bodies that both carry them. The dedicated `CloneCheckResultOut` that both clone-check
  operations answer with is the one place the brief's full shape appears intact.

`hint` is a **derived** property of `CloneCheck`, not a stored field: it is a pure function of
`status`, `output` and the lines, so it needs no second conditional key and cannot go stale.

**Why the check is a new module and a new fake.** `application/use_cases/projects.py` is at 374 of the
400 lines `test_source_limits.py` allows, so `run_clone_check` lives in
`application/use_cases/clone_check.py` and reaches its stores through the existing `ProjectPorts`,
which gains `git: Git | None = None` exactly as it gained `repositories` in 2.2 — one open transaction
per request, and the frozen `ProjectPorts(...)` constructions in three test files keep compiling. A
`ProjectPorts` without a git port is the Project-only harness, so `run_clone_checks_for_project`
returns `[]` for it rather than raising, while `run_clone_check` — only ever reached through a route
that wires one — raises loudly, mirroring `embedded_repositories` and `_repos()`.

**How the token reaches git.**

```python
env = {"PATH": ..., "HOME": ..., "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
       "GIT_ASKPASS": str(self._askpass), ASKPASS_TOKEN_VAR: self._token}
subprocess.run(["git", "-c", "credential.helper=", *args], env=env, timeout=120, ...)
```

The environment is built, never inherited, so no other secret in the backend's environment reaches a
git hook. `askpass.sh` ships beside the adapter and is copied once per adapter into a 0700 temp file,
because a wheel install does not preserve an executable bit and the package directory may be
read-only. Nothing writes the token: it exists only in that one subprocess environment.

**Line `seconds` come from the `Clock`,** not from a timer inside the adapter, so a unit test can
assert them by advancing `FakeClock` from the fake `Git`. `CloneResult{seconds, bytes}` is what the
adapter measured; line 2's `output` reports it (`cloned N bytes` / `fetched`).

**The e2e fixture, in both topologies.** In CI the backend runs from source on the runner, so a
directory the test creates is a directory the backend can read; under `make up` it runs in a container
and only the volumes are shared. The helper therefore writes its bare repository under
`settings.work_dir/e2e-fixtures` and runs `git init --bare` locally when that path is writable here,
otherwise through `docker compose exec -T backend-api`. Either way the registered URL is the same
`file://{work_dir}/e2e-fixtures/{uuid}.git`, and neither branch needs a new setting, a new compose
variable or a fixture mount.

## Verification

**Commands:**
- `cd backend-api && uv run --locked pytest tests/unit -q` -- expected: green, including the real-git
  adapter tests (they need the `git` binary and no network)
- `make lint` -- expected: ruff, mypy strict, `lint-imports` (3 contracts), env contract (still 25
  fields / 31 variables), test pairs, contract drift, and the web-client lane all pass
- `make test` -- expected: green, and `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` passes
- `make openapi` -- expected: `contracts/openapi.json` and `web-client/src/api/schema.d.ts` change only
  by the two clone-check operations, the two new schemas and `RepositoryOut`'s two new fields
- `make up` then `BACKEND_API_URL=http://127.0.0.1:8000 ORCHESTRATOR_TOKEN=… make e2e-api` -- expected:
  the clone-check suite passes against the containerised stack and Schemathesis reports no 5xx; run it
  a second time with the backend started from source on the host to exercise the other fixture branch
- `make coverage` -- expected: changed lines at or above 90 %

## Auto Run Result

Status: done
Blocking condition: none

**What was implemented.** The `Git` port and its subprocess adapter, the base clone layout, and
the Clone check, end to end.

- **Domain** — `domain/ports/git.py` is new: a `runtime_checkable` `Git` Protocol
  (`ls_remote`, `base_exists`, `clone_base`, `fetch_base`, `branch_exists`, `read_file`) with
  frozen `RemoteRef`, `CloneResult` and `GitError{command, exit_code, output}`.
  `domain/entities/repository.py` gained `CloneCheckLine`, a defaulted
  `CloneCheck.lines: tuple[...] = ()`, the four line-name constants, and `hint` as a pure
  derivation of `status`, `output` and the lines.
- **Application** — `application/use_cases/clone_check.py` is new: `run_clone_check` and
  `run_clone_checks_for_project`, the four lines in order, stop-at-first-failure across lines
  1–3 with line 4 always informational, the `{work_dir}/{project.slug}/{repository.slug}/base`
  layout, and `installed_version()` — a targeted two-key manifest reader rather than a YAML
  parse, so no runtime dependency was added. `ProjectPorts` gained `git: Git | None = None`.
- **Infrastructure** — `infrastructure/git/` is new: `redact.py`, `askpass.sh` and
  `subprocess_git.py`. Every command is `git -c credential.helper= …` in a **built**
  environment (`PATH`, a private empty `HOME`, `GIT_TERMINAL_PROMPT=0`,
  `GIT_CONFIG_NOSYSTEM=1`, `GIT_ASKPASS`, and the one private token variable) under a 120 s
  timeout. The db adapter writes `lines` inside the existing JSONB value, only when non-empty,
  and reads it back with a default — so no column was added and every row 2.2 wrote still reads.
- **API** — `api/schemas/clone_check.py` and `api/routers/clone_check.py` are new;
  `RepositoryOut` gained `clone_check_lines` and `clone_check_hint` as siblings of the
  untouched four-key `clone_check`; both Project writes run the checks after the use case has
  committed; `providers.py` reads `git` off `app.state` tolerantly; `main.py` builds
  `SubprocessGit` as the fifth `create_app` keyword.

**Files changed.**

| File | What changed |
| --- | --- |
| `backend-api/src/orchestrator/domain/ports/git.py` | new — the `Git` port and its three frozen dataclasses |
| `backend-api/src/orchestrator/domain/entities/repository.py` | `CloneCheckLine`, defaulted `lines`, the line names, the pure `hint` rule |
| `backend-api/src/orchestrator/application/use_cases/clone_check.py` | new — the check, the two entry points, the manifest reader |
| `backend-api/src/orchestrator/application/use_cases/projects.py` | `ProjectPorts.git` |
| `backend-api/src/orchestrator/infrastructure/git/redact.py` | new — the one function every path out of the adapter goes through |
| `backend-api/src/orchestrator/infrastructure/git/askpass.sh` | new — how the token reaches git and nothing else |
| `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py` | new — the only module here that starts a process |
| `backend-api/src/orchestrator/infrastructure/db/repositories/repository.py` | `lines` inside the existing JSONB, written only when non-empty |
| `backend-api/src/orchestrator/api/schemas/clone_check.py` | new — `CloneCheckLineOut`, `CloneCheckResultOut` |
| `backend-api/src/orchestrator/api/schemas/projects.py` | `RepositoryOut.clone_check_lines`, `.clone_check_hint` |
| `backend-api/src/orchestrator/api/routers/clone_check.py` | new — `POST` and `GET /repositories/{id}/clone-check` |
| `backend-api/src/orchestrator/api/routers/projects.py` | both writes check every Repository after committing |
| `backend-api/src/orchestrator/api/providers.py` | reads the git adapter off `app.state` tolerantly |
| `backend-api/src/orchestrator/main.py` | builds `SubprocessGit`; fifth `create_app` keyword |
| `backend-api/tests/unit/fakes/git.py` | new — `FakeGit`, the only double for this port |
| `backend-api/tests/unit/test_*.py` (8 new modules) | the TDD suites for the port, entity, use cases, adapter, redaction, storage, schemas, router |
| `backend-api/tests/unit/test_backend_image_git.py` | new — asserts the runtime image installs `git` |
| `backend-api/tests/e2e/test_clone_check.py` | new — the check against the running stack, in both topologies |
| `.github/workflows/ci.yml` | a writable `WORK_DIR` for the two `e2e-api` script steps |
| `contracts/openapi.json`, `web-client/src/api/schema.d.ts` | regenerated (AD-3) |

**Review findings.** 35 findings across four layers, deduplicated and triaged: **12 patched**
(1 high, 5 medium, 6 low), **6 deferred** (2 medium, 4 low — recorded in frontmatter
`deferred`), **17 rejected**. No `intent_gap` and no `bad_spec`: in every case the spec already
stated the invariant the code missed, so no loopback was needed and
`review_loop_iteration` stayed at 0.

The high-severity patch is the one worth knowing: only `GitError` was caught by the four steps,
so an `OSError` from `mkdir` under an unwritable `WORK_DIR`, from `tree_bytes`, or a
`FileNotFoundError` from a missing `git` binary escaped the post-commit check and answered 500
on a save that had **already committed** — breaking this story's own "a failing check never
fails the save" invariant. `OSError` is now handled exactly as `GitError` is. Two others were
correctness rather than hardening: line 3 accepted a tag or a `release/main` branch as proof
that `main` exists (the precise failure the check exists to catch), and nothing observed that
the runtime image installs `git` — removing it from the Dockerfile left every gate green while
the deployed stack would 500 on every check.

**Follow-up review recommended: true.** Patched by severity: high 1, medium 5, low 6. A high
patch alone sets this true; the score is 3 × 5 + 6 = 21, also ≥ 5.

**Verification performed** (all commands run by the workflow after the patches, not taken on
trust):

| Command | Outcome |
| --- | --- |
| `make lint` | exit 0 — ruff, mypy strict, `lint-imports` 3 contracts kept / 0 broken, env contract still **25 fields / 31 variables**, test pairs 38 modules, no contract drift, full web-client lane |
| `make test` | **1412 passed, 1 skipped** — the skip is the pre-existing empty parametrize at `tests/unit/test_makefile.py:113`, not a new one. `domain/` + `application/` at **100 % branch**, no `pragma: no cover` |
| `make openapi` | exit 0, re-export is a no-op; `/api/v1/repositories/{repository_id}/clone-check` declares both `get` and `post`, each with a 401 in `application/problem+json` |
| `make e2e-api` | **58 passed, 12 Schemathesis subtests, 0 skipped** against a freshly rebuilt containerised stack (`docker compose up -d --build --wait`), exercising the `docker compose exec` fixture branch. No 5xx |
| `make coverage` | changed lines at **99 %** (2 of 695 missing), against a 90 % floor |

**AD-5 re-confirmed independently against the live stack**, with 169 Repositories stored and 38
carrying a failed check whose real git output is persisted: `GITHUB_TOKEN`'s value appears in no
file under `/work`, in no `.git/config`, in no remote URL, in no container log line, in no
stored `clone_check` (`select count(*) … where clone_check::text like '%<token>%'` → `0`), and
in no response body. Base clones carry `partialclonefilter = blob:none`.

**No frozen anchor was modified.** The diff touches no `AGENTS.md`, no `SPEC.md`, no
`stories.yaml`, and no pre-existing test file — every test file in the diff is new to this
story. `tests/unit/test_dockerfiles.py` in particular was left untouched; the image assertion
went into a new module.

**Residual risks.**

- The two `deferred` medium items are the real ones: a clone check reads a Repository, spends
  minutes in git, then writes back every mutable field from that stale snapshot (a lost update
  if the Operator edits meanwhile), and the save-time check has no request-level time budget —
  N repositories × up to four 120 s commands run inside the request holding the database
  session. Neither is reachable from this story's own gates; both want a design decision.
- The e2e fixture chooses its topology by testing whether `WORK_DIR` is writable by the test
  process. On a host that both has a writable `/work` and runs the containerised stack it would
  take the wrong branch. It never skips, so that surfaces as a failure naming both routes
  rather than a false pass.
- Two of the intent's rows — a remote refusing a real credential, and a token appearing in real
  git output — are necessarily proved against local `file://` transport and synthetic strings,
  because the unit gate must not depend on the network. The redaction itself is proved
  directly; what is not proved end to end is an authenticated remote refusing this instance.
- `.env`'s `GITHUB_TOKEN` in this environment is a 13-character placeholder, so the AD-5 sweep
  above is a real absence check but not a check against a realistic high-entropy token; the
  unit suite covers that case directly.
