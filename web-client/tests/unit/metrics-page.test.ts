import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { afterEach, describe, expect, it, vi } from 'vitest';

import MetricsPage from '../../src/pages/metrics/index.astro';
import { monthText } from '../../src/lib/metrics/home';

const P1 = '11111111-0000-4000-8000-000000000001';
const P2 = '11111111-0000-4000-8000-000000000002';
const proj = (id: string, name: string) => ({ id, name, slug: name, repositories: [] });

function stub(ok = true): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        ok
          ? new Response(
              JSON.stringify({ items: [proj(P1, 'Alpha'), proj(P2, 'Beta')], next_cursor: null }),
              { status: 200 },
            )
          : new Response('{}', { status: 500 }),
      ),
    ),
  );
}

async function render(search = ''): Promise<string> {
  const container = await AstroContainer.create({
    renderers: await loadRenderers([getContainerRenderer()]),
  });
  return container.renderToString(MetricsPage, {
    request: new Request(`http://web-client.test/metrics${search}`),
  });
}

afterEach(() => vi.unstubAllGlobals());

describe('/metrics page', () => {
  it('renders the bar, the filter and the island', async () => {
    stub();
    const html = await render();
    expect(html).toContain('METRICS');
    expect(html).toContain(`${monthText(new Date())} · 2 projects`);
    expect(html).toMatch(
      /data-testid="nav-metrics"[^>]*aria-current="page"|aria-current="page"[^>]*data-testid="nav-metrics"/,
    );
    expect(html).toContain('Alpha');
    expect(html).toContain(`/metrics?project=${P2}`);
    expect(html).toMatch(/<a[^>]*aria-current="true"[^>]*>\s*all\s*<\/a>/);
    expect(html).toContain('MetricsHome');
  });

  it('passes the chosen project name and marks it current', async () => {
    stub();
    const html = await render(`?project=${P2}&select=a,b`);
    expect(html).toMatch(/aria-current="true"[^>]*>\s*Beta/);
    expect(html).toContain('Beta');
  });

  it('degrades to all-only when the project list fails', async () => {
    stub(false);
    const html = await render();
    expect(html).toContain('0 projects');
  });
});
