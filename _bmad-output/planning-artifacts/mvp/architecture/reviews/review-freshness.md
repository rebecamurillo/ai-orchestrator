# Freshness / verification review — ARCHITECTURE-SPINE.md

Reviewed 2026-09-02 against PyPI, npm, Docker Hub, GitHub releases and the live vendor docs. Scope: the spine's Stack table, the four `research/*.md` files it cites, and `deliverables/scripts/harness/{_common,claude,codex,opencode}.sh`.

Verdict key: **VERIFIED** (matches the web today) · **VERIFIED (source)** (confirmed in vendor source code, not in user docs) · **CONTRADICTED** (web says otherwise) · **UNSOURCED** (asserted in the spine/scripts with no research citation; checked here) · **UNVERIFIABLE** (could not confirm either way; needs a day-1 test).

---

## 1. Contradicted / high-risk

### 1.1 Alembic pin is stale
- **Claim:** Stack table `Alembic 1.17.1`; `research/backend.md` "alembic 1.17.1 … verified 2026-09-02".
- **Verdict:** CONTRADICTED. PyPI latest is **1.19.1** (2026-08-08). Two minor releases missed on the research's own "verified today" date, so the research pass was not a live lookup for this row.
- **URL:** https://pypi.org/pypi/alembic/json
- **Fix:** Pin `alembic==1.19.1` in the spine and `research/backend.md`; re-run the PyPI lookup for the whole table before build (script below already does this).

### 1.2 Codex `-c` override for `langfuse_tags` will fail to parse
- **Claim:** `codex.sh` comment: adapter passes `-c model_providers.litellm.http_headers.langfuse_tags='["run:<id>","story:<id>",…]'`.
- **Verdict:** CONTRADICTED. `--config` values "are parsed as TOML … If the value can't be parsed as TOML, Codex treats it as a string." A `[...]` value parses as a TOML **array**, but `model_providers.<id>.http_headers` is `map<string,string>`, so the override is rejected at config load. A bare UUID happens to fall back to string, but only by luck.
- **URL:** https://learn.chatgpt.com/docs/config-file/config-advanced (section "Config overrides from the CLI") · https://learn.chatgpt.com/docs/config-file/config-reference (`model_providers.<id>.http_headers map<string,string>`)
- **Fix:** Emit every header override as a quoted TOML string: `-c 'model_providers.litellm.http_headers.langfuse_tags="[\"run:<id>\",…]"'` and `-c 'model_providers.litellm.http_headers.langfuse_session_id="<run_id>"'`. Same for `otel.span_attributes.run.id`. Add a doctor check that runs `codex exec` with the real override string once.

### 1.3 Codex sandbox inside the hardened container is not reality-checked
- **Claim:** `codex.sh` writes `sandbox_mode = "workspace-write"`; the spine's compose runs `non-root, cap_drop ALL, no-new-privileges`.
- **Verdict:** UNSOURCED → high risk. Official docs: "Linux uses bwrap plus seccomp by default … When you run Linux in a containerized environment such as Docker, the sandbox may not work if the host or container configuration blocks the namespace, setuid bwrap, or seccomp operations that Codex needs. In that case, configure your Docker container to provide the isolation you need, then run codex with `--sandbox danger-full-access` (or `--dangerously-bypass-approvals-and-sandbox`) inside the container." bwrap needs `clone(CLONE_NEWUSER)`, which `cap_drop ALL` + `no-new-privileges` is very likely to block. Additionally, `workspace-write` "keeps network access turned off unless you enable it" (`[sandbox_workspace_write] network_access = true`), so `npm install` / test runs launched by the agent would have no network even if the sandbox did start.
- **URL:** https://developers.openai.com/codex/agent-approvals-security
- **Fix:** Decide explicitly in AD-10/AD-14: the container is the sandbox → `sandbox_mode = "danger-full-access"` (or the CLI flag) and drop the inner sandbox, **or** keep `workspace-write` + `network_access = true` and make the readiness run (AD-10) prove bwrap works under the compose hardening flags. Record the decision in `codex.sh` and `research/backend.md`.

