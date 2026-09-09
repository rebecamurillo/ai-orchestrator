---
status: blocked
---

# Answer a blocked story, with a scripted test harness

## Auto Run Result

Status: blocked
Blocking condition: a second, distinct anchor conflict — `backend-api/tests/unit/application/
test_handle_signal.py::test_answer_is_refused_not_available_yet_once_validation_passes`
asserts that `answer` is refused `"answer not available yet"` on exactly the park this story
must make it work on. It is a different file from the two the operator authorised, the ruling
covers "these four lines only", and it does not name a later story, so hard rule 1's
placeholder exception does not reach it. Halting rather than extending the ruling by analogy.

### Round 1 (resolved by the operator)

The web-client conflict is **authorised**: invert
`web-client/tests/unit/run-stop-body-blocked.test.ts` lines 110-111 and
`web-client/tests/e2e/run-detail-story-additions.spec.ts` lines 177-178, correct the e2e's
line-173 comment, leave everything else in both files — including the `misconfigured`
assertions at unit 166 and e2e 264 — untouched, and land
`run-stop-body-answer.test.ts` + `run-detail-answer.spec.ts` in the same commit. Recorded so
the next dispatch applies it without re-deciding.

### Round 2 — the blocking conflict

**File:** `backend-api/tests/unit/application/test_handle_signal.py`
**Test:** `test_answer_is_refused_not_available_yet_once_validation_passes` (lines 209-221)
**Assertions:**

```python
world = parked("blocked", BUILD, "blocked")          # BUILD = "stories[0].build"
with pytest.raises(Conflict, match="answer not available yet"):
    send(world, ports, "answer", text="use the psycopg adapter")
assert world.status_of(BUILD) == "blocked"
assert world.stored_run().status == "needs_you"
```

**Why it is unavoidable.** `application/use_cases/signals.py::handle_signal` is the single seam
between the router and `signal_run`; `_in_scope` (line 70) admits only `cancel`, `retry`, and
`continue` on `{checkpoint, plan_stale}`, and raises `Conflict("{kind} not available yet")` for
everything else. Story 6-1's first AC requires `answer` on a `blocked` agent row to move the row
to `queued` and resume the engine, which means passing that gate. `signal_effects.py` already
implements the `answer` effect correctly (4.5 built all ten kinds), so the only change needed is
widening `_in_scope` — and that is exactly what this test forbids. There is no second seam: the
router calls `handle_signal` and nothing else.

**Why it is not covered by the round-1 ruling.** Different file, and the ruling says "This
authorisation covers these four lines only… Do not extend this ruling by analogy."

**Minimal edit requested.** Invert the one test to assert the landed behaviour, keeping its two
state assertions inverted with it — nothing else in the file changes, and the parametrized
`test_every_kind_outside_this_epics_scope_is_refused_not_available_yet` (lines 236-262) does not
list `answer` and stays exactly as it is:

```python
def test_answer_moves_the_blocked_row_and_resumes_the_run() -> None:
    world = parked("blocked", BUILD, "blocked")
    ports = effect_ports(world)
    outcome = send(world, ports, "answer", text="use the psycopg adapter")
    assert world.status_of(BUILD) == "queued"
    assert outcome.run.status == "running"
```

