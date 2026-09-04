---
title: 'Repository constitution and backend-api skeleton with layering gates'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: 'c2aa9cdb6a5e7ff9bfc3d14e81141b5de4be79b6'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-1-repository-constitution-and-backend-skeleton.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repository holds planning documents and the BMAD method, but no code and no gates. Every story after this one is handed to a coding agent whose work is judged by `make lint` and `make test`, and neither command exists.

**Approach:** Place the root and backend constitutions and the configuration contract at the repo root, then create `backend-api/` as a four-layer Python package — settings, structlog, `/healthz`, a `Clock` port with its fake — and wire ruff, mypy, import-linter, the env-contract check, and pytest behind `make lint` and `make test` so both run green on a fresh clone.

## Boundaries & Constraints

**Always:**
- Layering (AD-2) is declared as import-linter layer *and* forbidden contracts in `backend-api/pyproject.toml`: `domain` ← `application` ← {`api`, `infrastructure`} ← `main`; `domain` and `application` may not import `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`, `langfuse`, `git`.
- Configuration is the environment (AD-20): `infrastructure/settings.py` is the only reader of environment variables, every field has a line in root `.env.example`, and a mismatch in either direction fails `make lint`.
- Stack pins are exact in `pyproject.toml` and `backend-api/uv.lock` is committed: Python 3.14, FastAPI 0.141.1, Pydantic 2.13.5, pydantic-settings 2.15.0, structlog 26.1.0, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0, httpx 0.28.1, ruff 0.16.5, mypy 2.3.1, import-linter 2.14.
- Existing files are revised in place, never moved, renamed, or replaced. `README.md` keeps every existing section including "Setting up the BMAD method on a new machine"; `.gitignore` keeps every existing BMAD rule; `GUIDELINES.md` is not touched.
- The two `AGENTS.md` files are copied verbatim from `architecture/deliverables/`; only a path that is factually wrong may be corrected.
- Tests first (AD-18): each test module is written and fails before the module it covers exists. Unit tests use fakes in `tests/unit/fakes/`.
- structlog JSON to stdout at `LOG_LEVEL`; no `print`. No `datetime.now()` outside `infrastructure/`. Module ≤ 400 lines, function ≤ 50 lines, complexity ≤ 10.
- No real secret and no `.env` is ever committed.

**Ask First:**
- Any dependency, top-level directory, or environment variable not named by the brief or the spine.
- Any change that would make a gate pass by weakening it — loosening a ruff/mypy rule, widening an import-linter contract, adding an ignore, or skipping a test.
- Anything that would delete, move, or overwrite a file that already exists.

**Never:** database, migrations, bearer auth, any router beyond `/healthz` (1.2); web-client or the generated contract (1.3); Dockerfiles or compose (1.6); CI workflow (1.7); `DBOS.launch()` or any DBOS import (Epic 4); domain entities beyond the `Clock` port.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Health check | `GET /healthz` on the ASGI app | 200, JSON `{"status": "ok", "version": "<package version>"}` | N/A |
| OpenAPI document | `GET /openapi.json` | 200, a document whose `paths` contains `/healthz` | N/A |
| Settings parse | every variable in `.env.example` present in the environment | `Settings` instantiates; all 25 backend fields typed; `ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SECRET_KEY`, `GITHUB_TOKEN`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LANGFUSE_SECRET_KEY` are `SecretStr` | missing required variable → pydantic `ValidationError` naming it |
| Env contract drift | a `Settings` field with no line in `.env.example` | the check exits non-zero and prints the variable name | same check, opposite direction: a non-allowlisted `.env.example` variable with no field also fails |
| Forbidden import | a module under `application/` importing `sqlalchemy`, in a temporary copy of the tree | `lint-imports` exits non-zero naming the forbidden contract | the real tree stays clean — the test never writes into `backend-api/src` |
| Unavailable make target | `make e2e-ui` or `make up` before their story | exit non-zero printing `not available until story <id>` | no target may silently succeed |
| Secret redaction | a `Settings` instance repr'd or logged | secret fields render as `**********`, never the value | N/A |

</frozen-after-approval>

## Code Map

- `README.md` -- exists, 53 lines. Sections: title, summary, planning-document index table, "Setting up the BMAD method on a new machine" (prerequisites / clone+install / check / notes), "Where the work stands". **Edit in place**: add a *Running it* section; every existing section survives.
- `.gitignore` -- exists, 9 lines: a BMAD block (`_bmad/config.user.toml`, `.claude/skills/bmad-*`) and `.DS_Store`. **Append only**: Python, Node, `.env`.
- `GUIDELINES.md` -- exists, 41 KB. **Read-only. Not touched by this story.**
- `_bmad-output/planning-artifacts/mvp/architecture/deliverables/AGENTS.md` -- source for root `AGENTS.md`, copied verbatim.
- `_bmad-output/planning-artifacts/mvp/architecture/deliverables/backend-api/AGENTS.md` -- source for `backend-api/AGENTS.md`, copied verbatim. Names the layout, the ports-first rule, the commands, and the checkable limits.
- `_bmad-output/planning-artifacts/mvp/architecture/deliverables/.env.example` -- source for root `.env.example`, copied verbatim. Holds 31 variables: 25 backend-api fields plus 6 read only by compose or web-client (`ORCHESTRATOR_SESSION_SECRET`, `BACKEND_API_URL`, `WEB_CLIENT_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) — those 6 are the env-contract allowlist.
- `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` -- binding. Design Paradigm table (layer → directory → may import), AD-2, AD-18, AD-20, Stack table, Structural Seed tree, variable table.
- `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-1-repository-constitution-and-backend-skeleton.md` -- this story's complete requirements.
- No `Makefile`, `backend-api/`, `scripts/`, `contracts/`, or Python source exists yet — every path below is new.
- Verified during planning: `uv 0.12.9` at `/opt/homebrew/bin/uv`, CPython 3.14.7 installed, and all pinned versions above resolve together (39 packages).

