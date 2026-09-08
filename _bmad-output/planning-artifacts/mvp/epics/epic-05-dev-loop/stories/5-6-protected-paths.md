---
title: 'Protected paths'
type: 'feature'
created: '2026-09-08'
status: 'done'
baseline_revision: 'e43def9bd7903b162c224863a332f206203e9cc5'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      The Accept branch's own Attempt records no `end_sha`, `exit_code` or `session_id`, so a
      later attempt reads it as a crash recovery rather than as a resume.
    evidence: |-
      `agent_tail.re_check` returns before `finish` runs, so only `apply_step_result._close_attempt`
      touches that attempt — it writes `ended_at`, `status` and `output_ref` and nothing else.
      `context.retrying` discriminates on `previous.end_sha is not None`, so the attempt after an
      Accept is classified as a backend that died mid-dispatch. Unreachable today: `handle_signal`
      still refuses `continue` on a `protected_path` park (`not available yet`), which is Epic 6's
      to land, and closing it means deciding what an attempt that dispatched nothing records.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:re_check
    severity: medium
  - summary: >-
      `re_check` cannot ask which park it is answering, so it keys on "a `continue` carrying
      files" rather than on `protected_path`.
    evidence: |-
      `StepContext` has no park kind (AD-9 closes the field list) and `run.park_kind` is not a
      substitute: `signal_run` clears the three park fields when it resumes the Run, so the
      executor always reads `None`. A `continue` carrying a `files` payload sent on a
      `checkpoint` park of an agent row would therefore skip the dispatch. `api/schemas/signals.py`
      accepts an arbitrary payload, so nothing upstream constrains it either.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:re_check
    severity: low
  - summary: >-
      `walk._frame` reads every frame row's attempts on every row execution, where the old
      `_frame_start_sha` stopped at the first row that had any.
    evidence: |-
      `_frame` is called from `_context` for each row of a frame and calls
      `attempts.list_for_row` once per frame row, including for rows that need neither the
      ranges nor the frozen set. Bounded by frame size (four rows in every shipped Template),
      so it is a cost rather than a defect.
    location: >-
      backend-api/src/orchestrator/application/use_cases/walk.py:_frame
    severity: low
  - summary: >-
      The `protected_path` park reason is unbounded: a bulk rename or a deleted test folder
      writes every hit path into `run.park_reason` and the gate record text.
    evidence: |-
      `agent_tail.protected` joins every hit with `PATH_SEPARATOR` and no cap. AD-17 says the
      reason lists the files, so truncating it is a product-copy decision this story's brief
      does not make; the full list is on `payload.hits` either way.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:protected
    severity: low
  - summary: >-
      An Accept over a previous attempt that recorded no `log_path` reports `output_ref` as
      `"."` rather than as nothing.
    evidence: |-
      `_reported` builds `Path(attempt.log_path or "")`, and `str(Path(""))` is `"."`. Only
      reachable through the Epic 6 Accept path over an attempt the harness never wrote a log
      for, which `mark_finished` always does today.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:_reported
    severity: low
  - summary: >-
      No test joins the walker's own anchor resolution to a real executor run: each half is
      asserted against a hand-written stand-in for the other.
    evidence: |-
      `test_walk_frame_anchors.py` registers a `Recording` stub for `agent` and `git.commit`,
      and `test_agent_protected_paths.py` injects `ANCHORS` onto `RunEnvironment` and
      hand-builds `FrameAnchors`. The joined chain — attempt writes `frozen_test_files`, walker
      builds the set, real executor parks — is the e2e suite's surface, and `make e2e-api` is
      not run by this story.
    location: >-
      backend-api/tests/unit/application/
    severity: low
---

<intent-contract>

## Intent

**Problem:** AD-17's frozen anchors — `SPEC.md`, `stories.yaml`, `epics.yaml`, every
`AGENTS.md`, and every test file that already existed when a Story frame started — are
declared as a port (`domain/ports/protected_paths.py`) and read as "no hits" by both call
sites, so today a coding agent can make a gate pass by editing what the gate reads.

**Approach:** Land `application/rules/protected_paths.py` as a pure rule over
`Change{path, kind}` values, resolve one frame's anchors and agent ranges in the walker
(the only place holding both the row and the repositories), and read them from the two
call sites AD-17 names: the agent tail *before* routing, and `git.commit` through the
port it already calls. A hit parks `protected_path` with the files named and is never
retried automatically.

