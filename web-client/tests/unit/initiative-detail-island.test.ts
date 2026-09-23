/**
 * `InitiativeDetail.tsx` (S7) mounts real DOM event handlers (`useState`, a polled fetch),
 * which needs a DOM — `vitest.config.ts` runs in `environment: 'node'`,
 * `tests/unit/newwf-island.test.ts`'s own documented constraint. Its wiring as rendered
 * inside a real page is `tests/e2e/initiative-detail.spec.ts`'s job, in a real browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `[slug].astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18) with a
 * real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import InitiativeDetail from '../../src/islands/InitiativeDetail';

describe('the InitiativeDetail island', () => {
  it('is exported as the function component [slug].astro mounts with client:load', () => {
    expect(typeof InitiativeDetail).toBe('function');
  });
});
