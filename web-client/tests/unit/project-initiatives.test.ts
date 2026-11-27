/** Story 10.2: ProjectInitiatives.astro and its mount in the projects page. */
import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProjectInitiatives from '../../src/components/projects/ProjectInitiatives.astro';
import ProjectsIndexPage from '../../src/pages/projects/index.astro';
import type { InitiativeRow } from '../../src/lib/initiatives/format';

const ID = '11111111-0000-4000-8000-000000000001';
const detail = {
  id: ID,
  slug: 'first-project',
  name: 'First Project',
  context_text: '',
  context_paths: [],
  env_vars: [],
  log_prompt_content: false,
  created_at: '2026-01-05T09:00:00Z',
  updated_at: '2026-01-06T10:00:00Z',
  repositories: [],
  monthly_spend_usd: '3.50',
  monthly_spend_provisional: true,
};
const row: InitiativeRow = {
  attention: null,
  id: 'ini-1',
  line: 'line one',
  name: 'Initiative One',
  position: 1,
  progress: 'p',
  project_id: ID,
  project_name: 'ProjectZed',
  reason: '',
  repo_tag: ['repo-a'],
  repository_id: 'r',
  slug: 'initiative-one',
  status: 'running',
  step: 's',
  updated_at: '2026-11-26T11:00:00Z',
  workflow: 'spec',
  workflow_count: 2,
  workflows: [{ workflow: 'spec', type: 'auto', state: 'ongoing' }],
};
const listBody = (items: InitiativeRow[]) => ({
  items,
  columns: [],
  counts: { ongoing: items.length, need_you: 0, cancelled: 0, oldest_wait_at: null },
  next_cursor: null,
});

const container = () =>
  loadRenderers([getContainerRenderer()]).then((renderers) => AstroContainer.create({ renderers }));

async function renderPage(initiatives: () => Response | Promise<Response>): Promise<string> {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      const { pathname } = new URL(request.url);
      if (pathname === '/api/v1/projects') {
        return Promise.resolve(
          new Response(JSON.stringify({ items: [detail], next_cursor: null }), { status: 200 }),
        );
      }
      if (pathname === `/api/v1/projects/${ID}/initiatives`) return Promise.resolve(initiatives());
      return Promise.resolve(new Response(JSON.stringify(detail), { status: 200 }));
    }),
  );
  return (await container()).renderToString(ProjectsIndexPage, {
    request: new Request(`http://web-client.test/projects?id=${ID}`),
  });
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.unstubAllGlobals());

describe('ProjectInitiatives component (story 10.2)', () => {
  it('AC7: null rows read unavailable', async () => {
    const html = await (
      await container()
    ).renderToString(ProjectInitiatives, {
      props: { projectId: ID, rows: null },
    });
    expect(html).toContain('INITIATIVES UNAVAILABLE');
    expect(html).toContain('The list could not be read from backend-api.');
    expect(html).toContain('Reload the page once the connection is restored.');
  });

  it('AC6: no rows reads NO INITIATIVES with a New initiative link', async () => {
    const html = await (
      await container()
    ).renderToString(ProjectInitiatives, {
      props: { projectId: ID, rows: [] },
    });
    expect(html).toContain('NO INITIATIVES');
    expect(html).toContain('An initiative starts from a project: a name and a first message.');
    expect(html).toContain(`href="/initiatives/new?project=${ID}"`);
  });

  it('AC6: one row renders the table without a Project column', async () => {
    const html = await (
      await container()
    ).renderToString(ProjectInitiatives, {
      props: { projectId: ID, rows: [row] },
    });
    expect(html).toContain('data-testid="initiatives-list"');
    expect(html).toContain('initiatives-row-initiative-one');
    expect(html).not.toContain('<th>Project</th>');
    expect(html).not.toContain('astro-island');
  });
});

describe('projects page INITIATIVES section (story 10.2)', () => {
  it('AC6: empty answer, section before RUNS ON THIS PROJECT', async () => {
    const html = await renderPage(() => json(listBody([])));
    expect(html).toContain('NO INITIATIVES');
    expect(html.indexOf('INITIATIVES')).toBeLessThan(html.indexOf('RUNS ON THIS PROJECT'));
  });

  it('AC6: one row renders server-side', async () => {
    const html = await renderPage(() => json(listBody([row])));
    expect(html).toContain('initiatives-row-initiative-one');
    expect(html).not.toContain('<th>Project</th>');
    // the page itself carries a MetricHint island; none may be the table
    expect(html).not.toContain('InitiativesTable');
    expect(html).not.toMatch(/<astro-island[^>]*>[^]*<table class="ini-table"[^]*<\/astro-island>/);
  });

  it('AC7: a 500 reads unavailable and the rest of the pane renders', async () => {
    const html = await renderPage(() =>
      json({ type: 'about:blank', title: 'boom', status: 500 }, 500),
    );
    expect(html).toContain('INITIATIVES UNAVAILABLE');
    expect(html).not.toContain('NO INITIATIVES');
    expect(html).toContain('REPOSITORIES');
    expect(html).toContain('RUNS ON THIS PROJECT');
  });

  it('AC7: a rejected fetch reads unavailable', async () => {
    const html = await renderPage(() => {
      throw new Error('down');
    });
    expect(html).toContain('INITIATIVES UNAVAILABLE');
    expect(html).toContain('REPOSITORIES');
  });
});
