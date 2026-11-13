/** `index.astro` mounts the `MetricHint` island only after a monthly figure. */
import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProjectsIndexPage from '../../src/pages/projects/index.astro';

const ID = '11111111-0000-4000-8000-000000000001';
const project = (over: Record<string, unknown>) => ({
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
  ...over,
});

function stub(detail: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      const { pathname } = new URL(request.url);
      const body =
        pathname === '/api/v1/projects' ? { items: [detail], next_cursor: null } : detail;
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
    }),
  );
}

async function render(): Promise<string> {
  const container = await AstroContainer.create({
    renderers: await loadRenderers([getContainerRenderer()]),
  });
  return container.renderToString(ProjectsIndexPage, {
    request: new Request(`http://web-client.test/projects?id=${ID}`),
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('projects pane monthly hint', () => {
  it('follows the unchanged this-month text with the island', async () => {
    stub(project({ monthly_spend_usd: '3.50', monthly_spend_provisional: true }));
    const html = await render();
    expect(html).toContain('this month $3.50 provisional');
    expect(html).toMatch(/MetricHint/);
    expect(html).toContain('spend.month_recorded');
  });

  it('renders no island without a monthly figure', async () => {
    stub(project({ monthly_spend_usd: null }));
    const html = await render();
    expect(html).not.toContain('this month');
    expect(html).not.toContain('spend.month_recorded');
  });
});
