---
story: "5-5"
epic: 5
title: Agent executor — contract evaluation and routing
requirements: [FR-10 (verify redispatch), FR-16, NFR-2, AR-13 (routing)]
binds: [AD-8, AD-9, AD-10, AD-13 (retry archive)]
---

# Story 5.5 — Agent executor: contract evaluation and routing

As the Operator,
I want the story file the agent wrote to be the only thing that decides what happens next, by rules I can read,
So that a harness's exit code, its output, or its mood never counts as done.

## Scope

**In:** `application/rules/routing.py`, the executor tail `_tail` for liveness, configuration failures, routing, `expect` + `retry`, the Retry-time de-ambiguation archive, the `## Verify Failure` append on a redispatched attempt, tests with 100 % branch coverage.
**Out:** protected paths (5.6, called first in the tail — leave the call), spend and budget (5.7, called last — leave the call).

## Binding rules (inlined)

- **Tail order (AD-9):** protected-path check (5.6) → routing (this story) → spend + budget (5.7). This story implements `_tail` with the two seams as no-ops.
- **Liveness (FR-16).** `Workspace.glob("{spec_folder}/stories/{id}-*.md")`: exactly one file with parseable YAML frontmatter containing `status` → proceed; zero → `StepResult(error, park Park{misconfigured, "no story file"})`; several → `Park{misconfigured, "ambiguous story file: {names}"}`; unparseable → `Park{misconfigured, "no story file: frontmatter unreadable in {name}"}`. On a `retry` resume after `ambiguous story file` the prepare phase (5.4's `_prepare_writes`) archives every matching file except the newest (by mtime, then name) to `stories/.answers/{name}` before dispatch — implement that hook here.
- **Configuration failures.** `status: blocked` whose `## Auto Run Result` `Blocking condition:` line is one of `no subagents`, `no stories.yaml found`, `story id not found in stories.yaml`, `version-control metadata not writable`, `no epic spec found`, `unrecognized status in existing story file`, `ambiguous story file match` → `Park{misconfigured, "harness misconfigured: {condition}"}`; no Answer is offered (the UI reads `park_kind`).
- **Routing on `status`:**
  - `done` → `StepResult(done, gate liveness)` (the verify row decides green);
  - `blocked` (not a configuration condition) → `StepResult(blocked, park Park{blocked, <the whole "## Auto Run Result" section text>})`; the reason text is the section verbatim, attributed in the read model with harness, model, and time;
  - `ready-for-dev` with `with_resolved.spec_checkpoint` → `StepResult(checkpoint, park Park{checkpoint, "spec checkpoint"})`;
  - `ready-for-dev` without spec checkpoint, `draft`, `in-progress`, `in-review`, or an unknown status, or `exit_code ≠ 0` with a `done` file → **retry path**: if `row.retry_count < retry.max` → return `StepResult(error, reason "unexpected status: {status}" | "harness exit {code}", retry=Retry{prompt: retry.prompt, resume_session})` — `apply_step_result` (extend 4.5 by a small edit here) increments `retry_count`, writes gate record `retry_auto` (`text: "{reason} · retry {n}/{max}"`), and re-queues the row; the next attempt's dispatch uses `harness.resume(session_id, retry.prompt)` when `resume_session` and the harness supports it, else a new session with the prompt prepended; when exhausted → `Park{misconfigured, "unexpected status: {status}"}` / `Park{misconfigured, "harness exit {code}"}`.
- **Verify redispatch (FR-10).** When the executor runs because a `verify` row redispatched it (`ctx.resume_signal is None` and `row.redispatch_count > previous`), `_prepare_writes` appends to the story file a section `## Verify Failure` with `Command: {quality_gate_command}`, `Exit code: {n}`, and the last 200 lines of the verify log, and sets the frontmatter `status: in-progress`; the prepare commit includes it; the prompt is the plain dispatch prompt (build-auto routes `in-progress` to implementation).
- **Every stop maps to one park kind** of the §4.6 table; `reason` texts are verbatim as above.
- **Never automatic:** `blocked`, `misconfigured`, `timeout`, `protected_path`, `internal`, `budget` are never retried by the executor.
- **Gate strength:** the row's gate stays `liveness`; the read model never shows a story step green.

## Acceptance criteria

**Given** a story file with `status: done`
**When** the tail runs
**Then** the result is `done` with gate `liveness` and no park.

**Given** `status: blocked` with `Blocking condition: intent gap` and questions listed
**When** the tail runs
**Then** the result is `blocked` with park `blocked` whose reason is the exact `## Auto Run Result` section text.

**Given** `status: blocked` with `Blocking condition: no subagents`
**When** the tail runs
**Then** the park is `misconfigured` with `harness misconfigured: no subagents`.

**Given** `status: ready-for-dev` and `spec_checkpoint: true`
**When** the tail runs
**Then** the result is `checkpoint` with reason `spec checkpoint`; with `spec_checkpoint: false` and `retry_count 0 < max 2` → `error` carrying the retry prompt; with `retry_count 2` → park `misconfigured · unexpected status: ready-for-dev`.

**Given** exit code 1 with a `done` file
**When** the tail runs
**Then** the retry path applies with reason `harness exit 1`.

**Given** zero, two, or an unparseable story file
**When** the tail runs
**Then** the parks are `no story file`, `ambiguous story file: a.md, b.md`, `no story file: frontmatter unreadable in a.md`; **and** on `retry` after the ambiguous case the older file is archived to `stories/.answers/` before dispatch.

**Given** a redispatched attempt after a verify failure
**When** the prepare phase runs
**Then** the story file has `status: in-progress` and a `## Verify Failure` section with the command, exit code, and log tail, committed in the prepare commit.

**Given** the coverage report
**When** run
**Then** `rules/routing.py` and the tail are at 100 % branch coverage.

## Implementation notes

- `rules/routing.py::route(story_file: StoryFile | None, files: [str], exit_code, spec_checkpoint, retry_count, retry) -> StepResult` pure; `StoryFile{path, status, auto_run_result: str, blocking_condition: str | None}` parsed by `application/story_file.py` (frontmatter + section extraction, unit-tested).
- `StepResult.retry: Retry | None` added to the value object; `apply_step_result` handles it (small, covered edit).
- Log tail helper from 4.12.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-16 (verbatim rules), FR-10 (redispatch), §4.6 table. Spine AD-9 (bounded re-execution), AD-13 (retry de-ambiguation), AD-8. `bmad-build-auto` HALT conventions (`## Auto Run Result`, `Blocking condition:` line, `status` values). `addendum.md` §D, §G.
