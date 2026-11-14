import { getContainerRenderer } from '@astrojs/react';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { loadRenderers } from 'astro:container';
import { describe, expect, it } from 'vitest';

import ComparePage from '../../src/pages/metrics/compare.astro';

async function render(search: string): Promise<string> {
  const container = await AstroContainer.create({
    renderers: await loadRenderers([getContainerRenderer()]),
  });
  return container.renderToString(ComparePage, {
    request: new Request(`http://web-client.test/metrics/compare${search}`),
  });
}

describe('/metrics/compare page', () => {
  it('renders COMPARE, the run count, Metrics current and the island', async () => {
    const html = await render('?runs=a,b,c');
    expect(html).toContain('COMPARE');
    expect(html).toContain('3 runs');
    expect(html).toMatch(
      /data-testid="nav-metrics"[^>]*aria-current="page"|aria-current="page"[^>]*data-testid="nav-metrics"/,
    );
    expect(html).toContain('astro-island');
  });

  it('counts only distinct ids', async () => {
    expect(await render('?runs=a,a,')).toContain('1 runs');
  });
});
