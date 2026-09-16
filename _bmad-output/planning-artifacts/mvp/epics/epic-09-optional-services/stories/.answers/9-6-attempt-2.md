---
title: 'Running without the host services, proven and documented'
type: 'feature'
created: '2026-09-13'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: '98a6f30bd29dafc24ae43f4855c70e9228752930'
---

<intent-contract>

## Intent

**Problem:** An Operator who wants to run the stack with both host services blanked has no runbook stating what changes, no UI tests pinning the null-trace and provisional-cost behaviors, and no code-check that will catch a variable or log-line rename after the runbook is written.

**Approach:** Add a "Running without the host services" section to `DEPLOY.md` (and a matching note to `host/README.md`) documenting the two switches, what each disabled service costs the Operator, and what to supply instead; add vitest tests pinning the null-trace and provisional-cost behaviors in CostBlock and HistoryTable; add a backend unit test that asserts the variable names and log event strings in the runbook match the source code; then HALT blocked naming the exact commands the Operator must run and the facts to report back, since AC 5 requires a real Run and its result recorded in `DEPLOY.md`.

## Boundaries & Constraints

**Always:**
- The runbook documents `LITELLM_BASE_URL` / `LANGFUSE_BASE_URL` as the only switches; `"gateway disabled"` / `"tracing disabled"` are the exact log event strings (from `main.py:339,341`) and the runbook states both; the backend test pins both by reading two committed files.
- No credential value appears in the runbook, in any log line documented there, or in the test (hard rule 5, AD-5).
- `src/api/schema.d.ts` is generated — never hand-written; `trace_url: string | null` and `cost_provisional: boolean` already exist (AD-3). No new API field, no schema change.
- Web-client tests use `renderToStaticMarkup` + vitest, placed as new files in `web-client/tests/unit/`; do not modify any existing test file.
- The backend runbook-claims test reads `DEPLOY.md` and source files to assert specific names and log strings; it does not test prose or section layout.
- Anything not in the Operator's reported result is written as "not observed" — no fabrication.

**Block If:**
- A change would require a new API payload field or a schema edit → halt naming AD-3.
- This story uncovers a defect in 9-1 … 9-5 → halt naming the earlier story, not fixing it here.
- All code tasks are done and gates pass: HALT with status `blocked`, blocking condition as described under the final task below — the Operator's run is required before the story can reach `done`.

**Never:** Edit any existing test file. Print or store a credential anywhere. Add a `*_ENABLED` environment variable. Infer or fabricate facts the Operator did not report.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Null trace_url, CostBlock | `cost.trace_url: null` | No `<tr>` for trace; no "open in Langfuse"; no placeholder | No error |
| Provisional cost, CostBlock | `cost.provisional: true` | `data-testid="wf-cost-provisional"` present; "provisional" beside the ratio | No error |
| Null trace_url, HistoryTable | `trace_url: null` on a normal agent row | Trace cell renders `—`; no `rel="noreferrer noopener"` anchor in that cell | No error |
| Runbook names match code | `DEPLOY.md` + `settings.py` + `main.py` | `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL` in both the runbook section and `settings.py`; `"gateway disabled"`, `"tracing disabled"` in both the runbook section and `main.py` | `AssertionError` on mismatch |

</intent-contract>

## Code Map

