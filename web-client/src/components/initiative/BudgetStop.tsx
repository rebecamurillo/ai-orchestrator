/**
 * The missing-budget answer: one number, saved as the project default with the project's other
 * four defaults carried over (the operation replaces all five), then the initiative advances.
 */
import { useState } from 'react';

import { api } from '../../api/client';
import { validBudget } from '../../lib/initiative/stops';
import { forceTick } from '../../stores/poll';

interface Props {
  projectId: string;
}

const refusal = (problem: unknown, fallback: string): string => {
  const p = problem as { detail?: string; title?: string };
  return p.detail ?? p.title ?? fallback;
};

export default function BudgetStop({ projectId }: Props) {
  const [raw, setRaw] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(): Promise<void> {
    if (posting || !validBudget(raw)) return;
    setPosting(true);
    try {
      const params = { path: { project_id: projectId } };
      const { data: p, error: readError } = await api.GET('/projects/{project_id}', { params });
      if (readError || !p) {
        setError(refusal(readError, 'The project was not read.'));
        setPosting(false);
        return;
      }
      const { error: problem } = await api.PUT('/projects/{project_id}/run-defaults', {
        params,
        body: {
          default_budget_usd: raw.trim(),
          default_harness: p.default_harness ?? null,
          default_model: p.default_model ?? null,
          default_autonomy: p.default_autonomy ?? null,
          default_senior_model: p.default_senior_model ?? null,
        },
      });
      if (problem) {
        setError(refusal(problem, 'The budget was not saved.'));
        setPosting(false);
        return;
      }
      setError(null);
      // Stays disabled until the poll replaces this stop: the advance starts once.
      forceTick();
    } catch {
      setError('The budget was not saved.');
      setPosting(false);
    }
  }

  return (
    <>
      <label htmlFor="ini-budget">budget USD</label>
      <input
        id="ini-budget"
        data-testid="ini-budget"
        type="number"
        min="0"
        step="0.01"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
      />
      {error ? <p role="alert">{error}</p> : null}
      <button
        type="button"
        className="primary"
        data-testid="ini-budget-set"
        disabled={!validBudget(raw) || posting}
        onClick={() => void submit()}
      >
        Set project budget and start
      </button>
    </>
  );
}