Strictly-exceeding coverage lands beside it in a new
`backend-api/tests/unit/application/test_answer_signal_scope.py`: the gate record's `answer`
event and its `text`, that `answer` on a `timeout` park still gets AD-13's own refusal text
(the brief's fourth AC), and that the three kinds still outside scope keep the
`"not available yet"` refusal.

### Conflicts checked and found NOT to be conflicts

Swept before halting, so the next dispatch needs no further rulings:

- `tests/unit/application/steps/test_agent_prompt.py:66-81` pins `compose_prompt`'s `answer`
  branch to payload keys `condition`/`answer`, while `signal_run` stores the operator's text
  under `rules/signals.py::ANSWER_KEY == "text"`. **Avoided without an edit**: `compose_prompt`
  is a pure function over resolved values and holds no `Workspace`, so it cannot read the
  archived file's `Blocking condition:` line anyway. The new `application/steps/agent_answer.py`
  resolves both facts — the condition from the archived file (or `spec rejected` at a spec
  checkpoint) and the text from `ANSWER_KEY` — and `_planned` passes `compose_prompt` a
  `resume_signal.model_copy` whose payload carries them under the keys `agent.py:86-87` already
  declares. `compose_prompt`'s contract is unchanged and still true, so the file stays frozen.
  This is a deliberate deviation from the ruling's wording ("read the operator text from
  `ANSWER_KEY`" *inside* `compose_prompt`) that keeps its intent and avoids a third anchor edit.
- `tests/unit/application/steps/test_agent_retry_dispatch.py:292-302`
  (`test_a_resume_that_is_not_a_retry_archives_nothing`, parametrized over `answer`/`continue`)
  stays green: the brief scopes the answer archive to **exactly one** `stories/{id}-*.md` match,
  and that test's world is the ambiguous one with two. Two matches archive nothing and the row
  parks `misconfigured`, which is also the honest reading of the brief.
- `tests/unit/test_signals_router.py:170-177` posts `answer` and expects AD-13's own
  `"invalid for status"` refusal — its Run is not parked `blocked`, so `validate` refuses before
  the scope gate either way.
- `tests/unit/test_harness_registry.py:43,58,76` and `tests/unit/test_main_harness_registry.py:25,32,43`
  pin `build_harnesses` to `["claude"]` and to a subset of `HARNESS_VERSION_SETTINGS`. Safe: the
  unit `env` fixture derives from `.env.example`, so with `ORCH_TEST_MODE=0` there the `fake`
  adapter is never registered.
- `tests/unit/test_main_templates_seed.py:85` (`recorder.order == ["migrate", "seed", "harness"]`)
  is about `run_migrations`'s three collaborators; seeding a fourth *row* inside
  `seed_harness_table` does not touch it.
- `tests/unit/test_e2e_isolation.py:164` forbids `ports` on `backend-api` in the overlay, not
  `environment`, so `ORCH_TEST_MODE=1` can go there.
- `tests/unit/test_env_contract.py` and `test_settings.py` derive every count from
  `Settings.model_fields` and the contract file, so adding `ORCH_TEST_MODE` to both passes.
- `web-client/tests/unit/run-detail-lib-blocked.test.ts:72` and `run-detail-lib.test.ts:275`
  pin `blockedSignals` to exclude `answer` and `hasEffect('answer')` to be `false`. Neither
  changes: the Answer box is its own component with its own payload-carrying post, not a member
  of the plain button row.

### The `fake` harness enum — resolved without touching the shipped templates

The operator ruled `fake` must be admitted only under `ORCH_TEST_MODE=1`, with the conditional in
plan-time validation and the shipped templates unchanged. Investigation shows that is already the
shape of the system: a bound `harness` value is **never** checked against a template's enum
`values` — `templates/inputs.py` uses `values` only to validate a declared *default*, and
`api/schemas/runs.py:58` types `harness` as `str | None`. The real admission gate is pre-flight's
`harness_line` (`application/preflight/checks.py:242-259`), which fails for a harness with no
`harness` row or a disabled one, and `create_run` refuses on that failing line
(`create_run.py:190-195`). So seeding the `fake` row `enabled: true` **only** in test mode is
itself the conditional: without test mode there is no row, `create_run` 409s, and New Workflow —
which renders the template's declared `values` — never offers `fake`. `templates/epic.yaml`,
`templates/story.yaml` and `templates/initiative.yaml` stay exactly as they are.

### Code Map (carried forward; still current)

- `application/steps/agent.py` (396/400 lines) — `compose_prompt` at line 151 with `ANSWER`
  at line 95 and `CONDITION_KEY`/`ANSWER_KEY` at 86-87; `_prepare_writes` at line 224 is the
  extension point, running `agent_tail.archive_ambiguous` first and making one
  `PREPARE_MESSAGE` commit over everything staged. Four lines of headroom, so the archive goes
  in a new `application/steps/agent_answer.py` (the `walk.py → walk_frame.py` precedent), which
  also owns the resolved-payload helper described above.
- `application/steps/agent_tail.py` (exactly 400) — `ANSWERS_DIRECTORY` at line 86,
  `story_files` at 274, `archive_ambiguous` at 290 (the model for reporting **both** ends of a
  move so `_prepare_writes` stages them; an unstaged move is attributed to the agent by AD-17).
  No headroom: add nothing here.
- `application/story_file.py` — `blocking_condition` (109) reads the archived file's condition;
  `appended` (144) writes the `## Human Answer` block.
- `application/use_cases/signals.py:70` `_in_scope` — the one-line widening this halt is about.
- `application/rules/signals.py:141-148` — `answer` already admitted on `{blocked, checkpoint}`
  × `{agent}`, `text_key = ANSWER_KEY = "text"`; `admitted_signals` already publishes it, so no
  read-model change is needed for the button to appear.
- `infrastructure/harness/fake/adapter.py` (new), shaped on
  `infrastructure/harness/claude/adapter.py` (371 lines): `run` = `wait(start(...))`, scripted
  file effects in `start` before the process exists, then one real `ProcessRunner` process
  (`sh` on a generated script: `sleep`, optional `git commit` as `fake <fake@local>`, `exit`),
  so `pgid` is a real group `kill_group` can reach and `timed_out` is the runner's. Capabilities
  `preassign_session=True, resume=True, native_tracing=False`. Per-story attempt counter under
  `settings.work_dir`, never inside the worktree (`_wip_commit`, agent.py:214, would commit it).
- `infrastructure/harness/registry.py:48` `build_harnesses` — add `fake` behind
  `settings.orch_test_mode`.
- `main.py:173-210` `seed_harness_table` / `HARNESS_VERSION_SETTINGS` — seed the `fake` row and
  enable it, in test mode only. `domain/entities/harness.py:26` `HARNESS_NAMES` stays
  `("claude", "codex", "local")`.
- `infrastructure/settings.py` — `orch_test_mode: bool`, plus `ORCH_TEST_MODE=0` in
  `/.env.example` in the same change (hard rule 8).
- `docker-compose.e2e.yml` — `environment: ORCH_TEST_MODE=1` on `backend-api` (compose
  `environment` beats `env_file`; `scripts/generate-env.sh` never rewrites an existing
  `.env.e2e`).
- `fixtures/gates-repo/` on the `fixtures/readiness-repo/` shape, plus a
  `_bmad/_config/manifest.yaml` written at materialisation time exactly as
  `tests/e2e/test_clone_check.py::manifest_stating` does — pre-flight (AD-16) needs the pinned
  `BMAD_VERSION` there, and the fake harness never plans, so no `npx bmad-method install`.
- `backend-api/tests/e2e/helpers/gates_fixture.py` on
  `tests/e2e/test_clone_check.py::Fixtures` (lines 76-135): one `sh` script run on the host or
  through `docker compose exec -T backend-api`, bare origin under `$WORK_DIR/e2e-fixtures`,
  registered by `file://`.
- Web: `src/components/run/StopBody.tsx` (157/300) renders `QuestionBlock` at line 69 — the
  Answer box is a new `src/components/run/AnswerBox.tsx` under it, gated on
  `kind === 'blocked' && detail.admitted_signals.includes('answer')`. The archived filename's
  `{id}` comes from `detail.stories.find(s => s.state === 'current').story_id` and `{n}` from
  `stepAt(detail.steps, currentStepPath(detail))?.latest?.n`. `src/islands/RunDetail.tsx`
  (163 lines) owns the in-flight and 409 state, as it already does for `onSignal`.

### Gates

Not run. No implementation was attempted this round either; the working tree holds only this
record.
