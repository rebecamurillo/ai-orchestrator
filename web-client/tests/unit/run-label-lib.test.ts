/** `lib/run/label.ts` (epic 3 story 3, SPEC CAP-3): the Run label's pure helpers. */
import { describe, expect, it } from 'vitest';

import {
  defaultLabelPreview,
  labelPayload,
  labelState,
  PLACEHOLDER,
  runTitle,
} from '../../src/lib/run/label';

const NOW = Date.parse('2026-11-10T10:23:40Z');

describe('runTitle', () => {
  it('is the label, and the branch when an older payload has none', () => {
    expect(runTitle({ label: 'my label', branch: 'feat/x' })).toBe('my label');
    expect(runTitle({ branch: 'feat/x' })).toBe('feat/x');
  });
});

describe('labelPayload', () => {
  it('trims, and sends null for blank text so the default is restored', () => {
    expect(labelPayload('  snake round 1 ')).toEqual({ label: 'snake round 1' });
    expect(labelPayload('   ')).toEqual({ label: null });
    expect(labelPayload('')).toEqual({ label: null });
  });
});

describe('labelState', () => {
  it('names who set the label', () => {
    expect(labelState(true)).toBe('your label · clear it to restore the default');
    expect(labelState(false)).toBe('default label');
  });
});

describe('defaultLabelPreview', () => {
  const base = { projectName: 'familio', template: 'bench-v1-staged', nowMs: NOW };

  it('joins project, initiative folder basename, template and UTC minute', () => {
    expect(
      defaultLabelPreview({ ...base, inputs: { initiative_folder: 'docs/familio-snake-v2' } }),
    ).toBe('familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23');
  });

  it('falls back to spec_folder and strips a trailing slash', () => {
    expect(defaultLabelPreview({ ...base, inputs: { spec_folder: 'a/b/spec-x//' } })).toBe(
      'familio spec-x bench-v1-staged 2026-11-10 10:23',
    );
  });

  it('skips a blank initiative folder and drops blank words', () => {
    expect(
      defaultLabelPreview({
        ...base,
        projectName: '',
        inputs: { initiative_folder: '', spec_folder: 'docs/s' },
      }),
    ).toBe('s bench-v1-staged 2026-11-10 10:23');
    expect(defaultLabelPreview({ ...base, inputs: {} })).toBe(
      'familio bench-v1-staged 2026-11-10 10:23',
    );
  });
});

describe('PLACEHOLDER', () => {
  it('prefixes the computed label', () => {
    expect(PLACEHOLDER('x y')).toBe('default: x y');
  });
});
