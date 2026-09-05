/**
 * `ProjectForm.tsx` (2.5) is the island itself, not the pure logic behind it — `project-form-
 * logic.test.ts` covers row add, mask/replace, field naming, and error lookup with no DOM,
 * per `vitest.config.ts`'s `environment: 'node'` (no DOM-mounting library is configured, so
 * this island cannot be mounted and asserted against here). Its behaviour as wired into a
 * real page is `tests/e2e/project-form.spec.ts`'s job.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `client:load` expects, satisfying `check-test-pairs.mjs` (AD-18) with a real import
 * rather than a bare string reference.
 */
import { describe, expect, it } from 'vitest';

import ProjectForm from '../../src/islands/ProjectForm';

describe('the ProjectForm island', () => {
  it('is exported as the function component new.astro and edit.astro mount with client:load', () => {
    expect(typeof ProjectForm).toBe('function');
  });
});
