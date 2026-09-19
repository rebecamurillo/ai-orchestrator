/**
 * The Answer box (6.1, FR-18, UX-DR10, UX-DR17): a textarea under the Question block, the
 * line that says what *Resume with answer* will do to the branch, and the button.
 *
 * The one stateful component on this screen, and only just: the draft answer is local text
 * that no other component reads, so it lives here rather than in the island — which owns the
 * in-flight and 409 state exactly as it does for every other signal (`StopBody`'s own split).
 *
 * `disabled` while the textarea is empty is a rule and not a nicety: `signal_run` records
 * whatever the payload held, so an empty Answer would archive the Story file and re-dispatch
 * with a clause quoting nothing — a Run resumed into the same gap it stopped in.
 *
 * When `replyAvailable` is true (story 3-4), two labelled radio buttons let the Operator
 * choose the delivery mode before submitting. The mode is forwarded through `onAnswer`.
 */
import { useState } from 'react';

import type { components } from '../../api/schema';
import {
  ANSWER_LABEL,
  SESSION_ANSWER_HINT,
  answerHint,
  type AnswerTarget,
} from '../../lib/run/answer';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  target: AnswerTarget;
  onAnswer: (text: string, mode: string) => void;
  posting: boolean;
  error: ProblemDetail | null;
  /** When true, show the restart/session mode selector (story 3-4). */
  replyAvailable?: boolean;
}

export default function AnswerBox({
  target,
  onAnswer,
  posting,
  error,
  replyAvailable = false,
}: Props) {
  const [text, setText] = useState('');
  const [mode, setMode] = useState<'restart' | 'session'>('restart');
  const empty = text.trim().length === 0;

  return (
    <div className="wf-answer-box">
      <textarea
        className="wf-answer"
        data-testid="wf-answer"
        rows={5}
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label="Answer to the blocking condition"
      />
      {replyAvailable ? (
        <div className="wf-answer-modes" data-testid="wf-answer-modes">
          <label className="wf-answer-mode-label">
            <input
              type="radio"
              name="answer-mode"
              value="restart"
              checked={mode === 'restart'}
              onChange={() => setMode('restart')}
            />
            {' Restart — '}
            {answerHint(target)}
          </label>
          <label className="wf-answer-mode-label">
            <input
              type="radio"
              name="answer-mode"
              value="session"
              checked={mode === 'session'}
              onChange={() => setMode('session')}
            />
            {' Session — '}
            {SESSION_ANSWER_HINT}
          </label>
        </div>
      ) : (
        <p className="wf-answer-hint" data-testid="wf-answer-hint">
          {answerHint(target)}
        </p>
      )}
      <div className="wf-answer-actions">
        <button
          type="button"
          className="wf-signal wf-answer-submit"
          data-testid="wf-signal-answer"
          disabled={empty || posting}
          onClick={() => onAnswer(text.trim(), mode)}
        >
          {ANSWER_LABEL}
        </button>
        {error ? (
          <span className="wf-signal-error" data-testid="wf-answer-error">
            {error.detail ?? error.title}
          </span>
        ) : null}
      </div>
    </div>
  );
}