- `DEPLOY.md:394` — end of file; new `## Running without the host services` section appended here; the backend runbook test locates it by finding this heading
- `host/README.md:19-25` — "Running both in Docker on this machine — optional" section; add a note that both services are themselves optional — blank `LITELLM_BASE_URL` / `LANGFUSE_BASE_URL` in `.env` runs without them; the host stack is optional even relative to itself
- `web-client/src/components/run/CostBlock.tsx:38-40` — `cost.provisional` conditional renders `<span data-testid="wf-cost-provisional"> provisional</span>` (READ-ONLY); new test pins this
- `web-client/src/components/run/CostBlock.tsx:55-64` — `cost.trace_url` truthy conditional emits the trace row; null → row absent entirely (READ-ONLY); new test pins this
- `web-client/src/components/runs/HistoryTable.tsx:74-81` — `row.trace_url` truthy → `<a rel="noreferrer noopener">` with `TRACE_LINK_TEXT`; null → `EMPTY_CELL` ("—") (READ-ONLY); new test pins this
- `web-client/src/lib/runs/history.ts:49,52` — `EMPTY_CELL = '—'`; `TRACE_LINK_TEXT = 'trace'`
- `web-client/tests/unit/run-cost-block-provisional.test.ts` — ANCHOR READ-ONLY; already covers provisional marker and null-trace scenarios; new file adds off-mode-attributed coverage
- `web-client/tests/unit/runs-history-table.test.ts` — ANCHOR READ-ONLY; covers trace_url null in a composite multi-null-field scenario; new file isolates the single-null case
- `backend-api/src/orchestrator/infrastructure/settings.py:127,147` — fields `litellm_base_url: str` and `langfuse_base_url: str` (env var names are their uppercase equivalents)
- `backend-api/src/orchestrator/main.py:339,341` — `log.warning("gateway disabled", spend="provisional")` and `log.warning("tracing disabled", traces="absent")`
- `backend-api/tests/unit/test_off_mode_runbook.py` — NEW: `PROJECT_ROOT = Path(__file__).parent.parent.parent.parent`; reads `DEPLOY.md` (asserts heading present, variable names and log strings appear in section); reads `settings.py` (asserts field names); reads `main.py` (asserts log event strings)

## Tasks & Acceptance

**Execution (TDD — write tests first; the backend runbook test fails until the DEPLOY.md section is written; web-client tests pass immediately since the components are already correct from 9-2):**
- `backend-api/tests/unit/test_off_mode_runbook.py` — CREATE: `PROJECT_ROOT = Path(__file__).parent.parent.parent.parent`; define `RUNBOOK_HEADING = "Running without the host services"`; in each test, read `DEPLOY.md`, assert heading present, slice to the section text, then assert the specific string is in section text; four tests: `test_runbook_names_litellm_base_url` (section contains `LITELLM_BASE_URL` AND `settings.py` contains `litellm_base_url`), `test_runbook_names_langfuse_base_url` (same for langfuse), `test_runbook_log_gateway_disabled` (section contains `gateway disabled` AND `main.py` contains `"gateway disabled"`), `test_runbook_log_tracing_disabled` (same for tracing)
- `web-client/tests/unit/run-cost-block-off-mode.test.ts` — CREATE: same helper pattern as `run-cost-block-provisional.test.ts` with a `detail(costOverrides)` function; test `trace_url: null` → `not.toContain('data-testid="wf-trace"')` and `not.toContain('open in Langfuse')`; test `provisional: true` → `toContain('data-testid="wf-cost-provisional"')` and `toContain('provisional')`
- `web-client/tests/unit/runs-history-table-off-mode.test.ts` — CREATE: same `row()` helper as `runs-history-table.test.ts`; import `EMPTY_CELL` from `../../src/lib/runs/history`; test `row({ trace_url: null })` (all other fields including cost_usd and harness non-null) → `toContain(EMPTY_CELL)` and `not.toContain('rel="noreferrer noopener"')`
- `DEPLOY.md` — ADD `## Running without the host services` section at the end; content must include: `LITELLM_BASE_URL` (blank disables Gateway, unset refuses), `LANGFUSE_BASE_URL` (blank disables tracing, unset refuses); with Gateway off: harness authenticates from its own login in the `agent-home` volume (`claude login` inside the container) or from a Project variable; cost is the harness's own provisional figure; `local` is unavailable (gateway disabled); with tracing off: no traces, no trace links, `cost.trace_url` null; stack logs `"gateway disabled"` and `"tracing disabled"` at startup; no step prints or stores a credential; end with `### Operator run result` subsection as a placeholder for the recorded result
- `host/README.md` — ADD to the "Running both in Docker on this machine — optional" section: a note that `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` can each be set to blank in `.env` to disable the respective service entirely; the full "Running without the host services" runbook is in `DEPLOY.md`
- **HALT blocked** — after all code tasks are complete and `make lint && make test && make e2e-ui` pass, HALT with status `blocked` and blocking condition: `"Operator run required: (1) in .env set LITELLM_BASE_URL= and LANGFUSE_BASE_URL= (blank, not deleted); (2) log in the harness — either docker exec -it <backend-api-container> claude login (interactive terminal required) or create a Project with ANTHROPIC_API_KEY set; (3) docker compose restart backend-api; (4) create a new workflow Run via the UI using the claude harness; (5) let a story run to done. Report back: which harness and which auth method; that backend-api startup logs showed 'gateway disabled' and 'tracing disabled'; that New workflow offered claude and codex but refused local with a stated reason; that a Story reached done; and what the Run detail showed for cost (was the 'provisional' marker present?) and for the trace row (was it absent?). Record nothing that was not observed."`

