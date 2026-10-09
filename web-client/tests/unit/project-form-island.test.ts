/**
 * `ProjectForm.tsx` (2.5) is the island itself, not the pure logic behind it — `project-form-
 * logic.test.ts` covers row add, mask/replace, field naming, and error lookup with no DOM,
 * per `vitest.config.ts`'s `environment: 'node'` (no DOM-mounting library is configured, so
 * this island cannot be mounted and asserted against here). Its behaviour as wired into a
 * real page is `tests/e2e/project-form.spec.ts`'s job.
 *
 * What this file proves is narrower: the module resolves and exports the component
 * `client:load` expects, satisfying `check-test-pairs.mjs` (AD-18) with a real import
 * rather than a bare string reference — plus what `renderToStaticMarkup` can show of the
 * initial markup without a DOM.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ProjectForm from '../../src/islands/ProjectForm';
import { emptyRepositoryRow, SUGGESTED_TEST_GLOBS } from '../../src/islands/project-form-logic';

describe('the ProjectForm island', () => {
  it('is exported as the function component new.astro and edit.astro mount with client:load', () => {
    expect(typeof ProjectForm).toBe('function');
  });

  // Operator decision 2026-10-06: test_globs are exactly what the operator lists; no default
  // merge. The field starts empty, suggests the former defaults as placeholder only, and says
  // what a listed glob does.
  it('renders the TEST GLOBS field empty, with the suggested globs as placeholder and a line on what they do', () => {
    const html = renderToStaticMarkup(
      createElement(ProjectForm, {
        mode: 'create',
        errors: [],
        initial: {
          name: '',
          contextText: '',
          contextPaths: '',
          logPromptContent: false,
          envVars: [],
          repositories: [emptyRepositoryRow()],
        },
      }),
    );

    expect(html).toContain('data-testid="repo-form-0-test-globs"');
    expect(html).toContain(`placeholder="${SUGGESTED_TEST_GLOBS}"`);
    expect(html).toMatch(/<textarea[^>]*name="repositories\[0\]\.test_globs"[^>]*><\/textarea>/);
    expect(html).toContain('data-testid="repo-form-0-test-globs-line"');
    expect(html).toContain('Empty freezes none');
  });
});