## Boundaries & Constraints

**Always:**
- Agent ranges only. The tail checks `diff_changes(start_sha, end_sha) ∪ uncommitted` of
  the attempt it just finished; `git.commit` checks the union of the frame's recorded
  agent ranges ∪ what it staged. An operator commit (`spec: operator edit (orchestrator)`)
  and the orchestrator's own WIP/prepare commits are outside both by construction.
- The protected-path result is returned **before** `route(...)` in `agent_tail.tail`
  (FR-31: a modified anchor wins over every route).
- `run.accepted_paths` excludes a path from every later check in the same frame.
- Status stays with its two writers (AD-8): the executor returns a `StepResult` carrying
  the park and the hit payload; `apply_step_result` writes them.
- Anchors are read-only (root AGENTS.md hard rule 1): no existing test file is edited,
  including to append. `tests/unit/fakes/*` may grow strictly additively.
- `domain/` + `application/` stay at 100 % branch coverage; every module ≤ 400 lines.

**Block If:**
- A frozen test would have to change to make a gate pass → report `ANCHOR CONFLICT`.
- The brief and the spine disagree on a rule the brief does not state → report, do not
  decide.

**Never:** the Accept *signal effect* (Epic 6 wires it; the executor branch lands here),
the budget read after routing (5.7), any change to `application/steps/git_commit.py`,
any new double for a port that already has a fake.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Anchor modified in the agent's range | attempt range modifies `{spec_folder}/SPEC.md` | `StepResult(error, gate=row.gate, park=protected_path, reason="protected path modified: specs/x/SPEC.md")`, `payload.hits == [{"path": …, "kind": "modified"}]`, `route` never called | park, no retry |
| `AGENTS.md` created anywhere | change `added web-client/AGENTS.md` | hit, `kind == "added"` | park |
| Frozen test modified | `frozen_test_files = ("tests/a.py",)`, changes modify `tests/a.py` and add `tests/new.py` | one hit: `tests/a.py` | park |
| File the agent created inside the frame | attempt 2 modifies `tests/new.py` (not frozen) | no hit | — |
| Frozen test deleted | attempt 2 deletes `tests/a.py` | hit, `kind == "deleted"` | park |
| Operator edit between attempts | `SPEC.md` changed by a commit outside `start_sha..end_sha` | no hit — the range never sees it | — |
| Accepted path | `run.accepted_paths = ("tests/a.py",)`, the frame modifies it again | no hit | — |
| Commit-guard, uncommitted anchor | `git status` lists `stories.yaml` | `park protected_path`, `Git.commit` never called | park |
| `continue` with accepted files | `resume_signal.event == "continue"` carrying `files` | no `Harness` call at all; the tail re-runs over `previous_attempt.start_sha/end_sha` with the accepted paths excluded and routes on the story file | — |
| Nothing protected changed | ordinary attempt | routes exactly as before | — |

</intent-contract>

## Code Map

Read-only anchors (**never edit, not even to append**): every file under `backend-api/tests/`
— in particular `tests/unit/application/steps/{agent_fixtures,agent_tail_fixtures,test_agent_tail,test_agent_prepare,test_agent_dispatch,test_agent_retry_dispatch}.py`,
`tests/unit/application/test_walk_use_case.py`, `tests/unit/test_run_environment.py`,
`tests/unit/test_git_commit_executor.py`, `tests/unit/test_git_port.py`,
`tests/unit/test_subprocess_git_worktrees.py`, `test_source_limits.py`,
`test_coverage_gates.py`, `step_fixtures.py`. `tests/unit/fakes/git.py` may grow additively.

- `backend-api/src/orchestrator/application/steps/agent_tail.py` (234) — `tail` holds the
  `# 5.6` seam comment immediately before `files = story_files(ctx)`; the check goes there
  and returns before `route(...)`. **`tests/unit/application/steps/test_agent_tail.py:315`
  asserts `body.index("5.6") < body.index("route(") < body.index("5.7")` over
  `inspect.getsource(tail)`** — the comment markers must survive, so the implemented check
  keeps a `5.6` comment above it and the `5.7` comment stays below `route(`.
