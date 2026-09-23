# Deferred work

Findings surfaced by review that are real but belong to a later story. Append-only.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: Root `AGENTS.md` describes `make lint` as running eslint, prettier and tsc and `make test` as running vitest; none exist until story 1.3.
  evidence: The constitution states the end state in the present tense with no not-yet marker, while the Makefile it points at is honest about what is missing. Story 1.1's brief requires both `AGENTS.md` files to be copied verbatim from `architecture/deliverables/`, so reconciling them is a change to the architecture companion, not to this story's code.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: Root `AGENTS.md` hard rule 6 defines done as `make lint test e2e-api e2e-ui` passing, but `e2e-api` and `e2e-ui` exit non-zero by design until stories 1.2 and 1.3.
  evidence: No Epic 1 story can satisfy its own definition of done as written. The rule and the Makefile contradict each other on the epic's own timeline; both files are anchors this story may not edit.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: `make openapi` is documented in root `AGENTS.md` as failing on contract drift; the target currently reports `not available until story 1.3`.
  evidence: Behaviour described as present does not exist yet. Story 1.3 owns CAP-3 and the drift check.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: `backend-api/AGENTS.md` promises 100 % branch coverage on `domain/` and `application/` rules and ≥ 90 % on changed lines; nothing invokes coverage and `pytest-cov` is installed but unused.
  evidence: Epic 1 SPEC CAP-7 assigns coverage thresholds to story 1.7 ("coverage configuration enforces 100 % branch on `domain/` and `application/` rules and ≥ 90 % on changed lines"). Adding thresholds here would pre-empt that story.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: Root `AGENTS.md` names `contracts/openapi.json`, `templates/*.yaml`, `scripts/harness/*.sh`, `docker-compose.yml` and the whole `web-client/` component, and tells the reader to open the component's own `AGENTS.md`; none exist yet.
  evidence: The brief's Out list assigns web-client to 1.3, Docker and compose to 1.6; templates and harness scripts belong to Epics 3 and 5. The constitution is written for the finished repository.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: `.env.example` states the Postgres password twice — as `POSTGRES_PASSWORD` and again inside `DATABASE_URL` — with nothing checking that the two agree.
  evidence: A real `.env` with a changed password leaves the application connecting with the old credential while compose provisions the new one. `.env.example` is copied verbatim from `architecture/deliverables/.env.example`; introducing `${VAR}` interpolation changes an architecture companion and affects how compose reads the file (story 1.6).

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: `/healthz` has no unhealthy branch and FastAPI serves `/docs` and `/redoc` unauthenticated.
  evidence: A degraded response needs a dependency to check — the database arrives in story 1.2, which also brings the bearer dependency that decides what stays public. Both are CAP-2.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: No `backend-api/tests/e2e/` directory, and `.gitignore` has no Playwright output rules, although `backend-api/AGENTS.md` documents `pytest tests/e2e`.
  evidence: `make e2e-api` lands in story 1.2 and `make e2e-ui` in story 1.3; each brings its own harness and the artefacts that need ignoring.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-1-repository-constitution-and-backend-api-skeleton-with-layering-gates.md`
  summary: The flake8-bandit (`S`) rule family is not selected, so security rules including the `0.0.0.0` bind and every `subprocess.run` call go unchecked.
  evidence: Enabling `S` requires a per-file ignore for `S101` (assert) across `tests/`, which the story's standing rules forbid adding without approval. Story 1.7 owns the CI gate configuration and is the right place to decide it.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-3-generated-contract-and-web-client-skeleton.md`
  summary: The proxy answers an unreachable backend-api with Astro's default 500 rather than an RFC 9457 problem document.
  evidence: `src/api/server.ts::forward` lets a `fetch` rejection propagate out of `src/pages/api/[...path].ts`. Every other error the browser sees is `application/problem+json` (Consistency Conventions), and FR-24's failed-fetch readout parses `detail`. No story yet owns the proxy's own error shape; 1.5 touches the same route for the session guard.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-3-generated-contract-and-web-client-skeleton.md`
  summary: The proxy flattens repeated upstream response headers, so several `Set-Cookie` headers would arrive as one comma-joined value.
  evidence: `src/pages/api/[...path].ts` copies headers with `Headers.forEach` + `set`, which cannot represent a repeated header. Inert today — AD-1 states backend-api sets no cookies and sends no CORS headers — and it becomes real only if a later story gives backend-api a repeated response header.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-6-container-images-and-the-compose-stack.md`
  summary: No gate builds the two container images; `backend-api/tests/unit/test_dockerfiles.py` asserts their text, and only a human running `make up` proves they build and run.
  evidence: Building takes minutes and network, so `make test` cannot do it. Story 1.6's brief assigns the image build to CI in 1.7 ("CI builds the images in 1.7"); until that lands, a Dockerfile change that still satisfies every text assertion can break `make up` with no gate failing.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-7-ci-pipeline-and-coverage-gates.md`
  summary: CI still does not build the two container images; 1.7 landed the four gate jobs its brief names and no image-build job.
  evidence: The 1.6 deferral above expects 1.7 to build them, but 1.7's brief fixes the pipeline at four jobs — `lint`, `unit`, `e2e-api` "with the postgres service and the backend started from source", `e2e-ui` "with the built web-client and a stubbed backend" — and lists no image build in its In scope. `backend-api/tests/unit/test_ci_workflow.py::test_the_four_gates_are_the_four_jobs` now pins that shape, so adding the build is a deliberate change to both the workflow and that test.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/stories/1-7-ci-pipeline-and-coverage-gates.md`
  summary: `web-client/src/api/server.ts` — the module that holds the bearer — has no unit test that imports it; it satisfies the new pairing rule only by being named as a file path.
  evidence: `web-client/tests/unit/lint.test.ts:56` names `src/api/server.ts` as a virtual file path for an eslint run, which asserts the AD-1 exemption rather than the module's behaviour. `pnpm test --coverage` measures it at 95 % lines because `client.test.ts` and the proxy test reach it indirectly; nothing asserts `forward` attaches the bearer, and `src/api/**` is outside the 90 % threshold globs the brief names.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/stories/4-17-durability-proof-restart-and-orphan-test.md`
  summary: `attempt.pgid` is never written, so `signal_effects._cancel` always finds `None` and `cancel` kills no process group — Epic 5's `agent` executor must land the `mark_started` write with it.
  evidence: AD-8 gives that write to the `agent` executor and the field list scopes `pgid` to `agent` rows, so no Epic 4 kind could write it. Costless in Epic 4 (nothing here leaves a process running at a stop) and therefore invisible: the signals endpoint, the writers and `ProcessRunner.kill_group` are each individually correct and tested, and the gap is only in what connects them. `cancel` will appear to work — it transitions the Run and removes the worktree — while leaving the process running.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/stories/4-7-process-runner-workspace-and-basic-kinds.md`
  summary: No local gate runs the backend unit suite on Linux, so a syscall whose behaviour differs between Darwin and Linux can be green locally and broken in production.
  evidence: `make lint`, `make test`, `make e2e-ui` and `make durability` all run on the operator's host; only `make e2e` enters a Linux image, and it exercises the app rather than the unit suite. This shipped a real defect — `_group_alive` read an unreaped zombie as dead on Darwin and alive on Linux, so `kill_group` burned its full ten-second grace on every kill in a container (measured 20.16s → 0.10s after commit `bb69235`). Caught only by CI's `unit` job. Closing this means either a Linux unit run in the local gate set or an explicit statement that CI is the only Linux evidence — a change to the gate set, and therefore a spine decision (AD-18 fixes the five CI jobs).

The remaining ~40 Epic 4 deferrals live in the seventeen story specs' `deferred` frontmatter under
`_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/stories/`, summarised in
`epic-4-handoff.md` §4. Only the two cross-epic ones are repeated here.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-06-human-gates/stories/6-8-uj3-proven-end-to-end.md`
  summary: `E2E_BACKEND=real make e2e-ui` is not a whole-suite gate — 43 of 159 specs read stub-backend fixtures server-side and fail against a real stack, so only the UJ-3 journey runs that way.
  evidence: Those specs mock `GET /runs/{id}/detail` with `page.route()`, which cannot intercept an SSR fetch. Closing it means adding `test.skip(USE_REAL_BACKEND, …)` to ten spec files, every one of them an anchor, so it needs an operator ruling rather than a story's own judgement. Until then `make e2e-ui` proves rendering against stubs and exactly one spec proves it against the product.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-06-human-gates/stories/6-5-skip-epic.md`
  summary: `skip_epic` has no compose-stack proof; it is covered only at the unit level over fakes.
  evidence: The e2e must save `templates/epic.yaml` under a name of its own, because `test_templates.py` asserts `pinned_by == 0` for `epic@1` and a Run pins every version it uses. That rename means a fixture Run can never satisfy `_has_epic_frame`'s literal `template_name == "epic"` branch, and no initiative-shaped fixture exists to exercise the frame-based branch. Building one is fixture engineering no story owned. The same gap leaves *Reject* at a spec checkpoint, the `protected_path` Accept and its hit-list 409, the `re-baseline failed after skip` park, and the whole terminal path proven only over fakes.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-06-human-gates/stories/6-8-uj3-proven-end-to-end.md`
  summary: `tests/e2e/test_queue.py`'s cleanup can still leak a global Run slot, which turns one timeout into a cascade that starves the rest of the suite.
  evidence: Its `finally` does `cancel(first)` → `wait_for(second)` → `cancel(second)`, so a timeout in the middle skips the second cancel and leaves a Run occupying one of `MAX_ACTIVE_RUNS=2`. Commit `aaa45d6` removed the contamination *source* — `make e2e` now tears its stack down before bringing it up, so a killed run no longer poisons the next — but the latent leak remains. It is an anchor file, so wrapping that `wait_for` needs an operator ruling.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-05-dev-loop/stories/5-11-claude-readiness-passes-end-to-end.md`
  summary: RESOLVED 2026-09-09. The harness-readiness Run could not reach its agent row; it now can, and the two code gaps behind it are closed.
  evidence: The Operator ruled that readiness proves the harness, not the repository, so `harness_readiness_seed` seeds no `quality_gate_command` (`74ff6bb`) and the fifth evaluation line reads `no quality gate to run: skipped · no quality_gate_command` — `ok`, but deliberately not named `verify exit 0`, since no gate ran. `epic@1`'s `baseline` keeps `on_fail: fail`, pinned by a new test. The model gap that this uncovered is closed too: `READINESS_MODELS` binds a per-harness model (`e6dcadb`), refusing at start-up if the mapping does not name every harness and with a 409 at dispatch if one is unbound. What remains is not code: the Run has never been observed against a live harness, and `enabled` still requires Langfuse reachable, `LITELLM_SPEND_KEY` reading `/spend/logs/v2`, the agent finishing the fixture story, and `git.push` to the fixture origin — all of which belong to the operator session that closes story 5-11.
- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-07-harnesses/stories/7-4-opencode-readiness-passes-end-to-end-with-host-model-serving.md`
  summary: The host Langfuse is in v4 `events_only` mode, so the `trace observed` readiness line cannot pass for any harness and none can reach `enabled`. It is a host setting, not code.
  evidence: `GET /api/public/observations` and `GET /api/public/traces` both answer `404` against the host instance (checked by story 7-4 during its precondition pass, re-checked independently the same day; `litellm:4000` answers `200`, so the gateway is not the problem). Every path `Tracer.attempt_observed` can take then returns `False` — 5.2's parented query, 7.2's `session_level.py` fallback, and 7.3's `user_level.py` rule alike — so the third evaluation line fails and `harness_readiness_evaluate` never enables the harness. That blocks stories 5-11, 7-2 and 7-4 together, and with them the orchestrator running any epic at all, since `preflight/checks.py::harness_line` refuses a Run naming a harness that is not enabled. Closing it means taking that Langfuse out of `events_only`; if that is not possible, the honest outcome is three recorded `trace observed · not ok` results and the PRD §6.1 fallback.

