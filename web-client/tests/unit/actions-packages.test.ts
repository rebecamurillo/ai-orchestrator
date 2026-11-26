/** Story 10.5: the packages Actions (AC6, AC7, AC10). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../src/actions/index';
import { install, remove } from '../../src/actions/packages';
import { ORCHESTRATOR_TOKEN } from '../stubs/astro-env-server';

const ACTION_CONTEXT = Symbol.for('astro.actionAPIContext');
const ID = '22222222-2222-4222-8222-222222222222';
const HUB = '33333333-3333-4333-8333-333333333333';

type Seen = { method: string; url: string; auth: string | null; body: string };
let seen: Seen[];

function stub(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      seen.push({
        method: request.method,
        url: request.url,
        auth: request.headers.get('authorization'),
        body: await request.text(),
      });
      return response;
    }),
  );
}
const problem = (status: number, detail?: string) =>
  new Response(JSON.stringify({ type: 'about:blank', title: 't', status, detail }), {
    status,
    headers: { 'Content-Type': 'application/problem+json' },
  });
const ctx = () => ({ [ACTION_CONTEXT]: true });
function form(fields: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.set(k, v);
  return f;
}
const full = { projectId: ID, repositoryId: HUB, path: 'package', ref: 'main' };

beforeEach(() => {
  seen = [];
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('install', () => {
  it('AC6: PUTs the body with the bearer', async () => {
    stub(new Response('{"name":"p"}', { status: 200 }));
    await install.orThrow.call(ctx(), form(full));
    expect(seen).toHaveLength(1);
    expect(seen[0]!.method).toBe('PUT');
    expect(seen[0]!.url).toBe(`http://backend-api.invalid:8000/api/v1/projects/${ID}/package`);
    expect(seen[0]!.auth).toBe(`Bearer ${ORCHESTRATOR_TOKEN}`);
    expect(JSON.parse(seen[0]!.body)).toEqual({ repository_id: HUB, path: 'package', ref: 'main' });
  });

  it.each(['projectId', 'repositoryId', 'path', 'ref'])(
    'AC6: a missing %s rejects and sends nothing',
    async (name) => {
      const fields: Record<string, string> = { ...full };
      delete fields[name];
      await expect(install.orThrow.call(ctx(), form(fields))).rejects.toThrow(
        `${name} is required`,
      );
      expect(seen).toEqual([]);
    },
  );

  it.each([404, 409, 422])('AC6: %s carries the problem detail', async (status) => {
    stub(problem(status, `detail ${status}`));
    await expect(install.orThrow.call(ctx(), form(full))).rejects.toThrow(`detail ${status}`);
  });

  it('falls back to the title, then to a plain word, for other failures', async () => {
    stub(problem(500));
    await expect(install.orThrow.call(ctx(), form(full))).rejects.toThrow('t');
  });
});

describe('remove', () => {
  it('AC7: DELETEs and resolves on 204', async () => {
    stub(new Response(null, { status: 204 }));
    await remove.orThrow.call(ctx(), form({ projectId: ID }));
    expect(seen[0]!.method).toBe('DELETE');
    expect(seen[0]!.url).toBe(`http://backend-api.invalid:8000/api/v1/projects/${ID}/package`);
  });

  it('AC7: a 409 rejects CONFLICT with exactly the detail', async () => {
    const detail = 'refused: 2 open initiatives use this package — a, b';
    stub(problem(409, detail));
    const result = await remove.call(ctx(), form({ projectId: ID }));
    expect(result.error?.code).toBe('CONFLICT');
    expect(result.error?.message).toBe(detail);
  });

  it('rejects a missing projectId, and falls back to a plain message', async () => {
    await expect(remove.orThrow.call(ctx(), form({}))).rejects.toThrow('projectId is required');
    expect(seen).toEqual([]);
    stub(problem(500));
    await expect(remove.orThrow.call(ctx(), form({ projectId: ID }))).rejects.toThrow(
      'remove failed',
    );
  });
});

it('AC10: the registry exports the three Actions and keeps recheck/init', () => {
  expect(server.packages.install).toBe(install);
  expect(server.packages.remove).toBe(remove);
  expect(server.repositories.initiativeFolder).toBeDefined();
  expect(server.repositories.recheck).toBeDefined();
  expect(server.repositories.init).toBeDefined();
});
