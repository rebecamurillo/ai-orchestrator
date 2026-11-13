import { beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $runAnalysis, loadRunAnalysis } from '../../src/stores/run-analysis';
import { analysis } from './static-fixtures';
import { HELDOUT, stepEntry } from './static-tier-fixtures';

beforeEach(() => {
  GET.mockReset();
  resetCatalogue();
  $runAnalysis.set({ runId: '', version: null, status: 'idle', items: [], failed: null });
});

describe('step entries of the analysis read', () => {
  it('keeps them in state and merges them into the catalogue', async () => {
    GET.mockResolvedValue({
      data: { run_id: 'r', version: 1, items: [analysis()], step_entries: [stepEntry()] },
    });
    await loadRunAnalysis('r', 1);
    expect($runAnalysis.get().stepEntries?.map((e) => e.id)).toEqual([HELDOUT]);
    expect($catalogue.get().entries[HELDOUT]).toBeDefined();
  });
  it('ignores a superseded response and a failed one', async () => {
    let release: (v: unknown) => void = () => undefined;
    GET.mockReturnValueOnce(new Promise((resolve) => (release = resolve)));
    const first = loadRunAnalysis('r', 1);
    GET.mockResolvedValueOnce({ data: undefined, response: { status: 500 } });
    await loadRunAnalysis('r', 2);
    release({ data: { run_id: 'r', version: 1, items: [], step_entries: [stepEntry()] } });
    await first;
    expect($catalogue.get().entries[HELDOUT]).toBeUndefined();
    expect($runAnalysis.get().stepEntries ?? []).toEqual([]);
  });
});
