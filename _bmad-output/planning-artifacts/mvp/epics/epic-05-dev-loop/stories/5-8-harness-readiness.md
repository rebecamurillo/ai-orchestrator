---
title: 'Harness readiness'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

# Harness readiness

## Auto Run Result

Status: done

**Resolution of the anchor conflict this file originally recorded as `blocked`.** The
operator ruled on it: authorised a revision of exactly two assertions —
`tests/e2e/test_harnesses.py::test_the_response_is_the_one_list_envelope` and
`tests/unit/test_harnesses_router.py::test_harness_out_of_renders_every_field` — to admit
`last_readiness_run_id` and `lines`, on the conditions that both stay exact closed-set
equalities (now seven names, not five), that the same commit adds tests asserting the
*values* those two fields carry after a real `evaluate()` run (not merely their presence),
and that nothing else in either file changes. Both conditions are met; see "Anchor check"
below for the diff and the new test. The walker-hook finding this file also recorded
(`on_terminal`, a second hook beside `run_finished`) and the gitignore-line-count finding
(three, not the brief's "two" — followed the landed `bmad_install.py::IGNORED` tuple) are
both implemented as originally proposed.

**What was implemented.**

- **The built-in `readiness` Project and its Repository** are seeded from inside
  `main.py::seed_harness_table`'s own body — not as a fourth top-level collaborator of
  `run_migrations` (`tests/unit/test_main_templates_seed.py::
  test_run_migrations_migrates_then_seeds_and_returns_the_head` closes that function's call
  sequence to exactly three named collaborators, `seed_harness_table` one of them, replaced
  wholesale by that test's own fake — extending its body changes nothing that test
  observes). `sync_pins` runs first, against the *stored* `version_pin`, before the existing
  upsert overwrites it; then `harness_readiness_seed.seed_readiness_project` creates the
  Project (`slug: readiness`, `builtin` computed from slug — see below) and its Repository
  (`url: file://{WORK_DIR}/readiness/origin.git`, `quality_gate_command: sh check.sh`) once,
  and re-runs the clone check every start-up (idempotent).
- **`Project.builtin` carries no migration.** `tests/unit/test_project_repository_adapter.
  py::test_the_table_carries_exactly_the_columns_the_entity_has` closes the `project` table
  to nine literal column names and names no successor story — a second anchor, not
  operator-authorised, discovered while implementing. Resolved without any anchor edit:
  `builtin` is derived from `slug == READINESS_PROJECT_SLUG` inside
  `infrastructure/db/repositories/projects.py::to_entity`, never a stored column. `Project.
  builtin` and `ProjectView.builtin` both default `False` so every pre-existing
  `Project(...)`/`ProjectView(...)` construction — every frozen fixture among them — keeps
  reading unchanged.
- **`application/use_cases/harness_readiness.py`** (`start`) dispatches `create_run` with
  `template: epic@1`, `project`/`repository` resolved by slug, `base_branch: main`,
  `branch: readiness/{name}/{date}` (suffixed `-2`, `-3`... past whatever a non-terminal Run
  for the harness already holds), `spec_folder: specs/readiness`, `harness: name`,
  `budget_usd: settings.readiness_budget_usd`, `skip_harness_check=True` (the existing,
  already-landed `CreateRunPorts.skip_harness_check` flag — AD-10's carried-forward caller,
  needed no change). `Conflict` (409) when a non-terminal readiness Run for that harness is
  already in flight.
- **`application/use_cases/harness_readiness_evaluate.py`** (`evaluate`) reads a finished
  readiness Run back: the `build` row (found by `path.endswith(".build")`, not a hard-coded
  path — the planner's own dotted naming is not this module's concern) and its latest
  attempt, the `verify` row, and the story file at the attempt's `end_sha` (via the base
  clone `Git.read_file`/`list_files`, reusing `application/templates/lists.py::_states_done`
  and `application/use_cases/clone_check.py::_base` rather than reimplementing either). Six
  lines, in the brief's own order — `story file done`, `session id recorded`,
  `trace observed`, `spend attributable`, `verify exit 0`, `run done` — each `{check, ok,
  text}`; all six `ok` writes `enabled=True, failing_check=None`, otherwise `enabled=False`
  and `failing_check` is the first failing line's `"{check}: {text}"` (the AC's own exact
  wording, `"trace observed: no spans for attempt …"`, is a literal test assertion, not a
  guess). `last_readiness_at`/`last_readiness_run_id` are written unconditionally, pass or
  fail — a readiness Run that cannot even start still has to leave `GET /harnesses` saying
  so.
