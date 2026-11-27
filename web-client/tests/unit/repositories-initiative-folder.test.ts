/** Story 10.5 AC8: the `initiative folder` column and the Action behind it. */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { initiativeFolder } from '../../src/actions/repositories';
import RepositoriesTable from '../../src/components/RepositoriesTable.astro';
import type { RepositoryRow } from '../../src/components/repository-row';

const ACTION_CONTEXT = Symbol.for('astro.actionAPIContext');
const REPO = '44444444-4444-4444-8444-444444444444';

let container: AstroContainer;
beforeAll(async () => {
  container = await AstroContainer.create();
});

function row(overrides: Partial<RepositoryRow> = {}): RepositoryRow {
  return {
    id: REPO,
    slug: 'hub',
    defaultBranch: 'main',
    method: '6.11.0',
    qualityGateCommand: 'make test',
    testGlobs: [],
    status: 'ok',
    seconds: 1,
    output: '',
    hint: '',
    verifySkipped: false,
    ...overrides,
  };
}
const render = (rows: RepositoryRow[]) =>
  container.renderToString(RepositoriesTable, { props: { projectId: 'pid', repositories: rows } });

describe('RepositoriesTable initiative folder column', () => {
  it('defaults to initiatives with a save button', async () => {
    const html = await render([row()]);
    expect(html).toContain('initiative folder');
    expect(html).toMatch(/data-testid="projects-folder-hub"[^>]*/);
    expect(html).toMatch(/value="initiatives"/);
    expect(html).toContain('data-testid="projects-folder-hub-save"');
    expect(html).toMatch(
      /action="\?id=pid&amp;_action=repositories\.initiativeFolder|action="\?id=pid&_action=repositories\.initiativeFolder/,
    );
  });

  it('shows the given folder', async () => {
    expect(await render([row({ initiativeFolder: 'specs' })])).toContain('value="specs"');
  });

  it('widens the inset row to eight columns', async () => {
    const html = await render([row({ status: 'failed' })]);
    expect(html).toContain('colspan="8"');
  });
});

describe('initiativeFolder Action', () => {
  let seen: { method: string; url: string; body: string }[];
  beforeEach(() => {
    seen = [];
  });
  afterEach(() => vi.unstubAllGlobals());

  function stub(response: Response) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        seen.push({ method: request.method, url: request.url, body: await request.text() });
        return response;
      }),
    );
  }
  const run = (fields: Record<string, string>) => {
    const f = new FormData();
    for (const [k, v] of Object.entries(fields)) f.set(k, v);
    return initiativeFolder.orThrow.call({ [ACTION_CONTEXT]: true }, f);
  };
  const problem = (status: number, detail?: string) =>
    new Response(JSON.stringify({ type: 'about:blank', title: 't', status, detail }), {
      status,
      headers: { 'Content-Type': 'application/problem+json' },
    });

  it('PUTs the folder', async () => {
    stub(new Response('{}', { status: 200 }));
    await run({ repositoryId: REPO, initiativeFolder: 'specs' });
    expect(seen[0]!.method).toBe('PUT');
    expect(seen[0]!.url).toBe(
      `http://backend-api.invalid:8000/api/v1/repositories/${REPO}/initiative-folder`,
    );
    expect(JSON.parse(seen[0]!.body)).toEqual({ initiative_folder: 'specs' });
  });

  it('rejects missing fields without sending', async () => {
    await expect(run({ initiativeFolder: 'x' })).rejects.toThrow('repositoryId is required');
    await expect(run({ repositoryId: REPO })).rejects.toThrow('initiativeFolder is required');
    expect(seen).toEqual([]);
  });

  it('maps 404, 422 and other failures', async () => {
    const fields = { repositoryId: REPO, initiativeFolder: 'x' };
    stub(problem(404, 'gone'));
    await expect(run(fields)).rejects.toThrow('gone');
    stub(problem(422, 'bad folder'));
    await expect(run(fields)).rejects.toThrow('bad folder');
    stub(problem(500));
    await expect(run(fields)).rejects.toThrow('initiative folder not saved');
  });
});
