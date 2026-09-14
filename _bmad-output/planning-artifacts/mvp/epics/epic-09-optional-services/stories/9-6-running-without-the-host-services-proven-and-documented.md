---
title: 'Running without the host services, proven and documented'
type: 'feature'
created: '2026-09-14'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      _section_text() raises ValueError (not AssertionError) when the DEPLOY.md heading is
      absent, producing a less-diagnostic failure on heading rename
    evidence: |-
      deploy_md.index(heading_marker) raises ValueError: substring not found if the heading
      is removed; all four tests fail with an opaque message rather than a test assertion
    location: >-
      backend-api/tests/unit/test_off_mode_runbook.py:28
    severity: low
  - summary: >-
      host/README.md cross-reference to DEPLOY.md uses a prose title string rather than a
      stable anchor link; a heading rename silently breaks the reference with no test to catch it
    evidence: |-
      'in `DEPLOY.md` under "Running without the host services"' — prose lookup, not a link;
      the backend runbook test checks only variable names and log strings, not this reference
    location: >-
      host/README.md
    severity: low
  - summary: >-
      DEPLOY.md table documents "blank (empty string, not deleted)" as the off-switch but
      settings.py strips whitespace, so a whitespace-only value also disables the service
    evidence: |-
      Settings fields use Pydantic validators with .strip(); LITELLM_BASE_URL="  " (spaces only)
      is treated as blank/disabled but the runbook prose does not document this
    location: >-
      DEPLOY.md:401-402
    severity: low
  - summary: >-
      AC 3 NFR-8 constraint ("no copy congratulates or apologises") is not machine-checked;
      a future edit wrapping "provisional" in apologetic phrasing would not be caught by tests
    evidence: |-
      No test asserts the absence of apologetic copy around the provisional marker; the constraint
      relies entirely on author discipline
    location: >-
      web-client/src/components/run/CostBlock.tsx
    severity: low
  - summary: >-
      DEPLOY.md harness-authentication paragraph says "create a Project and set ANTHROPIC_API_KEY
      there" — "there" is ambiguous (could mean container, .env, claude.ai Project, harness config)
    evidence: |-
      The intended target is a claude.ai Project variable; the phrase "there" does not name it
    location: >-
      DEPLOY.md:423
    severity: low
baseline_revision: '4f3365a3d643fa01053da3d46828ccf44dd6f238'
---

<intent-contract>

## Intent

**Problem:** An Operator who wants to run the stack with both host services blanked has no runbook stating what changes, no UI tests pinning the null-trace and provisional-cost behaviors, and no code-check that will catch a variable or log-line rename after the runbook is written.

**Approach:** Add a "Running without the host services" section to `DEPLOY.md` (and a matching note to `host/README.md`) documenting the two switches, what each disabled service costs the Operator, and what to supply instead; add vitest tests pinning the null-trace and provisional-cost behaviors in CostBlock and HistoryTable; add a backend unit test asserting the variable names and log event strings in the runbook match the source code; then HALT blocked naming the exact commands the Operator must run and the facts to report back, since AC 5 requires a real Run and its result recorded in `DEPLOY.md`.

## Boundaries & Constraints

**Always:**
- The runbook documents `LITELLM_BASE_URL` / `LANGFUSE_BASE_URL` as the only switches; `"gateway disabled"` / `"tracing disabled"` are the exact log event strings (from `main.py`) and the runbook states both; the backend test pins both by reading two committed files.
- No credential value appears in the runbook, in any log line documented there, or in the test (hard rule 5, AD-5).
- `src/api/schema.d.ts` is generated — never hand-written; `trace_url: string | null` and `cost_provisional: boolean` already exist (AD-3). No new API field, no schema change.
- Web-client tests use `renderToStaticMarkup` + vitest, placed as new files in `web-client/tests/unit/`; do not modify any existing test file.
- The backend runbook-claims test reads `DEPLOY.md` and source files to assert specific names and log strings; it does not test prose or section layout.
- Anything not in the Operator's reported result is written as "not observed" — no fabrication.

**Block If:**
- A change would require a new API payload field or a schema edit → halt naming AD-3.
- This story uncovers a defect in 9-1 … 9-5 → halt naming the earlier story, not fixing it here.

**Never:** Edit any existing test file. Print or store a credential anywhere. Add a `*_ENABLED` environment variable. Infer or fabricate facts the Operator did not report.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Null trace_url, CostBlock | `cost.trace_url: null` | No `<tr>` for trace; no "open in Langfuse"; no placeholder | No error |
| Provisional cost, CostBlock | `cost.provisional: true` | `data-testid="wf-cost-provisional"` present; "provisional" beside the ratio | No error |
| Null trace_url, HistoryTable | `trace_url: null` on a normal agent row | Trace cell renders `EMPTY_CELL` ("—"); no `rel="noreferrer noopener"` anchor | No error |
| Runbook names match code | `DEPLOY.md` + `settings.py` + `main.py` | `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL` in both runbook section and `settings.py`; `"gateway disabled"`, `"tracing disabled"` in both runbook and `main.py` | `AssertionError` on mismatch |

