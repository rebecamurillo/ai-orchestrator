---
id: SPEC-mvp-epic-09-optional-services
companions: []
sources:
  - ../../prd.md
  - ../../addendum.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../architecture/deliverables/.env.example
  - ../../architecture/deliverables/scripts/harness/
---

> **Canonical contract for Epic 9.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 9 — The Gateway and the tracing server are optional

## Why

The MVP was built against two host services, and both are load-bearing in a way nothing asked for. `Settings` declares `litellm_*` and `langfuse_*` with no defaults, so backend-api refuses to start when one is missing. `backend-api/docker-entrypoint.sh` runs `scripts/harness/<name>.sh configure` for all three harnesses before it serves, and `require_harness_env` refuses without `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. Every harness reaches its model through the Gateway by name: `ANTHROPIC_BASE_URL`, `model_provider = "litellm"`, `-m litellm/{model}`.

An Operator who wants to drive Claude Code on their own subscription, on a laptop, with no LiteLLM and no Langfuse in the picture, cannot start this system at all. This epic makes both services optional and makes the degraded mode legible: what still works, what is unknown, and which harness is unavailable — stated on screen and in the logs, never inferred.

The switch is the configuration that is already there. A **blank** `LITELLM_BASE_URL` turns the Gateway off; a **blank** `LANGFUSE_BASE_URL` turns tracing off. An **unset** variable stays what it is today: a refusal that names the field. No new variable is added to the AD-20 contract, and there is no second source of truth that can disagree with the first.

## Capabilities

- **CAP-1** The two switches — `Settings.gateway_enabled` / `Settings.tracing_enabled` derived from a blank base URL, the half-configured states refused at start-up, and one start-up line naming what is off. **success:** an environment whose `LITELLM_BASE_URL` is blank binds `Settings` and reports the Gateway off; the same variable unset still refuses, naming `litellm_base_url`.
- **CAP-2** Tracing off — a `NullTracer` behind the `Tracer` port, chosen by a factory, with a deterministic trace id and no Langfuse client. **success:** with tracing off no SDK client is constructed, every row executes against a schema-valid `SpanRef`, and `cost.trace_url` is `null` so the Run detail omits the trace row.
- **CAP-3** Gateway off — a `DisabledGateway` behind the `Gateway` port, answering *unknown* rather than *free*. **success:** an attempt's cost comes from the harness's own report and is flagged provisional; nothing renders a settled `$0.00` for a call that was never priced.
- **CAP-4** Harness environment off-mode — the contract keeps its names and carries blank values; no harness is handed an empty credential; `local` is unavailable without the Gateway and its pre-flight line says why. **success:** with the Gateway off, `env_for` exports no `ANTHROPIC_AUTH_TOKEN`, and pre-flight refuses `local` with `gateway disabled`.
- **CAP-5** Harness scripts off-mode — `configure` writes a config for what exists, `doctor` probes only what exists, and `install` still needs neither. **success:** with both blank, all three `configure` runs succeed and write no Gateway route and no OTLP exporter; with both unset, all three still refuse, naming the variable.
- **CAP-6** The Operator's runbook and the readout — `DEPLOY.md` and `host/README.md` state how to run without the host services and what is lost; one real Run proves it. **success:** a Story reaches `done` on an instance with both services blank, and the Run detail states the cost is provisional rather than congratulating anyone with a zero.

## Constraints

- **AD-5 holds.** No provider credential enters `Settings` or a config file. With the Gateway off, a harness authenticates from its own login in the `agent-home` volume (`claude login`, `codex login`) or from a variable the Project supplies, which is already encrypted at rest and already reaches the process. `GITHUB_TOKEN` and `LITELLM_SPEND_KEY` remain absent from every harness environment.
- **AD-10 holds.** `HARNESS_ENV_CONTRACT` does not change: the names are exported in both modes, carrying blank values when a service is off, and `scripts/harness/_common.sh` stays normative for that list.
- **AD-20 holds.** No new variable. `.env.example` keeps every line it has; only its comments change.
- **Anchors are read-only** (AGENTS.md hard rule 1). No existing test is edited; every story adds test files of its own. Four anchors shape this epic and must stay green as they are: `test_harness_scripts.py` (a scrubbed environment must still refuse, the guard must keep its literal `${NAME:?` expansions, `require_harness_env` must stay in the `configure|doctor` dispatch, `install` must stay clear of it), `test_harness_env.py` (the exported key set equals the contract plus the base names), `test_api_providers_tracing.py` / `test_dbos_startup_tracing.py` (the default environment still wires a real `LangfuseTracer`), and `test_env_contract.py` (both directions of the contract).
- **Defaults do not move.** The shipped `.env.example` configures both services, so every existing test, gate and Run behaves exactly as it does today.

## Non-goals

- No per-harness base-URL overrides, no second gateway, no direct provider endpoints in settings.
- No offline `local` harness: OpenCode's route to a host model server is the Gateway, and without it `local` is disabled rather than half-wired.
- No new pricing path. With the Gateway off, cost is the harness's own provisional figure; nothing here computes money from a model's token count.
- No change to how a Run executes: the walker, the statuses, the checkpoints and the trajectory row are untouched.

## Spine note

AD-11 makes the Gateway the source of an attempt's settled spend and Langfuse the trace sink. Running without them is a **documented degraded mode**, not a second design: spend degrades to the harness's own provisional report, budget parking is only as good as that report, `attempt_observed` answers `False`, and the trace link is absent. The SPEC states this so that an Operator choosing the mode is choosing it knowingly, and so that no later story reads a provisional zero as a fact.

## Success signal

On an instance whose `.env` has `LITELLM_BASE_URL=` and `LANGFUSE_BASE_URL=` blank: backend-api starts and logs `gateway disabled` and `tracing disabled`; New workflow offers `claude` and `codex` and refuses `local` with a reason; a Story runs to `done` through Claude Code on the Operator's own login; the Run detail shows tokens and a provisional cost with no trace row; and switching the two values back restores every figure and every link with no other change.
