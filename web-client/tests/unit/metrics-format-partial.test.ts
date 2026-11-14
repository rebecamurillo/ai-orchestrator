import { describe, expect, it } from 'vitest';

import { formatValue, partialWord, stateWords } from '../../src/lib/metrics/format';
import { value } from './metrics-fixtures';

describe('partialWord', () => {
  it('counts repositories for a code metric and attempts for any other', () => {
    expect(partialWord({ metric_id: 'code.x', partial_n: 1, partial_m: 2 })).toBe(
      'partial · 1 of 2 repositories',
    );
    expect(partialWord({ metric_id: 'cost.total', partial_n: 2, partial_m: 3 })).toBe(
      'partial · 2 of 3 attempts',
    );
  });
  it('is null without both fields', () => {
    expect(partialWord({ metric_id: 'code.x', partial_n: null, partial_m: 2 })).toBeNull();
    expect(partialWord({ metric_id: 'code.x', partial_n: 1, partial_m: null })).toBeNull();
  });
});

describe('stateWords and percent', () => {
  it('uses the repository wording for a code value', () => {
    const v = value({ metric_id: 'code.linter_warnings_new', partial_n: 1, partial_m: 2 });
    expect(stateWords(v, false)).toEqual(['partial · 1 of 2 repositories']);
  });
  it('formats a percent with two decimals', () => {
    expect(formatValue('75.00', '%')).toBe('75.00 %');
  });
});