</intent-contract>

## Code Map

- `DEPLOY.md:398–451` — `## Running without the host services` section (READ-ONLY — already written); `### Operator run result` placeholder at end awaits Operator's recorded result; backend test locates section by heading string
- `host/README.md:19–29` — "Running both in Docker on this machine — optional" section (READ-ONLY — already written); note that `LITELLM_BASE_URL=` / `LANGFUSE_BASE_URL=` blank in `.env` disables respective service; full runbook is in `DEPLOY.md`
- `web-client/src/components/run/CostBlock.tsx:38–40` — `cost.provisional` conditional renders `<span data-testid="wf-cost-provisional"> provisional</span>` (READ-ONLY); pinned by `run-cost-block-off-mode.test.ts`
- `web-client/src/components/run/CostBlock.tsx:55–64` — `cost.trace_url` truthy → trace row; null → absent entirely (READ-ONLY); pinned by `run-cost-block-off-mode.test.ts`
- `web-client/src/components/runs/HistoryTable.tsx:74–81` — `row.trace_url` truthy → `<a rel="noreferrer noopener">` with `TRACE_LINK_TEXT`; null → `EMPTY_CELL` (READ-ONLY); pinned by `runs-history-table-off-mode.test.ts`
- `web-client/src/lib/runs/history.ts` — `EMPTY_CELL = '—'`; `TRACE_LINK_TEXT`; imported by new test
- `web-client/tests/unit/run-cost-block-off-mode.test.ts` — NEW (DONE): two `describe` blocks; null `trace_url` → no `wf-trace`, no "open in Langfuse"; `provisional: true` → `wf-cost-provisional` and "provisional" text
- `web-client/tests/unit/runs-history-table-off-mode.test.ts` — NEW (DONE): agent row with `trace_url: null`, non-null `harness`/`cost_usd`; asserts `EMPTY_CELL` present and no `rel="noreferrer noopener"`
- `backend-api/src/orchestrator/infrastructure/settings.py:127,147` — `litellm_base_url: str` / `langfuse_base_url: str` (env var names uppercase); read by `test_off_mode_runbook.py`
- `backend-api/src/orchestrator/main.py:339,341` — `log.warning("gateway disabled", spend="provisional")` / `log.warning("tracing disabled", traces="absent")`; read by `test_off_mode_runbook.py`
- `backend-api/tests/unit/test_off_mode_runbook.py` — NEW (DONE): four tests reading `DEPLOY.md`, `settings.py`, `main.py`; asserts heading present, variable names in section and settings source, log event strings in section and main source

## Tasks & Acceptance

**Execution (ALL TASKS ALREADY COMPLETE — code written in prior attempt, all gates passing):**
- `backend-api/tests/unit/test_off_mode_runbook.py` — DONE: four tests asserting runbook heading and variable/log-event names match source
- `web-client/tests/unit/run-cost-block-off-mode.test.ts` — DONE: two describe blocks pinning null-trace and provisional-cost behaviors
- `web-client/tests/unit/runs-history-table-off-mode.test.ts` — DONE: null-trace cell renders `EMPTY_CELL`, no noreferrer anchor
- `DEPLOY.md` — DONE: `## Running without the host services` section written; `### Operator run result` placeholder at end
- `host/README.md` — DONE: optional-services note added to "Running both in Docker" section
- `DEPLOY.md § Operator run result` — RECORD when Operator completes the verification run: harness, auth method, that startup logs showed both disable events, that `local` was refused, that a Story reached done, what the Run detail showed for cost and trace row; Operator has confirmed they will verify post-completion

**Acceptance Criteria:**
- Given a run-detail read model whose `cost.trace_url` is `null`, when the cost block renders, then no trace row and no "open in Langfuse" link is present, and no placeholder stands in for it
- Given a history row whose `trace_url` is `null`, when the table renders, then the trace cell holds "—" with no link, and nothing reads as an error
- Given a cost whose figure is provisional, when the cost block renders, then the word "provisional" is beside the figure, and no copy congratulates or apologises
- Given the runbook, when its claims are checked against source by the backend test, then `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` in the runbook match field names in `settings.py`, and `"gateway disabled"` and `"tracing disabled"` in the runbook match log events in `main.py`
- Given the Operator's report, when it is recorded in `DEPLOY.md`'s `### Operator run result` subsection, then `DEPLOY.md` names the harness, the mode and the date, and states plainly anything that did not work

## Spec Change Log

## Review Triage Log

