---
story: "9-1"
epic: 9
title: The gateway and tracing switches
requirements: [NFR-7, NFR-8, AR-20]
binds: [AD-5, AD-11, AD-20]
---

# Story 9.1 — The gateway and tracing switches

As the Operator,
I want a blank `LITELLM_BASE_URL` or `LANGFUSE_BASE_URL` to mean "this instance does not use that service",
So that I can run the orchestrator on a laptop with my own harness login and no host services, without editing code or inventing a second configuration file.

## Scope

**In:** `infrastructure/settings.py` — two derived properties, the validators that refuse a half-configured service, and the start-up line that names what is off; the `.env.example` comments that document the mode.
**Out:** every behaviour the switches select. The `Tracer` factory is 9-2, the `Gateway` factory is 9-3, the harness environment is 9-4, the scripts are 9-5, the runbook and the real Run are 9-6. This story changes what `Settings` *answers*, and nothing that reads it.

## Binding rules (inlined)

- **Blank is the switch; unset is still a refusal.** `litellm_base_url` and `langfuse_base_url` keep their current declarations — required, no default — so an environment that never mentions them fails to bind exactly as it does today, naming the field. A value of `""` (or whitespace only) binds and means *off*. This is what keeps `scripts/harness/*.sh` able to refuse on a scrubbed environment, which `tests/unit/test_harness_scripts.py::test_configure_refuses_with_nothing_configured` requires.
- **Two properties, one source of truth each.**

      @property
      def gateway_enabled(self) -> bool: return bool(self.litellm_base_url.strip())
      @property
      def tracing_enabled(self) -> bool: return bool(self.langfuse_base_url.strip())

  No `*_ENABLED` variable is added. A second declaration of the same fact can disagree with the first, and there is no state in which the disagreement is right.
- **A half-configured service is refused at start-up**, the way `_covers_every_harness` already refuses a half-filled `READINESS_MODELS`: a non-blank `litellm_base_url` with a blank `litellm_api_key`; a non-blank `langfuse_base_url` with a blank `langfuse_public_key`, `langfuse_secret_key` or `langfuse_project_id`. The message names the base URL and the blank field, and says which mode each choice selects. `litellm_spend_key` is **not** in that list — it reads `/spend/logs/v2` and an instance may hold a model key without an admin one; a blank spend key with a live Gateway degrades the spend query exactly as it does today.
- **Off means the other values are ignored, not forbidden.** An Operator turning the Gateway off blanks one line; the key lines may keep whatever they held. Nothing in this system reads them while the service is off.
- **One start-up line per disabled service**, through the existing structlog logger, at `warning`: `gateway disabled` / `tracing disabled`, each with the consequence stated in the event's own fields (`spend=provisional`, `traces=absent`) — a fact, never an apology and never a reassurance (PRD NFR-8). No value of any credential is logged, blank or not (hard rule 5).
- **The AD-20 contract does not move.** No variable is added or removed, so `scripts/check_env_contract.py` and `tests/unit/test_env_contract.py` are untouched in both directions. `.env.example` keeps `LITELLM_BASE_URL=http://host.docker.internal:4000` and `LANGFUSE_BASE_URL=http://host.docker.internal:3000` as the shipped default — both services on — and gains comments that state: blank disables, unset refuses, what is lost, and that `local` needs the Gateway (9-4 enforces that).

## Acceptance criteria

**Given** the committed `.env.example` environment
**When** `Settings()` binds
**Then** `gateway_enabled` and `tracing_enabled` are both true, and no start-up line is emitted.

**Given** `LITELLM_BASE_URL=""` (and `LANGFUSE_BASE_URL` intact)
**When** `Settings()` binds
**Then** it succeeds, `gateway_enabled` is false, `tracing_enabled` is true, and one `warning` line reads `gateway disabled`; and the same holds mirrored for a blank `LANGFUSE_BASE_URL`.

**Given** `LITELLM_BASE_URL` set to whitespace only
**When** `Settings()` binds
**Then** `gateway_enabled` is false — a value that looks like a URL is the only thing that turns the service on.

**Given** `LITELLM_BASE_URL` *deleted* from the environment
**When** `Settings()` binds
**Then** it raises `ValidationError` naming `litellm_base_url`; and the same for `LANGFUSE_BASE_URL`.

**Given** a non-blank `LITELLM_BASE_URL` and a blank `LITELLM_API_KEY`
**When** `Settings()` binds
**Then** it raises, and the message names both variables and states that blanking the base URL is how the Gateway is turned off; **and** the three Langfuse equivalents (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PROJECT_ID`) each raise the same way.

**Given** both base URLs blank and every key blank
**When** `Settings()` binds
**Then** it succeeds with both properties false and two `warning` lines, and no line contains a credential value.

## Implementation notes

- New test file: `backend-api/tests/unit/test_optional_services_settings.py`. The `env` fixture in `tests/unit/conftest.py` builds the environment from `.env.example`, so use `monkeypatch.setenv(..., "")` for the blank cases and `monkeypatch.delenv` for the unset ones.
- The validators are a `model_validator(mode="after")` — two fields are compared, which a `field_validator` cannot see.
- Emit the start-up lines where `main.py` already binds `Settings` for the serving process, once per process, not from the properties (a property that logs would fire on every read).
- `SecretStr("")` binds and `get_secret_value()` returns `""`; nothing needs a new type.

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-20 (configuration is the environment), AD-5 (one credential), AD-11 (spend and tracing). `backend-api/src/orchestrator/infrastructure/settings.py` — `_covers_every_harness` is the precedent for refusing a half-filled setting, and `orch_test_mode` / `litellm_spend_match` are the precedent for a field whose default must not disturb an existing `.env`. PRD NFR-7 (host services), NFR-8 (product copy states facts).
