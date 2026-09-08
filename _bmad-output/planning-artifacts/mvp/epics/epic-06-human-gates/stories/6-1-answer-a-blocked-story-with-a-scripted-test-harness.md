---
status: blocked
---

# Answer a blocked story, with a scripted test harness

## Auto Run Result

Status: blocked
Blocking condition: anchor conflict — two frozen Epic 5 web-client test files assert that a
`blocked` park with `answer` in `admitted_signals` renders **no** Answer box, which is exactly
the state story 6-1's Answer box acceptance criterion requires it to render one for. The story
cannot be built without revising those assertions, and neither test names a later story as the
thing that replaces them, so hard rule 1's placeholder exception does not reach them. Only the
operator can authorise the edit.

### The conflict, exactly

**1. `web-client/tests/unit/run-stop-body-blocked.test.ts`**

- Test: `describe('StopBody · blocked')` → `it('shows the whole question and exactly the admitted skip/cancel buttons')` (lines 81–113).
- Fixture (line 95): `admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel']`, `alert.park_kind: 'blocked'`.
- Assertions that fail once the Answer box exists:
  - line 110 — `expect(html).not.toContain('data-testid="wf-signal-answer"');`
  - line 111 — `expect(html).not.toContain('<textarea');`

**2. `web-client/tests/e2e/run-detail-story-additions.spec.ts`**

- Test: `test('a blocked story shows the whole question, attribution, admitted skips, the strip states, and provisional cost with a trace link')` (line 105).
- Fixture (lines 34 and 91): `admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel']`, `alert.park_kind: 'blocked'`.
- Assertions that fail once the Answer box exists, under the comment
  `// exactly the admitted signals this epic renders for a blocked stop — never Answer`:
  - line 177 — `await expect(page.getByTestId('wf-signal-answer')).toHaveCount(0);`
  - line 178 — `await expect(page.locator('textarea')).toHaveCount(0);`

The sibling `misconfigured` assertions (unit line 166, e2e line 264) are **not** in conflict:
`misconfigured` never admits `answer`, so those two `textarea` counts stay true and must stay.

### Why it is unavoidable

- The brief's second acceptance criterion is *"**Given** the Answer box **When** rendered on a
  `blocked` detail **Then** the hint reads the verbatim line with the right file name, the button
  is disabled until text is typed, and clicking posts the signal."* The Answer box is specified to
  sit *under the question block*, which `components/run/StopBody.tsx:69` is the only renderer of.
- `answer` is **already** admitted by the backend for exactly this state:
  `application/rules/signals.py::VALID` gives `answer` `park_kinds={blocked, checkpoint}`,
  `row_kinds={agent}`, and `run_views.run_detail` (`application/use_cases/run_views.py:213-235`)
  publishes it. What is missing is only the scope gate —
  `application/use_cases/signals.py::_in_scope` (line 70) admits `cancel`, `retry` and `continue`
  and 409s everything else with `"{kind} not available yet"`. So the two fixtures above are not
  hypothetical shapes: they are the shape the read model produces today. There is no additional
  field the component could gate on that a real Epic 6 response would carry and these fixtures
  would not.
- Moving the box out of `StopBody` into `RunDetail` would keep the unit assertions true but not
  the e2e ones: `page.locator('textarea')` is page-wide.
- Any gate that keeps those assertions true would have to suppress the Answer box in precisely the
  state the story exists to serve, i.e. drop the acceptance criterion.

### Minimal edit requested

In the same commit that lands the Answer box, and nothing else in either file:

- `web-client/tests/unit/run-stop-body-blocked.test.ts` — delete lines 110–111, or invert them to
  `expect(html).toContain('data-testid="wf-signal-answer"')` / `toContain('<textarea')`.
- `web-client/tests/e2e/run-detail-story-additions.spec.ts` — delete lines 177–178, or invert them
  to `toHaveCount(1)`; the comment on line 176 would read "…and the Answer box Epic 6 adds".

