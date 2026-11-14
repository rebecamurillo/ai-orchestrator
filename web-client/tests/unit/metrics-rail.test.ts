/** Story 4.2 (2026-11-13): the rail reads Workflows · Runs · Metrics, then CONFIGURE. */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import AppRail from '../../src/components/AppRail.astro';

let container: AstroContainer;
beforeAll(async () => {
  container = await AstroContainer.create();
});

const render = (props: Record<string, unknown>) => container.renderToString(AppRail, { props });

describe('AppRail Metrics item', () => {
  it('orders the items and puts CONFIGURE after Metrics', async () => {
    const html = await render({ active: 'workflows' });
    const at = (needle: string) => html.indexOf(needle);
    const order = [
      at('nav-workflows'),
      at('nav-runs'),
      at('nav-metrics'),
      at('CONFIGURE'),
      at('nav-projects'),
      at('nav-templates'),
    ];
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('links to /metrics and carries no count', async () => {
    const html = await render({ active: 'workflows', runs: 4, workflows: 3 });
    const item = html.match(/<a[^>]*nav-metrics[\s\S]*?<\/a>/)![0];
    expect(item).toContain('href="/metrics"');
    expect(item).not.toContain('class="count');
    expect(item).not.toMatch(/count/);
  });

  it('marks Metrics current only when active', async () => {
    const on = await render({ active: 'metrics' });
    expect(on.match(/<a[^>]*nav-metrics[^>]*>/)![0]).toContain('aria-current="page"');
    expect(on.match(/aria-current="page"/g)).toHaveLength(1);
    const off = await render({ active: 'runs' });
    expect(off.match(/<a[^>]*nav-metrics[^>]*>/)![0]).not.toContain('aria-current');
  });
});
