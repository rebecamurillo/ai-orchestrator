---
title: 'Terminal resume command, session flag, and poll'
type: 'feature'
created: '2026-09-09'
status: 'done' # draft | ready-for-dev | in-progress | in-review | done | blocked
baseline_revision: '2de81333cac92334682228c902552a7a6301ffff'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
deferred: []
---

<intent-contract>

## Intent

**Problem:** A parked Story can only be unblocked from the screen. FR-21 promises a second
path — the Operator takes the agent's own session over in a terminal — but nothing publishes
the command, nothing holds the screen's actions while she is in there, and nothing notices
when she leaves the Story `done` on a clean tree.

**Approach:** Publish a `terminal` block on the Run detail read model whose `command` is
assembled from identifiers alone (AD-5: secrets are referenced by shell name and resolved
inside the container); admit the three `terminal_*` signals through the scope gate; narrow
`admitted_signals` to `cancel` + `terminal_release` while a session is in progress; and add a
30-second `terminal_poll` job that counts two clean `done` polls and then sends
`terminal_resume`, which moves the agent row `blocked → done` with actor `terminal` and
queues its successor so the walker runs verify.

## Boundaries & Constraints

**Always:**
- **AD-5 by construction, not by filtering.** The command builder takes *no* `Settings`
  object and no secret-valued mapping. The eight `-e` values are `Run`/`Attempt`/story/project
  identifiers; every other contract name enters the alias builder as the literal shell
  reference `$NAME`, so a secret value has no path into the string, the read model, the
  OpenAPI contract, a log or a fixture. `GITHUB_TOKEN` is in neither list.
- The export list is the harness's own `HARNESS_ENV_ALIASES`, obtained by calling the very
  `AliasBuilder` `infrastructure/harness/registry.py` already binds — never a second copy.
- `signal_effects.py`'s three `terminal_*` effects and `rules/signals.py::VALID`'s three
  terminal rows are 4.5's and are **verified, not rewritten**, against the brief.
- `terminal_resume` must leave the Run recoverable: it calls `resume_from(ports, park_row)`
  and a test asserts `use_cases/walk.py::next_row` finds the queued successor.
- Every Run status write stays in `apply_step_result`/`signal_run` (AD-8). The poll writes
  only `run.terminal_clean_polls` and the attempt's `end_sha`, and sends the signal.
- `application/` imports no `dbos`, `subprocess`, `os` or `httpx`; the job is a pure
  function over ports, wired in `infrastructure/`.
- New settings land in `infrastructure/settings.py` **and** `.env.example` in one change.
- Modules stay ≤ 400 lines; `rules/signals.py` is at 397 and must be split, not trimmed.

**Block If:**
- The brief cannot be built without editing an assertion in a test file predating this
  branch (Epic 5 and earlier), or any line of `SPEC.md`, `stories.yaml`, `epics.yaml`, or an
  `AGENTS.md`. Report file, test, assertion, why it is unavoidable, and the minimal edit.

**Never:**
- No new route on `api/routers/runs.py` or `run.py`; no widening of `stopSignals` /
  `blockedSignals` / `checkpointSignals`; no `dangerouslySetInnerHTML`.