Strictly-exceeding coverage would land beside them in new files —
`web-client/tests/unit/run-stop-body-answer.test.ts` (hint line verbatim, disabled-until-typed,
`wf-answer` + `wf-signal-answer` present only when `answer` is admitted, absent on
`misconfigured`) and `web-client/tests/e2e/run-detail-answer.spec.ts` (type, click, assert the
posted body `{kind: 'answer', payload: {text}}`, assert the 409 detail beside the button) — so the
two files above lose nothing that is not re-asserted more strongly.

### Everything else in this story is unblocked

Recorded here so a re-dispatch after authorisation does not repeat the investigation.

#### Code Map

- `backend-api/src/orchestrator/application/steps/agent.py` (396 lines, cap 400) —
  `compose_prompt` (line 151) **already implements the `answer` branch**: `ANSWER` at line 95 is
  ` Answer from the operator to the blocking condition "{condition}": {answer}`, read from the
  gate record's `payload["condition"]`/`payload["answer"]`. Note the brief and `signal_run` use
  `payload["text"]` for the answer (`application/rules/signals.py::ANSWER_KEY = "text"`, line 68)
  and store no `condition` at all — so either `compose_prompt`'s key names or the record's payload
  must be reconciled; this is a real decision the brief leaves open. The archived file's
  `Blocking condition:` line is available through
  `application/story_file.py::blocking_condition` (line 109).
- `_prepare_writes` (line 224) is the extension point: it already collects
  `agent_tail.archive_ambiguous(ctx)` moves plus written files, stages each and makes one
  `PREPARE_MESSAGE` commit. `_archive_with_answer` slots in as a third contributor and must run
  first, before `story_files` is read again. **agent.py has 4 lines of headroom**, so this needs
  the split the operator described: a new
  `backend-api/src/orchestrator/application/steps/agent_answer.py` beside `agent_tail.py`, on the
  `walk.py` → `walk_frame.py` precedent, with no comment deleted from `agent.py`.
- `backend-api/src/orchestrator/application/steps/agent_tail.py` (exactly 400 lines — no
  headroom): `ANSWERS_DIRECTORY = "{spec_folder}/stories/.answers"` (line 86) is the constant to
  reuse; `story_files(ctx)` (line 274) is the glob; `archive_ambiguous` (line 290) is the model for
  the move-and-report-both-ends contract (`workspace.move`, return `[path, archived]` so
  `_prepare_writes` stages both — an unstaged move would be attributed to the agent by AD-17).
- `backend-api/src/orchestrator/domain/ports/workspace.py` — `move`, `read`, `write`, `glob`,
  `mtime` are all present; no port change needed.
- `backend-api/src/orchestrator/application/story_file.py` — `appended(text, block)` (line 144) is
  the writer for the `## Human Answer` block; `section` and `blocking_condition` read the archived
  file. Nothing new needed beyond a constant for the block.
- `backend-api/src/orchestrator/application/steps/context.py` (400 lines, no headroom) —
  `StepContext.resume_signal` is a `GateRecord`; `require_workspace`, `require_cwd`,
  `resolved_text`, `committed` are the helpers to reuse. Do not grow this module.
- `backend-api/src/orchestrator/application/use_cases/signals.py:70` `_in_scope` +
  `CONTINUE_PARK_KINDS` (line 55) — the one-line widening that turns the standing 409
  `"answer not available yet"` into a real signal. `application/rules/signals.py::VALID` already
  admits it; `run_views.py:213-235` already publishes it.
- Fake harness: `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py`, shaped on
  `infrastructure/harness/claude/adapter.py` (371 lines) — `name`, `capabilities`
  (`preassign_session=True, resume=True, native_tracing=False`), `run` = `wait(start(...))`,
  `start` returns a `HarnessHandle`, `wait` calls `runner.wait` under
  `except BaseException: kill_group; raise`. Registered in
  `infrastructure/harness/registry.py::build_harnesses` (line 48) behind
  `settings.orch_test_mode`.
- Process shape: the scripted file effects belong in `start` before the process exists; the
  process itself should still go through `ProcessRunner` (`sh` on a generated script doing
  `sleep {sleep_seconds}`, the optional `git commit` as `fake <fake@local>`, `exit {exit_code}`),
  so `pgid` is a real group `_orphan_control`/`kill_group` can safely reach and `timed_out` comes
  from the runner's own deadline. A fabricated `pgid` would be an AD-14 hazard.
