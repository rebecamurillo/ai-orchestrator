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
