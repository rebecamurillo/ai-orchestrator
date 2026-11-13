// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import RunCharts from '../../src/components/charts/RunCharts';
import MetricsTab from '../../src/components/run/MetricsTab';
import MetricsFlatTable from '../../src/components/run/MetricsFlatTable';
import { resetCatalogue, $catalogue } from '../../src/stores/catalogue';
import { initMetricsTab, setView } from '../../src/stores/metrics-tab';
import type { TargetContext } from '../../src/lib/run/metrics-glance';
import { metricsContext } from '../../src/components/run/MetricsTab';
import { entry, value } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

const at = (metric_id: string, scope_type: string, scope_key: string, over = {}) =>
  value({ metric_id, scope_type, scope_key, value_num: '2', ...over });
const S0 = 'epics[0].stories[0]';
const S1 = 'epics[0].stories[1]';
const RETRO = 'epics[0].retro';

const items = () => [
  at('cost.gateway', 'story', S0, { value_num: '10' }),
  at('cost.harness', 'story', S0, { value_num: '12' }),
  at('cost.retries', 'story', S0, { source: 'gateway', value_num: '3' }),
  at('cost.retries', 'story', S0, { source: 'harness', value_num: '4' }),
  at('cost.gateway', 'story', S1),
  at('cost.harness', 'story', S1),
  at('cost.gateway', 'step', RETRO, {
    value_num: null,
    missing: 'n/a — shell step, no model called',
  }),
  at('cost.harness', 'step', RETRO, {
    value_num: null,
    missing: 'n/a — shell step, no model called',
  }),
  ...['implement', 'senior', 'review'].flatMap((role, i) => [
    at('cost.gateway', 'role', role, { value_num: String(9 - i) }),
    at('cost.harness', 'role', role, { value_num: String(8 - i) }),
    at('tokens.output', 'role', role, { unit: 'tokens', value_num: String(1000 * (i + 1)) }),
    at('tokens.cache_read', 'role', role, { unit: 'tokens' }),
    at('cost.gateway', 'attempt', `${S0}.build#${i + 1}`, { role, attempt_n: i + 1 }),
  ]),
  at('cost.harness', 'model', 'sonnet', { value_num: '7' }),
  at('time.machine', 'run', 'r', { unit: 'seconds', value_num: '5400' }),
  at('time.parked', 'run', 'r', { unit: 'seconds', value_num: '1800' }),
];

const extra = () =>
  ['tokens.cache_write', 'time.machine', 'time.parked', 'cost.retries'].map((id) =>
    entry(id, { label: `label of ${id}` }),
  );

function mountTab(over: Partial<Parameters<typeof MetricsTab>[0]> = {}) {
  const base: Parameters<typeof MetricsTab>[0] = {
    detail: detailOf('done'),
    glance: glanceOf({
      metrics: { items: items(), latest: 1, run_id: '1', values_so_far: false, version: 1 },
    }),
    onSelectVersion: vi.fn(),
    onRetryMetrics: vi.fn(),
  };
  const ui = (p: typeof base) => createElement(MetricsTab, p);
  const out = render(ui({ ...base, ...over }));
  return {
    ...out,
    again: (p: Partial<typeof base>) => out.rerender(ui({ ...base, ...over, ...p })),
  };
}

const titles = () => screen.getAllByRole('figure').map((f) => f.getAttribute('aria-label'));

beforeEach(() => {
  seedCatalogue(extra());
  initMetricsTab('1', { view: 'table', set: 'headline' });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
  setView('table');
});

describe('METRICS tab CHART view (AC8)', () => {
  it('replaces the tables with the figures in order, and TABLE brings them back', () => {
    mountTab();
    fireEvent.click(screen.getByRole('button', { name: 'CHART' }));
    expect(screen.getByRole('button', { name: 'CHART' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByTestId('wf-metrics-scope')).toBeNull();
    expect(screen.queryByTestId('wf-metrics-role')).toBeNull();
    expect(titles()).toEqual([
      'where the money went, by scope',
      'cost by role',
      'tokens by role · label of tokens.output',
      'tokens by role · label of tokens.cache_read',
      'cost by model',
      'where the time went',
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'ALL METRICS' }));
    expect(titles()).toEqual([
      'where the money went, by scope',
      'cost by role',
      'tokens by role · label of tokens.output',
      'tokens by role · label of tokens.cache_read',
      'tokens by role · label of tokens.cache_write',
      'tokens by role · label of tokens.input',
      'cost by model',
      'where the time went',
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'TABLE' }));
    expect(screen.queryAllByRole('figure')).toHaveLength(0);
    expect(screen.getByTestId('wf-metrics-scope')).toBeTruthy();
  });

  it('opens in the chart view from the store and keeps it across a poll re-render', () => {
    initMetricsTab('1', { view: 'chart', set: 'headline' });
    const { again } = mountTab();
    expect(screen.getByRole('button', { name: 'CHART' }).getAttribute('aria-pressed')).toBe('true');
    again({
      glance: glanceOf({
        metrics: { items: items(), latest: 1, run_id: '1', values_so_far: true, version: 1 },
      }),
    });
    expect(screen.getByRole('button', { name: 'CHART' }).getAttribute('aria-pressed')).toBe('true');
    expect(titles()).toHaveLength(6);
  });

  it('does not render a panel whose metric has no catalogue entry', () => {
    const entries = { ...$catalogue.get().entries };
    delete entries['tokens.cache_read'];
    $catalogue.set({ status: 'ready', entries });
    initMetricsTab('1', { view: 'chart', set: 'headline' });
    mountTab();
    expect(titles()).not.toContain('tokens by role · label of tokens.cache_read');
    expect(titles()).toHaveLength(5);
  });
});