### 1.4 `Gateway.spend(run_id)` "sums spend logs by the `run:` tag" has no verified LiteLLM API behind it
- **Claim:** AD-11: "`Gateway.spend(run_id) -> Decimal` sums spend logs by the `run:` tag"; `x-litellm-tags` / `x-litellm-session-id` "for spend logs".
- **Verdict:** UNSOURCED / UNVERIFIABLE. Verified: `x-litellm-tags` is "a comma separated list" landing in `request_tags` of `LiteLLM_SpendLogs`, and `x-litellm-session-id` lands in the `session_id` column. Not verified: any public endpoint that returns spend filtered by tag. `/spend/logs` filters by key/user/request id/date (no tag filter documented); the tag breakdowns in `spend_management_endpoints.py` live under `/spend/report`, which is gated on `premium_user` in source. `research/tracing.md` itself marks the session-id mapping UNVERIFIED.
- **URL:** https://docs.litellm.ai/docs/proxy/request_headers · https://docs.litellm.ai/docs/proxy/request_tags · https://docs.litellm.ai/docs/proxy/cost_tracking · https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/proxy/spend_tracking/spend_management_endpoints.py (`/spend/report` → `premium_user` check)
- **Fix:** Pick one mechanism and verify it day 1: (a) `/spend/logs?user_id=<run_id>` with `x-litellm-end-user-id: <run_id>` (documented filter), (b) query `LiteLLM_SpendLogs` directly (`session_id = run_id` or `request_tags @> '["run:…"]'`) since LiteLLM's Postgres is on the same host, or (c) sum Langfuse generation costs by `session.id` through the Langfuse API. Update AD-11 with the chosen one and its URL.

### 1.5 LiteLLM OTel v2 needs `LITELLM_OTEL_V2=true`
- **Claim:** AD-20 / `research/tracing.md`: host LiteLLM uses the `langfuse_otel` callback (`litellm_settings.callbacks: ["langfuse_otel"]`, env `LANGFUSE_PUBLIC_KEY/SECRET_KEY`, `LANGFUSE_OTEL_HOST|LANGFUSE_HOST`).
- **Verdict:** CONTRADICTED (incomplete). The cited page's "Getting started" says: "Set `LITELLM_OTEL_V2=true` in the proxy environment, then pick a destination below." Every example on the page includes that variable; the research omits it.
- **URL:** https://docs.litellm.ai/docs/observability/opentelemetry_v2
- **Fix:** Add `LITELLM_OTEL_V2=true` to `host/README.md` / `host/litellm.config.yaml` env and to `research/tracing.md`.

### 1.6 `@langfuse/opencode-observability-plugin@latest` is the only unpinned runtime dependency, and its enabling flag is scheduled for removal
- **Claim:** `opencode.sh` writes `"plugin": ["@langfuse/opencode-observability-plugin@latest"]` + `"experimental": { "openTelemetry": true }`.
- **Verdict:** VERIFIED today (Langfuse docs prescribe exactly this; live schema `https://opencode.ai/config.json` has `experimental.openTelemetry: boolean — "Enable OpenTelemetry spans for AI SDK calls"`), but two freshness risks: npm latest is **0.3.0** (2026-08-20) and every other pin in the spine is exact; and OpenCode's v2 spec marks `experimental.openTelemetry` "remove — Do not port". `OPENCODE_VERSION` is pinned so this does not break the image, but it does bound how long `opencode.sh` stays valid.
- **URL:** https://langfuse.com/integrations/developer-tools/opencode · https://registry.npmjs.org/@langfuse/opencode-observability-plugin · https://raw.githubusercontent.com/anomalyco/opencode/dev/specs/v2/config.md (row `experimental.openTelemetry`)
- **Fix:** Pin `@langfuse/opencode-observability-plugin@0.3.0`, add `LANGFUSE_OPENCODE_PLUGIN_VERSION` to `.env.example`; note in Deferred that the OpenCode v2 upgrade replaces the plugin path.

