# Test Automation Summary — orchestrator-initiative-steps / epic-1-step-logs

Generated: 2026-11-23. This run was dispatched with an empty story id, so it covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-1-step-logs/SPEC.md` (the path is relative to the hub).
Stories: 1–7 (commits `04dca98c`..`792089c5`).
Previous summary (orchestrator-run-metrics epic-6-analysis-tier2): in git history at `9c0433db`.

Framework: the project's own suites.
- pytest and httpx in `backend-api/tests/e2e`, run by `make e2e-api` (inside `make e2e`).
- This epic changes no web-client code apart from the regenerated `schema.d.ts`. No Playwright test is added.

Every story is covered by unit tests on fakes. The e2e module checks what only a real Run shows: the walker writes the logs to disk through the real `FsStepLog`, real git answers the drawer and files-by-epic reads, and the graph, the steps table and the drawer report the same `(seq, n)` for one Run. No existing test file was touched. No shipped template is read. The module uses the suite's own `tests/e2e/templates/hub*.yaml` and `fixtures/hub-repo`.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_step_logs.py` (27 tests).
  - **Fixture.** One hub Run is started with `start_hub_run` from `test_hub_run.py` and walked to alpha-epic's done checkpoint. The module reads the Run's graph once, then cancels the Run when it ends.
  - **CAP-4 (story 4), identity and run order:**
    - Each row that ran has a node with `seq`, ascending `attempt_ns`, and `attempt_n = max(attempt_ns)`. The steps-table row's `attempt_ns` is the same.
    - A row that is only planned (beta's story build) has `attempt_n` null and `attempt_ns` empty.
    - Story frame `epics[0].stories[0]`: `sync` is BEFORE, `build` is AGENT, `commit-guard` is AFTER, and every row is in seq order.
    - Epic frame `epics[0]`: `branch` and `baseline` are BEFORE, `spec-gate` is AGENT, and the done checkpoint is AFTER. The frame contains no story row.
    - Root frame: `checkout` and `submodules` are BEFORE.
  - **CAP-5/6 (stories 5–6), the drawer:**
    - With `n=0`, the drawer shows the latest attempt, lists every attempt, and its `run_order.frame` is the story frame. A drawer opened by an explicit `n` shows that attempt.
    - A build attempt on the fake harness reports `files_read` as `not_recorded`.
    - The workdir `commit-guard` row reports `files_written.state=commit`, with the sha and the subject `story 1: Ship the alpha feature (orchestrator)`. Its file list contains `repos/alpha/src/alpha_feature.py`.
    - The skipped `setup` row has `n` null, no attempts, and log `not_run` with the row's own reason.
    - An unknown Run, seq or attempt gets a 404 problem+json. A request without the bearer gets a 401.
  - **CAP-1/2/3 (stories 1–3), logs:**
    - For `git.submodule`, `git.merge` (story sync) and `git.commit`, the drawer's log state is `text`. The log endpoint returns `state=text`, `eof`, and lines starting `> `.
    - The commit log contains a `> commit …` line.
    - No log line of five deterministic rows contains `ORCHESTRATOR_TOKEN`.
  - **CAP-7 (story 7), files by epic:**
    - Both epics are listed in plan order, with folder and title.
    - Alpha lists `SPEC.md`, `stories.yaml` and `spec-gate-result.md` in that order. `RETROSPECTIVE.md` is absent, so it is left out.
    - Beta lists only its seeded `SPEC.md` and `stories.yaml`.
    - Alpha story 1 has `started` true and `story_file` `…/stories/1-work.md`. Beta story 1 has `started` false, no file and no change.
    - Every path in `changed` gets a 200 from the diff route. An unchanged path, an epic index outside the list, and an unknown Run each get a 404.

## Coverage

- API endpoints added or changed by this epic: 5 of 5 are exercised end to end:
  - `GET /runs/{id}/graph` (node identity and `run_order`)
  - steps-table `attempt_ns`
  - `GET /runs/{id}/attempts/{aid}/log` (state `text`)
  - `GET /runs/{id}/steps/{seq}/attempts/{n}/drawer`
  - `GET /runs/{id}/files-by-epic` and `/diff`
- Covered by unit tests only:
  - the log states `no_output` and `removed`, and the sweep mark (getting them on a stack needs retention to pass)
  - `refs updated:` lines (the fixture's heads do not move during sync)
  - `files_read=listed` (needs the Claude extractor)

## Verification

- `ruff check`, `ruff format --check` and `pytest --collect-only` (27 collected) pass on the new module.
- **Not run against a stack.** The epic's spec forbids starting, stopping or calling a running instance. Its quality gate is lint, test and openapi drift, with no e2e. So `make e2e` was not run in this dispatch. Before relying on this module, run `make e2e` on a machine where the disposable `aio-e2e` stack is allowed.
- Assertions that rest on code reading rather than an observed run:
  - the `commit-guard` subject and member path prefix
  - the exact list of alpha spec files at the checkpoint
  - the story file path

## Next Steps

- Run `make e2e` and fix any assertion the live stack contradicts.
- Epic 2 (Run page review) adds the Playwright side of these reads.