- **The walker's second hook.** `infrastructure/dbos/walker.py::WalkerDeps.on_terminal`
  (`Callable[[UUID], None] | None`), fired from `_finish` for every status in the new
  `TERMINAL` set (`done`, `failed`, `cancelled`) — an addition beside the existing
  `run_finished` branch, not a change to it: `test_dbos_walker_on_finished.py`'s own
  `DONE`-only assertion is untouched and still passes, because `on_terminal`'s branch is
  new code the old test never observes. Wired in `infrastructure/dbos/startup.py::
  walker_deps` through a new `infrastructure/db/harness_readiness.py::
  readiness_evaluate_hook`, mirroring `run_finished_hook`'s own session-per-call shape,
  reusing the same `LangfuseTracer`/`LiteLLMSpend` instances `walker_deps` already builds.
  `evaluate` itself is the gate on "is this a readiness Run" (checks `project.slug`), so the
  hook fires unconditionally and no-ops for every other Run — the same pattern
  `run_finished.on_finished`'s template-name gate already uses.
- **Endpoints.** `POST /api/v1/harnesses/{name}/readiness` → 201 `{run, starts_now,
  waiting}` (reuses `CreateRunOut`, the same shape `POST /runs` answers), 404 when the
  Project/Repository is not yet seeded, 409 on an in-flight readiness Run. A router of its
  own (`api/routers/harness_readiness.py`), not a growth of `harnesses.py`: that module's
  own frozen route-count test pins it to exactly `GET /harnesses`. `GET /harnesses/{name}/
  readiness` (200 `HarnessOut`, 404 for an unknown name) was added beside it, discovered
  necessary only once `make lint` ran for real: `tests/unit/test_bearer_auth.py::
  test_the_contract_declares_the_401_and_its_media_type` indexes `paths[path]["get"]` for
  *every* published `/api/v1` path (the same reason `api/routers/run.py`'s own docstring
  gives for `GET /runs/preflight` existing beside the `POST`) — a `POST`-only path broke
  that frozen sweep, and the fix is the established pattern, not a workaround.
- **`GET /harnesses`** (`api/routers/harnesses.py`, untouched) now renders
  `last_readiness_run_id`/`lines` through `HarnessOut.of`, which is all that changed —
  `harnesses.py`'s own route stayed frozen. Both new fields carry Python defaults
  (`None`/`[]`) *nullable*, not merely defaulted: `openapi-typescript` marks a defaulted but
  non-nullable field required in the generated client type regardless of the contract's own
  `required` list, and only a nullable one optional. Nullable defaults are what let
  `web-client/tests/unit/harness-list.test.ts` and `newwf-state.test.ts` — frozen, and
  predating this story — keep compiling against the regenerated contract with no edit.
  `model_dump()`/the actual JSON response still always renders both keys; only the OpenAPI
  `required` list (and hence the generated TS type) changed.
- **`fixtures/readiness-repo/`** (`README.md`, `check.sh` — exits 0 once `HELLO.md` exists
  and contains "hello" — `specs/readiness/SPEC.md`, `specs/readiness/stories.yaml` with one
  story `id: "1"`, no checkpoints) and **`scripts/readiness_fixture.sh`**: idempotent,
  rebuilds `$WORK_DIR/readiness/origin.git` from a scratch copy of the fixture every run,
  running the identical `npx bmad-method@{version} install --yes --modules bmm --tools
  claude-code,codex,opencode` command `bmad_install.py::INSTALL_COMMAND` runs for a real
  Run, appending the same three `.gitignore` lines its `IGNORED` tuple does. Wired into
  `backend-api/docker-entrypoint.sh` between the harness `configure` loop and `alembic
  upgrade head` (`tests/unit/test_dockerfiles.py::STARTUP_ORDER` checks relative order only,
  not adjacency — untouched and still passes). `backend-api/Dockerfile` copies `fixtures/`
  and the script the same way it already copies `templates/` and `scripts/harness/`.
