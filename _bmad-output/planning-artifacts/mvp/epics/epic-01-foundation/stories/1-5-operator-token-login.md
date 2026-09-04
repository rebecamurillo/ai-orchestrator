---
title: 'Operator token login'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: 'a491acd1553736463133270df7b07e6439260f69'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-5-operator-token-login.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** web-client serves every route, and the proxy attaches the instance bearer, to anyone
who can reach the port. The one credential the instance has (AD-4) is not yet asked for, so nothing
stands between the internet and the Operator's runs.

**Approach:** A `/login` screen whose Action compares the submitted token with `ORCHESTRATOR_TOKEN`
in constant time and, on a match, sets the signed HttpOnly cookie `orch_session` for 30 days.
`src/middleware.ts` verifies that cookie on every request: a page load without one is redirected to
`/login`, a call to the `/api/*` proxy is refused 401 `application/problem+json` before backend-api
is contacted. Signing and verification live in one pure module so the Playwright harness mints its
session with the same code the server checks.

## Boundaries & Constraints

**Always:**
- One credential (AD-4/AD-5). `ORCHESTRATOR_TOKEN` is read only in `src/actions/login.ts` and
  `src/api/server.ts`, both from `astro:env/server`. It never reaches the browser: not in HTML, not
  in a cookie value, not in a header, not in `dist/client`. The cookie value is
  `<issued-at>.<hmac-sha256(issued-at, ORCHESTRATOR_SESSION_SECRET)>` and carries no token.
- Cookie attributes are exactly `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=2592000`, and
  `Secure` only when the request arrived over https.
- An invalid, tampered, malformed or over-age cookie is treated as absent, never as an error.
- Guard split by path prefix: `/api/*` answers 401 problem+json and never forwards; every other
  path redirects 302 to `/login`. `/login` itself is always reachable.
- AD-1 holds: only `src/api/server.ts` and `src/api/client.ts` call `fetch`; no eslint exception,
  no widened contract.
- AD-3: `src/api/schema.d.ts` is generated; `make openapi` stays idempotent.
- Visual system (UX-DR1/DR6): tokens only, radius 0, no shadow, no inline style, no colour literal,
  no media query. The rejection line is `--color-signal-failed`; nothing else on the screen is red.
- Voice (NFR-8): `token rejected`, and a hint that states the mechanism. No welcome, no apology.
- Tests first (AD-18): every new test module lands red before the module it covers exists.
- Anchors are untouched: `SPEC.md`, `stories.yaml`, both `AGENTS.md`, `GUIDELINES.md`, every file
  under `backend-api/`, and the three existing Playwright specs. `backend-api/tests/unit/test_makefile.py`
  comes out byte-identical. No file is moved, renamed or wholesale replaced.
- No new environment variable: `ORCHESTRATOR_SESSION_SECRET` is already in `.env.example`, already
  allowlisted in `scripts/check_env_contract.py`, and already declared in `astro.config.mjs`.
- No new runtime dependency. No `.env` committed, no real secret in any fixture, log or message.

**Ask First:**
- Any change to the three frozen e2e specs, to a gate's strictness, or to a Makefile target.
- Any new dependency, top-level directory, or environment variable.

**Never:**
- No attempt counter, no `n attempts left`, no 15-minute lockout (Epic 8). No logout.
- No session table, no second user, no role. No cookie read by backend-api.
- No island, no `client:*` directive: the login screen is a form that works without JavaScript.
- No token, and no session secret, in a test fixture other than the declared placeholders.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Page, no cookie | `GET /`, `/runs`, `/projects`, `/templates`, `/workflows/new` | 302 to `/login` | N/A |
| Login page | `GET /login`, no cookie | 200, panel + hint line | N/A |
| Proxy, no cookie | `GET /api/ping` | 401 `application/problem+json` `{title:"unauthorized"}`; `next()` never called, upstream never fetched | refused before backend-api |
| Proxy, valid cookie | `GET /api/ping` | forwarded with the bearer; `{"pong": true}` | N/A |
| Wrong token | `POST /login?_action=login`, `token=wrong` | 200 at `/login`, `login-rejected` reads `token rejected`, input empty, no `Set-Cookie` | ActionError, rendered in place |
| Empty token | same, `token=` | identical to wrong token | one message; no distinct "missing" case |
| Right token | same, `token=<ORCHESTRATOR_TOKEN>` | `Set-Cookie: orch_session=…; Max-Age=2592000; Path=/; HttpOnly; SameSite=Lax`, 302 to `/` | N/A |
| Tampered cookie | signature byte flipped | treated as absent → 302 / 401 | N/A |
| Expired cookie | issued-at older than 30 days, signature valid | treated as absent | N/A |
| Malformed cookie | no `.`, empty, non-numeric issued-at, future issued-at | treated as absent | never throws |

