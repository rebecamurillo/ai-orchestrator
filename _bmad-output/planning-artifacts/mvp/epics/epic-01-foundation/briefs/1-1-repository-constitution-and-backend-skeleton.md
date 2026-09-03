---
story: "1-1"
epic: 1
title: Repository constitution and backend-api skeleton with layering gates
requirements: [NFR-7, NFR-9, AR-1, AR-2, AR-6, AR-22]
binds: [AD-2, AD-18, AD-20]
---

# Story 1.1 — Repository constitution and backend-api skeleton with layering gates

As the Operator who will hand every later story to a coding agent,
I want the repository to carry its constitutions, its configuration contract, and a backend-api package whose lint, type, layering, and unit-test gates already run green,
So that an agent's work can be judged by `make lint` and `make test` from the first story onward.

## Scope

**In:** root `AGENTS.md`, `CLAUDE.md`, `README.md`, `Makefile`, `.env.example`, `.gitignore`; `backend-api/` with `AGENTS.md`, `pyproject.toml`, the four-layer package, settings, logging, `/healthz`, the `Clock` port and its fake, the unit-test skeleton, and the env-contract check.
**Out:** database, auth, routers beyond `/healthz` (1.2); web-client (1.3); Docker (1.6); CI (1.7).

## Binding rules (inlined)

- **Layering (AD-2).** `src/orchestrator/domain/` imports stdlib (never `os`, `shutil`, `subprocess`) and pydantic only; `application/` imports `domain`; `api/` imports `application`, `domain`; `infrastructure/` imports `application`, `domain`; `main.py` imports everything. `domain/` and `application/` never import `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`, `langfuse`, `git`. Enforce with `import-linter` layer and forbidden contracts in `pyproject.toml`.
- **Configuration is the environment (AD-20).** `infrastructure/settings.py` (pydantic-settings) is the only reader of environment variables. Every field has a comment line in `.env.example`; a script compares the two and `make lint` fails on a missing variable.
- **Stack pins** (spine Stack table): Python 3.14, uv 0.12.9, FastAPI 0.141.1, Pydantic 2.13.5, pydantic-settings 2.15.0, structlog 26.1.0, pytest 9.1.1, pytest-asyncio 1.4.0, pytest-cov 7.1.0, ruff 0.16.5, mypy 2.3.1, import-linter 2.14. Pin exact versions in `pyproject.toml`; commit `uv.lock`.
- **Constitutions.** Copy `_bmad-output/planning-artifacts/mvp/architecture/deliverables/AGENTS.md` to the repo root and `deliverables/backend-api/AGENTS.md` to `backend-api/AGENTS.md` verbatim, then fix only paths that differ in reality. Add `CLAUDE.md` at the root containing `@AGENTS.md` so Claude Code loads the same constitution.
- **Clock port (conventions).** `domain/ports/clock.py` declares `Clock.now() -> datetime` (UTC, tz-aware); no `datetime.now()` outside `infrastructure/`. Fake in `tests/unit/fakes/clock.py`.
- **Logging.** `structlog` JSON to stdout, level from `LOG_LEVEL`; no `print`.
- **Limits** (backend AGENTS.md): module ≤ 400 lines, function ≤ 50 lines, ruff `C901` ≤ 10, `PLR0915`.

## Acceptance criteria

**Given** a fresh clone with `uv` installed
**When** I run `make lint` and `make test`
**Then** both exit 0, running ruff check + format check, mypy strict on `domain/` and `application/`, import-linter, the env-contract check, and pytest on `backend-api/tests/unit`.

**Given** a test module under `backend-api/tests/unit/` that imports `sqlalchemy` from a file placed in `src/orchestrator/application/`
**When** `uv run lint-imports` runs
**Then** it fails naming the forbidden contract (the test creates the file in a temp copy or asserts the contract config through import-linter's API; the real tree stays clean).

**Given** a new field added to `Settings` without a line in `.env.example`
**When** `make lint` runs
**Then** the env-contract check fails and names the variable.

**Given** the app started with `uv run python -m orchestrator.main`
**When** `GET /healthz` is called
**Then** it returns 200 with JSON `{"status": "ok", "version": "<package version>"}` and `GET /openapi.json` returns the OpenAPI document.

**Given** the `Settings` model
**When** it is instantiated from the variables in `.env.example`
**Then** every variable of the spine's variable table that belongs to backend-api parses into a typed field (`ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SECRET_KEY`, `DATABASE_URL`, `DBOS_APPLICATION_VERSION`, `GITHUB_TOKEN`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LOCAL_MODELS`, `MAX_ACTIVE_RUNS`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_ENVIRONMENT`, `BMAD_VERSION`, `CLAUDE_CODE_VERSION`, `CODEX_VERSION`, `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION`, `CLAUDE_ALLOWED_TOOLS`, `WORK_DIR`, `AGENT_HOME`, `LOG_PROMPT_CONTENT_DEFAULT`, `LOG_LEVEL`, `BACKEND_API_PORT`), secrets typed as `SecretStr`.

**Given** the root `Makefile`
**When** a target's tooling does not exist yet (`e2e-ui` before 1.3, `up` before 1.6)
**Then** the target exists and exits non-zero with the message `not available until story <id>`; no target silently succeeds.

## Implementation notes

- Files: `Makefile` (targets `lint test e2e-api e2e-ui openapi up down`, each delegating to `backend-api/` and `web-client/` when present), `.env.example` (copy of `deliverables/.env.example`), `.gitignore` (keep the existing BMAD rules; add Python, node, `.env`), `README.md` (three lines: what it is, `make up`, where the docs are).
- `backend-api/pyproject.toml`: `[project]` with pinned deps; `[tool.ruff]` (line length 100, select `E F I B UP PL C90`, `mccabe.max-complexity = 10`); `[tool.mypy]` strict scoped to `src/orchestrator/domain`, `src/orchestrator/application`; `[tool.importlinter]` root package `orchestrator`, contracts: layers `orchestrator.main | orchestrator.api, orchestrator.infrastructure | orchestrator.application | orchestrator.domain` and forbidden imports for `orchestrator.domain` and `orchestrator.application` listing the nine modules; `[tool.pytest.ini_options]` `asyncio_mode = auto`.
- `src/orchestrator/main.py`: `create_app(settings) -> FastAPI` with `/healthz`; `__main__` runs uvicorn on `BACKEND_API_PORT`. Keep `DBOS.launch()` out (Epic 4).
- `scripts/check_env_contract.py` at the repo root: instantiates `Settings.model_fields`, parses `.env.example` names, reports the difference (both directions; extra `.env.example` variables used only by compose or web-client are allowlisted in the script).
- Tests: `tests/unit/test_settings.py`, `tests/unit/test_healthz.py` (httpx ASGI transport), `tests/unit/test_layering.py`, `tests/unit/fakes/clock.py` + `test_clock_fake.py`.

## Verification

```bash
make lint && make test
uv run --directory backend-api python -m orchestrator.main &  # then: curl -s localhost:8000/healthz
```

## Sources for detail only

Spine: Design Paradigm table, AD-2, AD-18, AD-20, Stack, Structural Seed, variable table. PRD NFR-7, NFR-9. `deliverables/AGENTS.md`, `deliverables/backend-api/AGENTS.md`, `deliverables/.env.example`.
