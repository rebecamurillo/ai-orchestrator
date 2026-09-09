/**
 * The Reject box (6.2, FR-19, UX-DR10): a "Reject with a reason" link that reveals a
 * textarea, the hint, and the submit button — `AnswerBox`'s own shape (6.1), with the one
 * difference the brief asks for: the plan is not wrong by default, so the textarea starts
 * collapsed behind a toggle rather than always shown.
 */
import { useState } from 'react';

import type { components } from '../../api/schema';
import type { AnswerTarget } from '../../lib/run/answer';
import { REJECT_LABEL, REJECT_TOGGLE_LABEL, rejectHint } from '../../lib/run/checkpoint';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  target: AnswerTarget;
  onReject: (text: string) => void;
  posting: boolean;
  error: ProblemDetail | null;
}

export default function RejectBox({ target, onReject, posting, error }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const empty = text.trim().length === 0;

  if (!open) {
    return (
      <p className="wf-reject-toggle">
        <button
          type="button"
          className="wf-reject-open"
          data-testid="wf-reject-open"
          onClick={() => setOpen(true)}
        >
          {REJECT_TOGGLE_LABEL}
        </button>
      </p>
    );
  }

  return (
    <div className="wf-reject-box">
      <textarea
        className="wf-reject"
        data-testid="wf-reject"
        rows={5}
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label="Reason for rejecting the plan"
      />
      <p className="wf-reject-hint" data-testid="wf-reject-hint">
        {rejectHint(target)}
      </p>
      <div className="wf-reject-actions">
        <button
          type="button"
          className="wf-signal wf-reject-submit"
          data-testid="wf-signal-reject"
          disabled={empty || posting}
          onClick={() => onReject(text.trim())}
        >
          {REJECT_LABEL}
        </button>
        {error ? (
          <span className="wf-signal-error" data-testid="wf-reject-error">
            {error.detail ?? error.title}
          </span>
        ) : null}
      </div>
    </div>
  );
}
