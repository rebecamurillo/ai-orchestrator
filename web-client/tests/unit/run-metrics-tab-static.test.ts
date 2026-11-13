// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import MetricsTab from '../../src/components/run/MetricsTab';
import { resetCatalogue } from '../../src/stores/catalogue';
import { initMetricsTab } from '../../src/stores/metrics-tab';
import { $runAnalysis } from '../../src/stores/run-analysis';
import { version } from './metrics-fixtures';
import { detailOf, glanceOf, seedCatalogue } from './run-metrics-fixtures';

const mount = (over = {}, status = 'done') =>
  render(
    createElement(MetricsTab, {
      detail: detailOf(status),
      glance: glanceOf(over),
      onSelectVersion: vi.fn(),
      onRetryMetrics: vi.fn(),
    }),
  );

beforeEach(() => {
  GET.mockReset();
  GET.mockResolvedValue({ data: { run_id: '1', version: 1, items: [] } });
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
  seedCatalogue();
  initMetricsTab(String(Math.random()), { view: 'table', set: 'headline' });
});
afterEach(() => {
  cleanup();
  resetCatalogue();
});

describe('MetricsTab static signals', () => {
  it('prints the block in TABLE view for the shown version', async () => {
    mount();
    expect(await screen.findByText('not run in v1 · RECALCULATE METRICS runs it')).toBeTruthy();
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/analysis', {
      params: { path: { run_id: '1' }, query: { v: 1 } },
    });
  });
  it('reads the analyses of the version the items hold while a switch is in flight', async () => {
    mount({
      selected: 2,
      versions: [version(1), version(2)],
      metrics: { items: [], latest: 2, run_id: '1', values_so_far: false, version: 1 },
    });
    expect(await screen.findByText('not run in v1 · RECALCULATE METRICS runs it')).toBeTruthy();
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/analysis', {
      params: { path: { run_id: '1' }, query: { v: 1 } },
    });
    expect(GET).not.toHaveBeenCalledWith('/runs/{run_id}/analysis', {
      params: { path: { run_id: '1' }, query: { v: 2 } },
    });
  });
  it('is not charted in CHART view', () => {
    initMetricsTab(String(Math.random()), { view: 'chart', set: 'headline' });
    mount();
    expect(screen.queryByTestId('static-signals')).toBeNull();
  });
  it('is absent on a live Run', () => {
    mount(
      {
        metrics: { items: [], latest: null, run_id: '1', values_so_far: true, version: null },
      },
      'running',
    );
    expect(screen.queryByTestId('static-signals')).toBeNull();
  });
});
