/**
 * The Retry box (story 3-4): mode selector for the Retry signal, shown only when
 * `reply_available` is true. Restart archives the blocked story file and re-dispatches;
 * Session continues the harness session in place.
 *
 * Constants live here because they are Retry-specific and not shared with `answer.ts`.
 * `AnswerTarget` is reused so the restart hint can name the exact archive path.
 */
import { useState } from 'react';

import type { components } from '../../api/schema';
import { answerHint, type AnswerTarget } from '../../lib/run/answer';

type ProblemDetail = components['schemas']['ProblemDetail'];

/** The hint for retry-restart mode: names the archive path and states re-dispatch. */
export const RETRY_RESTART_HINT_SUFFIX = '; the story is re-dispatched fresh.';

/** The hint for retry-session mode (verbatim from spec). */
export const RETRY_SESSION_HINT =
  'The session continues with the retry prompt; the Story file stays in place.';

interface Props {
  target: AnswerTarget;
  onRetry: (mode: string) => void;
  posting: boolean;
  error: ProblemDetail | null;
}

export default function RetryBox({ target, onRetry, posting, error }: Props) {
  const [mode, setMode] = useState<'restart' | 'session'>('restart');
  const restartHint = answerHint(target) + RETRY_RESTART_HINT_SUFFIX;

  return (
    <div className="wf-retry-box" data-testid="wf-retry-box">
      <div className="wf-retry-modes">
        <label className="wf-retry-mode-label">
          <input
            type="radio"
            name="retry-mode"
            value="restart"
            checked={mode === 'restart'}
            onChange={() => setMode('restart')}
          />
          {' Restart — '}
          {restartHint}
        </label>
        <label className="wf-retry-mode-label">
          <input
            type="radio"
            name="retry-mode"
            value="session"
            checked={mode === 'session'}
            onChange={() => setMode('session')}
          />
          {' Session — '}
          {RETRY_SESSION_HINT}
        </label>
      </div>
      <div className="wf-retry-actions">
        <button
          type="button"
          className="wf-signal wf-retry-submit"
          data-testid="wf-signal-retry"
          disabled={posting}
          onClick={() => onRetry(mode)}
        >
          Retry
        </button>
        {error ? (
          <span className="wf-signal-error" data-testid="wf-retry-error">
            {error.detail ?? error.title}
          </span>
        ) : null}
      </div>
    </div>
  );
}
