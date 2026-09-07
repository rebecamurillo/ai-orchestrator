/**
 * `RunsQueue.tsx` (4.16) mounts real DOM effects (fetch, `useStore`) — `vitest.config.ts`
 * runs in `environment: 'node'` (no DOM-mounting library configured), the same constraint
 * `board-island.test.ts` documents for `Board.tsx`. Its wiring as rendered inside a real
 * page — the fetch loop, the staleness guard, the section head, the table, both empty
 * readings, and the failed-fetch swap — is `tests/e2e/runs-queue.spec.ts`'s job, in a real
 * browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `runs/index.astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18)
 * with a real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import RunsQueue from '../../src/islands/RunsQueue';

describe('the RunsQueue island', () => {
  it('is exported as the function component runs/index.astro mounts with client:load', () => {
    expect(typeof RunsQueue).toBe('function');
  });
});