- **Settings.** `READINESS_BUDGET_USD` (`Decimal`, `.env.example`/`.env`/`.env.e2e` all
  three, default `5`) — `Settings.readiness_budget_usd`.
- **New workflow line.** Unchanged by this story: `web-client/src/lib/newwf/state.ts` and
  `src/components/HarnessList.tsx` were already scaffolded by an earlier story for exactly
  this route (`HarnessList.tsx`'s own docstring names `POST /harnesses/{name}/readiness` as
  the wiring trigger) and already render `"{name} · enabled | disabled: {failing_check or
  'no readiness run'} · last readiness {time or —} · "` with a `re-run readiness` link.
  Flipping that link from an inert `<a href>` GET to an active POST that follows through to
  the created Run's card requires editing `harness-list.test.ts`'s and `new-workflow.spec.
  ts`'s own placeholder assertions (`"not available yet"`, the inert href) — outside this
  story's operator authorisation, which named exactly two backend assertions. Deferred; see
  below.

**Files changed:** 19 added (6 backend source modules, 1 migration, 8 new backend test
modules, 1 shell script, 4 fixture files — `fixtures/readiness-repo/{README.md,check.sh,
specs/readiness/{SPEC.md,stories.yaml}}`), 20 modified (14 backend source, 2 backend test —
the two authorised — `Dockerfile`, `docker-entrypoint.sh`, `.env.example`,
`contracts/openapi.json`, `web-client/src/api/schema.d.ts`).

**Verification performed** (every gate actually run, in the foreground, its exit code
observed directly — none reported from memory):

- `make lint` — exit 0: ruff check/format, `mypy --strict` over `domain/`+`application/`,
  import-linter (4/4 contracts kept), env-contract check (32 settings / 38 `.env.example`
  vars agree), `check_test_pairs` (172 backend + 71 web-client, every new module paired),
  `gen:api --check` (no drift), web-client astro-check/eslint/prettier/tsc all clean.
- `make test` — exit 0: 4869 backend unit tests passed, 1 skipped;
  `coverage report --include='domain/*,application/*' --fail-under=100`
  — 100% branch, every new module (`harness_readiness.py` 100%, `harness_readiness_
  evaluate.py` 100%, `harness_readiness_seed.py` 100%) included; web-client 973/973 passed.
