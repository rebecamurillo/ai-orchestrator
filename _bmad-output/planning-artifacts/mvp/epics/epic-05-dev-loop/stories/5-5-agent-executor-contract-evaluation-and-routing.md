---
title: 'Agent executor — contract evaluation and routing'
type: 'feature'
created: '2026-09-08'
status: 'done'
baseline_revision: '03f42b0cc682def3d70d0dbe8879072ea1c3127d'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      A resumed dispatch records no process group, so orphan control cannot reap the
      harness a dead backend left behind mid-retry.
    evidence: |-
      `Harness.resume` is a single call with no `start`/`wait` split, so `_run`'s resume
      branch skips the `pgid` commit AD-14 requires before the process is awaited.
      `_orphan_control` returns early on `previous.pgid is None`, so an interrupted resumed
      attempt is never killed. The same call takes no `model` and no `budget_usd_remaining`,
      so a resumed retry runs with no budget signal while `_start` still records a `model`
      that was never passed. Closing this means changing the `Harness` port (5.1/5.4's), a
      structural decision this story is not authorised to make.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:_run (resume branch)
    severity: medium
  - summary: >-
      A `blocked` story file that carries no `## Auto Run Result` section parks with an
      empty reason, so the Operator is shown a Question with no text.
    evidence: |-
      `rules/routing.py::_blocked` uses `story_file.auto_run_result` verbatim as both the
      reason and `Park.reason`, and `story_file.section` answers `""` for a missing heading.
      `bmad-build-auto`'s own HALT protocol always writes the section, so this is a
      non-conforming agent rather than a shipped path; a fallback sentence is product copy
      the brief does not name.
    location: >-
      backend-api/src/orchestrator/application/rules/routing.py:_blocked
    severity: medium
  - summary: >-
      Archiving to `stories/.answers/{name}` overwrites silently when the same basename is
      archived twice, or collides with FR-18's Answer archive in the same folder.
    evidence: |-
      Both `FsWorkspace.move` (`Path.rename`) and `FakeWorkspace.move` clobber the
      destination. FR-18 archives a blocked story file to the same folder as
      `{id}-attempt-{n}.md`. The brief fixes the archived name as `stories/.answers/{name}`,
      so making it collision-safe changes a named path.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:archive_ambiguous
    severity: low
  - summary: >-
      `walk._verify_failure` takes the first row whose `on_fail` names this seq without
      checking that row actually failed, and keeps resolving the same facts on later attempts.
    evidence: |-
      Every shipped story frame has exactly one `verify` row per `agent` row, and the
      executor's `redispatched()` filter is what stops a stale value being read — but
      `RunEnvironment.verify_failure` still carries one that 5.6/5.7 could read.
    location: >-
      backend-api/src/orchestrator/application/use_cases/walk.py:_verify_failure
    severity: low
  - summary: >-
      The 5.6/5.7 seam-order test asserts on comment text through `inspect.getsource`
      rather than on behaviour.
    evidence: |-
      `test_the_two_unimplemented_checks_are_named_where_ad_9_puts_them` compares
      `body.index("5.6") < body.index("route(") < body.index("5.7")`, so it breaks on a
      rewording and passes on any file whose comments happen to be ordered. The seams are
      comments because the spec asked for them "named and empty"; 5.6 and 5.7 replace them
      with code and should replace this assertion with a behavioural one.
    location: >-
      backend-api/tests/unit/application/steps/test_agent_tail.py
    severity: low
  - summary: >-
      Nothing runs the retry loop end to end: executor -> apply_step_result -> re-queue ->
      second dispatch.
    evidence: |-
      `test_agent_tail.py` proves the executor emits a `retry` and
      `test_apply_step_result_retry.py` proves the writer counts it, but the exhaustion
      boundary is covered by two independent tests of the same number rather than by one
      walk over both.
    location: >-
      backend-api/tests/unit/application/
    severity: low
  - summary: >-
      `story_file.with_status` rewrites frontmatter by line surgery, so an oddly spelled
      key (`status : x`, `"status": x`) leaves a duplicate YAML key behind.
    evidence: |-
      It drops only lines starting with `status:` at column 0 and hoists the new one to the
      first line. A duplicate key is last-wins in YAML, so the old status could survive a
      verify redispatch. Every file `bmad-build-auto` writes uses the plain spelling.
    location: >-
      backend-api/src/orchestrator/application/story_file.py:with_status
    severity: low
---

<intent-contract>

## Intent

**Problem:** The `agent` executor dispatches a harness and then believes it: `_tail` returns
`done` for every exit, so a harness that wrote nothing, wrote two files, or crashed is
indistinguishable from one that finished the Story. FR-16 says the story file the agent wrote
is the only thing that decides what happens next.

**Approach:** A pure `application/rules/routing.py::route` over a parsed
`application/story_file.py::StoryFile`, called from the executor's tail (moved to
`application/steps/agent_tail.py` to make room in a module at its 400-line cap); a
`StepResult.retry` value the two-writer `apply_step_result` turns into a counted, recorded
re-queue; and two prepare-phase hooks — the `## Verify Failure` append after a verify
redispatch, and the de-ambiguation archive on a `retry` resume.

