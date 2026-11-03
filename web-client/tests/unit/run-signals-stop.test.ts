/**
 * AD-24: the Run page names the stop on the signals that answer one.
 */
import { describe, expect, it } from 'vitest';

import { withStop } from '../../src/lib/run/signals';

describe('withStop', () => {
  it.each(['answer', 'retry', 'continue'] as const)('adds the stop to %s', (kind) => {
    expect(withStop({ kind, payload: { text: 'go' } }, 3)).toEqual({
      kind,
      payload: { text: 'go' },
      stop: 3,
    });
  });

  it.each(['cancel', 'budget_raise', 'skip_step', 'skip_story', 'skip_epic'] as const)(
    'leaves %s alone',
    (kind) => {
      expect(withStop({ kind }, 3)).toEqual({ kind });
    },
  );

  it('leaves the body alone when the Run has not stopped', () => {
    expect(withStop({ kind: 'answer' }, undefined)).toEqual({ kind: 'answer' });
  });
});
