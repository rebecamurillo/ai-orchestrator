/**
 * The budget stop's own body (6.6, FR-17, UX-DR10): the cost promoted out of the right-hand
 * column, a numeric field for the new budget, and the button that posts it.
 *
 * Stateful for the reason `AnswerBox` is: the figure being typed is local text no other
 * component reads, and `StopBody` stays stateless so its own unit tests keep rendering it
 * through `renderToStaticMarkup`. The island owns in-flight and 409 state, as it does for
 * every other signal.
 *
 * **The field is pre-filled and still editable, and the button is never disabled on a
 * guess.** AD-13 refuses a budget that does not exceed the spend, with the sentence that
 * says so; the screen does not duplicate that rule, it renders the 409 (`error`) when it
 * arrives. What the screen *does* guarantee is that the value it pre-filled always clears —
 * see `prefilledBudget`.
 */
import { useState } from 'react';

import type { components } from '../../api/schema';
import {
  BUDGET_FIELD_LABEL,
  BUDGET_RAISE_LABEL,
  budgetRatio,
  prefilledBudget,
} from '../../lib/run/budget';
import type { CostOut } from '../../lib/run/detail';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  cost: CostOut;
  onRaise: (budgetUsd: string) => void;
  posting: boolean;
  error: ProblemDetail | null;
}

export default function BudgetRaiseBox({ cost, onRaise, posting, error }: Props) {
  const [value, setValue] = useState(() => prefilledBudget(cost));
  const empty = value.trim().length === 0;

  return (
    <div className="wf-budget-box">
      <p className="wf-budget-cost" data-testid="wf-budget-cost">
        spent / budget: {budgetRatio(cost)}
      </p>
      <label className="wf-budget-field">
        <span className="wf-budget-label">{BUDGET_FIELD_LABEL}</span>
        <input
          type="number"
          className="wf-budget-input"
          data-testid="wf-budget-raise-input"
          min="0"
          step="0.01"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      <div className="wf-budget-actions">
        <button
          type="button"
          className="wf-signal wf-budget-submit"
          data-testid="wf-budget-raise"
          disabled={empty || posting}
          onClick={() => onRaise(value.trim())}
        >
          {BUDGET_RAISE_LABEL}
        </button>
        {error ? (
          <span className="wf-signal-error" data-testid="wf-budget-error">
            {error.detail ?? error.title}
          </span>
        ) : null}
      </div>
    </div>
  );
}
