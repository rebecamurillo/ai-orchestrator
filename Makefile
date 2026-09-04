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

.PHONY: lint test coverage e2e-api e2e-ui images openapi up down logs

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

## images — build both container images without starting anything
## `make up` builds them too, but only as a side effect of running the stack; this is the
## gate that proves a Dockerfile still builds, on a runner with no ports to bind
images:
	docker compose build

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
