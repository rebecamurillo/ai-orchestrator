/**
 * The *Pause* control beside *Cancel run* while a Run runs (story 2-1, CAP-8): an inline
 * `ConfirmAction` that states the mechanism before it posts, and a plain line once the request
 * stands. Stateless apart from the confirm's own open flag; the island owns the post.
 */
import type { RunDetailOut } from '../../lib/run/detail';
import {
  PAUSE_CONFIRM_LABEL,
  PAUSE_CONFIRM_LINE,
  PAUSE_KEEP_LABEL,
  PAUSE_LABEL,
  PAUSE_REQUESTED_LINE,
  offersPause,
} from '../../lib/run/pause';
import ConfirmAction from './ConfirmAction';

interface Props {
  run: RunDetailOut['run'];
  admitted: RunDetailOut['admitted_signals'];
  disabled: boolean;
  onPause: () => void;
}

export default function PauseControl({ run, admitted, disabled, onPause }: Props) {
  if (run.pause_requested) {
    return (
      <span className="wf-stop-reason" role="status" data-testid="wf-pause-requested">
        {PAUSE_REQUESTED_LINE}
      </span>
    );
  }
  if (!offersPause(admitted)) return null;
  return (
    <ConfirmAction
      kind="pause"
      label={PAUSE_LABEL}
      line={PAUSE_CONFIRM_LINE}
      confirmLabel={PAUSE_CONFIRM_LABEL}
      keepLabel={PAUSE_KEEP_LABEL}
      disabled={disabled}
      onConfirm={onPause}
    />
  );
}
