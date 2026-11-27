/**
 * The stop of the initiative, stated where it happened: one banner under the workflow track
 * with the answers its facts call for. Which banner, and every line, is `lib/initiative/stops`.
 */
import { useState, type ReactNode } from 'react';

import { api } from '../../api/client';
import type { InitiativeDetail } from '../../lib/initiative/page';
import { stopBanner, type Restart } from '../../lib/initiative/stops';
import { forceTick } from '../../stores/poll';
import BudgetStop from './BudgetStop';

interface Props {
  detail: InitiativeDetail;
  selectedPosition: number;
  onCancel(): void;
  reopen?: ReactNode;
}

function RestartButton({ detail, restart }: { detail: InitiativeDetail; restart: Restart }) {
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function restartStep(): Promise<void> {
    if (posting) return;
    setPosting(true);
    try {
      const { error: problem } =
        restart.kind === 'retry'
          ? await api.POST('/runs/{run_id}/session/retry', {
              params: { path: { run_id: restart.runId } },
            })
          : await api.POST('/initiatives/{initiative_id}/reopen', {
              params: { path: { initiative_id: detail.id } },
              body: { step: restart.step, reason: restart.reason },
            });
      if (problem) {
        const p = problem as { detail?: string; title?: string };
        setError(p.detail ?? p.title ?? 'The step was not restarted.');
        setPosting(false);
        return;
      }
      setError(null);
      // Stays disabled until the poll replaces this stop: a second post would restart twice.
      forceTick();
    } catch {
      setError('The step was not restarted.');
      setPosting(false);
    }
  }

  return (
    <>
      {error ? <p role="alert">{error}</p> : null}
      <button
        type="button"
        className="primary"
        data-testid="ini-restart"
        disabled={posting}
        onClick={() => void restartStep()}
      >
        Restart step
      </button>
    </>
  );
}

export default function StopBanner({ detail, selectedPosition, onCancel, reopen }: Props) {
  const b = stopBanner(detail, selectedPosition);
  if (!b) return null;
  return (
    <section
      className="ini-stop"
      data-testid="ini-stop"
      data-signal={b.tone === 'red' ? 'failed' : 'needs-you'}
      aria-live="polite"
    >
      <p className="ini-stop-head">{b.head}</p>
      {b.body ? <p className="ini-stop-body">{b.body}</p> : null}
      <div className="ini-stop-actions">
        {b.kind === 'budget' ? (
          <BudgetStop projectId={detail.project?.id ?? detail.project_id} />
        ) : null}
        {b.restart ? (
          <RestartButton
            key={b.restart.kind === 'retry' ? b.restart.runId : b.restart.step}
            detail={detail}
            restart={b.restart}
          />
        ) : null}
        {b.kind === 'advance' ? reopen : null}
        <button type="button" className="danger" data-testid="ini-cancel" onClick={onCancel}>
          Cancel initiative
        </button>
      </div>
    </section>
  );
}