- source_spec: `_bmad-output/planning-artifacts/mvp/epics/epic-07-harnesses/stories/7-5-runs-history.md`
  summary: `HistoryRow.log_tail_url` names a resource nothing serves, and a history row's `trace_url` resolves per Run rather than per attempt.
  evidence: No route returns an attempt's log tail; it is embedded in `GET /runs/{id}/detail` as `log_tail: list[str]`, so 7.5's field resolves to that detail path with the gap documented at the field — its brief's Scope was "Out: nothing else", so adding a route was not open to it. Separately, `domain/entities/attempt.py` stores no trace id; only `Run.trace_id` exists, so `trace_url` is the Run's and is stated as such rather than derived into something unrecorded. Epic 8 is the read-model epic and is where both should be decided.

- source_spec: `_bmad-output/implementation-artifacts/spec-dynamic-template-picker.md`
  summary: Two runtime rules outside the New Workflow form still branch on a hardcoded template name — `src/lib/run/detail.ts:235` (`run.template !== 'initiative'`) and `src/lib/projects/runs.ts:46` (`run.template.startsWith('repo-init@')`).
  evidence: Found by the verification-gap review of the ROOT_TEMPLATES change, 2026-09-22. Both predate that change and belong to other features (a Run's progress wording; a Repository's last repo-init Run), so neither was touched. They mean "no template name is hardcoded in web-client" is not yet true of the whole component, and a template renamed or replaced would silently change both behaviours.