## Boundaries & Constraints

**Always:** the row's gate stays `ctx.row.gate` (`liveness`) on every result — a story step is
never green. Reason texts are module constants, asserted verbatim. Every stop is one `Park`
kind of PRD §4.6. `route` is pure: no ports, no clock, no I/O. Status is written only by
`apply_step_result` (AD-8) — the executor returns a value. `application/` imports no I/O
(AD-2): the story file is read through `Workspace`, the verify log through `LogReader`.
`blocked`, `misconfigured`, `timeout`, `protected_path`, `internal`, `budget` are never
retried by the executor (AD-9). Reuse the one fake per port in `tests/unit/fakes/`;
extend them only additively. `domain/` + `application/` stay at 100 % branch coverage.

**Block If:** the FR-16 table and PRD §4.6 disagree on a park kind or a reason text; a change
to `StepContext`'s field list (AD-9 closes it) turns out to be unavoidable; a second module
beyond `agent_tail.py` has to be split out of `agent.py`.

**Never:** touch `SPEC.md`, `stories.yaml`, `epics.yaml`, any `AGENTS.md`, or any test file
that already exists (`tests/unit/fakes/` may be extended additively only). Do not implement
the protected-path check (5.6) or the spend/budget read (5.7) — leave both seams named and
empty in `_tail`'s order. No new endpoint, schema, migration or UI. Do not skip, delete or
relax a failing test.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| done | one file, `status: done`, exit 0 | `StepResult(done, gate liveness, output_ref log)`, no park | none |
| blocked, intent gap | `status: blocked`, `Blocking condition: intent gap` | `blocked` + `Park(blocked, <whole "## Auto Run Result" section text>)` | none |
| blocked, configuration | `Blocking condition: no subagents` | `error` + `Park(misconfigured, "harness misconfigured: no subagents")` | no Answer offered |
| configuration, all 7 | each of the 7 conditions | same shape, condition interpolated | none |
| spec checkpoint | `ready-for-dev`, `spec_checkpoint: true` | `checkpoint` + `Park(checkpoint, "spec checkpoint")` | none |
| ready-for-dev, retry left | `ready-for-dev`, `spec_checkpoint: false`, `retry_count 0`, `max 2` | `error`, reason `unexpected status: ready-for-dev`, `retry=Retry(prompt, max 2, resume_session)` | no park |
| ready-for-dev, exhausted | same, `retry_count 2` | `error` + `Park(misconfigured, "unexpected status: ready-for-dev")`, no retry | none |
| draft / in-progress / in-review / unknown | each status | retry path, reason `unexpected status: {status}` | none |
| harness exit ≠ 0 with done file | `status: done`, `exit_code 1` | retry path, reason `harness exit 1`; exhausted → `Park(misconfigured, "harness exit 1")` | none |
| exit ≠ 0 with a non-`done` file | `status: blocked`, exit 1 | routes on the status, not the code | none |
| no story file | glob matches nothing | `error` + `Park(misconfigured, "no story file")` | none |
| ambiguous | two matches `a.md`, `b.md` | `error` + `Park(misconfigured, "ambiguous story file: a.md, b.md")` | names sorted |
| unreadable frontmatter | one match, no/broken frontmatter or no `status` | `error` + `Park(misconfigured, "no story file: frontmatter unreadable in a.md")` | YAML error caught |
| retry with resume | retry attempt, `resume_session: true`, harness `capabilities.resume` | `harness.resume(session_id=<previous>, message=retry.prompt)`; `compose_prompt` not called | previous session id absent → new session |
| retry without resume | `resume_session: false` or harness cannot resume | `harness.start` in a new session, prompt = `retry.prompt` + " " + the dispatch prompt | none |
| retry counted | executor returned `retry` | `apply_step_result` sets `retry_count+1`, row `queued`, one `retry_auto` gate record `"{reason} · retry {n}/{max}"` | row not in `error` → `InvalidTransition` |
| verify redispatch | previous attempt `done`, `row.redispatch_count > 0`, no resume signal | prepare writes `status: in-progress` and appends `## Verify Failure` with `Command:`, `Exit code:`, last 200 log lines; prepare commit includes it | no verify facts resolved → no append |
| retry after ambiguous | `retry` resume signal, two files match | all but the newest (mtime, then name) moved to `{spec_folder}/stories/.answers/{name}` before dispatch | one match → no move |

