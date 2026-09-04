/**
 * The guard (AD-4), as the rows of the story's I/O matrix.
 *
 * The middleware is the only thing standing in front of both the pages and the proxy, and
 * the two answers it gives are deliberately different: a page load is redirected so the
 * Operator lands somewhere useful, a proxied API call is refused in the shape the rest of
 * the API answers errors in. The refusal case runs `next` into the *real* proxy route with
 * a mocked upstream, so "the upstream is not called" is measured rather than assumed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, sign } from '../../src/lib/session';
import { onRequest } from '../../src/middleware';
import { ORCHESTRATOR_SESSION_SECRET } from '../stubs/astro-env-server';

const ORIGIN = 'http://web-client.test';
const NOW = Date.now();
const GUARDED_PAGES = ['/', '/runs', '/projects', '/templates', '/workflows/new'];

type Locals = { authenticated?: boolean };

let upstream: ReturnType<typeof vi.fn>;

/** A context shaped like the parts of Astro's `APIContext` the middleware reads. */
function context(pathname: string, cookie?: string) {
  const locals: Locals = {};
  return {
    url: new URL(pathname, ORIGIN),
    request: new Request(`${ORIGIN}${pathname}`),
    cookies: {
      get: (name: string) => (name === SESSION_COOKIE && cookie ? { value: cookie } : undefined),
    },
    locals,
  };
}

/** `next()` as the router would run it for `/api/*`: straight into the proxy route. */
async function proxy(request: Request, path: string): Promise<Response> {
  const route = await import('../../src/pages/api/[...path]');
  return route.ALL({ params: { path }, request } as never);
}

function run(ctx: ReturnType<typeof context>, next: () => Promise<Response>): Promise<Response> {
  return Promise.resolve(onRequest(ctx as never, next as never)) as Promise<Response>;
}

/**
 * What the router would have returned. A factory, not a constant: the middleware appends a
 * header to whatever comes back from `next()`, and a shared Response would accumulate that
 * header across every test in the file.
 */
const served = () => new Response('served', { status: 200 });

beforeEach(() => {
  upstream = vi.fn(() => Promise.resolve(new Response('{"pong":true}', { status: 200 })));
  vi.stubGlobal('fetch', upstream);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('a page load with no session', () => {
  it.each(GUARDED_PAGES)('sends %s to the login screen with a 302', async (pathname) => {
    const next = vi.fn(() => Promise.resolve(served()));

    const response = await run(context(pathname), next);

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe('/login');
    expect(next).not.toHaveBeenCalled();
  });

  it('records that the request is unauthenticated', async () => {
    const ctx = context('/');

    await run(ctx, () => Promise.resolve(served()));

    expect(ctx.locals.authenticated).toBe(false);
  });
});

describe('the login screen', () => {
  it('is served without a session, or nobody could ever get one', async () => {
    const next = vi.fn(() => Promise.resolve(served()));

    const response = await run(context('/login'), next);

    expect(response.status).toBe(200);
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('is served for the form post the Action answers', async () => {
    // an Astro form Action posts to the page itself as `?_action=login`; guarding that
    // would make the login form unusable
    const next = vi.fn(() => Promise.resolve(served()));

    await run(context('/login?_action=login'), next);

    expect(next).toHaveBeenCalledTimes(1);
  });
});

describe('the proxy with no session', () => {
  it('answers 401 as a problem document and never reaches backend-api', async () => {
    const request = new Request(`${ORIGIN}/api/ping`);
    const next = vi.fn(() => proxy(request, 'ping'));

    const response = await run(context('/api/ping'), next);

    expect(response.status).toBe(401);
    expect(response.headers.get('content-type')).toContain('application/problem+json');
    expect(await response.json()).toMatchObject({ title: 'unauthorized', status: 401 });
    expect(next).not.toHaveBeenCalled();
    expect(upstream).not.toHaveBeenCalled();
  });

  it('refuses rather than redirecting, because the caller is a script', async () => {
    const response = await run(context('/api/runs'), () => Promise.resolve(served()));

    expect(response.headers.get('location')).toBeNull();
  });

  it('is never cached', async () => {
    const response = await run(context('/api/ping'), () => Promise.resolve(served()));

    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('carries no credential of any kind in the refusal', async () => {
    const response = await run(context('/api/ping'), () => Promise.resolve(served()));
    const body = await response.text();

    for (const [, value] of response.headers) expect(value).not.toContain('Bearer');
    expect(body).not.toContain('Bearer');
  });
});

describe('a valid session', () => {
  const valid = () => sign(Date.now(), ORCHESTRATOR_SESSION_SECRET);

  it.each(GUARDED_PAGES)('lets %s render', async (pathname) => {
    const next = vi.fn(() => Promise.resolve(served()));

    const response = await run(context(pathname, valid()), next);

    expect(response.status).toBe(200);
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('lets the proxy forward, with the bearer the browser never had', async () => {
    const request = new Request(`${ORIGIN}/api/ping`);
    const next = vi.fn(() => proxy(request, 'ping'));

    const response = await run(context('/api/ping', valid()), next);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ pong: true });
    expect(upstream).toHaveBeenCalledTimes(1);
  });

  it('records that the request is authenticated', async () => {
    const ctx = context('/', valid());

    await run(ctx, () => Promise.resolve(served()));

    expect(ctx.locals.authenticated).toBe(true);
  });
});

describe('a cookie that is not a session', () => {
  const OLD = NOW - (SESSION_MAX_AGE_SECONDS * 1000 + 1);

  it.each([
    ['a tampered signature', `${NOW}.${'0'.repeat(64)}`],
    ['a foreign secret', sign(NOW, 'some-other-instance-secret')],
    ['an expired issued-at', sign(OLD, ORCHESTRATOR_SESSION_SECRET)],
    ['a malformed value', 'not-a-session'],
    ['an empty value', ''],
  ])('is treated as absent on a page: %s', async (_case, cookie) => {
    const response = await run(context('/', cookie), () => Promise.resolve(served()));

    expect(response.status).toBe(302);
    expect(response.headers.get('location')).toBe('/login');
  });

  it.each([
    ['a tampered signature', `${NOW}.${'0'.repeat(64)}`],
    ['an expired issued-at', sign(OLD, ORCHESTRATOR_SESSION_SECRET)],
  ])('is treated as absent on the proxy: %s', async (_case, cookie) => {
    const request = new Request(`${ORIGIN}/api/ping`);
    const next = vi.fn(() => proxy(request, 'ping'));

    const response = await run(context('/api/ping', cookie), next);

    expect(response.status).toBe(401);
    expect(upstream).not.toHaveBeenCalled();
  });
});

describe('every answer the guard gives', () => {
  it.each([
    ['a redirected page', '/', undefined],
    ['a refused proxy call', '/api/ping', undefined],
    ['the login screen', '/login', undefined],
    ['a rendered page', '/', sign(Date.now(), ORCHESTRATOR_SESSION_SECRET)],
  ])('varies on the cookie it was chosen by: %s', async (_case, pathname, cookie) => {
    // the answer depends on the Cookie header, so a cache that stored one without keying on
    // it could hand a logged-in page to a browser with no session
    const response = await run(context(pathname, cookie), () => Promise.resolve(served()));

    expect(response.headers.get('vary')).toContain('Cookie');
  });
});
