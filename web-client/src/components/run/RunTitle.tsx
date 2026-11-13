import { useEffect, useRef, useState, type KeyboardEvent } from 'react';

import type { components } from '../../api/schema';
import { EDIT_LABEL, labelPayload, labelState, MAX_LABEL, SAVE_LABEL } from '../../lib/run/label';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  label: string;
  byOperator: boolean;
  /** Resolves to the problem a refused save returned, or `null` when it applied. */
  onSave: (label: string | null) => Promise<ProblemDetail | null>;
}

/** The Run's title: its label, edited in place. Enter saves, Escape closes and sends nothing. */
export default function RunTitle({ label, byOperator, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const [shown, setShown] = useState<string | null>(null);
  const [error, setError] = useState<ProblemDetail | null>(null);
  const field = useRef<HTMLInputElement>(null);

  // the saved text stands in only until the next poll brings the server's label
  useEffect(() => setShown(null), [label]);
  useEffect(() => {
    if (editing) field.current?.focus();
  }, [editing]);

  function open(): void {
    setDraft(shown ?? label);
    setError(null);
    setEditing(true);
  }

  async function save(): Promise<void> {
    const next = labelPayload(draft).label;
    const problem = await onSave(next);
    if (problem) {
      setError(problem);
      return;
    }
    setShown(next);
    setError(null);
    setEditing(false);
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter') void save();
    else if (event.key === 'Escape') setEditing(false);
  }

  return (
    <span className="wf-title-group">
      {editing ? (
        <input
          ref={field}
          type="text"
          className="wf-label-input"
          aria-label="Run label"
          maxLength={MAX_LABEL}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
      ) : (
        <h1 className="wf-title" data-testid="wf-title">
          {shown ?? label}
        </h1>
      )}
      <button
        type="button"
        className="wf-label-edit"
        data-testid="wf-label-edit"
        onClick={editing ? () => void save() : open}
      >
        {editing ? SAVE_LABEL : EDIT_LABEL}
      </button>
      <span className="wf-label-state">{labelState(byOperator)}</span>
      {error ? <span className="wf-signal-error">{error.detail ?? error.title}</span> : null}
    </span>
  );
}