### 1.7 PostgreSQL 17 is asserted, not researched
- **Claim:** Stack `PostgreSQL 17`; diagram `PostgreSQL 17`.
- **Verdict:** UNSOURCED. None of the four research files mentions a Postgres major. Both images exist: `postgres:17` and `postgres:18` (18.6, 2026-08-26). 18 has been GA since 2025-09; DBOS/psycopg have no stated upper bound.
- **URL:** https://hub.docker.com/v2/repositories/library/postgres/tags/17 · https://hub.docker.com/v2/repositories/library/postgres/tags/18
- **Fix:** Either pin `postgres:18` (current stable) or keep 17 with a one-line reason in the spine and a source in `research/backend.md`.

### 1.8 `opencode.sh` says "no --auto flag" — there is one
- **Claim:** `opencode.sh` comment: "Auto-approval is config-driven: no --auto flag."
- **Verdict:** CONTRADICTED (minor). `opencode run --auto`: "Auto-approve permissions that are not explicitly denied." The config-driven `permission` map the script uses is also valid, so nothing breaks; the comment is wrong.
- **URL:** https://opencode.ai/docs/cli/
- **Fix:** Correct the comment; optionally pass `--auto` as belt-and-braces for the readiness run.

---

## 2. Stack table — row by row

Live lookups 2026-09-02 (PyPI / npm / Docker Hub / GitHub). "Research" = the version in `research/*.md`.

