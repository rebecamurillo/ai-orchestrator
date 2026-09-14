---
title: 'The gateway and tracing switches'
type: 'feature'
created: '2026-09-13'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** `Settings` treats both `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` as unconditionally required with no off-path, so an Operator who wants to run without the host services cannot start the system at all, and the degraded-mode semantics (provisional spend, absent traces) are undocumented.

**Approach:** Derive two boolean properties from the existing fields — blank base URL means the service is off, unset still refuses — add a model validator that refuses a half-configured service at bind time, and emit one structured `warning` line per disabled service in `main()`. Update `.env.example` comments to document the mode. No new variable, no new field, no other reader changes.

## Boundaries & Constraints

**Always:**
- `gateway_enabled = bool(litellm_base_url.strip())`, `tracing_enabled = bool(langfuse_base_url.strip())` — exact property bodies as specified in the brief; no `*_ENABLED` variable
- Blank base URL with non-blank peer fields binds and succeeds; only a non-blank base URL with a blank key field raises
- `litellm_spend_key` is NOT in the half-config validator — a blank spend key with a live gateway is today's degraded spend path, not a refusal
- Start-up lines via `structlog` at `warning`, with `spend="provisional"` / `traces="absent"` as event fields; emitted in `main()` once per process, never from the properties themselves
- No credential value in any log record, blank or not (hard rule 5)
- AD-20: no new variable added; `.env.example` comments-only change on two existing lines
- Anchors are read-only: existing test files (`test_harness_scripts.py`, `test_harness_env.py`, `test_api_providers_tracing.py`, `test_dbos_startup_tracing.py`, `test_env_contract.py`) must not be edited

**Block If:**
- Any required field name or behavior diverges from the brief's verbatim property bodies or the stated error message format

**Never:**
- Add a `*_ENABLED` environment variable — blank base URL is the only switch
- Log any credential value (blank or non-blank)
- Edit existing test files
- Change `HARNESS_ENV_CONTRACT` names or `.env.example` variable names

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Default (both enabled) | `.env.example` values intact | `gateway_enabled=True`, `tracing_enabled=True`, no warning lines | No error |
| Gateway off | `LITELLM_BASE_URL=""` | `gateway_enabled=False`, `tracing_enabled=True`, one `"gateway disabled"` warning with `spend="provisional"` | No error |
| Tracing off | `LANGFUSE_BASE_URL=""` | `tracing_enabled=False`, `gateway_enabled=True`, one `"tracing disabled"` warning with `traces="absent"` | No error |
| Both off | Both blank, all keys blank | Both properties `False`, two warning lines, no credential key in any record | No error |
| Whitespace URL | `LITELLM_BASE_URL="   "` | `gateway_enabled=False` | No error |
| URL deleted | `LITELLM_BASE_URL` absent from env | `ValidationError` naming `litellm_base_url` | Pydantic required-field error |
| Half-config gateway | Non-blank `LITELLM_BASE_URL`, blank `LITELLM_API_KEY` | `ValidationError` naming both fields and stating blank-the-URL as the off-switch | Model validator raises |
| Half-config tracing (public key) | Non-blank `LANGFUSE_BASE_URL`, blank `LANGFUSE_PUBLIC_KEY` | `ValidationError` naming both fields | Model validator raises |
| Half-config tracing (secret key) | Non-blank `LANGFUSE_BASE_URL`, blank `LANGFUSE_SECRET_KEY` | `ValidationError` naming both fields | Model validator raises |
| Half-config tracing (project id) | Non-blank `LANGFUSE_BASE_URL`, blank `LANGFUSE_PROJECT_ID` | `ValidationError` naming both fields | Model validator raises |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/infrastructure/settings.py:203-211` -- `gateway_enabled` (line 204-206) and `tracing_enabled` (line 209-211) properties on `Settings`; properties are in the `# ── derived flags` section with a note that they are not fields and have no `.env.example` line
- `backend-api/src/orchestrator/infrastructure/settings.py:215-246` -- `_validate_service_config` model_validator (mode="after"); refuses non-blank base URL paired with blank key for gateway (`litellm_api_key`) and for tracing (`langfuse_public_key`, `langfuse_secret_key`, `langfuse_project_id`); `litellm_spend_key` intentionally excluded
- `backend-api/src/orchestrator/infrastructure/settings.py:248-266` -- `_covers_every_harness` field_validator (precedent for refusing half-filled settings at bind time)
- `backend-api/src/orchestrator/main.py:331-341` -- `main()` function; `Settings()` is bound at line 333; structured warnings emitted at lines 338-341 after `configure_logging` is called
- `backend-api/tests/unit/conftest.py` -- `env` fixture builds environment from `.env.example`; tests use `monkeypatch.setenv` for blank cases and `monkeypatch.delenv` for unset ones
- `backend-api/tests/unit/test_optional_services_settings.py` -- new test file (story 9-1); covers all ACs including credential-leak check on structured log output
- `.env.example:46` -- `LITELLM_BASE_URL` line; inline comment documents blank-disables, unset-refuses, and that local harness needs the Gateway
- `.env.example:53` -- `LANGFUSE_BASE_URL` line; inline comment documents blank-disables, tracing off means `cost.trace_url` is null

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_optional_services_settings.py` -- Create: one test per AC row covering `gateway_enabled`/`tracing_enabled` property values, `ValidationError` messages, and `main()` structured warning events with no credential leak; use `env` fixture + `monkeypatch.setenv`/`delenv`; stub `uvicorn.run` for the `main()` tests (TDD: tests first, all failing before the implementation steps below)
- `backend-api/src/orchestrator/infrastructure/settings.py` -- Add: `gateway_enabled` and `tracing_enabled` properties in the `# ── derived flags` comment section; add `_validate_service_config` model_validator refusing half-config (non-blank URL + blank required key) with a message naming both fields and stating the off-switch; `litellm_spend_key` excluded from the check
- `backend-api/src/orchestrator/main.py` -- Add: in `main()`, after `configure_logging`, emit `log.warning("gateway disabled", spend="provisional")` if `not settings.gateway_enabled` and `log.warning("tracing disabled", traces="absent")` if `not settings.tracing_enabled`
- `.env.example` -- Add: inline comments on `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` lines documenting the three modes (blank=off, unset=refuse, what is lost) and the local-harness dependency on the Gateway