</intent-contract>

## Code Map

Read-only anchors (**never edit**): every file under `backend-api/tests/`, including
`tests/unit/application/steps/{agent_fixtures,test_agent_prompt,test_agent_prepare,test_agent_dispatch}.py`,
`test_source_limits.py`, `test_coverage_gates.py`, `test_layering.py`, `test_walk.py`,
`test_apply_step_result*.py`, `step_fixtures.py`. `tests/unit/fakes/` may grow additively.

- `backend-api/src/orchestrator/application/steps/agent.py` (**400/400**) — `_tail` (line 364)
  is the stub this story replaces; `_prepare_writes` (line 213) is where the two prepare hooks
  go; `_dispatch`/`_run` (lines 279, 302) build the prompt and start the harness; `compose_prompt`
  (line 130) is untouched. Room must be made before anything is added.
- `backend-api/src/orchestrator/application/steps/context.py` (316) — `StepPorts`,
  `RunEnvironment`, the `NO_*`/`require_*` idiom to copy for a new port field.
- `backend-api/src/orchestrator/application/templates/agent_row.py:52-54` — `EXPECT_KEY`
  (`{files, status_in}`) and `RETRY_KEY` (`{max, prompt, resume_session}`) as the planner
  flattens them onto the row. `expect.files` is the liveness glob, already resolved (AD-7).
- `templates/story.yaml:26-32` — the shipped values: `files: ["{{spec_folder}}/stories/{{story.id}}-*.md"]`,
  `status_in: [done, blocked, ready-for-dev]`, `retry: {max: 2, prompt: …, resume_session: true}`,
  `verify`'s `on_fail: {redispatch: build, max: 1}`.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` (293) —
  `_route` (line 205) and `_redispatch` (line 232) are the exact shape `_retry` copies;
  `REDISPATCHED`/`VERIFY_FAILED` are the wording precedent. `record`/`Entry` from `writers.py:96-127`.
- `backend-api/src/orchestrator/domain/statuses.py:173-193` — `("error","retry") → "queued"`
  already exists; `MachineEvent` already carries `retry_auto`. No status change is needed.
- `backend-api/src/orchestrator/domain/values.py` (129) — `Redispatch{target_seq, max}` is the
  shape `Retry{prompt, max, resume_session}` mirrors; `StepResult` gains one field.
- `backend-api/src/orchestrator/application/templates/lists.py:173-192` — `_states_done` /
  `_frontmatter`: the frontmatter-fence convention `story_file.py` must match, not import
  (that module is a plan-time reader over `PlanReader`, not over a `Workspace`).
- `backend-api/src/orchestrator/application/use_cases/walk.py` (250) — `_context` (line 162)
  and `_frame_start_sha` (line 187): the precedent for a walker-resolved fact reaching the
  executor through `StepPorts`, and the only place that holds both the row and the repositories.
- `backend-api/src/orchestrator/application/templates/plan_model.py:71-92` — `ON_FAIL_KEY`,
  `REDISPATCH_TARGET_SEQ`, `REDISPATCH_MAX`, `COMMAND_KEY`: how the verify row names the agent row.
- `backend-api/src/orchestrator/domain/ports/logs.py` + `infrastructure/process/logs.py` —
  `LogReader.tail(path, n)` (4.12), the log-tail helper this story reuses; fake at
  `tests/unit/fakes/logs.py`.
