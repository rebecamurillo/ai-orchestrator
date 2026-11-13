import { describe, expect, it } from 'vitest';

import { findingLine, sarifFindings, sarifHref } from '../../src/lib/metrics/sarif';

const doc = {
  runs: [
    {
      results: [
        {
          ruleId: 'aws-key',
          message: { text: 'a key' },
          locations: [
            {
              physicalLocation: {
                artifactLocation: { uri: 'src/a.py' },
                region: { startLine: 12 },
              },
            },
          ],
        },
        {},
        'junk',
      ],
    },
    { results: 'nope' },
    null,
  ],
};

describe('sarif', () => {
  it('builds the download href', () => {
    expect(sarifHref('r', 'a', 'gitleaks')).toBe('/api/runs/r/analysis/a/sarif/gitleaks');
  });
  it('reads findings and tolerates missing fields', () => {
    const found = sarifFindings(doc);
    expect(found[0]).toEqual({ rule: 'aws-key', path: 'src/a.py', line: '12', message: 'a key' });
    expect(found[1]).toEqual({ rule: '—', path: '—', line: '—', message: '—' });
    expect(found).toHaveLength(3);
    expect(findingLine(found[0])).toBe('aws-key · src/a.py:12');
  });
  it('returns nothing for a non-object or a document without runs', () => {
    expect(sarifFindings(null)).toEqual([]);
    expect(sarifFindings([])).toEqual([]);
    expect(sarifFindings('x')).toEqual([]);
    expect(sarifFindings({})).toEqual([]);
  });
});
