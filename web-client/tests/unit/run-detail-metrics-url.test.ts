// @vitest-environment jsdom
/**
 * The Run page's METRICS default and URL state (story 3-4, AC1 and AC4), through the mounted
 * island: the default tab, `?v=` read on load, the URL left alone until the Operator changes
 * something, and a `?v=` naming the latest or a missing version settling on "follow latest".
 */
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { GET, POST } = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, POST } }));

import RunDetail from '../../src/islands/RunDetail';
import { $runMetrics, resetRunMetrics } from '../../src/stores/run-metrics';
import { stopPolling } from '../../src/stores/poll';
import { resetCatalogue } from '../../src/stores/catalogue';
import { RUN_ID, runDetail } from '../fixtures/run-detail';
import { version } from './metrics-fixtures';

type RunStatus = NonNullable<NonNullable<Parameters<typeof runDetail>[1]>['run']>['status'];

function serve(status: RunStatus, versions: number[]): void {
  GET.mockImplementation((path: string, init?: { params?: { query?: { v?: number } } }) => {
    if (path === '/runs/{run_id}/detail') {
      return Promise.resolve({ data: runDetail([], { run: { status } }), response: {} });
    }
    if (path === '/runs/{run_id}/metrics/versions') {
      return Promise.resolve({ data: { items: versions.map((n) => version(n)) }, response: {} });
    }
    if (path === '/runs/{run_id}/metrics') {
      const latest = versions.length ? Math.max(...versions) : null;
      const v = init?.params?.query?.v ?? latest;
      return Promise.resolve({
        data: { items: [], latest, run_id: RUN_ID, values_so_far: false, version: v },
        response: {},
      });
    }
    if (path.endsWith('/graph')) {
      return Promise.resolve({ data: { nodes: [], edges: [], groups: [] }, response: {} });
    }
    return Promise.resolve({ data: { items: [], next_cursor: null }, response: {} });
  });
}

function arrive(search: string): void {
  window.history.replaceState(null, '', `/workflows/${RUN_ID}${search}`);
}

const metricsQueries = (): (number | undefined)[] =>
  GET.mock.calls
    .filter(([p]) => p === '/runs/{run_id}/metrics')
    .map(([, init]) => init?.params?.query?.v);

afterEach(() => {
  cleanup();
  stopPolling();
  resetRunMetrics();
  resetCatalogue();
  GET.mockReset();
  POST.mockReset();
});

describe('RunDetail METRICS tab', () => {
  it('selects METRICS on an ended Run and leaves the arrival URL untouched', async () => {
    serve('done', [1]);
    arrive('');
    render(createElement(RunDetail, { runId: RUN_ID }));
    const tab = await screen.findByRole('button', { name: 'METRICS' });
    await waitFor(() => expect(tab.getAttribute('aria-pressed')).toBe('true'));
    expect(screen.getByTestId('wf-metrics')).toBeTruthy();
    expect(window.location.search).toBe('');
  });

  it('keeps GATE on a running Run', async () => {
    serve('running', []);
    arrive('?view=diagram');
    render(createElement(RunDetail, { runId: RUN_ID }));
    const gate = await screen.findByRole('button', { name: 'GATE' });
    await waitFor(() => expect(gate.getAttribute('aria-pressed')).toBe('true'));
    expect(window.location.search).toBe('?view=diagram');
  });

  it('reads ?v=1 with v and rewrites the URL only once the Operator acts', async () => {
    serve('done', [1, 2]);
    arrive('?tab=metrics&v=1&keep=yes#x');
    render(createElement(RunDetail, { runId: RUN_ID }));
    await screen.findByText('showing v1 of 2 · latest is v2');
    expect(metricsQueries()[0]).toBe(1);
    expect(window.location.search).toBe('?tab=metrics&v=1&keep=yes');

    fireEvent.click(screen.getByRole('button', { name: 'ALL METRICS' }));
    await waitFor(() => expect(window.location.search).toContain('metrics=all'));
    const q = new URLSearchParams(window.location.search);
    expect(q.get('tab')).toBe('metrics');
    expect(q.get('view')).toBe('table');
    expect(q.get('v')).toBe('1');
    expect(q.get('keep')).toBe('yes');
    expect(window.location.hash).toBe('#x');

    fireEvent.click(screen.getByRole('button', { name: 'STEPS' }));
    await waitFor(() =>
      expect(new URLSearchParams(window.location.search).get('tab')).toBe('steps'),
    );
    expect(window.location.search).not.toContain('metrics=all');
  });

  it('settles a ?v= naming the latest version on following the latest', async () => {
    serve('done', [1, 2]);
    arrive('?v=2');
    render(createElement(RunDetail, { runId: RUN_ID }));
    await waitFor(() => expect($runMetrics.get().versions.length).toBe(2));
    await waitFor(() => expect($runMetrics.get().selected).toBeNull());
    await waitFor(() => expect(window.location.search).not.toContain('v=2'));
  });

  it('settles a ?v= the Run does not have on following the latest', async () => {
    serve('done', [1, 2]);
    arrive('?v=99');
    render(createElement(RunDetail, { runId: RUN_ID }));
    await waitFor(() => expect($runMetrics.get().versions.length).toBe(2));
    await waitFor(() => expect($runMetrics.get().selected).toBeNull());
    await act(async () => {});
    expect(metricsQueries().at(-1)).toBeUndefined();
  });
});