describe('Run page rows (AC9)', () => {
  const ctx = (): TargetContext => metricsContext(detailOf('done'), glanceOf(), false);
  const stepOrder = [`${S0}.build`, `${S1}.build`, RETRO];
  const draw = () =>
    render(
      createElement(RunCharts, {
        entries: $catalogue.get().entries,
        items: items(),
        stepOrder,
        set: 'headline',
        ctx: ctx(),
      }),
    );
  const panel = (title: string) => screen.getByRole('figure', { name: title });

  it('lists stories and the epic-level step labelled as the tree labels them', () => {
    draw();
    const scope = panel('where the money went, by scope');
    expect(scope.textContent).toContain('epic 1 · story 1');
    expect(scope.textContent).toContain('epic 1 · story 2');
    expect(scope.textContent).toContain(RETRO);
    expect(within(scope).getAllByText('n/a — shell step, no model called')).toHaveLength(2);
    expect(within(scope).getAllByRole('button')).toHaveLength(4);
  });

  it('hatches the retries share of its own bar and names it in the key', () => {
    draw();
    const scope = panel('where the money went, by scope');
    expect(scope.querySelector('.chart-key')?.textContent).toBe(
      'label of cost.gateway · label of cost.harness · hatched = label of cost.retries',
    );
    const hatched = scope.querySelectorAll(
      'rect[fill="url(#hatch-1)"], rect[fill="url(#hatch-2)"]',
    );
    expect(hatched).toHaveLength(2);
  });

  it('says the per-model gateway split is not stored and draws only the harness mark', () => {
    draw();
    const model = panel('cost by model');
    expect(model.textContent).toContain('not available (per-model gateway split not stored)');
    expect(within(model).getAllByRole('button')).toHaveLength(1);
    expect(within(model).getByRole('button').getAttribute('aria-label')).toBe(
      'my run sonnet label of cost.harness $7.00',
    );
  });

  it('labels the time bars with the durations the table prints', () => {
    draw();
    const [machine, parked] = within(panel('where the time went')).getAllByRole('button');
    expect(machine.querySelector('text')?.textContent).toBe('1h 30m');
    expect(parked.querySelector('text')?.textContent).toBe('0h 30m');
    expect(parked.querySelector('rect')?.getAttribute('fill')).toBe('url(#hatch-2)');
  });
});

describe('the chart equals the table (AC5)', () => {
  it('names every mark with the text its table cell shows', () => {
    const rows = items();
    const ctx = metricsContext(detailOf('done'), glanceOf(), false);
    const table = render(createElement(MetricsFlatTable, { scopeType: 'role', items: rows, ctx }));
    const bodyRows = [...table.container.querySelectorAll('tbody tr')];
    const cells = new Map(
      bodyRows.map((tr) => [
        tr.querySelector('th')?.textContent as string,
        [...tr.querySelectorAll('td')].map((td) => td.textContent as string),
      ]),
    );
    table.unmount();
    expect([...cells.keys()].sort()).toEqual(['implement', 'review', 'senior']);

    render(
      createElement(RunCharts, {
        entries: $catalogue.get().entries,
        items: rows,
        stepOrder: [`${S0}.build`],
        set: 'headline',
        ctx,
      }),
    );
    const roleChart = screen.getByRole('figure', { name: 'cost by role' });
    const tokenChart = screen.getByRole('figure', {
      name: /tokens by role · label of tokens.output/,
    });
    expect(within(roleChart).getAllByRole('button')).toHaveLength(6);
    for (const [role, cols] of cells) {
      const [gateway, harness, , output] = cols;
      const names = (chart: HTMLElement) =>
        within(chart)
          .getAllByRole('button')
          .map((b) => b.getAttribute('aria-label') as string);
      expect(names(roleChart).some((n) => n.includes(` ${role} `) && n.endsWith(gateway))).toBe(
        true,
      );
      expect(names(roleChart).some((n) => n.includes(` ${role} `) && n.endsWith(harness))).toBe(
        true,
      );
      expect(names(tokenChart).some((n) => n.includes(` ${role} `) && n.endsWith(output))).toBe(
        true,
      );
    }
  });

  it('draws a value the table reads as a word as a word', () => {
    const rows = [
      at('cost.gateway', 'role', 'implement'),
      at('cost.harness', 'role', 'implement', { value_num: null, missing: 'not recorded' }),
    ];
    const ctx = metricsContext(detailOf('done'), glanceOf(), false);
    render(
      createElement(RunCharts, {
        entries: $catalogue.get().entries,
        items: rows,
        stepOrder: [],
        set: 'headline',
        ctx,
      }),
    );
    const figure = screen.getByRole('figure', { name: 'cost by role' });
    expect(within(figure).getByText('not recorded')).toBeTruthy();
    expect(within(figure).getAllByRole('button')).toHaveLength(1);
  });
});
