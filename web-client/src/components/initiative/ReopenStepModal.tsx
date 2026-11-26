/** Confirmation of `POST /initiatives/{id}/reopen`: the spec step to reopen, the mechanism, one post. */
import { useState } from 'react';

import { api } from '../../api/client';
import {
  KEEP_LABEL,
  REOPEN_HEAD,
  reopenLabel,
  reopenMechanism,
  reopenQuestion,
  reopenReason,
  reopenSteps,
  type ReopenOrigin,
} from '../../lib/initiative/reopen';
import type { InitiativeDetail } from '../../lib/initiative/page';
import { forceTick } from '../../stores/poll';
import ConfirmPlane from './ConfirmPlane';

interface Props {
  detail: InitiativeDetail;
  origin: ReopenOrigin;
  runId: string | null;
  onClose(): void;
  onReopened(step: string): void;
}

export default function ReopenStepModal({ detail, origin, runId, onClose, onReopened }: Props) {
  // Computed once: a poll must not change what she is confirming.
  const [frozen] = useState(() => ({
    steps: reopenSteps(detail),
    reason: reopenReason(detail, origin, runId),
    question: reopenQuestion(origin),
    mechanism: (step: string | null) => reopenMechanism(detail, runId, step),
  }));
  const [chosen, setChosen] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(): Promise<void> {
    if (posting || chosen === null) return;
    setPosting(true);
    try {
      const { error: problem } = await api.POST('/initiatives/{initiative_id}/reopen', {
        params: { path: { initiative_id: detail.id } },
        body: { step: chosen, reason: frozen.reason },
      });
      if (problem) {
        const p = problem as { detail?: string; title?: string };
        setError(p.detail ?? p.title ?? 'The step was not reopened.');
        setPosting(false);
        return;
      }
      onReopened(chosen);
      forceTick();
    } catch {
      setError('The step was not reopened.');
      setPosting(false);
    }
  }

  return (
    <ConfirmPlane
      labelId="ini-reopen-head"
      head={REOPEN_HEAD}
      onDismiss={() => {
        if (!posting) onClose();
      }}
    >
      <p>{frozen.question}</p>
      <fieldset>
        {frozen.steps.map((s) => (
          <label key={s.id}>
            <input
              type="radio"
              name="reopen-step"
              value={s.id}
              checked={chosen === s.id}
              disabled={posting}
              onChange={() => setChosen(s.id)}
            />{' '}
            {s.label}
          </label>
        ))}
      </fieldset>
      <p>{`first turn: "${frozen.reason}"`}</p>
      <p>{frozen.mechanism(chosen)}</p>
      {error ? <p role="alert">{error}</p> : null}
      <div className="ini-plane-actions">
        <button type="button" data-autofocus disabled={posting} onClick={onClose}>
          {KEEP_LABEL}
        </button>
        <button
          type="button"
          className="primary"
          data-testid="ini-reopen-confirm"
          disabled={chosen === null || posting}
          onClick={() => void confirm()}
        >
          {reopenLabel(chosen)}
        </button>
      </div>
    </ConfirmPlane>
  );
}
