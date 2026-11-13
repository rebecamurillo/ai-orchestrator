// @vitest-environment jsdom
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET, exportComparison } = vi.hoisted(() => ({ GET: vi.fn(), exportComparison: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));
vi.mock('../../src/lib/metrics/compare-export', () => ({ exportComparison }));

import MetricsCompare from '../../src/islands/MetricsCompare';
import type { CompareState } from '../../src/lib/metrics/compare';
import { resetCatalogue } from '../../src/stores/catalogue';
import { entry } from './metrics-fixtures';
import { A, B, C, comparePayload, header } from './metrics-compare-fixtures';

const initial = (over: Partial<CompareState> = {}): CompareState => ({
  runIds: [A, B, C],
  versions: {},
  view: 'table',
  set: 'headline',
  blind: false,
  ...over,
});

function plan(compare: (query: Record<string, unknown>) => unknown) {
  GET.mockImplementation(
    (path: string, init?: { params?: { query?: Record<string, unknown> } }) => {
      if (path === '/metrics/catalogue') {
        return Promise.resolve({
          data: {
            items: [
              entry('cost.gateway', { level: 'H' }),
              entry('tokens.input', { group: 'tokens', level: 'A' }),
            ],
            next_cursor: null,
          },
        });
      }
      return Promise.resolve(compare(init?.params?.query ?? {}));
    },
  );
}
const okFor = (query: Record<string, unknown>) => {
  const ids = String(query.runs).split(',');
  const payload = comparePayload(ids);
  if (query.blind) payload.runs = ids.map((id, i) => header(id, { label: `R${i + 1}` }));
  return { data: payload, response: { status: 200 } };
};
const compareCalls = () => GET.mock.calls.filter((c) => c[0] === '/metrics/compare');
const mount = (state = initial()) => render(createElement(MetricsCompare, { initial: state }));

beforeEach(() => window.history.replaceState(null, '', `/metrics/compare?runs=${A},${B},${C}`));
afterEach(() => {
  cleanup();
  resetCatalogue();
  GET.mockReset();
  exportComparison.mockReset();
});

describe('MetricsCompare', () => {
  it('requests the runs in order with no blind and no v, one column each', async () => {
    plan(okFor);
    mount();
    await screen.findByTestId('compare-grid');
    expect(compareCalls()).toHaveLength(1);
    expect(compareCalls()[0][1].params.query).toEqual({ runs: `${A},${B},${C}` });
    expect(screen.getByTestId(`compare-col-${C}`)).toBeTruthy();
  });

  it('removes a Run: re-requests, shows two columns, rewrites the URL', async () => {
    plan(okFor);
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId(`compare-remove-${B}`));
    await waitFor(() => expect(compareCalls()).toHaveLength(2));
    expect(compareCalls()[1][1].params.query).toEqual({ runs: `${A},${C}` });
    await waitFor(() => expect(screen.queryByTestId(`compare-col-${B}`)).toBeNull());
    expect(window.location.search).toBe(`?runs=${A},${C}`);
    expect((screen.getByTestId(`compare-remove-${A}`) as HTMLButtonElement).disabled).toBe(true);
  });

  it('blind re-requests with blind=true, shows the payload labels, and switches off again', async () => {
    plan(okFor);
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId('compare-blind'));
    await waitFor(() => expect(compareCalls()).toHaveLength(2));
    expect(compareCalls()[1][1].params.query).toEqual({ runs: `${A},${B},${C}`, blind: true });
    expect(window.location.search).toContain('blind=1');
    await waitFor(() => expect(screen.getByTestId(`compare-col-${A}`).textContent).toContain('R1'));
    fireEvent.click(screen.getByTestId('compare-blind'));
    await waitFor(() => expect(compareCalls()).toHaveLength(3));
    expect(compareCalls()[2][1].params.query).toEqual({ runs: `${A},${B},${C}` });
    expect(window.location.search).not.toContain('blind');
  });

  it('a set change makes no request and writes metrics=all', async () => {
    plan(okFor);
    mount();
    await screen.findByTestId('compare-grid');
    expect(screen.queryByTestId('compare-row-tokens.input')).toBeNull();
    fireEvent.click(screen.getByTestId('compare-set-all'));
    expect(window.location.search).toContain('metrics=all');
    expect(compareCalls()).toHaveLength(1);
    expect(screen.getByTestId('compare-row-tokens.input')).toBeTruthy();
    fireEvent.click(screen.getByTestId('compare-set-headline'));
    expect(window.location.search).not.toContain('metrics');
  });

  it('a version segment re-requests with v and the latest drops it again', async () => {
    plan(okFor);
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId(`compare-version-${A}-1`));
    await waitFor(() => expect(compareCalls()).toHaveLength(2));
    expect(compareCalls()[1][1].params.query).toEqual({ runs: `${A},${B},${C}`, v: `${A}:1` });
    expect(window.location.search).toContain(`v=${A}:1`);
    fireEvent.click(screen.getByTestId(`compare-version-${A}-2`));
    await waitFor(() => expect(compareCalls()).toHaveLength(3));
    expect(compareCalls()[2][1].params.query).toEqual({ runs: `${A},${B},${C}` });
    expect(window.location.search).not.toContain('v=');
  });

  it('ignores a response superseded by a newer request', async () => {
    let release: (v: unknown) => void = () => {};
    let n = 0;
    plan((query) => {
      n += 1;
      if (n === 2) return new Promise((resolve) => (release = resolve));
      return okFor(query);
    });
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId('compare-blind'));
    await waitFor(() => expect(compareCalls()).toHaveLength(2));
    fireEvent.click(screen.getByTestId('compare-blind'));
    await waitFor(() => expect(compareCalls()).toHaveLength(3));
    await screen.findByTestId('compare-grid');
    await act(async () => release(okFor({ runs: `${A},${B},${C}`, blind: true })));
    expect(screen.getByTestId(`compare-col-${A}`).textContent).not.toContain('R1');
  });

  it('shows the failed readout with a retry that re-reads', async () => {
    let fail = true;
    plan((query) => (fail ? { error: {}, response: { status: 422 } } : okFor(query)));
    mount();
    const readout = await screen.findByTestId('compare-failed');
    expect(readout.textContent).toContain('GET /api/metrics/compare');
    expect(readout.textContent).toContain('422');
    expect(screen.queryByTestId('compare-grid')).toBeNull();
    fail = false;
    fireEvent.click(screen.getByTestId('compare-retry'));
    await screen.findByTestId('compare-grid');
    expect(compareCalls()).toHaveLength(2);
  });

  it('keeps the bar over a failed re-request so the change can be undone', async () => {
    plan((query) => (query.blind ? { error: {}, response: { status: 500 } } : okFor(query)));
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId('compare-blind'));
    await screen.findByTestId('compare-failed');
    expect(screen.queryByTestId('compare-grid')).toBeNull();
    fireEvent.click(screen.getByTestId('compare-blind'));
    await screen.findByTestId('compare-grid');
    expect(window.location.search).not.toContain('blind');
  });

  it('shows the readout for a rejected read', async () => {
    GET.mockImplementation((path: string) =>
      path === '/metrics/catalogue'
        ? Promise.resolve({ data: { items: [] } })
        : Promise.reject(new Error('net')),
    );
    mount();
    await screen.findByTestId('compare-failed');
  });

  it('with fewer than two Runs makes no request and says so', async () => {
    plan(okFor);
    mount(initial({ runIds: [A] }));
    const line = await screen.findByTestId('compare-too-few');
    expect(line.textContent).toContain('select at least two Runs of one project in Metrics');
    expect(line.querySelector('a')?.getAttribute('href')).toBe('/metrics');
    expect(compareCalls()).toHaveLength(0);
  });

  it('exports through exportComparison and prints its line, hidden when it failed too', async () => {
    plan(okFor);
    exportComparison.mockResolvedValueOnce({ ok: true, line: 'exported done' });
    mount();
    await screen.findByTestId('compare-grid');
    fireEvent.click(screen.getByTestId('compare-export'));
    await waitFor(() =>
      expect(screen.getByTestId('compare-export-line').textContent).toBe('exported done'),
    );
    expect(exportComparison.mock.calls[0][0].runIds).toEqual([A, B, C]);
    expect(exportComparison.mock.calls[0][1]).toBe('Proj');
    exportComparison.mockResolvedValueOnce({ ok: false, line: 'export failed · GET x · 500' });
    fireEvent.click(screen.getByTestId('compare-export'));
    await waitFor(() =>
      expect(screen.getByTestId('compare-export-line').textContent).toBe(
        'export failed · GET x · 500',
      ),
    );
  });
});
