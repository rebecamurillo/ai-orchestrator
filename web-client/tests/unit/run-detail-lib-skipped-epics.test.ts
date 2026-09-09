/**
 * `src/lib/run/detail.ts::summaryLine`'s 6.5 addition: the `epics skipped: {ns}` clause.
 * Kept apart from the frozen `run-detail-lib.test.ts`, whose own `summaryLine` fixtures
 * predate `summary.skipped_epics` and must keep compiling and passing unedited — the field
 * is optional on the wire for exactly that reason (`src/lib/run/detail.ts`'s own doc).
 */
import { describe, expect, it } from 'vitest';

import { summaryLine, type RunDetailOut } from '../../src/lib/run/detail';

function detail(summary: RunDetailOut['summary']): RunDetailOut {
  return { summary } as unknown as RunDetailOut;
}

describe('summaryLine — skipped epics', () => {
  it('appends the epics-skipped clause after the stories one', () => {
    const d = detail({
      progress: { epics_done: 1, epics_total: 2, stories_done: 4, stories_total: 8, links: 1 },
      links: ['https://a'],
      skipped: ['4-9'],
      skipped_epics: [1],
    });

    expect(summaryLine(d)).toBe(
      '1/2 epics · 4/8 stories · 1 link · skipped: 4-9 · epics skipped: 1',
    );
  });

  it('appends it alone when no story was individually skipped', () => {
    const d = detail({
      progress: null,
      links: ['https://a', 'https://b'],
      skipped: [],
      skipped_epics: [1, 2],
    });

    expect(summaryLine(d)).toBe('2 links · epics skipped: 1, 2');
  });

  it('omits the clause when no epic was skipped', () => {
    const d = detail({ progress: null, links: ['https://a'], skipped: [], skipped_epics: [] });

    expect(summaryLine(d)).toBe('1 link');
  });

  it('reads as no epic skipped when the field is absent from the wire (pre-6.5 response)', () => {
    const d = detail({ progress: null, links: ['https://a'], skipped: ['4-9'] });

    expect(summaryLine(d)).toBe('1 link · skipped: 4-9');
  });
});