- `backend-api/src/orchestrator/application/steps/agent.py` (387/400) — `AgentExecutor.execute`
  is the four-call chain the Accept branch prefixes; `_start` (line ~279) and
  `_frozen_test_files` (line ~292) already write `start_sha` + `frozen_test_files` through
  `mark_started`; `WHOLE_TREE = "."`. Only ~13 lines of room: put the branch's body in
  `agent_tail.py` and call it from `execute`.
- `backend-api/src/orchestrator/application/steps/context.py` (**398/400**) —
  `RunEnvironment` is the walker-resolved value bag the tail already reads
  (`accepted_paths`, `test_globs`, `verify_failure`). Two lines of room: exactly one new
  field, `anchors: frozenset[str]`, with its `#:` comment.
- `backend-api/src/orchestrator/application/use_cases/walk.py` (315) — `_context` (line 180)
  and `_step_ports` (line 208) resolve per-row facts; `_frame_start_sha` (line 251)
  returns the **frame's first row-with-attempts' `attempts[0].start_sha`**, which for a
  Story frame is `git.sync`'s `None`. `rows_in_frame(rows, frame)` from `rules/frames.py`
  gives the frame's rows in `seq` order.
- `backend-api/src/orchestrator/application/steps/git_commit.py` (93) — `_protected` already
  calls `ctx.ports.protected_paths.check(changed=…, accepted=…)` and parks
  `protected_path` with `PROTECTED = "protected paths: {paths}"`. **Do not touch it.**
- `backend-api/src/orchestrator/domain/ports/protected_paths.py` (36) — `check(*, changed:
  Sequence[str], accepted: Sequence[str]) -> tuple[str, ...]`. **The protocol's member set
  is frozen by `tests/unit/test_run_environment.py:113` (`isinstance(NoHits(), ProtectedPaths)`
  where `NoHits` has only `check`) and by `test_git_commit_executor.py`'s `Hits`** — adding
  a second method to it breaks both. Only the docstring may change.
- `backend-api/src/orchestrator/domain/ports/git.py` (170) + `infrastructure/git/worktrees.py`
  (182) — `diff_names(worktree, from_sha)` unions `diff --name-only` with untracked files
  and is asserted by `test_subprocess_git_worktrees.py:192`; it must keep its signature and
  its return type. `RemoteRef`/`CloneResult` are the precedent for a port-owned value type.
- `backend-api/src/orchestrator/domain/values.py` (155) — `StepResult`; `Park{kind, reason,
  path}`; `ParkKind` already admits `protected_path` (`domain/statuses.py:49`).
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` (330) — `_park`
  (line 300) → `writers.park_run(ports, run, park, attempt_n)`; `writers.record`/`Entry`
  already carry a `payload` dict (`writers.py:96-127`, `gate_record.py`).
- `backend-api/src/orchestrator/application/rules/signals.py:70,301` — `FILES_KEY = "files"`
  and `accepted_files(payload)`: what a `continue` on a `protected_path` park carries, and
  `signal_run.py:98-104` records the signal payload verbatim onto the `GateRecord` the
  executor reads as `ctx.resume_signal`.
- `backend-api/src/orchestrator/application/rules/budget.py` (30) — the shape a one-purpose
  rule module has here. `rules/` is held to 100 % branch coverage.
- `backend-api/tests/unit/fakes/git.py` — `FakeGit`: one scripted list per port method,
  `called(name)`, last entry repeats. Extend additively with `diff_changes`.

## Tasks & Acceptance

**Execution:**

1. `backend-api/src/orchestrator/domain/ports/git.py` -- add `ChangeKind` (`added |
   modified | deleted`) and a frozen `Change{path, kind}` beside `RemoteRef`, and
   `diff_changes(worktree, from_sha, to_sha) -> tuple[Change, ...]` to the protocol --
   AD-17 checks a *bounded* commit range and records *how* each path changed;
   `diff_names` answers neither and is frozen by an existing adapter test.
2. `backend-api/src/orchestrator/infrastructure/git/worktrees.py` -- implement
   `diff_changes` over `git diff --name-status -z {from} {to}`, mapping `A`→added,
   `D`→deleted, `R`/`C` to the pair (old deleted, new added), everything else modified --
   a rename of a protected file must read as a deletion of it.
3. `backend-api/tests/unit/fakes/git.py` -- add a `diff_changes` script (default `[()]`)
   and the method, strictly additively -- AD-18: one fake per port, extended, never
   duplicated.
4. `backend-api/src/orchestrator/application/rules/protected_paths.py` (new) -- `build(*,
   spec_folders, initiative_folder, frozen_test_files) -> frozenset[str]`,
   `uncommitted(status) -> tuple[Change, ...]` (porcelain, untracked included, renames
   split), `check(changed, protected, accepted) -> tuple[Change, ...]`, and `FrameAnchors`
   — the frozen `ProtectedPaths` implementation that unions the frame's recorded agent
   ranges with whatever `git.commit` hands it -- AD-17's rule, pure, plus the one binding
   that lets the commit-guard reach it without changing `git_commit.py`.
5. `backend-api/src/orchestrator/application/steps/context.py` -- add
   `RunEnvironment.anchors: frozenset[str] = frozenset()` with its `#:` comment (two lines,
   398 → 400) -- the tail needs the *frame's* frozen test set, and only the walker can see
   it; `RunEnvironment` is where every other walker-resolved fact already travels.
