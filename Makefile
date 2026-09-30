# ai-orchestrator — the gates that decide whether work is done (AGENTS.md "Commands").
# Targets whose tooling has not landed yet exit non-zero naming the story that brings it,
# so no gate ever passes silently.

UV ?= uv
PNPM ?= pnpm
# the test-pair gate imports nothing outside the standard library, so it runs on the system
# interpreter: `backend-api/tests/unit/test_makefile.py` is frozen and pins how many `uv`
# invocations the lint recipe may hold
PYTHON ?= python3
BACKEND := backend-api
WEB := web-client
# --locked: a gate must never silently re-resolve the committed uv.lock
PYTHON_RUN := $(UV) run --locked --directory $(BACKEND)
# --dir: the web-client scripts run from the repository root, with no `cd` in a recipe
NODE_RUN := $(PNPM) --dir $(WEB) run

.PHONY: install install-e2e doctor lint test coverage e2e e2e-api e2e-ui durability images openapi env up down logs host-up host-down host-logs host-doctor host-env-sync local local-backend local-web bundle push

## install — a fresh checkout to a machine the gates run on (scripts/install.sh)
## Syncs backend-api's virtualenv from uv.lock, installs web-client from pnpm-lock.yaml at
## the pinned pnpm, and writes `.env` and `.env.e2e` if they are absent. Every step is a
## no-op the second time, so this is the first line of a session, not a one-time ritual.
## What it deliberately does NOT do: install uv, Node or Docker. Those are the machine's,
## and it names the exact command for each one it finds missing rather than guessing.
install:
	./scripts/install.sh

## install-e2e — the same, plus the Playwright chromium build (~95 MB) that `make e2e-ui` needs
install-e2e:
	./scripts/install.sh --e2e

## doctor — report what is missing without installing anything; exits non-zero when the
## machine is not ready. This is the target to run before blaming a red gate on the code.
doctor:
	./scripts/install.sh --check

## lint — ruff · mypy (strict on domain/ and application/) · import-linter · env-contract check
##        · test pairs · contract drift · eslint · prettier --check · tsc --noEmit · astro check
## the web-client half of the test-pair check runs inside `pnpm lint`
lint:
	$(PYTHON_RUN) ruff check . ../scripts
	$(PYTHON_RUN) ruff format --check . ../scripts
	$(PYTHON_RUN) mypy src/orchestrator/domain src/orchestrator/application
	$(PYTHON_RUN) lint-imports
	$(PYTHON_RUN) python ../scripts/check_env_contract.py
	$(PYTHON) scripts/check_test_pairs.py
	$(NODE_RUN) gen:api -- --check
	$(NODE_RUN) lint

## test — backend unit tests (pytest) + web-client unit tests (vitest); no Postgres, no network
## coverage is measured in the same run (AD-18): the second line re-reports over the two rule
## packages alone, where 100 % branch coverage is the gate. `coverage.xml` is what `make
## coverage` reads; both it and `.coverage` are git-ignored.
test:
	$(PYTHON_RUN) pytest tests/unit -q --cov --cov-report=term-missing:skip-covered --cov-report=xml
	$(PYTHON_RUN) coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100
	$(NODE_RUN) test

## coverage — changed lines >= 90 % (AD-18), against the branch this work forks from.
## Reads the `coverage.xml` that `make test` wrote, so it runs after it, and needs the base
## branch present: `git fetch origin main` locally, `fetch-depth: 0` in CI.
DIFF_COVER_BASE ?= origin/main
coverage:
	$(PYTHON_RUN) diff-cover coverage.xml --compare-branch=$(DIFF_COVER_BASE) --fail-under=90

