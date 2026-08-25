# Addendum — AI Orchestrator

Technical detail, rejected alternatives, and mechanism decisions that belong downstream (architecture, solution design) rather than in the PRD. Researched 2026-08-24; **verify before relying on any specific flag or path** — several sources are explicitly documented as unstable.

## A. Workflow engine selection

### Recommendation: DBOS as a library, custom non-Turing-complete YAML above it

**Why DBOS.** MIT-licensed and needs only Postgres — no separate orchestration server. That makes "one container + Postgres" and "N containers + same Postgres" *the same architecture*, satisfying NFR-2. Human-in-the-loop is first-class: `DBOS.recv()` / `DBOS.send()` with waits documented as surviving restart and code upgrade, plus durable `DBOS.sleep()` with no documented cap. `DBOS.list_workflows()` with GIN-indexed JSONB attributes gives the inbox its query surface (FR-17, FR-33) without any vendor UI.

**Shape.** One `@DBOS.workflow()` interpreter, `async def`, taking `(dsl_doc_version, repo_vars)`. Every side effect — container run, LLM call, git operation — is a `@DBOS.step()`. Human gates are `await DBOS.recv_async(topic="approval", timeout_seconds=...)`. Use `async` rather than sync: a sync workflow parked in `recv` holds an executor thread. *(Durability is identical either way; the threading claim is source-read, not documented.)*

**Known DBOS limitations to design around:**
- Determinism required in workflow bodies; violations surface at *recovery*, not at write time.
- Cannot start or enqueue workflows from inside a step.
- Python serializes with pickle; 1GB field cap → **store artifacts in object storage, pass pointers**.
- PgBouncer session mode only (LISTEN/NOTIFY).
- The admin HTTP server was deprecated (2.29.0) and is off by default — build against `list_workflows` / `DBOSClient`, not admin endpoints.
- Conductor (the UI) is proprietary and paid; not needed, since we build our own inbox.

### Rejected: CNCF Open Workflow Specification as an implementation dependency
Renamed from CNCF Serverless Workflow; now v1.0.3, still CNCF Sandbox. The DSL *does* express what we need on paper — `listen.to` with correlation keys for unbounded human waits, `run.container` with `await` for long tasks, sub-workflows with per-instance input overrides. Two disqualifiers: (1) **no Python runtime exists** — `sdk-python` is a validator pinned to spec 0.8, last released 2022-04, with an unmerged 7-month-old 1.0 migration PR and no interpreter even in that PR; only JVM runtimes implement 1.0. (2) The spec **imposes no normative durability requirement** — grepping it for `durab|persist|checkpoint|replay` returns nothing, so whether a 3-week wait survives restart is entirely runtime-specific.

**Retained from it:** task *vocabulary* (`run/container`, `run/shell`, `listen`, `run/workflow`) so an exit path stays open. Not the dependency.

### Rejected: Kestra as the engine
One container, indefinite `Pause`, typed per-repo inputs, replay-from-task, native Docker task runner — genuinely attractive. Disqualifiers: the editor is **not embeddable** (`kestra-io/ui-libs` sunsetting, not accepting external PRs); assignee-based **Human Tasks are Enterprise-only**; OSS is single-server by default; K8s/ECS task runners, RBAC, SSO, and multi-tenancy are Enterprise. Also moves orchestration logic out of Python into YAML.

### Rejected: Prefect
`pause_flow_run` holds infrastructure open for the entire wait; `suspend_flow_run` **re-executes the flow from the top** on resume. Both are disqualifying for multi-day human gates.

### Considered: Temporal
The strongest alternative — MIT with nothing paywalled, and the only engine with a true `Replayer`. Rejected on operational weight for a single-container PoC. **Revisit if multi-container recovery (C-3) proves painful**, since Temporal's model handles it natively.

### Precedent for the layering
"Declarative YAML over a code-first durable engine" is a blessed pattern, not a hack: Zigflow (by a Temporal Staff Solutions Architect) compiles Open-Workflow-Spec-shaped YAML onto Temporal, and Temporal ships an official DSL-interpreter sample. The argued benefit is that **determinism stops being developer discipline and becomes a property the declaration layer cannot express**. The documented trap: JSON/YAML DSLs "tend to evolve into accidental programming languages." Hence FR-10 — no expressions, no loops, no string manipulation. Hard boundary, deliberately.

## B. Harness integration

