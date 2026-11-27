/** Confirmation of `POST /initiatives/{id}/start-next`: the mechanism, then one post. */
import { useState } from 'react';

import { api } from '../../api/client';
import {
  forceHead,
  forceMechanism,
  forceQuestion,
  keepLabel,
  startLabel,
} from '../../lib/initiative/actions';
import { forceTick } from '../../stores/poll';
import ConfirmPlane from './ConfirmPlane';

interface Props {
  initiativeId: string;
  current: string;
  next: string;
  parkSeq: number;
  slug: string;
  workflow: string;
  nextWorkflow: string | null;
  onClose(): void;
}

export default function ForceStartModal(p: Props) {
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(): Promise<void> {
    if (posting) return;
    setPosting(true);
    try {
      const { error: problem } = await api.POST('/initiatives/{initiative_id}/start-next', {
        params: { path: { initiative_id: p.initiativeId } },
        body: { park_seq: p.parkSeq },
      });
      if (problem) {
        const d = problem as { detail?: string; title?: string };
        setError(d.detail ?? d.title ?? 'The step was not started.');
        setPosting(false);
        return;
      }
      p.onClose();
      forceTick();
    } catch {
      setError('The step was not started.');
      setPosting(false);
    }
  }

  return (
    <ConfirmPlane
      labelId="ini-force-head"
      head={forceHead(p.next)}
      onDismiss={() => {
        if (!posting) p.onClose();
      }}
    >
      <p>{forceQuestion(p.current)}</p>
      <p>{forceMechanism(p.current, p.next, p.slug, p.workflow, p.nextWorkflow)}</p>
      {error ? <p role="alert">{error}</p> : null}
      <div className="ini-plane-actions">
        <button type="button" data-autofocus disabled={posting} onClick={p.onClose}>
          {keepLabel(p.current)}
        </button>
        <button
          type="button"
          className="primary"
          data-testid="ini-force-confirm"
          disabled={posting}
          onClick={() => void confirm()}
        >
          {startLabel(p.next)}
        </button>
      </div>
    </ConfirmPlane>
  );
}
