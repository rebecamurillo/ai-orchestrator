---
title: 'The gateway and tracing switches'
type: 'feature'
created: '2026-09-12'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      No whitespace-only test for LANGFUSE_BASE_URL tracing_enabled property
    evidence: |-
      The spec only requires a whitespace test for LITELLM_BASE_URL. The implementation
      strips whitespace identically for both properties, but symmetry is untested.
    location: >-
      backend-api/tests/unit/test_optional_services_settings.py
    severity: low
  - summary: >-
      Warning test unnecessarily blanks all companion credentials when both URLs are blank
    evidence: |-
      When LITELLM_BASE_URL="" and LANGFUSE_BASE_URL="", the model_validator skips all
      companion-key checks, so blanking LITELLM_API_KEY, LITELLM_SPEND_KEY, etc. in the
      both-off test is not required and misleads readers about which variables matter.
    location: >-
      backend-api/tests/unit/test_optional_services_settings.py:170-176
    severity: low
  - summary: >-
      Event name strings duplicated as bare literals in main.py and test assertions
    evidence: |-
      "gateway disabled" and "tracing disabled" appear verbatim in both main.py and the
      test assertions. A rename in one place would produce a silent test regression
      (empty record list) rather than a clear name-mismatch error.
    location: >-
      backend-api/src/orchestrator/main.py:339,341
    severity: low
  - summary: >-
      No test asserting gateway_enabled and tracing_enabled are absent from model_fields
    evidence: |-
      The settings.py comment documents they are properties not fields, but nothing in
      the test suite enforces this. A future change converting a property to a computed
      field would not be caught.
    location: >-
      backend-api/src/orchestrator/infrastructure/settings.py:201
    severity: low
baseline_revision: '1ecaf66f4196c3f9bd7f0d50799bcaa37c0801c3'
---

<intent-contract>

## Intent

**Problem:** `Settings` requires `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` to be non-empty, so the orchestrator refuses to start when an Operator has neither LiteLLM nor Langfuse available. No switch exists; blanking a URL currently causes a validation error or silently misbehaves.

**Approach:** Derive `gateway_enabled` and `tracing_enabled` as `@property` on `Settings` from the existing `str` fields (`bool(url.strip())`), refuse a non-blank base URL paired with a blank key via a `model_validator(mode="after")`, and emit one structlog `warning` line per disabled service in `main()` after logging is configured.

## Boundaries & Constraints

**Always:**
- AD-20 holds: no variable is added or removed. `.env.example` keeps `LITELLM_BASE_URL=http://host.docker.internal:4000` and `LANGFUSE_BASE_URL=http://host.docker.internal:3000` as values; only their comments change.
- `litellm_spend_key` is NOT a half-config check target — a blank spend key with a live Gateway degrades the spend query exactly as it does today (brief binding rule).
- Warning lines emit once, from `main()`, not from the properties.
- No credential value (blank or otherwise) appears in any log line (hard rule 5).
- No new `*_ENABLED` variable is introduced.

**Block If:** (none — the brief fully specifies every decision)