### Claude Code
- **Invoke:** `claude -p`. Consider `--bare` for orchestrator runs (skips auto-discovery of hooks/MCP/plugins/CLAUDE.md) — but note it never reads OAuth credentials or the keychain, so it needs an explicit API key.
- **Session identity (FR-21):** pre-assign with `--session-id <uuid>`. No output parsing.
- **Resume (FR-23):** `claude -p --resume "$id" "message"`. Recent versions search all projects, so cwd need not match.
- **Structured output (FR-24):** `--output-format json --json-schema '<schema>'` → validated `structured_output`. This enforces `open_questions` / `assumptions` at the schema level rather than by inspecting prose.
- **Blocked detection (FR-31):** a `PreToolUse` hook returning `permissionDecision: "defer"` exits the process **cleanly** with `stop_reason: "tool_deferred"` and a `deferred_tool_use` payload. The orchestrator collects the human answer; on resume the hook returns `allow` with `updatedInput`. Constraints: `-p` only, single tool call in the turn, no timeout. **This is markedly better than inferring blockage from output files** and should be the primary mechanism.
- **Durable sessions (FR-22, C-4):** local state is `~/.claude/projects/<project>/<session-id>.jsonl`, default 30-day retention, format explicitly internal and liable to break on any release — **do not parse it**. The CLI has no export/import. Cross-machine resume is supported only via the **Agent SDK `sessionStore` adapter** (`append`/`load`, with reference S3/Redis/Postgres examples). `SessionKey.projectKey` encodes the working directory, so a resuming host must match cwd or pin the project-dir name. **Consequence for v2, not the PoC.** The SDK session store cannot serve the interactive SSH path (there is no terminal), and the PoC runs in one container where local state survives. **PoC uses print-mode CLI with orchestrator-owned session identity in Postgres.** Migrate to the SDK store when moving to multiple containers — see C-4 for the accepted risks in the meantime.
- **Long-lived process alternative:** `--input-format stream-json` with user messages pushed on stdin. *Superseded for the interactive path — see below.*

### Interactive session access — DEFERRED TO M3
**M1 does not build this.** The orchestrator prints the exact `--resume` command (harness, session id, working directory) into the inbox and the operator runs it in their own terminal (FR-23a). The orchestrator-owns-session-identity invariant is fully preserved at a fraction of the cost — this was the single largest scope cut available.

The deferred design: a custom web interface fronting **Apache Guacamole** (`guacamole.apache.org`), installed in the infrastructure, connecting to the execution container over **SSH**. Guacamole is a clientless remote-desktop gateway, so the browser talks to it and it talks SSH — no harness-specific streaming protocol to build.

**Ordering is the design point:** the orchestrator **creates** the harness session (pre-assigning the session id, FR-21) and only then does the human **resume** it interactively. Session identity is therefore always orchestrator-owned; there is no path where a human starts a session the orchestrator does not know about.

Consequences for architecture: (a) it is a real shell into the container, so it is a privileged surface (SEC-9) and must be authenticated, scoped to the project worktree, and audited; (b) it is harness-agnostic by construction, which sidesteps the Codex capability gap (C-5) for the *interactive* path even though the automated path still degrades; (c) Guacamole is infrastructure the PoC's single-container assumption does not cover — it sits alongside, not inside.

### Codex — DEFERRED TO M3
`codex exec`, `--json` event stream, `-o/--output-last-message`, `--output-schema`. Session id from the `thread.started` event; resume via `codex exec resume <SESSION_ID>`. State under `$CODEX_HOME` (default `~/.codex`).

**Capability gaps (C-5):** no documented defer / needs-input round trip; no documented OTEL exporter or tracing integration; session file path and retention unverified. OpenAI publishes no Codex Docker image — documented guidance is that where native sandboxing is unavailable, **the container itself is the boundary**.

**Design consequence:** model harnesses by *declared capability* — `supports_defer`, `supports_native_tracing`, `supports_structured_output`, `supports_resume` — and degrade the UX explicitly rather than pretending parity.

## C. Gateway and observability

### LiteLLM
Claude Code points at it via `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`; LiteLLM serves the native `/v1/messages`, and cache token accounting survives. Codex via a `[model_providers.litellm]` entry with `wire_api="responses"`.

