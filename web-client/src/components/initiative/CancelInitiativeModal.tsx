/**
 * The Cancel initiative confirm (S8, AD-13). Follows `CancelModal.tsx`'s own structure —
 * outer div (fixed inset, flex centre), backdrop div, panel — the same precedent
 * `ArtifactModal.tsx` already follows for its own, different subject: a shared component
 * would need a prop for "which sentence" and "which testids" that costs more than the
 * duplication it would save, so this is its own component rather than a widened
 * `CancelModal`. Confirming posts `{kind: cancel}` to `POST /initiatives/{slug}/signals`;
 * dismissing posts nothing.
 *
 * Stateless — the island owns whether it is open and the in-flight state; this component
 * only renders it and reports the two outcomes upward. The confirm sentence itself is
 * `lib/initiative/view.ts::cancelConfirmText`, not restated here, so the copy a unit test
 * checks and the copy this panel renders can never drift apart.
 */
import { cancelConfirmText } from '../../lib/initiative/view';

interface Props {
  slug: string;
  posting: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}

export default function CancelInitiativeModal({ slug, posting, onConfirm, onDismiss }: Props) {
  return (
    <div
      className="newin-cancel-modal"
      data-testid="newin-cancel-confirm"
      role="alertdialog"
      aria-modal="true"
    >
      <div className="newin-cancel-backdrop" onClick={onDismiss} />
      <div className="newin-cancel-modal-panel">
        <p className="newin-cancel-modal-text">{cancelConfirmText(slug)}</p>
        <div className="newin-cancel-modal-actions">
          <button
            type="button"
            className="newin-signal newin-cancel"
            data-testid="newin-cancel-confirm-yes"
            disabled={posting}
            onClick={onConfirm}
          >
            Cancel initiative
          </button>
          <button
            type="button"
            className="newin-signal"
            data-testid="newin-cancel-confirm-no"
            disabled={posting}
            onClick={onDismiss}
          >
            Keep running
          </button>
        </div>
      </div>
    </div>
  );
}
