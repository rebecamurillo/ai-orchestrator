/**
 * `NewWorkflow.tsx` (4.13) mounts real DOM event handlers (`useState`, debounced pre-flight,
 * `window.location`), which needs a DOM — `vitest.config.ts` runs in `environment: 'node'`
 * (no DOM-mounting library configured), the same constraint `project-form-island.test.ts`
 * and `template-editor-island.test.ts` document. Its wiring as rendered inside a real page —
 * the debounced pre-flight, the harness list, the plan table and the Start run round trip —
 * is `tests/e2e/new-workflow.spec.ts`'s job, in a real browser.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `new.astro` mounts with `client:load`, satisfying `check-test-pairs.mjs` (AD-18) with a
 * real import rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import NewWorkflow from '../../src/islands/NewWorkflow';

describe('the NewWorkflow island', () => {
  it('is exported as the function component new.astro mounts with client:load', () => {
    expect(typeof NewWorkflow).toBe('function');
  });
});
