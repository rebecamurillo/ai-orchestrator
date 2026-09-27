# AGENTS.md — backend-api

Python 3.14 · uv · FastAPI · Pydantic v2 · SQLAlchemy 2 (psycopg 3) · Alembic · DBOS 2.31 · structlog. Read the root `AGENTS.md` first.

## Layout (AD-2) — where a change goes

```text
src/orchestrator/
  domain/          entities (Run, StepRun, Attempt, TemplateVersion, Project, Repository, GateRecord, Trajectory),
                   status machines, value objects, ports/ (engine, harness, git, workspace, process, gateway, tracer, clock, repositories)
  application/     use_cases/ (create_run, plan_run [pure], apply_step_result, signal_run, preflight, projects, templates, queue, record_trajectory)
                   steps/<kind>.py (one StepExecutor per kind; registry in steps/__init__.py)
                   templates/validate.py, templates/plan.py, graph.py, rules/ (routing, budget, protected_paths)
  api/             routers/<feature>.py, schemas/ (Pydantic — the API contract), deps.py (bearer auth)
  infrastructure/  dbos/ (engine adapter + walker), db/ (SQLAlchemy models, repositories, unit of work), git/, workspace/, process/,
                   harness/<name>/adapter.py, gateway/ (LiteLLM spend), tracing/ (Langfuse), crypto/ (Fernet), settings.py
  main.py          composition root
tests/unit/fakes/  one in-memory fake per port — reuse them
tests/unit/        domain, application, api (httpx ASGI, fakes injected)
tests/e2e/         against http://backend-api:8000 — httpx scenarios + schemathesis
alembic/           migrations for schema `public` only; schema `dbos` is DBOS-managed
```

Decision rule: **business rule → `application/`; talks to the outside world → `infrastructure/`; HTTP shape → `api/`; a concept every layer names → `domain/`.** If a change needs `dbos`, `sqlalchemy`, `subprocess`, `os` or `shutil`, it is an adapter; use cases read and write worktree files only through the `Workspace` port.

## Rules specific to this component

- **Ports first.** A new external dependency gets a `Protocol` in `domain/ports/` and a fake in `tests/unit/fakes/` before an adapter. Use cases receive ports by constructor injection; `main.py` is the only place adapters are instantiated.
- **The engine is opaque** (AD-6). Only `infrastructure/dbos/` imports `dbos`. `run.engine_ref` / `attempt.engine_ref` are JSON the adapter owns. Inside the walker every side effect is a DBOS step; list files are read once per Run; `DBOS_APPLICATION_VERSION` is pinned.
- **Step kinds** (AD-9): adding a kind = one module in `application/steps/` implementing `StepExecutor.execute(ctx) -> StepResult`, one registry entry, one validator test, one graph test. No `if kind == ...` anywhere else. Kinds: `git.worktree git.sync shell agent git.commit git.push pr.link template checkpoint bmad.install`.
- **Prompts** are the template's own prose (Operator revision 2026-09-27): every sentence a harness receives is a `prompts` clause the row declares — `application/steps/agent_prompt.py::compose_prompt` only fills the runtime placeholders and joins the parts; it authors no words, and neither does any adapter (they pass prompts verbatim). `resume` is used only to retry the same row; a row never resumes another row's session.
- **Harness adapters** (AD-10): implement the `Harness` port; return `HarnessResult{session_id, exit_code, usage, log_path}`; never parse model output; build the process env with `env_for(attempt)` = exactly `HARNESS_ENV_CONTRACT` (see `scripts/harness/_common.sh`) plus Project env vars; config files under `AGENT_HOME` reference env NAMES only and are never written by an adapter. Processes start in their own process group and record `pgid` before being awaited (AD-14).
- **Tracing** (AD-11): open the attempt span through the `Tracer` port and export `TRACEPARENT`; never call `langfuse` outside `infrastructure/tracing/`.
- **Routers** are thin: parse → call one use case → map result/`ProblemDetail`. One router per feature under `/api/v1/<feature>`; signals are `POST /runs/{id}/signals`.
- **Migrations**: every model change ships with an Alembic revision; `make test` runs against a fresh schema.

## Commands

```bash
uv sync --locked
uv run pytest tests/unit -q                       # TDD loop (no Postgres, no network)
uv run ruff check . && uv run ruff format --check .
uv run mypy src/orchestrator/domain src/orchestrator/application   # strict
uv run lint-imports                                # AD-2 contract
uv run alembic upgrade head
uv run python -m orchestrator.main                 # DBOS.launch() then uvicorn
uv run python -m orchestrator.tools.export_openapi > ../contracts/openapi.json
uv run pytest tests/e2e -q                         # needs `make up`
```

## Checkable limits

- A module is ≤ 400 lines; a function ≤ 50 lines (ruff `PLR0915`, `C901` ≤ 10).
- `domain/` and `application/` have 100% branch coverage on status transitions and routing rules (`rules/`, `steps/agent.py`).
- No `print`; log with `structlog` bound to `run_id`, `path`, `attempt`.
