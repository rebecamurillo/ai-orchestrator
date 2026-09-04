"""End-to-end suite: HTTP against a running backend-api and a running Postgres.

`make e2e-api` is the gate. Unlike `tests/unit`, everything here needs the stack up:

    docker compose up -d postgres
    uv run --locked --directory backend-api python -m orchestrator.main   # in another shell
    BACKEND_API_URL=http://localhost:8000 make e2e-api
"""