| Row | Spine | Research (URL present?) | Live today | Verdict |
| --- | --- | --- | --- | --- |
| Python | 3.14 | 3.14.7 (no URL) | 3.14.7 | VERIFIED |
| uv | 0.12.9 | 0.12.9 (docs.astral.sh URL) | 0.12.9 (PyPI + ghcr) | VERIFIED |
| FastAPI | 0.141.1 | 0.141.1 | 0.141.1 | VERIFIED |
| Pydantic | 2.13.5 | 2.13.5 | 2.13.5 | VERIFIED |
| pydantic-settings | 2.x | not pinned | **2.15.0** (2026-08-07) | UNSOURCED → pin `2.15.0` |
| SQLAlchemy | 2.0.52 | 2.0.52 | 2.0.52 | VERIFIED |
| psycopg | 3.3.5 | 3.3.5 | 3.3.5 | VERIFIED |
| Alembic | 1.17.1 | 1.17.1 | **1.19.1** | CONTRADICTED (§1.1) |
| dbos | 2.31.0 | 2.31.0 (docs URLs) | 2.31.0 | VERIFIED |
| langfuse SDK | 4.15.1 | 4.15.1 | 4.15.1 | VERIFIED |
| structlog | 26.1.0 | 26.1.0 | 26.1.0 | VERIFIED |
| PyYAML | 6.0.3 | 6.0.3 | 6.0.3 | VERIFIED |
| cryptography | 50.0.1 | 50.0.1 | 50.0.1; `Fernet`/`MultiFernet.rotate()` documented, no deprecation | VERIFIED — https://cryptography.io/en/latest/fernet/ |
| pytest | 9.1.1 | 9.1.1 | 9.1.1 | VERIFIED |
| pytest-asyncio | 1.4.0 | 1.4.0 | 1.4.0 | VERIFIED |
| pytest-cov | latest | not pinned | **7.1.0** (2026-03-21) | UNSOURCED → pin `7.1.0` |
| httpx | 0.28.1 | 0.28.1 | 0.28.1 (2024-12) | VERIFIED |
| schemathesis | 4.25.2 | 4.25.2 (URL) | 4.25.2 | VERIFIED |
| ruff | 0.16.5 | 0.16.5 | 0.16.5 | VERIFIED |
| mypy | 2.3.1 | 2.3.1 | 2.3.1 | VERIFIED |
| import-linter | 2.14 | 2.14 (URL) | 2.14 | VERIFIED |
| Node.js | 24 LTS | 24 Active LTS (nodejs.org URL) | v24.20.0 "Krypton" LTS; v26.8.1 is Current | VERIFIED (24 stays Active LTS until 2026-10, then Maintenance to 2028-04) |
| pnpm | 11.25.0 | 11.25.0 | 11.25.0 | VERIFIED |
| Astro | 7.2.10 | 7.2.10 (docs URLs) | 7.2.10 | VERIFIED |
| @astrojs/node | 11.1.5 | 11.1.5 | 11.1.5 | VERIFIED |
| @astrojs/react | 6.0.5 | 6.0.5 | 6.0.5 | VERIFIED |
| React | 19.2.8 | 19.2.8 | 19.2.8 | VERIFIED |
| nanostores | 1.5.2 | 1.5.2 | 1.5.2 | VERIFIED |
| @nanostores/react | 1.1.0 | 1.1.0 (recipe URL) | 1.1.0 (2026-03-16) | VERIFIED — https://registry.npmjs.org/@nanostores/react |
| openapi-typescript | 7.13.0 | 7.13.0 (URL) | 7.13.0 | VERIFIED |
| openapi-fetch | 0.17.0 | 0.17.0 | 0.17.0 | VERIFIED |
| @codemirror/state / view / lang-yaml | 6.7.2 / 6.43.10 / 6.1.3 | same | same | VERIFIED |
| @dagrejs/dagre | 3.1.1 | 3.1.1 (URL) | 3.1.1 | VERIFIED |
| Vitest | 4.1.11 | 4.1.11 | 4.1.11 | VERIFIED |
| @playwright/test | 1.62.1 | 1.62.1 | 1.62.1 | VERIFIED |
| PostgreSQL | 17 | — | 17 and 18 both published | UNSOURCED (§1.7) |
| LiteLLM (host) | 1.99.0 | 1.99.0 | 1.99.0 (`requires_python <3.15` — host only, fine) | VERIFIED |
| Langfuse (host) | v4.27.0 | v4.27.0 | v4.27.0 (2026-09-01) | VERIFIED |
| bmad-method | 6.11.0 | 6.11.0 (docs URL) | 6.11.0 (npm + GitHub release 2026-08-10) | VERIFIED |
| Claude Code | 2.1.258 | 2.1.258 | 2.1.258 (2026-09-01) | VERIFIED |
| Codex CLI | 0.152.1 | 0.152.1 | 0.152.1 (2026-09-01) | VERIFIED |
| OpenCode | 1.18.26 | 1.18.26 | 1.18.26 (2026-09-01) | VERIFIED |
| `python:3.14-slim-trixie` | — | named (uv docs URL) | tag exists (2026-09-01) | VERIFIED — https://hub.docker.com/v2/repositories/library/python/tags/?name=3.14-slim |
| `node:24-bookworm-slim` | — | named, "UNVERIFIED script name" for NodeSource | tag exists (2026-08-27); `node:24-trixie-slim` also exists | VERIFIED; minor: prefer `24-trixie-slim` to match the python base |

Other stack-adjacent checks requested:
- **`uuid.uuid7()`** — VERIFIED: "Generate a time-based UUID according to RFC 9562 §5.7 … Added in version 3.14" (uuid6/7/8 all new in 3.14). https://docs.python.org/3.14/library/uuid.html . Not cited in research → add.
- **`astro check` package** — `@astrojs/check` **0.9.10** (2026-07-27) exists on npm; Astro's CLI reference does not name the package on the `astro check` section (UNVERIFIABLE from docs, well-known from the install prompt). Add `@astrojs/check` + `typescript` to the stack table so `make lint` is reproducible. https://registry.npmjs.org/@astrojs/check · https://docs.astro.build/en/reference/cli-reference/#astro-check

