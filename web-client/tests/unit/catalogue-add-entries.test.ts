import { beforeEach, describe, expect, it, vi } from 'vitest';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import { $catalogue, addEntries, loadCatalogue, resetCatalogue } from '../../src/stores/catalogue';
import { entry } from './metrics-fixtures';
import { stepEntry } from './static-tier-fixtures';

beforeEach(() => {
  GET.mockReset();
  resetCatalogue();
});

describe('addEntries', () => {
  it('merges step entries beside the loaded ones', () => {
    $catalogue.set({ status: 'ready', entries: { 'cost.total': entry() } });
    addEntries([stepEntry()]);
    expect(Object.keys($catalogue.get().entries).sort()).toEqual([
      'cost.total',
      'step.bench-v1.heldout_tests',
    ]);
  });
  it('survives a later catalogue load', async () => {
    addEntries([stepEntry()]);
    GET.mockResolvedValue({ data: { items: [entry()] } });
    await loadCatalogue();
    expect(Object.keys($catalogue.get().entries).sort()).toEqual([
      'cost.total',
      'step.bench-v1.heldout_tests',
    ]);
  });
  it('is cleared by resetCatalogue', () => {
    addEntries([stepEntry()]);
    resetCatalogue();
    expect($catalogue.get().entries).toEqual({});
    addEntries([]);
    expect($catalogue.get().entries).toEqual({});
  });
});