- `backend-api/src/orchestrator/domain/ports/workspace.py` (62) +
  `infrastructure/workspace/fs.py` — `glob`, `read`, `write`, `move`; **no mtime accessor yet**.
- `backend-api/src/orchestrator/domain/ports/harness.py:120-216` — `HarnessCapabilities.resume`,
  `Harness.resume(cwd, session_id, message, env, timeout_min, log_path) -> HarnessResult`
  (one call, no `start`/`wait` split).
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py::walker_deps` — where the new
  `StepPorts.logs` is wired, beside `process`/`workspace`/`tracer`.
- `backend-api/tests/unit/fakes/{harness,workspace,logs,runs,git,clock,db,process,tracer}.py` —
  the one double per port. `FakeHarness.called("resume")` already records resume calls.
- `scripts/check_test_pairs.py` — every new source module needs a unit test importing it.

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_story_file.py` -- new: frontmatter, section extraction, blocking
  condition, every unparseable shape -- TDD first.
- `backend-api/tests/unit/application/test_routing_rule.py` -- new: every row of the FR-16
  table above, driven directly against `route` -- the SPEC's "every row has a unit test".
- `backend-api/tests/unit/application/steps/agent_tail_fixtures.py` -- new: a tail world built
  on the frozen `agent_fixtures.py` (import, never edit).
- `backend-api/tests/unit/application/steps/test_agent_tail.py` -- new: the tail end to end
  through `AgentExecutor.execute`, including gate strength and the 5.6/5.7 seam order.
- `backend-api/tests/unit/application/steps/test_agent_retry_dispatch.py` -- new: resume vs
  new-session retry dispatch, the archive hook, the `## Verify Failure` append.
- `backend-api/tests/unit/application/test_apply_step_result_retry.py` -- new: the counter, the
  `retry_auto` record text, the re-queue.
- `backend-api/tests/unit/test_walk_verify_failure.py` -- new: the walker resolving the verify
  row's command, exit code and log tail onto `RunEnvironment`.
- `backend-api/tests/unit/test_workspace_mtime.py` -- new: `FsWorkspace.mtime` and the fake's.
- `backend-api/src/orchestrator/application/story_file.py` -- new: `StoryFile`, `parse`,
  `section`, `blocking_condition` -- the parser `route` consumes.
- `backend-api/src/orchestrator/application/rules/routing.py` -- new: `route(...)` and every
  reason constant -- the whole FR-16 table, pure.
- `backend-api/src/orchestrator/domain/values.py` -- add `Retry` and `StepResult.retry`.
- `backend-api/src/orchestrator/domain/ports/workspace.py`,
  `infrastructure/workspace/fs.py`, `tests/unit/fakes/workspace.py` -- add `mtime(path)`
  (needed by "newest by mtime, then name"); the fake grows additively only.
- `backend-api/src/orchestrator/application/steps/agent_tail.py` -- new: the tail moved out of
  `agent.py` plus liveness, routing, the retry decision, and the two named-but-empty seams.
- `backend-api/src/orchestrator/application/steps/agent.py` -- delete the moved code, call
  `agent_tail.tail`, add the two prepare hooks and the retry dispatch path; stay ≤ 400 lines.
- `backend-api/src/orchestrator/application/steps/context.py` -- add `StepPorts.logs`,
  `RunEnvironment.verify_failure`, the `VerifyFailure` value and `resolved_text`.
- `backend-api/src/orchestrator/application/use_cases/walk.py` -- resolve the verify failure for
  a redispatched agent row and hand it over on `StepPorts`.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` -- handle
  `StepResult.retry`: counter, `retry_auto` record, re-queue.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` -- wire `RealLogReader` into
  `StepPorts.logs`.

**Acceptance Criteria:**
- Given a story file with `status: done` and exit 0, when the tail runs, then the result is
  `done` at gate `liveness` with no park and `output_ref` the harness log.
- Given every one of the 7 configuration conditions, when the tail runs, then the park is
  `misconfigured` with `harness misconfigured: {condition}` and the step status is `error`.
- Given `status: blocked` with any other condition, when the tail runs, then the park is
  `blocked` and its reason is the `## Auto Run Result` section verbatim, heading included.
- Given a retry result, when `apply_step_result` applies it, then `retry_count` is one higher,
  the row is `queued`, and exactly one `retry_auto` gate record reads `{reason} · retry {n}/{max}`.