**Acceptance Criteria:**
- Given the `.env.example` environment, when `Settings()` binds, then `gateway_enabled` and `tracing_enabled` are both `True` and no start-up warning is emitted
- Given `LITELLM_BASE_URL=""` (Langfuse intact), when `Settings()` binds, then it succeeds, `gateway_enabled` is `False`, `tracing_enabled` is `True`, and exactly one `warning` record with `event="gateway disabled"` and `spend="provisional"` is emitted by `main()`
- Given `LANGFUSE_BASE_URL=""` (LiteLLM intact), when `Settings()` binds, then it succeeds, `tracing_enabled` is `False`, `gateway_enabled` is `True`, and exactly one `warning` record with `event="tracing disabled"` and `traces="absent"` is emitted by `main()`
- Given `LITELLM_BASE_URL="   "` (whitespace only), when `Settings()` binds, then `gateway_enabled` is `False`
- Given `LITELLM_BASE_URL` deleted from environment, when `Settings()` binds, then it raises `ValidationError` with `litellm_base_url` in the message; same for `LANGFUSE_BASE_URL`
- Given non-blank `LITELLM_BASE_URL` and blank `LITELLM_API_KEY`, when `Settings()` binds, then it raises `ValidationError` naming both fields and the word "blank"; each of the three Langfuse key fields raises identically when its base URL is non-blank
- Given both URLs blank and all key fields blank, when `main()` runs, then both warning lines are emitted and no structured log record contains a credential field name as a key

## Spec Change Log

## Review Triage Log

## Design Notes

`SecretStr("")` binds without error and `get_secret_value()` returns `""` — the half-config validator compares `get_secret_value().strip()` to empty, which is why a blank key with a non-blank URL still triggers the refusal. No new type is needed.

The validator is `mode="after"` because it compares two sibling fields (`langfuse_base_url` against `langfuse_public_key`, etc.); a `field_validator` runs per-field and cannot see peers.

Properties are not fields: they have no entry in `model_fields`, no line in `.env.example`, and no entry in `HARNESS_ENV_CONTRACT`. The `# ── derived flags (not fields — no line in .env.example, not in model_fields) ──` comment block in `settings.py` marks this distinction explicitly.

Previous run context (operator-supplied): a prior attempt halted with blocking condition `spec rejected`. If a git commit error occurs during implementation, report the full error output for the Operator to investigate.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff, mypy, import-linter, and env-contract violations
- `make test` -- expected: all pytest and vitest tests green, including `test_optional_services_settings.py`

## Auto Run Result

Status: ready-for-dev
