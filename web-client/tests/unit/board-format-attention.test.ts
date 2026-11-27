/**
 * `src/lib/board/format.ts` — the oldest wait follows the server's column rule (story 4,
 * epic 7 review, 2026-11-25): a `needs_you` card with attention other than `blocked` is in
 * Running and is not waiting on the Operator.
 */
import { describe, expect, it } from 'vitest';

import { oldestWaitSeconds, type CardOut } from '../../src/lib/board/format';

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    token: 'RUN',
    status: 'needs_you',
    park_kind: 'conversation',
    branch: 'main',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'conversation',
    harness: null,
    template: 'spec',
    version: 1,
    progress: null,
    kind_label: 'spec',
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

describe('oldestWaitSeconds by attention', () => {
  it('ignores a needs_you card whose attention is not blocked', () => {
    const cards = [
      card({ attention: 'your_turn', age_seconds: 9_000 }),
      card({ attention: 'answering', age_seconds: 8_000 }),
      card({ attention: 'queued', age_seconds: 7_000 }),
    ];
    expect(oldestWaitSeconds(cards)).toBeNull();
  });

  it('counts a blocked card and one with no attention read', () => {
    const cards = [
      card({ attention: 'your_turn', age_seconds: 9_000 }),
      card({ attention: 'blocked', age_seconds: 300 }),
      card({ age_seconds: 400 }),
    ];
    expect(oldestWaitSeconds(cards)).toBe(400);
  });
});
