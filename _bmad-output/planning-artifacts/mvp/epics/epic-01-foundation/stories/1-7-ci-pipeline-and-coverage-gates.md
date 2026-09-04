---
title: 'CI pipeline and coverage gates'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '0d7a59d44e6dd0d31fcbe0d3f65058289384f946'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-7-ci-pipeline-and-coverage-gates.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 1.1–1.6 landed six gates that only ever run when a human types them, and two
of the rules AD-18 calls checkable — "every `src` module has a test module" and "the rule packages
have 100 % branch coverage, changed lines ≥ 90 %" — are still prose. From Epic 2 on a coding agent
is judged by these gates alone, so a gate nobody runs on a push is a gate that does not exist.

**Approach:** One GitHub Actions workflow runs the four gates as four jobs in the fixed order
lint → unit → e2e-api → e2e-ui, each job calling the same `make` target the Operator types. Two
pairing scripts and a coverage configuration make the two unchecked AD-18 rules fail `make lint`
and `make test` locally, before CI ever sees them.

## Boundaries & Constraints

**Always:** every CI job's gate is a `make` target, so the workflow file holds setup and no gate
logic. Gate order is lint → unit → e2e-api → e2e-ui with `needs:`; a failed job stops the ones
after it. Coverage is raised by adding tests, never by lowering a threshold, excluding a source
file, or adding a `pragma: no cover`. Actions are pinned to a full commit SHA. The workflow names
no credential value; the gates run on the `.env.example` placeholders and need no real secret.

**Ask First:** anything that would change `backend-api/tests/unit/test_makefile.py` (frozen:
`PENDING_TARGETS` is empty, `DECLARED_TARGETS` and `LINT_SUBGATES` are anchors — the lint recipe
must keep exactly five `uv` invocations); any change to an existing test file; any threshold below
the brief's 100 % / 90 % / 90 %.

**Never:** push, open a PR, or trigger a remote workflow — CI behaviour is proven by asserting the
workflow file's structure and by running the same commands locally. No deployment job, no branch
protection, no release step, no new runtime setting (`.env.example` is unchanged).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| paired tree | every `src` module is imported by a `tests/unit/` module | both pair scripts exit 0 with a count | N/A |
| orphan module | a new `src/orchestrator/x.py` no test imports | `make lint` exits non-zero | the offending path is named on stderr |
| orphan module (web) | a new `src/lib/x.ts` no test imports | `pnpm lint` exits non-zero | the offending path is named on stderr |
| package re-export | a test does `from orchestrator.infrastructure.db import Base` | `base.py` counts as paired | N/A |
| rule coverage drop | a branch in `domain/` left untested | `make test` exits non-zero at the strict report | coverage names the file and line |
| changed lines | a commit whose changed lines are < 90 % covered | `make coverage` exits non-zero | diff-cover names the file and lines |
| hand-edited contract | `schema.d.ts` edited by hand | `make lint` exits non-zero (AD-3) | `gen:api --check` names the file |

</frozen-after-approval>

## Code Map

Read-only / must not change:

- `backend-api/tests/unit/test_makefile.py` — **frozen and it constrains this story.**
  `PENDING_TARGETS:25` is empty and stays empty; `DECLARED_TARGETS:29` is an anchor (a new target
  may be added to `.PHONY`, the tuple may not change); `test_the_lint_recipe_runs_inside_the_backend_package:86`
  asserts `len(_uv_invocations(make -n lint)) == len(LINT_SUBGATES) == 5`, so **no new `uv run`
  line may enter the `lint` recipe** — the backend pair check runs on the system interpreter.
- Every other file under `backend-api/tests/unit/`, `backend-api/tests/e2e/`, `web-client/tests/`
  — anchors. New behaviour lands in new test modules.
- `AGENTS.md` ×3, `SPEC.md`, `stories.yaml`, `GUIDELINES.md`, `.env.example` (no new setting).
- `README.md` § "Setting up the BMAD method on a new machine":130-165 — verbatim, untouched.

Existing, edited in place:

