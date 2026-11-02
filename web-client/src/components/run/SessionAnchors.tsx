/**
 * The anchor review a refused close opens (story 2-4, CAP-7, AD-23): each file the session
 * changed in `SPEC.md`, `stories.yaml`, `epics.yaml` or an `AGENTS.md`, with *Confirm* and
 * *Revert*. A revert is a message to the senior, so both controls wait for a running turn.
 * *Close with confirmed files* is live only when every listed file is confirmed.
 */
import {
  ANCHOR_BUSY_LINE,
  ANCHOR_LINE,
  CLOSE_CONFIRMED_LABEL,
  CONFIRMED_LABEL,
  CONFIRM_LABEL,
  NO_ANCHOR_LINE,
  REVERT_LABEL,
  allConfirmed,
  type AnchorEdit,
} from '../../lib/run/session';

interface Props {
  edits: readonly AnchorEdit[];
  confirmed: ReadonlySet<string>;
  turnRunning: boolean;
  posting: boolean;
  onToggle: (path: string) => void;
  onRevert: (path: string) => void;
  onClose: () => void;
}

export default function SessionAnchors({
  edits,
  confirmed,
  turnRunning,
  posting,
  onToggle,
  onRevert,
  onClose,
}: Props) {
  const held = turnRunning || posting;
  return (
    <div className="wf-session-anchors" data-testid="wf-session-anchors">
      <p className="wf-answer-hint">{edits.length === 0 ? NO_ANCHOR_LINE : ANCHOR_LINE}</p>
      {turnRunning ? <p className="wf-session-note">{ANCHOR_BUSY_LINE}</p> : null}
      <ul className="wf-session-anchor-list">
        {edits.map((edit) => (
          <li key={edit.path} className="wf-session-anchor">
            <span className="wf-session-anchor-kind">{edit.kind}</span>
            <span className="wf-session-anchor-path">{edit.path}</span>
            <button
              type="button"
              className="wf-signal"
              data-testid={`wf-session-confirm-${edit.path}`}
              aria-pressed={confirmed.has(edit.path)}
              disabled={held}
              onClick={() => onToggle(edit.path)}
            >
              {confirmed.has(edit.path) ? CONFIRMED_LABEL : CONFIRM_LABEL}
            </button>
            <button
              type="button"
              className="wf-signal"
              data-testid={`wf-session-revert-${edit.path}`}
              disabled={held}
              onClick={() => onRevert(edit.path)}
            >
              {REVERT_LABEL}
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="wf-signal"
        data-testid="wf-session-close-confirmed"
        disabled={held || !allConfirmed(edits, confirmed)}
        onClick={onClose}
      >
        {CLOSE_CONFIRMED_LABEL}
      </button>
    </div>
  );
}
