/**
 * The ARTIFACTS column's own editor (6.3, FR-19, UX-DR9, UX-DR17): a textarea holding the
 * file's own text, the hint that says what *Save* will do to the branch, and the Save /
 * Cancel controls — `AnswerBox`'s own shape (6.1), shown alongside the textarea rather than
 * only after a successful save, the same way that box's own hint is.
 *
 * The draft text is local state no other component reads (`AnswerBox`'s own reasoning): the
 * island owns in-flight and error state exactly as it does for every other write on this
 * screen (`ArtifactsPanel`'s own split of `RunDetail.tsx`'s established pattern).
 */
import { useState } from 'react';

import type { components } from '../../api/schema';
import { editHint } from '../../lib/run/artifacts';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  path: string;
  initialContent: string;
  branch: string;
  saving: boolean;
  error: ProblemDetail | null;
  onSave: (content: string) => void;
  onCancel: () => void;
}

export default function FileEditor({
  path,
  initialContent,
  branch,
  saving,
  error,
  onSave,
  onCancel,
}: Props) {
  const [text, setText] = useState(initialContent);

  return (
    <div className="wf-editor-box">
      <textarea
        className="wf-editor"
        data-testid="wf-editor"
        rows={16}
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label={`Edit ${path}`}
      />
      <p className="wf-editor-hint" data-testid="wf-editor-hint">
        {editHint(branch)}
      </p>
      <div className="wf-editor-actions">
        <button
          type="button"
          className="wf-signal wf-editor-save"
          data-testid="wf-editor-save"
          disabled={saving}
          onClick={() => onSave(text)}
        >
          Save
        </button>
        <button
          type="button"
          className="wf-editor-cancel"
          data-testid="wf-editor-cancel"
          disabled={saving}
          onClick={onCancel}
        >
          Cancel
        </button>
        {error ? (
          <span className="wf-signal-error" data-testid="wf-editor-error">
            {error.detail ?? error.title}
          </span>
        ) : null}
      </div>
    </div>
  );
}