**A non-first-party base URL silently disables things.** Each needs explicit re-enabling:
- MCP tool search → `ENABLE_TOOL_SEARCH=true`
- Fine-grained tool streaming → `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING=1`
- **Trace-context propagation → `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`** ← FR-43 depends on this
- Pin `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` — unrecognized gateway model IDs default output to 32000.

Virtual keys (`POST /key/generate`) carry `models`, `max_budget`, `budget_duration`, `tpm_limit`, `rpm_limit`, `metadata`, `tags` — this is the mechanism for FR-44/45. Requires Postgres. Spend tracking and team budgets are open source; **key rotation is Enterprise**.

### Langfuse
Claude Code emits a real span tree — `claude_code.interaction` → `claude_code.llm_request` / `.tool` / `.hook` — carrying `session.id`, gated on `CLAUDE_CODE_ENABLE_TELEMETRY=1` + `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER=otlp`. In `-p` and SDK sessions it **reads `TRACEPARENT`/`TRACESTATE` from its environment**, which is exactly the single-trace mechanism FR-43 needs. *(Interactive sessions deliberately ignore inbound traceparent.)*

**Langfuse ingests OTLP traces only** — not metrics, not logs — over HTTP/protobuf or HTTP/JSON; **gRPC unsupported**. Set the traces endpoint to the Langfuse OTLP path and route metrics/logs elsewhere or disable them.

**Content redaction is on by default.** `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT` enable it. Enabling puts source code and prompts into the telemetry backend — a deliberate decision, not a default to flip casually.

Langfuse's own "Claude Code" integration is a `Stop`-hook script that replays transcripts and **accepts no external trace id** — prefer the OTEL path.

