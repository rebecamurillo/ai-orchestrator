# Test Automation Summary — orchestrator-initiative-steps / epic-6-package

Generated: 2026-11-24. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-6-package/SPEC.md` (relative to the hub).
Stories: 1–3 (through commit `27f2f9d9`).
Previous summary (epic-5-step-close): in git history at `e7f0c149`.

Framework: pytest + httpx (`backend-api/tests/e2e`, the `make e2e-api` gate). The epic changes no UI;
its contract changes are backend operations plus the regenerated `schema.d.ts`. No Playwright test
is added.

The stories' own tests are unit tests over the shared fakes. The new module proves the same behaviour
on the running stack: real HTTP, Postgres, Alembic, the real `Git` adapter reading a bare origin,
`POST /runs` and pre-flight, and the MCP endpoint. No existing test file was touched and no shipped
template is read or named. Every package name (`e2e-pkg-<hex>`) and template name is fresh, and every
origin is a new bare repository the module writes. The origin is written through the container first
(as `talking_origin` does), so the backend can always read it.

## Generated Tests

### API tests — `backend-api/tests/e2e/test_project_package.py` (44 tests)

- **CAP-1, run defaults (story 1):**
  - [x] A new project reads all five defaults `null` on create and on read.
  - [x] `PUT …/run-defaults` stores and returns the five values. A second read returns them, the
    full-replace `PUT /projects/{id}` leaves them unchanged, and an all-`null` body clears them.
  - [x] A budget of `0` or `-1` is refused 422 naming `default_budget_usd`, and nothing is stored.
  - [x] An unknown key, or an omitted key, is refused 422. An unknown project is 404.
- **CAP-2, the initiative folder (story 2):**
  - [x] A new repository reads `initiatives`. `PUT …/initiative-folder` stores and returns
    `specs/initiatives`.
  - [x] `""`, `/abs`, `a/../b`, `a/` and `a//b` are each refused 422, and the folder stays as it was.
    An unknown repository is 404.
  - [x] With a root template that declares `initiative_folder`:
    - an omitted input is stored on the created Run (`/runs/{id}/detail` → `run.inputs`) as
      `initiatives`;
    - `initiatives/snake` is kept as given;
    - `docs/initiative`, `initiatives/../x`, `initiatives//a` and `3` are each refused 422 with the
      exact reason, and the project lists no Run. Pre-flight reports the same `plan_error.reason`
      with `start_allowed: false`.
  - [x] After the folder changes to `specs/work`, an omitted input binds `specs/work` and
    `initiatives` is refused.
  - [x] A template that declares no `initiative_folder` input gets none bound.
- **CAP-3, the package install (story 3):**
  - [x] A valid fixture package installs. The fixture is `spec` (interactive: two `conversation` rows
    and a `spec-gate` row) plus `merge` (interactive, no conversation row).
    - The answer carries `sha`, `name`, the hub `repository` block, `gate` and `status_map`.
    - `spec` reads `shown_as: workflow` with steps
      `[conversation, conversation, automatic gate]`, and each step's skill, persona, file and
      `writes` are exact. `merge` reads `shown_as: step`.
    - `GET …/package` returns the same payload. `GET /templates/{name}.spec/1` reads the stored text
      through one path segment.
  - [x] Installing again at the same sha keeps the record id and stores no new version.
  - [x] 13 malformed packages are each refused 422 naming the file and the exact reason. Nothing is
    stored: no record, and no `{name}.spec` or `{name}.merge` version. The cases:
    - in `package.yaml`: an unknown key, `Bad_Name`, an empty sequence, a duplicate workflow, a `..`
      template path, an unknown shipped name, a word in both `pass` and `fail`, no spec-gate row,
      and the `finished` status word;
    - in a template file: a missing file, a template that fails `judge_text`, a `name:` that differs
      from the stem, and a spec-gate row missing a gate word.
  - [x] Two templates with the stem `spec` (`a/`, `b/`) are refused with the exact reason.
  - [x] A missing `package.yaml` reads `file not found`, and a `../pkg` path is refused 422.
  - [x] A ref the remote lacks is 409 naming it. A repository of another project is 404.
  - [x] The same origin and path installs on two projects. A different package of the same name is
    409 naming a holding project, and nothing is stored.
  - [x] `DELETE` answers 204. Afterwards `GET` and a second `DELETE` are 404, and every template
    version stays.
  - [x] `GET`, `PUT` and `DELETE …/package`, `PUT …/run-defaults` and `PUT …/initiative-folder` all
    need the bearer (401).
