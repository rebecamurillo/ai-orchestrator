import type { components } from '../../api/schema';
import { tokenSignal } from '../../lib/board/format';
import { OWN_LABEL_WORD } from '../../lib/metrics/home';
import {
  headerView,
  NOT_RUN_WORD,
  RECALC_WORD,
  recalcHref,
  REMOVE_WORD,
} from '../../lib/metrics/compare';
import '../../styles/metrics-compare.css';

type CompareRunHeaderOut = components['schemas']['CompareRunHeaderOut'];

interface Props {
  header: CompareRunHeaderOut;
  canRemove: boolean;
  diffSize: string | undefined;
  onRemove: (id: string) => void;
  onVersion: (id: string, n: number, latest: number | null) => void;
}

/** One Run's column head: every word is the API's header field, placed. */
export default function CompareHeader({ header, canRemove, diffSize, onRemove, onVersion }: Props) {
  const view = headerView(header);
  return (
    <th scope="col" className="compare-col" data-testid={`compare-col-${view.id}`}>
      <div className="compare-col-top">
        <span className="metrics-token" data-signal={tokenSignal(view.token)}>
          {view.token}
        </span>
        <a href={view.href}>{view.shortId}</a>
        <button
          type="button"
          className="compare-remove"
          data-testid={`compare-remove-${view.id}`}
          disabled={!canRemove}
          onClick={() => onRemove(view.id)}
        >
          {REMOVE_WORD}
        </button>
      </div>
      <div className="compare-col-label">
        {view.label}
        {view.ownLabel && <span className="compare-under"> {OWN_LABEL_WORD}</span>}
      </div>
      <div className="compare-under">{view.template}</div>
      <div className="compare-under">{view.harness}</div>
      {view.models.map((line) => (
        <div key={line} className="compare-under">
          {line}
        </div>
      ))}
      <div className="compare-under">{view.base}</div>
      <div className="compare-under">{view.status}</div>
      {view.stories !== null && <div className="compare-under">{view.stories}</div>}
      {view.versions.length > 0 && (
        <div className="metric-version-segments">
          {view.versions.map((n) => (
            <button
              key={n}
              type="button"
              className="metric-version-segment"
              aria-pressed={n === view.selected}
              data-testid={`compare-version-${view.id}-${n}`}
              onClick={() => onVersion(view.id, n, view.latest)}
            >
              {`v${n}${n === view.latest ? ' latest' : ''}`}
            </button>
          ))}
        </div>
      )}
      {diffSize === NOT_RUN_WORD && (
        <a className="compare-under" href={recalcHref(view.id)}>
          {RECALC_WORD}
        </a>
      )}
    </th>
  );
}