- Attempt counter: the k-th call per story per worktree must **not** be stored inside the
  worktree — `_wip_commit` (agent.py:214) would commit it and it would dirty the commit guard.
  `settings.work_dir / "fake-harness" / <worktree key> / <story_id>` is outside every worktree and
  survives a restart.
- Settings: `orch_test_mode: bool` in `infrastructure/settings.py` (no prefix — the env name is
  the field name uppercased) **and** `ORCH_TEST_MODE=0` in `/.env.example` in the same change
  (hard rule 8); `scripts/check_env_contract.py` fails both directions otherwise.
- Harness row: `HARNESS_NAMES = ("claude", "codex", "local")`
  (`domain/entities/harness.py:26`) is pinned verbatim by
  `tests/unit/application/test_harness_readiness_start_unknown_name.py:130` and
  `HARNESS_VERSION_SETTINGS` must equal it (line 140) — so **`fake` must not be added to
  `HARNESS_NAMES`**. Seed the `fake` row separately in `main.py::seed_harness_table`
  (lines 176–210) under the test-mode flag. `tests/e2e/test_harnesses.py` asserts the three names
  are *present*, not that they are the only ones, so a fourth row is safe there.
- Template enum: `templates/{epic,story,initiative}.yaml` all declare
  `harness: { type: enum, values: [claude, codex, local], default: claude }`. `fake` has to be
  added to at least `epic.yaml` and `story.yaml` for a Run to name it. No test pins those values
  (`tests/e2e/test_templates.py` pins `epic@1`'s input *count* = 8, unchanged;
  `tests/unit/application/templates/test_plan_rows.py` and `test_plan_agent_row.py` use their own
  inline templates). These files are not anchors.
- Fixture: `fixtures/gates-repo/` modelled on `fixtures/readiness-repo/`
  (`README.md`, `check.sh`, `specs/…/SPEC.md`, `specs/…/stories.yaml`), plus `.fake-harness/`
  scenarios. Pre-flight (AD-16) requires `_bmad/_config/manifest.yaml` at `plan_ref` matching
  `BMAD_VERSION`; the helper can write that manifest at materialisation time exactly as
  `tests/e2e/test_clone_check.py::manifest_stating` does, so no `npx bmad-method install` is
  needed for a fixture the fake harness never plans against.
- e2e helper: `backend-api/tests/e2e/helpers/gates_fixture.py`, modelled on
  `tests/e2e/test_clone_check.py::Fixtures` (lines 76–135) — one `sh` script run either on the
  host or through `docker compose exec -T backend-api`, writing a bare origin under
  `$WORK_DIR/e2e-fixtures` and registering it by `file://`.
- e2e stack must run in test mode: `.env.e2e` is generated once from `.env.example` and never
  rewritten (`scripts/generate-env.sh:70-156`), so `ORCH_TEST_MODE=1` belongs on `backend-api` in
  `docker-compose.e2e.yml` (compose `environment:` wins over `env_file:`), not in the generator.

#### Design notes

- New source modules need a unit test that imports them (`scripts/check_test_pairs.py`, run by
  `make lint`), and anything under `application/` needs 100 % branch coverage
  (`Makefile:39`).
- `make test` is 400-line-capped per module by `tests/unit/test_source_limits.py`;
  `agent.py` (396), `agent_tail.py` (400) and `context.py` (400) all need the split route.
- New coverage goes in new test files only. Planned new files: backend
  `tests/unit/application/steps/test_agent_answer_archive.py`,
  `tests/unit/test_fake_harness_adapter.py`, `tests/unit/test_fake_harness_scenarios.py`,
  `tests/unit/test_gates_fixture.py`, `tests/e2e/test_answer_signal.py`; web-client
  `tests/unit/run-answer-box.test.ts`, `tests/unit/run-stop-body-answer.test.ts`,
  `tests/e2e/run-detail-answer.spec.ts`.
- `make e2e-ui` and the dev stack both bind 4321 — `make down` first.

### Gates

Not run. No implementation was attempted, so there is nothing to gate; the working tree holds
only this record.
