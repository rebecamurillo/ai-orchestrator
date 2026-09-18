import { describe, expect, it } from 'vitest';

import { SAVE_TEXT } from '../../src/lib/newwf/state';

describe('SAVE_TEXT', () => {
  it('is "Save"', () => {
    expect(SAVE_TEXT).toBe('Save');
  });
});
