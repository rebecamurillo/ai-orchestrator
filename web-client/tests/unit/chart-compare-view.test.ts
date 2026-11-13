// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { writePng } = vi.hoisted(() => ({ writePng: vi.fn() }));
vi.mock('../../src/lib/charts/export', async (importActual) => ({
  ...(await importActual<typeof import('../../src/lib/charts/export')>()),
  writePng,
}));

import { BACKGROUNDS, PREVIEWS, Switch } from '../../src/components/charts/ChartSwitch';
import CompareChartPanel from '../../src/components/charts/CompareChartPanel';
import CompareCharts from '../../src/components/charts/CompareCharts';
import { chartsFor } from '../../src/lib/charts/compare-charts';
import {
  A,
  B,
  attemptCell,
  entries,
  header,
  metricOf,
  payloadOf,
  roleCell,
  runValueMetric,
} from './compare-chart-fixtures';
import type { CompareOut } from './metrics-compare-fixtures';

const ids = [A, B];
const run = (id: string, v: string[]) => runValueMetric(id, ids, v);

const base = payloadOf([
  run('cost.gateway', ['1.5', '2.5']),
  run('cost.harness', ['1.6', '2.4']),
  run('tokens.output', ['10', '20']),
  run('tokens.cache_read', ['5', '6']),
]);
const named: CompareOut = {
  ...base,
  runs: [
    header(A, { label: 'familio snake-v2 opus' }),
    header(B, { label: 'familio snake-v2 sonnet' }),
  ],
};

const mount = (payload = named, set: 'headline' | 'all' = 'headline', stepOrder: string[] = []) =>
  render(createElement(CompareCharts, { payload, entries: entries(), set, stepOrder }));

beforeEach(() => writePng.mockReset().mockResolvedValue(undefined));
afterEach(cleanup);