6. `backend-api/src/orchestrator/application/use_cases/walk.py` -- resolve the frame's
   attempts once in `_context`; fix `_frame_start_sha` to answer the frame's **lowest-`n`
   attempt that has a `start_sha`** (AD-17's own words) instead of the first row-with-
   attempts' `attempts[0]`; build `anchors` and the `FrameAnchors` and hand both over via
   `RunEnvironment` / `StepPorts.protected_paths` -- one resolution, two readers.
7. `backend-api/src/orchestrator/application/steps/agent_tail.py` -- add the check to
   `tail` before `route(...)` (keeping the `5.6` / `5.7` comment markers), `PROTECTED =
   "protected path modified: {paths}"`, and `re_check(ctx)` for the Accept branch --
   FR-31's "wins over every route", and AD-9's "a `continue` on `protected_path` does not
   dispatch".
8. `backend-api/src/orchestrator/application/steps/agent.py` -- call `agent_tail.re_check`
   first in `execute` and return its result when it is not `None` -- three lines, because
   `agent.py` has thirteen.
9. `backend-api/src/orchestrator/domain/values.py` +
   `backend-api/src/orchestrator/application/use_cases/{apply_step_result,writers}.py` --
   `StepResult.payload`, threaded through `_park` into `park_run`'s gate record -- AD-17:
   the hit list is recorded, so 5.9's trajectory can carry it.
10. New test modules (never appended to an existing one):
    `tests/unit/application/test_protected_paths_rule.py`,
    `tests/unit/application/steps/test_agent_protected_paths.py`,
    `tests/unit/application/test_walk_frame_anchors.py`,
    `tests/unit/test_git_diff_changes.py`,
    `tests/unit/application/test_apply_step_result_payload.py` -- every I/O row above, the
    100 % branch gate, and `check_test_pairs` for the new module.

**Acceptance Criteria:**

- Given an attempt whose range modified `{spec_folder}/SPEC.md`, when `tail` runs, then it
  returns `error` + `Park(protected_path, "protected path modified: …/SPEC.md")` and the
  story-file glob is never read.
- Given an operator commit between two attempts that changed `SPEC.md`, when attempt 2's
  tail runs, then there is no hit and the row routes normally.
- Given `git.commit` with an uncommitted change to `stories.yaml`, when it executes, then
  it parks `protected_path` and `Git.commit` is never called.
- Given a `continue` gate record carrying `files`, when the executor runs, then no
  `Harness` method is called, no WIP or prepare commit is made, and the result is the tail's
  routing over the previous attempt's SHAs with the accepted paths excluded.
- Given a Story frame whose `git.sync` attempt recorded no `start_sha` and whose `agent`
  attempt recorded one, when the walker builds the context, then `frame_start_sha` is the
  agent attempt's.
- Given `make lint && make test`, when they run, then both exit 0 and
  `application/rules/protected_paths.py`, `steps/agent.py` and `steps/agent_tail.py` are at
  100 % branch coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-08 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 3, medium 2, low 2)
