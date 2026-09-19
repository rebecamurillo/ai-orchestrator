/**
 * Test-pairs coverage for the `CONSENT_CHECK_TEXT` export added to `state.ts` (story 5-2).
 *
 * The consent text is surfaced as a constant so the island and its acceptance tests share
 * the same string rather than duplicating it.
 */
import { describe, expect, it } from 'vitest';

import { CONSENT_CHECK_TEXT } from '../../src/lib/newwf/state';

describe('CONSENT_CHECK_TEXT', () => {
  it('equals "this can lead to merge conflicts"', () => {
    expect(CONSENT_CHECK_TEXT).toBe('this can lead to merge conflicts');
  });
});
