---
story: "4-17"
epic: 4
title: Durability proof — restart and orphan test
requirements: [FR-12, NFR-1, SM-4]
binds: [AD-6, AD-8, AD-14]
---

# Story 4.17 — Durability proof: restart and orphan test

As the Operator,
I want a repeatable test that kills the orchestrator in the middle of a Run and proves it resumes at the same row with exactly one process,
So that "runs survive restart" is measured (SM-4), not promised.

## Scope

**In:** an e2e scenario in `tests/e2e/test_durability.py` runnable against the compose stack (`make e2e-api` marker `durability`), a `make durability` target, a short section in the root `README.md` on how to run it, and any small fix it uncovers in 4.6–4.8.
**Out:** new features.

## Binding rules (inlined)

- **Scenario.** On the local remote, create a Repository whose `install_command` is `sleep 120` (so `git.worktree` of `repo-init@1` runs long enough), start a `repo-init` Run, wait until the `checkout` row is `running` with an Attempt and a recorded `pgid`; `docker compose kill backend-api` (SIGKILL); assert the child `sleep` process is orphaned or gone as the container restarts (`docker compose up -d backend-api`); wait for the Run to end `done`.
- **Assertions (FR-12).** Rows completed before the kill (`plan`) have exactly one Attempt and are not re-executed; the interrupted row has Attempt 1 `error · interrupted` and Attempt 2 `done`; after restart at most one process group for the Run exists at any time (`docker compose exec backend-api ps -o pgid,cmd` filtered on the worktree path); the gate record shows `start` once and `done` once; `run.worktrees` has one entry.
- **Second scenario.** Kill while the Run waits in `recv` on a `checkpoint` row (use `epic@1` on a Repository with a `stories.yaml` whose single story has `done_checkpoint: true` and an already-`done` story file so no agent row runs); restart; signal `continue`; the Run finishes with no repeated row.
- **Timing:** the whole test under 5 minutes; use `HUMAN_WAIT_SECONDS` default (the wait is resumed by the signal, not by expiry).

## Acceptance criteria

**Given** the compose stack
**When** `make durability` runs
**Then** both scenarios pass with the assertions above, and the output prints the attempt table of each Run.

**Given** the CI workflow
**When** it runs on the epic's final commit
**Then** the durability marker runs in the `e2e-api` job (or a dedicated job) and passes.

## Implementation notes

- Helpers: `wait_for_row(run_id, path, status)`, `pgids_for(run_id)` via `docker compose exec`; the test drives compose through `subprocess` from the host side (allowed in tests).
- Record any adapter fix under the story's Auto Run Result so the retrospective sees it.

## Verification

```bash
make up && make durability
```

## Sources for detail only

PRD FR-12 (test sentence: "kill the orchestrator mid-Story, restart — exactly one Harness process for that Run exists afterwards"), SM-4, NFR-1. Spine AD-6, AD-14.
