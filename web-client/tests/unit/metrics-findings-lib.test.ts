import { describe, expect, it } from 'vitest';

import { findingText, findingsPath, newFindings } from '../../src/lib/metrics/findings';
import { FINDING } from './static-tier-fixtures';

describe('findings', () => {
  it('keeps the new findings of one kind in payload order', () => {
    const items = [
      FINDING,
      { ...FINDING, state: 'unchanged' as const },
      { ...FINDING, state: 'absent' as const },
      { ...FINDING, kind: 'bug' as const },
      { ...FINDING, rule: 'r.second' },
    ];
    expect(newFindings(items, 'security').map((f) => f.rule)).toEqual(['r.xss', 'r.second']);
    expect(newFindings(items, 'bug')).toHaveLength(1);
  });
  it('writes rule, place, severity and CWE', () => {
    expect(findingText(FINDING)).toBe('r.xss · a.py:4 · high · CWE-79');
    expect(findingText({ ...FINDING, line: null, cwe: [] })).toBe('r.xss · a.py:— · high · no CWE');
    expect(findingText({ ...FINDING, cwe: ['CWE-79', 'CWE-80'] })).toContain('CWE-79, CWE-80');
  });
  it('names the request path', () => {
    expect(findingsPath('r1', 'an-1')).toBe('/runs/r1/analysis/an-1/findings');
  });
});