- Given a redispatched attempt, when prepare runs, then the story file's frontmatter reads
  `status: in-progress`, a `## Verify Failure` section holds the command, the exit code and the
  last 200 verify-log lines, and the prepare commit includes the file.
- Given the coverage report, when `make test` runs, then `application/rules/routing.py`,
  `application/story_file.py`, `application/steps/agent.py` and
  `application/steps/agent_tail.py` are all at 100 % branch coverage.
- Given `make lint`, when it runs, then `test_source_limits.py` is green — no module exceeds 400
  lines — and all four import-linter contracts are KEPT.

## Spec Change Log

## Review Triage Log

### 2026-09-08 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 3, medium 1, low 1)
- defer: 7: (high 0, medium 2, low 5)
- reject: 11: (high 0, medium 3, low 8)
- addressed_findings:
  - `[high]` `[patch]` The AD-13 de-ambiguation archive was gated on `retrying(ctx)` (the
    automatic retry), which can never be true with two matching files: `ambiguous story
    file` is a `misconfigured` park that carries no `retry`, so the row only re-runs on an
    Operator signal — which sets `resume_signal` and makes `retrying()` False. Added
    `context.operator_retry(ctx)` and gated the archive on it OR `retrying(ctx)`; added
    tests that reach the archive through an Operator `retry` resume and that a resume
    carrying `answer` or `continue` archives nothing.
  - `[high]` `[patch]` The archive's `workspace.move` was never staged, so the rename sat
    in the tree when `_start` read `start_sha` — 5.6 would have read the orchestrator's own
    move as the agent's (AD-17, FR-31) — and it dirtied the whole-tree commit guard while
    leaving the index empty, which makes `git commit` exit non-zero. `archive_ambiguous`
    now reports both ends of every rename and `_prepare_writes` stages them with the files
    it wrote; added tests for the staged pathspecs and for "an archive that changed nothing
    else still leaves no empty commit".
  - `[high]` `[patch]` `retrying()` classified a crash-recovered attempt as a Template
    retry: `start_attempt` closes an interrupted attempt `error` and the walk restarts with
    no signal, so a restart resumed the killed session with the retry prompt, uncounted
    against `retry_count` (AD-9 forbids an uncounted automatic re-execution). Added
    `previous.end_sha is not None` — the same "the dispatch came back" discriminator
    `_orphan_control` already uses — plus tests for both the interrupted and the
    came-back shapes.
  - `[medium]` `[patch]` Nothing asserted that `walker_deps` wires `StepPorts.logs`;
    deleting the line left `make test` green and would have sent every redispatched Story
    back with an empty `## Verify Failure` tail. `tests/unit/test_dbos_startup_agent.py` is
    frozen, so the assertion went into a new `tests/unit/test_dbos_startup_logs.py`.
  - `[low]` `[patch]` `after_verify` rendered the Python literal `Exit code: None` into a
    file the agent reads, because `VerifyFailure.exit_code` is legitimately `None`. It now
    states the fact (`not recorded`); both renderings are tested.

## Design Notes

**Why `route` takes two keyword-only extras.** The brief's signature
(`story_file, files, exit_code, spec_checkpoint, retry_count, retry`) cannot build a `StepResult`:
`gate` and `Park.path` are facts of the row. Both are added keyword-only — the same resolution
5.1 used for `env_for`'s `traceparent` and 5.2 for `create_run_trace`'s `name`. `files` decides
liveness first (0 → `no story file`, ≥2 → `ambiguous story file: …`), then `story_file is None`
with one match means unparseable frontmatter.

**`expect.status_in` is not consulted.** The FR-16 table routes on the fixed tokens, and it sends
`ready-for-dev` *without* a spec checkpoint down the retry path although the shipped
`status_in` lists it. `expect.files` is used — it is the resolved liveness glob (AD-7) — with the
brief's literal `{spec_folder}/stories/{story_id}-*.md` as the fallback when a row declares none.

**How the executor knows which kind of re-dispatch it is**, with no new `StepContext` field
(AD-9 closes that list):

```python
retry     = ctx.resume_signal is None and previous is not None and previous.status == "error"
redispatch= ctx.resume_signal is None and previous is not None and previous.status == "done" \
            and ctx.row.redispatch_count > 0
```

