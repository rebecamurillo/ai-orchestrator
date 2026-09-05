/**
 * The `recheck` Action, exercised without a browser — `vi.stubGlobal('fetch', ...)` pattern
 * from `proxy.test.ts`, and the `Symbol.for('astro.actionAPIContext')` double from
 * `actions.test.ts`, since `defineAction` refuses to run a handler whose `this` is not
 * marked as one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../src/actions/index';
import { recheck } from '../../src/actions/repositories';
import { ORCHESTRATOR_TOKEN } from '../stubs/astro-env-server';

const ACTION_CONTEXT = Symbol.for('astro.actionAPIContext');

type Upstream = { url: string; headers: Headers };

let seen: Upstream[];

/**
 * openapi-fetch calls `fetch(request, init)` with a single `Request` object rather than a
 * separate url and header bag (unlike `src/api/server.ts`'s own `fetch(target, {...})`, which
 * `proxy.test.ts` stubs the same way but reads apart) — the url and the headers both live on
 * the `Request` itself here.
 */
function stubUpstream(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      seen.push({ url: request.url, headers: request.headers });
      return Promise.resolve(response);
    }),
  );
}

function context() {
  return { [ACTION_CONTEXT]: true };
}

function form(repositoryId?: string): FormData {
  const body = new FormData();
  if (repositoryId !== undefined) body.set('repositoryId', repositoryId);
  return body;
}

function submit(body: FormData): Promise<unknown> {
  return recheck.orThrow.call(context(), body);
}

beforeEach(() => {
  seen = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('the registry Astro builds `astro:actions` from', () => {
  it('exports the recheck Action under repositories, beside login', () => {
    expect(server.repositories.recheck).toBe(recheck);
    expect(server.login).toBeDefined();
  });
});

describe('the recheck Action', () => {
  it('runs the clone check and returns the result on success', async () => {
    const body = {
      status: 'ok',
      at: '2026-09-04T12:00:00Z',
      output: 'cloned ok',
      bmad_version: '6.11.0',
      lines: [{ name: 'clone', status: 'ok', seconds: 3, output: 'ok' }],
      hint: '',
    };
    stubUpstream(new Response(JSON.stringify(body), { status: 200 }));

    await expect(submit(form('11111111-1111-4111-8111-111111111111'))).resolves.toEqual(body);

    expect(seen).toHaveLength(1);
    expect(seen[0]!.url).toBe(
      'http://backend-api.invalid:8000/api/v1/repositories/11111111-1111-4111-8111-111111111111/clone-check',
    );
    expect(seen[0]!.headers.get('authorization')).toBe(`Bearer ${ORCHESTRATOR_TOKEN}`);
  });

  it('answers a missing repositoryId with a rejected BAD_REQUEST, and calls nothing', async () => {
    await expect(submit(form())).rejects.toThrow('repositoryId is required');
    expect(seen).toEqual([]);
  });

  it('answers an empty repositoryId the same way', async () => {
    await expect(submit(form(''))).rejects.toThrow('repositoryId is required');
    expect(seen).toEqual([]);
  });

  it('surfaces a 404 upstream as a NOT_FOUND ActionError carrying the detail', async () => {
    stubUpstream(
      new Response(
        JSON.stringify({
          type: 'about:blank',
          title: 'not found',
          status: 404,
          detail: 'no Repository has that id',
        }),
        {
          status: 404,
          headers: { 'Content-Type': 'application/problem+json' },
        },
      ),
    );

    await expect(submit(form('missing-id'))).rejects.toThrow('no Repository has that id');
  });

  it('surfaces any other upstream failure as INTERNAL_SERVER_ERROR', async () => {
    stubUpstream(
      new Response(JSON.stringify({ type: 'about:blank', title: 'error', status: 500 }), {
        status: 500,
        headers: { 'Content-Type': 'application/problem+json' },
      }),
    );

    await expect(submit(form('some-id'))).rejects.toThrow('clone check failed');
  });
});
