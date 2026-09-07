/**
 * `RunDetail.tsx` (4.15) mounts real DOM effects (fetch, `useStore`) — `vitest.config.ts`
 * runs in `environment: 'node'` (no DOM-mounting library configured), the same constraint
 * `board-island.test.ts` documents for `Board.tsx`. Its wiring as rendered inside a real page
 * — the poll, the stop bodies per state, the Cancel confirm, the failed-fetch swap — is
 * `tests/e2e/run-detail.spec.ts`'s job, in a real browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `[id].astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18) with a
 * real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import RunDetail from '../../src/islands/RunDetail';

describe('the RunDetail island', () => {
  it('is exported as the function component [id].astro mounts with client:load', () => {
    expect(typeof RunDetail).toBe('function');
  });
});
