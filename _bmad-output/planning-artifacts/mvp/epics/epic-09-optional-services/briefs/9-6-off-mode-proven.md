---
story: "9-6"
epic: 9
title: Running without the host services, proven and documented
requirements: [NFR-7, NFR-8, FR-24, FR-33]
binds: [AD-5, AD-11, AD-20]
---

# Story 9.6 — Off-mode, proven and documented

As the Operator,
I want one Run to reach `done` on an instance with no LiteLLM and no Langfuse, and a page that tells me what the mode costs me,
So that the degraded mode is something I have seen work rather than something the tests imply.

## Operator and agent split

Read this first. **You** (the agent) write the runbook, the web-client checks and any code the checks require, then halt `blocked` naming exactly what the Operator must do and the facts to report back. **The Operator** edits their own `.env`, logs a harness in (`claude login` inside the container, or a Project variable carrying their own key), restarts the stack and runs the Story. You never run a real harness, never log a harness in, never write a credential anywhere, and record nothing in the runbook that the Operator did not report. If no Operator login is available, halt `blocked` saying so — that is an acceptable outcome for this story, and 9-1 … 9-5 stand on their own tests.

## Scope

**In:** the "Running without the host services" section of `DEPLOY.md` and the matching note in `host/README.md`; web-client tests that an absent trace and a provisional cost read as facts; the Operator's recorded result.
**Out:** any change to the switches, the adapters, the registry or the scripts — those are 9-1 … 9-5 and are finished before this story starts. If this story finds a defect in one of them, it halts `blocked` naming the story rather than fixing it here.

## Binding rules (inlined)

- **The runbook states the mode and its price, in the Operator's words:** blank `LITELLM_BASE_URL` disables the Gateway, blank `LANGFUSE_BASE_URL` disables tracing, an unset variable still refuses at start-up; with the Gateway off the harness authenticates from its own login in the `agent-home` volume or from a Project variable, cost is the harness's own provisional figure, budget parking is only as good as that figure, and `local` is unavailable; with tracing off there are no traces and no trace links, and `attempt_observed` never confirms an attempt. No step of the runbook prints or stores a credential.
- **The screen never congratulates and never implies a figure it does not have (PRD NFR-8).** The trace row is *absent* when `cost.trace_url` is `null` — the Run detail's cost block and the history table already do this (`web-client/src/components/run/CostBlock.tsx`, `src/components/runs/HistoryTable.tsx`); this story adds the tests that pin it, and adds the word `provisional` beside a provisional cost if the block does not already carry it. `skipped` and `unvalidated` stay words on screen, never green.
- **No new API field and no schema change.** `trace_url` is already `string | null` in `web-client/src/api/schema.d.ts`, and `cost_provisional` already exists. If a change here would need a payload field, halt `blocked`: it belongs to another story and `src/api/schema.d.ts` is generated, never hand-written (AD-3).
- **What the Operator is asked to report,** and all this story records: which harness and which login, that `backend-api` started and logged `gateway disabled` / `tracing disabled`, that New workflow offered `claude` and `codex` and refused `local` with the stated reason, that the Story reached `done`, and what the Run detail showed for cost and for the trace row. Anything not reported is written as not observed.

## Acceptance criteria

**Given** a run-detail read model whose `cost.trace_url` is `null`
**When** the cost block renders
**Then** no trace row and no `open in Langfuse` link is present, and no placeholder stands in for it.

**Given** a history row whose `trace_url` is `null`
**When** the table renders
**Then** the trace cell holds the row's stated text with no link, and nothing reads as an error.

**Given** a cost whose figure is provisional
**When** the cost block renders
**Then** the word `provisional` is beside the figure, and no copy congratulates or apologises.

**Given** the runbook
**When** an Operator follows it on a machine with neither host service
**Then** the stack starts, and every claim in it matches what 9-1 … 9-5 actually implement (assert the runbook's variable names and log lines against the code in a test, so a later rename cannot leave the document lying).

**Given** the Operator's report
**When** it is recorded
**Then** `DEPLOY.md` names the harness, the mode and the date, and states plainly anything that did not work.

## Implementation notes

- Web-client tests are vitest, beside the existing component tests; do not modify an existing test file.
- The runbook's claims-versus-code check belongs in the backend unit tests (it reads two committed files); keep it to the names and the log lines, not prose.
- Halt with `blocked` and the exact commands the Operator must run — the same shape stories 7-2 and 7-4 used.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

PRD NFR-7 (host services), NFR-8 (copy states facts), FR-24 (cost readout), FR-33 (readiness). Spine AD-3 (the contract is generated), AD-11. `DEPLOY.md` and `host/README.md` — the existing setup they extend. Stories 7-2 and 7-4 briefs — the Operator-and-agent split this story reuses.
