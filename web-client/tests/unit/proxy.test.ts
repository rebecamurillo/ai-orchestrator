/**
 * The proxy is the whole of AD-1 in one route: the browser reaches backend-api only
 * through it, and it is the only place the bearer is attached. What follows are the rows
 * of the story's I/O matrix, each against a mocked upstream.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ORCHESTRATOR_TOKEN } from '../stubs/astro-env-server';

const UPSTREAM = 'http://backend-api.invalid:8000';

type Upstream = { url: string; init: RequestInit };

let seen: Upstream[];

/** Records what the route asked of backend-api and answers with `response`. */
function stubUpstream(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string | URL | Request, init: RequestInit = {}) => {
      seen.push({ url: String(url), init });
      return Promise.resolve(response);
    }),
  );
}

async function proxy(request: Request, path: string): Promise<Response> {
  const route = await import('../../src/pages/api/[...path]');
  return route.ALL({ params: { path }, request } as never);
}

beforeEach(() => {
  seen = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('the proxy route', () => {
  it('forwards /api/ping to the versioned upstream path with the bearer', async () => {
    stubUpstream(new Response('{"pong":true}', { status: 200 }));

    await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(seen).toHaveLength(1);
    expect(seen[0]!.url).toBe(`${UPSTREAM}/api/v1/ping`);
    const headers = new Headers(seen[0]!.init.headers);
    expect(headers.get('authorization')).toBe(`Bearer ${ORCHESTRATOR_TOKEN}`);
  });

  it('keeps the query string', async () => {
    stubUpstream(new Response('[]', { status: 200 }));

    await proxy(new Request('http://web-client.test/api/runs?view=board&limit=2'), 'runs');

    expect(seen[0]!.url).toBe(`${UPSTREAM}/api/v1/runs?view=board&limit=2`);
  });

  it('forwards the method, the body and the content type', async () => {
    stubUpstream(new Response('{}', { status: 201 }));

    await proxy(
      new Request('http://web-client.test/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{"template":"story"}',
      }),
      'runs',
    );

    const { init } = seen[0]!;
    expect(init.method).toBe('POST');
    expect(new Headers(init.headers).get('content-type')).toBe('application/json');
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"template":"story"}');
  });

  it('sends no body on a GET', async () => {
    stubUpstream(new Response('{}', { status: 200 }));

    await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(seen[0]!.init.body).toBeUndefined();
  });

  it('returns the upstream status and body unchanged', async () => {
    stubUpstream(
      new Response('{"title":"unauthorized","status":401}', {
        status: 401,
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    );

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(response.status).toBe(401);
    expect(response.headers.get('content-type')).toBe('application/problem+json');
    expect(await response.text()).toBe('{"title":"unauthorized","status":401}');
  });

  it('drops hop-by-hop response headers', async () => {
    stubUpstream(
      new Response('{}', {
        status: 200,
        headers: {
          Connection: 'keep-alive',
          'Keep-Alive': 'timeout=5',
          'Transfer-Encoding': 'chunked',
          'X-Request-Id': 'kept',
        },
      }),
    );

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(response.headers.get('connection')).toBeNull();
    expect(response.headers.get('keep-alive')).toBeNull();
    expect(response.headers.get('transfer-encoding')).toBeNull();
    expect(response.headers.get('x-request-id')).toBe('kept');
  });

  it('never lets the credential back out to the browser', async () => {
    stubUpstream(
      new Response('{}', {
        status: 200,
        // an upstream that echoed the header back would otherwise be copied verbatim
        headers: { Authorization: `Bearer ${ORCHESTRATOR_TOKEN}`, 'X-Echo': ORCHESTRATOR_TOKEN },
      }),
    );

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    for (const [, value] of response.headers) {
      expect(value).not.toContain(ORCHESTRATOR_TOKEN);
    }
  });

  it.each([
    ['../healthz', 'a plain parent segment'],
    ['%2e%2e/openapi.json', 'percent-encoded dots, which the router does not decode'],
    ['v1/../../healthz', 'a segment that climbs out after descending'],
  ])('refuses %s (%s) rather than reaching an unversioned route', async (path) => {
    stubUpstream(new Response('{"leaked":true}', { status: 200 }));

    const response = await proxy(new Request(`http://web-client.test/api/${path}`), path);

    expect(seen).toEqual([]);
    expect(response.status).toBe(400);
    expect(response.headers.get('content-type')).toContain('application/problem+json');
    expect(await response.json()).toMatchObject({ title: 'invalid path', status: 400 });
  });

  it('leaves an encoded separator as one opaque segment', async () => {
    // `%2F` is not a path separator to either URL parser, so this names a single segment
    // inside the prefix. It is forwarded verbatim and 404s upstream; refusing it here
    // would refuse legitimate ids that happen to contain an encoded slash.
    stubUpstream(new Response('{}', { status: 404 }));

    await proxy(new Request('http://web-client.test/api/..%2Fhealthz'), '..%2Fhealthz');

    expect(seen[0]!.url).toBe(`${UPSTREAM}/api/v1/..%2Fhealthz`);
  });

  it('answers a status that carries no body without one', async () => {
    stubUpstream(new Response(null, { status: 204 }));

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(response.status).toBe(204);
    expect(response.body).toBeNull();
  });

  it('does not forward the browser cookie or host to backend-api', async () => {
    stubUpstream(new Response('{}', { status: 200 }));

    await proxy(
      new Request('http://web-client.test/api/ping', {
        headers: { Cookie: 'orch_session=abc', 'X-Trace': 'kept' },
      }),
      'ping',
    );

    const headers = new Headers(seen[0]!.init.headers);
    expect(headers.get('cookie')).toBeNull();
    expect(headers.get('host')).toBeNull();
    expect(headers.get('x-trace')).toBe('kept');
  });

  it('re-frames the body rather than repeating the upstream framing', async () => {
    stubUpstream(
      new Response('{}', {
        status: 200,
        headers: { 'Content-Encoding': 'gzip', 'Content-Length': '999' },
      }),
    );

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    // the fetch implementation already decoded the body; repeating these would describe a
    // message the browser is not receiving
    expect(response.headers.get('content-encoding')).toBeNull();
    expect(response.headers.get('content-length')).toBeNull();
  });

  it('lets the fetch implementation negotiate its own encoding', async () => {
    stubUpstream(new Response('{}', { status: 200 }));

    await proxy(
      new Request('http://web-client.test/api/ping', {
        headers: { 'Accept-Encoding': 'gzip, br' },
      }),
      'ping',
    );

    expect(new Headers(seen[0]!.init.headers).get('accept-encoding')).toBeNull();
  });

  it('marks every proxied response uncacheable', async () => {
    stubUpstream(new Response('{}', { status: 200, headers: { 'Cache-Control': 'max-age=600' } }));

    const response = await proxy(new Request('http://web-client.test/api/ping'), 'ping');

    expect(response.headers.get('cache-control')).toBe('no-store');
  });
});
