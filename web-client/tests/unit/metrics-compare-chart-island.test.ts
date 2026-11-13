// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));
vi.mock('../../src/lib/metrics/compare-export', () => ({ exportComparison: vi.fn() }));

import MetricsCompare from '../../src/islands/MetricsCompare';
import type { CompareState } from '../../src/lib/metrics/compare';
import { resetCatalogue } from '../../src/stores/catalogue';
import { entries } from './compare-chart-fixtures';
import { A, B, attemptCell, metricOf, payloadOf, roleCell } from './compare-chart-fixtures';
import { comparePayload } from './metrics-compare-fixtures';

const initial = (over: Partial<CompareState> = {}): CompareState => ({
  runIds: [A, B],
  versions: {},
  view: 'chart',
  set: 'headline',
  blind: false,
  ...over,
});

const payload = payloadOf([
  metricOf('tokens.output', {
    [A]: [
      roleCell('plan', '1'),
      roleCell('implement', '2'),
      attemptCell('plan', 'b.0', 1),
      attemptCell('implement', 'a.0', 1),
    ],
    [B]: [roleCell('plan', '3'), roleCell('implement', '4')],
  }),
]);

function plan(detail: () => unknown) {
  GET.mockImplementation((path: string) => {
    if (path === '/metrics/catalogue') {
      return Promise.resolve({ data: { items: Object.values(entries()), next_cursor: null } });
    }
    if (path === '/runs/{run_id}/detail') return Promise.resolve(detail());
    return Promise.resolve({ data: payload, response: { status: 200 } });
  });
}
const calls = (path: string) => GET.mock.calls.filter((c) => c[0] === path);
const mount = (state = initial()) => render(createElement(MetricsCompare, { initial: state }));
const groups = () =>
  screen.getAllByTestId(/^chart-group-/).map((e) => e.getAttribute('data-testid'));

beforeEach(() =>
  window.history.replaceState(null, '', `/metrics/compare?runs=${A},${B}&view=chart`),
);
afterEach(() => {
  cleanup();
  resetCatalogue();
  GET.mockReset();
});

describe('MetricsCompare · chart view', () => {
  it('draws the charts from one compare request and reads the first Run detail once', async () => {
    plan(() => ({
      data: {
        steps: [
          { path: 'a.0', seq: 2 },
          { path: 'b.0', seq: 1 },
        ],
      },
    }));
    mount();
    await screen.findByTestId('compare-charts');
    await waitFor(() => expect(calls('/runs/{run_id}/detail')).toHaveLength(1));
    expect(calls('/runs/{run_id}/detail')[0][1]).toEqual({ params: { path: { run_id: A } } });
    expect(calls('/metrics/compare')).toHaveLength(1);
    expect(screen.queryByTestId('compare-grid')).toBeNull();
    expect(screen.getByTestId('compare-view-chart').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('compare-breakdown-role'));
    await waitFor(() => expect(groups()).toEqual(['chart-group-plan', 'chart-group-implement']));
  });

  it('orders roles by the detail steps by seq', async () => {
    plan(() => ({
      data: {
        steps: [
          { path: 'a.0', seq: 1 },
          { path: 'b.0', seq: 2 },
        ],
      },
    }));
    mount();
    await screen.findByTestId('compare-charts');
    await waitFor(() => expect(calls('/runs/{run_id}/detail')).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 0));
    fireEvent.click(screen.getByTestId('compare-breakdown-role'));
    await waitFor(() => expect(groups()).toEqual(['chart-group-implement', 'chart-group-plan']));
  });

  it('switches TABLE and CHART without a new compare request and writes view=chart', async () => {
    plan(() => ({ data: { steps: [] } }));
    mount(initial({ view: 'table' }));
    await screen.findByTestId('compare-grid');
    expect(calls('/runs/{run_id}/detail')).toHaveLength(0);
    fireEvent.click(screen.getByTestId('compare-view-chart'));
    await screen.findByTestId('compare-charts');
    expect(window.location.search).toContain('view=chart');
    fireEvent.click(screen.getByTestId('compare-view-table'));
    await screen.findByTestId('compare-grid');
    expect(window.location.search).not.toContain('view=chart');
    expect(calls('/metrics/compare')).toHaveLength(1);
    await waitFor(() => expect(calls('/runs/{run_id}/detail')).toHaveLength(1));
  });

  it('still draws the charts when the detail read fails or throws', async () => {
    plan(() => ({ error: { status: 500 }, response: { status: 500 } }));
    mount();
    await screen.findByTestId('compare-charts');
    await waitFor(() => expect(calls('/runs/{run_id}/detail')).toHaveLength(1));
    cleanup();
    GET.mockReset();
    plan(() => {
      throw new Error('network');
    });
    mount();
    await screen.findByTestId('compare-charts');
    expect(screen.getAllByRole('figure').length).toBeGreaterThan(0);
    expect(comparePayload).toBeTypeOf('function');
  });
});
