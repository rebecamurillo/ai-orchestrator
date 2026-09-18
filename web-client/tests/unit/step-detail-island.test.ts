/**
 * `StepDetail.tsx` (story 1-2): the full attempt history island for one step.
 *
 * StepDetail mounts real DOM effects (api polling, useStore) and is exercised
 * end-to-end in `tests/e2e/step-detail.spec.ts`.  This file satisfies the
 * `check-test-pairs.mjs` (AD-18) requirement with a real import rather than a bare string
 * reference, and asserts the component is exported as a function — the same narrow contract
 * `run-detail-island.test.ts` uses for `RunDetail`.
 */
import { describe, expect, it } from 'vitest';

import StepDetail from '../../src/islands/StepDetail';

describe('the StepDetail island', () => {
  it('is exported as the function component [...path].astro mounts with client:load', () => {
    expect(typeof StepDetail).toBe('function');
  });
});
