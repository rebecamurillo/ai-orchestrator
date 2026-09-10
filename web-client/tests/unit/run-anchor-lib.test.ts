/**
 * `#step-{seq}` (7.5): the id the Steps table gives a row, and the seq a fragment names.
 *
 * The parse is the half that has to be strict — a fragment is user-supplied text that
 * survives copy-paste and hand-editing — so every near-miss is checked here rather than
 * left to a `Number()` coercion the browser would then look up as an element id.
 */
import { describe, expect, it } from 'vitest';

import { anchoredSeq, PROMOTED_MS, stepAnchorId } from '../../src/lib/run/anchor';

describe('stepAnchorId', () => {
  it('is the fragment a history row links with', () => {
    expect(stepAnchorId(7)).toBe('step-7');
    expect(stepAnchorId(0)).toBe('step-0');
  });
});

describe('anchoredSeq', () => {
  it('reads the seq out of the fragment', () => {
    expect(anchoredSeq('#step-7')).toBe(7);
    expect(anchoredSeq('#step-0')).toBe(0);
    expect(anchoredSeq('#step-142')).toBe(142);
  });

  it('answers null for an empty or absent fragment', () => {
    expect(anchoredSeq('')).toBeNull();
    expect(anchoredSeq('#')).toBeNull();
  });

  it.each([
    '#step-',
    '#step-7x',
    '#step--1',
    '#step- 7',
    '#step-7e2',
    '#step-0x7',
    '#steps-7',
    '#other-7',
  ])('answers null for %s rather than a number to look up', (hash) => {
    expect(anchoredSeq(hash)).toBeNull();
  });
});

describe('the promotion', () => {
  it('is brief, and stated once', () => {
    expect(PROMOTED_MS).toBeGreaterThan(0);
    expect(PROMOTED_MS).toBeLessThanOrEqual(10_000);
  });
});