</frozen-after-approval>

## Code Map

Read-only / must not change:
- `AGENTS.md`, `web-client/AGENTS.md`, `SPEC.md`, `stories.yaml`, `GUIDELINES.md` — anchors.
- Everything under `backend-api/`, `contracts/openapi.json`, `web-client/src/api/schema.d.ts`,
  `Makefile`, `.env.example`, `astro.config.mjs`, `eslint.config.js` — this story adds no setting,
  no route on the backend, and no gate.
- `web-client/tests/e2e/smoke.spec.ts`, `shell.spec.ts`, `no-credential.spec.ts` — **frozen.** All
  three drive `/`, the four other routes and `/api/*` with no session and expect 200. None of them
  names a later story as replacing what it asserts, so the amended hard rule 1 exception (commit
  `055e228`) does not reach them. They are kept green from **outside**: `playwright.config.ts` gains
  a `use.storageState` carrying a valid `orch_session`, which Playwright applies to the `page` **and**
  the `request` fixtures. Verified during planning against playwright 1.62.1 — an inline
  `storageState` object in `use` reached both fixtures and both sent the cookie.

Existing, edited in place:
- `web-client/playwright.config.ts` — add `use.storageState`, minted by the new `tests/e2e/session.ts`.
  This is what makes an authenticated session the default for every spec.
- `web-client/src/pages/index.astro:14` — the Board `EmptyState` gains the linked line
  `register a project to start` → `/projects`. The three existing lines stay.
- `web-client/src/components/EmptyState.astro:7` — additive optional `action?: {label, href}` prop.
  The existing unit test passes no `action` and keeps passing.
- `web-client/src/components/Button.astro:11` — additive optional `type?: 'button' | 'submit'`,
  default `'button'`. Needed because a `type="button"` inside a form does not submit; the existing
  test at `components.test.ts` asserts the default and keeps passing.
- `web-client/src/layouts/Shell.astro:4` — one comment line: it is no longer the *only* module that
  imports the stylesheets, because `/login` renders outside the shell.

New:
- `web-client/src/lib/session.ts` — pure, no `astro:env`: `SESSION_COOKIE`, `SESSION_MAX_AGE_SECONDS`,
  `sign(issuedAt, secret)`, `verify(value, secret, now)`, `tokenMatches(submitted, expected)`.
  Purity is load-bearing twice: it is unit-testable with a fixed secret, and `playwright.config.ts`
  can import it, so the harness cookie is minted by the code the server verifies.
- `web-client/src/actions/login.ts`, `web-client/src/actions/index.ts` — the Action and the `server`
  export Astro discovers (`src/actions/index.ts` is one of the filenames it searches).
- `web-client/src/middleware.ts`, `web-client/src/env.d.ts` (`App.Locals.authenticated`).
- `web-client/src/pages/login.astro` — its own document; imports `tokens.css` + `base.css`.
- `web-client/tests/unit/session.test.ts`, `web-client/tests/unit/middleware.test.ts`.
- `web-client/tests/e2e/session.ts`, `web-client/tests/e2e/login.spec.ts` (the latter opts out with
  `test.use({ storageState: { cookies: [], origins: [] } })`).

Reuse pointers:
- `web-client/tests/e2e/config.ts:14` — `PROBE_SESSION_SECRET`, already piped to the preview server
  by `playwright.config.ts:60`. Story 1.3 provisioned it for this story; no config value is invented.
- `web-client/tests/stubs/astro-env-server.ts:10` — `ORCHESTRATOR_SESSION_SECRET` placeholder,
  already present for the unit run.
- `web-client/tests/unit/lint.test.ts:61` — already lints all of `src/`, so new modules are covered.
- `web-client/src/components/EmptyState.astro`, `Button.astro` — the 1.4 components the screen uses.

