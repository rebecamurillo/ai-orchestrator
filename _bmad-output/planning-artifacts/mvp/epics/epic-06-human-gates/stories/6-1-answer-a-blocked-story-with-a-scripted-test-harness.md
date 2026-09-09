---
status: done
date: 2026-09-09
---

# Answer a blocked story, with a scripted test harness

Story 6-1 (SPEC CAP-1, FR-18, NFR-8, UX-DR10, UX-DR17, AR-14; binds AD-9, AD-10, AD-13).

## What landed

**1 — the Answer's effect in the agent executor.**
`backend-api/src/orchestrator/application/steps/agent_answer.py` (new, 200 lines) moves the
one `{spec_folder}/stories/{id}-*.md` match to `stories/.answers/{id}-attempt-{n}.md` where
`n` is the previous attempt's number, appends `## Human Answer` with an ISO-8601-Z time from
the `Clock` port and the Operator's text, and returns **both** ends of the rename so
`agent.py::_prepare_writes` stages them into the prepare commit — an unstaged move would be
in the tree at `start_sha` and read as the agent's own edit (AD-17, FR-31). The glob is empty
afterwards, so the re-dispatch is a first dispatch and `bmad-build-auto` plans fresh.
Exactly one match is archived: none is logged `no file to archive` and proceeds as a first
dispatch, and two is the `ambiguous story file` misconfiguration only a Retry's
de-ambiguation may resolve.