## e2e — the whole gate: build the aio-e2e stack, run e2e-api in it, destroy it
## This is the target to type. `make e2e-api` alone is the gate itself, and attaches to
## whatever stack is already configured — which is how the suite's Projects, fixture
## repositories and base clones end up in the database you develop against. The suite is
## right to leave them (it must pass twice against the same stack); the stack is what has to
## be disposable, so this target owns one: its own project, its own volumes, its own ports,
## and `down -v` in a trap so a failed run cleans up as thoroughly as a green one.
## `--build`, so the gate never runs yesterday's image; the layer cache makes repeats cheap.
E2E_ENV := .env.e2e
E2E_FILES := -f docker-compose.yml -f docker-compose.e2e.yml
E2E_COMPOSE := docker compose -p aio-e2e --env-file $(E2E_ENV) $(E2E_FILES)
# The gate is defined once, in `e2e-api`, and reached from here by recursion — not copied,
# which is how the two would drift. Written `$(SUBMAKE)` rather than `$(MAKE)`: make executes
# any recipe line holding the literal `$(MAKE)` even under `-n`, so a dry run of this target
# would start containers instead of printing what it would do.
SUBMAKE := $(MAKE)
e2e:
	./scripts/generate-env.sh e2e
	set -e; \
	set -a; . ./$(E2E_ENV); set +a; \
	trap '$(E2E_COMPOSE) down -v' EXIT; \
	trap 'exit 130' INT TERM; \
	$(E2E_COMPOSE) down -v; \
	$(E2E_COMPOSE) up -d --build --wait --wait-timeout 300 backend-api; \
	COMPOSE_PROJECT_NAME=aio-e2e; \
	COMPOSE_FILE=docker-compose.yml:docker-compose.e2e.yml; \
	COMPOSE_ENV_FILES=$(E2E_ENV); \
	export COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_ENV_FILES; \
	export BACKEND_API_URL="http://127.0.0.1:$$BACKEND_API_PORT"; \
	export DATABASE_URL="postgresql+psycopg://$$POSTGRES_USER:$$POSTGRES_PASSWORD@127.0.0.1:$$E2E_POSTGRES_PORT/$$POSTGRES_DB"; \
	$(SUBMAKE) e2e-api

## e2e-api — httpx scenarios + schemathesis against the running stack
## needs: a stack up, and the whole contract exported with DATABASE_URL and BACKEND_API_URL
## reachable from this machine. `make e2e` does all of that; running this target directly is
## the sharp edge it exists to blunt, so the guard refuses any database but the gate's own.
##
## E2E_MARKER is what this target selects. The default deselects `durability`, which kills and
## restarts the backend *container*: this target attaches to whatever stack is configured, and
## in CI that is a backend-api process started from source on the runner, with no container to
## kill. `make durability` sets the marker the other way round, against a stack of its own.
E2E_MARKER ?= not durability
e2e-api:
	./scripts/check_e2e_target.sh
	$(PYTHON_RUN) pytest tests/e2e -q --maxfail=3 -m "$(E2E_MARKER)"

## durability — the restart-and-orphan proof (SPEC CAP-17, FR-12, SM-4)
## The same disposable stack `make e2e` builds — its own project, its own volumes, its own
## `down -v` trap — with the marker inverted, because this gate SIGKILLs `backend-api` and
## brings it back. Reached by recursion for the reason `make e2e` reaches `e2e-api` by
## recursion: the stack is defined once, so the two cannot drift.
durability:
	$(SUBMAKE) e2e E2E_MARKER=durability

## e2e-ui — playwright against the built web-client
## needs: pnpm --dir web-client exec playwright install chromium, once per machine
## the build comes first: the credential spec greps dist/ for the token
e2e-ui:
	$(NODE_RUN) build
	$(NODE_RUN) e2e

## images — build both container images without starting anything
## `make up` builds them too, but only as a side effect of running the stack; this is the
## gate that proves a Dockerfile still builds, on a runner with no ports to bind
images:
	docker compose build

## ── the release version: one file, reused everywhere ────────────────────────
## `VERSION` at the repository root is the image tag (`ghcr.io/…/backend-api:$(TAG)`), the
## bundle's name, and what the git tag `v$(TAG)` must equal for release.yml to publish.
## Override on the command line for a one-off: `make push TAG=1.0.0-rc.2`.
TAG ?= $(shell cat VERSION)