- `make openapi` — exit 0: `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerated and committed with this story, both required (new routes, new `HarnessOut`/
  `ProjectRead` fields).
- `make e2e` (wraps `e2e-api`) — exit 0, observed directly: **145 passed, 11 deselected, 36
  subtests passed** against the real built image — the readiness fixture's `npx bmad-method
  install` ran for real inside the container at start-up, the `readiness` Project/Repository
  seeded, the clone check ran, and the whole existing e2e-api suite (including the two
  revised assertions) passed against it.
- `make e2e-ui` — exit 0, observed directly: 118 passed.
- `make durability` — exit 0, observed directly: 11 passed, 145 deselected — the new
  migration (`0008_harness_readiness`) applies cleanly through the restart-and-orphan proof.
- Branch coverage measured per new module (`--cov-branch`): `harness_readiness.py`,
  `harness_readiness_evaluate.py`, `harness_readiness_seed.py` — each **100%**.

**Anchor check** (the literal command from the dispatch instructions):
```
for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done
```
Flags exactly five files: `tests/unit/fakes/{clock,git,workspace}.py` (pre-approved,
carried from earlier stories on this branch, none touched here) and
`tests/e2e/test_harnesses.py` + `tests/unit/test_harnesses_router.py` — the two the operator
authorised. Both diffs are additive-only: two new keys added to an already-closed-set
equality, nothing else in either file changed. The value-asserting coverage the
authorisation's second condition requires lives in a new file,
`tests/unit/test_harnesses_readiness_fields_values.py`: it runs a real `evaluate()` over a
fully-passing scripted Run and asserts `HarnessOut.of(updated).last_readiness_run_id` equals
that Run's own id, `enabled is True`, `failing_check is None`, and the six lines' `(check,
ok)` pairs and two of their `text` values (`"session sess-42"`, `"2 calls attributed"`) —
values, not presence.

**What was moved to make room, and final line counts.** `main.py` (377 → 399/400): the
`seed_harness_table` docstring was tightened rather than left at its original length, and
the `for router in (...)` tuple that mounts feature routers stayed a one-liner with a
separate `_mount(app, harness_readiness.router)` call rather than growing to a multi-line
tuple, saving five lines against the alternative. `harness_readiness_evaluate.py`'s six
per-check helper functions are typed against `Attempt | None`/`Repository | None` directly,
not `object` + inline `isinstance` narrowing, keeping the module a clean 214/400. No
pressure-point module named in the dispatch (`agent_tail.py`, `context.py`, `walk.py`,
`run_views.py` either file, `agent.py`) was touched; all five remain at their pre-story line
counts. New modules: `harness_readiness.py` 120, `harness_readiness_evaluate.py` 214,
`harness_readiness_seed.py` 131, `api/routers/harness_readiness.py` 64,
`infrastructure/db/harness_readiness.py` 62 — all comfortably under 400.

**Deferred.**
1. **The New workflow "re-run readiness" wiring** (making the existing inert link an active
   POST that follows to the created Run's card) — blocked on the same class of anchor as the
   backend one, in `web-client/tests/unit/harness-list.test.ts` and `tests/e2e/
   new-workflow.spec.ts`, not covered by this story's operator authorisation. The backend
   endpoint (`POST /harnesses/{name}/readiness`) and the regenerated contract are both
   ready; only the frontend click-through remains.
2. The brief's exact wording for `scripts/readiness_fixture.sh`'s gitignore step says "the
   two gitignore lines"; the implementation follows the landed `bmad_install.py::IGNORED`
   tuple (three lines) instead, per the operator's own instruction to do so and record the
   wording mismatch here.

**What 5-9 / 5-10 / 5-11 must know.**
- **Hook points.** `WalkerDeps.on_terminal` is the seam for "do X when a Run of some
  Project reaches any terminal status" — reuse it rather than adding a third hook;
  `run_finished` stays `DONE`-only and frozen.
- **Line-count pressure.** `main.py` is at 399/400 — one line of headroom. Any story that
  adds a fourth call inside `seed_harness_table`, a new top-level `run_migrations`
  collaborator, or another router mount will need to trim elsewhere first, not just append.
  `harness_readiness_evaluate.py` (214) and `harness_readiness_seed.py` (131) have real
  room if 5-11 needs to extend either.
- **What 5-11 must actually do to run this for real.** Everything here was built and
  proven against fakes and the real e2e-api/e2e-ui/durability gates — never against live
  LiteLLM/Langfuse/a real `claude` CLI, per this story's explicit scope boundary. To make a
  `claude` readiness Run reach `enabled` for real, 5-11 needs: (a) real `LITELLM_API_KEY`/
  `LITELLM_SPEND_KEY`/Langfuse keys in `.env` (currently placeholders, deliberately); (b) the
  host LiteLLM/Langfuse stack up (it already is, per this dispatch's own notes) and reachable
  from the compose network; (c) `POST /harnesses/claude/readiness` dispatched against the
  running dev stack (`make up`, not the disposable e2e one) so the readiness Project's
  fixture origin persists long enough for the agent to actually clone, work, and push; (d)
  confirm the fixture's own `_bmad/` (installed by `scripts/readiness_fixture.sh` at
  container start) actually carries the `bmad-build-auto` skill the `story@1` Template's
  `build` step invokes — this story never exercised that skill for real, only the plumbing
  around it; (e) watch `evaluate()`'s six lines on the resulting `GET /harnesses/claude/
  readiness` (or the Run's own trace/spend) to see which one, if any, fails first, since a
  first real run is exactly what this story's whole design expects to sometimes fail on.

**Operator decisions needed:** none blocking further work — the New workflow UI wiring
(deferred item 1) is the one open thread, and it is a scoped, well-understood follow-up
(same shape as this story's own resolved backend anchor conflict), not a structural
question.

**Follow-up review recommended:** false. Self-reviewed against the brief's four ACs (all
pass — the `sync_pins` AC in particular reuses the exact `"2.1.258 → 2.1.260"` wording), the
spine's AD-8/AD-9/AD-10/AD-16/AD-18, and the deferred item is scoped and named rather than
silently dropped.
