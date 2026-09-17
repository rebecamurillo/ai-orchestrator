/**
 * `lib/run/budget.ts` (6.6, FR-17, AD-11) — the pre-filled figure, the ratio, the body, and
 * the predicate that decides whether the box is offered at all.
 *
 * The pre-fill is the only one of the four with a rule behind it rather than a shape:
 * AD-13 refuses a budget that does not *exceed* the spend, so a value the screen offers must
 * always clear it. That is what the ceiling is for, and it is what most of this file asserts.
 */
import { describe, expect, it } from 'vitest';

import {
  BUDGET_HEADROOM,
  BUDGET_RAISE_LABEL,
  budgetRaiseBody,
  budgetRatio,
  offersBudgetRaise,
  prefilledBudget,
} from '../../src/lib/run/budget';
import type { CostOut, SignalKind } from '../../src/lib/run/detail';

function cost(spent: string, budget = '40.00'): CostOut {
  return {
    spent_usd: spent,
    budget_usd: budget,
    tokens_in: 0,
    tokens_out: 0,
    wall_clock_seconds: 0,
    active_seconds: 0,
    provisional: false,
    trace_url: null,
  } as unknown as CostOut;
}

describe('prefilledBudget', () => {
  it('offers the spend plus ten dollars, rounded up', () => {
    expect(prefilledBudget(cost('41.20'))).toBe('52.00');
  });

  it('always clears the spend, which is what the server refuses against', () => {
    for (const spent of ['0', '0.004', '0.5', '9.99', '41.20', '1234.56']) {
      expect(Number(prefilledBudget(cost(spent)))).toBeGreaterThan(Number(spent));
    }
  });

  it('never offers less than the spend plus the headroom', () => {
    for (const spent of ['0.01', '7.4', '99.999']) {
      expect(Number(prefilledBudget(cost(spent)))).toBeGreaterThanOrEqual(
        Number(spent) + BUDGET_HEADROOM,
      );
    }
  });

  it('reads a spend it cannot parse as nothing spent rather than as NaN', () => {
    expect(prefilledBudget(cost('—'))).toBe('10.00');
  });
});

describe('budgetRatio', () => {
  it('is the same spent-over-budget ratio the cost block shows', () => {
    expect(budgetRatio(cost('41.20'))).toBe('$41.20 / $40.00');
  });

  it('returns "tracked, no cap" when budget_usd is null', () => {
    const nullBudgetCost = { ...cost('41.20'), budget_usd: null } as unknown as CostOut;
    expect(budgetRatio(nullBudgetCost)).toBe('tracked, no cap');
  });
});

describe('budgetRaiseBody', () => {
  it('posts the figure under the key AD-13 names', () => {
    expect(budgetRaiseBody('60.00')).toEqual({
      kind: 'budget_raise',
      payload: { budget_usd: '60.00' },
    });
  });
});

describe('offersBudgetRaise', () => {
  const admitted = ['budget_raise', 'cancel'] as SignalKind[];

  it('is offered on the budget stop when the server admits the kind', () => {
    expect(offersBudgetRaise('budget', admitted)).toBe(true);
  });

  it('is not offered on any other stop', () => {
    expect(offersBudgetRaise('blocked', admitted)).toBe(false);
    expect(offersBudgetRaise(null, admitted)).toBe(false);
  });

  it('is not offered when the server does not admit it, whatever the stop', () => {
    expect(offersBudgetRaise('budget', ['cancel'] as SignalKind[])).toBe(false);
  });
});

describe('the button', () => {
  it("reads the brief's own word", () => {
    expect(BUDGET_RAISE_LABEL).toBe('Raise budget');
  });
});
