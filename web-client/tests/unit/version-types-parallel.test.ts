// Story 10.4 review, 2026-11-26: the per-version reads start together, not one after another.
import { describe, expect, it, vi } from 'vitest';

import { readVersionTypes } from '../../src/lib/templates/version-rows';

describe('readVersionTypes parallelism', () => {
  it('starts every read before any of them settles', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const read = vi.fn(async () => {
      await gate;
      return 'auto' as const;
    });
    const pending = readVersionTypes({
      versions: [1, 2, 3, 4],
      loaded: { version: 1, type: 'interactive' },
      read,
    });
    await Promise.resolve();
    expect(read).toHaveBeenCalledTimes(3);
    release();
    const map = await pending;
    expect([...map.keys()].sort()).toEqual([1, 2, 3, 4]);
  });
});
