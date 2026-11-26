/**
 * The full-plane frame of the initiative confirmations: focus starts on the non-destructive
 * action (`data-autofocus`), Escape and the scrim dismiss, Tab wraps inside the panel, and the
 * opener gets focus back on unmount.
 */
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react';

interface Props {
  labelId: string;
  head: string;
  onDismiss(): void;
  children: ReactNode;
}

const FOCUSABLE = 'button, [href], textarea, input, select, [tabindex]:not([tabindex="-1"])';

export default function ConfirmPlane({ labelId, head, onDismiss, children }: Props) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    if (e.key === 'Escape') {
      e.preventDefault();
      onDismiss();
      return;
    }
    if (e.key !== 'Tab') return;
    const items = Array.from(panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
      (el) => !(el as HTMLButtonElement).disabled,
    );
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !panel.current?.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !panel.current?.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="ini-plane">
      <div className="ini-plane-scrim" onClick={onDismiss} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
        className="ini-plane-panel"
        onKeyDown={onKeyDown}
      >
        <p id={labelId} className="ini-plane-head">
          {head}
        </p>
        {children}
      </div>
    </div>
  );
}