---

## 3. Harness scripts — flag/key by flag/key

### 3.1 `claude.sh`
| Item | Verdict | URL |
| --- | --- | --- |
| `~/.claude/settings.json` `"env": {…}` block applies to every session | VERIFIED ("An `env` block inside a settings file is an ordinary key"; examples on env-vars and gateway pages) | https://code.claude.com/docs/en/settings · https://code.claude.com/docs/en/env-vars |
| `DISABLE_AUTOUPDATER=1` | VERIFIED ("Set to 1 to disable automatic background updates … Use DISABLE_UPDATES to block both") | https://code.claude.com/docs/en/env-vars |
| `CLAUDE_CODE_ENABLE_TELEMETRY=1` + `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER=otlp` | VERIFIED ("To enable [tracing], set both … then set OTEL_TRACES_EXPORTER") | https://code.claude.com/docs/en/monitoring-usage |
| `OTEL_METRICS_EXPORTER=none`, `OTEL_LOGS_EXPORTER=none` | VERIFIED ("Use `none` to disable") | same |
| `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`, `OTEL_EXPORTER_OTLP_ENDPOINT=<langfuse>/api/public/otel`, `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic …,x-langfuse-ingestion-version=4` | VERIFIED (standard OTLP env; Langfuse: HTTP/protobuf or JSON, no gRPC; Basic `pk:sk`; `x-langfuse-ingestion-version: 4` recommended — "without this header … delayed by up to 10 minutes") | https://langfuse.com/integrations/native/opentelemetry |
| `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`; `claude -p` reads inbound `TRACEPARENT`/`TRACESTATE` | VERIFIED ("In Agent SDK and non-interactive sessions started with -p, Claude Code also reads TRACEPARENT and TRACESTATE from its own environment") | https://code.claude.com/docs/en/monitoring-usage |
| `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_CONTENT` only when `log_prompt_content` | VERIFIED; note docs: "Set it in your shell, user settings, or managed settings. Ignored in project and local settings" — the adapter passes it via env, fine | https://code.claude.com/docs/en/env-vars |
| `ANTHROPIC_AUTH_TOKEN` (Bearer), `ANTHROPIC_BASE_URL`, `ANTHROPIC_CUSTOM_HEADERS` newline-separated (v2.1.227+) | VERIFIED | https://code.claude.com/docs/en/env-vars · https://code.claude.com/docs/en/llm-gateway-connect |
| Invocation `claude -p --session-id <uuid> --permission-mode dontAsk --allowedTools … --disallowedTools "mcp__*" --output-format json --max-budget-usd <n>` | VERIFIED — all flags present; `dontAsk` is a listed mode; `"mcp__*"` "removes every MCP tool"; `--max-budget-usd` is print-mode only and counts subagents. Not in research → add. | https://code.claude.com/docs/en/cli-reference |
| Skill discovery `~/.claude/skills` (not `.agents/skills`) | VERIFIED (`.agents/skills` absent from Claude skills doc) | https://code.claude.com/docs/en/skills |

