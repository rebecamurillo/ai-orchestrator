import { compareHref, OWN_LABEL_WORD, RUNNING_WORD, type RunRowView } from '../../lib/metrics/home';
import { tokenSignal } from '../../lib/board/format';
import '../../styles/metrics-home.css';
import HintControl from './HintControl';

interface Props {
  rows: RunRowView[];
  selected: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
}

const HEADS = ['', 'status', 'label', 'run', 'template', 'harness', 'base → branch', 'wall-clock'];

export default function MetricsRunsTable({ rows, selected, onToggle, onClear }: Props) {
  return (
    <>
      <div className="metrics-scroll">
        <table className="metrics-table" data-testid="metrics-runs-table">
          <thead>
            <tr>
              {HEADS.map((head, i) => (
                <th key={i}>{head}</th>
              ))}
              <th>
                gateway <HintControl metricId="cost.gateway" />
              </th>
              <th>
                harness <HintControl metricId="cost.harness" />
              </th>
              <th>metrics</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} data-testid={`metrics-run-row-${row.id}`}>
                <td>
                  {row.select === 'box' ? (
                    <button
                      type="button"
                      role="checkbox"
                      className="metrics-box"
                      aria-checked={selected.includes(row.id)}
                      aria-label={`select ${row.label}`}
                      data-testid={`metrics-run-select-${row.id}`}
                      onClick={() => onToggle(row.id)}
                    >
                      {selected.includes(row.id) ? '■' : '□'}
                    </button>
                  ) : row.select === 'running' ? (
                    <span>{RUNNING_WORD}</span>
                  ) : null}
                </td>
                <td>
                  <span className="metrics-token" data-signal={tokenSignal(row.token)}>
                    {row.token}
                  </span>
                </td>
                <td>
                  {row.label}
                  {row.ownLabel && <span className="metrics-own"> {OWN_LABEL_WORD}</span>}
                </td>
                <td>
                  <a href={row.href}>{row.shortId}</a>
                </td>
                <td>{row.template}</td>
                <td>{row.harness}</td>
                <td>{row.baseBranch}</td>
                <td>{row.wallClock}</td>
                <td>{row.gateway}</td>
                <td>{row.harnessSpend}</td>
                <td>{row.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="metrics-selection">
        <span data-testid="metrics-selection-count">{selected.length} selected</span>
        {selected.length >= 2 ? (
          <a href={compareHref(selected)} data-testid="metrics-compare">
            COMPARE {selected.length} RUNS
          </a>
        ) : (
          <button type="button" disabled data-testid="metrics-compare">
            COMPARE {selected.length} RUNS
          </button>
        )}
        <button type="button" data-testid="metrics-clear" onClick={onClear}>
          clear
        </button>
      </div>
    </>
  );
}
