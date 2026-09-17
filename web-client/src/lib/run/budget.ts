/**
 * The *Raise budget* control's own facts (6.6, FR-17, AD-11, UX-DR10, NFR-8): which stop
 * offers it, what the field starts at, and the body the button posts.
 *
 * Kept beside `answer.ts`/`skip.ts` for the reason those are: this module says what an
 * action will **do**, while `detail.ts` reads a response.
 *
 * **No filter is widened for this one.** `budget_raise` is not in `detail.ts`'s
 * `EFFECTIVE_KINDS`, so `stopSignals` has never rendered it and still does not — the budget
 * stop's control is a box of its own (the `AnswerBox` precedent), because AD-13's signal
 * carries a figure and a plain button cannot ask for one. `admitted_signals` still decides
 * whether the box appears at all.
 */
import type { CostOut, SignalKind } from './detail';
import type { SignalIn } from './signals';

/** The primary button's word, and the field's own label. */
export const BUDGET_RAISE_LABEL = 'Raise budget';
export const BUDGET_FIELD_LABEL = 'new budget';

/** How much headroom the field offers over what the Run has already spent. */
export const BUDGET_HEADROOM = 10;

/**
 * What the field starts at: the spend plus ten dollars, rounded **up**.
 *
 * The brief marks the rounding as an assumption; a ceiling is what makes it safe. AD-13
 * refuses a budget that does not *exceed* the spend, and rounding down would land at or
 * below it for any spend under a dollar (`$0.40 + 10` floored is `$10`, which is fine, but
 * `$0.40` alone floored is `$0`) — so the pre-filled value would sometimes be one the
 * server is about to refuse. Ceiling can never be less than `spend + 10`, so it always
 * clears.
 */
export function prefilledBudget(cost: CostOut): string {
  const spent = Number(cost.spent_usd);
  const base = Number.isFinite(spent) ? spent : 0;
  return Math.ceil(base + BUDGET_HEADROOM).toFixed(2);
}

/** `$4.18 / $15.00` promoted into the stop body — the same ratio `CostBlock` shows.
 * Returns `"tracked, no cap"` when `budget_usd` is null (story 3-2, NFR-8).
 * The budget-park box never renders for null-budget runs, but the guard is here for
 * TypeScript compliance and the defensive path. */
export function budgetRatio(cost: CostOut): string {
  if (cost.budget_usd == null) return 'tracked, no cap';
  return `$${cost.spent_usd} / $${cost.budget_usd}`;
}

/** `POST /runs/{id}/signals`'s body for a raise: the new figure, under `budget_usd`. */
export function budgetRaiseBody(budgetUsd: string): SignalIn {
  return { kind: 'budget_raise', payload: { budget_usd: budgetUsd } };
}

/** Whether this stop shows the box: a `budget` body whose Run admits `budget_raise`. */
export function offersBudgetRaise(kind: string | null, admitted: readonly SignalKind[]): boolean {
  return kind === 'budget' && admitted.includes('budget_raise');
}
