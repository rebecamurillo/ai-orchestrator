/**
 * `Board.tsx` (4.14) mounts real DOM effects (fetch, `useStore`, `document.querySelector`
 * shell-sync), which needs a DOM — `vitest.config.ts` runs in `environment: 'node'` (no
 * DOM-mounting library configured), the same constraint `newwf-island.test.ts` documents for
 * `NewWorkflow.tsx`. Its wiring as rendered inside a real page — the fetch loop, the
 * staleness guard, the five columns, both empty states, the failed-fetch swap, and the
 * rail/footer DOM sync — is `tests/e2e/board.spec.ts`'s job, in a real browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `index.astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18) with a
 * real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import Board from '../../src/islands/Board';

describe('the Board island', () => {
  it('is exported as the function component index.astro mounts with client:load', () => {
    expect(typeof Board).toBe('function');
  });
});
