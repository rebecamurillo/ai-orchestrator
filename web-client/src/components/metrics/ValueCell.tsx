import { useStore } from '@nanostores/react';

import { formatValue, stateWords } from '../../lib/metrics/format';
import { $catalogue } from '../../stores/catalogue';
import { openOrigin, type OriginTarget } from '../../stores/metric-ui';
import '../../styles/metrics.css';
import CarriedMarker from './CarriedMarker';
import MissingWord from './MissingWord';

/** A value that opens its origin drawer; no catalogue entry, no cell (EXPERIENCE §5.2). */
export default function ValueCell({ target }: { target: OriginTarget }) {
  const { entries } = useStore($catalogue);
  const { value } = target;
  const entry = entries[value.metric_id];
  if (!entry) return null;

  const shown =
    value.value_num === null ? (value.missing ?? '') : formatValue(value.value_num, value.unit);
  const words = stateWords(value, target.subscription ?? false);

  return (
    <button
      type="button"
      className="metric-value-cell"
      aria-label={[target.runLabel, entry.label, shown, ...words].join(' ')}
      onClick={() => openOrigin(target)}
    >
      {value.value_num === null ? (
        <MissingWord word={shown} />
      ) : (
        <span className="metric-figure">{shown}</span>
      )}
      {value.carried_from !== null && <CarriedMarker from={value.carried_from} />}
    </button>
  );
}