## Tasks & Acceptance

**Execution:**

- [x] `AGENTS.md`, `backend-api/AGENTS.md` -- copy verbatim from the two `deliverables/` sources -- the constitutions are read-only anchors from this point on.
- [x] `CLAUDE.md` -- create containing `@AGENTS.md` -- Claude Code loads the same constitution.
- [x] `.env.example` -- copy verbatim from `deliverables/.env.example` -- AD-20 contract.
- [x] `.gitignore` -- append Python, Node, and `.env` rules below the existing blocks -- keeps every BMAD rule.
- [x] `README.md` -- add a *Running it* section covering the `make` targets -- every existing section preserved.
- [x] `Makefile` -- targets `lint test e2e-api e2e-ui openapi up down`; `lint`/`test` delegate into `backend-api/` and run the env-contract check; targets whose tooling arrives later exit 1 printing `not available until story <id>` -- no target silently succeeds.
- [x] `backend-api/pyproject.toml` -- pinned deps (plus `uvicorn==0.52.4`: the brief names uvicorn for `main.py`'s `__main__`, the spine Stack table carries no pin — supervisor-approved deviation), `[tool.ruff]` (line-length 100, select `E F I B UP PL C90`, `mccabe.max-complexity = 10`), `[tool.mypy]` strict on `domain`/`application`, `[tool.importlinter]` layer + forbidden contracts, `[tool.pytest.ini_options]` `asyncio_mode = auto` -- one file declares every gate.
- [x] `backend-api/tests/unit/fakes/` + `conftest.py` -- test tree and a `.env.example`-derived environment fixture -- AD-18. (Flat `tests/unit/test_*.py` per the brief's implementation notes; per-layer subdirectories arrive with the layers' first tests.)
- [x] `backend-api/tests/unit/test_clock_fake.py`, `backend-api/tests/unit/fakes/clock.py` -- fake advancing a UTC tz-aware clock -- the shared fake every later story reuses.
- [x] `backend-api/tests/unit/test_settings.py`, `test_healthz.py`, `test_layering.py`, `test_env_contract.py`, `test_makefile.py` -- written first, failing -- cover the I/O matrix rows.
- [x] `backend-api/src/orchestrator/domain/ports/clock.py` -- `Clock` Protocol, `now() -> datetime` -- no wall-clock call outside infrastructure.
- [x] `backend-api/src/orchestrator/infrastructure/settings.py` -- `Settings(BaseSettings)`, 25 typed fields, secrets as `SecretStr` -- the only env reader.
- [x] `backend-api/src/orchestrator/infrastructure/logging.py` -- structlog JSON to stdout at `LOG_LEVEL` -- no `print` anywhere.
- [x] `backend-api/src/orchestrator/main.py` -- `create_app(settings) -> FastAPI` with `/healthz`; `__main__` runs uvicorn on `BACKEND_API_PORT` -- composition root; no DBOS.
- [x] `scripts/check_env_contract.py` -- diff `Settings.model_fields` against `.env.example` both ways, allowlisting the 6 non-backend variables, exit non-zero naming each difference -- AD-20's enforcement.
- [x] `backend-api/uv.lock` -- generated by `uv lock` and committed -- reproducible gates.

**Acceptance Criteria:**

- Given a clean checkout, when `make lint` runs, then it exits 0 having run ruff check, ruff format check, mypy strict on `domain/` and `application/`, `lint-imports`, and the env-contract check.
- Given a clean checkout, when `make test` runs, then it exits 0 running pytest over `backend-api/tests/unit`.
- Given the finished story, when `git status` is compared to the pre-story tree, then `README.md` and `.gitignore` appear as modified — never deleted or recreated — `GUIDELINES.md` is unchanged, and every section previously in `README.md` is still present.
- Given `uv run --directory backend-api python -m orchestrator.main`, when `GET /healthz` is called over HTTP, then it returns 200 with `{"status": "ok", "version": "<package version>"}`.
- Given the repository, when it is searched, then no `.env` file and no real secret value is committed.

## Spec Change Log

## Verification

**Commands:**
- `make lint` / `make test` -- expected: exit 0, each sub-gate visibly run.
- `make e2e-ui`, `make up` -- expected: exit 1 printing `not available until story <id>`.
- `uv run --directory backend-api python -m orchestrator.main` then `curl -s localhost:8000/healthz`.
- `git status --porcelain` -- expected: `README.md`, `.gitignore` as ` M`; `GUIDELINES.md` absent.
- `git grep -nE '(ghp_|sk-)[A-Za-z0-9]' -- ':!*.env.example'` -- expected: no hits.

## Spec Change Log

- **Review round 1 (2026-09-03).** Three context-free reviewer layers returned 30 + 23 + 9
  findings. Nothing classified as `intent_gap` or `bad_spec`, so the code was not re-derived;
  every accepted finding was applied as a `patch` and nine were recorded in `deferred-work.md`.
  Two were reproduced before being accepted: `DATABASE_URL` typed `str` put the Postgres
  password in `repr(Settings())` while the test guarding hard rule 5 passed, and no test ran
  `make lint` or `make test` at all, so the gate could be narrowed silently. Known-bad state
  avoided: a foundation whose central deliverable — the gate — is unverified, and a redaction
  test that is name-scoped rather than value-scoped. **KEEP:** the tests-first order; the
  temp-copy strategy in `test_layering.py` that never writes to the real `src/`; the
  `.env.example`-derived `env` fixture; the `not available until story <id>` Makefile
  convention. No gate was weakened to reach green — the ruff selection was widened
  (`DTZ`, `T20`, `RUF`), `--locked` was added to every gate invocation, and `scripts/` was
  brought inside ruff's scope.

## Suggested Review Order

**The gate, and the tests that prove it runs**

- The five sub-gates and `--locked`; deleting a line here now fails a test.
  [`Makefile:13`](../../../../../../Makefile#L13)

- Reads the recipe through `make -n`; `_uv_invocations` exists because `$(UV)` expands to an absolute path, which made an earlier version of this assertion vacuous.
  [`test_makefile.py:78`](../../../../../../backend-api/tests/unit/test_makefile.py#L78)

- The AD-20 contract check: drift in three directions, one parser shared with the test fixture.
  [`check_env_contract.py:57`](../../../../../../scripts/check_env_contract.py#L57)

**Secrets (hard rule 5)**

- `DATABASE_URL` is `SecretStr` because the committed contract embeds `POSTGRES_PASSWORD` in it.
  [`settings.py:56`](../../../../../../backend-api/src/orchestrator/infrastructure/settings.py#L56)

- Value-scoped redaction: a future leaking field fails without anyone extending a name list.
  [`test_settings.py:88`](../../../../../../backend-api/tests/unit/test_settings.py#L88)

**Layering (AD-2)**

- Layer and forbidden contracts; `include_external_packages` is what lets them see `sqlalchemy`.
  [`pyproject.toml:57`](../../../../../../backend-api/pyproject.toml#L57)

- Proves the contracts fire, against a throwaway copy — the real tree stays clean.
  [`test_layering.py:77`](../../../../../../backend-api/tests/unit/test_layering.py#L77)

**Composition root and logging**

- `create_app` builds the app; `main()` fails with a named configuration error, not a traceback.
  [`main.py:36`](../../../../../../backend-api/src/orchestrator/main.py#L36)

- stdlib records routed through the same processors, so uvicorn's lines are JSON too.
  [`logging.py:36`](../../../../../../backend-api/src/orchestrator/infrastructure/logging.py#L36)

- The `Clock` port: time is injected, never read ambiently outside `infrastructure/`.
  [`clock.py:14`](../../../../../../backend-api/src/orchestrator/domain/ports/clock.py#L14)

**Supporting**

- Limits `AGENTS.md` calls checkable, actually checked: module length, no `print`, no wall clock.
  [`test_source_limits.py:32`](../../../../../../backend-api/tests/unit/test_source_limits.py#L32)

- The ignore rules read through git, so inverting the `.env.example` negation fails a test.
  [`test_gitignore.py:31`](../../../../../../backend-api/tests/unit/test_gitignore.py#L31)
