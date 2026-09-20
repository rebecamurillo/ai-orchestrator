# Two-tier configuration contract: boot on MUST-HAVE secrets only, default everything else

## Context

Today `Settings` (backend-api/src/orchestrator/infrastructure/settings.py) makes ~35 env
fields required and the compose files fail-close (`${VAR:?}`) on every reference. That
design made every later-added setting a breaking change for every existing `.env` — which
is exactly how the operator's dev stack crash-looped on 2026-09-20 (`HARNESS_SCRIPTS_DIR`
added as required; stale `.env` refused). The Operator has ruled (in conversation,
2026-09-20): **the app must start with only MUST-HAVE variables; every other setting gets
a default and env is the override.** This declaration is the hard-rule-1(b) basis for
every test revision below; each revised test cites it.

Tiering:
- **MUST-HAVE (refuse to start)** — Settings: `ORCHESTRATOR_TOKEN`,
  `ORCHESTRATOR_SECRET_KEY`, `DATABASE_URL`, `GITHUB_TOKEN`. Stack-level (compose `:?`):
  those plus `ORCHESTRATOR_SESSION_SECRET`, `POSTGRES_PASSWORD` (and `IMAGE_TAG` in
  deploy).
- **CONDITIONALLY REQUIRED** — `LITELLM_API_KEY`+`LITELLM_SPEND_KEY` when
  `LITELLM_BASE_URL` is non-blank; `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`/`PROJECT_ID` when
  `LANGFUSE_BASE_URL` is non-blank. The existing `_validate_service_config`
  (settings.py:220-251) already implements this — keep it unchanged.
