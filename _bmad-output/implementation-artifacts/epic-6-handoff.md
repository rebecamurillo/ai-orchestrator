# Epic 6 handoff — the human gates, and the machine bug they uncovered

Written 2026-09-09, after story 6-8. For whoever builds Epic 7 and after.

`epic-1-handoff.md` … `epic-5-handoff.md` all still hold; nothing in them was undone here. Read this
once before your first Epic 7 story; you should not need it again.

Eight stories were dispatched and **all eight landed with every gate green**. Three halted on anchor
conflicts first and were resumed under an operator ruling; none was worked around. Two fixes landed
outside any story — one before story 6-1, one on the test harness itself — and both are described
below because they change how the repository behaves, not just what it contains.

The epic's own headline is not a feature. **The quality-gate retry loop had never worked.** Story 6-8
was the first thing to drive a Run past a failing gate, and it found that every such Run was
unrecoverable. See §2.

---

## 1. What you can rely on

Every AD-13 signal is landed, in scope, and applied by a resumed executor.

```
answer            archive to stories/.answers/, ## Human Answer, re-plan with the answer as context
continue          on an agent row at a checkpoint: re-dispatch with no halt suffix, no archive
                  on a protected_path park: record accepted files, re-run the tail with no dispatch
skip_story        remaining agent/checkpoint rows skipped, verify re-runs as re-baseline,
                  commit-guard rewritten to `story {id}: skipped by operator`
skip_epic         the current frame as skip_story, later frames skipped, push and link still run
                  (except on push_rejected, where both are skipped and the next epic starts)
budget_raise      resumes at the row's routed status; on a blocked/checkpoint row the body returns
terminal_start    terminal_release    terminal_resume
cancel            retry
```

```
application/rules/signals.py       the AD-13 table — VALID, Rule.text_from, Rule.extra_refusal
application/use_cases/signals.py   handle_signal — validate, refuse during a terminal session, apply
application/use_cases/terminal.py  resume_command · poll
application/jobs/terminal_poll.py  the 30 s job; infrastructure/terminal_jobs.py schedules it
application/steps/agent_answer.py  archive_with_answer · condition · halts_after_planning
application/use_cases/run_files.py list_files · read_file · write_file · diff
application/use_cases/run_views_alert.py    Alert.row_kind · Alert.checkpoint_story · Alert.payload
application/use_cases/run_views_summary.py  skipped_stories · skipped_epics
infrastructure/harness/fake/       the scripted test harness — scenario.py · adapter.py
fixtures/gates-repo/               stories 1, 2 (spec checkpoint), 3 (done checkpoint)
```

**Two endpoints, one router.** `GET`/`PUT /runs/{id}/files` live in `api/routers/run_files.py` with
`use_cases/run_files.py` and `api/schemas/run_files.py`. `GET` with no `path` is the tree, with a
`path` is content, with `diff=1` is a unified diff. The route count is **two** — `diff` is a mode, not
a route, because `api/routers/runs.py` has a frozen route-count test and every new endpoint this epic
added went into a sibling module instead.

**One migration:** `0010_terminal_clean_polls`. It survives `make durability`.

**Two settings:** `ORCH_TEST_MODE` (default `false`, test-only) and `TERMINAL_POLL_CRON`.

---

## 2. The bug that mattered — read this one

**FR-10's redispatch loop had never closed.** `apply_step_result::_redispatch` queues the redispatch
*target* and leaves the gate row that sent the walk back at `error`. `_advance` will not touch a
successor that is not `planned`. So once the re-dispatched Story finished, **nothing ever re-ran the
quality gate**: `close_run` read the leftover `error` row as a stall and parked the Run `internal`, a
stop that admits no signal but `cancel`.

Every Run whose quality gate failed once was unrecoverable, and AD-9's own `verify failed {n}/{n}`
park was unreachable. It was invisible for two epics because no test ever drove a gate failure past
its first turn — the two `test_apply_step_result.py` tests that come closest build their worlds with
an empty `with_resolved`, so neither carries a redispatch at all.

