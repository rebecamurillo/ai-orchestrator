# ai-orchestrator — the gates that decide whether work is done (AGENTS.md "Commands").
# Targets whose tooling has not landed yet exit non-zero naming the story that brings it,
# so no gate ever passes silently.

UV ?= uv
BACKEND := backend-api
# --locked: a gate must never silently re-resolve the committed uv.lock
PYTHON_RUN := $(UV) run --locked --directory $(BACKEND)

.PHONY: lint test e2e-api e2e-ui openapi up down

## lint — ruff · mypy (strict on domain/ and application/) · import-linter · env-contract check
lint:
	$(PYTHON_RUN) ruff check . ../scripts
	$(PYTHON_RUN) ruff format --check . ../scripts
	$(PYTHON_RUN) mypy src/orchestrator/domain src/orchestrator/application
	$(PYTHON_RUN) lint-imports
	$(PYTHON_RUN) python ../scripts/check_env_contract.py

## test — backend unit tests (no Postgres, no network)
test:
	$(PYTHON_RUN) pytest tests/unit -q

## e2e-api — httpx scenarios + schemathesis against the running stack
## needs: docker compose up -d postgres, the app running, and BACKEND_API_URL + ORCHESTRATOR_TOKEN exported
e2e-api:
	$(PYTHON_RUN) pytest tests/e2e -q

## e2e-ui — playwright against astro preview
e2e-ui:
	@echo "not available until story 1.3" >&2
	@exit 1

## openapi — export contracts/openapi.json, then regenerate the web-client types
openapi:
	@echo "not available until story 1.3" >&2
	@exit 1

## up — docker compose up: web-client, backend-api, postgres
up:
	@echo "not available until story 1.6" >&2
	@exit 1

## down — stop the compose stack
down:
	@echo "not available until story 1.6" >&2
	@exit 1
