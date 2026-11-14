import type { components } from '../../api/schema';
import { versionView } from '../../lib/metrics/format';
import '../../styles/metrics.css';

type ResultVersionOut = components['schemas']['ResultVersionOut'];

interface Props {
  versions: ResultVersionOut[];
  selected: number;
  onSelect: (n: number) => void;
}

export default function VersionSelector({ versions, selected, onSelect }: Props) {
  if (versions.length === 0) return null;
  const view = versionView(versions, selected);
  const label = (n: number) => `v${n}${n === view.latest ? ' latest' : ''}`;
  const all = versions.map((v) => v.n).sort((a, b) => a - b);

  return (
    <div className="metric-version">
      <div className="metric-version-segments">
        {view.segments.map((n) => (
          <button
            key={n}
            type="button"
            className="metric-version-segment"
            aria-pressed={n === selected}
            onClick={() => onSelect(n)}
          >
            {label(n)}
          </button>
        ))}
        {view.overflow && (
          <select
            aria-label="result version"
            value={selected}
            onChange={(event) => onSelect(Number(event.target.value))}
          >
            {all.map((n) => (
              <option key={n} value={n}>
                {label(n)}
              </option>
            ))}
          </select>
        )}
      </div>
      {view.detail && <p className="metric-version-detail">{view.detail}</p>}
    </div>
  );
}
