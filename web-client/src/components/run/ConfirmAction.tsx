/**
 * An inline confirm for one signal button (6.4, FR-20, NFR-8) — *not* a modal, which the
 * brief rules out: the line appears in the stop body's own action row, beside the buttons it
 * belongs to, and nothing is dimmed or trapped behind it.
 *
 * **Why this component owns its open/closed state.** `StopBody` is stateless by design and
 * every one of its unit tests renders it through `renderToStaticMarkup`. Keeping the flag
 * here means the static render *is* the closed state — the same single
 * `data-testid="wf-signal-{kind}"` button that stop body has always shown — so a confirm was
 * added without changing what any existing spec sees. It is the same split `AnswerBox` draws
 * for its own draft text: local state no other component reads.
 *
 * Written to be reused: 6.5's *Skip epic* is this component with a different `kind`, `line`
 * and `confirmLabel`. Nothing about skipping a story is hard-coded below.
 */
import { useState } from 'react';

interface Props {
  /** The signal this confirms — the trigger's test id and the confirm's own id prefix. */
  kind: string;
  /** The trigger button's word. */
  label: string;
  /** What confirming will do, in mechanism (NFR-8). */
  line: string;
  /** The word on the button that posts the signal. */
  confirmLabel: string;
  /** The word on the button that posts nothing and closes the confirm. */
  keepLabel: string;
  /** True while any signal on this screen is in flight — every button is refused meanwhile. */
  disabled: boolean;
  onConfirm: () => void;
}

export default function ConfirmAction({
  kind,
  label,
  line,
  confirmLabel,
  keepLabel,
  disabled,
  onConfirm,
}: Props) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        className="wf-signal"
        data-testid={`wf-signal-${kind}`}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        {label}
      </button>
    );
  }

  return (
    <span className="wf-confirm" data-testid={`wf-confirm-${kind}`}>
      <span className="wf-confirm-line" role="status" data-testid={`wf-confirm-${kind}-line`}>
        {line}
      </span>
      <button
        type="button"
        className="wf-signal wf-confirm-yes"
        data-testid={`wf-confirm-${kind}-yes`}
        disabled={disabled}
        onClick={onConfirm}
      >
        {confirmLabel}
      </button>
      <button
        type="button"
        className="wf-signal"
        data-testid={`wf-confirm-${kind}-keep`}
        disabled={disabled}
        onClick={() => setOpen(false)}
      >
        {keepLabel}
      </button>
    </span>
  );
}