## push — build both images for linux/amd64 and linux/arm64 and push them as :$(TAG)
## needs a `docker login ghcr.io` with a token that can write the packages (scripts/push-images.sh)
push:
	./scripts/push-images.sh $(TAG)

## bundle — the client package for one release: dist/ai-orchestrator-deploy-$(TAG).tar.gz
## deploy/ (install.sh, compose, env contract) + host/ + plugin/ + VERSION, from the working
## tree via `git ls-files`, so a filled .env can never travel. release.yml runs the same script.
bundle:
	./scripts/bundle.sh $(TAG)

## openapi — export contracts/openapi.json, then regenerate the web-client types (AD-3)
## the exporter writes through a temporary file: `> contracts/openapi.json` would empty the
## committed contract before the export ran, and leave it empty when the export failed
openapi:
	$(PYTHON_RUN) python -m orchestrator.tools.export_openapi --output ../contracts/openapi.json
	$(NODE_RUN) gen:api

## env — write the environment file of each local environment (AD-20)
## `.env` is aio-dev, the stack you develop against; `.env.e2e` is aio-e2e, which `make e2e`
## creates and destroys. Neither is ever rewritten once it exists.
env:
	./scripts/generate-env.sh

## up — docker compose up: web-client, backend-api, postgres
## needs: cp .env.example .env, filled in. --build so an edited Dockerfile is never ignored;
## -d so the acceptance commands (curl, e2e-api, compose exec) can follow it
up:
	docker compose up -d --build

## down — stop the compose stack, keeping pgdata, work and agent-home
## `docker compose down -v` would delete all three; that is a deliberate act, not a target
down:
	docker compose down

## ── local mode: run the app on this machine instead of in containers ────────
## Mode A is `make up` (everything in compose, harness CLIs in the image). Mode B is
## `make local`: postgres stays in compose, backend-api and web-client run from source as
## host processes — faster iteration, and Runs dispatch to the harness CLIs on YOUR PATH.
## The published ports are the same as `make up`'s, so the two modes cannot run at once;
## scripts/local.sh refuses a bound port and says to `make down` first.

## local — backend-api in the background, web-client in the foreground, one Ctrl-C stops both
local:
	./scripts/local.sh up

## local-backend — postgres in compose, then backend-api from source in the foreground
local-backend:
	./scripts/local.sh backend

## local-web — web-client (astro dev) from source in the foreground
local-web:
	./scripts/local.sh web

## ── the host stack: LiteLLM and Langfuse (host/docker-compose.yml) ──────────
## Separate from the product stack on purpose: different lifecycle, its own data, and it
## stays up across a `make down`. See host/README.md.
HOST_COMPOSE := docker compose -f host/docker-compose.yml --env-file host/.env

## host-up — generate host/.env if absent, then start LiteLLM and Langfuse and wait
host-up:
	./host/generate-env.sh
	$(HOST_COMPOSE) up -d --wait

## host-down — stop the host stack, keeping its volumes
## `$(HOST_COMPOSE) down -v` would drop Langfuse's traces and re-run the database init
host-down:
	$(HOST_COMPOSE) down

## host-logs — follow the host stack's output
host-logs:
	$(HOST_COMPOSE) logs -f

## host-env-sync — point the root .env at the running host stack (mints the harness key)
host-env-sync:
	./host/sync-env.sh

## host-doctor — every harness checks its gateway and its skills, inside the backend image
## this is the half of the doctor contract that needs a reachable gateway to prove
host-doctor:
	docker compose exec -T backend-api scripts/harness/claude.sh doctor
	docker compose exec -T backend-api scripts/harness/codex.sh doctor
	docker compose exec -T backend-api scripts/harness/opencode.sh doctor

## logs — follow every service's output
logs:
	docker compose logs -f