- No `pgid` on a resumed dispatch and no `model`/`budget_usd_remaining` on `Harness.resume`
  (Epic 7's, deferred by the operator). The terminal path resumes outside the harness, so
  neither blocks this story.
- No UJ-3 end-to-end scenario (6.8's).
- No codex/local harness (Epic 7). The mechanism is generic; `local` yields `terminal: null`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Claude agent park | `blocked` park on an `agent` row, harness `claude` (`capabilities.resume`), attempt has `session_id` and `started_at` | `terminal.command` = the eight `-e` identifier flags + `backend-api sh -c 'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY" ANTHROPIC_CUSTOM_HEADERS="…"; cd {worktree} && claude --resume {session}'`; `session_lifetime_ends_at` = start + 30 d | No error expected |
| Harness without resume, or unknown/`local` | park row's attempt `harness` not in the registry, or `capabilities.resume` false | `terminal` is `null` | No error expected |
| No session / not an agent row / no worktree | park row `kind != "agent"`, or attempt `session_id` empty, or `run.worktree_path` `None` | `terminal` is `null` | No error expected |
| Session lifetime unknown | harness is not `claude` (e.g. `fake`) | `session_lifetime_ends_at` is `null`; the line is not rendered | No error expected |
| Session in progress | `run.terminal_session` true | `admitted_signals == ("cancel", "terminal_release")`; `PUT /runs/{id}/files` 409 | `answer` → 409 `signal answer invalid …` |
| `terminal_start` twice | already `terminal_session` | 409 (`_no_terminal_session` refuses) | AD-13's `INVALID` sentence |
| `terminal_release` with no session | `terminal_session` false | 409 | AD-13's `INVALID` sentence |
| Poll: clean once | story file `done`, `git.status` empty, no `.git/index.lock` | `terminal_clean_polls == 1`; no signal | No error expected |
| Poll: clean twice | same, second fire | `terminal_resume` sent: row `done` (actor `terminal`), Run `running`, successor `queued`, counter back to 0, attempt `end_sha` = HEAD | No error expected |
| Poll: dirty between | `git.status` non-empty, or `.git/index.lock` present, or story file not `done`, or glob not exactly one match | counter reset to `0` | No error expected |
| Poll: no worktree / no park row | `run.worktree_path` `None`, or `park_path` names no row | counter reset to `0`, nothing sent | No error expected |
| Copy click | command block's Copy | clipboard holds the command, button reads `COPIED` ~1.2 s, `terminal_start` posted | A clipboard the browser refuses still posts and still reads `COPIED` |

</intent-contract>

## Code Map

**Backend — the scope gate and the illustration it retires.**
- `application/use_cases/signals.py::_in_scope` (~line 96) — the last three kinds join it.
  With `terminal_start`/`terminal_release`/`terminal_resume` admitted, and `validate` already
  refusing `continue` outside `CONTINUE_PARK_KINDS`, the function is **always true**: delete
  `_in_scope`, `NOT_AVAILABLE`, `CONTINUE_PARK_KINDS`, `CONTINUE_KIND`'s scope use and the
  `raise Conflict(NOT_AVAILABLE…)` line in `_refuse_early`, and rewrite the docstring
  paragraph that describes the refusal. Check first that nothing else reaches it.
- `tests/unit/application/test_handle_signal.py` (lines ~211-240) — standing authorisation
  (a): remove all three parametrize rows, the `ids` list, `_terminal_release_world`,
  `_terminal_resume_world`, and the now-vacuous
  `test_every_kind_outside_this_epics_scope_is_refused_not_available_yet`. Nothing else in
  that file changes.
- `tests/unit/test_signals_router.py::test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet`
  (line 160) — standing authorisation (b): retire it with the branch it proves. Nothing else
  in that file changes.

**Backend — `rules/signals.py` at 397/400, split before touching.**
- New `application/rules/signals_table.py` — move `Rule`, `_raised_budget`,
  `_raises_the_budget`, `_has_story_frame`, `_has_epic_frame`, `_budget_raised_text`,
  `_accepted_text`, `_no_terminal_session`, `_in_terminal_session`, `raised_budget`,
  `accepted_files`, `VALID`, `INVALID` and the constants (`PARKED`, `NON_TERMINAL`,
  `ANY_PARK`, `BUDGET_KEY`, `ANSWER_KEY`, `FILES_KEY`, `BUDGET_RAISED`, `BUDGET_TOO_LOW`,
  `ACCEPTED`, `ACCEPTED_SEPARATOR`, `REBASELINE_FAILED`). `raised_budget`/`accepted_files`
  go **with the table**, not with the questions: `_budget_raised_text`/`_accepted_text` call
  them, and splitting them the other way is an import cycle. Keep every explanatory comment.
- `application/rules/signals.py` keeps `validate`, `admitted_signals`, `run_admitted_signals`,
  `record_text`, `row_at`, `_refuse`, `_refuse_extra`, and re-exports every public name above
  (`__all__` + `from …signals_table import …`), so `apply_step_result.py`'s
  `REBASELINE_FAILED`, `signal_effects.py`'s `signals.accepted_files`/`signals.raised_budget`,
  `signal_run.py`'s `Rule`, and `run_views.py`'s `row_at`/`run_admitted_signals` all still
  resolve unchanged.
- `run_admitted_signals` gains the terminal narrowing, **before** the `needs_you` test:
  `if run.terminal_session: return TERMINAL_SESSION_SIGNALS` where
  `TERMINAL_SESSION_SIGNALS = ("cancel", "terminal_release")` (`VALID`'s own order).
  `terminal_release` cannot come from `admitted_signals` — its `operator_action` is `False`
  and must stay so, or it would be offered on every stop with no session at all.

**Backend — the command (AD-5's whole proof).**
- `infrastructure/harness/env.py` — extract the eight identifier names as
  `IDENTIFIER_NAMES = HARNESS_ENV_CONTRACT[:8]` and the identifier values `_contract` already
  computes into a shared `identifiers(attempt, run=…, project_slug=…, story_id=…,
  traceparent=…)`; `_contract` calls it, so the two orders cannot drift. Add
  `terminal_contract(...)`: `identifiers(...)` merged with `{name: f"${name}"}` for every
  other contract name. **It takes no `Settings`** — that signature is the AD-5 proof, and a
  test asserts it.
- `infrastructure/harness/registry.py::build_terminal_env(settings)` — returns the
  `TerminalEnv` port closure: picks `SUBSCRIPTION_ALIASES`/`ALIASES` off
  `settings.claude_subscription_auth` (a bool, not a secret) and calls the *same*
  `AliasBuilder` with the reference-valued contract, so `ANTHROPIC_AUTH_TOKEN` comes back as
  the literal `$LITELLM_API_KEY` and `ANTHROPIC_CUSTOM_HEADERS` as identifier-only header
  lines. `ORCH_LOG_CONTENT` arrives as `$ORCH_LOG_CONTENT`, never `"1"`, so the content-logging
  pair is absent from a terminal session — document it.
- `domain/ports/harness.py` — add `TerminalEnvironment(identifiers, exports)` (both
  `tuple[tuple[str, str], ...]`) and the `TerminalEnv` Protocol beside `HarnessEnv`. Do **not**
  add a method to the `Harness` Protocol: `tests/unit/test_harness_port.py` isinstance-checks
  doubles against it.

**Backend — the read model.**
- New `application/use_cases/terminal.py` — `Terminal(command, session_lifetime_ends_at,
  in_progress)`, `TerminalPorts(env: TerminalEnv, harnesses: Mapping[str, Harness])`,
  `SESSION_LIFETIME_DAYS = {"claude": 30}` (Epic 7 adds `codex`), and
  `resume_command(ports, run, park_row, attempt, project_slug) -> Terminal | None`. Guards, in
  order: park row is `AGENT_KIND`; `run.worktree_path` set; `attempt` present with a
  `session_id`; harness in the registry with `capabilities.resume`. Command shape is the
  brief's, verbatim; `ORCH_LANGFUSE_TAGS` is single-quoted (it is JSON), the rest bare.
- `application/use_cases/run_view_types.py` — `RunViewPorts.terminal: TerminalPorts | None =
  None` (the `tracer` precedent: every existing frozen construction keeps compiling);
  `RunDetailView.terminal: Terminal | None = None`.
- `application/use_cases/run_views.py::run_detail` (314/400, room) — one call, guarded on
  `ports.terminal is not None`, passing `project.slug` and `_latest_of(park_attempts)`.
- `api/schemas/run_views.py` — `TerminalOut` + `RunDetailOut.terminal: TerminalOut | None =
  None` with `json_schema_extra=_drop_default`, so web-client fixtures predating it compile.
- `api/providers.py::run_view_ports` — wire `TerminalPorts(env=build_terminal_env(settings),
  harnesses=build_harnesses(settings, RealProcessRunner()))`.

**Backend — the poll.**
- New `application/jobs/terminal_poll.py` — `TerminalPollPorts(uow, runs, steps, attempts,
  git, workspace, signal: SignalPorts)`, `CLEAN_POLLS_TO_RESUME = 2`, `INDEX_LOCK =
  ".git/index.lock"`, `RESUMED_TEXT`, `run_terminal_poll(ports) -> list[UUID]`. Reads the
  story file through `Workspace.glob` on `agent_tail.STORY_FILE_GLOB` formatted from the park
  row's own `with_resolved` (`SPEC_FOLDER_KEY`/`STORY_ID_KEY`) and `story_file.parse`;
  `routing.DONE` is the status token. Clean tree = `git.status(worktree).strip() == ""` **and**
  not `workspace.exists(INDEX_LOCK)`.
- `domain/entities/run.py` — `terminal_clean_polls: int = 0`, beside `terminal_session`.
- `infrastructure/db/models/run.py`, `repositories/runs.py` (both halves of the mapping),
  `alembic/versions/0010_terminal_clean_polls.py` (`down_revision = "0009_trajectory"`,
  `Integer NOT NULL server_default "0"` — a `NOT NULL` column with a default, the
  `0007_run_gc` precedent, so `test_run_repository_adapter.py`'s frozen nullable set is
  untouched).
- `infrastructure/settings.py` — `terminal_poll_cron: str`; `.env.example` gets
  `TERMINAL_POLL_CRON` beside the other two crons.
- **`infrastructure/jobs.py::scheduled_jobs` must not grow.**
  `tests/unit/test_scheduled_jobs.py` (Epic 4, predates this branch) asserts the list is
  exactly `[clone_check, worktree_gc]` and that `schedule_jobs` registers exactly those two.
  The terminal poll also genuinely needs the `WorkflowEngine` — for `SignalPorts` — which
  `scheduled_jobs(settings, session_factory, git)` never receives. So: new
  `infrastructure/terminal_jobs.py::engine_jobs(settings, session_factory, git, engine)` and
  `infrastructure/dbos/startup.py::schedule_engine_jobs(settings)` (the `_SERVING` guard
  `schedule_jobs` already uses, plus the engine each entry holds), called from `main.py`
  beside `schedule_jobs(settings)`.

**Frontend.**
- New `src/lib/run/terminal.ts` — `TerminalOut` type, `terminalBlock(detail)`,
  `sessionLifetimeLine(endsAt)` (`session lifetime ends {date}`), `TERMINAL_SESSION_LINE`
  (verbatim), `RELEASE_LABEL`, `COPIED_LABEL`, `COPIED_MS = 1200`, `COMMAND_EYEBROW =
  'OR CONTINUE IN THE SESSION'`, and `terminalSignals(admitted)` — the sibling filter that
  appends `terminal_release`; `stopSignals`/`blockedSignals`/`checkpointSignals` are untouched.
- New `src/components/run/CommandBlock.tsx` — the eyebrow bar with the Copy button
  (`wf-terminal-copy`), a `<pre data-testid="wf-terminal-command">` that scrolls
  horizontally and never wraps, the lifetime line, and — while `in_progress` — the session
  line and *Release* (`wf-terminal-release`). Clipboard through `navigator.clipboard`, in a
  `try`/`catch` so a refused clipboard still posts and still shows `COPIED`.
- `src/components/run/StopBody.tsx` — render `CommandBlock` when `detail.terminal` is not
  null, above the button row; two new optional props (`onTerminalStart`, `onTerminalRelease`).
- `src/islands/RunDetail.tsx` — pass the two callbacks, each `void sendSignal(kind)`.
- `src/styles/run-detail.css` — `.wf-command-*` on `--color-surface-inset` /
  `--color-line-strong`, `white-space: pre; overflow-x: auto`.

**Reused, unchanged:** `ConfirmAction.tsx`, `signal_effects.py::_terminal_*` + `resume_from`,
`rules/signals.py::VALID`'s three terminal rows, `run_files.py::write_run_file`'s
`or run.terminal_session` refusal (already landed in 6.3 — confirm with a test, do not edit).

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/application/test_signals_table.py` (new) -- the split's public
  surface and `run_admitted_signals`' terminal narrowing -- TDD first, and the test-pair
  gate needs a test importing `rules/signals_table.py`.
- `backend-api/tests/unit/test_terminal_command.py` (new) -- the command's shape **and the
  absence of every secret value** -- AD-5 is proved by test, not by review.
- `backend-api/tests/unit/application/test_terminal_signals.py` (new) -- the three kinds now
  apply through `handle_signal` and the router; strictly exceeds the three removed rows and
  the retired scope-gate illustration.
- `backend-api/tests/unit/application/test_terminal_poll.py` (new) -- the whole matrix above,
  including `next_row` finding the queued successor after `terminal_resume`.
- `backend-api/src/orchestrator/application/rules/signals_table.py` (new) + `…/rules/signals.py`
  -- split and re-export; add the narrowing -- 397/400 with no headroom.
- `…/domain/ports/harness.py`, `…/infrastructure/harness/env.py`, `…/harness/registry.py` --
  `TerminalEnvironment`/`TerminalEnv`, `identifiers`/`terminal_contract`, `build_terminal_env`.
- `…/application/use_cases/terminal.py` (new), `…/run_view_types.py`, `…/run_views.py`,
  `…/api/schemas/run_views.py`, `…/api/providers.py` -- the read model.
- `…/application/use_cases/signals.py` -- retire the scope gate; `…/domain/entities/run.py`,
  `…/infrastructure/db/models/run.py`, `…/db/repositories/runs.py`,
  `alembic/versions/0010_terminal_clean_polls.py` -- the counter.
- `…/application/jobs/terminal_poll.py` (new), `…/infrastructure/terminal_jobs.py` (new),
  `…/infrastructure/dbos/startup.py`, `…/main.py`, `…/infrastructure/settings.py`,
  `.env.example` -- the job and its cron.
- `web-client/src/lib/run/terminal.ts`, `…/components/run/CommandBlock.tsx` (both new),
  `…/components/run/StopBody.tsx`, `…/islands/RunDetail.tsx`, `…/styles/run-detail.css`.
- `web-client/tests/unit/run-terminal-lib.test.ts`, `…/run-command-block.test.ts`,
  `web-client/tests/e2e/run-detail-terminal.spec.ts` (all new) -- copy, `COPIED`, the posted
  signal, the disabled-actions line, and no secret in the rendered command.

**Acceptance Criteria:**
- Given a Run parked `blocked` on a `claude` attempt, when the detail is read, then
  `terminal.command` holds the eight identifier `-e` flags, `sh -c` with the alias exports by
  name and `cd {worktree} && claude --resume {session}`, `session_lifetime_ends_at` is the
  attempt's start + 30 days, and **no** value of `LITELLM_API_KEY`, `LANGFUSE_SECRET_KEY`,
  `LITELLM_SPEND_KEY`, `GITHUB_TOKEN`, `ORCHESTRATOR_TOKEN` or `ORCHESTRATOR_SECRET_KEY`
  occurs anywhere in it.
- Given a `local` (or otherwise non-resumable) attempt, when the detail is read, then
  `terminal` is `null` and the section is not rendered.
- Given `terminal_session` true, when `answer` is posted, then 409; when `terminal_release`
  is posted, then 200 and `admitted_signals` returns the stop's own actions.
- Given the command block, when Copy is clicked, then the clipboard holds the command, the
  button reads `COPIED` for about 1.2 s, `terminal_start` is posted, and the session line and
  *Release* appear.
- Given the poll on the fakes with the story file `done` and a clean tree, when run twice,
  then the first sets `terminal_clean_polls = 1` and the second sends `terminal_resume` — the
  row `done` with actor `terminal`, the Run `running`, the successor `queued` and found by
  `next_row`; and a dirty tree between the two resets the counter to 0.
- `contracts/openapi.json` and `web-client/src/api/schema.d.ts` are regenerated and carry
  no secret value and no secret *name* other than the shell references inside `command`'s
  own example-free schema (the schema publishes types, never a command instance).

## Spec Change Log

**Two plan changes, both forced by an anchor that predates this branch.**

1. **`terminal` moved from `RunDetailOut` to `RunDetailOut.run`.** The plan put it at the top
   level; `tests/unit/test_run_detail_router.py::test_a_known_run_answers_every_section`
   (story 4-12, Epic 4) asserts `set(body)` is a closed set of nine section names, and a tenth
   key fails it. No exception applies, so the block went where the brief's own words already
   put it — "in the Run read model", beside `run.terminal_session`, whose value its
   `in_progress` is. `RunDetailSummaryOut` has no closed-set assertion, and the field is
   `_drop_default`-guarded, so every web-client fixture predating it still compiles. The nine
   top-level keys are screen *sections*; `terminal` is a property of the Run, like `worktrees`
   and `accepted_paths` beside it.
2. **`api/schemas/run_views.py` had to be split.** Adding `TerminalOut` took it to 416 of the
   400 lines `tests/unit/test_source_limits.py` enforces. The three Alert shapes moved to
   `api/schemas/run_alert.py` along the seam `application/use_cases/run_views_alert.py`
   already cut on the builder side, and are imported straight back.

**One correction to 4.5's own table, driven by the brief.** `VALID["terminal_resume"].text`
read `resumed from the terminal session`; the brief states the record as `story file done and
tree clean, resumed by terminal`. The table now carries the brief's sentence
(`signals_table.py::TERMINAL_RESUMED`), and `terminal_poll` re-exports it rather than keeping
a second copy. No test asserted the old string.

## Review Triage Log

**Two defects found by the review layers, both fixed, both now covered.**

1. **`ANTHROPIC_CUSTOM_HEADERS` was corrupted by the inner shell** (high). The header carries
   `ORCH_LANGFUSE_TAGS`, a JSON array, and its `"` characters closed the double-quoted export
   a character early — so the pasted command exported `langfuse_tags: [run:…, attempt:…]`,
   which is not JSON, and AD-11's attribution would have been silently wrong for every Gateway
   call made from the terminal. The command still *parsed*, so no string assertion could see
   it. Fixed with `_escaped`/`_single_quoted` (`"`, `\` and backtick escaped; `$` deliberately
   not, because the reference is the mechanism), and covered by
   `test_terminal_command.py::test_the_langfuse_tag_header_is_still_json_after_two_shells`,
   which runs the command's own script through a real `/bin/sh` and parses the result.
2. **The command block stretched the grid track instead of scrolling** (medium). A grid
   track's `min-width` is `auto`, so the deliberately unwrappable command widened the whole
   left column and scrolled the *page* sideways — the opposite of UX-DR5's rule. Found by
   `run-detail-terminal.spec.ts`'s own `scrollWidth > clientWidth` assertion. Fixed with
   `min-width: 0` on `.wf-left, .wf-right`.

**One design correction.** `terminalSignals` and a second helper had no production caller: the
Release control was rendered off `terminal.in_progress` rather than off `admitted_signals`,
which the operator's standing rule forbids. `CommandBlock` now takes `canRelease`, computed by
`offersRelease(detail.admitted_signals)`, and the unused helper was deleted.

## Design Notes

**Why the command cannot leak, stated as a mechanism.** `terminal_contract` has no
`Settings` parameter, so the only strings it can produce are the eight identifiers and
`"$NAME"` literals. `claude_aliases` is then called on that mapping — the same function the
real environment uses — so the export list *is* `HARNESS_ENV_ALIASES` and
`ANTHROPIC_AUTH_TOKEN` comes back as `$LITELLM_API_KEY` because that is literally what the
contract said `LITELLM_API_KEY` was. Subscription mode is covered by the same trick: its
extra header renders `Bearer $LITELLM_API_KEY`.

```python
def terminal_contract(attempt, *, run, project_slug, story_id, traceparent):
    known = identifiers(attempt, run=run, project_slug=project_slug,
                        story_id=story_id, traceparent=traceparent)
    return {**known, **{name: f"${name}" for name in HARNESS_ENV_CONTRACT if name not in known}}
```

**"The other buttons are disabled" vs. the read model.** The brief's own binding rule says
`admitted_signals` *drops* `answer`/`continue`/`skip_*`/`retry` while a session is in
progress, so those controls are not offered at all — buttons come from `admitted_signals`,
never hardcoded. The screen states the fact in the brief's own words (`… Answer, Continue,
Skip and Retry disabled until Release …`), which is strictly stronger than a greyed button:
nothing is clickable and the copy says why and until when.

**`end_sha` on resume (the brief's `[ASSUMPTION]`).** Set the park row's latest attempt's
`end_sha` to `git.head_sha(worktree)` before signalling. AD-17's `FrameAnchors` diffs
`(start_sha, end_sha)` per attempt, so without it everything the Operator did in the terminal
is invisible to the commit-guard's protected-path check. Resolving it this way means the
terminal is a second path *through* AD-17, not around it: a protected path touched by hand
parks `protected_path` and is Accepted like any other.

**Why `SESSION_LIFETIME_DAYS` is a table in the use case.** A session's lifetime is a harness
fact, but `HarnessCapabilities` is a set of booleans ("every field defaults to `False`") and a
duration is not a capability. A one-entry name-keyed table, `run_views.py::_KIND_LABELS`'s own
shape, keeps it beside the only rule that reads it.

## Notes for the next story (6-8, UJ-3 proven end to end)

- **The three `terminal_*` kinds all apply now**, and `use_cases/signals.py::_in_scope` is
  gone with them: `handle_signal` refuses nothing this epic has not built, because there is
  nothing left. `validate` is the whole of AD-13's refusal again, plus two cross-cutting
  checks that AD-13's columns cannot see — the Accept's hit list (6.6) and
  `_refuse_during_terminal_session` (this story).
- **A terminal session refuses every action but `cancel`, `terminal_release` and
  `terminal_resume`, with a 409** (`IN_TERMINAL_SESSION`). An e2e scenario that parks a Run
  and then posts `answer` will get a 409 if anything ever left `terminal_session` set — the
  `fake` harness never sets it, so nothing in the existing suite is affected.
- **`terminal_poll` now runs in the compose stack**, every 30 s, over
  `list_by_status("needs_you")`. It is a no-op for every Run without `terminal_session`, and
  `make e2e` and `make durability` both pass with it firing. `TERMINAL_POLL_CRON` is in
  `.env.example`, so a scenario can shorten it.
- **`fake` resumes but states no session lifetime**, so a `fake`-harness Run publishes a
  `terminal` block whose `session_lifetime_ends_at` is `null` and whose command ends
  `cd {worktree} && {the fake's own resume line}`. If 6-8 asserts on a Run detail body, that
  block is now present on any `blocked` park of an `agent` row with a session id.
- **`run.terminal_clean_polls` is a new `run` column** (migration `0010`), `NOT NULL`
  default `0`.
- **Still deferred to Epic 7, untouched:** a resumed dispatch records no `pgid`, and
  `Harness.resume` takes neither `model` nor `budget_usd_remaining`. Neither blocked this
  story: the terminal path resumes *outside* the harness entirely — the Operator's own shell
  runs the CLI, and the orchestrator only notices the result.
- **`.env` and `.env.e2e` are generated once and never rewritten**, so a new contract variable
  orphans an existing file and the backend then fails start-up (its container reports
  unhealthy, which is what `make e2e` shows). Delete `.env.e2e` and re-run
  `./scripts/generate-env.sh e2e`; top up `.env` by hand.

## Verification

**Commands:**
- `make lint` -- expected: ruff/mypy/import-linter/env-contract/test-pairs/eslint/tsc clean
- `make test` -- expected: green, 100 % branch coverage on `domain/`+`application/`
- `make openapi` -- expected: contract and `schema.d.ts` regenerate, no drift on re-run
- `make e2e` -- expected: green in its own disposable stack
- `make e2e-ui` -- expected: green (run `make down` first — both bind 4321)
- `make durability` -- expected: green, the new migration survives restart
