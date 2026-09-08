/**
 * `signalLabel`'s 5.10 additions — `Skip story`/`Skip epic` — kept apart from the frozen
 * `run-signals-lib.test.ts`, which predates both and only names the three kinds 4.15 gave.
 */
import { describe, expect, it } from 'vitest';

import { signalLabel } from '../../src/lib/run/signals';

describe('signalLabel · skips', () => {
  it('reads Skip story and Skip epic', () => {
    expect(signalLabel('skip_story')).toBe('Skip story');
    expect(signalLabel('skip_epic')).toBe('Skip epic');
  });
});