Fixed in `walk.py::_sent_back`, the exact twin of `_resumed_in_place`, using AD-8's existing
`("error","retry") → "queued"` pair. No new transition, no new counter.

**The guard on that fix is as important as the fix.** As first written, `_sent_back` would have
resumed a Run the *exhausted* bound had already parked: an exhausted redispatch leaves byte-identical
rows (target `done`, gate `error`) and differs only in that the Run is parked. `next_row` is called on
parked Runs — an Epic 4 test pins that contract — so `verify failed 2/2` would have un-parked itself
and the Operator's stop would never have held. It is guarded on the Run's own status.

### The failure mode this codebase keeps repeating

**A row moved with nothing enqueued leaves the Run unrecoverable.** Four instances now:

1. `continue` on a `plan_stale` park (Epic 4/5 defect, fixed in this epic's pre-story).
2. `_budget_raise` (fixed in 6-6). A `done` park row restarted only *by accident* —
   `walk.py::_start_the_plan` fires when every row is planned/done/skipped. An `error` row, which is
   FR-17's own retry path, matched none of `next_row`'s three ways of finding work.
3. `terminal_resume` — nearly, caught by 6-7 asserting against `next_row` itself.
4. `_redispatch`, above, and the first that is the machine's own re-execution rather than a signal.

**When you land a new signal effect or a new re-execution path, assert against `next_row`, not against
the repository.** "The row is queued" and "the walk finds it" are two different claims, and this
codebase has broken the second one four times while the first stayed true. `resume_from(ports, row)`
is the call the other effects use.

---

## 3. Decisions that are load-bearing — do not undo these by accident

**`_in_scope` is gone.** Epic 4 gated the signals endpoint with a "not available yet" scope list that
each Epic 6 story widened. Story 6-7 landed the last three kinds and retired the predicate *and* the
test that proved it, after checking the branch was genuinely dead: after `validate`, `continue`'s park
kind is always one of `CONTINUE_PARK_KINDS`, so the predicate was unconditionally `True`.
**`rules/signals.py::validate` is the only gate now.**

**AD-5 is structural, not a filter.** `env.py::identifiers()` and `terminal_contract()` **take no
`Settings` parameter**, so a credential has no path into the terminal command at all; the export list
*is* `HARNESS_ENV_ALIASES` because `registry.py::build_terminal_env` feeds reference values through
the same `AliasBuilder` the real environment uses. `domain/ports/harness.py` has `TerminalEnv` beside
`HarnessEnv` as a separate port precisely because one returns credentials and one must not. **Do not
"simplify" these into one function.**

**The terminal command's exports are shell-escaped, and `$` is deliberately not escaped.**
`ANTHROPIC_CUSTOM_HEADERS` carries `ORCH_LANGFUSE_TAGS`, a JSON array whose `"` characters closed the
double-quoted export early — the container would have exported malformed Langfuse tags and silently
corrupted AD-11 attribution. The command still *parsed*, so no string assertion saw it; it was found by
running the produced script through two real shells. `_escaped` handles `"`, `\` and backtick. `$` is
the mechanism and must survive.

**The terminal path runs *through* AD-17, not around it.** `terminal_resume` updates the attempt's
`end_sha` to HEAD, so `FrameAnchors`' `(start_sha, end_sha)` range covers the Operator's own terminal
work. A protected path touched by hand parks `protected_path` and is Accepted like any other change.

**Buttons come from `admitted_signals`, never hardcoded.** `stopSignals` / `blockedSignals` /
`checkpointSignals` are frozen; every control this epic added is **appended by a sibling filter**.
`lib/run/skip.ts` is the pattern. Note `offersSkipEpic` reads the parked row's own path rather than the
Template's name — a name check false-negatives against a custom-named copy of an initiative-shaped
Template.

**`spec_edit` widens the `GateEvent` type but not `ALL_GATE_EVENTS`'s pinned value**, mirroring the
`GATE_EVENTS ⊂ ALL_GATE_EVENTS` precedent from story 4-5. It touches no anchor.

**The `diff` mode is scoped to the Run's own recorded hit list, not the spec folder.** Every anchor
AD-17 protects — `AGENTS.md` anywhere, every frozen test file — is *outside* the spec folder by
construction, so `_within_spec_folder` would 403 exactly the paths the mode exists to show. The hit
list is strictly tighter and is state the Run wrote itself.

---

## 4. The rules that will bite you

**Modules were split, not trimmed.** Epic 5 bought space under the 400-line cap by deleting its own
explanatory prose; the operator stopped that here. Six splits landed, every public name re-exported:
`walk.py → walk_frame.py`, `agent.py → agent_answer.py`, `main.py → infrastructure/db/seed.py`,
`run_views.py → run_views_alert.py` and `→ run_views_summary.py`, and `rules/signals.py` split along
the seam between the table and the questions asked of it. **If you must grow a capped module, split it.**

**`agent_tail.py` is still exactly 400 lines and its marker order is frozen.** An assertion reads
`inspect.getsource(tail)` and requires `"5.6" < "route(" < "5.7"` — the protected-path check must win
over every route (FR-31). Do not reorder.

**New coverage goes in a new test file. Always.** Adding a test to an existing test file is itself an
anchor violation.

**Do not pin behaviour a later story's brief owns.** Story 6-1 wrote a test guessing at 6-2's
behaviour, guessed wrong, and cost the epic a halt and a ruling. Its own docstring admitted it was
guessing.

**Two Epic 5 PNGs change on every `make e2e-ui` run.** `epic-5-screens/{01,02}-*.png` are regenerated
by story 5.10's anchor spec, which screenshots the whole Run detail page — so they change whenever that
page's chrome changes. Commit the new bytes; reverting leaves the tree permanently dirty and editing
the anchor spec is forbidden.

**`.env` and `.env.e2e` are generated once and never rewritten**, so a new setting orphans them and the
backend comes up unhealthy. `.env.e2e` is disposable — delete and regenerate. `.env` is the operator's;
`TERMINAL_POLL_CRON` was appended to it by hand.

---

## 5. What Epic 6 has and has not proved

Story 5-11 ended the last epic by discovering its loop had never run for real. This epic ends one layer
deeper, and the same honesty applies.

**Proven end to end on the compose stack, with the real walker and real git** — story 6-8's `test_uj3.py`
walks one Run through all of it in 5.4 s, and `uj3.spec.ts` walks the same path in a real browser:

- the Answer — archive, `## Human Answer`, the re-planned file echoing the verbatim clause, the
  trajectory row carrying the human action;
- the spec checkpoint and *Continue* — no re-plan, no halt suffix; the done checkpoint and *Continue*;
- inline spec editing while parked — one `spec: operator edit (orchestrator)` commit, one `spec_edit`
  record, and the refusal order;
- `retry` and `skip_story` — the re-baseline, the rewritten commit message, the frame's checkpoint going
  with it, `summary.skipped`;
- `budget_raise`; `cancel` with real worktree and branch cleanup;
- **FR-10's redispatch loop, for the first time ever.**

**Proven only at the unit level, over fakes:**

- `skip_epic` — no fixture Run can satisfy `_has_epic_frame`'s `template_name == "epic"` branch,
  because the e2e must rename the Template (`test_templates.py` asserts `pinned_by == 0` for `epic@1`);
- *Reject* at a spec checkpoint;
- the `protected_path` Accept and its hit-list 409 — no scenario produces a real AD-17 hit on `fake`;
- **the whole terminal path** — `terminal_start` / `terminal_release` / `terminal_resume`, the resume
  command's contents, and `terminal_poll`'s two-clean-polls rule. The job runs in the stack every 30 s
  and is a proven no-op, but no e2e ever sets `terminal_session`;
- the `re-baseline failed after skip` park, and the `budget` / `timeout` / `push_rejected` stop bodies.

**`E2E_BACKEND=real make e2e-ui` is not a whole-suite gate.** 43 of 159 specs read stub-backend fixtures
server-side and fail against a real stack, because `page.route()` cannot intercept an SSR fetch. Exactly
one spec — the UJ-3 journey — runs against the product. Closing this needs `test.skip` in ten anchor
files and therefore an operator ruling.

---

## 6. What Epic 7 inherits

- **The deferred `Harness.resume` gap is still open and still deferred by operator decision.** A resumed
  dispatch records no `pgid`, and `Harness.resume` takes neither `model` nor `budget_usd_remaining`, so
  orphan control cannot reap a retry a dead backend interrupted and the budget can be exceeded by one
  attempt across a resume. Closing it changes the signature story 5-1's tests freeze. It did **not**
  block any Epic 6 story: the Accept resumes the tail with no dispatch, and the terminal path resumes
  outside the harness entirely.
- **The `fake` harness is the model for a new adapter.** It is registered only under `ORCH_TEST_MODE=1`,
  is absent from the shipped template enums, and its `harness` row is seeded in that mode — an operator
  never sees it offered. Note the mechanism: a bound `harness` value is never checked against a
  Template's enum, so **seeding the row is itself the gate** (pre-flight's `harness_line` refuses a
  harness with no row or a disabled one).