- defer: 6: (high 0, medium 1, low 5)
- reject: 11: (high 0, medium 3, low 8)
- addressed_findings:
  - `[high]` `[patch]` `git status --porcelain` collapses a wholly-untracked directory to one
    `?? dir/` entry, so an `AGENTS.md` an agent creates inside a directory it also created was
    never enumerated and could not be a hit — AD-17's headline case. `SubprocessGit.status`
    now passes `--untracked-files=all`; pinned by a real-git test that creates a nested
    untracked anchor and asserts `uncommitted(status(...))` names the file itself.
  - `[high]` `[patch]` The timeout park returned before `tail`, so an attempt that modified an
    anchor and then hung escaped the check permanently: the retry's WIP commit lands that edit
    in a commit that is inside no agent range and gone from the tree. `finish` now runs
    `protected` inside the timeout branch, before the timeout result; both directions pinned.
  - `[high]` `[patch]` `_step_ports` bound the rule on every row with a `RunEnvironment`, frame
    or not, leaving "anything staged whose basename is `AGENTS.md`" in force for `repo-init@1`
    — a false park on a file the orchestrator itself wrote. AD-17 is frame-scoped; the rule and
    the anchors are now bound only inside a frame, and both directions are pinned.
  - `[medium]` `[patch]` Porcelain C-quotes non-ASCII paths, so a quoted anchor matched neither
    the anchor set nor the `AGENTS.md` basename. `status` now runs with `core.quotePath=false`;
    pinned by a real-git test over an accented anchor path.
  - `[medium]` `[patch]` `git_commit._changed` strips porcelain's status letters, so a staged
    rename of an anchor reached the rule as the single string `old -> new` and matched nothing
    — the one call site that stages before it looks could commit a renamed anchor.
    `FrameAnchors.check` now offers both readings of a staged entry; pinned through
    `GitCommitExecutor`.
  - `[low]` `[patch]` `uncommitted` split on `" -> "` in any path, inventing two paths out of an
    ordinary filename holding those bytes. The split is now gated on a rename or copy code.
  - `[low]` `[patch]` The multi-hit sentence and the payload order were unasserted — every
    `reason` assertion had exactly one hit. A two-hit park now pins the joined sentence and
    that `payload["hits"]` keeps `check`'s first-mention-wins order.

## Design Notes

**Why the protocol does not grow a second method.** `tests/unit/test_run_environment.py`
asserts `isinstance(NoHits(), ProtectedPaths)` against a class holding only `check`, and
`runtime_checkable` checks the whole member set — so a `hits(...)` sibling would fail a
frozen test. The commit-guard therefore keeps the path-only `check`, and the tail — which
needs the kinds for `payload.hits` — calls the pure rule directly with the values it
computed itself.

**Why the tail's range and the commit-guard's differ.** AD-17 gives them different scopes
on purpose: the tail is "what this attempt just did", the commit-guard is "everything the
agent did in this frame, plus whatever is still uncommitted". Binding the frame's ranges to
the `FrameAnchors` object rather than to the tail keeps each call site checking exactly its
own scope, and keeps `git_commit.py` unchanged — the object supplies what that module
cannot know.

**`_frame_start_sha`, and what the frame's first attempt actually is.** AD-17 names "the
frame's lowest-`n` attempt that has a `start_sha`". The current function takes the first row
of the frame that has *any* attempt and reads `attempts[0].start_sha`, which in a Story
frame is `git.sync`'s `None` — so the value is `None` on every attempt and identifies
nothing. Reading past attempts that recorded no commit answers AD-17's question directly
and keeps all three existing `test_walk_use_case.py` assertions green (the frame whose sync
attempt *did* record `"a" * 40` still answers it; the frame with no recorded commit still
answers `None`; the frame that reads past a row that never ran still answers `"b" * 40`).

```python
def _frame_start_sha(attempts: Sequence[Attempt]) -> str | None:
    return next((a.start_sha for a in attempts if a.start_sha is not None), None)
```

**Why the Accept branch is `agent_tail.re_check`.** `agent.py` is 387/400 and the branch
needs a docstring plus a reconstructed `HarnessResult`; the tail is the module that owns
"what the dispatch reached", the branch re-runs exactly that, and `agent.py` already
delegates its whole tail there. The discriminator is observable off `StepContext` alone:
`resume_signal.event == "continue"` **and** the record's payload carries `files`
(`rules/signals.py::FILES_KEY`) — a `continue` on a `checkpoint` park carries none.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; ruff, mypy `--strict` over `domain/` + `application/`,
  all four import-linter contracts KEPT, env contract unchanged (no new setting),
  `check_test_pairs` naming no unpaired module, no OpenAPI drift.
