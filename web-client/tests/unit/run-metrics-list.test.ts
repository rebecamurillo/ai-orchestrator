import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';

import MetricsList from '../../src/components/run/MetricsList';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { $catalogue } from '../../src/stores/catalogue';
import { entry, value } from './metrics-fixtures';
import { detailOf, glanceOf } from './run-metrics-fixtures';

const ctx = metricsContext(detailOf(), glanceOf(), false);

beforeEach(() => {
  const all = [
    entry('cost.gateway', { group: 'cost', level: 'H' }),
    entry('tokens.input', { group: 'tokens', level: 'A' }),
    entry('process.retries', { group: 'process', level: 'A', fingerprint_group: true }),
  ];
  $catalogue.set({ status: 'ready', entries: Object.fromEntries(all.map((e) => [e.id, e])) });
});

const items = ['cost.gateway', 'tokens.input', 'process.retries'].map((id) =>
  value({ metric_id: id, source: id === 'tokens.input' ? 'gateway' : null }),
);
const render = (set: 'headline' | 'all') =>
  renderToStaticMarkup(createElement(MetricsList, { items, set, ctx }));

describe('MetricsList', () => {
  it('lists groups in order with the fingerprint group last', () => {
    const out = render('all');
    const at = (s: string) => out.indexOf(s);
    expect(at('COST')).toBeLessThan(at('TOKENS'));
    expect(at('TOKENS')).toBeLessThan(at('describes how the method works, not how well'));
    expect(out).toContain('label of tokens.input');
    expect(out).toContain(' · gateway');
  });

  it('keeps level H only for the headline, with no fingerprint group', () => {
    const out = render('headline');
    expect(out).toContain('COST');
    expect(out).not.toContain('TOKENS');
    expect(out).not.toContain('describes how');
  });
});
