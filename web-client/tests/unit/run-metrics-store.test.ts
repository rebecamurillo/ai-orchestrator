/** `stores/run-metrics.ts` (epic 3 story 3, AC5): reads, version selection, calculation. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { version } from './metrics-fixtures';

const { GET, POST } = vi.hoisted(() => ({ GET: vi.fn(), POST: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET, POST } }));

import {
  $runMetrics,
  calcActive,
  loadRunMetrics,
  pollCalculation,
  resetRunMetrics,
  selectVersion,
  startCalculation,
} from '../../src/stores/run-metrics';

const RUN = 'run-1';

function metrics(v: number | null, latest: number | null) {
  return { items: [], latest, run_id: RUN, values_so_far: false, version: v };
}
function route(map: Record<string, unknown>) {
  GET.mockImplementation(
    async (path: string) => map[path] ?? { error: {}, response: { status: 404 } },
  );
}
function calc(state: string, extra = {}) {
  return {
    ended_at: null,
    entry_point: ['manual'],
    id: 'c',
    output: '',
    queued_at: '2026-11-19T14:02:05Z',
    run_id: RUN,
    started_at: null,
    state,
    target_n: 4,
    ...extra,
  };
}
const VERSIONS = '/runs/{run_id}/metrics/versions';
const METRICS = '/runs/{run_id}/metrics';
const CALC = '/runs/{run_id}/metrics/calculations/{n}';

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  resetRunMetrics();
});

describe('loadRunMetrics', () => {
  it('reads versions and metrics and becomes ready', async () => {
    route({
      [VERSIONS]: { data: { items: [version(1), version(2)] } },
      [METRICS]: { data: metrics(2, 2) },
    });
    await loadRunMetrics(RUN);
    const s = $runMetrics.get();
    expect(s.status).toBe('ready');
    expect(s.versions.map((v) => v.n)).toEqual([1, 2]);
    expect(s.metrics?.latest).toBe(2);
    expect(GET).toHaveBeenCalledWith(METRICS, {
      params: { path: { run_id: RUN }, query: undefined },
    });
  });

  it('drops a stale response', async () => {
    let release: (v: unknown) => void = () => undefined;
    GET.mockImplementationOnce(() => new Promise((r) => (release = r)));
    const first = loadRunMetrics(RUN);
    route({
      [VERSIONS]: { data: { items: [version(9)] } },
      [METRICS]: { data: metrics(9, 9) },
    });
    await loadRunMetrics(RUN);
    release({ data: { items: [version(1)] } });
    await first;
    expect($runMetrics.get().versions.map((v) => v.n)).toEqual([9]);
  });

  it('keeps the last good data and records the failed request', async () => {
    route({
      [VERSIONS]: { data: { items: [version(1)] } },
      [METRICS]: { data: metrics(1, 1) },
    });
    await loadRunMetrics(RUN);
    route({
      [VERSIONS]: { data: { items: [version(1)] } },
      [METRICS]: { error: {}, response: { status: 500 } },
    });
    await loadRunMetrics(RUN);
    const s = $runMetrics.get();
    expect(s.status).toBe('failed');
    expect(s.failed).toEqual({ path: `/api/runs/${RUN}/metrics`, status: 500 });
    expect(s.metrics?.version).toBe(1);
    expect(s.versions).toHaveLength(1);
  });

  it('records a failed versions read and a network failure', async () => {
    route({
      [VERSIONS]: { error: {}, response: { status: 503 } },
      [METRICS]: { data: metrics(null, null) },
    });
    await loadRunMetrics(RUN);
    expect($runMetrics.get().failed).toEqual({
      path: `/api/runs/${RUN}/metrics/versions`,
      status: 503,
    });
    GET.mockRejectedValue(new Error('down'));
    await loadRunMetrics(RUN);
    expect($runMetrics.get().failed).toEqual({
      path: `/api/runs/${RUN}/metrics/versions`,
      status: null,
    });
  });

  it('names the metrics request when it is the read that fails on the network', async () => {
    GET.mockImplementation(async (p: string) => {
      if (p === VERSIONS) return { data: { items: [version(1)] } };
      throw new Error('down');
    });
    await loadRunMetrics(RUN);
    expect($runMetrics.get().failed).toEqual({ path: `/api/runs/${RUN}/metrics`, status: null });
    expect($runMetrics.get().versions.map((v) => v.n)).toEqual([1]);
  });
});

describe('selectVersion', () => {
  it('sends v for an older version and clears the selection for the latest', async () => {
    route({
      [VERSIONS]: { data: { items: [version(1), version(2)] } },
      [METRICS]: { data: metrics(1, 2) },
    });
    await loadRunMetrics(RUN);
    await selectVersion(RUN, 1);
    expect($runMetrics.get().selected).toBe(1);
    expect(GET).toHaveBeenLastCalledWith(METRICS, {
      params: { path: { run_id: RUN }, query: { v: 1 } },
    });
    await selectVersion(RUN, 2);
    expect($runMetrics.get().selected).toBeNull();
  });
});

describe('startCalculation', () => {
  it('stores the accepted calculation', async () => {
    POST.mockResolvedValue({ data: calc('queued') });
    await startCalculation(RUN);
    expect($runMetrics.get().calc?.target_n).toBe(4);
    expect(calcActive($runMetrics.get())).toBe(true);
    expect(POST).toHaveBeenCalledTimes(1);
  });

  it('keeps the problem on a refusal and re-reads on 409', async () => {
    route({ [VERSIONS]: { data: { items: [] } }, [METRICS]: { data: metrics(null, null) } });
    POST.mockResolvedValue({ error: { status: 409, title: 'busy' }, response: { status: 409 } });
    await startCalculation(RUN);
    expect($runMetrics.get().calcError?.title).toBe('busy');
    expect(GET).toHaveBeenCalled();
    GET.mockReset();
    POST.mockResolvedValue({ error: { status: 500, title: 'x' }, response: { status: 500 } });
    await startCalculation(RUN);
    expect(GET).not.toHaveBeenCalled();
  });

  it('reports a network failure as a problem', async () => {
    POST.mockRejectedValue(new Error('down'));
    await startCalculation(RUN);
    expect($runMetrics.get().calcError?.status).toBe(0);
  });
});

describe('pollCalculation', () => {
  async function started() {
    POST.mockResolvedValue({ data: calc('queued') });
    await startCalculation(RUN);
  }

  it('does nothing without a calculation', async () => {
    await pollCalculation(RUN);
    expect(GET).not.toHaveBeenCalled();
  });

  it('updates a running calculation', async () => {
    await started();
    route({ [CALC]: { data: calc('running', { started_at: '2026-11-19T14:02:11Z' }) } });
    await pollCalculation(RUN);
    expect($runMetrics.get().calc?.state).toBe('running');
  });

  it('on done re-reads and a null selection follows the new latest', async () => {
    await started();
    route({
      [CALC]: { data: calc('done') },
      [VERSIONS]: { data: { items: [version(1), version(4)] } },
      [METRICS]: { data: metrics(4, 4) },
    });
    await pollCalculation(RUN);
    const s = $runMetrics.get();
    expect(s.calc).toBeNull();
    expect(s.selected).toBeNull();
    expect(s.versions.map((v) => v.n)).toEqual([1, 4]);
  });

  it('on failed keeps the record and leaves the versions untouched', async () => {
    route({ [VERSIONS]: { data: { items: [version(1)] } }, [METRICS]: { data: metrics(1, 1) } });
    await loadRunMetrics(RUN);
    await started();
    route({ [CALC]: { data: calc('failed', { output: 'boom' }) } });
    await pollCalculation(RUN);
    const s = $runMetrics.get();
    expect(s.calc?.output).toBe('boom');
    expect(calcActive(s)).toBe(false);
    expect(s.versions.map((v) => v.n)).toEqual([1]);
  });

  it('keeps the calculation when the read fails', async () => {
    await started();
    GET.mockRejectedValue(new Error('down'));
    await pollCalculation(RUN);
    expect($runMetrics.get().calc?.state).toBe('queued');
    route({ [CALC]: { error: {}, response: { status: 500 } } });
    await pollCalculation(RUN);
    expect($runMetrics.get().calc?.state).toBe('queued');
  });
});
