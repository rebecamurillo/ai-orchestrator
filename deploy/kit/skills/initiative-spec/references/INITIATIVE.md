---
initiative: stats-area
phase: 6-projection
branch: feat/initiative-stats
flavor: initiative-hub@1
autonomy: assisted
artifacts:
  context: CONTEXT.md
  research: research/market-2026-10.md
  prd: PRD.md
  ux: UX-SPEC.md
  architecture: ARCHITECTURE.md
  epics: epics.yaml
open_questions: []
decisions:
  - date: 2026-10-01
    what: Statistics ships read-only; no export in this initiative.
    why: Export needs a billing decision the user has not taken; it would block epic 1.
gate:
  verdict: pending
  checked_at: null
runs: []
commands_verified:
  - epic: "1"
    kind: install
    workdir: repos/application
    command: "cd repos/application/client && yarn install"
    exit: 0
    seconds: 94
    at: 2026-10-01T09:12:04Z
  - epic: "1"
    kind: test
    workdir: repos/application
    command: "cd repos/application/client && yarn test --watchAll=false"
    exit: 0
    seconds: 38
    at: 2026-10-01T09:13:51Z
---

# Initiative — stats-area

One paragraph: what this initiative is for, in the user's own terms. Nothing else. The
requirements live in `PRD.md`, the invariants in `ARCHITECTURE.md`, the contract the Run
executes in `epics.yaml` and each `<spec_folder>/SPEC.md`.

## Status

What the current phase is waiting on, in one or two lines, and the link to the Run once
one exists. Rewritten each phase, never appended to.

---

This file is the **template** for `<initiative_folder>/INITIATIVE.md`. Copy it, replace the
values, keep the keys.

## The contract

**State and pointers, never content.** Nothing downstream reads this file for
requirements; a copy of the PRD here is a second source of truth that will disagree with
the first. Commit it with every step that changes it: the state on the branch is the state.

| key | type | contract |
| --- | --- | --- |
| `initiative` | string | the initiative's slug; matches the folder name |
| `phase` | enum | `0-context` `1-intake` `2-requirements` `3-ux` `4-architecture` `5-breakdown` `6-projection` `7-gate` `ready` — what a resume reads, and the only place it reads it |
| `branch` | string | the one initiative branch, shared by the hub and every member submodule |
| `flavor` | string | `name@version` of the template this folder is authored for, as discovered at the last gate. A record, not a pin: step 7 re-discovers the version every time |
| `autonomy` | enum | `supervised` `assisted` `auto` — read by `initiative-run` to choose which parks it may answer. `assisted` is the default; `auto` requires `open_questions: []` |
| `artifacts` | map | key → path. Relative to the initiative folder when the file lives there, otherwise repository-relative. `null` for a step deliberately skipped (`ux: null` when no UI is in scope) |
| `open_questions` | list of strings | what you could not close. **`[]` is a precondition of the gate**; it is never emptied by deciding for the user |
| `decisions` | list of `{date, what, why}` | every decision that closed a step, and every deliberate omission (a skipped UX step, an omitted `quality_gate`) |
| `gate` | `{verdict, checked_at}` | `pending` \| `PASS` \| `FAIL`, and the ISO 8601 UTC timestamp of the preflight that produced it. A `PASS` older than the last edit to `epics.yaml` is stale — re-run step 7 |
| `runs` | list | Run ids and their outcomes, appended by `initiative-run`; `[]` until one is launched |
| `commands_verified` | list | one entry per command executed in step 6: `{epic, kind, workdir, command, exit, seconds, at}`. `kind` is `install` \| `test` \| `quality_gate`; `command` is the **exact** string that landed in `epics.yaml`; `exit` is 0 for every command that landed |

`commands_verified` is the audit trail for the step-6 rule — no command lands in
`epics.yaml` that has not exited 0 in its own `workdir`. Step 7 cross-checks the two
files: a command in `epics.yaml` with no matching entry here, or with a non-zero `exit`,
fails the gate.
