---
story: "1-7"
epic: 1
title: CI pipeline and coverage gates
requirements: [NFR-9, AR-4, AR-22]
binds: [AD-3, AD-18]
---

# Story 1.7 — CI pipeline and coverage gates

As the Operator,
I want every push to run lint, unit, API end-to-end, and UI end-to-end gates in that order with contract drift and coverage thresholds enforced,
So that a story built unattended is judged by the same gates I would run, and nothing merges green by accident.

## Scope

**In:** a GitHub Actions workflow `[ASSUMPTION: the repository is hosted on GitHub, as the compare links imply]`, coverage configuration for backend and web-client, `diff-cover` for changed lines, the `make` targets CI calls, a `CONTRIBUTING.md` section in the root `README.md` naming the gates.
**Out:** deployment (the Mac mini pulls and runs `make up` by hand); branch protection settings.

## Binding rules (inlined)

- **Gate order (AD-18):** lint → unit → e2e-api → e2e-ui; a failed gate stops the pipeline.
- **Contract drift (AD-3):** CI runs `make openapi` then `git diff --exit-code contracts/ web-client/src/api/schema.d.ts`.
- **Coverage (AD-18):** backend `pytest --cov=orchestrator --cov-branch`; `fail_under = 100` for the packages `orchestrator.domain` and `orchestrator.application` (measured on what exists now: `domain/ports`, `domain/ids`, `domain/errors`, the app package skeleton); changed lines ≥ 90 % via `diff-cover --fail-under=90` against the base branch; web-client Vitest coverage with `thresholds` on `src/lib/**` and `src/stores/**` at 90 % lines.
- **Every `src` module has a test module:** a script `scripts/check_test_pairs.py` (backend) and `scripts/check-test-pairs.mjs` (web-client) fail lint when a module under `src/` has no counterpart under `tests/unit/` (allowlist: `__init__.py`, `main.py`, generated files, `.astro` pages).
- **The same commands locally and in CI:** every job calls a `make` target; no logic lives only in the workflow file.

## Acceptance criteria

**Given** a push to any branch
**When** the workflow runs
**Then** four jobs run in dependency order (`lint`, `unit`, `e2e-api` with the `postgres` service and the backend started from source, `e2e-ui` with the built web-client and a stubbed backend), and the epic's final commit is green.

**Given** a commit that adds a `src` module without a test module, or that lowers `domain/` branch coverage below 100 %, or that edits `schema.d.ts` by hand
**When** the workflow runs
**Then** it fails at `lint`, `unit`, or `lint` respectively with the offending file named (verified once by a deliberately failing commit on a throwaway branch, then reverted).

**Given** `make lint`, `make test`, `make e2e-api`, `make e2e-ui` run locally
**When** compared with the workflow logs
**Then** they run the same commands.

## Implementation notes

- `.github/workflows/ci.yml`: `concurrency` per ref; jobs with `needs:`; caches for uv and pnpm; `e2e-api` job runs `docker compose up -d postgres`, starts the backend with `uv run python -m orchestrator.main &`, waits on `/healthz`, runs `make e2e-api`; `e2e-ui` installs Playwright browsers and runs `make e2e-ui`.
- `backend-api/pyproject.toml` `[tool.coverage.report]` with per-package `fail_under` via two invocations or `coverage report --include`; add `diff-cover` as a dev dependency.
- `web-client/vitest.config.ts` coverage thresholds.
- Root `README.md`: "Gates" section listing the four targets and the coverage rule.

## Verification

```bash
make lint && make test   # locally
gh run watch             # the workflow on the pushed branch
```

## Sources for detail only

Spine AD-3, AD-18, Consistency Conventions "Code quality". PRD NFR-9. Root `AGENTS.md` "Commands (the gates)".
