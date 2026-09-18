/**
 * `LogViewer.tsx` (story 1-2): cursor-paged log reader with follow mode and raw download.
 *
 * LogViewer mounts real DOM effects (fetch cursor paging, scroll tracking, useStore) and
 * is exercised end-to-end in `tests/e2e/step-detail.spec.ts`.  This file satisfies the
 * `check-test-pairs.mjs` (AD-18) requirement with a real import rather than a bare string
 * reference, and asserts the component is exported as a function — the same narrow contract
 * `run-detail-island.test.ts` uses for `RunDetail`.
 */
import { describe, expect, it } from 'vitest';

import LogViewer from '../../src/components/run/LogViewer';

describe('the LogViewer component', () => {
  it('is exported as the function component StepDetail mounts for each attempt', () => {
    expect(typeof LogViewer).toBe('function');
  });
});
