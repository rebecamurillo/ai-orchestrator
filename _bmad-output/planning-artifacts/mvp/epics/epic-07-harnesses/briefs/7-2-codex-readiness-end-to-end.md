---
story: "7-2"
epic: 7
title: Codex readiness passes end to end
requirements: [FR-14, FR-27, FR-33, PRD §8 item 2, AR-27]
binds: [AD-10, AD-11]
---

# Story 7.2 — Codex readiness passes end to end

As the Operator,
I want `codex` proven on the real host: one story to `done`, its spans under the Run, its spend attributed,
So that the harness comparison (SM-3) has its second data point on a proven path.

## Operator and agent split

*Added 2026-09-09, when the Operator decided this epic would be run by the orchestrator itself.*

**A coding agent cannot complete this story.** It needs a live Codex CLI, the host LiteLLM and Langfuse,
and credentials that never reach a harness process. The agent's work is everything before the run and
everything after it — never the run.

**The agent does, in one dispatch:**

1. Any code the fallbacks below require, unit-covered over the fakes: `attempt_observed` accepting
   session-level observations for `codex`, the tag-based spend fallback of 5.3, and any fix to 7.1 that
   reading the CLI's own output makes necessary.
2. A runbook, committed to this story's spec: the exact commands, what to read in each output, and what
   each outcome forces as a decision.
3. Then it **halts `blocked`**, its Blocking condition naming exactly what the Operator must run and the
   facts to report back. **It never guesses a value only a live run can confirm** — Epic 5 shipped
   `stop_reason: "max_budget"` as a plausible constant behind a passing test, and story 5-11 later
   disproved it against the shipped bundle.

**The Operator then runs it**, with the assistant reading the output alongside them, and answers with:
the six evaluation lines and their text; whether Codex spans appear parented under the attempt span or
only at session level; whether `/spend/logs/v2` returned the attempt's rows; and whether
`bmad-build-auto` was discovered from `~/.agents/skills` with subagents available.

**The agent, resumed with that Answer**, records the dated "Codex — verified" block in `addendum.md` §B
from the reported facts, lands whatever fix the outcome forces, and finishes the story. **It writes
nothing into §B that the Operator did not observe.**

## Scope

**In:** running `POST /harnesses/codex/readiness` on the compose stack against the host LiteLLM and Langfuse; settling `TRACEPARENT` honouring; applying the fallback when needed; recording the verified block in `addendum.md` §B; small tested fixes in 7.1.
**Out:** OpenCode (7.3, 7.4).

## Binding rules (inlined)

- **Preconditions.** As 5.11: `.env` with real host values; `make up` green; halt `blocked` with `host services unreachable: {which}` otherwise.
- **Trace continuity (spine "Open at handoff" 1).** If `attempt_observed` finds Codex spans under the attempt span, record `TRACEPARENT honoured`. If not: apply the fallback — the Langfuse Codex integration producing a flat trace seeded under the Run's session `[per research/tracing.md §Codex; the exact mechanism is chosen at the spec checkpoint]`, and make `attempt_observed` for `codex` accept observations found by `session_id == run_id` with the attempt tag; record `TRACEPARENT not honoured · fallback: session-level`.
- **Skill discovery (item 3).** Codex must run `bmad-build-auto` from `~/.agents/skills` with the worktree as project root and satisfy the subagent requirement (`multi_agent`); a `blocked · no subagents` result means the fallback of 5.11 (stubs copied into the worktree) or a Codex feature flag `[verify]`; record the outcome.
- **Spend.** `/spend/logs/v2` must return the attempt's rows via `env_http_headers`; if the responses API path drops headers, record it and apply the tag-based fallback of 5.3.
- **Record.** `addendum.md` §B gains a dated "Codex — verified" block: argv, session capture event, trace result, header result, skill discovery result.

## Acceptance criteria

**Given** the stack against the host services
**When** the `codex` readiness Run completes
**Then** `GET /harnesses` shows `codex · enabled` with every line `ok`, the trace holds the attempt's Codex observations (parented or session-level, as recorded), and the attempt's cost is non-provisional.

**Given** `addendum.md` §B
**When** read
**Then** it contains the verified Codex block with the trace decision.

**Given** any fix made to 7.1 or the tracer
**When** `make lint test` runs
**Then** it is unit-covered and green.

## Verification

```bash
make up && curl -s -X POST -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" localhost:8000/api/v1/harnesses/codex/readiness
```

## Sources for detail only

PRD §8 items 2, 3, 6; FR-33. Spine "Open at handoff" 1, 4; AD-11. `research/tracing.md` §Codex. `addendum.md` §B, §H.
