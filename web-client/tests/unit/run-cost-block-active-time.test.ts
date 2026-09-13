/**
 * `activeTimeText` (8.2): `active_seconds` as `hh:mm:ss` (zero-padded).
 *
 * Four cases that strictly exceed `run-cost-block.test.ts`'s revised `'00:00:30'`
 * assertion (placeholder exception, AGENTS.md §1): zero, sub-minute, multi-minute,
 * and cross-hour boundaries are all covered.
 */
import { describe, expect, it } from 'vitest';

import { activeTimeText } from '../../src/lib/run/detail';
import type { CostOut } from '../../src/lib/run/detail';

function cost(active_seconds: number): CostOut {
  return {
    spent_usd: '0.00',
    budget_usd: '10.00',
    tokens_in: 0,
    tokens_out: 0,
    wall_clock_seconds: 0,
    active_seconds,
    provisional: false,
    trace_url: null,
  };
}

describe('activeTimeText', () => {
  it('renders 0 seconds as 00:00:00', () => {
    expect(activeTimeText(cost(0))).toBe('00:00:00');
  });

  it('renders 30 seconds as 00:00:30', () => {
    expect(activeTimeText(cost(30))).toBe('00:00:30');
  });

  it('renders 90 seconds as 00:01:30', () => {
    expect(activeTimeText(cost(90))).toBe('00:01:30');
  });

  it('renders 3661 seconds as 01:01:01', () => {
    expect(activeTimeText(cost(3661))).toBe('01:01:01');
  });
});
