/**
 * `RunsHistory.tsx` (7.5) mounts real DOM effects (fetch, `useStore`) — `vitest.config.ts`
 * runs in `environment: 'node'` with no DOM-mounting library configured, the same constraint
 * `runs-queue-island.test.ts` documents for `RunsQueue.tsx`. Its wiring as rendered inside a
 * real page — the fetch, the *more* control, the empty reading, the failed-fetch swap and the
 * filters reaching the query — is `tests/e2e/runs-history.spec.ts`'s job, in a real browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `runs/index.astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18)
 * with a real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import RunsHistory from '../../src/islands/RunsHistory';

describe('the RunsHistory island', () => {
  it('is exported as the function component runs/index.astro mounts with client:load', () => {
    expect(typeof RunsHistory).toBe('function');
  });
});
