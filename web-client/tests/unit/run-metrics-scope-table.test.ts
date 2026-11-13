import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import MetricsScopeTable from '../../src/components/run/MetricsScopeTable';
import { $catalogue } from '../../src/stores/catalogue';
import { initMetricsTab, toggleRow } from '../../src/stores/metrics-tab';
import { value } from './metrics-fixtures';
import { glanceOf, seedCatalogue } from './run-metrics-fixtures';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { detailOf } from './run-metrics-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);
const html = (items: ReturnType<typeof value>[]) =>
  renderToStaticMarkup(createElement(MetricsScopeTable, { items, stepOrder: [], ctx }));

beforeEach(() => {
  seedCatalogue();
  initMetricsTab('run-x', { view: 'table', set: 'headline' });
});

describe('MetricsScopeTable', () => {
  it('drops a column whose metric has no catalogue entry', () => {
    const { entries } = $catalogue.get();
    const { 'tokens.input': _gone, ...rest } = entries;
    $catalogue.set({ status: 'ready', entries: rest });
    const out = html([value({ metric_id: 'cost.gateway' })]);
    expect(out).toContain('label of cost.gateway');
    expect(out).not.toContain('label of tokens.input');
  });

  it('indents by depth and shows only expanded levels', () => {
    const items = [
      value({ metric_id: 'cost.gateway', scope_type: 'epic', scope_key: 'epics[0]' }),
      value({ metric_id: 'cost.gateway', scope_type: 'story', scope_key: 'epics[0].stories[0]' }),
    ];
    expect(html(items)).toContain('data-depth="1"');
    expect(html(items)).not.toContain('story 1');
    toggleRow('epic:epics[0]');
    expect(html(items)).toContain('data-depth="2"');
    expect(html(items)).toContain('epic 1 · story 1');
  });

  it('joins several source values in one cell', () => {
    const run = (source: string, n: string) =>
      value({ metric_id: 'process.retries', source, value_num: n, unit: 'count' });
    const out = html([run('gateway', '1'), run('harness', '2')]);
    expect(out).toContain(' · ');
    expect(out.match(/metric-value-cell/g)).toHaveLength(2);
  });
});