Verified during planning (do not re-verify):
- Astro 7.2.10 form Actions do **not** redirect: `actions.login.toString()` is `?_action=login`, so
  the form posts to `/login?_action=login`; `getCallerInfo` reads `calledFrom: 'form'` and the page
  re-renders in place. `Astro.getActionResult(actions.login)` then carries the result. The pathname
  stays `/login`, so the middleware exemption covers the POST.
- Cookies set inside the Action survive `Astro.redirect('/')`: `handleMiddleware` calls
  `attachCookiesToResponse(response, state.cookies)` after the chain returns.
- User middleware wraps the Action handler (`handleMiddleware(state, actionsAndPages)`), so the
  guard runs first and a refused `/api/*` request never reaches the proxy route.
- `@astrojs/node` standalone serves `dist/client` before the SSR handler, so `/_astro/*.css` is not
  guarded and the login screen is styled while logged out.
- Astro's origin check 403s a form POST with no `Origin` header, so login e2e must submit through a
  real browser page, not `request.post`.
- `astro:middleware` and `astro:actions` both resolve under the existing Vitest config.
- `--color-*`, `--type-*` and `--font-*` are closed sets in `tokens.test.ts`; the 400px panel width
  is a literal, adds no token, and `stylesheets.test.ts` forbids only colour literals.

## Tasks & Acceptance

**Execution:** (tests first — each test module lands red before the modules it names exist)

- [x] `web-client/tests/unit/session.test.ts` — sign/verify round trip, tamper, expiry boundary,
      malformed input, and that `tokenMatches` is length-independent — the cookie is the whole guard.
- [x] `web-client/src/lib/session.ts` — implement it, pure, `node:crypto` only.
- [x] `web-client/tests/unit/middleware.test.ts` — the matrix above against a fake context and a
      `next` spy plus a stubbed global `fetch`, proving the refused proxy call reaches neither.
- [x] `web-client/src/middleware.ts` + `web-client/src/env.d.ts` — the guard and `locals.authenticated`.
- [x] `web-client/src/actions/login.ts` + `index.ts` — compare, set the cookie, or throw ActionError.
- [x] `web-client/src/pages/login.astro` — UX-DR6 panel with test-ids `login-token`, `login-submit`,
      `login-hint`, `login-rejected`; redirects to `/` on a successful result.
- [x] `web-client/src/components/Button.astro` — optional `type`, so the panel's *Enter* submits.
- [x] `web-client/src/components/EmptyState.astro` + `src/pages/index.astro` — the linked
      `register a project to start` line on the Board readout.
- [x] `web-client/tests/e2e/session.ts` + `playwright.config.ts` — mint the authenticated
      `storageState` and make it the default, keeping the three frozen specs green.
- [x] `web-client/tests/e2e/login.spec.ts` — the six acceptance criteria, session opted out.
- [x] `web-client/src/layouts/Shell.astro` — correct the stylesheet-ownership comment.

**Acceptance Criteria:**
- Given a session is required, when `make lint`, `make test`, `make e2e-ui` and `make e2e-api` run,
  then all four exit 0 and `make openapi` twice leaves `git status --porcelain` empty.
- Given the three specs 1.3 and 1.4 committed, when the guard lands, then they pass unmodified —
  `git diff` over those three paths is empty.
- Given a successful login, when the response is inspected, then it carries `Set-Cookie: orch_session`
  with `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=2592000`, and redirects to `/`, which reads
  `NOTHING REGISTERED`.
- Given any served byte — `dist/**`, the login HTML, every response header — when searched for the
  token, then it is absent.

## Spec Change Log

## Design Notes

**The rejected login renders 200, not Astro's 401.** `ActionError({code: 'UNAUTHORIZED'})` makes
Astro set the re-render's status to 401. That was found by the e2e gate, and the code was changed
rather than the matrix row: the response is a whole HTML screen, and this product answers errors as
`application/problem+json`. Inside web-client each status now means one thing — 302 is "go and log
in", 401 is "the proxy refused an API call", and 200 is "this page rendered", which is true even
when the attempt it reports failed. `src/pages/login.astro` sets it explicitly, with the reason.

The cookie is a value, not a store: `<issued-at ms>.<hmac>`, verified by recomputing the HMAC over
the issued-at and comparing digests in constant time, then checking the age. Nothing is persisted,
so there is no session table to migrate and no state to lose on restart.

