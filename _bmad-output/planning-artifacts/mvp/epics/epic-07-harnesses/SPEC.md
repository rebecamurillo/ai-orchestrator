---
id: SPEC-mvp-epic-07-harnesses
companions: []
sources:
  - ../../prd.md
  - ../../addendum.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../architecture/research/tracing.md
  - ../../architecture/deliverables/scripts/harness/
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 7.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 7 — Codex and local harnesses, cost and time per Story

## Why

An opportunity: the three-harness design exists to compare cost, time, and outcome per story across Claude Code, Codex, and an open-weight model served locally (SM-3). This epic adds the two remaining adapters behind the same port and the same readiness gate, joins their traces and spend to the Run the way each harness allows, and completes the two readouts that make the comparison readable: the Runs history and the trajectory export.

## Capabilities

- **CAP-1** Codex adapter and script — `codex exec` with session capture, `danger-full-access`, headers by env name, OTLP traces. **success:** the contract test passes for `codex`; the adapter returns `HarnessResult` with the captured session id.
- **CAP-2** Codex readiness passes end to end — `TRACEPARENT` honoured or the documented fallback. **success:** `codex · enabled` on the real host; the addendum records the invocation and the trace result.
- **CAP-3** OpenCode adapter and script (`local`) — `opencode run --format json`, config-driven permissions, the Langfuse plugin keyed by the Run id, `LOCAL_MODELS`, cost `0` with tokens. **success:** the contract test passes for `opencode`; `attempt_observed` finds generations by user id.
- **CAP-4** OpenCode readiness passes end to end with host model serving. **success:** `local · enabled` on the real host with a local model; the addendum and `host/README.md` record the setup, or the documented fallback is recorded.
- **CAP-5** Runs history — `GET /steps` and the **HISTORY** table, one row per attempt, paginated. **success:** every execution of every step is a row with harness, session, tokens, cost, and trace link; rows link to the Run detail at the path.
- **CAP-6** Trajectory export — `GET /projects/{id}/trajectories.jsonl` and *Export trajectories*. **success:** a JSON-lines file, newest first, one line per done story with the fields SM-1 and SM-3 need.

## Constraints

- One port, one adapter per harness, `env_for` equal to the scripts' lists, no model-output parsing (AD-10).
- One exporter per harness; `codex` parented by `TRACEPARENT` where honoured, `local` found by user and session id (AD-11).
- Readiness gates every harness the same way (FR-33); `enabled` is read only by `create_run` and pre-flight (AD-10).
- Local models are recorded as cost `0` with tokens (PRD §11).
- Read models, tokens, and voice conventions of Epics 4–6 apply.

## Non-goals

- No per-Project harness defaults, no model routing rules, no comparison dashboard (the trajectory export is the comparison's input).
- No session resume across containers.

## Success signal

The same fixture story runs to `done` on `claude`, `codex`, and `local`; the Runs history shows the three attempts with their harness, tokens, and cost; the trajectory export lists three lines whose `harness`, `cost_usd`, and `wall_clock_seconds` differ; New workflow reads `enabled` on all three.
