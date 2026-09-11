# Brownfield — the abandoned first attempt, and what the engine already provides

State as of 2026-09-11. `feat/improve-init-and-quality-checks` (= `main` + `f79a2a1..5cce5ab`) fails its own quality checks and is **abandoned as read-only reference**: consult it for design shapes and pitfalls, never cherry-pick from it. The fresh build starts from `main`, where **none** of the below is landed.

## Already provided by the engine on `main` (reuse, do not rebuild)

- **Verify-failure context (CAP-2):** a `verify` redispatch already writes a `## Verify Failure` block — command, exit code, log tail — into the Story file at `in-progress` (FR-10, `application/story_file.py::after_verify`, `steps/agent.py::_verify_failure`). The CAP-2 delta is the investigate-and-fix framing sentence, nothing structural.
- **Human reply loop (CAP-1):** the Epic 6 Answer path (FR-18, `steps/agent_answer.py`) archives the previous output, redispatches fresh, and puts the Operator's reply in the prompt. Multiple rounds are inherent — each dispatch may block again. It is keyed on Story files (`stories/{id}-*.md`, the `Blocking condition:` line); CAP-1's output-file contract is its frameless equivalent.
- **Bounded retries, escalation, checkpoints:** template-declared `retry`/`on_fail`/`escalate_when`/`pause_when` plus the AD-13 signals table.
- **Repository commands:** `install_command`, `unit_test_command`, `quality_gate_command` all exist on `domain/entities/repository.py`.

## What the abandoned branch attempted (reference only)

| Attempt | Where it sits on the branch |
| --- | --- |
| `context` agent step (`bmad-project-context`, `writes: ["AGENTS.md"]`, `escalate_when: output.status == blocked`) + `context-review` checkpoint | `templates/repo-init.yaml` |
| Frameless dispatch: agent row with no Story behind it plans without an invented `expect` contract; frameless stops offer no dead skip buttons | `agent_row.py`, `agent_tail.py`, `rules/signals.py`, tests `test_frameless_dispatch_contract.py`, `test_admitted_signals_outside_a_frame.py` |
| Story `verify` → `unit_test_command`; epic `setup` (install) / `baseline` (unit) / `e2e` (quality gate, 45 min) | `templates/story.yaml`, `templates/epic.yaml` |
| `skipped · no <field>` reasons naming the missing Repository command | `application/templates/skip_reason.py` |
| Unit exemplar freeze: content coverage on `tests/unit/application/templates/fixtures/exemplars/`; real `templates/` read only by invariant/property tests | commit `5cce5ab` |

## Known defects of the attempt (why it was abandoned, and what the fresh build must not repeat)

1. Its quality checks fail; the Operator suspects regressions or false negatives from the test restructure — the reason nothing is cherry-picked and story 1 re-derives the strategy through TDD.
2. The blocked→reply loop was never closed for the frameless `context` row: `escalate_when: output.status == blocked` had no status to read (no Story file), so the only stop was the unconditional checkpoint and a reply had no channel back into a redispatch.
3. The context prompt carried none of the required contract (`args: {intent: setup, target: "."}` only).
4. The epic `e2e` step had no `on_fail` — failure escalated to the Operator; no fix agent existed. The DSL redispatch rule (`model.py::BAD_REDISPATCH`: earlier agent steps only) and the Story-file-bound FR-10 write were never reconciled with a gate-level fixer.
5. Its e2e tests pin shipped template content (`tests/e2e/test_repo_init.py::ROWS`, `STOP_ROW`): the exemplar-freeze rule was applied to unit tests only, so the next template edit breaks e2e — CAP-4 closes this half too.

## Epic 8 overlap assessment

Epic 8 (readouts) runs off `main` in parallel and changes no Run execution. Real overlap with this work: `tests/unit/test_run_router.py` / `test_runs_router.py` (both sides may touch), the graph area (8-1 renders `GET /runs/{id}/graph`; graph tests must not assert shapes over *shipped* templates or they re-create the pinning CAP-4 removes), and e2e suite growth. No overlap in `templates/`, `steps/`, or the signals machinery. Epic 8 merges first; this branch rebases and merges after.
