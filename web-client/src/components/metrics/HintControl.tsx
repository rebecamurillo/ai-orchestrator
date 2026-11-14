import { useStore } from '@nanostores/react';
import { useEffect, useId, useRef, type KeyboardEvent } from 'react';

import { $catalogue } from '../../stores/catalogue';
import { $openHint, closeHint, openHint } from '../../stores/metric-ui';
import '../../styles/metrics.css';
import Hint, { type FlaggedMethod } from './Hint';

interface Props {
  metricId: string;
  methodId?: string;
  showLabel?: boolean;
  flagged?: FlaggedMethod[];
}

/** Opens on click, Enter or Space only — never on hover (EXPERIENCE §5.1). */
export default function HintControl({ metricId, methodId, showLabel, flagged }: Props) {
  const key = useId();
  const { entries } = useStore($catalogue);
  const open = useStore($openHint) === key;
  const button = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const entry = entries[metricId];

  useEffect(() => {
    if (open) dialog.current?.focus();
  }, [open]);

  // a hint whose control unmounts must not stay "open" and swallow the next Escape
  useEffect(
    () => () => {
      if ($openHint.get() === key) closeHint();
    },
    [key],
  );

  if (!entry) return null;

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key !== 'Escape' || !open) return;
    // the origin drawer listens on the document; its Escape yields to an open hint
    event.stopPropagation();
    closeHint();
    button.current?.focus();
  }

  return (
    <span className="metric-hint-anchor" onKeyDown={onKeyDown}>
      {showLabel && <span className="metric-label">{entry.label}</span>}
      <button
        type="button"
        ref={button}
        className="metric-hint-control"
        aria-label={`how ${entry.label} is calculated`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => (open ? closeHint() : openHint(key))}
      >
        i
      </button>
      {open && <Hint entry={entry} methodId={methodId} flagged={flagged} ref={dialog} />}
    </span>
  );
}