- `make test` -- expected: exit 0; `domain/` + `application/` 100 % branch under
  `--fail-under=100`; backend unit count strictly above the 4654 that 5.5 left.
- `uv run --directory backend-api pytest tests/unit --cov=src/orchestrator/application/rules/protected_paths.py --cov=src/orchestrator/application/steps/agent.py --cov=src/orchestrator/application/steps/agent_tail.py --cov-branch --cov-report=term-missing`
  -- expected: 100 % for all three.
- `uv run --directory backend-api pytest tests/unit/test_source_limits.py` -- expected:
  green, so `context.py` (400), `agent.py`, `agent_tail.py`, `walk.py` are all ≤ 400.
- `for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done`
  -- expected: nothing outside `tests/unit/fakes/`, and those strictly additive.

**Manual checks (if no CLI):**
- `make e2e-api` / `make e2e-ui` / `make openapi` need no run: this story adds no route, no
  schema field and no UI. Report them as not-run with that reason.

## Auto Run Result

Status: done

**What was implemented.** AD-17's frozen anchors stopped being a declaration and became a
check. `application/rules/protected_paths.py` is the rule — `build` composes the anchor set,
`uncommitted` reads `git status --porcelain`, `check` subtracts `run.accepted_paths` and
reports what is left as `Change{path, kind}` — and `FrameAnchors` is the one binding that
lets `git.commit` reach AD-17's full scope through the port call it already made, so
`steps/git_commit.py` is byte-for-byte unchanged. The walker resolves a frame once and hands
the two readers what each needs: the anchor set travels on `RunEnvironment` for the agent
tail, the whole object goes into `StepPorts.protected_paths` for the commit-guard, and only
a row inside a Story frame gets either. The two call sites check different ranges on purpose
— the tail checks `diff_changes(start_sha, end_sha) ∪ uncommitted` of the attempt that just
finished, the commit-guard the union of every agent range the frame recorded plus what it
staged — so an operator's `spec: operator edit (orchestrator)` and the orchestrator's own WIP
and prepare commits are outside both by construction. A hit is `error` + `Park(protected_path,
"protected path modified: {paths}")`, returned before `route(...)` and before the timeout park,
carrying its hit list on the new `StepResult.payload` for `apply_step_result` to write onto
the append-only gate record.

**`_frame_start_sha` is fixed, and the frame's first attempt is now identifiable.** It
returned the *first row-with-attempts'* `attempts[0].start_sha`, which in a Story frame is
`git.sync`'s `None` — so the value was `None` on every attempt and identified nothing. It now
takes the frame's attempts in plan-then-attempt order and answers the lowest-`n` one that
*has* a `start_sha`, which is AD-17's own wording and is exactly the attempt `steps/agent.py`
writes `frozen_test_files` on. All three existing `test_walk_use_case.py` assertions stay
green: the frame whose sync attempt did record a commit still answers it, the frame that
recorded none still answers `None`, and the frame that reads past a row that never ran still
answers the row that did.

**Files changed (6 added, 11 modified):**
- `application/rules/protected_paths.py` — added: `build`, `uncommitted`, `check`,
  `FrameAnchors`, and the two porcelain helpers. 175 lines.
- `application/steps/agent_tail.py` — modified: `protected`, `re_check`, `_changes`,
  `_reported`, `PROTECTED`; the timeout branch checks anchors first. 234 → 350.
- `application/steps/agent.py` — modified: `re_check` first in `execute`. 387 → 396.
- `application/steps/context.py` — modified: `RunEnvironment.anchors`. 398 → 400.
- `application/use_cases/walk.py` — modified: `_Frame`, `_frame`, `_anchors`,
  `_spec_folders`, `_frozen_test_files`, `_agent_ranges`, and the `_frame_start_sha` fix.
  315 → 399.
- `application/use_cases/{apply_step_result,writers}.py` — modified: `result.payload`
  threaded through `_park` into `park_run`'s record.