An agent row reaches `done` before verify can fail, and an automatic re-queue only ever follows
`error` (a retry) or `done` (a redispatch); every operator resume carries a `resume_signal`. This
is the observable form of the brief's `row.redispatch_count > previous`, and it stays correct when
a retry follows a redispatch (that attempt's predecessor is `error`, so nothing is re-appended).

**Where the verify facts come from.** `walk._context` is the only place holding both the agent
row and the repositories; it finds the row whose `on_fail` redispatches to this row's `seq`, reads
its command, its latest attempt's `exit_code` and — through the new `StepPorts.logs` — the last 200
lines of its log, and hands a frozen `VerifyFailure` over on `RunEnvironment`. Same move as
`_frame_start_sha`, and the executor still reads a value, never a repository (AD-8).

**Retry dispatch.** `resume_session` **and** `harness.capabilities.resume` **and** a previous
`session_id` → `harness.resume(session_id=…, message=retry.prompt)`, which is one call and
therefore has no `pgid`-before-await commit; otherwise a fresh `start` whose prompt is
`retry.prompt` prepended to the ordinary dispatch prompt, because a new session has no context to
continue. `compose_prompt` is unchanged and never sees a retry prompt.

**The split.** `agent_tail.py` takes everything that happens after the harness exits — `finish`,
`tail`, `usage`, liveness, routing, the retry decision — and imports only `context.py`,
`story_file.py`, `rules/routing.py` and `domain/`. `agent.py` imports it; the dependency runs one
way, so the shared `resolved_text` moves to `context.py` rather than being duplicated or
re-imported backwards.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; import-linter all KEPT; `check_test_pairs` names no new module.
- `make test` -- expected: exit 0; `domain/` + `application/` 100 % branch under `--fail-under=100`.
- `uv run pytest tests/unit/test_source_limits.py` -- expected: green, so `agent.py` and
  `agent_tail.py` are both ≤ 400 lines.
- `for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done`
  -- expected: nothing outside `tests/unit/fakes/`, and those strictly additive.

## Auto Run Result

Status: done

**What was implemented.** The `agent` executor now decides nothing itself: the Story file
the agent wrote is read through the `Workspace`, parsed by `application/story_file.py`, and
handed to `application/rules/routing.py::route`, a pure function that is FR-16's table and
nothing else. The tail moved out of `application/steps/agent.py` into
`application/steps/agent_tail.py` — the sanctioned split, forced because `agent.py` was at
exactly 400/400 — and the 5.6 protected-path seam and the 5.7 spend/budget seam sit around
the `route(` call in AD-9's order. `StepResult` gained a `Retry` sibling to `Redispatch`,
and `apply_step_result` turns it into a counted, recorded, re-queued attempt (`retry_auto`,
`"{reason} · retry {n}/{max}"`) — the second writer stays the only thing that writes a
status. A retry dispatches through `Harness.resume` when the contract asked for it and the
harness can, otherwise into a fresh session with the retry prompt in front of the dispatch
sentence; `compose_prompt` is unchanged and never sees a retry prompt. Two prepare-phase
hooks close FR-10 and AD-13: a verify redispatch hands the file back at `in-progress` with a
`## Verify Failure` section carrying the command, the exit code and the last 200 log lines,
and an Operator *Retry* after an ambiguity archives every match but the newest to
`stories/.answers/`. Both are staged into the one prepare commit, so nothing the
orchestrator wrote is inside the agent's own range.

**Files changed (11 added, 9 modified):**
- `application/story_file.py` — added: `StoryFile`, `parse`, `frontmatter`, `section`,
  `blocking_condition`, `with_status`, `appended`, `after_verify`.
- `application/rules/routing.py` — added: `route`, the seven `CONFIGURATION_CONDITIONS`,
  and every reason constant PRD §4.6 prints.
- `application/steps/agent_tail.py` — added: `finish`, `tail`, `story_files`,
  `archive_ambiguous`, `retry_of`, `usage`; the two seams, named and empty.
- `application/steps/agent.py` — modified: tail deleted and delegated; `_planned` (the three
  re-dispatches); `_run`'s resume branch; `_prepare_writes` staging every write. 400 → 387.
- `application/steps/context.py` — modified: `VerifyFailure`, `RunEnvironment.verify_failure`,
  `StepPorts.logs`, `resolved_text`, `committed`, `retrying`, `operator_retry`,
  `redispatched`. 316 → 398.
- `application/use_cases/apply_step_result.py` — modified: `_retry` and `RETRIED`.
- `application/use_cases/walk.py` — modified: `_step_ports`, `_verify_failure`,
  `_redispatches_to`, `VERIFY_LOG_LINES`.
- `domain/values.py` — modified: `Retry`, `StepResult.retry`.
- `domain/ports/workspace.py`, `infrastructure/workspace/fs.py` — modified: `mtime`.
- `infrastructure/dbos/startup.py` — modified: `logs=RealLogReader()`.
- `tests/unit/fakes/workspace.py` — modified, strictly additively: `mtime`, `mtimes`,
  `globbed`, and one line in `move` that carries the mtime entry across.
- Ten new test modules: `test_story_file.py`, `application/test_routing_rule.py`,
  `application/steps/{agent_tail_fixtures,test_agent_tail,test_agent_retry_dispatch}.py`,
  `application/test_apply_step_result_retry.py`, `test_walk_verify_failure.py`,
  `test_workspace_mtime.py`, `test_dbos_startup_logs.py`.

**Review findings:** 5 patched (3 high, 1 medium, 1 low), 7 deferred (frontmatter
`deferred`), 11 rejected. No `intent_gap` and no `bad_spec`, so no repair loopback ran. All
three high patches were defects no gate could see: the de-ambiguation archive was gated on a
condition the routing rule can never produce, the archive's renames escaped the prepare
commit and would have been attributed to the agent by AD-17, and a crash-recovered attempt
was classified as a Template retry.

**Follow-up review recommended:** true. Three patched findings were `high` severity, which
sets the flag on its own; the medium/low score was `3 × 1 + 1 × 1 = 4`, under the threshold.

**Verification performed (re-run by the coordinator, not only trusted from the
implementation subagent):**
- `make lint` — exit 0, twice (before and after the patch pass): ruff, mypy `--strict` over
  `domain/` + `application/`, all four import-linter contracts KEPT, env contract unchanged
  (31 settings fields / 37 `.env.example` variables — no new setting), `check_test_pairs`
  166/166 paired, `gen:api --check` no drift, web-client clean.
- `make test` — exit 0, twice: 4654 backend unit tests passed, 1 skipped (4444 before this
  story); `domain/` + `application/` at 100 % branch under `--fail-under=100`; web-client 973.
- Branch coverage of this story's modules: `steps/agent.py` 180 statements / 42 branches
  **100 %**; `steps/agent_tail.py` 77 / 22 **100 %**; `rules/routing.py` 52 / 20 **100 %**;
  `story_file.py` 71 / 20 **100 %**.
- `test_source_limits.py` — 529 passed, so every module is ≤ 400 lines. `agent.py` 387,
  `agent_tail.py` 234, `context.py` 398, `walk.py` 315, `apply_step_result.py` 330,
  `routing.py` 147, `story_file.py` 158.
- `make openapi` — ran; `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  unchanged, so no drift.
- Matrix audit: all 18 I/O matrix rows are covered by named tests that ran and passed, plus
  the eleven the patch pass added.
- Anchor check (the literal command from the dispatch instructions) — two lines,
  `backend-api/tests/unit/fakes/clock.py` (changed by story 5-4, already committed on this
  branch, untouched here) and `backend-api/tests/unit/fakes/workspace.py`, the sanctioned
  shared-double exception; its diff is 17 insertions and 1 deletion, the deletion being the
  `__init__` signature reflowing across four lines. No pre-existing test file, `SPEC.md`,
  `stories.yaml` or `AGENTS.md` was modified.
- `make e2e-api`, `make e2e-ui` and `make durability` were **not run by the coordinator**:
  this story adds no route, no schema field, no UI and no migration, `make lint` already ran
  `gen:api --check` with no drift, and `make openapi` confirmed it.

**Residual risks:** the seven `deferred` items above. The two worth carrying forward are the
resumed dispatch that records no `pgid` (orphan control cannot reap it, and closing that
means changing the `Harness` port) and a `blocked` file with no `## Auto Run Result` section
parking with an empty Question. `context.py` is now at **398/400** and `agent.py` at 387:
5.6 and 5.7 have room in the executor but almost none in the shared context module.
