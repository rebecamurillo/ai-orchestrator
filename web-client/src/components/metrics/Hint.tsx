import type { KeyboardEventHandler, Ref } from 'react';

import type { components } from '../../api/schema';
import { methodOf } from '../../stores/catalogue';
import '../../styles/metrics.css';

type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export interface FlaggedMethod {
  methodId: string;
  runs: string[];
}

interface Props {
  entry: CatalogueEntryOut;
  methodId?: string;
  flagged?: FlaggedMethod[];
  ref?: Ref<HTMLDivElement>;
  onKeyDown?: KeyboardEventHandler<HTMLDivElement>;
}

function latestMethodId(entry: CatalogueEntryOut): string {
  const n = Math.max(...entry.methods.map((m) => m.n));
  return `${entry.id}@${n}`;
}

/** Every string here is the catalogue entry's own; only the five row terms are fixed. */
export default function Hint({ entry, methodId, flagged, ref, onKeyDown }: Props) {
  const used = methodId ?? latestMethodId(entry);
  const how =
    flagged && flagged.length > 1
      ? flagged.map((f) => ({
          key: f.methodId,
          text: methodOf(entry, f.methodId)?.description ?? '',
          runs: f.runs,
        }))
      : [{ key: used, text: methodOf(entry, used)?.description ?? '', runs: null }];

  return (
    <div
      role="dialog"
      aria-label={`how ${entry.label} is calculated`}
      className="metric-hint"
      tabIndex={-1}
      ref={ref}
      onKeyDown={onKeyDown}
    >
      <div className="metric-hint-head">
        <span className="metric-hint-label">{entry.label}</span>
        <span className="metric-hint-id">
          {entry.id} · {used}
        </span>
      </div>
      <dl className="metric-hint-rows">
        <dt>WHAT</dt>
        <dd>
          {entry.label} · {entry.unit}
        </dd>
        <dt>HOW</dt>
        <dd>
          {how.map((m) => (
            <p key={m.key}>
              {m.text}
              {m.runs && <span className="metric-hint-runs"> Runs: {m.runs.join(', ')}</span>}
            </p>
          ))}
        </dd>
        <dt>SOURCE</dt>
        <dd>{entry.source}</dd>
        {entry.limits && (
          <>
            <dt>LIMITS</dt>
            <dd>{entry.limits}</dd>
          </>
        )}
        <dt>MISSING</dt>
        <dd>{entry.missing_words.join(' · ')}</dd>
      </dl>
    </div>
  );
}
