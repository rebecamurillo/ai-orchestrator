import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProjectsIndexPage from '../../src/pages/projects/index.astro';

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

afterEach(() => vi.unstubAllGlobals());

describe('project pane metrics link', () => {
  it('links to /metrics for the project and keeps the meta line', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) => {
        const { pathname } = new URL(request.url);
        const body =
          pathname === '/api/v1/projects' ? { items: [detail], next_cursor: null } : detail;
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
      }),
    );
    const container = await AstroContainer.create({
      renderers: await loadRenderers([getContainerRenderer()]),
    });
    const html = await container.renderToString(ProjectsIndexPage, {
      request: new Request(`http://web-client.test/projects?id=${ID}`),
    });
    expect(html).toMatch(
      new RegExp(`<a[^>]*href="/metrics\\?project=${ID}"[^>]*>metrics for this project</a>`),
    );
    expect(html).toContain('this month $3.50 provisional');
  });
});
