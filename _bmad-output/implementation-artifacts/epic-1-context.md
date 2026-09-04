# Epic 1 Context: Repository foundation, quality gates, and Operator login

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Turn an empty repository into the two-component monorepo the architecture describes, with every gate that later work will be judged by already in place and green. Every epic after this one is built unattended by coding agents, and an agent can only be trusted with a story when `make lint`, `make test`, `make e2e-api`, and `make e2e-ui` already decide "done" without a human reading the diff. The epic delivers the constitutions, the configuration contract, the layering linter, the generated API contract, the container images, the instrument-dark shell, and the Operator's token login. It is complete when a fresh clone with a filled `.env` reaches a logged-in empty Board in under 30 minutes.

## Stories

- Story 1.1: Repository constitution and backend-api skeleton with layering gates
- Story 1.2: Database, migrations, bearer auth, and API conventions
- Story 1.3: Generated contract and web-client skeleton
- Story 1.4: Design tokens and the instrument-dark shell
- Story 1.5: Operator token login
- Story 1.6: Container images and the Compose stack
- Story 1.7: CI pipeline and coverage gates

## Requirements & Constraints

- Two deployables, one browser-facing origin: web-client (Astro SSR + React islands) is the only origin the browser talks to; it reaches backend-api server-side with a bearer token. Islands never hold a backend credential.
- One credential: a single access token serves both the web login and the API bearer. Secrets are read only by the typed settings module and never appear in code, tests, logs, or fixtures.
- Configuration is the environment: both components read configuration only from environment variables through one typed settings module, and `.env.example` at the repo root lists every variable with a comment. Adding a setting without updating that file fails lint.
- The API contract is owned by the backend and generated into the web-client; hand-editing generated types is forbidden and lint fails on drift.
- Errors are RFC 9457 problem documents; lists are `{items, next_cursor}`; ids are UUIDv7; times are ISO 8601 UTC with `Z`; money is a decimal USD string.
- Tests are layered and the gates are checkable: backend unit tests use only in-memory port fakes from a shared fakes directory; e2e hits a running stack over HTTP; the web-client uses Vitest for units and Playwright against a preview server. Tests exist and fail before the implementation. Gate order is lint → unit → e2e-api → e2e-ui.
- Coverage rules: 100 % branch on domain and application rule modules; changed lines ≥ 90 %.
- Visual system: instrument-dark tokens only, monospace, radius 0, no shadows, status rendered as word tokens, at most one signal colour per card or row; a screen with nothing needing the Operator shows no amber or red.
- Copy states facts and mechanisms; it never congratulates or apologises.
- Stack versions are pinned exactly from the architecture Stack table, and lockfiles are committed.
- Existing repository files are revised in place, never moved, renamed, or replaced.

## Technical Decisions

- **Backend layering.** `domain/` (entities, value objects, status machines, port protocols) imports stdlib — never `os`, `shutil`, `subprocess` — and pydantic only. `application/` imports `domain`. `api/` and `infrastructure/` import `application` and `domain`. `main.py` is the composition root and imports everything. `domain/` and `application/` never import `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`, `langfuse`, or `git`. Enforced by import-linter layer and forbidden contracts declared in `pyproject.toml`.
- **Ports first.** A new external dependency gets a `Protocol` in `domain/ports/` and an in-memory fake under `tests/unit/fakes/` before any adapter exists. Use cases receive ports by constructor injection; the composition root is the only place adapters are instantiated. Time comes from a `Clock` port; no direct wall-clock call outside infrastructure.
- **Routes.** `/api/v1/<feature>` per feature router; `/healthz` and `/openapi.json` are unversioned. Auth is a constant-time bearer comparison applied to every versioned route.
- **Migrations** cover the application schema only; the durable engine manages its own schema. They run at container start before the engine launches.
- **Logging** is structlog JSON to stdout at a level taken from configuration; no `print`.
- **Front-end auth** is a signed HttpOnly session cookie set after a successful token login, checked by middleware on every page except the login page; unauthenticated API calls answer 401 rather than redirecting.
- **Code quality gates.** Python: ruff lint + format check, mypy strict scoped to domain and application, import-linter. TypeScript: eslint (including the restriction that only the server API modules may call `fetch`), prettier check, `tsc --noEmit`, `astro check`. Plus the environment-contract check. All of it behind one `make lint`.
- **Checkable limits.** A module is ≤ 400 lines, a function ≤ 50 lines, cyclomatic complexity ≤ 10.
- **Containers.** Two Dockerfiles and one compose file bring up web-client, backend-api, and Postgres with named volumes and hardening flags; the backend image runs as a non-root user and carries the three harness CLIs and the BMAD method at pinned versions. The model gateway and the tracing server run on the host, outside compose, and are documented rather than orchestrated.

## UX & Interaction Patterns

- One shell wraps every route: a left rail, a surface bar, and a footer readout. Every screen is reachable and renders as an empty readout before its data exists.
- Status is a word token, never a colour alone. Only deterministic or human gates may render green.
- The empty Board reads `NOTHING REGISTERED`.
- Login: a wrong token re-renders the login page with `token rejected`; a correct token sets the session cookie and redirects to the Board. Form errors re-render the page with every submitted value and print the problem detail verbatim beside the field it names — no toast, no redirect on error.
- A failed fetch renders a full-surface readout naming the failed request, with a retry control.

## Cross-Story Dependencies

- 1.1 establishes the root constitution, the Makefile gate targets, the environment contract, and the backend package with its layering gates. Every later story in every epic adds to that skeleton; Makefile targets whose tooling does not exist yet must fail loudly rather than silently pass.
- 1.2 adds the database, migrations, and bearer auth on top of 1.1's package, and turns on `make e2e-api`.
- 1.3 depends on 1.2's routes existing to export a meaningful contract, and creates the web-client that 1.4 and 1.5 build on; it turns on `make openapi` and `make e2e-ui`.
- 1.4 supplies the tokens and shell that 1.5's login page and every later screen render inside.
- 1.5 needs 1.2's bearer auth and 1.3's proxy; it completes the browser path end to end.
- 1.6 packages what 1.1–1.5 produced and is the first story where `make up` is expected to work.
- 1.7 wires the gates from all previous stories into CI in their fixed order and enforces the coverage thresholds.
- Later epics add domain tables when they need them; this epic creates no Project, Repository, Template, or Run table.