- **CAP-4, the MCP tools:**
  - [x] `tools/list` holds the five tools. `set_run_defaults`, `set_initiative_folder`,
    `install_package`, `read_package` and `remove_package` each reach their operation over
    `POST /mcp`, and the effect is read back over REST.

Not covered end to end (unit tests only):
- A shipped-name sequence entry on the happy path. The stack's only shipped templates are the
  repository's `templates/*.yaml`, which no test may name (hard rule 6). Only the refusal of an
  unknown shipped name is covered here.
- A new sha storing the next version (needs a second commit pushed to the origin mid-test).
- The tool-set order and the 28-operation allow-list (`test_mcp_allow_list.py`, `test_mcp_endpoint.py`).
- The migrations' downgrades.

## Results

### Defect found: story 2's migration breaks start-up on Postgres

`backend-api/alembic/versions/0046_repository_initiative_folder.py` declares
`revision = "0046_repository_initiative_folder"`, which is 33 characters. `alembic_version.version_num`
is `varchar(32)`, so the backend exits 1 at the migrate step of start-up:

```
sqlalchemy.exc.DataError: (psycopg.errors.StringDataRightTruncation) value too long for type character varying(32)
[SQL: UPDATE public.alembic_version SET version_num='0046_repository_initiative_folder' WHERE public.alembic_version.version_num = '0045_project_run_defaults']
```

This blocks `make e2e`, `make up` and any upgrade of a running instance to this branch. The unit
migration tests do not catch it. The fix is a shorter revision id in `0046_…` and in `0047`'s
`down_revision`. It is not applied here: this run generates tests only.

### Run of the new module

The new module could only run with that id shortened. It ran from a scratch git worktree of
`27f2f9d9` with `revision = "0046_repo_initiative_folder"` in `0046` and `0047`, against the
disposable `aio-e2e` stack (`docker compose -p aio-e2e`, `.env.e2e`). Both the scratch worktree and
the stack were destroyed afterwards. The member tree is unchanged apart from the new test file.

- `test_project_package.py`: **44 passed**, twice in a row against the same stack (re-runnable).
- `test_migrations.py`, `test_projects.py`, `test_repositories.py` (unchanged, on the same stack):
  passed.
- `test_mcp_setup_path.py` (unchanged): **1 failed**. This is environmental and predates this epic.
  `Fixtures.make` tries the host route first; on this machine the host can write `/work`, but the
  backend container cannot see what it writes there, so the clone check reads `fatal: … does not
  appear to be a git repository`. `test_project_package.py` avoids this by writing through the
  container first.

### Environment notes (not test changes)

- The host `backend-api/.venv` was moved aside during the image build and restored right after.
  `.dockerignore` still excludes only a root-level `.venv`.

## Coverage

- SPEC capabilities with an e2e test: CAP-1, CAP-2, CAP-3, CAP-4 (4 of 4).
- Endpoints, all 5 new operations: `PUT /projects/{id}/run-defaults`,
  `PUT /repositories/{id}/initiative-folder`, and `PUT`, `GET` and `DELETE /projects/{id}/package`.
  Also exercised through the changed behaviour: `POST /runs`, `POST /runs/preflight`,
  `PUT /projects/{id}`, `GET /templates/{name}/{version}` and `POST /mcp`.
- UI features: none in scope.

## Next Steps

- Shorten the `0046` revision id (and `0047`'s `down_revision`), then run the full `make e2e`.
- Make `Fixtures.make` try the container first, as `talking_origin` and `package_origin` do.
- Exclude `**/.venv` in `.dockerignore`.