- `Makefile:14` `.PHONY` gains `coverage`; `:18` `lint` gains one non-uv line running the backend
  pair check; `:28` `test` gains `--cov` and the strict `coverage report --include … --fail-under=100`;
  a new `coverage` target runs `diff-cover`. `PYTHON ?= python3` joins `UV`/`PNPM` at `:5`.
- `backend-api/pyproject.toml:17` dev group gains `diff-cover` and `pyyaml`; a new
  `[tool.coverage.run]`/`[tool.coverage.report]` pair after `[tool.pytest.ini_options]:110`.
- `web-client/package.json:16` `lint` gains `node scripts/check-test-pairs.mjs`; devDependencies
  gain `@vitest/coverage-v8` at exactly the pinned `vitest` version (4.1.11).
- `web-client/vitest.config.ts:25` `test` gains `coverage` with per-glob `thresholds`.
- `.gitignore:36` Node section gains `coverage/` (`.coverage`, `coverage.xml` are already there:25-27).
- `README.md` — a new "## Contributing" section after "### The web-client half":129 naming the four
  gates in order, the coverage rule, the pairing rule, and CI.

Reuse pointers:

- `scripts/check_env_contract.py` — the shape a repo-root gate script takes: argparse, `main(argv)`,
  a message naming the offending variable, `raise SystemExit(main())`. Also the ruff target of
  `ruff check . ../scripts`, so the new script is linted by the same run.
- `web-client/scripts/gen-api.mjs:12` — the `--flag PATH` convention that lets a unit test drive a
  gate script against a scratch tree instead of the repository's own. Copy it.
- `backend-api/tests/unit/conftest.py:21` `REPO_ROOT`; `tests/unit/test_makefile.py:41` `_make`,
  `:71` `_uv_invocations` — imported, never re-implemented (`test_makefile_e2e_api.py` is the pattern).
- `web-client/tests/unit/components.test.ts` — the `astro/container` render pattern the Shell test
  reuses; `web-client/tests/stubs/astro-env-server.ts` + `vitest.config.ts:20` — the alias pattern
  for a virtual `astro:*` module, if `astro:actions` does not resolve on its own.

Verified during planning (do not re-verify):

- Coverage today: `orchestrator.domain` 100 % branch (24 stmts), whole package 97 % (417 stmts,
  9 missed) — the 100 % gate is already met and the ≥ 90 % changed-lines gate has ~7 points of
  headroom. `orchestrator.application` is `__init__.py` only and needs `source` in config to be
  measured at all (`--cov=orchestrator.application` warns "never imported" and reports nothing).
- Unpaired modules under the import rule, i.e. the tests this story must add:
  `api/routers/ping.py` (exercised through `create_app` by `test_bearer_auth.py`, never imported),
  `web-client/src/layouts/Shell.astro`, `src/actions/index.ts`, `src/actions/login.ts`.
  Everything else pairs once package `__init__` re-exports are followed one hop.
- `@vitest/coverage-v8@4.1.11` exists and must equal the pinned vitest; `diff-cover` 10.5.1
  (requires-python ≥ 3.10); PyYAML 6.0.3 is present transitively — declared explicitly because a
  test parses the workflow with it.