- source_spec: `_bmad-output/implementation-artifacts/spec-dynamic-template-picker.md`
  summary: `plan.py::root_scope` never applies a Template input's declared `default:` — it substitutes only what the Run was started with, so a Run created through the API gets `""` where the Template declared a value.
  evidence: Traced during planning, 2026-09-22. `RunInputs.values` carries the submitted inputs and nothing reads `InputDecl.default`; `RunInputs.harness` defaults from `dto.DEFAULT_HARNESS`, not from the Template's own `default: claude`. The New Workflow form now prefills declared defaults, which closes it for the UI path only.

- source_spec: `_bmad-output/implementation-artifacts/spec-dynamic-template-picker.md`
  summary: A Template input declared `type: enum` renders as a free-text field; its `values` are served by the API and discarded by the form.
  evidence: Found by the edge-case review, 2026-09-22. `InputDeclOut.values` is populated, and `deriveFields` ignores it. No shipped Template declares a bindable enum (`harness` is the only enum and the form owns it), so nothing is broken today — but an authored Template can declare one and the Operator can then submit a value the Template does not accept.

- source_spec: `_bmad-output/implementation-artifacts/spec-dynamic-template-picker.md`
  summary: A required Template input left blank does not stop *Start run*; `runBody` gates only on project, repository and base branch.
  evidence: Found by the blind and edge-case reviews, 2026-09-22. Pre-existing — the old hardcoded field table marked every input mandatory and nothing enforced it either. The catalog now carries `required` per input, so the data to enforce it exists for the first time.

