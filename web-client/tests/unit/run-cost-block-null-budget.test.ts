/**
 * `moneyRatio` — null budget renders "tracked, no cap" (story 3-2, AC4).
 */
import { describe, expect, it } from 'vitest';

import { moneyRatio } from '../../src/lib/run/detail';
import type { CostOut } from '../../src/lib/run/detail';

function costWithNullBudget(): CostOut {
  return {
    spent_usd: '4.18',
    budget_usd: null,
    tokens_in: 100,
    tokens_out: 200,
    wall_clock_seconds: 90,
    active_seconds: 30,
    provisional: false,
    trace_url: null,
  } as unknown as CostOut;
}

describe('moneyRatio with null budget', () => {
  it('returns "tracked, no cap" when budget_usd is null', () => {
    expect(moneyRatio(costWithNullBudget())).toBe('tracked, no cap');
  });
});
