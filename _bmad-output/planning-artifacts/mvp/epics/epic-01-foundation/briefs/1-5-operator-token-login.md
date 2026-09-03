---
story: "1-5"
epic: 1
title: Operator token login
requirements: [FR-1 (MUST part), NFR-3, AR-5, UX-DR6]
binds: [AD-1, AD-4]
---

# Story 1.5 — Operator token login

As the Operator,
I want to enter the access token once and stay logged in for 30 days, with every page and every API call refused until I do,
So that the single credential of the instance is the only thing standing between the internet and my runs.

## Scope

**In:** `/login` page and Action, signed HttpOnly cookie, `src/middleware.ts` page guard, session guard on the `/api/*` proxy, the `/` page reading `NOTHING REGISTERED`, Playwright and Vitest coverage.
**Out:** attempt counter and lockout (`n attempts left`, 15-minute refusal) — Epic 8; logout.

## Binding rules (inlined)

- **One secret, two carriers (AD-4).** The login Action compares the submitted token with `ORCHESTRATOR_TOKEN` using a constant-time comparison. Success sets cookie `orch_session`: value = `<issued-at>.<hmac-sha256(issued-at, ORCHESTRATOR_SESSION_SECRET)>`, `HttpOnly`, `SameSite=Lax`, `Secure` when the request is https, `Path=/`, `Max-Age` 30 days. The middleware verifies the signature and age on every request; an invalid or expired cookie is treated as absent.
- **Guard (AD-1, AD-4).** `src/middleware.ts` redirects unauthenticated page loads to `/login` (302) except `/login` itself; the proxy `src/pages/api/[...path].ts` returns 401 `application/problem+json` `{title: "unauthorized"}` without a valid cookie and never forwards upstream. The token is read only in `src/actions/login.ts` and `src/api/server.ts` (`astro:env/server`).
- **Screen (UX-DR6).** Centred 400px panel on `bg`: brand, `ACCESS TOKEN` label + input (`type=password`, autocomplete off), *Enter* primary outline button, one hint line in `meta` type: `the token is ORCHESTRATOR_TOKEN in the instance .env · session cookie lasts 30 days`. On rejection the hint is replaced by the red line `token rejected` (the counter arrives with lockout in Epic 8). The form re-renders with no redirect on error; nothing else is on the screen.
- **Board placeholder.** `/` renders `NOTHING REGISTERED` with the line `register a project to start` linking to `/projects` (the `EmptyState` from 1.4; Epic 4 replaces the body).
- **Voice (NFR-8):** no "welcome", no "oops".

## Acceptance criteria

**Given** no cookie
**When** I open `/`, `/runs`, `/projects`, `/templates`, or `/workflows/new`
**Then** I am redirected to `/login` with status 302.

**Given** no cookie
**When** the browser calls `/api/ping`
**Then** the proxy answers 401 `application/problem+json` and the upstream is not called (unit test with a mocked upstream).

**Given** the login page
**When** I submit a wrong token
**Then** the page re-renders at `/login` with the line `token rejected` in the red signal colour, the input empty, and no cookie set.

**Given** the login page
**When** I submit the correct token
**Then** the response sets `orch_session` with `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=2592000`, and redirects to `/`, which renders `NOTHING REGISTERED`.

**Given** a cookie whose signature was altered or whose issued-at is older than 30 days
**When** any page is requested
**Then** the request is treated as unauthenticated.

**Given** a valid cookie
**When** the browser calls `/api/ping`
**Then** the proxy forwards with the bearer and returns the backend's `{"pong": true}`.

## Implementation notes

- `src/actions/login.ts` (Astro Action with `accept: 'form'`): validates, compares with `crypto.timingSafeEqual` on equal-length buffers, sets the cookie via `context.cookies.set`, returns `{ok: true}`; on failure returns an `ActionError` the page renders as the rejection line.
- `src/lib/session.ts`: `sign(issuedAt)`, `verify(cookieValue, now) -> boolean`, both pure and unit-tested (Vitest) with a fixed secret.
- `src/middleware.ts`: `defineMiddleware` reading `orch_session`, exposing `locals.authenticated`; page redirect vs proxy 401 decided by path prefix `/api/`.
- `src/pages/login.astro` per UX-DR6 with test-ids `login-token`, `login-submit`, `login-hint`, `login-rejected`.
- Playwright `tests/e2e/login.spec.ts`: the six criteria above with the backend stubbed by route handlers; `E2E_BACKEND=real` variant uses the compose stack.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

PRD FR-1, NFR-3. Spine AD-1, AD-4, conventions "Front-end auth", "Form errors". `EXPERIENCE-v1.md` §1 Login. `DESIGN.md` components (buttons, focus ring).
