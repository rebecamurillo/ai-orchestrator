import { beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { $runAnalysis, loadRunAnalysis } from '../../src/stores/run-analysis';
import { analysis } from './static-fixtures';

beforeEach(() => {
  GET.mockReset();
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
});

describe('loadRunAnalysis', () => {
  it('reads the version of the Run', async () => {
    GET.mockResolvedValue({ data: { run_id: 'r', version: 2, items: [analysis()] } });
    await loadRunAnalysis('r', 2);
    expect(GET).toHaveBeenCalledWith('/runs/{run_id}/analysis', {
      params: { path: { run_id: 'r' }, query: { v: 2 } },
    });
    expect($runAnalysis.get()).toMatchObject({ status: 'ready', runId: 'r', version: 2 });
    expect($runAnalysis.get().items).toHaveLength(1);
  });
  it('keeps the items of the same version while it reloads', async () => {
    GET.mockResolvedValue({ data: { run_id: 'r', version: 2, items: [analysis()] } });
    await loadRunAnalysis('r', 2);
    GET.mockResolvedValue({ data: { run_id: 'r', version: 2, items: [] } });
    const reading = loadRunAnalysis('r', 2);
    expect($runAnalysis.get()).toMatchObject({ status: 'loading' });
    expect($runAnalysis.get().items).toHaveLength(1);
    await reading;
    expect($runAnalysis.get().items).toEqual([]);
  });
  it('drops a superseded response', async () => {
    let release: (v: unknown) => void = () => undefined;
    GET.mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    const first = loadRunAnalysis('r', 1);
    GET.mockResolvedValueOnce({ data: { run_id: 'r', version: 2, items: [analysis()] } });
    await loadRunAnalysis('r', 2);
    release({ data: { run_id: 'r', version: 1, items: [] } });
    await first;
    expect($runAnalysis.get()).toMatchObject({ version: 2, status: 'ready' });
    expect($runAnalysis.get().items).toHaveLength(1);
  });
  it('names the failed request, with a status or without one', async () => {
    GET.mockResolvedValueOnce({ data: undefined, response: { status: 404 } });
    await loadRunAnalysis('r', 3);
    expect($runAnalysis.get().failed).toEqual({ path: '/api/runs/r/analysis?v=3', status: 404 });
    GET.mockRejectedValueOnce(new Error('down'));
    await loadRunAnalysis('r', 3);
    expect($runAnalysis.get()).toMatchObject({ status: 'failed', failed: { status: null } });
  });
});
