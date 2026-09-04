# ai-orchestrator — the gates that decide whether work is done (AGENTS.md "Commands").
# Targets whose tooling has not landed yet exit non-zero naming the story that brings it,
# so no gate ever passes silently.

UV ?= uv
PNPM ?= pnpm
BACKEND := backend-api
WEB := web-client
# --locked: a gate must never silently re-resolve the committed uv.lock
PYTHON_RUN := $(UV) run --locked --directory $(BACKEND)
# --dir: the web-client scripts run from the repository root, with no `cd` in a recipe
NODE_RUN := $(PNPM) --dir $(WEB) run

.PHONY: lint test e2e-api e2e-ui openapi up down logs

## lint — ruff · mypy (strict on domain/ and application/) · import-linter · env-contract check
##        · contract drift · eslint · prettier --check · tsc --noEmit · astro check
lint:
	$(PYTHON_RUN) ruff check . ../scripts
	$(PYTHON_RUN) ruff format --check . ../scripts
	$(PYTHON_RUN) mypy src/orchestrator/domain src/orchestrator/application
	$(PYTHON_RUN) lint-imports
	$(PYTHON_RUN) python ../scripts/check_env_contract.py
	$(NODE_RUN) gen:api -- --check
	$(NODE_RUN) lint

## test — backend unit tests (pytest) + web-client unit tests (vitest); no Postgres, no network
test:
	$(PYTHON_RUN) pytest tests/unit -q
	$(NODE_RUN) test

## e2e-api — httpx scenarios + schemathesis against the running stack
## needs: docker compose up -d postgres, the app running, and BACKEND_API_URL + ORCHESTRATOR_TOKEN exported
e2e-api:
	$(PYTHON_RUN) pytest tests/e2e -q

## e2e-ui — playwright against the built web-client
## needs: pnpm --dir web-client exec playwright install chromium, once per machine
## the build comes first: the credential spec greps dist/ for the token
e2e-ui:
	$(NODE_RUN) build
	$(NODE_RUN) e2e

## openapi — export contracts/openapi.json, then regenerate the web-client types (AD-3)
## the exporter writes through a temporary file: `> contracts/openapi.json` would empty the
## committed contract before the export ran, and leave it empty when the export failed
openapi:
	$(PYTHON_RUN) python -m orchestrator.tools.export_openapi --output ../contracts/openapi.json
	$(NODE_RUN) gen:api

## up — docker compose up: web-client, backend-api, postgres
## needs: cp .env.example .env, filled in. --build so an edited Dockerfile is never ignored;
## -d so the acceptance commands (curl, e2e-api, compose exec) can follow it
up:
	docker compose up -d --build

## down — stop the compose stack, keeping pgdata, work and agent-home
## `docker compose down -v` would delete all three; that is a deliberate act, not a target
down:
	docker compose down

## logs — follow every service's output
logs:
	docker compose logs -f
