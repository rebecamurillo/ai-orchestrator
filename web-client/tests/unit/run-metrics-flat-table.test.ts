import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import MetricsFlatTable from '../../src/components/run/MetricsFlatTable';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { value } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);
const role = (key: string, num: string | null) =>
  value({
    metric_id: 'cost.gateway',
    scope_type: 'role',
    scope_key: key,
    value_num: num,
    missing: num === null ? 'not available' : null,
  });

beforeEach(() => seedCatalogue());

describe('MetricsFlatTable', () => {
  it('orders roles by gateway descending with a missing one last', () => {
    const items = [role('implement', '4.00'), role('senior', '9.00'), role('review', null)];
    const out = renderToStaticMarkup(
      createElement(MetricsFlatTable, { scopeType: 'role', items, ctx }),
    );
    const order = [...out.matchAll(/<th scope="row">([^<]*)</g)].map((m) => m[1]);
    expect(order).toEqual(['senior', 'implement', 'review']);
    expect(out).toContain('BY ROLE');
    expect(out).toContain('not available');
  });

  it('orders models the same way', () => {
    const items = [
      { ...role('a', '1.00'), scope_type: 'model' },
      { ...role('b', '2.00'), scope_type: 'model' },
    ];
    const out = renderToStaticMarkup(
      createElement(MetricsFlatTable, { scopeType: 'model', items, ctx }),
    );
    expect(out.indexOf('>b<')).toBeLessThan(out.indexOf('>a<'));
    expect(out).toContain('BY MODEL');
  });

  it('renders nothing without rows', () => {
    expect(
      renderToStaticMarkup(createElement(MetricsFlatTable, { scopeType: 'role', items: [], ctx })),
    ).toBe('');
  });
});