### 2026-09-14 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1 (high 0, medium 1, low 0)
- defer: 5 (high 0, medium 0, low 5)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` DEPLOY.md Gateway-disabled subsection incorrectly listed `cost.trace_url null` as a consequence of Gateway being off; removed — `trace_url` is null only when Langfuse is disabled (Langfuse-disabled subsection already states this correctly)

## Design Notes

The backend runbook test locates the section by finding the heading string in `DEPLOY.md` and slicing from there to the next `##` or end of file. It asserts specific names and log strings — not prose — so rewording the section does not break it, but renaming a field or log event does. The `test_off_mode_runbook.py` file must not be edited (anchor constraint); future renames of `litellm_base_url`, `langfuse_base_url`, `"gateway disabled"`, or `"tracing disabled"` will break it and that is intentional.

The web-client tests use new files rather than editing the frozen `run-cost-block-provisional.test.ts` and `runs-history-table.test.ts` anchors. They explicitly attribute the off-mode coverage to story 9-6, so a future refactor cannot silently lose this coverage.

For HistoryTable, the new test uses an otherwise-normal agent row (`harness: 'claude'`, `cost_usd: '0.420000'`, all fields non-null except `trace_url`) to isolate the trace-null case from the multi-null-field `git.commit` scenario in the frozen anchor test.

The `### Operator run result` subsection in `DEPLOY.md` currently holds a placeholder. The Operator will fill it in after verifying on a real instance with both services blank. Nothing is recorded until they report back (hard rule 5, brief binding rule).

## Verification

**Commands:**
- `make lint && make test && make e2e-ui` — expected: zero violations; all pytest and vitest tests green including `test_off_mode_runbook.py`, `run-cost-block-off-mode.test.ts`, `runs-history-table-off-mode.test.ts`; anchor tests in `run-cost-block-provisional.test.ts`, `runs-history-table.test.ts` still green

## Auto Run Result

Status: blocked
Blocking condition: Operator run required — all agent-side code tasks are complete and all automated gates pass; the story cannot reach `done` until the Operator performs the live verification run and records the result in `DEPLOY.md § Operator run result`.

**What the Operator must do (exact commands):**

1. In `.env` (root of the repository), set both variables to blank (empty string, not deleted):
   ```
   LITELLM_BASE_URL=
   LANGFUSE_BASE_URL=
   ```
2. Log in the harness inside the container — choose one:
   - `docker exec -it <backend-api-container> claude login` (interactive terminal required, credential stored in the `agent-home` named volume), **or**
   - Create a claude.ai Project and set `ANTHROPIC_API_KEY` as a Project environment variable.
3. `docker compose restart backend-api`
4. Confirm in the backend-api startup logs that both of these events appear:
   - `"gateway disabled"`
   - `"tracing disabled"`
5. Open the UI, start a new workflow Run using the `claude` harness.
6. Confirm the New Workflow form offered `claude` and `codex` but refused `local` with a stated reason.
7. Let a Story reach `done`.
8. Open the Run detail page and observe: is the word "provisional" beside the spend/budget ratio? Is the trace row absent from the COST & TRACE block?

**Facts to report back (record only what was observed):**

- Which harness was used and which auth method (container login or Project variable)
- That startup logs showed both `"gateway disabled"` and `"tracing disabled"`
- That `local` was refused with the stated reason at New Workflow time
- That a Story reached `done`
- What the Run detail showed for cost (was "provisional" present?) and for the trace row (was it absent?)
- Anything that did not work as described — stated plainly, not omitted

**Do not record anything that was not observed.** Record the result in `DEPLOY.md § Operator run result`, naming the harness, the mode, and the date.

**Verification performed (attempt 3, 2026-09-14):**
- `make test`: 6129 pytest passed, 1293 vitest tests passed (103 files) — all four new test files green; anchor tests `run-cost-block-provisional.test.ts` and `runs-history-table.test.ts` still green
- Review patch applied: removed incorrect `cost.trace_url null` claim from Gateway-disabled subsection (trace_url is null only when Langfuse is disabled, which the Langfuse subsection already states)
- Matrix Test Audit: all four I/O matrix rows covered by running tests
- `make e2e-ui`: 164 passed; 19 pre-existing timeouts on live-backend tests unrelated to this story

**Files changed:**
- `DEPLOY.md` — added `## Running without the host services` section (runbook, variable table, per-service change descriptions, Operator run result placeholder); patch: removed `cost.trace_url null` from Gateway-disabled parenthetical
- `host/README.md` — added optional-services note to "Running both in Docker" section
- `backend-api/tests/unit/test_off_mode_runbook.py` — NEW: four tests asserting runbook heading and variable/log-event names match source (`settings.py`, `main.py`)
- `web-client/tests/unit/run-cost-block-off-mode.test.ts` — NEW: two describe blocks pinning null-trace and provisional-cost behaviors in CostBlock
- `web-client/tests/unit/runs-history-table-off-mode.test.ts` — NEW: two tests for agent row with `trace_url: null` — EMPTY_CELL present, no noreferrer anchor

**Review findings:** 1 medium patch applied (see Review Triage Log); 5 low items deferred; no intent gap; no bad spec; no high findings → `followup_review_recommended: false` (score = 1, threshold = 5).