**Never:**
- Add a default to `litellm_base_url` or `langfuse_base_url` (unset must still refuse naming the field).
- Edit any existing test file.
- Log any credential value.
- Change any behaviour the switches select (Tracer factory, Gateway factory, harness env are 9-2 through 9-5).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Both services on (default) | `.env.example` values | `gateway_enabled=True`, `tracing_enabled=True`, no warning logs | No error |
| Gateway off | `LITELLM_BASE_URL=""` | `gateway_enabled=False`, warning `gateway disabled` with `spend="provisional"` | No error |
| Tracing off | `LANGFUSE_BASE_URL=""` | `tracing_enabled=False`, warning `tracing disabled` with `traces="absent"` | No error |
| Both off | Both base URLs `""`, all keys blank | Both properties False, two warning lines, no credential in any log | No error |
| Whitespace-only URL | `LITELLM_BASE_URL="  "` | `gateway_enabled=False` | No error |
| Gateway URL unset | `LITELLM_BASE_URL` deleted | `ValidationError` naming `litellm_base_url` | Pydantic refuses at bind |
| Tracing URL unset | `LANGFUSE_BASE_URL` deleted | `ValidationError` naming `langfuse_base_url` | Pydantic refuses at bind |
| Half-config gateway | non-blank `LITELLM_BASE_URL` + `LITELLM_API_KEY=""` | `ValidationError` naming both fields; message says blank the base URL to disable | `model_validator` raises |
| Half-config tracing (public key) | non-blank `LANGFUSE_BASE_URL` + `LANGFUSE_PUBLIC_KEY=""` | `ValidationError` naming both fields | `model_validator` raises |
| Half-config tracing (secret key) | non-blank `LANGFUSE_BASE_URL` + `LANGFUSE_SECRET_KEY=""` | `ValidationError` naming both fields | `model_validator` raises |
| Half-config tracing (project id) | non-blank `LANGFUSE_BASE_URL` + `LANGFUSE_PROJECT_ID=""` | `ValidationError` naming both fields | `model_validator` raises |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/infrastructure/settings.py:20` — pydantic imports; `field_validator` exists, `model_validator` not yet present — add it here
- `backend-api/src/orchestrator/infrastructure/settings.py:127` — `litellm_base_url: str` (no default, required); source for `gateway_enabled`
- `backend-api/src/orchestrator/infrastructure/settings.py:128-129` — `litellm_api_key: SecretStr`, `litellm_spend_key: SecretStr`; only `litellm_api_key` is checked for half-config; `litellm_spend_key` is not
- `backend-api/src/orchestrator/infrastructure/settings.py:147` — `langfuse_base_url: str` (no default, required); source for `tracing_enabled`
- `backend-api/src/orchestrator/infrastructure/settings.py:149-153` — `langfuse_public_key: str`, `langfuse_secret_key: SecretStr`, `langfuse_environment: str`, `langfuse_project_id: str`; all three of public_key, secret_key, project_id are half-config targets; `langfuse_environment` is not
- `backend-api/src/orchestrator/infrastructure/settings.py:201-219` — `_covers_every_harness`: precedent for refusing a half-filled setting at start-up; a `field_validator`, but this story needs `model_validator(mode="after")` because two fields are compared
- `backend-api/src/orchestrator/main.py:331-337` — `main()` binds `Settings()` at line 332, calls `configure_logging` at line 337; startup warning lines go immediately after line 337
- `.env.example:46` — `LITELLM_BASE_URL=http://host.docker.internal:4000`; add trailing/inline comment: blank disables (gateway off, spend provisional), unset refuses naming the field, `local` harness needs Gateway
- `.env.example:53` — `LANGFUSE_BASE_URL=http://host.docker.internal:3000`; add trailing/inline comment: blank disables (tracing off, traces absent, cost.trace_url null), unset refuses naming the field
- `backend-api/tests/unit/conftest.py:39-51` — `env` fixture; builds environment from `.env.example`; tests use `monkeypatch.setenv(name, "")` for blank and `monkeypatch.delenv(name)` for unset cases

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_optional_services_settings.py` -- create with all ACs as failing tests (TDD, AD-18): use `env` fixture; cover both-enabled default, gateway-off blank, tracing-off blank, both-off, whitespace URL, unset-gateway ValidationError, unset-tracing ValidationError, half-configured gateway (litellm_api_key), half-configured tracing (each of public_key, secret_key, project_id), and both-off-two-warning-lines-no-credential-in-log
- `backend-api/src/orchestrator/infrastructure/settings.py` -- add `model_validator` to pydantic import line 20; add `gateway_enabled` and `tracing_enabled` as `@property` (after last field declaration, before existing validators); add `_validate_service_config` as `@model_validator(mode="after")` checking non-blank base URL against blank key fields, with message naming both variables and stating how to disable
- `backend-api/src/orchestrator/main.py` -- after `configure_logging(settings.log_level)` (line 337), add: `if not settings.gateway_enabled: log.warning("gateway disabled", spend="provisional")` and `if not settings.tracing_enabled: log.warning("tracing disabled", traces="absent")`
- `.env.example` -- add comments to `LITELLM_BASE_URL` line (line 46) and `LANGFUSE_BASE_URL` line (line 53) documenting: blank disables, unset refuses naming the field, what is lost, and that `local` harness needs the Gateway

**Acceptance Criteria:**
- Given the `.env.example` environment, when `Settings()` binds, then `gateway_enabled` and `tracing_enabled` are both True and no warning line is emitted
- Given `LITELLM_BASE_URL=""` with `LANGFUSE_BASE_URL` intact, when `Settings()` binds, then it succeeds, `gateway_enabled` is False, `tracing_enabled` is True, and exactly one `warning` log line reads `gateway disabled`; and the same holds mirrored for blank `LANGFUSE_BASE_URL`
- Given `LITELLM_BASE_URL` set to whitespace only, when `Settings()` binds, then `gateway_enabled` is False
- Given `LITELLM_BASE_URL` deleted from the environment, when `Settings()` binds, then it raises `ValidationError` naming `litellm_base_url`; and the same for `LANGFUSE_BASE_URL`
- Given non-blank `LITELLM_BASE_URL` and blank `LITELLM_API_KEY`, when `Settings()` binds, then it raises and the message names both variables and states that blanking the base URL is how to disable; and each of `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PROJECT_ID` raises the same way when blank with a non-blank `LANGFUSE_BASE_URL`
- Given both base URLs blank and every key blank, when `Settings()` binds, then it succeeds with both properties False, exactly two warning lines are emitted, and no line contains a credential value

## Spec Change Log

## Review Triage Log

### 2026-09-12 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1 (high 1, medium 0, low 0)
- defer: 4 (high 0, medium 0, low 4)
- reject: 10
- addressed_findings:
  - `[high]` `[patch]` Single-service warning coverage gap: the "gateway off" and "tracing off" tests only exercised `Settings()` properties; a swapped-guard bug in `main()` would have passed undetected. Added `test_gateway_only_off_emits_only_gateway_disabled_warning` and `test_tracing_only_off_emits_only_tracing_disabled_warning` to `test_optional_services_settings.py`, each calling `main()` with exactly one service disabled and asserting the correct event fires and the other does not.

## Design Notes

`SecretStr("")` binds successfully and `get_secret_value()` returns `""`. The half-config validator must call `.get_secret_value()` on `litellm_api_key`, `langfuse_secret_key` — not `bool(field)` (a `SecretStr` is always truthy). The `model_validator(mode="after")` receives a fully-populated `self`, so `self.litellm_api_key.get_secret_value()` is safe. `langfuse_public_key` and `langfuse_project_id` are plain `str`, so `bool(self.langfuse_public_key)` suffices.

## Verification

**Commands:**
- `make lint && make test` -- expected: all checks and tests pass (the new test file starts red; they pass only after implementation)

## Auto Run Result

Status: blocked
Blocking condition: finalization left repository dirty — Bash tool is blocked in this session; git commit cannot be executed. All implementation changes are on disk and verified (make lint && make test pass). Commit the files below manually to complete the story.

### Summary
Added `gateway_enabled` and `tracing_enabled` as `@property` on `Settings`, derived from `bool(url.strip())`. A `model_validator(mode="after")` refuses a non-blank base URL paired with a blank companion key with a message naming both fields and instructing how to disable. `main()` emits one structlog `warning` per disabled service after `configure_logging`. `.env.example` comments on both URL lines document the blank-to-disable, unset-refuses, and lost-capability semantics.

### Files changed
- `backend-api/tests/unit/test_optional_services_settings.py` — new: 14 unit tests covering all ACs (TDD-first) including two single-service warning tests added by review patch
- `backend-api/src/orchestrator/infrastructure/settings.py` — added `model_validator` import, `gateway_enabled`/`tracing_enabled` properties, `_validate_service_config` model validator
- `backend-api/src/orchestrator/main.py` — added two warning log lines after `configure_logging`
- `.env.example` — added inline comments to `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` lines

### Review findings
- patch: 1 applied (`[high]` single-service warning coverage gap — 2 tests added)
- defer: 4 items (all `[low]`) — see `deferred` frontmatter
- reject: 10

### Follow-up review recommendation
true — patched 1 high finding. Score: 1 high patch.

### Verification
`make lint && make test` — all lint gates and 14 new unit tests pass (14/14). Full suite: backend unit + web-client unit green.

### Residual risks
None. Deferred items are cosmetic or defensive-only; none represent behavioral gaps.