describe('CompareCharts · TOTAL', () => {
  it('draws the cost dot plot first, ticks off zero, and bars from zero elsewhere', () => {
    mount();
    const figures = screen.getAllByRole('figure');
    expect(figures[0].getAttribute('aria-label')).toBe('cost · gateway and harness');
    const filled = figures[0].querySelectorAll('circle[data-series="gateway"]');
    const open = figures[0].querySelectorAll('circle[data-series="harness"]');
    expect(filled).toHaveLength(2);
    expect(open).toHaveLength(2);
    expect(filled[0].getAttribute('fill')).toBe('var(--color-chart-data-1)');
    expect(open[0].getAttribute('stroke')).toBe('var(--color-chart-data-2)');
    expect(within(figures[0]).getAllByTestId('chart-context').at(-1)!.textContent).toBe(
      'US dollars · axis does not start at zero',
    );
    expect(figures[0].textContent).toContain('$1.50 · $1.60');
    const first = (fig: HTMLElement) => fig.querySelector('svg > g text')!.textContent;
    expect(first(figures[0])).not.toBe('0');
    expect(first(figures[1])).toBe('0');
    expect(figures[1].querySelector('rect')!.getAttribute('x')).toBe('230');
  });

  it('prints shared words once and wraps the row names with the short id', () => {
    mount();
    const fig = screen.getAllByRole('figure')[0];
    expect(within(fig).getByTestId('chart-shared-words').textContent).toBe('familio snake-v2');
    expect(fig.textContent).toContain('opus');
    expect(fig.textContent).toContain(A.slice(0, 8));
    expect(screen.queryByTestId('compare-not-split')).toBeNull();
  });

  it('follows a Run across every chart, announces it and clears on a second click', () => {
    mount();
    const names = screen.getAllByTestId(`chart-run-${A}`);
    expect(names.length).toBeGreaterThan(1);
    fireEvent.click(names[0]);
    for (const n of screen.getAllByTestId(`chart-run-${A}`)) {
      expect(n.getAttribute('aria-pressed')).toBe('true');
      expect(n.getAttribute('class')).toContain('is-followed');
    }
    expect(screen.getByTestId('compare-following').textContent).toBe(
      'following: familio snake-v2 opus · click again to stop',
    );
    expect(document.querySelectorAll('[data-follow]').length).toBeGreaterThan(2);
    for (const n of screen.getAllByTestId(`chart-run-${B}`)) {
      expect(n.getAttribute('aria-pressed')).toBe('false');
    }
    fireEvent.keyDown(screen.getAllByTestId(`chart-run-${A}`)[0], { key: 'Enter' });
    expect(document.querySelectorAll('[data-follow]')).toHaveLength(0);
    expect(screen.getByTestId('compare-following').textContent).toBe('');
    fireEvent.keyDown(screen.getAllByTestId(`chart-run-${A}`)[0], { key: 'x' });
    expect(screen.getByTestId('compare-following').textContent).toBe('');
  });

  it('writes a PNG per chart without follow state and one per chart for all', async () => {
    mount();
    fireEvent.click(screen.getAllByTestId(`chart-run-${A}`)[0]);
    fireEvent.click(screen.getByLabelText('PNG output tokens'));
    expect(writePng).toHaveBeenCalledTimes(1);
    const [svg, file] = writePng.mock.calls[0];
    expect(file).toBe(`proj-compare-output-tokens-${new Date().toISOString().slice(0, 10)}.png`);
    expect(svg).not.toContain('data-follow');
    expect(svg).not.toContain('following:');
    expect(svg).not.toContain('--color-accent');
    fireEvent.click(screen.getByTestId('compare-png-all'));
    await vi.waitFor(() => expect(writePng).toHaveBeenCalledTimes(1 + 3));
  });

  it('reports a failed write and stops the loop', async () => {
    writePng.mockRejectedValueOnce(new Error('boom'));
    mount();
    fireEvent.click(screen.getByTestId('compare-png-all'));
    expect((await screen.findByTestId('compare-png-failed')).textContent).toBe(
      'PNG not written · boom',
    );
    expect(writePng).toHaveBeenCalledTimes(1);
    writePng.mockRejectedValueOnce('plain');
    fireEvent.click(screen.getByLabelText('PNG output tokens'));
    expect((await screen.findByText('PNG not written · plain')).tagName).toBe('P');
  });

  it('previews the PNG ink in place of the chart', () => {
    mount();
    fireEvent.click(screen.getByText('DARK PAGE'));
    expect(document.querySelectorAll('img.chart-preview').length).toBeGreaterThan(1);
    fireEvent.click(screen.getByText('DARK'));
    fireEvent.click(screen.getByText('SCREEN'));
    expect(document.querySelectorAll('img.chart-preview')).toHaveLength(0);
  });

  it('scrolls only past 15 Runs', () => {
    const many = (n: number): CompareOut => {
      const rid = Array.from(
        { length: n },
        (_, i) => `${String(i).padStart(8, '0')}-0000-7000-8000-000000000001`,
      );
      return payloadOf(
        [
          runValueMetric(
            'tokens.output',
            rid,
            rid.map(() => '1'),
          ),
        ],
        rid,
      );
    };
    mount(many(16));
    expect(document.querySelectorAll('.compare-chart-scroll')).toHaveLength(1);
    cleanup();
    mount(many(15));
    expect(document.querySelectorAll('.compare-chart-scroll')).toHaveLength(0);
  });
});