- `domain/values.py` — modified: `StepResult.payload`.
- `domain/ports/git.py` — modified: `ChangeKind`, `Change`, `Git.diff_changes`.
- `domain/ports/protected_paths.py` — modified: docstring only; the member set is still
  exactly `check`, which is what `tests/unit/test_run_environment.py` fixes.
- `infrastructure/git/worktrees.py` — modified: `diff_changes`; `status` now asks for every
  untracked file by name and for unquoted paths.
- `tests/unit/fakes/git.py` — modified, additively: the `diff_changes` script and method.
- Five new test modules: `application/test_protected_paths_rule.py`,
  `application/steps/test_agent_protected_paths.py`, `application/test_walk_frame_anchors.py`,
  `application/test_apply_step_result_payload.py`, and `test_git_diff_changes.py`, which
  covers the real adapter's `diff_changes` and the two `status` fixes against real `git`.

**Review findings:** 7 patched (3 high, 2 medium, 2 low), 6 deferred (frontmatter
`deferred`), 11 rejected. No `intent_gap` and no `bad_spec`, so no repair loopback ran. The
three high patches were escapes no gate could see: a new anchor inside a new directory was
never enumerated by porcelain, a timed-out attempt's anchor edit escaped every later range,
and the rule was bound outside Story frames where it could park `repo-init@1` on a file the
orchestrator wrote itself.

**Follow-up review recommended:** true. Three patched findings were `high` severity, which
sets the flag on its own.

**Verification performed (re-run by the coordinator, not only trusted from the
implementation subagent):**
- `make lint` — exit 0, twice (before and after the patch pass): ruff, mypy `--strict` over
  `domain/` + `application/`, all four import-linter contracts KEPT, env contract unchanged
  (31 settings fields / 37 `.env.example` variables — no new setting), `check_test_pairs`
  167/167 paired, `gen:api --check` no drift, web-client clean.
- `make test` — exit 0, twice: 4752 backend unit tests passed, 1 skipped (4654 before this
  story); web-client 973 passed; `domain/` + `application/` at 100 % branch under
  `--fail-under=100`.
- Branch coverage measured per module: `rules/protected_paths.py`, `steps/agent.py`,
  `steps/agent_tail.py` and `use_cases/walk.py` are each **100 %**.
- `pytest tests/unit/test_source_limits.py` — 532 passed: `context.py` 400, `agent.py` 396,
  `agent_tail.py` 350, `walk.py` 399, all ≤ 400.
- The anchor sweep flags only `tests/unit/fakes/{clock,workspace,git}.py`; the first two are
  earlier stories on this branch, and `git.py`'s own diff is additive (one keyword, one script
  entry, one method, and the module docstring's method list extended).
- `make e2e-api` / `make e2e-ui` / `make openapi` / `make durability` — **not run**: this
  story adds no route, no schema field, no UI and no durable-step change, and `gen:api --check`
  inside `make lint` already proves no contract drift.

**Residual risks.** The recorded `payload.hits` has no reader yet — `GateRecordOut` projects
six fields and drops `payload` — so the list is written for 5.9's trajectory and 5.10's Run
detail to pick up. The Accept branch is code without a caller until Epic 6 lands the signal
effect (`handle_signal` still refuses `continue` on a `protected_path` park), so it is proved
by unit tests over a hand-built gate record rather than by a Run. `_agent_ranges` reads "an
attempt carrying both SHAs" as an agent range, which is exact only while `end_sha` is written
by `agent_tail.finish` alone.

**What 5.7 and 5.8 must know.** The `# 5.7` seam is still where 5.5 left it, immediately after
`route(...)` in `agent_tail.tail`, and `tests/unit/application/steps/test_agent_tail.py` still
asserts over `inspect.getsource(tail)` that `"5.6"` precedes `"route("` precedes `"5.7"` — a
5.7 that replaces the comment with code must leave that ordering readable. `finish` now has a
second early return (the anchor check inside the timeout branch) ahead of `tail`. Line
pressure is now acute: `context.py` is **400/400**, `walk.py` **399/400**, `agent.py`
**396/400**; `agent_tail.py` (350) and the new `rules/protected_paths.py` (175) are where the
room is. `StepResult.payload` exists and `park_run` takes one, so a budget park that needs to
record figures has the channel already.
