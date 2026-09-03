---
story: "5-10"
epic: 5
title: Run detail additions for story steps
requirements: [FR-16 (Question), FR-23, FR-28 (provisional), NFR-2, NFR-6, NFR-8, UX-DR9, UX-DR10 (blocked and misconfigured bodies), UX-DR18]
binds: [AD-1, AD-3]
---

# Story 5.10 — Run detail additions for story steps

As the Operator,
I want a blocked story's question shown whole and attributed, the cost figures marked provisional until the Gateway confirms them, and the trace one click away,
So that coming back cold I read what the agent needs and what the Run has cost, without guessing (SM-2).

## Scope

**In:** in `RunDetail`: the **Question** block for `park_kind blocked`, the `misconfigured` body (condition, file list, log tail, no Answer box), Stories strip states, `harness` and `cost` columns filled, the cost kv with `provisional`, the Langfuse trace link, `readiness` and `repo-init` labels; the read-model fields they need; tests.
**Out:** the Answer box and *Resume with answer* (Epic 6; render the buttons the read model admits only when Epic 6 lands — here the blocked body shows the question and *Skip story* / *Skip epic* / *Cancel run* as admitted).

## Binding rules (inlined)

- **Question block (UX-DR9, `DESIGN.md`).** For `alert.park_kind == blocked`: eyebrow `Agent · {harness} · {model} · {ended_at}`, then the whole `## Auto Run Result` section (`alert.reason`) at `typography.question` on `surface-raised` with the 2px amber rule; Markdown rendered minimally (headings, lists, code) with no images or links executed. Test-id `wf-question`.
- **Misconfigured body (UX-DR10).** For `park_kind misconfigured`: the condition line (`harness misconfigured: no subagents`, `no story file`, `ambiguous story file: a.md, b.md`, `unexpected status: draft`, `harness exit 1`, `gateway unreachable`), the file list when the reason names files, the log tail (last 40 lines) in a command block, **no Answer box**, buttons from `admitted_signals` (*Retry*, skips when available, *Cancel run*).
- **Steps table.** `harness` column = attempt harness on agent rows, empty otherwise; `cost` = the row's `cost_usd` as `$0.00`, with the word `provisional` after it when the latest attempt is provisional; `time` = seconds of the latest attempt.
- **Stories strip.** Cells from `stories[]`: done filled, current amber (the only amber besides the token), future hollow, skipped struck-through; a `blocked` story's cell is the current one.
- **Cost & trace kv.** `spent / budget` as `$41.20 / $40.00` (+ `provisional` word when any), `tokens in / out`, `wall-clock`, `your active time —` (Epic 8), `trace` → link `open in Langfuse` to `cost.trace_url` (absent when null), the compare links, the branch link.
- **Cards.** `readiness` / `repo-init` Runs show that word in place of progress (4.14 already reads `kind_label`; verify).
- **Signal rule:** the question block's rule and the current strip cell are the allowed amber elements on a `BLK` detail; nothing else.
- **Test-ids:** `wf-question`, `wf-question-eyebrow`, `wf-stop-misconfigured`, `wf-cost-provisional`, `wf-trace`, `wf-stories-cell-<id>`.

## Acceptance criteria

**Given** a stubbed detail parked `blocked` with a three-paragraph `## Auto Run Result`
**When** rendered
**Then** the question block shows the whole section with the eyebrow `Agent · claude · claude-opus-4 · {time}`, and the buttons are exactly the admitted signals from the stub.

**Given** a detail parked `misconfigured` with `no story file`
**When** rendered
**Then** the body shows the condition and the log tail and contains no textarea.

**Given** a step row whose latest attempt is provisional
**When** rendered
**Then** its cost cell reads `$1.23 provisional` and the cost kv reads `$12.30 / $40.00 provisional`.

**Given** `cost.trace_url` set
**When** rendered
**Then** the kv shows the `open in Langfuse` link; when null, no trace row.

**Given** the stories strip with states done, current, future, skipped
**When** rendered
**Then** each cell has the matching class and only the current cell uses the amber token.

## Implementation notes

- `src/components/run/QuestionBlock.tsx` (Markdown via a small allowlist renderer, unit-tested against script injection), `StopBody` extended for `blocked` and `misconfigured`.
- Read model: ensure `StepRow.latest.cost_provisional`, `alert.attribution {harness, model, ended_at}` exist (add in `run_views.py` if missing).

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2.2 (stop bodies for `blocked` and `misconfigured`, cost kv, strip). PRD FR-16, FR-23, FR-28. `DESIGN.md` question block, kv table.
