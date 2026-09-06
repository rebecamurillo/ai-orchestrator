/**
 * `TemplateEditor.tsx` (3.5) mounts a real CodeMirror `EditorView`, which needs a DOM —
 * `vitest.config.ts` runs in `environment: 'node'` (no DOM-mounting library configured), the
 * same constraint `project-form-island.test.ts` documents. Its wiring as rendered inside a
 * real page — the debounced Validate, Save, and the error list — is `tests/e2e/
 * templates.spec.ts`'s job, in a real browser.
 *
 * What the first block proves is narrower: the module resolves and exports the component
 * `[name]/[version].astro` mounts with `client:load`, satisfying `check-test-pairs.mjs`
 * (AD-18) with a real import rather than a bare string reference.
 *
 * The three pure helpers below it need no DOM at all, unlike the component — the same reason
 * `yamlEditor.ts`'s siblings get direct coverage in `yaml-editor.test.ts` (Review Triage Log,
 * story 3.5, finding 13).
 */
import { describe, expect, it } from 'vitest';

import TemplateEditor, {
  errorRows,
  errorsFromProblem,
  readoutTime,
} from '../../src/islands/TemplateEditor';

describe('the TemplateEditor island', () => {
  it('is exported as the function component [version].astro mounts with client:load', () => {
    expect(typeof TemplateEditor).toBe('function');
  });
});

describe('readoutTime', () => {
  it('reads the HH:MM:SS out of an ISO 8601 UTC timestamp', () => {
    expect(readoutTime('2026-09-06T14:03:09.123Z')).toBe('14:03:09');
  });
});

describe('errorRows', () => {
  it('renders a gated error as line {n} · {reason}', () => {
    const rows = errorRows({
      errors: [{ line: 4, reason: 'parallel is reserved' }],
      unvalidated: [],
    });

    expect(rows).toEqual(['line 4 · parallel is reserved']);
  });

  it('renders an error with no line as the reason alone', () => {
    const rows = errorRows({
      errors: [{ line: null, reason: 'version must be 2' }],
      unvalidated: [],
    });

    expect(rows).toEqual(['version must be 2']);
  });

  it('lists every error before every unvalidated path, in order', () => {
    const rows = errorRows({
      errors: [{ line: 1, reason: 'parallel is reserved' }],
      unvalidated: ['steps.build', 'steps.checkout'],
    });

    expect(rows).toEqual([
      'line 1 · parallel is reserved',
      'unvalidated · steps.build',
      'unvalidated · steps.checkout',
    ]);
  });

  it('renders nothing for a clean result', () => {
    expect(errorRows({ errors: [], unvalidated: [] })).toEqual([]);
  });
});

describe('errorsFromProblem (Review Triage Log, story 3.5, finding 1)', () => {
  it('passes a real errors[] through untouched', () => {
    const problem = {
      type: 'about:blank',
      title: 'invalid template',
      status: 422,
      errors: [{ line: 4, reason: 'parallel is reserved' }],
    };

    expect(errorsFromProblem(problem)).toEqual([{ line: 4, reason: 'parallel is reserved' }]);
  });

  it('synthesizes one row from detail when errors[] is absent, so a failure is never silent', () => {
    const problem = {
      type: 'about:blank',
      title: 'no Template has that name',
      status: 404,
      detail: 'no Template has that name',
    };

    expect(errorsFromProblem(problem)).toEqual([{ reason: 'no Template has that name' }]);
  });

  it('synthesizes one row from title alone when even detail is absent', () => {
    const problem = { type: 'about:blank', title: 'not found', status: 404 };

    expect(errorsFromProblem(problem)).toEqual([{ reason: 'not found' }]);
  });

  it('synthesizes a row when errors[] is present but empty', () => {
    const problem = { type: 'about:blank', title: 'refused', status: 422, errors: [] };

    expect(errorsFromProblem(problem)).toEqual([{ reason: 'refused' }]);
  });
});