- source_spec: `_bmad-output/implementation-artifacts/spec-claude-readiness-fast-auth-check.md`
  summary: No test exercises subscription-mode login check together with an actually-enabled, reachable Gateway probe — every test in `test_harness_claude_subscription_login_probe.py` disables `LITELLM_BASE_URL` so only the login check itself is isolated.
  evidence: Found by the Blind Hunter review, 2026-09-23. `host/README.md` documents subscription mode as still routing through the Gateway (forwarded OAuth token), so the two real production paths — login check, then a live gateway model-list call — are never exercised together in one test. Doing so needs a fake local HTTP server in the test, which is more than a trivial patch; the two checks are sequential and independent in the script, so the risk is low, but the combination is unverified.

- source_spec: `_bmad-output/implementation-artifacts/spec-claude-readiness-fast-auth-check.md`
  summary: `probe()`'s `[ "${CLAUDE_SUBSCRIPTION_AUTH:-false}" = "true" ]` is an exact-string comparison; a `.env` typo (`1`, `True`, `TRUE`) silently disables the new login check rather than erroring.
  evidence: Found by the Blind Hunter review, 2026-09-23. This is the first harness script to read a boolean env var directly in bash — `scripts/harness/_common.sh` centralizes `probe_gateway_models`/`probe_output` for reuse but has no shared boolean-parsing helper. Low probability (the variable is documented and defaults correctly), but worth a shared helper if a second such flag appears.
