import { describe, expect, it } from 'vitest';

import { trajectoryCountText } from '../../src/lib/projects/export';

describe('trajectoryCountText', () => {
  it('reads the plural for zero', () => {
    expect(trajectoryCountText(0)).toBe('0 trajectories');
  });

  it('reads the singular for exactly one', () => {
    expect(trajectoryCountText(1)).toBe('1 trajectory');
  });

  it('reads the plural for more than one', () => {
    expect(trajectoryCountText(3)).toBe('3 trajectories');
  });
});