### 3.2 `codex.sh`
| Item | Verdict | URL |
| --- | --- | --- |
| `approval_policy = "never"` | VERIFIED (`untrusted \| on-request \| never \| { granular = … }`; "use … never for non-interactive runs") | https://learn.chatgpt.com/docs/config-file/config-reference |
| `sandbox_mode = "workspace-write"` | VERIFIED value; **container behaviour and network default UNSOURCED** (§1.3) | same · https://developers.openai.com/codex/agent-approvals-security |
| `model_provider = "litellm"`, `[model_providers.litellm] base_url / env_key / wire_api = "responses"` | VERIFIED ("responses is the only supported value") | config-reference |
| `http_headers` / `env_http_headers` static maps | VERIFIED (`map<string,string>`) | config-reference · config-advanced |
| `[otel] environment, log_user_prompt, metrics_exporter = "none"` | VERIFIED | config-reference |
| `trace_exporter = { otlp-http = { endpoint, protocol = "binary", headers = {…} } }` inline-table shape | VERIFIED (source): `OtelExporterKind` is `#[serde(rename_all = "kebab-case")]` externally-tagged enum with `OtlpHttp { endpoint, headers, protocol, tls }`; docs show the same shape for `exporter = { otlp-http = { endpoint = ".../v1/logs", protocol = "binary", headers = {…} }}`. The research's "`trace_exporter = "otlp-http"` **and** `[otel.trace_exporter.otlp-http]`" wording would be a TOML key redefinition — the script's form is the correct one. | https://raw.githubusercontent.com/openai/codex/main/codex-rs/config/src/types.rs · https://learn.chatgpt.com/docs/config-file/config-advanced |
| endpoint ends in `/v1/traces` | VERIFIED (source): provider calls `.with_endpoint(endpoint)` as-is, no path appended; docs example uses a full `/v1/logs` URL for the log exporter | https://raw.githubusercontent.com/openai/codex/main/codex-rs/otel/src/provider.rs |
| `[otel.span_attributes]` static map | VERIFIED (source) — `OtelConfigToml.span_attributes: BTreeMap<String,String>` + README example; **absent from the config reference page** | https://raw.githubusercontent.com/openai/codex/main/codex-rs/otel/README.md · https://raw.githubusercontent.com/openai/codex/main/codex-rs/core/src/config/otel.rs |
| `-c key=value` dotted overrides | VERIFIED ("Keys can use dot notation … values are parsed as TOML") — **but see §1.2** for the array value | config-advanced |
| Inbound `TRACEPARENT` honoured by `codex exec` | VERIFIED (source, still undocumented): `exec/src/lib.rs` `if let Some(context) = traceparent_context_from_env() { set_parent_from_context(&exec_span, context) }`; `trace_context.rs` reads env `TRACEPARENT` | https://raw.githubusercontent.com/openai/codex/main/codex-rs/exec/src/lib.rs · …/otel/src/trace_context.rs |
| Invocation `codex exec --json -C <dir> -m <model> -o <file>`; session id from `thread.started` | VERIFIED (source): `--json` (alias `experimental-json`), `-o/--output-last-message`, `-C/--cd` global, `model` global; `ThreadStartedEvent { thread_id }` serialised as `"thread.started"`. Not in research → add. | https://raw.githubusercontent.com/openai/codex/main/codex-rs/exec/src/cli.rs · …/exec/src/exec_events.rs |
| Skills `$HOME/.agents/skills` + `$CWD/.agents/skills` + parents + repo root | VERIFIED | https://developers.openai.com/codex/skills |
| `features.multi_agent` (Open at handoff 4) | VERIFIED exists, "stable; on by default" | config-reference |

### 3.3 `opencode.sh`
| Item | Verdict | URL |
| --- | --- | --- |
| `~/.config/opencode/opencode.json`; `OPENCODE_CONFIG`; `OPENCODE_CONFIG_CONTENT` merged over files | VERIFIED ("Configuration files are merged together … Later configs override earlier ones only for conflicting keys") | https://opencode.ai/docs/config/ |
| `"plugin": ["@langfuse/opencode-observability-plugin@latest"]` + `"experimental": {"openTelemetry": true}` coexistence | VERIFIED (exact Langfuse recipe; schema has `experimental.openTelemetry`) — pin risk §1.6 | https://langfuse.com/integrations/developer-tools/opencode · https://opencode.ai/config.json |
| Plugin env `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASEURL`, `LANGFUSE_USER_ID`, `LANGFUSE_ENVIRONMENT` | VERIFIED (spelling `LANGFUSE_BASEURL` confirmed) | Langfuse page above |
| `provider.litellm = { npm: "@ai-sdk/openai-compatible", options: { baseURL, apiKey: "{env:LITELLM_API_KEY}" }, models }` | VERIFIED (provider docs) | https://opencode.ai/docs/providers/ |
| `permission: { edit: "allow", bash: "allow", webfetch: "deny" }` | VERIFIED (keys `edit`, `bash`, `webfetch` …; values `allow/ask/deny`) | https://opencode.ai/docs/permissions/ |
| Model naming `litellm/<model>` | VERIFIED (`provider/model`) | https://opencode.ai/docs/config/ · https://opencode.ai/docs/cli/ |
| `opencode run --format json --dir <worktree> -m …` | VERIFIED (`--format default\|json`, `--dir`, `-m provider/model`, `-s/--session`, `-c/--continue`) | https://opencode.ai/docs/cli/ |
| "no --auto flag" | CONTRADICTED (§1.8) | same |
| Skill dirs `~/.config/opencode/skills`, `~/.claude/skills`, `~/.agents/skills`, project equivalents | VERIFIED | https://opencode.ai/docs/skills/ |