**2 — the prompt clause, without touching `compose_prompt`'s frozen tests.**
`compose_prompt` is pure over the values the planner resolved and holds no `Workspace`, so it
cannot read the archived file's `Blocking condition:` line. `agent_answer.resolved_signal`
resolves both facts — the condition from the archived file (or `spec rejected` at a spec
checkpoint) and the text from `rules/signals.py::ANSWER_KEY` — into a `model_copy` of the
resume record under the keys `agent.py` already declares, and `_planned` passes that. The
signal contract is untouched and `test_agent_prompt.py` stayed frozen. *(Operator-approved
deviation from the ruling's wording, which had `compose_prompt` read `ANSWER_KEY` itself.)*

**3 — the Answer box.** `web-client/src/components/run/AnswerBox.tsx` renders under
`QuestionBlock` when the stop is `blocked` **and** `answer` is in `admitted_signals` — the
read model decides, nothing is hardcoded. `web-client/src/lib/run/answer.ts` holds the
verbatim UX-DR17 hint, reads the archive path off the response (`stories` strip's `current`
cell, the parked row's `latest.n`), and builds the `{kind: answer, payload: {text}}` body.
`RunDetail.tsx` gained a payload-carrying `sendSignal`. First `<textarea>` on the surface;
still no `dangerouslySetInnerHTML` anywhere.

**4 — the scripted `fake` harness (AR-14).**
`backend-api/src/orchestrator/infrastructure/harness/fake/` — `scenario.py` reads
`{worktree}/.fake-harness/{story_id}/attempt-{k}.yaml` (falling back to `default.yaml`) and
never raises on a malformed one; `adapter.py` applies the writes in `start`, then runs one
real `ProcessRunner` process (`sh` on a generated script: the sleep, the `fake <fake@local>`
commit, the result envelope, the exit code) so `pgid` is a group `kill_group` can reach
(AD-14) and `run` stays `wait(start(...))`. `usage` is read back out of the log through
`claude/result.py`'s parser, so the path under test is the production one.

**5 — the conditional an Operator never sees.** A bound `harness` value is never checked
against a Template's enum (`templates/inputs.py` reads `values` only to validate a default;
`api/schemas/runs.py` types it `str | None`), so the real gate is pre-flight's harness line.
`fake` is registered in `build_harnesses` and its `harness` row seeded **enabled** only under
`ORCH_TEST_MODE`; with test mode off there is no row, `create_run` refuses the name, and
`templates/{epic,story,initiative}.yaml` are byte-identical. `fake` is not in `HARNESS_NAMES`
and not in `HARNESS_VERSION_SETTINGS`.

**6 — the fixture and the e2e.** `fixtures/gates-repo/` (three stories, `check.sh` reading a
committed `GATE_OK`, `.fake-harness/` scenarios); `backend-api/tests/e2e/helpers/gates_fixture.py`
materialises it as a `file://` origin on either topology and reads the branch back;
`backend-api/tests/e2e/test_answer_signal.py` walks blocked → Answer → done on the compose
stack and asserts the archived question, the re-planned Story file, the echoed Answer clause
and `NOTIFY.md` on the branch.

## Anchor edits (both authorised, each with strictly-exceeding coverage in the same commit)

| File | Lines | Was | Is | New coverage |
| --- | --- | --- | --- | --- |
| `web-client/tests/unit/run-stop-body-blocked.test.ts` | 110-111 | `not.toContain` answer/textarea | `toContain` both | `tests/unit/run-stop-body-answer.test.ts` (17 tests) |
| `web-client/tests/e2e/run-detail-story-additions.spec.ts` | 173, 177-178 | comment + `toHaveCount(0)` ×2 | corrected comment + `toBeVisible()` / `toHaveCount(1)` | `tests/e2e/run-detail-answer.spec.ts` (4 tests) |
| `backend-api/tests/unit/application/test_handle_signal.py` | 209-221 | `answer not available yet` | the row reaches `queued`, the Run `running` | `tests/unit/application/test_answer_signal_scope.py` (9 tests) |

The `misconfigured` siblings (unit 166, e2e 264) and
`test_every_kind_outside_this_epics_scope_is_refused_not_available_yet` with its `ids` list
were not touched.

## Splits (no comment deleted to buy space)

- `application/steps/agent.py` 396 → 397 of 400: the archive went to a new
  `application/steps/agent_answer.py`, which re-exports `ANSWER_EVENT`/`ANSWER_KEY`/
  `CONDITION_KEY` back through `agent.py` so every existing import path still resolves.
- `main.py` 399 → 357 of 400: `HARNESS_VERSION_SETTINGS` and `seed_harness_table` moved to
  `infrastructure/db/seed.py`, re-exported from `main.py` (the `registry.py` precedent), so
  `run_migrations` still names one collaborator and the frozen monkeypatches still bind.

## Gates — all run from a clean tree, all green

| Gate | Result |
| --- | --- |
| `make lint` | pass — ruff, mypy, import-linter (4 contracts kept), env contract, test pairs (184 backend / 75 web), gen:api `--check`, eslint, prettier, astro check (0 errors) |
| `make test` | pass — 5098 passed, 1 skipped; `domain/` + `application/` **100 %** branch coverage; web 1031 passed in 76 files |
| `make openapi` | pass — no drift; `contracts/openapi.json` and `schema.d.ts` unchanged (the read model already published `answer`) |
| `make e2e` | pass — 154 passed, 11 deselected, 36 subtests, on the disposable `aio-e2e` stack with `ORCH_TEST_MODE=1` |
| `make e2e-ui` | pass — 124 passed |

## Notes for the next story

- **6-2 reuses the archive helper.** `agent_answer.archive_with_answer` fires on
  `resume_signal.event == "answer"` regardless of the park kind, and
  `agent_answer.condition` already answers `spec rejected` when the row carries
  `spec_checkpoint` — so a Reject at a spec checkpoint needs no new archive code, only the
  button and the park's own body. `compose_prompt` already suppresses `Halt after planning.`
  for any resume.
- **6-2 reuses the fake harness.** `fixtures/gates-repo/` already ships story `2`
  (`spec_checkpoint: true`) and story `3` (`done_checkpoint: true`) with `default.yaml`
  scenarios that finish in one pass — deliberately `default.yaml` rather than `attempt-1.yaml`,
  because a Continue makes the *second* dispatch for that story and both must write the same
  finished file. `tests/e2e/helpers/gates_fixture.py::epic_template_as` is how an e2e runs the
  epic plan without pinning `epic@1` (`test_templates.py` asserts `pinned_by == 0` for it).
- **`ORCH_TEST_MODE` defaults to `false`.** It is the only `Settings` field with a default,
  because `scripts/generate-env.sh` writes `.env.e2e` once and never rewrites it; a required
  field broke 79 e2e fixtures before this was found.
- **Still deferred to Epic 7, untouched:** a resumed dispatch records no `pgid`, and
  `Harness.resume` takes neither `model` nor `budget_usd_remaining`.
