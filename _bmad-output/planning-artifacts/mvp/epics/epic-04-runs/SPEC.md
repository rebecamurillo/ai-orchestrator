---
id: SPEC-mvp-epic-04-runs
companions: []
sources:
  - ../../prd.md
  - ../../addendum.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../architecture/research/dbos.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 4.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 4 — Plan, start, and durably execute a Run: `repo-init` end to end

## Why

The vision to realise: a Run is planned completely before it starts, executed by a durable engine one row at a time, parked for the Operator only where declared, and visible as one honest readout. This epic builds that machine without the agent step: the domain model and its two status writers, the pure planner, pre-flight, the DBOS engine behind its port, the process, workspace, and git adapters, every non-agent step kind, the repository lock and queue, the signals endpoint with cancel, retry, and continue, and the screens that show a Run (New workflow, Board, Run detail, Runs queue). The first Run to reach `done` is `repo-init@1`, initialising a Repository for the method and returning a compare link.

## Capabilities

- **CAP-1** Run domain model and status machines — entities `Run`, `StepRun`, `Attempt`, `GateRecord`, the two state machines, repository ports, migrations. **success:** every transition of the spine's two diagrams is a unit-tested pure function; unknown transitions raise.
- **CAP-2** Pure planner — `plan_run` expands a pinned Template tree into rows from the remote branch at one commit. **success:** `repo-init@1`, `epic@1`, and `initiative@1` expand to the expected rows, paths, labels, gates, and skipped reasons on a fake `Git`.
- **CAP-3** Pre-flight — every FR-8 check as a line, plus *What will run*. **success:** `POST /runs/preflight` returns the lines, `start_allowed`, the queue note, and the rows the planner would persist.
- **CAP-4** Create and enqueue a Run — rows persisted in one transaction, versions pinned transitively, enqueued behind the repository partition. **success:** `POST /runs` returns whether the Run starts now or waits behind a named Run; `pinned_by` counts appear on Template versions.
- **CAP-5** Status writers — `start_attempt`, `apply_step_result`, `signal_run` are the only writers of Run, Step, Attempt, and gate-record state. **success:** 100 % branch coverage; every operator signal is validated against the AD-13 table and refused with 409 otherwise.
- **CAP-6** Durable engine adapter and walker — DBOS behind `WorkflowEngine`, one queue partitioned by Repository, human waits as one `recv`, scheduled jobs. **success:** a Run survives a process restart without repeating a completed row; two Runs on one Repository serialise; parked Runs hold their slot.
- **CAP-7** Process, workspace, and basic step kinds — `ProcessRunner`, `Workspace`, executors `plan.check`, `shell`, `checkpoint` with timeouts and logs. **success:** a shell row records its output and exit code; an expired `timeout_min` kills the process group and parks `timeout`.
- **CAP-8** Git step kinds — `git.worktree` (with `install_command`), `git.sync`, `git.commit`, `git.push`, `pr.link`, `bmad.install`. **success:** `repo-init@1` runs worktree → install → commit → push → link on a local remote and records the compare URL.
- **CAP-9** Signals: cancel, retry, continue — endpoint and effects. **success:** cancel kills processes, removes worktrees, deletes never-pushed branches; retry re-runs the errored row; continue resolves checkpoint and `plan_stale` stops.
- **CAP-10** Repository initialisation from the Project screen — `POST /repositories/{id}/init` and the row action. **success:** the Repository row links to the Run, then to its compare link; the method cell reads the new version after the next clone check.
- **CAP-11** Queue read model and scheduled jobs — `GET /queue` from the engine port; `clone_check` daily; `worktree_gc` at 7 days. **success:** queue reasons match the fixed set; a terminal Run's worktree disappears after 7 days.
- **CAP-12** Run read models — board cards, full detail, run graph with group statuses. **success:** one request per screen; the run graph's group tokens follow the one rule.
- **CAP-13** New workflow screen — form, pre-flight, *What will run*, start. **success:** matches the experience spec; a failing line disables *Start run* with the fix.
- **CAP-14** Board with polling and the failed-fetch readout. **success:** five columns always rendered; polling 5 s / 30 s; no content moves under the cursor.
- **CAP-15** Run detail core — header, banner, Steps table, gate record, cost block, links, Cancel confirm, Retry and Continue bodies. **success:** every planned row is visible from the start; the words `skipped` and `unvalidated` are never green.
- **CAP-16** Runs screen queue section. **success:** position, reason, and waiting time per queued Run; parked Runs at `—`.
- **CAP-17** Durability proof — the restart and orphan test. **success:** killed mid-step and restarted, the Run resumes at that row and exactly one process for it exists afterwards.

## Constraints

- A Run is planned completely, purely, from the remote branch at `plan_ref`, before enqueue (AD-7); the walker executes only existing rows in `seq` order; re-execution is a new attempt on the same row.
- Exactly two writers of execution and operator state (AD-8); executors return results and never touch status.
- The engine is a port; DBOS appears only in `infrastructure/dbos/`; `engine_ref` is opaque JSON (AD-6).
- The repository lock is the queue partition, held for the Run's whole life including `needs_you` (AD-12).
- Every filesystem, git, and process side effect goes through `Git`, `Workspace`, `ProcessRunner` (AD-14); the process runner owns every timeout.
- Credentials per AD-5: `GITHUB_TOKEN` via `GIT_ASKPASS` only; nothing else reaches a child process beyond the Project's env vars and the minimum PATH/HOME.
- API, contract, UI, signal, and voice conventions of Epics 1–3 apply; screens read one endpoint each and aggregate nothing.
- Tests first; fakes shared; 100 % branch on status machines, `signal_run`, `apply_step_result`.

## Non-goals

- No `agent` step, no harness process, no tracing, no spend, no budget, no protected paths (Epic 5); the `agent` executor is registered as a stub that parks `misconfigured: agent step not available yet`.
- No answer, skip, budget raise, accept, or terminal signals (Epic 6); `signal_run` validates them but their effects are absent.
- No history table (Epic 7), no run diagram screen (Epic 8; the graph endpoint ships here).

## Success signal

From the Projects screen the Operator clicks *Initialise repository* on a repository whose method is `missing`; a `repo-init` card appears on the Board, moves from `Queued` to `Running` to `Done`, its detail lists `plan · checkout · install · commit · push · link` all `DON`, and the compare link opens GitHub on `main...chore/bmad-init`. Restarting the backend in the middle of `install` resumes at `install` without repeating `checkout`.
