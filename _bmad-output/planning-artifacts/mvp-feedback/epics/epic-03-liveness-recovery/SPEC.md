# SPEC — Epic 3: Runs that stall park, healthy runs finish

A healthy hour-long story runs to its end — the stall detector replaces the default hard kill and the budget cap becomes optional (`tracked, no cap`) — and when a story blocks or errors the Operator chooses reply-in-session or restart, with every retry prompt explicit in the template. Realises features F5 and F9 (IMP-003 extended to Retry).

## Authority order

1. `ARCHITECTURE-SPINE.md` (2026-09-15) — AD-8, AD-10 (resume + `reply_available`), AD-11 (nullable budget), AD-13 (`mode`, session = new Attempt), AD-14 (stall detector), AD-17. Disagreement → `blocked`.
2. `prd.md` (2026-09-15) — FR-10, FR-17, FR-18, FR-20, §4.6 stop table, NFR-8.
3. UX authority: EXPERIENCE-v1 stop table (stall reason) and cost kv (`tracked, no cap`); Answer box copy per FR-18.
4. `stories.yaml` in this folder.

## Scope

- `ProcessRunner.start(cmd, cwd, env, timeout_min?, stall_min?)`; `wait` returns `{exited(code) | timed_out | stalled}`; the stall signal is exactly no mtime change under `cwd` (`.git` included) plus no growth of the attempt log for `n` minutes; the `agent` executor composes the park (row `error`, `timeout` kind, `stalled {path}: no activity for {n} min`).
- `timeout_min` optional on `agent` steps, no default hard kill; `stall_min` default 30, template-tunable (`validate.py` accepts the key), passed only by the `agent` executor; `shell` (30) and `git.*` (5) wall clocks stay.
- `run.budget_usd` nullable; null → budget rule no-op, `tracked, no cap` on cost surfaces, `--max-budget-usd` omitted; tracking untouched and authoritative.
- `mode: restart | session` on Answer and Retry payloads; `session` requires `reply_available` (= `capabilities.resume` ∧ recorded `session_id`) else 422 naming the reason; a session delivery is a **new Attempt** on the same row — `n+1`, inherited `session_id`, `start_sha = HEAD` at delivery, `env_for` of the new Attempt, `mark_started`/`mark_finished`, protected-path check, FR-16 routing, `Gateway.spend`, budget rule; prepare commit skipped; nothing archived, no re-plan. `Harness.resume` returns a `HarnessResult`.
- UI: the mode choice offered only when `reply_available`; the box states in words what each mode does; gate record names the mode.
- Every shipped template's `retry` block declares its `prompt` explicitly.

## Out of scope

Dispatch-form DSL changes (`skill`/`prompt` — epic 4); the Step-run detail that displays retry prompts (epic 1, already landed); saved runs and dependencies (epic 5); any new status token — stall and cap conditions are reason texts under existing park kinds.

## Rules that bind every story

- Anchors read-only. **Known anchor moment:** if an existing test pins the agent 90-min default (`KIND_META`), it is revised only under the operator revision of 2026-09-15 (anchor exception 4) — the revised test names the decision and date; no other assertion may be weakened.
- TDD with the shared fakes (the `ProcessRunner` fake is extended, never duplicated); generated contract only (AD-3) for the payload change; two-writer rule untouched (`signal_run` gains a field, not a writer).
- Voice: `stalled {path}: no activity for {n} min` and `tracked, no cap` verbatim from the PRD §4.6 / FR-17 copy (NFR-8).

## Verification

`make lint` · `make test` · `make e2e-api` · `make e2e-ui` green after every story; the epic's e2e pass exercises: an agent attempt parked by the stall detector with the exact reason text, a run without budget showing `tracked, no cap` and never parking `budget`, and a 422 on `mode: session` against a non-resumable row.
