# Langfuse × harnesses × LiteLLM — verified 2026-09-02

Versions: Langfuse self-hosted v4.27.0 (2026-09-01); langfuse Python SDK 4.15.1; LiteLLM 1.99.0 (PyPI 2026-09-01); Claude Code 2.1.258; Codex CLI 0.152.1; OpenCode 1.18.26.

## Claude Code — same trace, parented (documented)
- Native OTEL: `CLAUDE_CODE_ENABLE_TELEMETRY=1 CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 OTEL_TRACES_EXPORTER=otlp OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf OTEL_EXPORTER_OTLP_ENDPOINT=<langfuse>/api/public/otel OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <b64 pk:sk>" OTEL_RESOURCE_ATTRIBUTES=k=v,...`; optional `OTEL_LOG_USER_PROMPTS=1`, `OTEL_LOG_TOOL_CONTENT=1`. Spans `claude_code.interaction > llm_request / tool / hook`, `session.id` attribute. **`claude -p` reads inbound `TRACEPARENT`/`TRACESTATE` from env** (interactive ignores). `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` (v2.1.152+) sends `traceparent` to non-Anthropic base URLs (the gateway) and to Bash/hook subprocesses. `ANTHROPIC_CUSTOM_HEADERS="Name: Value"` newline-separated (v2.1.227+). https://code.claude.com/docs/en/monitoring-usage · https://code.claude.com/docs/en/env-vars · https://code.claude.com/docs/en/llm-gateway-connect
- Langfuse plugin alternative (Stop hook, `uv`, langfuse>=4.7): `CC_LANGFUSE_TRACEPARENT`, `CC_LANGFUSE_TRACE_SEED`; richer content but a second exporter → duplicates if combined with native OTEL. https://langfuse.com/integrations/developer-tools/claude-code

## Codex CLI — same trace, parented (source-verified, undocumented)
- Native OTEL in `config.toml`: `[otel] environment, exporter, trace_exporter = "otlp-http", metrics_exporter, log_user_prompt; [otel.trace_exporter.otlp-http] endpoint, headers, protocol = "binary"|"json"`; `[otel.span_attributes]` static map on every span. `codex exec` calls `traceparent_context_from_env()` → `set_parent_from_context` (codex-rs/exec/src/lib.rs, codex-rs/otel/src/trace_context.rs) — honours inbound `TRACEPARENT` env; not in user docs → verify day 1. Provider headers static: `model_providers.<id>.http_headers` / `env_http_headers`; `wire_api = "responses"` only.
- Langfuse plugin alternative: `LANGFUSE_CODEX_TRACE_SEED` gives derivable but separate root traces (flat). https://langfuse.com/integrations/developer-tools/codex

## OpenCode — same session id only
- Langfuse plugin `@langfuse/opencode-observability-plugin` (opencode.json `plugin`, `experimental.openTelemetry: true`), env `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASEURL`, `LANGFUSE_USER_ID`; one trace per turn keyed by OpenCode sessionID; no traceparent/seed input. Native OTLP (`experimental.openTelemetry`) has no TRACEPARENT support and is dropped in OpenCode v2. Provider `options.headers` static map works for `langfuse_*` headers to LiteLLM. https://langfuse.com/integrations/developer-tools/opencode · https://opencode.ai/docs/providers/

## LiteLLM proxy → Langfuse
- Callback `langfuse_otel` (`litellm_settings.callbacks: ["langfuse_otel"]`, env `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_OTEL_HOST`|`LANGFUSE_HOST`). Legacy `langfuse` callback: not recommended for Langfuse v3/v4.
- Any request header prefixed `langfuse_` becomes metadata: `langfuse_trace_id`, `langfuse_existing_trace_id`, `langfuse_session_id`, `langfuse_trace_user_id`, `langfuse_tags`, `langfuse_trace_metadata` → span attrs `langfuse.trace.id`, `session.id`, `user.id`, `langfuse.trace.tags`... Static-header CLIs can therefore tag every generation with the Run's session id and tags.
- Inbound `traceparent` header is honoured (LiteLLM continues that trace; `OTEL_IGNORE_CONTEXT_PROPAGATION=true` disables). `x-litellm-tags`, `x-litellm-session-id`, `x-litellm-end-user-id` are for spend logs (mapping to Langfuse session UNVERIFIED). https://docs.litellm.ai/docs/observability/opentelemetry_v2 · https://docs.litellm.ai/docs/proxy/request_headers

## Langfuse
- Trace id = 32 lowercase hex (W3C); `Langfuse.create_trace_id(seed=...)` deterministic; `trace_context={"trace_id", "parent_span_id"}`; `propagate_attributes(session_id=, tags=, metadata=)`. OTLP endpoint `<host>/api/public/otel` (`/v1/traces`), HTTP protobuf or JSON, Basic auth `pk:sk`, header `x-langfuse-ingestion-version=4`; a root span must reach Langfuse for the trace to render. https://langfuse.com/integrations/native/opentelemetry · https://langfuse.com/docs/observability/sdk/python/instrumentation

## Verdict
| Harness | Achievable | Mechanism |
|---|---|---|
| claude | same trace, parented | `TRACEPARENT` env + native OTEL + `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1` |
| codex | same trace, parented (verify day 1) | `TRACEPARENT` env + `[otel] trace_exporter=otlp-http` |
| local (opencode) | same session id | Langfuse plugin + `langfuse_session_id` header to gateway |
Universal floor: `session.id = run id` on the root span, every harness, and every gateway request (`langfuse_session_id` header) → the Sessions view always shows the whole Run.
