---
story: "5-6"
epic: 5
title: Protected paths
requirements: [FR-31, NFR-2, AR-13 (protected_paths)]
binds: [AD-9, AD-14, AD-17]
---

# Story 5.6 — Protected paths

As the Operator,
I want the spec, the epics list, every constitution, and every pre-existing test to be read-only to agents, checked deterministically after every attempt and at every commit-guard,
So that an agent can never make a gate pass by editing what the gate reads.

## Scope

**In:** `application/rules/protected_paths.py`, the frozen test set (computed in 5.4, consumed here), the check in the agent tail (first) and in `git.commit`, the `protected_path` park with its file list, `run.accepted_paths` exclusion, tests.
**Out:** the Accept signal effect (Epic 6).

## Binding rules (inlined)

- **Protected set per Run (AD-17):** `{spec_folder}/SPEC.md`, `{spec_folder}/stories.yaml`, `{initiative_folder}/epics.yaml` (when the Run has one), every path whose basename is `AGENTS.md` (existing or created), and every file in `frozen_test_files` of the story frame's lowest-`n` attempt that has a `start_sha` (pre-existing files matching `repository.test_globs`). Files the agent created inside the frame that match the globs are **not** protected on later attempts. The agent's own story file under `stories/` and `project-context.md` are never protected.
- **Agent ranges only.** `changed = Git.diff_names(cwd, attempt.start_sha, attempt.end_sha) ∪ Git.status(cwd)` (uncommitted, including untracked) for the agent tail; for `git.commit`: the union over every agent attempt of the frame (`diff_names(start_sha_i, end_sha_i)`) ∪ uncommitted. Operator commits (`spec: operator edit (orchestrator)`) and orchestrator commits are outside these ranges by construction.
- **Rule.** `rules/protected_paths.check(changed: [Change{path, kind: added | modified | deleted}], protected: ProtectedSet, accepted: [str]) -> [Hit]`; a hit is any change to a protected path, or an added `AGENTS.md` anywhere; paths in `accepted` are excluded. Pure, 100 % covered.
- **Park.** Any hit → `StepResult(error, park Park{protected_path, "protected path modified: {paths, comma-separated}"}, payload {hits: [{path, kind}]})`; it wins over routing (the tail returns before routing); never retried automatically. In `git.commit` a hit parks the same way before committing.
- **Accept (Epic 6 wires the signal):** when `ctx.resume_signal.kind == continue` on a `protected_path` park, the agent executor does not dispatch; it re-runs the tail over `previous_attempt`'s recorded `start_sha`/`end_sha` with `run.accepted_paths` excluded, on the same attempt number; implement the branch now so Epic 6 only adds the signal effect.
- **Record.** The hit list is written to the gate record payload by `apply_step_result` (`payload.hits`) and later to the trajectory.

## Acceptance criteria

**Given** an attempt whose range modifies `specs/x/SPEC.md`
**When** the tail runs
**Then** the result parks `protected_path` with `protected path modified: specs/x/SPEC.md` and routing is not reached.

**Given** an agent that adds `web-client/AGENTS.md`
**When** checked
**Then** it is a hit (`added`).

**Given** `frozen_test_files = ["tests/a.py"]`, the agent modifies `tests/a.py` and creates `tests/new.py`
**When** checked on attempt 1
**Then** one hit (`tests/a.py`); on attempt 2 of the same frame, a modification of `tests/new.py` is not a hit and a deletion of `tests/a.py` is.

**Given** an operator commit `spec: operator edit (orchestrator)` between attempts that changed `SPEC.md`
**When** attempt 2's range is checked
**Then** no hit (the change is outside `start_sha..end_sha`).

**Given** `run.accepted_paths = ["tests/a.py"]`
**When** the same frame's later attempt modifies `tests/a.py` again
**Then** no hit.

**Given** `git.commit` with an uncommitted change to `stories.yaml`
**When** it runs
**Then** it parks `protected_path` and commits nothing.

**Given** `continue` on a `protected_path` park
**When** the agent executor resumes
**Then** no harness call is made, the tail re-runs over the previous attempt's SHAs with the accepted paths excluded, and routing proceeds on the story file as it is.

## Implementation notes

- `ProtectedSet` built by `application/rules/protected_paths.build(run, row, frame_attempts, repository)`.
- `Git.diff_names(cwd, from_sha, to_sha) -> [Change]` (extend the port/adapter if 4.8 only returned names).
- The `git.commit` executor (4.8) already calls `ctx.ports.protected_paths.check(...)` through a seam; wire the real rule here.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-31 (verbatim), §11 Anchors. Spine AD-17 (the whole rule), AD-9 (accept path without dispatch), AD-13 (`continue` on `protected_path`). `GUIDELINES.md` §2.5.2, §2.5.4 (why anchors are frozen).
