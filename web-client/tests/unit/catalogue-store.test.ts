import { beforeEach, describe, expect, it, vi } from 'vitest';

import { entry } from './metrics-fixtures';

const { GET } = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock('../../src/api/client', () => ({ api: { GET } }));

import {
  $catalogue,
  entryOf,
  loadCatalogue,
  methodOf,
  resetCatalogue,
} from '../../src/stores/catalogue';

beforeEach(() => {
  GET.mockReset();
  resetCatalogue();
});

describe('loadCatalogue', () => {
  it('fetches once for two calls and stores the entries by id', async () => {
    GET.mockResolvedValue({ data: { items: [entry('a'), entry('b')], next_cursor: null } });

    const first = loadCatalogue();
    const second = loadCatalogue();
    await Promise.all([first, second]);

    expect(first).toBe(second);
    expect(GET).toHaveBeenCalledTimes(1);
    expect(GET).toHaveBeenCalledWith('/metrics/catalogue');
    expect($catalogue.get().status).toBe('ready');
    expect(Object.keys($catalogue.get().entries)).toEqual(['a', 'b']);
  });

  it('is loading while the request is in flight', async () => {
    GET.mockResolvedValue({ data: { items: [], next_cursor: null } });
    const pending = loadCatalogue();
    expect($catalogue.get().status).toBe('loading');
    await pending;
  });

  it('is failed on an error and allows one new call, never an automatic retry', async () => {
    GET.mockResolvedValueOnce({ error: { status: 500 } });
    await loadCatalogue();
    expect($catalogue.get().status).toBe('failed');
    expect(GET).toHaveBeenCalledTimes(1);

    GET.mockResolvedValueOnce({ data: { items: [entry('a')], next_cursor: null } });
    await loadCatalogue();
    expect($catalogue.get().status).toBe('ready');
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it('ignores a request superseded by a reset, whether it succeeds or fails', async () => {
    const settle: { ok?: (v: unknown) => void; fail?: (e: unknown) => void } = {};
    GET.mockReturnValueOnce(new Promise((ok) => (settle.ok = ok)));
    const stale = loadCatalogue();
    resetCatalogue();
    GET.mockReturnValueOnce(new Promise((_ok, fail) => (settle.fail = fail)));
    const staleFailing = loadCatalogue();
    resetCatalogue();
    GET.mockResolvedValueOnce({ data: { items: [entry('fresh')], next_cursor: null } });
    const current = loadCatalogue();
    await current;

    settle.ok!({ data: { items: [entry('stale')], next_cursor: null } });
    settle.fail!(new Error('offline'));
    await Promise.all([stale, staleFailing]);

    expect($catalogue.get().status).toBe('ready');
    expect(Object.keys($catalogue.get().entries)).toEqual(['fresh']);
    expect(loadCatalogue()).toBe(current);
    expect(GET).toHaveBeenCalledTimes(3);
  });

  it('is failed when the request throws', async () => {
    GET.mockRejectedValueOnce(new Error('offline'));
    await loadCatalogue();
    expect($catalogue.get().status).toBe('failed');
  });
});

describe('entryOf and methodOf', () => {
  it('finds an entry and a method by its metric@n id; misses give null', async () => {
    GET.mockResolvedValue({ data: { items: [entry('cost.total')], next_cursor: null } });
    await loadCatalogue();

    const found = entryOf('cost.total');
    expect(found?.id).toBe('cost.total');
    expect(entryOf('nope')).toBeNull();
    expect(methodOf(found!, 'cost.total@2')?.description).toBe('how cost.total v2');
    expect(methodOf(found!, 'cost.total@9')).toBeNull();
    expect(methodOf(found!, 'garbage')).toBeNull();
  });
});