**Acceptance Criteria:**
- Given a run-detail read model whose `cost.trace_url` is `null`, when the cost block renders, then no trace row and no "open in Langfuse" link is present, and no placeholder stands in for it
- Given a history row whose `trace_url` is `null`, when the table renders, then the trace cell holds "—" with no link, and nothing reads as an error
- Given a cost whose figure is provisional, when the cost block renders, then the word "provisional" is beside the figure, and no copy congratulates or apologises
- Given the runbook, when its claims are checked against source by the backend test, then `LITELLM_BASE_URL` and `LANGFUSE_BASE_URL` in the runbook match field names in `settings.py`, and `"gateway disabled"` and `"tracing disabled"` in the runbook match log events in `main.py`
- Given the Operator's report, when it is recorded in `DEPLOY.md`'s `### Operator run result` subsection, then `DEPLOY.md` names the harness, the mode and the date, and states plainly anything that did not work

## Design Notes

The backend runbook test locates the section by finding the heading string in `DEPLOY.md` and slicing from there, so it is resilient to the section's position in the file. It asserts specific names and log strings — not prose — so rewording the section does not break it, but renaming a field or log event does.

The web-client tests deliberately live in new files even though `run-cost-block-provisional.test.ts` and `runs-history-table.test.ts` already cover the same behaviors. The new files explicitly attribute the off-mode coverage to this story, so a future refactor of the general component tests cannot accidentally lose the off-mode reading.

For HistoryTable, the new test uses an otherwise-normal agent row (`harness: 'claude'`, `cost_usd: '0.42'`, all non-null except `trace_url`) to isolate the trace-null case. The existing test uses a `git.commit` row with multiple null fields; the new test proves the behavior holds for agent attempts specifically.

## Verification

**Commands:**
- `make lint && make test && make e2e-ui` -- expected: zero violations; all pytest and vitest tests green including new `test_off_mode_runbook.py`, `run-cost-block-off-mode.test.ts`, `runs-history-table-off-mode.test.ts`; anchor tests in `run-cost-block-provisional.test.ts`, `runs-history-table.test.ts` still green

## Auto Run Result

Status: blocked
Blocking condition: Operator run required: (1) in `.env` set `LITELLM_BASE_URL=` and `LANGFUSE_BASE_URL=` (blank, not deleted); (2) log in the harness — either `docker exec -it <backend-api-container> claude login` (interactive terminal required) or create a Project with `ANTHROPIC_API_KEY` set; (3) `docker compose restart backend-api`; (4) create a new workflow Run via the UI using the claude harness; (5) let a story run to done. Report back: which harness and which auth method; that backend-api startup logs showed `"gateway disabled"` and `"tracing disabled"`; that New workflow offered claude and codex but refused local with a stated reason; that a Story reached done; and what the Run detail showed for cost (was the `"provisional"` marker present?) and for the trace row (was it absent?). Record nothing that was not observed.

Verification result (2026-09-14): make lint passed (0 errors); make test passed (6129 pytest, 103 vitest files / 1293 tests); make e2e-ui 163 passed, 1 pre-existing failure (run-detail-skip-story.spec.ts:121, last modified story 6-4, unrelated). All four new tests ran and passed. Matrix Test Audit: all four I/O matrix rows covered by new tests.

## Human Answer

2026-09-14T05:17:14.589632Z · operator

human will test after story is done. no need to run real test on your side, since requires modifying env variables in your sandbox, to be done by human. continue and finish the story so pipeline can continue to next step
