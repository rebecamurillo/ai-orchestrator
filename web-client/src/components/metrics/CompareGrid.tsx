import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import {
  cellTarget,
  deltaOf,
  DIFF_SIZE_LABEL,
  groupRows,
  methodsLine,
  METHODS_DIFFER,
  NO_CELL,
  NOT_RUN_WORD,
  RECALC_WORD,
  recalcHref,
  runCells,
  SAME_WORK_LABEL,
  SAME_WORK_SUB,
  sameWorkView,
  STATIC_GROUP,
  type CompareState,
} from '../../lib/metrics/compare';
import { $catalogue } from '../../stores/catalogue';
import '../../styles/metrics-compare.css';
import CompareHeader from './CompareHeader';
import HintControl from './HintControl';
import MissingWord from './MissingWord';
import ValueCell from './ValueCell';

type CompareOut = components['schemas']['CompareOut'];

interface Props {
  payload: CompareOut;
  set: CompareState['set'];
  onRemove: (id: string) => void;
  onVersion: (id: string, n: number, latest: number | null) => void;
}

export default function CompareGrid({ payload, set, onRemove, onVersion }: Props) {
  const { entries } = useStore($catalogue);
  const work = sameWorkView(payload);
  const groups = groupRows(entries, payload.metrics, set);
  const span = payload.runs.length + 1;

  return (
    <div className="compare-frame">
      <table className="compare-grid" data-testid="compare-grid">
        <thead>
          <tr>
            <th scope="col" className="compare-metric">
              metric
            </th>
            {payload.runs.map((h) => (
              <CompareHeader
                key={h.run_id}
                header={h}
                canRemove={payload.runs.length > 2}
                diffSize={payload.diff_size[h.run_id]}
                onRemove={onRemove}
                onVersion={onVersion}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          <tr data-testid="compare-same-work">
            <th scope="row" className="compare-metric">
              {SAME_WORK_LABEL}
              <div className="compare-under">{SAME_WORK_SUB}</div>
              {work.flag !== null && <div className="compare-flag">{work.flag}</div>}
            </th>
            {payload.runs.map((h) => (
              <td key={h.run_id}>
                <div>{work.cells[h.run_id].commits}</div>
                <div className="compare-under">{work.cells[h.run_id].initiative}</div>
                <div className="compare-under">{work.cells[h.run_id].stories}</div>
              </td>
            ))}
          </tr>
          {groups.map(({ group, rows }) => (
            <GroupRows key={group} group={group} rows={rows} payload={payload} span={span} />
          ))}
          <tr className="compare-grp" data-testid="compare-group-static">
            <th colSpan={span} scope="colgroup">
              {STATIC_GROUP}
            </th>
          </tr>
          <tr data-testid="compare-row-diff-size">
            <th scope="row" className="compare-metric">
              {DIFF_SIZE_LABEL}
            </th>
            {payload.runs.map((h) => {
              const word = payload.diff_size[h.run_id] ?? NO_CELL;
              return (
                <td key={h.run_id} data-testid={`compare-diff-size-${h.run_id}`}>
                  <MissingWord word={word} />
                  {word === NOT_RUN_WORD && (
                    <>
                      {' '}
                      <a href={recalcHref(h.run_id)}>{RECALC_WORD}</a>
                    </>
                  )}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function GroupRows({
  group,
  rows,
  payload,
  span,
}: {
  group: string;
  rows: components['schemas']['CompareMetricOut'][];
  payload: CompareOut;
  span: number;
}) {
  const { entries } = useStore($catalogue);
  const slug = group.split(' ')[0].toLowerCase();
  return (
    <>
      <tr className="compare-grp" data-testid={`compare-group-${slug}`}>
        <th colSpan={span} scope="colgroup">
          {group}
        </th>
      </tr>
      {rows.map((m) => (
        <tr key={m.metric_id} data-testid={`compare-row-${m.metric_id}`}>
          <th scope="row" className="compare-metric">
            <span className="metric-label">{entries[m.metric_id].label}</span>
            <HintControl metricId={m.metric_id} />
            {m.methods_differ && <span className="compare-flag"> {METHODS_DIFFER}</span>}
          </th>
          {payload.runs.map((h) => {
            const cells = runCells(m, h.run_id);
            const methods = methodsLine(m, h.run_id);
            const delta = deltaOf(m, h.run_id);
            return (
              <td key={h.run_id} data-testid={`compare-cell-${m.metric_id}-${h.run_id}`}>
                {cells.length === 0
                  ? NO_CELL
                  : cells.map((c) => (
                      <ValueCell
                        key={c.method_id + c.scope_key}
                        target={cellTarget(c, m.metric_id, h)}
                      />
                    ))}
                {methods ? <div className="compare-under">{methods}</div> : null}
                {delta !== null && <div className="compare-under">{delta}</div>}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}
