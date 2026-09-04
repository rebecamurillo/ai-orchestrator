/**
 * The guard (AD-4). Every request to web-client passes through here before a page renders
 * or the proxy forwards, and the session cookie is the only thing that opens either.
 *
 * Two answers, chosen by path, because the two callers are different. A page load is a
 * person with a browser: send them to the screen that can fix the problem. A call to
 * `/api/*` is a script: refuse it in the shape the rest of the API answers errors in
 * (RFC 9457), and refuse it *here* — the proxy is never entered, so `ORCHESTRATOR_TOKEN`
 * is never attached to a request nobody proved they were allowed to make.
 *
 * An invalid cookie is not an error condition. A tampered signature, a rewritten issued-at,
 * a malformed value and a 31-day-old session are all simply "no session"; distinguishing
 * them on screen would tell an attacker which half of the guess was right.
 */
import { defineMiddleware } from 'astro:middleware';
import { ORCHESTRATOR_SESSION_SECRET } from 'astro:env/server';

import { SESSION_COOKIE, verify } from './lib/session';

/** The one page reachable without a session; guarding it would close the only way in. */
const LOGIN_PATH = '/login';

/** The proxy route (`src/pages/api/[...path].ts`), which answers rather than redirects. */
const PROXY_PREFIX = '/api/';

// Astro also injects an RPC route at `/_actions/*`, and it is guarded like any other path.
// That is correct for every Action a logged-in screen calls, and harmless for the login
// Action itself: a form posts to the page as `/login?_action=login`, which is why the login
// screen works with no JavaScript and why the one Action reachable without a session is
// reached through the exemption above rather than through the RPC route.

function unauthorized(): Response {
  return new Response(JSON.stringify({ type: 'about:blank', title: 'unauthorized', status: 401 }), {
    status: 401,
    headers: {
      'Content-Type': 'application/problem+json',
      // a refusal that got cached would outlive the session it was refused for
      'Cache-Control': 'no-store',
    },
  });
}

function toLogin(): Response {
  return new Response(null, { status: 302, headers: { Location: LOGIN_PATH } });
}

export const onRequest = defineMiddleware(async (context, next) => {
  const cookie = context.cookies.get(SESSION_COOKIE)?.value;
  const authenticated = verify(cookie, ORCHESTRATOR_SESSION_SECRET, Date.now());
  context.locals.authenticated = authenticated;

  const { pathname } = context.url;
  const response =
    authenticated || pathname === LOGIN_PATH
      ? await next()
      : pathname.startsWith(PROXY_PREFIX)
        ? unauthorized()
        : toLogin();

  // every answer above was chosen by reading the Cookie header, so anything that caches
  // one has to key on it. Without this a shared cache could hand a stored Board to a
  // browser that has no session — the guard would still be running and still be bypassed.
  response.headers.append('Vary', 'Cookie');
  return response;
});
