/**
 * `BudgetRaiseBox.tsx` (6.6, FR-17, UX-DR10) — the budget stop's own control.
 *
 * `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library, so what is
 * asserted here is the first render: the promoted cost, the pre-filled numeric field, the
 * primary button, and the 409 readout. Typing into the field and posting are
 * `tests/e2e/run-detail-accept.spec.ts`'s job, in a real browser — the same split
 * `run-confirm-action.test.ts` draws for `ConfirmAction`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import BudgetRaiseBox from '../../src/components/run/BudgetRaiseBox';
import type { CostOut } from '../../src/lib/run/detail';

function cost(spent = '41.20', budget = '40.00'): CostOut {
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

function render(over: Partial<Parameters<typeof BudgetRaiseBox>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(BudgetRaiseBox, {
      cost: cost(),
      onRaise: () => {},
      posting: false,
      error: null,
      ...over,
    }),
  );
}

describe('BudgetRaiseBox', () => {
  it('promotes the cost, so the figure being beaten is on screen beside the field', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-budget-cost"');
    expect(html).toContain('$41.20 / $40.00');
  });

  it('offers a numeric field pre-filled with a figure that clears the spend', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-budget-raise-input"');
    expect(html).toContain('type="number"');
    expect(html).toContain('value="52.00"');
  });

  it('labels the field the way the brief names it', () => {
    expect(render()).toContain('new budget');
  });

  it('offers the primary button, enabled', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-budget-raise"');
    expect(html).toContain('Raise budget');
    expect(html).not.toContain('disabled=""');
  });

  it('refuses the button while a signal is in flight', () => {
    expect(render({ posting: true })).toContain('disabled=""');
  });

  it("shows the server's own refusal rather than restating AD-13's rule itself", () => {
    const html = render({
      error: {
        status: 409,
        title: 'Conflict',
        type: 'about:blank',
        detail: 'new budget must exceed spend $41.20',
      },
    });

    expect(html).toContain('data-testid="wf-budget-error"');
    expect(html).toContain('new budget must exceed spend $41.20');
  });

  it('falls back to the problem title when it carries no detail', () => {
    const html = render({
      error: { status: 409, title: 'Conflict', type: 'about:blank', detail: null },
    });

    expect(html).toContain('Conflict');
  });
});
