/**
 * The Retry box (story 3-4, 4): mode selector and optional instruction for the Retry signal.
 * Always renders when `retry` is in `admitted_signals` — regardless of `replyAvailable`.
 * When `replyAvailable` is true, both restart and session radios are shown (session default).
 * When `replyAvailable` is false, only restart is available; the reason explains why.
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

/** Message shown when no session was recorded for this stop. */
export const NO_SESSION_REASON = 'No session was recorded for this stop; restart is the only path.';

/** Message shown when the harness does not support resume. */
export const NO_CAPABILITY_REASON =
  'This harness does not support resume; restart is the only path.';

interface Props {
  target: AnswerTarget;
  onRetry: (mode: string, text: string) => void;
  posting: boolean;
  error: ProblemDetail | null;
  /** Whether a session resume is available — drives the default radio selection and whether
   * the session radio is offered at all (story 4, 2026-09-25). */
  replyAvailable: boolean;
  /** Why session is unavailable: `"no_session"` or `"no_capability"`. `null` when available
   * or when the port is not wired (story 4, 2026-09-25). */
  resumeUnavailableReason: string | null;
}

export default function RetryBox({
  target,
  onRetry,
  posting,
  error,
  replyAvailable,
  resumeUnavailableReason,
}: Props) {
  const [mode, setMode] = useState<'restart' | 'session'>(replyAvailable ? 'session' : 'restart');
  const [text, setText] = useState('');
  const restartHint = answerHint(target) + RETRY_RESTART_HINT_SUFFIX;

  const unavailableMessage =
    resumeUnavailableReason === 'no_session'
      ? NO_SESSION_REASON
      : resumeUnavailableReason === 'no_capability'
        ? NO_CAPABILITY_REASON
        : null;

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
        {replyAvailable ? (
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
        ) : unavailableMessage ? (
          <p className="wf-retry-unavailable">{unavailableMessage}</p>
        ) : null}
      </div>
      <div className="wf-retry-text">
        <textarea
          className="wf-retry-instruction"
          data-testid="wf-retry-instruction"
          placeholder="Optional instruction to the agent (overrides the template retry prompt)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={posting}
          rows={2}
        />
      </div>
      <div className="wf-retry-actions">
        <button
          type="button"
          className="wf-signal wf-retry-submit"
          data-testid="wf-signal-retry"
          disabled={posting}
          onClick={() => onRetry(mode, text)}
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
