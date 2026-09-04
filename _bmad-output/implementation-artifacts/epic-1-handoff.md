# Epic 1 handoff — what exists, and why it is shaped that way

Written 2026-09-04, after story 1.7. For whoever builds Epic 2 and after.

`epic-1-context.md` says what Epic 1 was *asked* to do. This says what it *did*, which
decisions are load-bearing, and which traps are still set. Read it once before your first
Epic 2 story; you do not need it again.

The commits are `c2aa9cd..HEAD` on `feat/mvp`. Nine are stories and fixes; three are
one-line amendments to the constitution, each made only with the operator's sign-off.

---

## 1. What you can rely on

**backend-api** (`backend-api/`, Python 3.14, uv). Four layers with `import-linter` holding
them apart: `tools → main → {api, infrastructure} → application → domain`. `domain/` and
`application/` import no framework and do no I/O — everything goes through a port. Ports live
in `domain/ports/`, their fakes in `tests/unit/fakes/`. Postgres through one SQLAlchemy 2
datasource, Alembic running at startup before the app binds, one baseline revision. Bearer
auth on `/api/v1` with `hmac.compare_digest`. RFC 9457 problem responses, the `{items,
next_cursor}` envelope, UUIDv7 ids, and the typed settings module are all in place — use them,
do not restate them.

**web-client** (`web-client/`, Astro 7 SSR + React 19, pnpm). The browser talks only to
web-client. `src/api/server.ts` holds the credential and is server-only; `src/api/client.ts`
is the browser's, bound to `/api`; `src/pages/api/[...path].ts` proxies to
`${BACKEND_API_URL}/api/v1/*` and attaches the bearer. eslint refuses `fetch` and any import
of `api/server` under `src/islands/**`, `src/stores/**`, `src/components/**`. Payload types
come only from `pnpm gen:api`. The instrument-dark tokens, the shell, and twelve components
exist; so does the signed-cookie login and the middleware guard.

**Infrastructure.** Two Dockerfiles, a three-service compose stack (all ports on
`127.0.0.1`, both app services non-root with `cap_drop: ALL` and `no-new-privileges`), three
harness scripts with install/configure/doctor, and a five-job CI pipeline.

**Gates.** `make lint test coverage e2e-api e2e-ui images openapi up down logs`. All of them
are landed and all of them pass. There is no longer any such thing as an unlanded gate.

---

## 2. Decisions that are load-bearing — do not undo these by accident

**The pending-gate registry is empty and must stay empty.** `test_makefile.py`'s
`PENDING_TARGETS` was how a story said "this gate isn't real yet". Every entry is gone. Hard
rule 6 says a landed gate is required from then on and no story may return one to that state.
If you find yourself wanting to add an entry, you want something else.

**`test_makefile.py` asserts the `lint` recipe holds exactly five `uv` invocations.** That is
why `scripts/check_test_pairs.py` runs on `python3` and is stdlib-only rather than under `uv`
like everything else. If you add a sub-gate to `make lint`, it cannot be a sixth `uv` call
without breaking a frozen anchor. This has already forced one design; expect it to force
yours.

**Coverage thresholds are commands, not config.** `--fail-under=100` sits on the `coverage
report` line in the Makefile, not in `[tool.coverage.report]`, because a repo-wide
`fail_under` would also fire on the informational whole-package report.
`test_coverage_gates.py` asserts the recipe, and separately asserts there is no `omit`, no
`exclude_also`, and no `pragma: no cover` anywhere. Raise a number by writing a test.

**Every source module needs a test module.** `make lint` fails with the path of any module
under `backend-api/src/` not imported by something under `tests/unit/`, or any module under
`web-client/src/` not named by one. Exemptions are narrow: `__init__.py`, the root `main.py`,
`*.d.ts`, and `src/pages/**/*.astro`. Write the test with the module, not after.

**`make up` and `make e2e-ui` both bind `127.0.0.1:4321`** and cannot run at once. Sequence
them. On a machine with an unrelated dev server on `[::1]:4321`, `localhost` resolves to the
wrong stack — the harness binds IPv4 explicitly for that reason. Keep it that way.

**`make openapi` needs no database.** It builds the app with dummy settings. Keep it that way;
CI depends on it.

---

## 3. The rules that will bite you

**Anchors are read-only** (hard rule 1): `SPEC.md`, `stories.yaml`, `epics.yaml`, any
`AGENTS.md`, and every existing test file. Add new test files; never modify or delete one.
Epic 1 hit this four times and it was never worked around silently — each time the operator
decided. Three narrow exceptions now exist because of that:

1. *The pending-gate registry.* The story landing a gate may retire that gate's entry, only if
   the same commit adds a test proving the gate now runs. Now moot — the registry is empty.
