---
id: SPEC-mvp-epic-05-dev-loop
companions: []
sources:
  - ../../prd.md
  - ../../addendum.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../architecture/research/tracing.md
  - ../../architecture/research/spend.md
  - ../../architecture/deliverables/scripts/harness/
---

> **Canonical contract for Epic 5.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 5 — The unattended dev loop through Claude Code

## Why

The vision itself: a story-sized unit of work runs to a verified commit without anyone watching. This epic adds the one step kind that dispatches a coding agent — through the Claude Code harness first — and everything that makes its result trustworthy: the prepare commits that give the agent a clean tree, the prompt that names the skill and nothing else, the evaluation of the story file the agent writes, the protected-path check, the budget halt, one trace and one attributable cost per Run through the Gateway, the readiness Run that proves a harness before it is offered, and the trajectory record written once per done story. It realises user journey UJ-2 and success metric SM-1 for `claude`.

## Capabilities

- **CAP-1** Harness port, environment contract, and the Claude adapter — `Harness` protocol, `env_for(attempt)` equal to the scripts' declared lists, `claude -p` dispatch with pre-assigned session, budget cap, allowlist, resume, resume command. **success:** a unit test proves the adapter's env key set equals `HARNESS_ENV_CONTRACT` ∪ `HARNESS_ENV_ALIASES` ∪ Project vars; the adapter returns `HarnessResult` uninterpreted.
- **CAP-2** Tracer port and Langfuse adapter — Run trace seeded from the Run id with the Run id as session, a span per Step, a child span per Attempt exporting `TRACEPARENT`, `attempt_observed`. **success:** the Run detail's trace link opens a Langfuse trace holding every Step span; content logging is off unless the Project enables it.
- **CAP-3** Gateway spend adapter and the budget rule — `spend_for_attempt` from `/spend/logs/v2` with the spend key, provisional fallback, `run.spend_usd` as the sum. **success:** an Attempt's cost and tokens are filled from the Gateway; when absent they are provisional and replaced later.
- **CAP-4** Agent executor: prepare and dispatch — WIP commit, `project-context.md`, prepare commit, `start_sha`, `compose_prompt`, dispatch, `mark_started` / `mark_finished`, timeout. **success:** the harness always starts on a clean tree; nothing the orchestrator wrote is attributed to the agent; the prompt contains exactly the mandated parts.
- **CAP-5** Agent executor: contract evaluation and routing — story-file liveness, configuration failures, the FR-16 routing table, `expect` + `retry` with session resume, verify redispatch (`## Verify Failure`). **success:** every row of the routing table has a unit test; the Run parks with the exact reason texts.
- **CAP-6** Protected paths — frozen anchors checked over agent ranges after every attempt and at commit-guard, with `accepted_paths`. **success:** an agent edit of `SPEC.md`, an `AGENTS.md`, or a pre-existing test parks the Run; an operator edit never does.
- **CAP-7** Budget halt — spend read after every attempt before verify; `spend > budget` parks `budget` while the row keeps its routed status; the Claude cap exit is a budget park. **success:** a Run never exceeds its budget by more than one attempt.
- **CAP-8** Harness readiness — the built-in Project `readiness`, the fixture repository, `start`, `evaluate`, `sync_pins`, the endpoints, the New workflow line. **success:** `claude` is `enabled` only after an `epic@1` Run on the fixture reaches `done` with a trace, a session id, a non-empty spend, and verify exit 0.
- **CAP-9** Trajectory record — one append-only row per done story. **success:** the row carries run, story, harness, model, attempts, gate results, cost, story-file snapshot, start and end SHA; nothing updates or deletes it.
- **CAP-10** Run detail additions — Question block for `blocked`, misconfigured bodies without an Answer box, Stories strip states, cost figures with `provisional`, trace link, harness and cost columns. **success:** the whole `## Auto Run Result` is shown as the Question with agent attribution.
- **CAP-11** Claude readiness passes end to end — the day-1 verifications recorded in the addendum. **success:** the readiness Run for `claude` reaches `enabled` on the real host services and `addendum.md` §B records the invocation and allowlist.

## Constraints

- A harness process receives exactly the env contract plus the Project's variables; never `GITHUB_TOKEN`, never `LITELLM_SPEND_KEY`, never the orchestrator's env (AD-5, AD-10).
- Adapters never read model output; `compose_prompt` in `steps/agent.py` is the only prompt builder (AD-9, AD-10).
- Every side effect stays inside the engine step; status changes go through the two writers (AD-8).
- `blocked`, budget, timeout, protected-path, internal, and configuration failures are never re-executed automatically (AD-9).
- One exporter per harness; `TRACEPARENT` for `claude` (AD-11).
- `enabled` is read only by `create_run` and pre-flight (AD-10).
- Tests first; `rules/` and `steps/agent.py` at 100 % branch coverage (AD-18).

## Non-goals

- No `codex` or `local` adapters (Epic 7); no Answer, Continue-on-agent-row, Skip, Raise budget, Accept, or terminal signals (Epic 6) — the parks exist, the resumes do not.
- No trajectory export (Epic 7).

## Success signal

On the fixture repository, a `claude` readiness Run plans `checkout · baseline · story 1 (sync · build · verify · commit_guard) · push · link`, the agent writes `stories/1-*.md` with `status: done` and commits, verify exits 0, the Gateway returns the attempt's spend, Langfuse shows the attempt's spans under the Run's session, and the harness list on New workflow reads `claude · enabled`.