- **OPTIONAL (code default = today's `.env.example` value)** — everything else.
  `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` default to `""` = integration off.

Key design win from exploration: **no Dockerfile changes at all.** If Settings defaults
are the container paths (`/app/scripts/harness`, `/app/templates`, `/work`,
`/home/agent`) and the version pins (whose only Python reader is `db/seed.py:49-51`),
the image boots with zero non-secret env. This entirely sidesteps
`test_dockerfiles.py::test_no_harness_version_is_re_pinned_in_a_dockerfile` (which
forbids version literals in Dockerfiles) — no revision of that anchor needed. The harness
shell scripts already carry their own `: "${VAR:=default}"` pins.

Existing two-tier precedent to imitate: `host/docker-compose.yml` +
`test_host_compose.py::test_every_secret_the_file_reads_fails_closed` (`:?` on a named
secret list only, `:-default` elsewhere; its port parser already resolves both forms).

## 1. Settings defaults (`backend-api/src/orchestrator/infrastructure/settings.py`)

Give every non-MUST-HAVE field a default equal to its current `.env.example` value:

- `dbos_application_version=1`, `max_active_runs=2`, `human_wait_seconds=2592000`,
  `worktree_retention_days=7`, the three crons, `readiness_budget_usd=Decimal("5")`,
  `readiness_models={"claude": "claude-sonnet-4-6", "codex": "gpt-5.4", "local": "local-coder"}`
  (keep `_covers_every_harness`).
- `litellm_base_url=""`, `langfuse_base_url=""` (**off by default**);
  `litellm_api_key=SecretStr("")`, `litellm_spend_key=SecretStr("")`,
  `langfuse_public_key=""`, `langfuse_secret_key=SecretStr("")`,
  `langfuse_environment="mvp"`, `langfuse_project_id=""`,
  `local_models=["local-coder","local-general"]`, `litellm_spend_match="session"` (already).
- Version pins: `bmad_version="6.11.0"`, `claude_code_version="2.1.258"`,
  `codex_version="0.152.1"`, `opencode_version="1.18.26"`,
  `langfuse_opencode_plugin_version="0.3.0"`.
- Paths: `work_dir=Path("/work")`, `agent_home=Path("/home/agent")`,
  `harness_scripts_dir=Path("/app/scripts/harness")`, `templates_dir=Path("/app/templates")`.
- Process: `log_level="info"`, `log_prompt_content_default=False`,
  `backend_api_port=8000`, `claude_subscription_auth=False`,
  `claude_allowed_tools=[...]` (current contract list), `orch_test_mode=False` (already).

Required (no default): `orchestrator_token`, `orchestrator_secret_key`, `database_url`,
`github_token`. Update the module docstring: contract is two-tier; `.env.example` remains
the full documented reference (names still checked bidirectionally by
`check_env_contract.py` — it compares names only, so it survives untouched).

**Drift guard (the mitigation that keeps "one source of truth"):** new test file
`backend-api/tests/unit/test_settings_defaults.py` asserting for every defaulted field:
code default == the parsed `.env.example` value (via `parse_env_example` from conftest),
with a named exception list `{LITELLM_BASE_URL, LANGFUSE_BASE_URL}` whose example lines
deliberately show the "on" value while the code default is off. Also assert
`Settings()` constructs successfully from exactly the four MUST-HAVE vars and nothing
else (build env with `monkeypatch`, clearing all contract names first — conftest's `env`
fixture shows the pattern), and that each of the four missing → `ValidationError` naming
the field.

## 2. Compose relaxation

**`docker-compose.yml`** — keep `:?` only for `ORCHESTRATOR_TOKEN`,
`ORCHESTRATOR_SESSION_SECRET`, `POSTGRES_PASSWORD`. Relax to `:-` with contract-equal
defaults: `POSTGRES_USER:-orchestrator`, `POSTGRES_DB:-orchestrator`,
`BACKEND_API_PORT:-8000`, `WEB_CLIENT_PORT:-4321`,
`BACKEND_API_URL:-http://backend-api:8000`, `WORK_DIR:-/work`,
`AGENT_HOME:-/home/agent`. Update the header comment (fail-closed is now the *secret*
tier's property; cite the Operator decision + date).

**`deploy/docker-compose.yml`** — same split; `:?` for the three secrets **plus
`IMAGE_TAG`** (unchanged); `BIND_ADDRESS:-127.0.0.1` already the precedent.

**Test revisions (all citing "Operator decision 2026-09-20, two-tier contract" and the
date, per hard rule 1b):**
- `test_compose_fails_closed.py` — reshape to the host-compose pattern:
  `test_every_reference_is_guarded` becomes *every reference is either `:?` or `:-`*
  (`REFERENCED == REQUIRED ∪ DEFAULTED`), plus a new pinned assertion that the `:?` set
  is **exactly** `{ORCHESTRATOR_TOKEN, ORCHESTRATOR_SESSION_SECRET, POSTGRES_PASSWORD}`
  (stronger than before: the old test never named the set). Keep the two parametrized
  refusal tests (they derive from the `:?` regex and shrink automatically). Add: every
  `:-` default equals the `.env.example` value (drift guard, parsed with the same regex
  approach as `_host_side_ports`).
- `test_compose.py` — `test_an_unset_variable_refuses…` keeps only `POSTGRES_PASSWORD`
  of the three (USER/DB move to a new "defaults to the contract value" case);
  `test_the_project_refuses_to_start_with_nothing_configured` still passes (secrets
  remain `:?`) — verify, don't touch.
- `test_compose_services.py` — `test_each_web_client_variable_fails_closed` splits:
  TOKEN + SESSION_SECRET stay `:?`; BACKEND_API_URL + WEB_CLIENT_PORT asserted as `:-`
  with contract-equal defaults. The four-variable-set test is untouched (the mapping
  keys don't change).
- `test_deploy_compose.py` / `test_deploy_env_contract.py` — mirror the same split for
  the deploy file (these are this cycle's own tests; same-commit revision with the
  declaration named).

## 3. Optional-services tests

`test_optional_services_settings.py` — the two `delenv` tests
(`test_deleted_litellm_base_url_raises_naming_field`, `…langfuse…`) pin the old
"unset refuses" behavior. Replace each with its inverse, asserting the new behavior at
least as thoroughly: unset base URL → `Settings()` constructs, `gateway_enabled` /
`tracing_enabled` is False, and the registry drops `local` (existing
`registry.py:157` behavior). Keep every blank/whitespace and half-config test unchanged
— `_validate_service_config` still refuses base-URL-without-key.

## 4. `.env.example` restructure (values unchanged, order/comments only)

Two sections: `# ── REQUIRED — the app refuses to start without these ──` (the four +
SESSION_SECRET + POSTGRES_PASSWORD block) and `# ── OPTIONAL — defaults shown; delete or
keep, the app boots either way ──` (everything else, values identical to today so the
drift-guard test passes and `test_env_example_is_sourceable.py` still sees non-empty
values). `deploy/.env.example` gets the same restructure (superset checker
`check_env_contract.py::check_deploy` is name-based — unaffected). Root README §4 and
`deploy/README.md` quickstart: show the **minimal `.env`** (deploy: `IMAGE_TAG` + 3
secrets + `DATABASE_URL`/`POSTGRES_PASSWORD` + `GITHUB_TOKEN` ≈ 7 lines), full reference
still `.env.example`. DEPLOY.md §3.3: the `comm -13` preflight note becomes advisory
("missing *optional* names now mean defaults, not refusal; the REQUIRED section is what
must exist").

## 5. Fixes that ride along

- **`scripts/local.sh` bug (found in exploration):** it never exports
  `HARNESS_SCRIPTS_DIR`, so local (mode B) probes point at `/app/scripts/harness`. Add
  `export HARNESS_SCRIPTS_DIR="$root/scripts/harness"` beside the `TEMPLATES_DIR` line.
- **`make doctor` (`scripts/install.sh` `--check` branch):** add an advisory `note` (not
  `problem`) listing contract names present in `.env.example` but absent from `.env`
  (the DEPLOY.md `comm -13` one-liner, inline) — "these will use defaults". Missing
  REQUIRED names → `problem`. No new Makefile line (stays inside install.sh; avoids the
  `test_makefile.py` 5-subgate pin).

## Untouched, deliberately

- `check_env_contract.py` + `test_env_contract.py` — name-based, both directions still
  hold: *documented* stays mandatory; *required* is now a Settings property.
- Dockerfiles, harness scripts and their pin tests (`test_harness_scripts.py`,
  `test_dockerfiles.py`) — no changes needed under this design.
- `scripts/generate-env.sh`, `.env.e2e`, `docker-compose.e2e.yml`, CI e2e path — the
  generator still writes the full contract; its 10 substituted names all remain in
  `.env.example`.
- `_validate_service_config`, `_covers_every_harness`, `_must_be_absolute` validators.
- web-client: Astro's own three required envFields are its fail-closed mechanism;
  compose still always supplies them.

## Risks

1. **Frozen-test revisions** (compose fails-closed suite, web-client `:?` params, two
   optional-services delenv tests). Mitigated by the rule itself: Operator declaration
   2026-09-20 cited in each revised test, every revision same-commit with
   equal-or-stronger replacement (the new `:?`-set-is-exactly assertion is stronger than
   the old shape).
2. **Silent misconfiguration** — a typo'd optional var name now silently means "default"
   instead of refusing. Mitigated by the `make doctor` drift note; residual risk accepted
   by the Operator's ruling (this is the intended trade).
3. **Default drift** across code / `.env.example` / compose `:-` values / harness-script
   `:=` pins. Mitigated by the two new drift-guard tests (Settings↔example,
   compose↔example); scripts↔example already pinned by `test_harness_scripts.py`.
4. **Old images + minimal env**: a consumer running `IMAGE_TAG=v0.1.0` (old Settings)
   with a new minimal `.env` will refuse to start — the minimal contract only works from
   the release that ships this change. One line in `deploy/README.md` upgrading section +
   release notes.
5. **e2e gate** constructs `Settings()` in the test process (21 call sites) — unaffected
   because `.env.e2e` remains fully populated, but run `make e2e` locally to prove it.
6. **`test_the_two_stacks_can_run_at_the_same_time`** resolves `${VAR:-default}` via
   `_host_side_ports` already — verify it against the relaxed root compose (it now takes
   the default branch for the two app ports).

## Verification

- `make lint` && `make test` green; specifically the revised compose suites and the two
  new drift-guard test files.
- Minimal-boot proof (the acceptance test of the whole change): in a scratch dir, a
  4-line env (`ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SECRET_KEY`, `DATABASE_URL`,
  `GITHUB_TOKEN`) + `Settings()` constructs in a python one-liner; then
  `docker compose config` with only TOKEN+SESSION_SECRET+POSTGRES_PASSWORD in the env
  file renders with every default visible.
- `make e2e` (disposable stack — proves the gate path end to end).
- `scripts/local.sh` smoke: mode-B env resolves `HARNESS_SCRIPTS_DIR` to the checkout.
- Commit slicing: (1) Settings defaults + settings tests; (2) compose relaxation + test
  revisions; (3) `.env.example`/deploy docs restructure + doctor note + local.sh fix.