describe('CompareCharts · breakdowns', () => {
  const roles = payloadOf([
    metricOf('tokens.output', {
      [A]: [
        roleCell('plan', '3'),
        roleCell('implement', '4'),
        roleCell('review', '5'),
        attemptCell('plan', 's1', 1),
        attemptCell('implement', 's2', 1),
        attemptCell('review', 's3', 1),
      ],
      [B]: [roleCell('plan', '3'), roleCell('implement', '4')],
    }),
  ]);

  it('groups by role in plan order, leaves the missing role without a mark and says what is not split', () => {
    mount(roles, 'headline', ['s1', 's2', 's3']);
    fireEvent.click(screen.getByTestId('compare-breakdown-role'));
    expect(screen.getByTestId('compare-roles-declared').getAttribute('aria-pressed')).toBe('true');
    const fig = screen.getByRole('figure');
    expect(fig.getAttribute('aria-label')).toBe('output tokens by role');
    expect(
      ['plan', 'implement', 'review'].map(
        (r) => within(fig).getByTestId(`chart-group-${r}`).textContent,
      ),
    ).toEqual(['plan', 'implement', 'review']);
    expect(within(fig).getByTestId('chart-run-key').textContent).toContain(
      `R1 · label a · ${A.slice(0, 8)}`,
    );
    expect(fig.textContent).toContain('no such step in this template');
    expect(fig.querySelectorAll('rect[fill]').length).toBe(5);
    expect(screen.getByTestId('compare-not-split').textContent).toContain('not split by role');
    expect(screen.queryByText(/machine time/, { selector: '[role=figure] *' })).toBeNull();
    fireEvent.click(screen.getByTestId('compare-breakdown-total'));
    expect(screen.queryByTestId('compare-not-split')).toBeNull();
  });

  it('shows the family flag only when a structure differs', () => {
    const fam = (differs: boolean) =>
      payloadOf([
        metricOf(
          'tokens.output',
          {},
          {
            families: [
              {
                family: 'story work',
                source: null,
                step_structure_differs: differs,
                cells: {
                  [A]: { value_num: '10', missing: null, roles: ['plan', 'implement', 'review'] },
                  [B]: { value_num: '12', missing: null, roles: ['orchestrate'] },
                },
              },
            ],
          },
        ),
      ]);
    mount(fam(true));
    fireEvent.click(screen.getByTestId('compare-breakdown-role'));
    fireEvent.click(screen.getByTestId('compare-roles-family'));
    expect(screen.getByTestId('chart-flag').textContent).toBe(
      '≠ step structure differs · story work: R1 plan · implement · review; R2 orchestrate',
    );
    cleanup();
    mount(fam(false));
    fireEvent.click(screen.getByTestId('compare-breakdown-role'));
    fireEvent.click(screen.getByTestId('compare-roles-family'));
    expect(screen.queryByTestId('chart-flag')).toBeNull();
  });

  it('draws model charts on MODEL', () => {
    const model = payloadOf([
      metricOf('tokens.output', {
        [A]: [{ ...roleCell('x', '3'), scope_type: 'model', scope_key: 'm1' }],
        [B]: [],
      }),
    ]);
    mount(model);
    fireEvent.click(screen.getByTestId('compare-breakdown-model'));
    expect(screen.getByRole('figure').getAttribute('aria-label')).toBe('output tokens by model');
    expect(screen.getByTestId('chart-group-m1')).toBeTruthy();
  });
});

describe('CompareChartPanel', () => {
  it('draws one chart and reports a PNG request and a Run click', () => {
    const chart = chartsFor(named, entries(), {
      breakdown: 'total',
      roles: 'declared',
      set: 'headline',
      stepOrder: [],
    })[2];
    const onPng = vi.fn();
    const onFollow = vi.fn();
    const meta = { entries: entries(), project: 'Proj', headers: named.runs, date: '2026-11-13' };
    render(
      createElement(CompareChartPanel, {
        chart,
        headers: named.runs,
        followed: null,
        onFollow,
        onPng,
        preview: 'screen',
        meta,
      }),
    );
    fireEvent.click(screen.getByLabelText(`PNG ${chart.title}`));
    expect(onPng).toHaveBeenCalledWith(chart);
    fireEvent.keyDown(screen.getByTestId(`chart-run-${B}`), { key: ' ' });
    expect(onFollow).toHaveBeenCalledWith(B);
  });
});

describe('ChartSwitch', () => {
  it('lists the backgrounds and previews', () => {
    expect(BACKGROUNDS.map(([k]) => k)).toEqual(['transparent', 'light', 'dark']);
    expect(PREVIEWS.map(([k]) => k)).toEqual(['screen', 'dark', 'light']);
    expect(typeof Switch).toBe('function');
  });
});
