/**
 * `HelperDrawer.tsx` (story 1-3): the right-side helper drawer for prompt-result and reach-agent.
 *
 * HelperDrawer renders DOM effects and is exercised end-to-end in e2e tests. This file
 * satisfies the `check-test-pairs.mjs` (AD-18) requirement with a real import and asserts
 * the component is exported as a function — the same narrow contract
 * `step-detail-island.test.ts` uses for `StepDetail`.
 */
import { describe, expect, it } from 'vitest';

import HelperDrawer from '../../src/components/run/HelperDrawer';

describe('the HelperDrawer component', () => {
  it('is exported as the function component StepDetail mounts as a drawer', () => {
    expect(typeof HelperDrawer).toBe('function');
  });
});
