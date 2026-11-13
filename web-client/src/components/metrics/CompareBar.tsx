import {
  addRunsHref,
  ADD_RUNS_WORD,
  BLIND_WORD,
  EXPORT_LABEL,
  type CompareState,
} from '../../lib/metrics/compare';
import { SET_LABELS, VIEW_LABELS } from '../../lib/run/metrics-tab';
import '../../styles/metrics-compare.css';

interface Props {
  state: CompareState;
  projectId: string;
  onChange: (next: CompareState) => void;
  onExport: () => void;
  exportLine: string;
}

export default function CompareBar({ state, projectId, onChange, onExport, exportLine }: Props) {
  return (
    <div className="compare-bar-wrap">
      <div className="compare-bar">
        <div className="compare-segments" role="group" aria-label="view">
          {(['table', 'chart'] as const).map((view) => (
            <button
              key={view}
              type="button"
              className="metric-version-segment"
              aria-pressed={state.view === view}
              aria-disabled={view === 'chart' ? true : undefined}
              disabled={view === 'chart'}
              data-testid={`compare-view-${view}`}
              onClick={() => onChange({ ...state, view })}
            >
              {VIEW_LABELS[view]}
            </button>
          ))}
        </div>
        <div className="compare-segments" role="group" aria-label="metrics">
          {(['headline', 'all'] as const).map((set) => (
            <button
              key={set}
              type="button"
              className="metric-version-segment"
              aria-pressed={state.set === set}
              data-testid={`compare-set-${set}`}
              onClick={() => onChange({ ...state, set })}
            >
              {SET_LABELS[set]}
            </button>
          ))}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={state.blind}
          className="metric-version-segment"
          data-testid="compare-blind"
          onClick={() => onChange({ ...state, blind: !state.blind })}
        >
          {BLIND_WORD}
        </button>
        <a data-testid="compare-add-runs" href={addRunsHref(projectId, state.runIds)}>
          {ADD_RUNS_WORD}
        </a>
        <button
          type="button"
          className="compare-export"
          data-testid="compare-export"
          onClick={onExport}
        >
          {EXPORT_LABEL}
        </button>
      </div>
      <p role="status" className="compare-export-line" data-testid="compare-export-line">
        {exportLine}
      </p>
    </div>
  );
}