`tokenMatches` hashes both sides before `timingSafeEqual`, which the brief's "equal-length buffers"
requires anyway — digesting supplies the equal length by construction and removes the length
side-channel that a raw comparison would leave:

```ts
const digest = (value: string) => createHash('sha256').update(value, 'utf8').digest();
export const tokenMatches = (submitted: string, expected: string): boolean =>
  expected.length > 0 && timingSafeEqual(digest(submitted), digest(expected));
```

## Verification

**Commands:**
- `make lint` — exits 0.
- `make test` — exits 0; the two new Vitest modules run.
- `make openapi`, twice — `git status --porcelain` empty afterwards.
- `make e2e-ui` — exits 0, including the three unmodified specs from 1.3 and 1.4.
- `make e2e-api` — exits 0 against the running stack (README "Running it").
- `git diff --stat backend-api web-client/tests/e2e/smoke.spec.ts web-client/tests/e2e/shell.spec.ts web-client/tests/e2e/no-credential.spec.ts` — empty.

## Suggested Review Order

**The guard**

- The whole session in one pure module: a signed timestamp, never the credential.
  [`session.ts:82`](../../../../../../web-client/src/lib/session.ts#L82)
- Where the credential is compared, over digests so no length is leaked.
  [`session.ts:108`](../../../../../../web-client/src/lib/session.ts#L108)
- One spelling per session, and a blank signing key fails closed rather than open.
  [`session.ts:30`](../../../../../../web-client/src/lib/session.ts#L30)
- The page/proxy split: a person is redirected, a script is refused.
  [`middleware.ts:47`](../../../../../../web-client/src/middleware.ts#L47)
- The refusal, in the shape the rest of the API answers errors in.
  [`middleware.ts:32`](../../../../../../web-client/src/middleware.ts#L32)
- Every answer was chosen by reading the cookie, so caches must key on it.
  [`middleware.ts:63`](../../../../../../web-client/src/middleware.ts#L63)

**Getting a session**

- The one place `ORCHESTRATOR_TOKEN` is compared; one answer for every failure.
  [`login.ts:23`](../../../../../../web-client/src/actions/login.ts#L23)
- Attributes come from the unit-tested module; only `Secure` is decided here.
  [`login.ts:27`](../../../../../../web-client/src/actions/login.ts#L27)
- The form posts back to the page, so a rejection re-renders with no redirect.
  [`login.astro:23`](../../../../../../web-client/src/pages/login.astro#L23)
- Why the rejected screen answers 200 rather than Astro's 401.
  [`login.astro:33`](../../../../../../web-client/src/pages/login.astro#L33)
- The rejection line: the only signal colour this screen can ever paint.
  [`login.astro:66`](../../../../../../web-client/src/pages/login.astro#L66)

**Keeping 1.3's and 1.4's frozen specs green**

- An authenticated session becomes the harness default, from outside the specs.
  [`playwright.config.ts:54`](../../../../../../web-client/playwright.config.ts#L54)
- The cookie is minted by the module the server verifies with, not a copy.
  [`session.ts:38`](../../../../../../web-client/tests/e2e/session.ts#L38)
- What a spec opts into when the guard itself is the subject.
  [`session.ts:59`](../../../../../../web-client/tests/e2e/session.ts#L59)

**The Board readout**

- The readout names the one surface that changes what it says.
  [`index.astro:22`](../../../../../../web-client/src/pages/index.astro#L22)
- Additive optional prop; the line comes after the facts, never instead.
  [`EmptyState.astro:27`](../../../../../../web-client/src/components/EmptyState.astro#L27)

**Tests and supporting changes**

- The cookie as a value: tamper, expiry boundary, malformed input, misconfiguration.
  [`session.test.ts:56`](../../../../../../web-client/tests/unit/session.test.ts#L56)
- The matrix, with the refused proxy call run into the real route.
  [`middleware.test.ts:100`](../../../../../../web-client/tests/unit/middleware.test.ts#L100)
- The six acceptance criteria, session opted out.
  [`login.spec.ts:24`](../../../../../../web-client/tests/e2e/login.spec.ts#L24)
- The two props added to 1.4's components, which its frozen suite predates.
  [`component-props.test.ts:33`](../../../../../../web-client/tests/unit/component-props.test.ts#L33)