For Codex, which has no custom-header env var, propagate the trace id via a **per-run LiteLLM virtual key carrying `langfuse_` metadata** (LiteLLM's Langfuse callback reads `trace_id`, `session_id`, `tags`, etc., accepted as `langfuse_`-prefixed HTTP headers).

## D. Container and security

Reference: Anthropic's devcontainer (`node:20`, non-root `node` user, `--cap-add=NET_ADMIN --cap-add=NET_RAW`, `init-firewall.sh` default-deny egress with an ipset allowlist).

- **Non-root is mandatory (NFR-3):** `--dangerously-skip-permissions` / `bypassPermissions` **refuses to start as root or sudo** on Linux and macOS unless inside a recognized sandbox.
- **Preferred automated recipe (NFR-4):** `--permission-mode dontAsk` with an explicit `--allowedTools` allowlist — the documented locked-down CI pattern — rather than blanket bypass.
- **Defence in depth:** `PreToolUse` hooks run first and a deny wins *even under bypass*. Built-in Bash sandboxing (macOS Seatbelt / Linux bubblewrap) with filesystem and network allowlists.
- **Hardening (SEC-3):** `--cap-drop ALL --security-opt no-new-privileges --read-only --user 1000:1000`; never mount `~/.ssh` or `~/.aws`.
- **Credential injection at the proxy (SEC-6)** so the agent process never holds a usable secret. Documented warning: under bypass mode a malicious repository can exfiltrate the agent's own credential store — hence repo-scoped short-lived tokens (SEC-1).
- **Sizing:** roughly 1 GiB RAM / 5 GiB disk / 1 CPU per concurrent agent. Relevant to FR-48 concurrency decisions.
- **Headless auth:** `claude setup-token` mints a one-year OAuth token (the documented CI path) — or a plain API key. Codex supports `codex login --device-auth` or a copied `auth.json`.

## D1b. The test-id contract (FR-24a)

The AC → Playwright translation must produce specs for a UI that **does not exist yet**. Selectors cannot be discovered, so they must be **agreed**.

**The acceptance-criteria contract is extended:** every Given/When/Then names the stable `data-testid` values and routes it touches. The criterion stops being pure prose and becomes a partial interface contract.

```
Given the operator is on /projects/{id}/epics
When they click [data-testid="epic-approve"]
Then [data-testid="epic-status"] shows "approved"
```

**Why this preserves independence.** FR-27 defines a deterministic oracle by **timing** — fixed before the implementation existed — not by authorship. Authorship was never achievable, since the translation is itself an agent task. The contract is fixed at G1b (M2) or at ingest (M1), the spec is generated and approved at G2, and only then does implementation begin. The implementation must satisfy an interface it did not choose.

**Costs, stated plainly.** It makes G1b heavier, pushes interface decisions earlier than engineers usually make them, and constrains implementation freedom. It is the largest untested assumption in the design (§11) and is first on the verification queue.

**Enforcement:** an acceptance criterion with no test-ids is rejected at ingest; a criterion with no generated spec blocks G2 (FR-28b). Neither is a warning.

## D2. Workflow library

Three authored templates, versioned in git. Instances are produced by variable binding only.

| Template | Variables bound per run | Owns |
|---|---|---|
| **`new-feature`** *(M2)* | project, repos, base branches, issue | Workspace prep (Phase A) → analyst/PM session → **G1a** → architecture + epic planning → **G1b** → checkpoint validation → plan generation → **G2** |
| **`epics`** *(M1)* | epic id, story list, target repo | Branch + worktree (Phase B) → copy approved inputs into worktree → loop stories → integration E2E → open PR → **G3** |
| **`stories`** *(M1)* | story id, target repo, commands, AC set | Implement (agent) → unit tests → code quality → story E2E against the G2-approved spec → gate evaluation → escalate on `open_questions` or `blocking`/`material` assumptions |

**Why structure is authored rather than generated.** Three independent reasons, any one sufficient: (1) FR-9 pins each run to a DSL document version — a model-invented graph has no stable document to pin; (2) the G2 gate would review an unfamiliar graph every run, which is expensive enough that it degrades into a rubber stamp, the precise failure mode §12 warns about; (3) it violates the non-Turing-complete boundary (FR-10) that keeps the DSL from becoming a bad programming language.

**Where the real dynamism lives:** the story list and its length, target repositories, per-repo commands, and the AC set — all bound from the spec at G2 time. That is enough for "no hardcoded workflows" in the sense that matters: nothing is authored per project.

**Bugfix variant deferred to M3.** One intake path until the loop works.

**Note on ordering:** the AC → Playwright translation happens in `new-feature`/ingest, **not** in `stories`. The spec must exist and be approved at G2 before any story runs, or it is no longer independent of the implementation.

**Deferred: the `adversarial` gate tier.** An independent agent instructed to refute a finding, with a majority vote. Defined in FR-27's original taxonomy, removed from M1 as unproven cost. Revisit if the deterministic oracle proves insufficient.

## E. Rejected framings (from the forge)

| Rejected | Reason |
|---|---|
| "An OS for AI agent workflows" | Overclaims. It is a cockpit for one engineer, and the framing hid that human attention is the ceiling. |
| Generic "issue → PR" as first scenario | Roughly half of tickets are faster to write than to specify precisely. The tool wins only on slow-to-write / fast-to-specify / fast-to-verify. |
| File-existence as validation | A liveness check. Catches the crashed agent, never the confidently-wrong one — which is the failure that reaches the PR. |
| Escalating on agent-reported blockage alone | Non-interactive agents cannot ask, so they assume and proceed. Catches honest agents, misses dangerous ones. → FR-30. |
| Human QA as the *only* gate | A human handed a running, green feature is in confirmation mode. The premise check must happen before the build, when it is still free. → Gate 1. |
| Agent-generated E2E tests as the oracle | A test generated from the implementation is a mirror, not an oracle. Independence requires the spec to precede the code. |
| Model-generated workflow structure | No stable document to version-pin, an unreviewable G2 gate, and a DSL that grows into a bad programming language. Dynamic instantiation yes; dynamic structure no. |
| Atomic cross-repository merge | Does not exist in git or GitHub. One story targets one repository; merge order is a human decision at G3. |

## F. Verification queue

**Order matters — item 1 is the largest untested assumption and item 7 is a one-way door.**


Before architecture commits to any of this:
1. **Write acceptance criteria with test-ids for three real features by hand** and confirm it is tolerable in practice (FR-24a). If this is painful, the oracle strategy needs rethinking before anything is built.
2. Confirm the defer-hook round trip end-to-end in a container.
3. Confirm `TRACEPARENT` propagation survives LiteLLM into Langfuse as one trace.
4. Confirm DBOS `recv_async` survives container restart across a multi-day park.
5. Confirm the DSL-document-version pinning strategy against a deliberate mid-flight YAML change (C-1).
6. Verify that the AC → Playwright translation (FR-28b) produces specs traceable to signed criteria, and that unmatched criteria are reported rather than silently dropped.
7. Establish a manual baseline on two or three comparable features — **before** the pipeline exists, or the "better than by hand" question can never be answered honestly (§12).
