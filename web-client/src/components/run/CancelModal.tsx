/**
 * The Cancel run confirm (4.15, FR-20) — the only modal in the product. States what
 * cancelling actually does, in mechanism (NFR-8): processes killed, worktrees removed,
 * branches this Run created and never pushed deleted. Confirming posts `{kind: cancel,
 * payload: {confirm: true}}`; dismissing posts nothing.
 *
 * Stateless — the island owns whether it is open and the in-flight state; this component
 * only renders it and reports the two outcomes upward.
 */
interface Props {
  branch: string;
  posting: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}

export default function CancelModal({ branch, posting, onConfirm, onDismiss }: Props) {
  return (
    <div
      className="wf-cancel-modal"
      data-testid="wf-cancel-confirm"
      role="alertdialog"
      aria-modal="true"
    >
      <div className="wf-cancel-backdrop" onClick={onDismiss} />
      <div className="wf-cancel-modal-panel">
        <p className="wf-cancel-modal-text">
          cancel run {branch}? running processes are killed, worktrees removed, branches created by
          this run and never pushed are deleted
        </p>
        <div className="wf-cancel-modal-actions">
          <button
            type="button"
            className="wf-signal wf-cancel"
            data-testid="wf-cancel-confirm-yes"
            disabled={posting}
            onClick={onConfirm}
          >
            Cancel run
          </button>
          <button
            type="button"
            className="wf-signal"
            data-testid="wf-cancel-confirm-no"
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