### 3.4 `_common.sh`
| Item | Verdict | URL |
| --- | --- | --- |
| `npx bmad-method@6.11.0 install --yes --modules bmm --tools <t> --directory <dir>` | VERIFIED (installer source: `--directory <path>`, `--modules`, `--tools`, `--list-tools`, `--yes` via `--help`) | https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/main/tools/installer/commands/install.js · https://docs.bmad-method.org/start/install-bmad/ |
| `claude-code → .claude/skills`, `codex`/`opencode → .agents/skills` | PARTIALLY VERIFIED: installer source references `.agents/skills` as "the platform's skill install directory"; the exact per-tool mapping is only printed by `--list-tools` (docs page does not enumerate). Keep the `doctor` check. | https://raw.githubusercontent.com/bmad-code-org/BMAD-METHOD/main/tools/installer/ide/_config-driven.js |
| BMAD Node >=20.12, uv needed by skills, per-project only | VERIFIED (npm `engines.node >=20.12.0`; docs: "uv is required by skills that render or run Python") | https://registry.npmjs.org/bmad-method/6.11.0 |
| `curl … ${LITELLM_BASE_URL}/v1/models` doctor | VERIFIED (OpenAI-compatible proxy; also `/v1/responses` documented for Codex `wire_api = "responses"`) | https://docs.litellm.ai/docs/response_api |

---

## 4. Research-file claims re-checked (DBOS, tracing)