- **`fake` is deliberately not in `HARNESS_NAMES`**, which a frozen test pins to
  `("claude","codex","local")`. Adding `codex` in Epic 7 means that tuple, `HARNESS_VERSION_SETTINGS`,
  and the readiness path — not a new registry entry alone.
- **The harness-readiness Run structurally cannot reach `enabled`** — it dies on `baseline` before any
  agent row dispatches. See `deferred-work.md`; the fix is an unmade design decision.
- `Alert.payload` is generic, so a new stop can carry detail to the screen without a new field.
  `Rule.text_from` / `Rule.extra_refusal` build a signal's record sentence and refusal text.
- `make e2e` now tears its stack down **before** bringing it up (`aaa45d6`). A hard-killed run used to
  leave the Postgres volume holding parked Runs that occupied both `MAX_ACTIVE_RUNS=2` slots, starving
  `test_queue` and cascading — and presenting as a code defect in whatever story ran next.

---

## 7. Anchor rulings the operator granted, and why

Four, all recorded in the story specs. They are here so the *shape* of the exception is reusable, not
so they are treated as precedent for editing tests generally.

1. **Story 6-1** — two frozen Epic 5 web-client tests asserted a `blocked` detail renders no Answer box,
   on fixtures already carrying `admitted_signals: ['answer', …]`. Four lines were **inverted, not
   deleted**, so both files keep guarding against a regression.
2. **Story 6-1** — one backend test pinned `answer` as out of scope. Inverted, with the pending-gate
   registry beside it left untouched.
3. **Story 6-2** — story 6-1 had landed a test contradicting 6-2's own brief. This produced a standing
   rule for the epic: **where a test written earlier in this epic pins behaviour a later story's brief
   explicitly governs, the owning story may correct it.**
4. **Stories 6-5, 6-6, 6-7** — one ruling for a whole arc: a **pending-gate assertion** for a gate the
   story lands may be removed, whether a parametrized row or a standalone function, and the containing
   test goes with the last row. When the last kind landed, 6-7 retired the scope-gate illustration and
   the dead branch it proved.

**Every ruling required strictly-exceeding coverage in a new file in the same commit.** No test was ever
deleted, skipped or relaxed to make a gate pass, and no `SPEC.md`, `stories.yaml`, `epics.yaml` or
`AGENTS.md` line changed anywhere in the epic.

One process note for whoever orchestrates next: the harness flagged story 6-5's hand-back as a
*fabricated operator authorisation*. It was not — the ruling was granted in-session and relayed to the
subagent, which the classifier cannot see. **Audit the diff, not the warning.** Epic 4 hit the same
false positive twice.