- Action tags → commit SHAs: `actions/checkout` v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`,
  `actions/setup-node` v7.0.0 `820762786026740c76f36085b0efc47a31fe5020`, `astral-sh/setup-uv`
  v10.0.1 `20cfd1bf945f4377ade1205e4dbc17946fc9a30d`, `actions/cache` v6.1.0
  `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`.
- `make up` and `make e2e-ui` both bind `127.0.0.1:4321`; the DoD run sequences them.

## Tasks & Acceptance

**Execution:** (tests first — each test module lands red before the artefact it names exists)

- [x] `backend-api/tests/unit/test_check_test_pairs.py` — the pair script on scratch trees: a paired
      tree exits 0; an orphan module exits non-zero naming its path; a package `__init__` re-export
      counts as an import; `__init__.py` and `main.py` are exempt; and the real backend tree passes.
- [x] `scripts/check_test_pairs.py` — AST import graph over `tests/unit/`, one hop through package
      `__init__` re-exports, `--src`/`--tests`/`--package` flags for the test above.
- [x] `backend-api/tests/unit/test_ping_route.py` — pairs `api/routers/ping.py`: the router declares
      one `GET /ping` and its handler returns `Pong(pong=True)`.
- [x] `web-client/tests/unit/check-test-pairs.test.ts` — the same three cases for the mjs script,
      driven against scratch trees, plus the real `web-client` tree.
- [x] `web-client/scripts/check-test-pairs.mjs` — the same rule over `src/**/*.{ts,tsx,astro}`,
      allowlisting `*.d.ts`, generated `schema.d.ts` and `src/pages/**/*.astro`.
- [x] `web-client/tests/unit/shell.test.ts` + `web-client/tests/unit/actions.test.ts` — pair the
      three unpaired web modules with real tests (Shell renders rail/surface/footer; the login
      Action rejects a wrong token with `token rejected` and mints the session cookie on a match).
- [x] `backend-api/tests/unit/test_coverage_gates.py` — the coverage contract: `[tool.coverage.run]`
      is branch-mode over `src/orchestrator` with no exclusion carving, `make test` runs the strict
      `--fail-under=100` report over exactly `domain` + `application`, `make coverage` runs
      `diff-cover --fail-under=90`, both dev dependencies are pinned, and `vitest.config.ts` sets
      90 % line thresholds for `src/lib/**` and `src/stores/**`.
- [x] `backend-api/pyproject.toml`, `Makefile`, `web-client/vitest.config.ts`,
      `web-client/package.json`, `.gitignore` — the configuration those tests describe, edited in
      place; `uv.lock` and `pnpm-lock.yaml` regenerated by the tools, never by hand.
- [x] `backend-api/tests/unit/test_ci_workflow.py` — the workflow contract: four jobs named for the
      four gates chained by `needs:` in order, each running its `make` target; `concurrency` per ref;
      every `uses:` pinned to a 40-hex SHA; no secret value and no `${{ secrets.* }}` inline in a
      `run:`; `fetch-depth: 0` wherever `make coverage` runs; and the README gate list matches the
      workflow's targets.
- [x] `.github/workflows/ci.yml` — the workflow.
- [x] `README.md` — the "Contributing" section; the BMAD section untouched.

**Acceptance Criteria:**

- Given the repository at this commit, when `make lint`, `make test`, `make coverage`, `make openapi`,
  `make e2e-api` and `make e2e-ui` run locally, then every one exits 0, `make openapi` twice leaves
  `git status --porcelain` empty, and `git diff --numstat` over every pre-existing test file is empty.
- Given a scratch `src` module that no test imports, when `make lint` runs, then it exits non-zero
  and prints that module's path; same for a hand-edited `web-client/src/api/schema.d.ts`; and given
  an uncovered branch in `domain/`, `make test` exits non-zero naming the file and line. Each is
  verified by making the change locally, running the gate, and reverting it.
- Given `.github/workflows/ci.yml`, when it is parsed, then the four jobs run lint → unit → e2e-api
  → e2e-ui in dependency order and every gate they run is a `make` target that exists in the
  `Makefile`.

## Design Notes

**Why the backend pair check does not run under `uv`.** `test_makefile.py:91` asserts the `lint`
recipe contains exactly `len(LINT_SUBGATES)` uv invocations. That file is frozen and its pending-gate
exception no longer applies, so a sixth `uv run` line is not available. The script therefore imports
nothing outside the standard library and runs as `$(PYTHON) scripts/check_test_pairs.py` with
`PYTHON ?= python3` — one more sub-gate, no relaxed assertion.

**What "has a test module" means.** A source module is paired when some module under `tests/unit/`
imports it. Imports are read with `ast`, and `from PKG import NAME` resolves both ways: to the
submodule `PKG.NAME` when one exists, and — when `PKG` is a package — to whatever `PKG/__init__.py`
itself imports. That second hop is not a loophole: `from orchestrator.infrastructure.db import Base`
really does execute `db/base.py`. Reachability through `main.py` is deliberately *not* followed,
because everything is reachable from the composition root and the rule would assert nothing.

**Where the 100 % lives.** On the command, not in `[tool.coverage.report]`: the same run also prints
the whole-package report (97 %), and a repository-wide `fail_under = 100` in config would either
fail that report or have to be silenced with `--cov-fail-under=0`. `make test` runs
`coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100`,
and `test_coverage_gates.py` asserts that line, so the threshold cannot be lowered silently either.

## Verification

**Commands:**

- `make lint` — expected: exit 0, including the two new pair checks.
- `make test` — expected: exit 0; the strict report prints `TOTAL … 100%` for the rule packages.
- `make coverage` — expected: exit 0; diff-cover reports the changed-line percentage ≥ 90.
- `make openapi && git status --porcelain` — expected: empty, twice.
- `make up && curl -fs 127.0.0.1:8000/healthz && make e2e-api && make down` then `make e2e-ui` —
  expected: exit 0 each (they cannot share port 4321).
- `git diff --numstat` over `backend-api/tests/unit/test_makefile.py` — expected: no output.
- `python3 -c "import yaml,sys;print(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs'].keys())"`
  — expected: `lint`, `unit`, `e2e-api`, `e2e-ui`.

**Manual checks:**

- CI cannot be executed here: nothing is pushed and no workflow is triggered. What is proven by
  local execution is that every command the workflow runs passes on this machine; what is proven
  only by assertion over the file is the job graph, the runner setup, and the caches.

## Suggested Review Order

**The pipeline**

- The whole design in one file: four jobs, AD-18's order, no gate logic of its own.
  [`ci.yml:35`](../../../../../../.github/workflows/ci.yml#L35)

- The AD-3 half `make lint` cannot see — the contract re-exported and any diff refused.
  [`ci.yml:62`](../../../../../../.github/workflows/ci.yml#L62)

- The base branch follows a pull request rather than always the default branch.
  [`ci.yml:102`](../../../../../../.github/workflows/ci.yml#L102)

**The gates the pipeline calls**

- One non-uv line: the frozen anchor pins how many `uv` invocations `lint` may hold.
  [`Makefile:29`](../../../../../../Makefile#L29)

- The 100 % lives on the command, over the two rule packages alone.
  [`Makefile:39`](../../../../../../Makefile#L39)

- Changed lines ≥ 90 %, reading the report `make test` wrote.
  [`Makefile:47`](../../../../../../Makefile#L47)

- Branch mode over the whole package, with nothing carved out of the measurement.
  [`pyproject.toml:125`](../../../../../../backend-api/pyproject.toml#L125)

- 90 % lines on the web-client rule modules; `src/stores/**` is listed before it exists.
  [`vitest.config.ts:35`](../../../../../../web-client/vitest.config.ts#L35)

**The test-pair rule**

- What "has a test module" means: imports, followed one package re-export at a time.
  [`check_test_pairs.py:96`](../../../../../../scripts/check_test_pairs.py#L96)

- The web half: an import specifier or the path a test names outright.
  [`check-test-pairs.mjs:84`](../../../../../../web-client/scripts/check-test-pairs.mjs#L84)

**Peripherals**

- The workflow read as a document, since nothing here can run it.
  [`test_ci_workflow.py:76`](../../../../../../backend-api/tests/unit/test_ci_workflow.py#L76)

- The thresholds asserted where they can be read, not only measured.
  [`test_coverage_gates.py:86`](../../../../../../backend-api/tests/unit/test_coverage_gates.py#L86)

- Scratch trees prove the pair gates fire, not just that they pass here.
  [`test_check_test_pairs.py:53`](../../../../../../backend-api/tests/unit/test_check_test_pairs.py#L53)

- The three modules the pairing rule left unpaired, now tested for real.
  [`actions.test.ts:56`](../../../../../../web-client/tests/unit/actions.test.ts#L56)

- The gates a contributor runs, and the two rules that are enforced rather than asked for.
  [`README.md:130`](../../../../../../README.md#L130)
