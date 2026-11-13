// @vitest-environment jsdom
/** `CostBlock` with the metric glance (epic 3 story 3, AC3, AC5-AC7). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CostBlock from '../../src/components/run/CostBlock';
import CostGlance from '../../src/components/run/CostGlance';
import type { RunDetailOut } from '../../src/lib/run/detail';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import type { RunMetricsState } from '../../src/stores/run-metrics';
import { entry, value, version } from './metrics-fixtures';

const IDS = [
  'cost.gateway',
  'cost.harness',
  'cost.figure_gap',
  'cost.retries',
  'process.retries',
  'time.retries',
  'time.parked',
  'budget.used',
];

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: Object.fromEntries(IDS.map((id) => [id, entry(id)])),
  });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
});

function detail(status = 'done'): RunDetailOut {
  return {
    run: {
      id: '1',
      status,
      branch: 'chore/x',
      label: 'my run',
      compare_urls: [],
      project: 'p1',
    },
    header: { meta: { project: 'familio' } },
    cost: {
      spent_usd: '16.01',
      budget_usd: '100.00',
      tokens_in: 1,
      tokens_out: 2,
      wall_clock_seconds: 60,
      active_seconds: 30,
      provisional: false,
      trace_url: null,
    },
  } as unknown as RunDetailOut;
}

const v = (metric_id: string, num: string | null, over = {}) =>
  value({
    metric_id,
    value_num: num,
    unit: metric_id.startsWith('time')
      ? 'seconds'
      : metric_id.startsWith('process')
        ? 'count'
        : 'USD',
    ...over,
  });

function state(over: Partial<RunMetricsState> = {}): RunMetricsState {
  return {
    runId: '1',
    status: 'ready',
    failed: null,
    metrics: {
      items: [
        v('cost.gateway', '15.35'),
        v('cost.harness', '16.01'),
        v('process.retries', '2', { source: 'gateway' }),
        v('process.retries', '1', { source: 'harness' }),
        v('cost.retries', '1.20', { source: 'gateway' }),
        v('cost.retries', '0.50', { source: 'harness' }),
        v('time.retries', '720'),
        v('time.parked', '6000'),
      ],
      latest: 3,
      run_id: '1',
      values_so_far: false,
      version: 3,
    },
    versions: [version(1), version(2), version(3)],
    selected: null,
    calc: null,
    calcError: null,
    ...over,
  };
}

const withItems = (items: ReturnType<typeof v>[], extra: Partial<RunMetricsState> = {}) => {
  const s = state(extra);
  return { ...s, metrics: { ...s.metrics!, ...(extra.metrics ?? {}), items } };
};

const mount = (glance: RunMetricsState | undefined, d = detail(), extra = {}) =>
  render(createElement(CostBlock, { detail: d, glance, ...extra } as never));
const text = () => screen.getByTestId('wf-cost').textContent!;

describe('the figure pair and the card', () => {
  it('shows GATEWAY then HARNESS and the differ card at cent precision', () => {
    const { container } = mount(state());
    const heads = Array.from(container.querySelectorAll('.metric-figure-head'));
    expect(heads.map((h) => h.textContent!.replace('i', '').trim())).toEqual([
      'GATEWAY',
      'HARNESS',
    ]);
    expect(container.querySelectorAll('.metric-value-cell').length).toBeGreaterThanOrEqual(2);
    const card = screen.getByTestId('wf-figures-differ').textContent!;
    expect(card).toContain('FIGURES DIFFER');
    expect(card).toContain('gateway $15.35 · harness $16.01 · harness is $0.66 higher (4.3 %)');
    expect(card).toContain('the budget gate uses the higher figure');
    expect(card).toContain('how cost.figure_gap v2');
  });

  it('shows no card for equal figures, cents-equal figures or a missing figure', () => {
    for (const [g, h] of [
      ['15.35', '15.35'],
      ['15.351', '15.349'],
      ['15.35', null],
    ] as const) {
      const base = state();
      mount(
        withItems([v('cost.gateway', g), v('cost.harness', h, { missing: 'not recorded' })], {
          metrics: base.metrics,
        }),
      );
      expect(screen.queryByTestId('wf-figures-differ')).toBeNull();
      cleanup();
    }
  });

  it('uses the figure_gap value method when a value carries one', () => {
    const s = withItems([
      v('cost.gateway', '15.35'),
      v('cost.harness', '16.01'),
      v('cost.figure_gap', '0.66', { method_id: 'cost.figure_gap@1' }),
    ]);
    mount(s);
    expect(screen.getByTestId('wf-figures-differ').textContent).toContain('how cost.figure_gap v1');
  });

  it('drops the reason when the catalogue has no figure_gap entry', () => {
    const entries = { ...$catalogue.get().entries };
    delete entries['cost.figure_gap'];
    $catalogue.set({ status: 'ready', entries });
    mount(state());
    expect(screen.getByTestId('wf-figures-differ').textContent).not.toContain('how cost');
  });
});

describe('the glance rows', () => {
  it('reads budget used, retries and waiting on you', () => {
    mount(state());
    expect(text()).toContain('budget used');
    expect(text()).toContain('$16.01 / $100.00');
    expect(text()).toContain('retries 3 · of which $1.20 gateway · $0.50 harness · 0h 12m');
    expect(text()).toContain('waiting on you');
    expect(text()).toContain('1h 40m');
  });

  it('prints a missing word, never 0', () => {
    mount(
      withItems([
        v('process.retries', null, { missing: 'not recorded' }),
        v('time.parked', null, { missing: 'not recorded' }),
      ]),
    );
    expect(text()).toContain('retries not recorded');
    expect(text()).toContain('waiting on you');
    expect(text()).not.toMatch(/retries 0|waiting on you\s*0/);
  });

  it('prints not available for a value the read did not return', () => {
    mount(withItems([]));
    expect(text()).toContain('retries not available');
    expect(text()).toContain('waiting on you not available');
  });

  it('states which version is shown when an older one is selected', () => {
    mount(state({ selected: 1 }));
    expect(text()).toContain('showing v1 of 3 · latest is v3');
    cleanup();
    mount(state());
    expect(text()).not.toContain('showing v');
  });

  it('keeps the existing rows', () => {
    mount(state());
    expect(text()).toContain('100 in / 200 out'.replace('100', '1').replace('200', '2'));
    expect(text()).toContain('00:00:30');
  });
});

describe('the version selector', () => {
  it('lists the versions and reports a selection', () => {
    const onSelectVersion = vi.fn();
    mount(state(), detail(), { onSelectVersion });
    expect(screen.getByRole('button', { name: 'v3 latest' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'v1' }));
    expect(onSelectVersion).toHaveBeenCalledWith(1);
  });

  it('after a failed calculation shows no new version', () => {
    const failed = state({
      calc: {
        ended_at: null,
        entry_point: ['manual'],
        id: 'c',
        output: 'boom',
        queued_at: '2026-11-19T14:02:05Z',
        run_id: '1',
        started_at: null,
        state: 'failed',
        target_n: 4,
      },
    });
    mount(failed);
    expect(screen.queryByRole('button', { name: /^v4/ })).toBeNull();
  });
});

describe('the state rows (EXPERIENCE §6)', () => {
  it('queued: the budget row only, no figure pair', () => {
    mount(state({ metrics: null, versions: [] }), detail('queued'));
    expect(text()).toContain('budget used');
    expect(document.querySelector('.metric-figure-pair')).toBeNull();
    expect(text()).not.toContain('retries');
    expect(screen.queryByTestId('wf-figures-differ')).toBeNull();
  });

  it('running: the values so far, with the word running after each total', () => {
    const s = state();
    mount({ ...s, metrics: { ...s.metrics!, values_so_far: true } }, detail('running'));
    expect(document.querySelectorAll('.wf-glance-running')).toHaveLength(2);
    expect(text()).toContain('running');
  });

  it('ended without a version: no result version and no selector', () => {
    mount(
      state({
        metrics: { items: [], latest: null, run_id: '1', values_so_far: false, version: null },
        versions: [],
      }),
    );
    expect(text()).toContain('no result version');
    expect(document.querySelector('.metric-version')).toBeNull();
    expect(document.querySelector('.metric-figure-pair')).toBeNull();
    expect(text()).toContain('$16.01 / $100.00');
  });

  it('carried: a carried value says from v{n}', () => {
    mount(withItems([v('cost.gateway', '15.35', { carried_from: 2 }), v('cost.harness', '15.35')]));
    expect(text()).toContain('from v2');
  });

  it('a failed read shows the readout inside the block and keeps the rows', () => {
    mount(state({ status: 'failed', failed: { path: '/api/runs/1/metrics', status: 500 } }));
    expect(screen.getByTestId('fetch-failed').textContent).toContain('/api/runs/1/metrics');
    expect(text()).toContain('$16.01 / $100.00');
  });

  it('an idle store renders the existing rows only', () => {
    mount(state({ status: 'idle', metrics: null, versions: [] }));
    expect(text()).toContain('$16.01 / $100.00');
    expect(document.querySelector('.metric-figure-pair')).toBeNull();
  });
});

describe('CostGlance on its own', () => {
  it('renders nothing before the first metrics read', () => {
    const { container } = render(
      createElement(CostGlance, {
        detail: detail(),
        glance: state({ metrics: null }),
        subscription: false,
      }),
    );
    expect(container.innerHTML).toBe('');
  });

  it('says list-price equivalent once on a subscription Run', () => {
    render(createElement(CostGlance, { detail: detail(), glance: state(), subscription: true }));
    expect(document.body.textContent!.match(/list-price equivalent/g)).toHaveLength(1);
  });
});
