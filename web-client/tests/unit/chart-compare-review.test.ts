// @vitest-environment jsdom
// Story 4 review (2026-11-13): a dot row with one cost missing prints both facts; a dotted bar's
// methods suffix reads on screen as in the PNG; a compare re-read does not re-read the detail.
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));
vi.mock('../../src/lib/metrics/compare-export', () => ({ exportComparison: vi.fn() }));

import CompareCharts from '../../src/components/charts/CompareCharts';
import MetricsCompare from '../../src/islands/MetricsCompare';
import { totalCharts } from '../../src/lib/charts/compare-charts';
import { compareSvg, dotWords, drawn } from '../../src/lib/charts/compare-png';
import { resetCatalogue } from '../../src/stores/catalogue';
import {
  A,
  B,
  entries,
  header,
  metricOf,
  payloadOf,
  roleCell,
  runValueMetric,
} from './compare-chart-fixtures';

const ids = [A, B];
const run = (id: string, v: string[], over = {}) => runValueMetric(id, ids, v, over);

function harnessMissingForB() {
  const harness = run('cost.harness', ['1.6', '0']);
  harness.cells[B] = [{ ...harness.cells[B][0], value_num: null, missing: 'not recorded' }];
  return payloadOf([run('cost.gateway', ['1.5', '1.2']), harness]);
}

afterEach(() => {
  cleanup();
  resetCatalogue();
  GET.mockReset();
});

describe('dot row with one cost missing', () => {
  it('prints the present figure and the missing word, in the PNG and on screen', () => {
    const [chart] = totalCharts(harnessMissingForB(), entries(), 'headline');
    const [, rowB] = chart.groups[0].rows;
    expect(dotWords(rowB.marks[0], rowB.marks[1])).toBe('$1.20 · not recorded');
    expect(dotWords({ value: null, word: 'x' }, undefined)).toBe('x · —');
    const svg = compareSvg(chart, {
      entries: entries(),
      project: 'P',
      headers: [header(A), header(B)],
      date: '2026-11-13',
    });
    expect(svg).toContain('$1.20 · not recorded');
    render(
      createElement(CompareCharts, {
        payload: harnessMissingForB(),
        entries: entries(),
        set: 'headline',
        stepOrder: [],
      }),
    );
    expect(screen.getAllByText('$1.20 · not recorded').length).toBeGreaterThan(0);
  });
});

describe('dotted bar of another method', () => {
  it('ends its value label with the methods, on screen as in the model', () => {
    const out = run('tokens.output', ['10', '20'], {
      methods_differ: true,
      methods: { [A]: ['m1'], [B]: ['m2', 'm3'] },
    });
    const [chart] = totalCharts(payloadOf([out]), entries(), 'headline');
    const markB = chart.groups[0].rows[1].marks[0];
    expect(drawn(markB, 20, 100)?.label).toMatch(/ · m2, m3$/);
    expect(drawn(chart.groups[0].rows[0].marks[0], 20, 100)?.label).not.toContain('m1');
    render(
      createElement(CompareCharts, {
        payload: payloadOf([out]),
        entries: entries(),
        set: 'headline',
        stepOrder: [],
      }),
    );
    expect(screen.getByText(/ · m2, m3$/)).toBeTruthy();
  });
});

describe('MetricsCompare · detail read across compare re-reads', () => {
  it('reads the first Run detail once when blind re-requests the comparison', async () => {
    const payload = payloadOf([
      metricOf('tokens.output', {
        [A]: [roleCell('plan', '1')],
        [B]: [roleCell('plan', '3')],
      }),
    ]);
    GET.mockImplementation((path: string) => {
      if (path === '/metrics/catalogue') {
        return Promise.resolve({ data: { items: Object.values(entries()), next_cursor: null } });
      }
      if (path === '/runs/{run_id}/detail') {
        return Promise.resolve({ data: { steps: [{ path: 'a.0', seq: 1 }] } });
      }
      return Promise.resolve({ data: payload, response: { status: 200 } });
    });
    window.history.replaceState(null, '', `/metrics/compare?runs=${A},${B}&view=chart`);
    render(
      createElement(MetricsCompare, {
        initial: { runIds: ids, versions: {}, view: 'chart', set: 'headline', blind: false },
      }),
    );
    await screen.findByTestId('compare-charts');
    const calls = (path: string) => GET.mock.calls.filter((c) => c[0] === path);
    await waitFor(() => expect(calls('/runs/{run_id}/detail')).toHaveLength(1));
    fireEvent.click(screen.getByTestId('compare-blind'));
    await waitFor(() => expect(calls('/metrics/compare')).toHaveLength(2));
    await screen.findByTestId('compare-charts');
    expect(calls('/runs/{run_id}/detail')).toHaveLength(1);
  });
});