2. *A placeholder assertion.* Where a test names a later story as the thing that replaces what
   it asserts, exactly that story may revise that assertion, only if the same commit adds
   coverage that strictly exceeds it. This exists because 1.3 wrote a Playwright test asserting
   the literal text `web-client up` while its own docstring said 1.4 would replace the page —
   which made 1.4's acceptance criteria and `make e2e-ui` mutually unsatisfiable.
3. *A nondeterministic assertion.* Where an existing test asserts on a third-party tool's
   output and that output is not deterministic across runs or releases, the assertion may be
   narrowed to the part that is, only if the same commit adds a test covering deterministically
   what the narrowed assertion stops covering. This exists because `test_compose.py` asserted
   that `docker compose config` with an empty env file names a `POSTGRES_` variable. Story 1.1
   wrote it when postgres was the only service; 1.6 added two more, so ten variables are
   missing at once and compose names one of them in Go map iteration order — random per
   process. It failed roughly one CI run in four. `test_compose_fails_closed.py` replaced it
   by removing exactly one variable from the contract at a time, which admits exactly one
   error, and it covers all ten rather than the three the old line implied.

**Do not assert on which item a tool picks out of a set.** How many interpolation errors
compose prints is not stable even across patch releases — v5.4.0 printed all of them, v5.5.0
printed one, v5.5.1 printed all of them again — so "pin a version that behaves" was not a fix
available here. Construct the input so only one answer is possible instead.

**The lesson is written into hard rule 1: do not write the assertion that needs the second
exception.** A test covering a placeholder asserts that the route is served, not what it says.
If your story ships something another story will replace, assert its existence, not its copy.

**A third case was resolved by the operator directly, not by a new exception.** `make images`
and its CI job were added after 1.7 at the operator's request, which required editing
`test_ci_workflow.py`'s exact job tuple. That was an operator decision on a specific change,
not a standing rule — do not cite it as precedent.

**Never push and never open a PR** unless the operator says so in that session.

---

## 4. Known gaps, honestly

- **CI now runs; all five jobs are green on x86-64 Linux.** The one thing it caught that no
  local run could was the compose flake above: the runner's compose reports a single
  interpolation error where Docker Desktop's reports all of them, so a test that passed every
  time on a developer machine failed about one run in four on a runner. Expect more of that
  shape — a green local gate is evidence about arm64 macOS and Docker Desktop, not about the
  runner.
- **`web-client/src/api/server.ts` satisfies the pairing gate by being named as a *file path
  string* in `lint.test.ts`, not by a real import.** Its coverage is genuinely fine (95 %
  statements, 100 % branches, via `proxy.test.ts`'s dynamic import of the route), but the
  pairing signal there is weaker than it looks. If you touch that module, add a test that
  imports it.
- **The `secure: true` cookie branch has never run over real TLS** — the harness has no TLS.
- **Astro's `/_actions/*` RPC route is guarded like any other path.** Harmless now; a
  JS-driven login would need an exemption. Noted in `src/middleware.ts`.
- **`locals.authenticated` exists and is tested but nothing reads it yet.**
- **`--detail-max` and `DenseTable`'s row/column contract** have no consumer until Epic 4.
- Everything else deferred is in `deferred-work.md`, which is the list to read, not this one.

---

## 5. What Epic 2 specifically inherits

Epic 2 adds Projects and Repositories with the Clone check. Four things are already decided
for you:

- **`ORCHESTRATOR_SECRET_KEY` is already in `.env.example` and in the settings module** as the
  Fernet key for Project environment variables. Do not add a second one.
- **`GITHUB_TOKEN` is already read only in `infrastructure/settings.py`,** is absent from the
  web-client container's environment entirely, and appears in `scripts/harness/` only inside a
  comment saying it is never passed. `GIT_ASKPASS` per command is the only route to git; keep
  it that way (AD-5).
- **There is no `Git` port yet.** AD-14 and the Epic 2 SPEC both require one. It belongs in
  `domain/ports/`, with its fake in `tests/unit/fakes/`, and use cases must never import
  `subprocess`, `os` or `shutil` — `import-linter` will fail the task if they do.
- **The Projects surface has an empty-state page already** (`src/pages/projects/index.astro`,
  reading `NOTHING REGISTERED`). Replace its content; the shell, tokens, `StatusToken`,
  `EmptyState`, `RecordRow` and `DenseTable` are there to be used rather than re-created.

One tension worth knowing: the Board's empty state says `register a project to start` and
links to `/projects`. Epic 2 makes that link lead somewhere real. Nothing asserts the Board's
copy beyond its existence, deliberately — see §3.
