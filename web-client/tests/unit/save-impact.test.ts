import { describe, expect, it } from 'vitest';

import { APPLIES_LINE, saveImpactLines } from '../../src/lib/templates/save-impact';

describe('saveImpactLines (unpinned callees, 2026-10-02)', () => {
  it('names the unpinned callers that follow the save, then the standing line', () => {
    expect(
      saveImpactLines(
        [
          { name: 'initiative-hub-epic', version: 2, pinned: false },
          { name: 'other', version: 1, pinned: false },
        ],
        3,
      ),
    ).toEqual(['followed on save by initiative-hub-epic@2, other@1', APPLIES_LINE]);
  });

  it('names the pinned callers as staying on the version being edited', () => {
    expect(saveImpactLines([{ name: 'epic', version: 1, pinned: true }], 1)).toEqual([
      'pinned to v1, will not follow: epic@1',
      APPLIES_LINE,
    ]);
  });

  it('lists followers before pinned callers when both exist', () => {
    const lines = saveImpactLines(
      [
        { name: 'a', version: 1, pinned: true },
        { name: 'b', version: 4, pinned: false },
      ],
      2,
    );
    expect(lines).toEqual([
      'followed on save by b@4',
      'pinned to v2, will not follow: a@1',
      APPLIES_LINE,
    ]);
  });

  it('states only the standing line for a Template nothing calls', () => {
    expect(saveImpactLines([], 1)).toEqual([APPLIES_LINE]);
  });
});
