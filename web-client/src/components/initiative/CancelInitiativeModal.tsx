/** Confirmation of `POST /initiatives/{id}/cancel`: what is removed, then one post. */
import { useState } from 'react';

import { api } from '../../api/client';
import { cancelLines } from '../../lib/initiative/actions';
import type { InitiativeDetail } from '../../lib/initiative/page';
import { forceTick } from '../../stores/poll';
import ConfirmPlane from './ConfirmPlane';

interface Props {
  detail: InitiativeDetail;
  onClose(): void;
}

export default function CancelInitiativeModal({ detail, onClose }: Props) {
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm(): Promise<void> {
    if (posting) return;
    setPosting(true);
    try {
      const { error: problem } = await api.POST('/initiatives/{initiative_id}/cancel', {
        params: { path: { initiative_id: detail.id } },
      });
      if (problem) {
        const d = problem as { detail?: string; title?: string };
        setError(d.detail ?? d.title ?? 'The initiative was not cancelled.');
        setPosting(false);
        return;
      }
      onClose();
      forceTick();
    } catch {
      setError('The initiative was not cancelled.');
      setPosting(false);
    }
  }

  return (
    <ConfirmPlane
      labelId="ini-cancel-head"
      head="CANCEL INITIATIVE"
      onDismiss={() => {
        if (!posting) onClose();
      }}
    >
      <p>Cancel {detail.slug}?</p>
      <ul>
        {cancelLines(detail).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {error ? <p role="alert">{error}</p> : null}
      <div className="ini-plane-actions">
        <button type="button" data-autofocus disabled={posting} onClick={onClose}>
          Keep it
        </button>
        <button
          type="button"
          className="danger"
          data-testid="ini-cancel-confirm"
          disabled={posting}
          onClick={() => void confirm()}
        >
          Cancel initiative
        </button>
      </div>
    </ConfirmPlane>
  );
}
