---
story: "1-3"
epic: 1
title: Generated contract and web-client skeleton
requirements: [AR-3, AR-4, AR-22, AR-25]
binds: [AD-1, AD-3, AD-18, AD-20]
---

# Story 1.3 — Generated contract and web-client skeleton

As the Operator,
I want the API contract exported from the backend and the web-client scaffolded around generated types, a server-side proxy, and its own lint, unit, and end-to-end gates,
So that no TypeScript payload type is ever written by hand and the browser never holds a backend credential.

## Scope

**In:** `make openapi`, `contracts/openapi.json`, `web-client/` with Astro 7 SSR, React 19, `src/api/{server,client}.ts`, the proxy route, `src/api/schema.d.ts` generation with drift check, eslint restrictions, prettier, `tsc`, `astro check`, Vitest, Playwright, `web-client/AGENTS.md`.
**Out:** tokens and shell (1.4); login and middleware (1.5); any real page content.

## Binding rules (inlined)

- **One browser origin (AD-1).** The browser talks only to web-client. `src/api/server.ts` (server-only, reads `astro:env/server` `BACKEND_API_URL` and `ORCHESTRATOR_TOKEN`) and `src/api/client.ts` (browser, `openapi-fetch` with `baseUrl: '/api'`) are the only modules that call `fetch`. The proxy route `src/pages/api/[...path].ts` forwards `/api/*` to `${BACKEND_API_URL}/api/v1/*` adding `Authorization: Bearer`. Enforce with eslint `no-restricted-globals` (`fetch`) and `no-restricted-imports` (`src/api/server`) on `src/islands/**`, `src/stores/**`, `src/components/**`.
- **Contract owned by the backend (AD-3).** `make openapi` runs `uv run python -m orchestrator.tools.export_openapi > contracts/openapi.json` then `pnpm gen:api` (`openapi-typescript ../contracts/openapi.json -o src/api/schema.d.ts`). `pnpm gen:api --check` (regenerate to a temp file and diff) is part of `make lint`. `schema.d.ts` is committed and carries a `GENERATED` header.
- **Stack pins:** Node 24, pnpm 11.25.0, Astro 7.2.10, `@astrojs/node` 11.1.5, `@astrojs/react` 6.0.5, `@astrojs/check` 0.9.10, React 19.2.8, nanostores 1.5.2, `@nanostores/react` 1.1.0, openapi-typescript 7.13.0, openapi-fetch 0.17.0, Vitest 4.1.11, `@playwright/test` 1.62.1. Commit `pnpm-lock.yaml`.
- **Astro config:** `output: 'server'`, adapter `@astrojs/node({ mode: 'standalone' })`, `react()`, `env.schema` declaring `BACKEND_API_URL` and `ORCHESTRATOR_TOKEN` as `context: 'server', access: 'secret'`, `ORCHESTRATOR_SESSION_SECRET` likewise (used in 1.5).
- **Tests (AD-18):** Vitest for units (islands with React Testing Library), Playwright in `tests/e2e/` with `webServer: pnpm preview`; backend stubbed by route handlers unless `E2E_BACKEND=real`.
- **Constitution:** copy `deliverables/web-client/AGENTS.md` to `web-client/AGENTS.md`, fix only paths that differ in reality.

## Acceptance criteria

**Given** the backend from 1.2
**When** `make openapi` runs
**Then** `contracts/openapi.json` is written and `web-client/src/api/schema.d.ts` is regenerated from it; running it twice produces no diff.

**Given** a hand edit to `schema.d.ts` or a backend schema change without regeneration
**When** `make lint` runs
**Then** the drift check fails naming the file.

**Given** a file under `src/islands/` that calls `fetch` or imports `src/api/server`
**When** `pnpm lint` runs
**Then** eslint fails on that line (covered by a fixture test in `tests/unit/lint.test.ts` that runs eslint on a temp file).

**Given** a request to `/api/ping` on the Astro server
**When** the proxy handles it
**Then** it forwards to `${BACKEND_API_URL}/api/v1/ping` with the bearer, streams status, headers, and body back unchanged, and the token appears in no response header, HTML, or client bundle (unit test with a mocked upstream; a bundle grep test).

**Given** `make lint`, `make test`, `make e2e-ui`
**When** run from a fresh clone with Node 24 and pnpm
**Then** eslint, prettier check, `tsc --noEmit`, `astro check`, Vitest, and a Playwright smoke test on `/` (placeholder page) all pass.

## Implementation notes

- `backend-api/src/orchestrator/tools/export_openapi.py`: builds the app with dummy settings and prints `app.openapi()` with stable key ordering.
- `web-client/package.json` scripts: `dev`, `build`, `preview`, `gen:api`, `lint`, `test`, `e2e`; `pnpm gen:api --check` implemented as a small script in `scripts/gen-api.mjs`.
- `src/api/server.ts` exports `backend()` returning an `openapi-fetch` client bound to `BACKEND_API_URL` with the bearer, for Actions and pages; `src/api/client.ts` exports `api` bound to `/api`.
- `src/pages/api/[...path].ts`: `ALL` handler; drop hop-by-hop headers; pass `Content-Type`; no caching. (1.5 adds the session guard.)
- Placeholder `src/pages/index.astro` rendering the text `web-client up`; 1.4 replaces it.
- `playwright.config.ts`: `webServer: { command: 'pnpm preview', port: 4321 }`, `use.baseURL`; `tests/e2e/smoke.spec.ts`.
- Root `Makefile`: `lint` and `test` now include `pnpm lint` and `pnpm test`; `e2e-ui` = `pnpm build && pnpm e2e`.

## Verification

```bash
make openapi && make lint && make test && make e2e-ui
```

## Sources for detail only

Spine: AD-1, AD-3, AD-18, Stack, Structural Seed (web-client tree), Consistency Conventions (Front-end data, Naming). `deliverables/web-client/AGENTS.md`.
