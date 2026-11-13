import { useStore } from '@nanostores/react';
import { useEffect } from 'react';

import { formatValue, originRows, stateWords } from '../../lib/metrics/format';
import { $catalogue } from '../../stores/catalogue';
import { $openHint, $originTarget, closeHint, closeOrigin } from '../../stores/metric-ui';
import '../../styles/metrics.css';
import { DrawerPanel } from '../run/HelperDrawer';
import HintControl from './HintControl';
import MissingWord from './MissingWord';

function copy(text: string): void {
  if (navigator.clipboard) void navigator.clipboard.writeText(text);
}

/** Where a value came from. Escape closes whichever is open, the hint first (EXPERIENCE §7). */
export default function OriginDrawer() {
  const target = useStore($originTarget);
  const { entries } = useStore($catalogue);
  const open = target !== null;

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent): void {
      if (event.key !== 'Escape') return;
      if ($openHint.get() !== null) closeHint();
      else closeOrigin();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  const entry = target ? entries[target.value.metric_id] : undefined;
  if (!target || !entry) return null;
  const { value } = target;
  const words = stateWords(value, target.subscription ?? false);

  const head = (
    <div className="origin-drawer-head">
      <div className="origin-drawer-value">
        {value.value_num === null ? (
          <MissingWord word={value.missing ?? ''} />
        ) : (
          formatValue(value.value_num, value.unit)
        )}
      </div>
      <div className="origin-drawer-label">{entry.label}</div>
      {words.length > 0 && <div className="origin-drawer-state">{words.join(' · ')}</div>}
      <div className="origin-drawer-run">
        {target.runLabel} · {value.origin?.run_id}
      </div>
    </div>
  );

  return (
    <DrawerPanel className="origin-drawer" testId="origin-drawer" head={head} onClose={closeOrigin}>
      <table className="origin-drawer-rows">
        <tbody>
          {originRows(target, entry).map(([key, text, copyable]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td>
                {text}
                {copyable && (
                  <button
                    type="button"
                    className="step-drawer-copy"
                    aria-label={`copy ${key}`}
                    onClick={() => copy(text)}
                  >
                    copy
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {target.aggregate && (
        <p className="origin-drawer-aggregate">
          sum of {target.aggregate.n} {target.aggregate.noun}
          {target.onBreakdown && (
            <button type="button" className="step-drawer-copy" onClick={target.onBreakdown}>
              see the breakdown
            </button>
          )}
        </p>
      )}
      <div className="origin-drawer-foot">
        <HintControl metricId={value.metric_id} methodId={value.method_id} showLabel />
      </div>
    </DrawerPanel>
  );
}