| Claim | Verdict | URL |
| --- | --- | --- |
| `Queue(...)` deprecated → `DBOS.register_queue(name, global_concurrency, worker_concurrency, partition_concurrency, …)` | VERIFIED ("The Queue(...) constructor … is deprecated") | https://docs.dbos.dev/python/reference/queues |
| `SetEnqueueOptions(queue_partition_key=…)`; partition limits per partition, global limits across | VERIFIED | same |
| `DBOS.listen_queues([...])` before launch | VERIFIED ("You must call DBOS.listen_queues before DBOS is launched") | https://docs.dbos.dev/python/tutorials/queue-tutorial (Explicit Queue Listening) |
| `@DBOS.scheduled` deprecated → `DBOS.create_schedule(schedule_name=, workflow_fn=, schedule=)` | VERIFIED | https://docs.dbos.dev/python/tutorials/scheduled-workflows |
| `SQLAlchemyDatasource.create(url)`, `ds.sql_session()` | VERIFIED | https://docs.dbos.dev/python/reference/datasources |
| `dbos_system_schema` default `dbos`; `application_version`; `run_admin_server` default False (deprecated); no `fastapi=` kwarg | VERIFIED (research's UNVERIFIED on `fastapi=` resolves to: not in the reference) | https://docs.dbos.dev/python/reference/configuration |
| `DBOS.step_id: int` exists; equality with `operation_outputs.function_id` | still UNVERIFIED (docs: `list_workflow_steps` ordered by `function_id`; `fork_workflow` "input step ID must match the function_id") — Open at handoff 2 stands | https://docs.dbos.dev/python/reference/contexts |
| Langfuse `create_trace_id(seed=)` deterministic; `propagate_attributes(session_id=, tags=…)` | VERIFIED | https://langfuse.com/docs/observability/sdk/python/instrumentation |
| LiteLLM `langfuse_*` request headers → metadata → `session.id`/tags under `langfuse_otel` | VERIFIED (source): `LangfuseOtelLogger._extract_langfuse_metadata` "Enriches it with any langfuse_* request-header params via … add_metadata_from_header"; mapping `session_id → SESSION_ID`, `tags → TAGS`. **Docs citation in research is wrong**: the `opentelemetry_v2` page does not document these headers; the legacy `langfuse_integration` page does (`'langfuse_tags: ["tag1","tag2"]'` JSON-array string). | https://raw.githubusercontent.com/BerriAI/litellm/main/litellm/integrations/langfuse/langfuse_otel.py · https://docs.litellm.ai/docs/observability/langfuse_integration |
| LiteLLM honours inbound `traceparent`; `OTEL_IGNORE_CONTEXT_PROPAGATION=true` disables | VERIFIED | https://docs.litellm.ai/docs/observability/opentelemetry_v2 |
| `LANGFUSE_HOST` or `LANGFUSE_OTEL_HOST` | VERIFIED; plus `LITELLM_OTEL_V2=true` (§1.5) | same |
| `x-litellm-tags` comma list; `x-litellm-session-id` → spend-log `session_id` | VERIFIED | https://docs.litellm.ai/docs/proxy/request_headers |
| Langfuse OTLP endpoint `/api/public/otel` (+`/v1/traces`), Basic auth, no gRPC | VERIFIED | https://langfuse.com/integrations/native/opentelemetry |

---

## 5. Spine statements with no research source (c)

Checked here; each either verified above or listed as a fix:
1. PostgreSQL 17 — §1.7.
2. `Gateway.spend(run_id)` by tag — §1.4.
3. Codex sandbox inside compose hardening; `network_access` — §1.3.
4. `--max-budget-usd`, `--permission-mode dontAsk`, `--disallowedTools "mcp__*"`, `--session-id` — verified now (§3.1); add to `research/backend.md`.
5. `DISABLE_AUTOUPDATER` — verified now (§3.1).
6. `codex exec --json -o`, `thread.started` — verified now (§3.2).
7. `opencode run --format json --dir` — verified now (§3.3).
8. `uuid.uuid7()` — verified now (§2).
9. `@astrojs/check` for `astro check` — exists; add to stack (§2).
10. `pydantic-settings 2.x`, `pytest-cov latest` — pin (§2).
11. `LITELLM_OTEL_V2` — §1.5.
12. `@langfuse/opencode-observability-plugin` version — §1.6.
13. Docker base `node:24-bookworm-slim` copied into a trixie image — works (older glibc → newer), but `node:24-trixie-slim` exists; minor.
14. `ANTHROPIC_CUSTOM_HEADERS` carrying `langfuse_tags` as a JSON-array string — header value contains `"` and `[`; docs only forbid characters "an HTTP header can't carry" (curly quotes, zero-width space), so ASCII JSON is fine. VERIFIED by reading the rule; test day 1.

## 6. Reproducible version check

```bash
for p in pydantic-settings pytest-cov alembic; do curl -fsS https://pypi.org/pypi/$p/json | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["info"]["name"],d["info"]["version"])'; done
curl -fsS https://registry.npmjs.org/@langfuse/opencode-observability-plugin | python3 -c 'import sys,json;print(json.load(sys.stdin)["dist-tags"]["latest"])'
curl -fsS "https://hub.docker.com/v2/repositories/library/postgres/tags/18" | python3 -c 'import sys,json;print(json.load(sys.stdin)["name"])'
```
Run this (extended to every row) as `make lint`'s "stack freshness" step or at least before the first build.
